# Execution Trace Tables to Verify Ordering on Success and Failure in Spring AOP

## 1. Purpose of the Execution Trace Table

When multiple Spring `@Aspect` beans intercept the same method of a Spring bean, looking solely at `@Before`, `@After`, `@AfterReturning`, or `@AfterThrowing` is not enough to tell **which line appears first**. A method can pass through multiple interceptor layers; order on the **way in** differs from order on the **way out**, and when the method throws an exception, success callbacks do not run at all.

An **execution trace table** is a way to record each milestone in the observed order, for example:

~~~text
Caller
  -> Spring AOP proxy
       -> OuterAspect @Around: enter
            -> InnerAspect @Around: enter
                 -> OutcomeAspect @AfterReturning / @AfterThrowing
                 -> target method
            <- InnerAspect @Around: finally
       <- OuterAspect @Around: finally
  <- Caller receives value or exception
~~~

Note that the diagram above is a **layering diagram**, not log order: the `@AfterReturning` or `@AfterThrowing` callback runs **after the target method finishes**, before the chain returns control to the outer around advice methods.

This lesson focuses **specifically on proxy-based Spring Aspect / Spring AOP**, within the **Advice Ordering** section. Learners will:

1. Build traces with columns for **step, layer, event, reason, and outcome branch**.
2. Understand `@Order`/`Ordered`: **smaller number = higher precedence**, entering first and exiting last.
3. Construct separate tables for **normal return** and **exceptional exit**.
4. Distinguish `@AfterReturning`, `@AfterThrowing`, `@After`, and `finally` inside `@Around`.
5. Write a **Maven + Java 17+** example with three explicitly ordered Spring aspects, an event collector, and self-checking assertions.
6. Debug cases of missing logs, duplicate logs, early-returning advice, `this.method()` self-calls, or exceptions handled inside the method.

**The goal is not** to study generic Aspect theory, but to verify **the real execution sequence on a Spring AOP proxy of a Spring-managed bean**.

## 2. Rules for Reading a Spring Trace Table

Before recording a table, identify **who the caller is and what object reference the caller holds**. If the caller invokes a plain Java object created via `new` outside Spring, or an internal `this.method()` call on the target bypassing the proxy, advice may not appear at all.

Suppose three aspects have this ordering:

| Aspect | Declaration | Order / Precedence | Role |
| --- | --- | --- | --- |
| `OuterTraceAspect` | `@Aspect @Order(10)` | **Highest** among the three aspects | `@Around`, logs enter, after, finally |
| `InnerTraceAspect` | `@Aspect @Order(20)` | Middle | `@Around`, logs enter, after, finally |
| `OutcomeAspect` | `@Aspect @Order(30)` | Lowest | `@AfterReturning` on success; `@AfterThrowing` on failure |

When **all three pointcuts match the same invocation**:

- 10 enters before 20; 20 enters before 30.
- Outer(10) wraps Inner(20), while Outcome(30) sits deeper.
- As the result or exception travels back out, Outcome(30) handles the matching branch first.
- Next, Inner(20) executes the code after `proceed()` if successful, then `finally`.
- Finally, Outer(10) executes the code after `proceed()` if successful, then `finally`.
- The caller receives the result or exception only after all interceptors finish unwinding.

**Common pitfall:** "10 has higher priority than 20" does not mean **every statement in aspect 10** appears before **every statement in aspect 20**. Structurally, aspect 10 is the **outer wrapper**, so its trailing part occurs **after** aspect 20.

## 3. From the Interceptor Chain to a Verifiable Table

Model of a Spring proxy:

~~~text
                       ====== WAY IN ======>
Caller -> [A: order 10] -> [B: order 20] -> [C: order 30] -> Target
Caller <- [A: finally] <- [B: finally] <- [C: outcome] <- Target result/throw
                       <====== WAY OUT =======
~~~

In this example, C does not use `@Around`; it has two **branch-selecting** advice methods:

- `@AfterReturning` when the target execution returns normally.
- `@AfterThrowing` when the target execution exits by throwing an exception.

Because C is an inner interceptor relative to B and A, both C's success callback and C's failure callback appear **before** the exit portions of B and A.

### 3.1. Ideal Success Trace Table

| Step | Location | Event | Why |
| ---: | --- | --- | --- |
| 1 | A(10) | `A: enter` | Spring proxy enters the highest-precedence aspect |
| 2 | B(20) | `B: enter` | A calls `proceed()` to enter layer B |
| 3 | Target | `target: begin` | B calls `proceed()`, chain reaches the method |
| 4 | Target | `target: return OK` | Method completes normally |
| 5 | C(30) | `C: returned OK` | `@AfterReturning` receives the String value |
| 6 | B(20) | `B: after` | B's `proceed()` returned normally |
| 7 | B(20) | `B: finally` | B's Java finally block executes |
| 8 | A(10) | `A: after` | A's `proceed()` returned normally |
| 9 | A(10) | `A: finally` | A's Java finally block executes |
| 10 | Caller | `caller result: OK` | Proxy call returned the result |

The two "after" entries in the table are **code placed after `proceed()` inside `@Around`**, not the `@After` annotation. Without distinguishing them, readers may mistakenly think Spring is ordering advice wrongly.

### 3.2. Trace Table When the Target Throws an Exception

| Step | Location | Event | Why |
| ---: | --- | --- | --- |
| 1 | A(10) | `A: enter` | Outer aspect receives the call |
| 2 | B(20) | `B: enter` | A proceeded |
| 3 | Target | `target: begin` | B proceeded |
| 4 | Target | `target: throw boom` | Method throws IllegalStateException |
| 5 | C(30) | `C: throwing IllegalStateException` | `@AfterThrowing` matches the exception |
| 6 | B(20) | `B: finally` | B's `proceed()` threw; finally still runs |
| 7 | A(10) | `A: finally` | A's `proceed()` threw; finally still runs |
| 8 | Caller | `caller caught: boom` | Caller catches the original exception |

**There is no `B: after`, `A: after`, or `C: returned OK`** because `proceed()` did not return normally. Instead, the `finally` blocks of the around advice methods **that were entered** still run as the stack unwinds.

**This is the central distinction to capture in traces:** If a test only verifies that "A enters before B enters," you have not checked ordering on the failure path. You must assert the **complete sequence** of both branches separately.

## 4. Preconditions for the Trace Above to Hold

A reliable trace table must state its preconditions clearly:

1. `OuterTraceAspect`, `InnerTraceAspect`, and `OutcomeAspect` are all **Spring-managed aspect beans**.
2. Spring Framework has `@EnableAspectJAutoProxy` or equivalent AOP infrastructure enabled.
3. The target is a **Spring bean** with a Spring AOP proxy, not an object instantiated manually via `new`.
4. All three pointcuts match the exact method called by the caller.
5. The aspects have **distinct** orders: 10, 20, 30.
6. Both `@Around` advice methods call `ProceedingJoinPoint.proceed()` **exactly once**.
7. Advice does not alter the result/exception, does not short-circuit, and does not throw logging errors.
8. The illustrative project registers no other transaction/cache/security advisors on the target.
9. All calls in the demo are **synchronous** and run on the same thread.
10. Events are recorded in exact synchronous call order without asynchronous logging reordering display.

If preconditions change, the trace table may need to change too. Do not declare a fixed sequence when aspects omit `@Order`/`Ordered` or an outer advisor can terminate early.

## 5. Runnable Maven / Java 17+ Project

We build a small Spring Framework application to **observe** and **programmatically verify** the order shown in the two tables.

### 5.1. Directory Structure

~~~text
spring-aop-trace-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── TraceEvents.java
    ├── TransferService.java
    ├── OuterTraceAspect.java
    ├── InnerTraceAspect.java
    ├── OutcomeAspect.java
    └── Main.java
~~~

Illustrative environment: **Java 17+**, Maven, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**. Spring AOP uses AspectJ annotation syntax and pointcut expressions, but **does not use compile-time or load-time bytecode weaving** in this example.

### 5.2. Maven `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-trace-demo</artifactId>
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

The Spring Framework BOM keeps Spring modules on the same version. For Spring Boot applications, use Boot's dependency management rather than forcing a version set copied from an example project.

### 5.3. Event Recorder `TraceEvents.java`

~~~java
package example;

import java.util.ArrayList;
import java.util.List;

public final class TraceEvents {
    private final List<String> events = new ArrayList<>();

    public void record(String event) {
        events.add(event);
        System.out.println(event);
    }

    public List<String> drain() {
        List<String> result = List.copyOf(events);
        events.clear();
        return result;
    }
}
~~~

This class stores the exact event sequence and prints to console. `Main` takes a snapshot via `drain()` and uses `List.equals(...)` to check **ordering**, not just event presence.

**Scope:** The demo runs synchronously, single-threaded, one invocation at a time; `ArrayList` and `drain()` **are not safe** for mixing concurrent requests. In production or parallel integration tests, use collectors separated by invocation ID (or properly cleaned-up thread-local scopes), and assert only on event sequences belonging to **the same invocation**. A single global `Collections.synchronizedList` alone also fails to solve interleaving events from multiple invocations.

### 5.4. Target `TransferService.java`

~~~java
package example;

public class TransferService {

    private final TraceEvents trace;

    public TransferService(TraceEvents trace) {
        this.trace = trace;
    }

    public String transfer(boolean fail) {
        trace.record("target: begin");

        if (fail) {
            trace.record("target: throw boom");
            throw new IllegalStateException("boom");
        }

        trace.record("target: return OK");
        return "OK";
    }
}
~~~

One target with two branches:

- `transfer(false)` returns `String "OK"`;
- `transfer(true)` throws `IllegalStateException("boom")`.

Business data and exceptions are preserved across all aspects. There is no sleep, randomness, network call, or concurrency to make stdout nondeterministic.

### 5.5. Outer Aspect `OuterTraceAspect.java`

~~~java
package example;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class OuterTraceAspect {

    private final TraceEvents trace;

    public OuterTraceAspect(TraceEvents trace) {
        this.trace = trace;
    }

    @Around("execution(public * example.TransferService.transfer(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        trace.record("A: enter");

        try {
            Object result = pjp.proceed();
            trace.record("A: after");
            return result;
        } finally {
            trace.record("A: finally");
        }
    }
}
~~~

Explanation:

1. Order 10 is the highest precedence among the three aspects in the demo.
2. `A: enter` is printed **before** calling `proceed()`.
3. `proceed()` advances to inner advisors, not necessarily straight to the target immediately.
4. `A: after` is printed **only when `proceed()` returns normally**.
5. `A: finally` is printed on both success and failure once the around advice has been entered.
6. The method uses `return result` to return the original value unchanged.
7. The method declares `throws Throwable` and does not swallow the target's exception.

When an exception escapes from B/C/target, `trace.record("A: after")` is skipped, yet Java `finally` still executes.

### 5.6. Middle Aspect `InnerTraceAspect.java`

~~~java
package example;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(20)
public class InnerTraceAspect {

    private final TraceEvents trace;

    public InnerTraceAspect(TraceEvents trace) {
        this.trace = trace;
    }

    @Around("execution(public * example.TransferService.transfer(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        trace.record("B: enter");

        try {
            Object result = pjp.proceed();
            trace.record("B: after");
            return result;
        } finally {
            trace.record("B: finally");
        }
    }
}
~~~

Aspect B has the same structure as A, differing only in order 20. Since `20 > 10`, B is **wrapped outside** by A. This clear structure reveals:

- On the way in: A enter then B enter.
- On the success way out: B after/finally then A after/finally.
- On the failure way out: B finally then A finally.

**Do not** confuse the code label `B: after` with an `@After` advice. It is simply a Java statement inside `@Around` running after `proceed()`.

### 5.7. Outcome-Distinguishing Aspect `OutcomeAspect.java`

~~~java
package example;

import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(30)
public class OutcomeAspect {

    private final TraceEvents trace;

    public OutcomeAspect(TraceEvents trace) {
        this.trace = trace;
    }

    @AfterReturning(
        pointcut = "execution(public * example.TransferService.transfer(..))",
        returning = "result",
        argNames = "result"
    )
    public void onReturned(String result) {
        trace.record("C: returned " + result);
    }

    @AfterThrowing(
        pointcut = "execution(public * example.TransferService.transfer(..))",
        throwing = "error",
        argNames = "error"
    )
    public void onThrown(IllegalStateException error) {
        trace.record("C: throwing " + error.getClass().getSimpleName());
    }
}
~~~

Because `OutcomeAspect` has precedence 30, C's callbacks sit inside A and B during a normal invocation of the demo.

- When the target returns `String "OK"`, `@AfterReturning` with `returning = "result"` binds the result to `String result` and prints `C: returned OK`.
- When the target throws `IllegalStateException`, `@AfterReturning` **does not run**, while `@AfterThrowing` with `throwing = "error"` binds the exception to `IllegalStateException error` and prints the exception type.
- Two advice methods **of different types** handle two **mutually exclusive** branches of the same target method, so the demo does not rely on ordering between two same-type advice methods in one class.
- `argNames` explicitly specifies the binding names matching `returning` / `throwing`, avoiding reliance on whether the compiler preserves method parameter names.
- `@AfterThrowing` **does not swallow the exception** merely because the advice method returns `void`; the target exception still propagates to A/B/caller unless handled by another interceptor.

**Scope of typed binding:** `String` and `IllegalStateException` narrow each advice's matching condition; do not claim they will run for **every** return type or throwable type in an application.

### 5.8. Spring Configuration `AppConfig.java`

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public TraceEvents traceEvents() {
        return new TraceEvents();
    }

    @Bean
    public TransferService transferService(TraceEvents trace) {
        return new TransferService(trace);
    }

    @Bean
    public OuterTraceAspect outerTraceAspect(TraceEvents trace) {
        return new OuterTraceAspect(trace);
    }

    @Bean
    public InnerTraceAspect innerTraceAspect(TraceEvents trace) {
        return new InnerTraceAspect(trace);
    }

    @Bean
    public OutcomeAspect outcomeAspect(TraceEvents trace) {
        return new OutcomeAspect(trace);
    }
}
~~~

**Important for Spring:**

- `@Aspect` marks a class as containing advice, yet by itself **does not register a Spring bean**. The `@Bean` methods create the aspect instances.
- `@EnableAspectJAutoProxy` enables annotation-style AOP in Spring Framework.
- `proxyTargetClass = true` selects a class-based Spring proxy so the demo can request the bean by `TransferService.class`. **Do not assume CGLIB alters `@Order` logic.**
- `TraceEvents` is only a collector; pointcuts in the three aspects match `TransferService.transfer(..)`, not methods on `TraceEvents`.
- The order of `@Bean` methods in the file **does not decide** advice ordering. Precedence is driven by `@Order(10)`, `@Order(20)`, and `@Order(30)`.
- If transaction/cache/security advisors are added in a larger application, the actual chain may gain layers to observe; this project intentionally omits them.

### 5.9. Automated Verification and Execution: `Main.java`

~~~java
package example;

import java.util.List;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    private static void check(
            String scenario,
            List<String> actual,
            List<String> expected) {

        if (!expected.equals(actual)) {
            throw new AssertionError(
                scenario + " trace mismatch.\n"
                + "expected: " + expected + "\n"
                + "actual:   " + actual
            );
        }
        System.out.println("verified: " + scenario);
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            TransferService service = context.getBean(TransferService.class);
            TraceEvents trace = context.getBean(TraceEvents.class);

            System.out.println("spring AOP proxy: "
                + AopUtils.isAopProxy(service));

            System.out.println("-- success --");
            String returned = service.transfer(false);
            System.out.println("caller result: " + returned);

            check("success", trace.drain(), List.of(
                "A: enter",
                "B: enter",
                "target: begin",
                "target: return OK",
                "C: returned OK",
                "B: after",
                "B: finally",
                "A: after",
                "A: finally"
            ));

            System.out.println("-- failure --");
            try {
                service.transfer(true);
                throw new AssertionError("Expected IllegalStateException");
            } catch (IllegalStateException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }

            check("failure", trace.drain(), List.of(
                "A: enter",
                "B: enter",
                "target: begin",
                "target: throw boom",
                "C: throwing IllegalStateException",
                "B: finally",
                "A: finally"
            ));
        }
    }
}
~~~

The `check` method does not merely verify event membership; `List.equals` verifies **every position in order** and **event count**, catching extra logs, missing logs, swapped A/B, or an erroneous "after" on the failure branch.

The collector is drained via `drain()` after each case so the failure trace never mixes with success. This per-case segmentation is a simple substitute for a correlation ID **strictly in a single-threaded demo**.

### 5.10. Run Command

In the `spring-aop-trace-demo` directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

Once dependencies are resolved and the project runs with Java 17+, `System.out.println` lines appear in this order:

~~~text
spring AOP proxy: true
-- success --
A: enter
B: enter
target: begin
target: return OK
C: returned OK
B: after
B: finally
A: after
A: finally
caller result: OK
verified: success
-- failure --
A: enter
B: enter
target: begin
target: throw boom
C: throwing IllegalStateException
B: finally
A: finally
caller caught: boom
verified: failure
~~~

Maven or the framework may emit their own messages not listed above. The `verified` lines appear only when **the entire event order is exact**; otherwise `Main.check(...)` throws `AssertionError` and prints expected/actual for debugging.

### 5.11. Step-by-Step Verification Through Code

**Success case:**

1. Caller executes `service.transfer(false)` through the Spring proxy.
2. A(10) prints `enter`, then proceeds.
3. B(20) prints `enter`, then proceeds.
4. C(30) does not run before the target because it only has after-returning/after-throwing advice; Spring forwards to the target method.
5. Target logs begin and return OK.
6. C receives normal return and prints `returned OK`.
7. B receives the return from `proceed`, prints after, then finally.
8. A receives the return from B, prints after, then finally.
9. Caller receives `OK` and `check` confirms all nine events in the collector.

**Failure case:**

1. A(10) enters, then B(20) enters.
2. Target logs begin, logs throw, then throws `IllegalStateException("boom")`.
3. C(30) receives the exception in `@AfterThrowing` and logs the exception type.
4. B does not reach its `after` line because `proceed` threw; B's `finally` still logs.
5. A also skips its `after` line; A's `finally` still logs.
6. Caller catches the exception, and `check` compares all seven events.
7. In both cases, the target is called **once**; neither around advice alters arguments or return/throw.

## 6. Distinguishing "After" in the Trace Table

Four concepts can share the word "after" while having different semantics:

| Form | When Does It Appear? | In the Trace Table |
| --- | --- | --- |
| Code placed after `pjp.proceed()` in `@Around` | Only when `proceed` returns normally, without an enclosing catch/finally | `A: after`, `B: after` |
| `@AfterReturning` | Advised method execution returns normally | `C: returned OK` |
| `@AfterThrowing` | Advised method execution exits via a matching exception | `C: throwing IllegalStateException` |
| `@After` | Method execution ends normally **or** via exceptional exit | Can be added to trace; omitted from project to avoid clutter |
| Java `finally` inside `@Around` | Try block in advice was entered and exited normally or via exception | `A: finally`, `B: finally` |

**Common mistake:** `B: after` **not appearing when the target fails** is not because Spring forgot to run `@After`. There is no `@After` annotation on B in the demo; `B: after` is an ordinary Java statement after `proceed`, so when `proceed` throws, Java skips that statement.

**To do cleanup in `@Around`:** use `try/finally`. **To run logic after the method on both branches without separate state:** consider `@After`. **To observe only the outcome:** use `@AfterReturning` or `@AfterThrowing`.

## 7. What If `@After` Is Added to the Same Aspect?

Spring Framework documents advice ordering **within the same `@Aspect` class**. From highest to lowest precedence:

1. `@Around`
2. `@Before`
3. `@After`
4. `@AfterReturning`
5. `@AfterThrowing`

However, `@After` has **after-finally semantics** and **actually appears after** the corresponding `@AfterReturning` or `@AfterThrowing` when the join point ends within the same aspect. That is why you must distinguish **precedence when forming the interceptor chain** from **statement print order on the exit path**.

Example supplementary snippet inside `OutcomeAspect`:

~~~java
@After("execution(public * example.TransferService.transfer(..))")
public void onFinished() {
    trace.record("C: finally");
}
~~~

This snippet **is not in the original project**, because adding it requires updating the expected/output tables in section 5.

If added and executed **inside the same `OutcomeAspect`**, the outcome-layer sequence on the success branch for layer C becomes:

~~~text
target: return OK
C: returned OK
C: finally
B: after
B: finally
A: after
A: finally
~~~

Failure branch:

~~~text
target: throw boom
C: throwing IllegalStateException
C: finally
B: finally
A: finally
~~~

Lesson point: `@After` here does **not** mean "only after returning"; it runs on both branches. This is clearly described in Spring Framework's official advice-ordering guide.

**Do not confuse with two advice methods of the same type in the same aspect:** for instance, two `@After` methods matching the same join point have no guaranteed order based on Java source declaration position. To keep traces deterministic, merge logic into one advice or split into explicitly ordered aspects.

## 8. If `@Order` Changes, How Must the Trace Table Change?

Suppose we replace:

~~~java
@Order(10)
public class OuterTraceAspect { /* ... */ }
~~~

with:

~~~java
@Order(40)
public class OuterTraceAspect { /* ... */ }
~~~

The three classes in the demo then have the order:

~~~text
B: 20 (highest precedence)
C: 30
A: 40 (lowest precedence)
~~~

Since C is after advice, A and B remain around advice, yet **B now wraps outside A**. The trace on success (after reconfiguration) has the events:

~~~text
B: enter
A: enter
target: begin
target: return OK
A: after
A: finally
C: returned OK
B: after
B: finally
~~~

Here C(30) sits **between B(20) and A(40)**. Because C's after-returning advice wraps the call to A(40), C only observes the normal return once A finishes. C does not necessarily sit right next to the target when orders change.

This is a useful reasoning exercise: **execution order depends not only on advice type**, but also on **which layer sits outside vs. inside**.

**Do not treat those lines as the default project stdout**: they are a prediction after changing order and initializing **a fresh `ApplicationContext`**. Do not rely on modifying annotations on a live proxy expecting the chain to auto-update.

## 9. When Multiple Infrastructure Advisors Are Present

A Spring bean can carry more advisors than the three developer-declared aspects:

- Transaction interceptor via `@Transactional`.
- Cache interceptor via `@Cacheable`.
- Method security interceptor.
- Async/proxy infrastructure.
- `ProxyFactory` wrappers created by application code or third-party libraries.

Suppose:

~~~text
Caller
 -> Trace A
    -> TransactionInterceptor
       -> Trace B
          -> Target
       <- B finally
    <- commit/rollback
 <- A finally
~~~

If A sits **outside** the transaction interceptor, A's finally can appear **after** transaction commit/rollback. If A sits **inside** the transaction interceptor, A's finally can appear **before** commit/rollback. Trace tables must mark this boundary rather than concluding the transaction committed merely because "target returned OK."

**Do not claim transactions have a fixed order in every Spring context.** Spring offers precedence configuration for certain infrastructure advisors (e.g., `@EnableTransactionManagement(order = ...)`). Read the actual configuration and inspect the advisor chain / run integration tests whenever ordering affects business logic.

A trace using only `System.out.println` from custom aspects **does not automatically reveal** transaction begin/commit or cache hits. If your goal is to verify ordering relative to transactions or caching, add real instrumentation/transaction tests at **the right layer** instead of over-interpreting A/B logs.

## 10. When an Around Advice Terminates Early

Suppose a higher-precedence aspect has this logic:

~~~java
@Around("execution(public * example.TransferService.transfer(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    if (cached()) {
        return "CACHED";
    }
    return pjp.proceed();
}
~~~

This is an **illustrative snippet**, with `cached()` defined by the application and not part of the runnable project.

If the outer layer returns `"CACHED"` without **calling `proceed()`**, inner layers **are never entered**. Thus the trace table may be:

~~~text
outer: enter
outer: cache hit
caller result: CACHED
~~~

Missing a "target begin" line is not necessarily a bug; an advice intentionally short-circuited. However, if you are debugging mandatory audit/security checks, verify interceptor placement and whether early termination is valid.

**Distinguish three cases:**

1. Outer **never entered** → no outer logs.
2. Outer **entered but did not proceed** → only logs from outer or layers entered before it.
3. Outer **proceeded** yet an inner advisor short-circuited → logs from outer + some inner layers, **no target logs**.

Only by building a complete trace table can you distinguish "Spring AOP is not working," "pointcut did not match," "proxy was bypassed," and "intended interceptor short-circuit."

## 11. When Exceptions Do Not Originate From the Target

The failure tables in sections 3 and 5 assume **the target method itself throws the exception**. Yet an exceptional exit from a Spring AOP invocation can arise at many points:

| Exception Source | Did the Target Necessarily Run? | Milestones That Can Appear |
| --- | --- | --- |
| Target throws | Yes, call reached the target | target throw; matching on-throw callback; outer finally |
| Inner `@Before` advice throws | **No** | outer enter, possibly inner enter, then outer finally |
| Outer `@Around` throws before `proceed()` | **No** | outer layers already entered; inner layers may not have entered |
| `@AfterReturning`/`@After` advice throws | Target may already have returned normally | outer catch/finally can observe the advice error |
| Metrics/logging backend inside advice throws | Depends on throw location | trace may be incomplete or original exception masked |
| Transaction commit throws after target | Target may have returned normally | order depends on where the transaction advisor sits |

**Safety rule:** `@AfterThrowing` is not a global exception handler for all errors raised by other advice. Per Spring guidance, `@AfterThrowing` targets exceptional exits of **the method join point** and does not promise to receive exceptions thrown by another `@After`/`@AfterReturning`.

If you need traces that distinguish errors from target, advice, or transaction commit, log **where the exception was observed** clearly rather than just the exception type. An outer `@Around` with `catch(Throwable t)` can observe exceptions unwinding from **any inner part of the chain** that threw, not only the target.

## 12. What Trace Does "Exception Caught Inside the Target" Produce?

Example:

~~~java
public String transferRecovering() {
    try {
        riskyOperation();
    } catch (IllegalStateException ex) {
        return "RECOVERED";
    }
}
~~~

This is a **snippet**; `riskyOperation()` is an illustrative method not defined in the section 5 project.

If the method **catches all exceptions internally and returns `RECOVERED`**, from Spring AOP's perspective the method execution **completed normally**. Consequences:

- Matching `@AfterReturning` can run with `"RECOVERED"`.
- `@AfterThrowing` does not run for the internally caught exception.
- Code after `proceed()` in an outer `@Around` can run.
- `finally` blocks of entered around advice still run.

Do not see "operation failed internally" in the target and wonder why `@AfterThrowing` did not appear; the dividing line is **whether the exception escaped the method join point**.

An outer interceptor can also catch an exception from an inner layer and return a fallback. Then an aspect **outside** that interceptor sees a **normal return**, whereas deeper layers saw an exception. That is why trace tables must specify **which layer** observed the outcome instead of using a single global "success/failure" label.

## 13. Self-Invocation and Missing Trace Lines

In proxy-based Spring AOP:

~~~java
public void outer() {
    this.inner();
}
~~~

The internal `this.inner()` call inside the target **does not route back through the Spring proxy**. If your pointcut targets only `inner()`, advice runs when a caller invokes `service.inner()` directly through the proxy, yet **not** for calls originating from `this.inner()`.

Example table:

| Call Path | Observable AOP Trace |
| --- | --- |
| `client -> springProxy.inner()` | aspect enter → inner target → aspect exit |
| `client -> springProxy.outer() -> target.this.inner()` | May have aspect for **outer**, yet **no separate aspect automatically for inner** |
| `client -> new Service().inner()` | No Spring-managed proxy advice for a manually instantiated object |

**`@Order` does not solve self-invocation.** Switching from JDK proxy to CGLIB does not fix it automatically either, because this is a boundary of Spring AOP's proxy model.

The preferred fix: extract the method needing advice into **another Spring bean** and call it via dependency injection. Do not unwrap `Advised.getTargetSource()` to call the target while debugging; doing so deliberately skips all advice you are trying to verify.

## 14. `@After` and `@AfterReturning`/`@AfterThrowing` in the Same Aspect

Spring defines precedence **within a single `@Aspect`** across different advice types, with a **notable detail for finally semantics**:

| Advice Type | Primary Direction | Ordering Note |
| --- | --- | --- |
| `@Around` | Wraps invocation | Can run before and after `proceed()` |
| `@Before` | Before join point | Does not know the result itself |
| `@After` | When join point exits along either branch | In effect, runs **after** same-aspect after-returning/after-throwing |
| `@AfterReturning` | When join point returns normally | Does not run if an exception escapes the method |
| `@AfterThrowing` | When join point throws an exception | Does not run if the method catches the error and returns |

Spring describes precedence among distinct advice types in the same aspect from highest to lowest as: `@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`. Yet **never** turn that precedence table into a one-way stdout table: due to `finally` semantics, `@After` **actually runs after** the corresponding `@AfterReturning`/`@AfterThrowing` in the same aspect.

If there are **two advice methods of the same type** in **the same aspect** both matching the same method, the order between them is not guaranteed by method declaration order in Java source. Java reflection does not provide a reliable source order to depend on.

**For deterministic traces**, do not write tests requiring a fixed order between two `@Before` methods in the same aspect; combine sequential work into one advice or split into two aspects with distinct `@Order` values.

## 15. Trace Table Template for Integration Tests

When debugging in a real Spring Boot or Spring Framework application, you can build a table with these columns:

| Field | Example | Purpose |
| --- | --- | --- |
| `invocationId` | `op-17` | Groups events of a single call to avoid mixing requests |
| `sequence` | `1,2,3,...` | Observed order within the same invocation |
| `layer` | `outerAspect(10)` | Identifies which advisor/layer recorded it |
| `phase` | `enter/after/throw/finally` | Distinguishes way in and way out |
| `method` | `TransferService.transfer` | Identifies the advised method |
| `outcome` | `normal/exceptional/unknown` | Separates observed outcome kinds |
| `exceptionType` | `IllegalStateException` | Classifies error types without logging secrets |
| `thread` | Thread name/ID | Helps detect interleaved events |
| `advisorOrder` | `10/20/30` | Explains precedence if configured accurately |

**Do not turn trace tables into a place that logs sensitive data:** operation names and exception types are usually sufficient. Never log passwords, tokens, transaction payloads, raw method arguments, or PII by default. For production traces, use well-governed logging/tracing with correlation context.

### 15.1. Expected/Actual Table When a Test Fails

A test should present both sequences:

~~~text
Expected:
[A: enter, B: enter, target: begin, C: ..., B: finally, A: finally]

Actual:
[B: enter, A: enter, target: begin, C: ..., A: finally, B: finally]
~~~

If they differ on the **way in**, check `@Order`/`Ordered` or the actual advisor chain. If they differ only on the **way out**, check `finally` placement, `@After`, and `catch` branches. If target lines are missing, check `proceed()` or cache short-circuiting. If all advice lines are missing, check pointcuts, bean/proxy setup, and self-invocation.

### 15.2. Assertions Must Cover the Failure Branch Too

A common mistake is asserting only:

~~~java
assertTrue(events.contains("A: enter"));
assertTrue(events.contains("B: enter"));
~~~

Both assertions still pass when the order is reversed. To verify ordering, **compare the entire list in sequence**, as with `List.equals(...)` in the demo or `assertEquals(expectedEvents, actualEvents)` in JUnit.

Also assert:

- Business result remains accurate on the normal path.
- Exception **type** and message/identity when required by contract.
- Target invocation count is exactly one when there are no retries.
- No `@AfterReturning` callback appears on the exceptional path.
- No `@AfterThrowing` callback appears on the normal path.
- Each **entered** around advice's `finally` appears the expected number of times.
- No events from other invocations leak in.
- Methods/beans outside the pointcut are not advised accidentally.

## 16. Limitations That Make Trace Tables Differ from Expectations

### 16.1. Asynchronous Logging and Multiple Threads

A synchronous Spring AOP call has a clear Java execution order, yet an asynchronous log exporter may ship or display events in a different order. If two requests run concurrently, `A: enter` from request 2 can land between `A: enter` and `B: enter` of request 1.

Therefore, **never use a single unsynchronized global list** to test multiple concurrent calls. Use per-invocation collections or properly scoped trace contexts with correlation IDs; group first and only then compare ordering.

### 16.2. Methods Returning Future / Reactive Publishers

`@AfterReturning` on a method returning `CompletableFuture` can run as soon as the method **returns the Future object**, which does not mean background work finished. `@AfterThrowing` does not automatically observe errors occurring **later** in the async computation. Likewise, a method returning `Mono`/`Flux` can return before the reactive pipeline is subscribed.

If you need to trace **the entire** async lifecycle, use completion hooks or lifecycle operators suited to that abstraction; do not read "method returned" as "request fully completed."

### 16.3. Proxy Configuration and Uninterceptable Methods

- JDK proxies expose only appropriate interfaces; class-based CGLIB proxies use subclassing.
- `final` classes/methods or `private` methods may not be advised under class proxying.
- `@Aspect` classes must be registered as beans.
- A bean having an AOP proxy does not guarantee **every method** matches every advisor.
- Self-invocation still bypasses the proxy under both JDK and CGLIB.
- Third-party infrastructure advisors can sit outside custom `@Aspect` beans.

A trace missing an event does not prove a Spring AOP bug; first confirm the target bean, proxy reference, and pointcut eligibility.

## 17. Symptom-Based Diagnosis

| Symptom | Top Hypothesis | How to Verify |
| --- | --- | --- |
| A enters before B, yet A's finally also runs before B's finally | Logs may be recorded at different layers or finally code placed unexpectedly | Inspect `proceed()` structure and actual interceptor chain |
| `C returned` appears when target was thought to fail | Target or inner interceptor caught the exception and returned fallback | Determine the outcome at C's boundary |
| No `C throwing` when target throws | Throwable type mismatch, caller bypassed proxy, or an inner layer handled it | Check throwing binding and target method execution |
| `B after` missing yet `B finally` present | B's `proceed()` threw an exception | This may be expected behavior |
| Neither A nor B logs anything | Aspect not a Spring bean, pointcut mismatch, or caller bypassed proxy | Check `@Bean`, AOP config, `AopUtils.isAopProxy` |
| `A enter` present yet `B enter` missing | A did not proceed or a layer before B short-circuited | Check early returns, cache hits, preconditions |
| Target runs twice | Retry / multiple `proceed()` / duplicate caller | Count invocations and check idempotency |
| Trace passes on success, fails on failure | Omitted `finally` or different exception handling | Assert the exceptional path separately |
| Trace changes after adding `@Transactional` | Added infrastructure advisor with its own order | Inspect advisor chain and transaction boundary |
| Events appear when called from controller, missing when service calls itself | Self-invocation | `this.method()` bypasses the Spring proxy |
| Logs scramble randomly across requests | Parallel requests or async log backend | Group by `invocationId`, do not compare globally |
| Two same-type advice methods in the same aspect swap after build | Source method order is not guaranteed | Merge advice or split into ordered aspect classes |
| Small `@Order` yet advice does not run | Order does not decide pointcut matching | Check bean/method and call path |
| `onThrow` advice throws a new exception | Caller may see a replaced exception | Minimize instrumentation errors, check exception contract |

### Sequential Troubleshooting Checklist

1. Identify the exact **method, target bean, and caller reference**.
2. Read the Spring AOP configuration and names of registered `@Aspect` beans.
3. Confirm pointcuts and eligible advisors for the method.
4. Assign **explicit numeric** orders to aspects needing fixed precedence.
5. Separate events into **enter / target / result or throw / after / finally**.
6. Run one success invocation and one failure invocation, sequentially.
7. Compare **full expected vs. actual sequences**, not mere log presence.
8. Add a variant where the method catches exceptions and returns if business logic has fallbacks.
9. When transaction/cache/async exist, expand the trace table for those real layers.
10. Verify behavior: return value, exception, side effects, invocation count.
11. Expand to concurrency/log-aggregation tests only after the single-threaded path is right.
12. When order changes, start a fresh context/test run and re-verify the chain.

## 18. Practice Questions

**Question 1.** A has `@Order(5)`, B has `@Order(50)`, and both around advice methods proceed. Which enters first, and which runs `finally` last?

**Answer:** A(5) has higher precedence, **enters first**, and runs **`finally` last** relative to B(50).

**Question 2.** Logs show A enter → B enter → target throw → B finally → A finally, with no "A after." Is Spring AOP broken?

**Answer:** No. Statements placed **after `proceed()`** inside around advice do not run when `proceed()` throws. Both A's and B's `finally` blocks still run.

**Question 3.** `@AfterReturning` and `@AfterThrowing` both match the method signature, and the target returns normally. Do both run?

**Answer:** No. Only matching after-returning runs on a normal exit; after-throwing runs only when an exception escapes the method and matches the throwable type.

**Question 4.** The target method catches its own exception and returns `"RECOVERED"`. Which trace table applies?

**Answer:** From Spring AOP's perspective, that is a **normal return**, so matching after-returning can run. An internally caught error does not automatically trigger after-throwing.

**Question 5.** Outer around skips `proceed()` due to a cache hit. Must the target and inner advice run?

**Answer:** No. Only layers entered before the short-circuit can emit events. Verify whether this is intended behavior or an accidental missing `proceed()`.

**Question 6.** There are two `@Before` methods in the same `@Aspect` class matching the same join point. Source declares `first` above `second`; is the order guaranteed?

**Answer:** No. If deterministic order is needed, merge the logic or use two aspect classes with distinct orders.

**Question 7.** In one aspect, `@After` and `@AfterReturning` match a successful method. Since `@After` has higher precedence, does `@After` always print before `@AfterReturning`?

**Answer:** No. Spring specifies `@After` has **after-finally semantics** and actually runs after the matching after-returning or after-throwing **within the same aspect**.

**Question 8.** Is asserting `events.contains("A: enter")` and `events.contains("B: enter")` enough to prove A ran before B?

**Answer:** No. You must assert **element order**, such as `List.equals(expectedSequence)` or explicit index checks.

**Question 9.** Caller instantiates `new TransferService(trace)` and calls the method. Does the A/B/C table apply?

**Answer:** Not automatically. An instance outside the Spring container is not a Spring AOP-managed proxy bean.

**Question 10.** Can a business trace conclude "transaction committed" solely because `@AfterReturning` appeared after the target?

**Answer:** No. Commit may occur in a transaction interceptor at another position; inspect the actual transaction boundary and advisor ordering.

## 19. Official References

- [Spring Framework — Declaring Advice / Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): ordering rules across aspects, `@Order`/`Ordered`, way-in/way-out, after-returning/after-throwing, and `@After` finally semantics.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, self-invocation, and proxy boundaries.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): registering Spring aspect beans and enabling AOP proxies.
- [Spring Framework — Declaring Pointcuts](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): selecting matching method executions and avoiding unintended beans.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): Spring AOP join points and advice types.
- [Spring Framework — Manipulating Advised Objects](https://docs.spring.io/spring-framework/reference/core/aop-api/advised.html): inspecting the advisor chain of a Spring AOP proxy.
- [Spring Javadoc — Ordered](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html): precedence value ordering.
