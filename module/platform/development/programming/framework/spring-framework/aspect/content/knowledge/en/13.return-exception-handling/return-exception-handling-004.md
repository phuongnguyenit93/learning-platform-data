# Impact of Exceptions Thrown by Advice Itself in Spring AOP

## 1. Why are exceptions inside advice especially dangerous?

In Spring Framework, a call to a Spring bean can pass through **a chain of advisors/interceptors** before reaching the business method (*target method*). Every advice declared by `@Aspect` also executes along this path. Therefore, if **code inside advice throws an exception itself**, the outcome observed by the caller can differ completely from the result the target intended to return or the original error the target threw.

Practical questions:

- If a `@Before` advice throws an error, is the target called?
- The target returned `"OK"`, yet `@AfterReturning` fails while recording a metric: what does the caller receive?
- The target throws `IllegalArgumentException`, yet `@AfterThrowing` throws a new `IllegalStateException`: which error reaches the client?
- How does `@After` acting like `finally` throwing an error on the success path differ from throwing on the error-handling path?
- How can `@Around` catching, transforming, or throwing exceptions from `proceed()` mask the original failure?
- Can an outer aspect observe an error from an inner advice, and what determines that?

**Key message:** an advice is not automatically "out of band" relative to the call's return path. An exception inside advice can **halt inner execution, turn a normal return into an exceptional return, or replace the original exception**. In Spring AOP, the exact effect depends on **the advice's position in the proxy interceptor chain**.

This lesson focuses on **Spring Aspect (@AspectJ style on Spring AOP proxies)**. General Java exception mechanics and AspectJ weaving are mentioned only when needed to contrast with actual Spring behavior.

## 2. Proxy call model: where exceptions can arise

A proxy can arrange interceptors into nested layers:

```text
Caller
  |
  v
Spring AOP proxy
  |
  +-- Outer @Around: enter
        |
        +-- @Before
        |     |
        |     +-- if throws -> inner layers do not run
        |
        +-- Target business method
        |     |
        |     +-- return or throw
        |
        +-- @AfterReturning / @AfterThrowing
        |     |
        |     +-- if this advice throws -> outer outcome changes
        |
        +-- @After (finally)
        |     |
        |     +-- if throws -> can mask both return value and prior error
        |
        +-- Outer @Around: return / catch / finally
  |
  v
Caller receives final value or exception
```

This diagram is a **conceptual model**, not the absolute order for every configuration. Each `@Aspect` has a precedence level, transaction/cache/async advisors may be present, and advice can short-circuit or call `proceed()` multiple times. For a given invocation, only advisors with matching pointcuts participate.

What is certain from the Java call stack mechanism: **an exception thrown in one layer propagates outward until a layer catches it**. If a layer throws a new exception while unwinding, outer layers may see only that new exception.

### Simple error path example

```text
Target:         throw BusinessException("business failed")
After advice:   throw TelemetryException("log unavailable")
Outer advice:   catch TelemetryException
Caller:         receives TelemetryException
```

If `TelemetryException` does not preserve `BusinessException` as its `cause` or `suppressed`, root-cause information can become very hard to trace. That is why throwing errors from logging, metrics, or cleanup advice must be designed intentionally.

## 3. Overview table by advice type

The table assumes the advice code is actually triggered, has a matching pointcut, and no outer layer converts the error into a fallback:

| Advice that throws an exception | What happens to the target | What the caller typically sees |
| --- | --- | --- |
| `@Before` | If advice throws **before entering the target**, the target does not execute | Exception from `@Before` |
| `@AfterReturning` | Target **already returned normally**; advice runs then throws | Exception from `@AfterReturning` instead of return value |
| `@AfterThrowing` | Target **already threw a matching error**; advice receives it then throws another | New exception thrown by advice, unless altered by an outer layer |
| `@After` | Inner execution reached the finally branch; advice throws | Can mask normal return **or** the original exception |
| `@Around` before `proceed()` | Inner chain not called; target may not run | Exception from around advice |
| `@Around` after `proceed()` returns normally | Target/inner chain may have completed normally | Exception from around advice |
| `@Around` catches then throws new | Target/inner chain raised a Throwable | New Throwable, which may retain the old error as cause |
| `@Around` catches then returns fallback | Target/inner chain failed | Caller receives fallback, not original error, unless outer chain throws another error |

This table does **not** mean advice is forced to rethrow the original exception. In Java, `@Before`/`@AfterReturning`/`@AfterThrowing`/`@After` are usually `void` methods; their bodies can still throw unchecked exceptions. Spring does not automatically isolate every advice error from the caller.

### Three things you must always separate

1. **Target error:** an exception created by the target method while executing business logic.
2. **Advice error:** an exception arising from authorization checks, logging, metric increments, cleanup, transformation, or retries themselves.
3. **Caller-observed error:** the final exception escaping **the entire Spring proxy chain**. This may be a target error, an advice error, a wrapper exception, or no error if an outer around returned a fallback.

Do not use `@AfterThrowing` to naively infer that "every exception the caller receives was thrown by the target."

## 4. `@Before` throws an exception: the target is not called

Example of an advice checking a precondition before method execution:

```java
@Aspect
public class PermissionAspect {
    @Before("execution(* com.example.app.service..*.submit(..))")
    public void check() {
        throw new IllegalStateException("permission unavailable");
    }
}
```

This is a **snippet inside a Spring `@Aspect` bean**, not a standalone program. If the advice matches and throws before the invocation continues:

```text
CLIENT -> Spring proxy -> @Before throws
                             |
                             +--> TARGET.submit() does not run
                             |
                             +--> exception propagates outward
```

This may be **intentional** if the advice performs authorization and uses an exception to reject the call. Yet it can also be an **unintended bug** when the advice is supposed to only log—for instance, `logger.info(...)` or a formatter throwing an exception itself.

### Is every other `@After` guaranteed to run when `@Before` throws?

**No.** If `@Before` sits in an outer layer and throws **before an inner after/finally interceptor is invoked**, that inner interceptor has not been entered yet and cannot run its cleanup. Conversely, an outer `@Around` that already started before the before advice can use `try/finally` to record the incident.

Ordering among advice in Spring is governed by precedence and nesting; do not treat `@After` as a "global finally catching every error at any layer".

If cleanup must run **even when a pre-target precondition fails**, place the cleanup in an outer layer that has actually been entered, and test the specific advisor order.

### Checking side-effect preservation

If `@Before` fails before the target, the target does not execute its method side effects. However, an **outer-layer** advice may already have produced side effects before the error occurred, such as writing a request-start audit entry or opening a tracing span. Do not use "the target did not run" to claim "nothing happened."

## 5. `@AfterReturning` throws an exception: turning success into failure

`@AfterReturning` is called **only when the corresponding method execution returns normally**. It can bind the return value:

```java
@AfterReturning(
    pointcut = "execution(* com.example.app.service..*.complete(..))",
    returning = "result",
    argNames = "result"
)
public void recordSuccess(String result) {
    System.out.println("BUSINESS RETURNED " + result);
    throw new IllegalStateException("metrics unavailable");
}
```

This is an **illustrative snippet**. After the target executes and returns `"OK"`:

```text
Target.complete()       -> return "OK"
@AfterReturning         -> throw IllegalStateException
Outer caller            -> receives IllegalStateException, does not receive "OK"
```

**This is a major trap:** the business operation executed successfully, possibly writing data or sending messages, yet the client thinks the operation failed because telemetry advice threw an error.

Consequences:

- The client may retry the request upon receiving a 5xx; if the operation is not idempotent, retries can produce **duplicate side effects**.
- If a transaction advisor is present, an exception from advice **can affect the transaction** depending on the relative order of the advice and the transaction interceptor. Do not infer whether data committed or rolled back from a log line alone.
- `@AfterReturning` cannot replace the return object by returning a value from the advice; however, **throwing an exception** still turns the exit path into an exceptional one unless an outer handler catches it.

### Advice throwing after target returns differs from a target exception

An outer `@Around` seeing an exception from `proceed()` in this scenario may catch `IllegalStateException("metrics unavailable")`, even though the target threw no error at all. Outer observers should therefore distinguish **infrastructure/advice errors** from **business errors** via typing, cause chains, structured events, or proper logging design.

**Spring documentation notes:** a companion `@AfterThrowing` in the same aspect **is not considered a callback that catches errors thrown by another `@AfterReturning` in that aspect**. If you want to monitor errors across the entire chain, design an explicit outer `@Around`.

## 6. `@AfterThrowing` throws a new exception: masking the original business error

Suppose the target method throws:

```java
throw new IllegalArgumentException("invalid order");
```

An after-throwing advice can bind the original throwable:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.placeOrder(..))",
    throwing = "original",
    argNames = "original"
)
public void onFailure(IllegalArgumentException original) {
    System.out.println("FAILED " + original.getMessage());
    throw new IllegalStateException("audit system failed", original);
}
```

This is a snippet, not a standalone project. When the advice throws a new exception, Java control flow exits **from the advice** with `IllegalStateException`:

```text
Target:           IllegalArgumentException("invalid order")
Advice:           receives original
Advice:           throws IllegalStateException("audit system failed", original)
Caller/outer:     sees IllegalStateException
Cause chain:      IllegalArgumentException -> "invalid order"
```

Compared to throwing:

```java
throw new IllegalStateException("audit system failed");
```

using the constructor with `cause` preserves the trail to the initial failure. Still, a **better choice** for audit/logging-only advice is not to throw a new exception that obscures the business error if telemetry fails.

### `throwing` name and exception type still matter

- `throwing = "original"` must match the advice parameter name; `argNames = "original"` keeps binding explicit.
- Type `IllegalArgumentException` only matches runtime throwables of that class or subclasses.
- If the target throws `IOException` and the advice only accepts `IllegalArgumentException`, the advice does not run, so it **cannot throw a secondary error from that advice body** for that case.
- If using `Throwable original`, the advice can receive `Error` too—think carefully before invoking logging/metrics systems that could fail on severe error paths.

### Why isn't `@AfterThrowing` "the handler for all proxy errors"?

Spring Framework 6.2 documentation makes a clear distinction: this advice serves **exceptions from the join point (the user-declared target method)**, and must not be treated as a general callback catching exceptions raised by companion `@After` or `@AfterReturning` advice in the same `@Aspect`. Advisor ordering and nesting are why a new exception from advice **does not necessarily** pass through other `@AfterThrowing` advice.

To handle errors across the full chain, use a clearly ordered **outer around interceptor/aspect** and test the real call paths.

## 7. `@After` throws an exception: risks of logic inside finally

In Spring AOP, `@After` has **after-finally advice** semantics. It runs when the corresponding method execution completes either normally or by throwing an exception:

```java
@After("execution(* com.example.app.service..*.store(..))")
public void release() {
    System.out.println("RELEASING");
    throw new IllegalStateException("cleanup failed");
}
```

The snippet above intentionally contains a bug to illustrate two branches:

### 7.1. Target succeeded

```text
Target.store()     -> return "STORED"
@After.release()   -> throw IllegalStateException("cleanup failed")
Caller             -> receives cleanup exception instead of "STORED"
```

Like the `@AfterReturning` case, the target may already have performed side effects while the caller receives a cleanup error.

### 7.2. Target threw an exception

```text
Target.store()     -> throw IllegalArgumentException("storage rejected")
@After.release()   -> throw IllegalStateException("cleanup failed")
Caller             -> receives cleanup exception
Original exception -> risks disappearing from the cause chain
```

This has the same semantics as a Java `finally` block throwing a new exception and masking the propagating exception. With `@After`, you **have no `throwing` attribute** to receive the original exception directly. Thus, if `@After` throws without attaching the prior cause, original failure details are easily lost on the way to the client.

### Do not confuse with `try-with-resources`

Java `try-with-resources` has special rules to keep the `try` error as the primary exception and attach `close()` errors as **suppressed exceptions**. Spring `@After` throwing an exception **does not automatically apply try-with-resources suppressed-exception mechanics**. If you need to preserve both errors, design an explicit cause/suppressed policy at a layer that has both throwables, such as an outer `@Around`.

### Cleanup should be fail-safe within requirements

An advice that merely records metrics or clears tracing state should generally avoid failing a business operation just because telemetry is temporarily unavailable. Yet **do not mechanically swallow all errors**: if advice is genuinely responsible for enforcing a mandatory invariant, failure needs an explicit business contract and tests.

## 8. `@Around`: can catch, translate, throw new, or swallow exceptions

`@Around` receives `ProceedingJoinPoint` and controls the call via `proceed()`. Therefore, it has the strongest impact on exception flow.

### 8.1. Preserving the error and running finally

```java
@Around("execution(* com.example.app.service..*.dispatch(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } finally {
        System.out.println("TRACE finished");
    }
}
```

If the inner layer throws an exception and `finally` throws no additional error, the original exception propagates. If the inner layer returns normally, that value is preserved as well.

### 8.2. Translating an exception while keeping cause

```java
@Around("execution(* com.example.app.service..*.dispatch(..))")
public Object wrapFailure(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalArgumentException original) {
        throw new IllegalStateException(
            "dispatch failed in proxy chain", original
        );
    }
}
```

Here `IllegalStateException` is received by the caller; `original` remains in `getCause()`. Ensure the new type truly matches the service/API contract rather than wrapping arbitrarily and making client error handling harder.

### 8.3. Catching and returning a fallback

```java
@Around("execution(* com.example.app.service..*.lookup(..))")
public Object fallback(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException original) {
        return "FALLBACK";
    }
}
```

This snippet is valid **only when the advised method returns a `String`-compatible type** and the business contract permits a fallback. If `pjp.proceed()` throws an exception from an inner advice, `catch` here can catch that error too, **not just target errors**.

**Warning:** broadly catching every `RuntimeException` in around advice can accidentally turn authorization, validation, transaction, or telemetry failures into successes. When fallback is needed, match specific exception classes and tightly control pointcut scope.

### 8.4. Throwing before `proceed()`

```java
@Around("execution(* com.example.app.service..*.lookup(..))")
public Object deny(ProceedingJoinPoint pjp) {
    throw new IllegalStateException("precondition failed");
}
```

The target is not called because the advice never calls `proceed()`. This can be intentional (policy/security), but is inappropriate for a logging-only aspect.

### 8.5. Throwing after `proceed()` succeeds

```java
@Around("execution(* com.example.app.service..*.lookup(..))")
public Object postValidate(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    if (result == null) {
        throw new IllegalStateException("unexpected null");
    }
    return result;
}
```

In this case, the target may have completed normally, yet the caller receives an exception due to post-validation advice. Distinguish **advice result evaluation** from **business method success** in logs and metrics.

## 9. Runnable demo: five advice failure modes and one healthy call

The complete example uses **Java 17+, Maven, Spring Framework 6.2.19**. A Spring bean has intentionally separate methods so each method triggers **only one type of failing advice** in the inner aspect:

1. `scenarioBefore()`: `@Before` throws; target does not run.
2. `scenarioReturning()`: target returns normally; `@AfterReturning` throws.
3. `scenarioThrowing()`: target throws `IllegalArgumentException`; `@AfterThrowing` throws a new `IllegalStateException` **with the original cause**.
4. `scenarioFinallyNormal()`: target returns normally; `@After` throws.
5. `scenarioFinallyError()`: target throws; `@After` throws a new error **masking the original error**.
6. `scenarioAround()`: target throws; inner `@Around` catches and wraps into another error.
7. `scenarioHealthy()`: no inner failing advice applies, so target returns normally.

An outer observing aspect carries `@Order(1)`; the intentionally failing inner aspect carries `@Order(2)`. Thus the **outer around** log reveals which exception actually exits the inner chain. **Do not run the earlier illustrative snippets alongside the demo**, as they can create extra advisors and change the trace.

### 9.1. Project structure

```text
spring-aop-advice-exceptions/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AdviceFailureDemo.java
```

### 9.2. `pom.xml` file

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-advice-exceptions</artifactId>
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
            <version>1.9.22.1</version>
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
                    <mainClass>demo.AdviceFailureDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 9.3. `src/main/java/demo/AdviceFailureDemo.java` file

```java
package demo;

import java.util.function.Supplier;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.core.annotation.Order;

public class AdviceFailureDemo {

    public interface ScenarioService {
        String scenarioBefore();
        String scenarioReturning();
        String scenarioThrowing();
        String scenarioFinallyNormal();
        String scenarioFinallyError();
        String scenarioAround();
        String scenarioHealthy();
    }

    public static class ScenarioServiceImpl implements ScenarioService {
        @Override
        public String scenarioBefore() {
            System.out.println("TARGET before");
            return "BEFORE-OK";
        }

        @Override
        public String scenarioReturning() {
            System.out.println("TARGET returning");
            return "RETURNING-OK";
        }

        @Override
        public String scenarioThrowing() {
            System.out.println("TARGET throwing");
            throw new IllegalArgumentException("business throwing");
        }

        @Override
        public String scenarioFinallyNormal() {
            System.out.println("TARGET finally normal");
            return "FINALLY-OK";
        }

        @Override
        public String scenarioFinallyError() {
            System.out.println("TARGET finally error");
            throw new IllegalArgumentException("business finally");
        }

        @Override
        public String scenarioAround() {
            System.out.println("TARGET around");
            throw new IllegalArgumentException("business around");
        }

        @Override
        public String scenarioHealthy() {
            System.out.println("TARGET healthy");
            return "HEALTHY";
        }
    }

    @Aspect
    @Order(1)
    public static class OuterObserverAspect {

        @Around("execution(* demo..*.scenario*(..))")
        public Object observe(ProceedingJoinPoint pjp) throws Throwable {
            String name = pjp.getSignature().getName();
            System.out.println("OUTER enter " + name);

            try {
                Object result = pjp.proceed();
                System.out.println("OUTER returned " + result);
                return result;
            } catch (Throwable ex) {
                System.out.println(
                    "OUTER caught "
                        + ex.getClass().getSimpleName()
                        + ":" + ex.getMessage()
                );
                throw ex;
            }
        }
    }

    @Aspect
    @Order(2)
    public static class FailingAdviceAspect {

        @Before("execution(* demo..*.scenarioBefore(..))")
        public void failBefore() {
            System.out.println("ADVICE before throws");
            throw new IllegalStateException("before advice failed");
        }

        @AfterReturning(
            pointcut = "execution(* demo..*.scenarioReturning(..))",
            returning = "result",
            argNames = "result"
        )
        public void failAfterReturn(String result) {
            System.out.println(
                "ADVICE afterReturning result=" + result
            );
            throw new IllegalStateException("returning advice failed");
        }

        @AfterThrowing(
            pointcut = "execution(* demo..*.scenarioThrowing(..))",
            throwing = "original",
            argNames = "original"
        )
        public void failAfterThrow(IllegalArgumentException original) {
            System.out.println(
                "ADVICE afterThrowing original="
                    + original.getMessage()
            );
            throw new IllegalStateException(
                "throwing advice failed", original
            );
        }

        @After("execution(* demo..*.scenarioFinally*(..))")
        public void failAfterFinally() {
            System.out.println("ADVICE afterFinally throws");
            throw new IllegalStateException("after advice failed");
        }

        @Around("execution(* demo..*.scenarioAround(..))")
        public Object failAround(ProceedingJoinPoint pjp)
                throws Throwable {
            System.out.println("ADVICE around enters");
            try {
                return pjp.proceed();
            } catch (IllegalArgumentException original) {
                System.out.println(
                    "ADVICE around caught " + original.getMessage()
                );
                throw new IllegalStateException(
                    "around advice failed", original
                );
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class Config {

        @Bean
        public ScenarioService scenarioService() {
            return new ScenarioServiceImpl();
        }

        @Bean
        public OuterObserverAspect outerObserverAspect() {
            return new OuterObserverAspect();
        }

        @Bean
        public FailingAdviceAspect failingAdviceAspect() {
            return new FailingAdviceAspect();
        }
    }

    private static void runCase(
            String label, Supplier<String> operation) {

        System.out.println("=== " + label + " ===");
        try {
            System.out.println("CLIENT value=" + operation.get());
        } catch (RuntimeException ex) {
            System.out.println(
                "CLIENT exception="
                    + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage()
            );

            Throwable cause = ex.getCause();
            if (cause != null) {
                System.out.println(
                    "CLIENT cause="
                        + cause.getClass().getSimpleName()
                        + ":" + cause.getMessage()
                );
            }
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            ScenarioService service =
                    context.getBean(ScenarioService.class);

            System.out.println(
                "AOP_PROXY=" + AopUtils.isAopProxy(service)
            );
            System.out.println(
                "JDK_PROXY=" + AopUtils.isJdkDynamicProxy(service)
            );

            runCase("before", service::scenarioBefore);
            runCase("returning", service::scenarioReturning);
            runCase("throwing", service::scenarioThrowing);
            runCase("finally normal", service::scenarioFinallyNormal);
            runCase("finally error", service::scenarioFinallyError);
            runCase("around", service::scenarioAround);
            runCase("healthy", service::scenarioHealthy);
        }
    }
}
```

**Important reading note:** all method references `service::scenarioBefore` ... invoke the **bean reference supplied by the context**, not `new ScenarioServiceImpl()` directly. Spring has AOP auto-proxy enabled and the class implements an interface, so a JDK proxy applies. `@Order(1)` is numerically lower (higher precedence) than `@Order(2)`, so the observer sits outside the failing aspect where pointcuts overlap.

### 9.4. Running the application

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**Stdout lines printed by the program according to the presented logic** (excluding Maven or Spring logs):

```text
AOP_PROXY=true
JDK_PROXY=true
=== before ===
OUTER enter scenarioBefore
ADVICE before throws
OUTER caught IllegalStateException:before advice failed
CLIENT exception=IllegalStateException:before advice failed
=== returning ===
OUTER enter scenarioReturning
TARGET returning
ADVICE afterReturning result=RETURNING-OK
OUTER caught IllegalStateException:returning advice failed
CLIENT exception=IllegalStateException:returning advice failed
=== throwing ===
OUTER enter scenarioThrowing
TARGET throwing
ADVICE afterThrowing original=business throwing
OUTER caught IllegalStateException:throwing advice failed
CLIENT exception=IllegalStateException:throwing advice failed
CLIENT cause=IllegalArgumentException:business throwing
=== finally normal ===
OUTER enter scenarioFinallyNormal
TARGET finally normal
ADVICE afterFinally throws
OUTER caught IllegalStateException:after advice failed
CLIENT exception=IllegalStateException:after advice failed
=== finally error ===
OUTER enter scenarioFinallyError
TARGET finally error
ADVICE afterFinally throws
OUTER caught IllegalStateException:after advice failed
CLIENT exception=IllegalStateException:after advice failed
=== around ===
OUTER enter scenarioAround
ADVICE around enters
TARGET around
ADVICE around caught business around
OUTER caught IllegalStateException:around advice failed
CLIENT exception=IllegalStateException:around advice failed
CLIENT cause=IllegalArgumentException:business around
=== healthy ===
OUTER enter scenarioHealthy
TARGET healthy
OUTER returned HEALTHY
CLIENT value=HEALTHY
```

This is the **expected stdout from the code**, not a claim that Maven was executed in a live runtime. The demo uses only the beans and aspects defined above. Logs emitted by the framework or Maven are not part of the expected sequence.

### 9.5. Analyzing why the trace has this order

**Case `before`:** outer around entered and printed `OUTER enter`. The failing before advice threw immediately, so **there is no `TARGET before` line**. The outer observer caught the advice error and the caller received it.

**Case `returning`:** the target returned successfully (`TARGET returning` appears), after-returning received `"RETURNING-OK"` and then threw. The observer and caller see **returning advice failed**, without receiving `RETURNING-OK`. This is dangerous if the target already produced side effects.

**Case `throwing`:** the target threw `IllegalArgumentException("business throwing")`, inner after-throwing received the original error and threw `IllegalStateException("throwing advice failed", original)`. The outer observer sees the new error, yet the client can still trace back to the original error via `getCause()`.

**Case `finally normal`:** the target completed normally, and then `@After` threw. The caller receives a failure instead of `FINALLY-OK`. Running "finally" after return does not mean it is harmless to the return path.

**Case `finally error`:** the target threw `IllegalArgumentException("business finally")`, yet `@After` threw `IllegalStateException("after advice failed")`. Because the advice did not preserve the original error, the client has no `CLIENT cause` line. This is an example of **losing the root cause**.

**Case `around`:** the target threw a business error; inner around caught and wrapped it with a cause; outer received the wrapper. No cause is lost because the code preserved `original`.

**Case `healthy`:** no failing advice applies to this method; the outer observer sees the target return normally. `OUTER returned HEALTHY` contrasts with the six error paths, confirming the outer observer is not the cause of the failures.

### 9.6. What when one method matches multiple failing advice methods?

The demo separates methods by advice type **so outcomes are clear and independent of ordering among multiple advice methods of the same type**. In real applications, when multiple advice methods match one method, you must analyze nesting order.

Example with two aspects:

```text
OuterAspect @Order(1)
    |
    +-- @Around
          |
          +-- InnerAspect @Order(2)
                |
                +-- @AfterReturning or @AfterThrowing
                +-- @After
                |
                +-- Target
```

If an inner advice throws an exception, the outer around can catch it because `pjp.proceed()` encloses the entire inner chain. If the **outer** advice throws a new exception after calling `proceed()`, inner advice that already finished earlier does not re-run to observe the outer error.

Do not assume log line order when one aspect contains multiple `@After` methods of the same kind based solely on source declaration order; Spring docs do not guarantee such ordering.

## 10. Distinguishing "advice errors" from "target errors" in large systems

### 10.1. Using exception types and cause chains

A custom exception dedicated to advice errors can distinguish the source:

```java
public class AdviceInfrastructureException
        extends RuntimeException {

    public AdviceInfrastructureException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

This is a **standalone illustrative class**. You do not need a new exception class for every minor advice, but if the system genuinely wants to propagate infrastructure failures, a clear type and full cause chain help:

- Separate business errors from telemetry/infrastructure errors.
- Avoid retrying business operations for the wrong reason.
- Simplify logging and alerting rules.
- Preserve stack traces of both advice and target when an original failure exists.

**However, a typed wrapper does not replace the bigger design decision:** whether a non-essential logging/metrics failure should break a business call at all.

### 10.2. Inspecting exceptions at the outer boundary

An outer around can record exception context:

```java
@Around("execution(public * com.example.app.service..*.*(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (Throwable failure) {
        System.out.println(
            "FAILED " + pjp.getSignature().toShortString()
                + " with " + failure.getClass().getSimpleName()
        );
        throw failure;
    }
}
```

This is a **snippet** requiring its own aspect bean, proper pointcut, and ordering. It observes exceptions from **the portion of the chain inside it**. It is not a universal observer for every bean or every JVM error if the Spring proxy is not invoked.

Do not assume an exception seen by the observer is always a "target failure"; it may be an error from another inner before/after/around advice.

### 10.3. Preserving the exact Throwable with `throw failure`

In the observer snippet, `throw failure;` rethrows the exact existing object without creating a different exception. When logging succeeds, the caller still receives the same throwable. This is generally the safe choice when the aspect's responsibility is solely monitoring.

Important phrasing in production logs:

- `method execution observed as failed` does not mean the target caused the failure.
- `proxy invocation failed` is more accurate when advice could be the cause.
- `business rejected` should only be used when backed by the service contract or a business exception type.

## 11. Safe advice design: when to swallow errors vs. when to propagate

There is no "catch every exception in advice" rule for all requirements. You must consider the **advice's purpose**.

### Non-essential cases: best-effort logging or metrics

A defensive approach:

```java
@Before("execution(* com.example.app.service..*.*(..))")
public void before(JoinPoint jp) {
    try {
        telemetryRecordSafely(jp.getSignature().toShortString());
    } catch (RuntimeException telemetryFailure) {
        // Send error to fallback diagnostic path if available;
        // do not obscure business flow due to non-essential telemetry.
    }
}
```

This is a **non-standalone conceptual pattern**, since `telemetryRecordSafely(...)` must be defined and the `@Aspect` bean registered. If you catch errors to protect the business call, include **fallback reporting** or appropriate health monitoring; swallowing errors so nobody knows logging/metrics are broken creates observability blind spots.

Do not catch `Throwable` and swallow `OutOfMemoryError`/`StackOverflowError` just to keep a request "successful"; severe errors should generally not be hidden.

### Essential cases: authorization or invariant checks

If an aspect is responsible for **denying access**, throwing an exception may be the exact intended behavior:

```java
@Before("execution(* com.example.app.service..*.sensitive(..))")
public void denyIfNotAllowed() {
    if (!accessAllowed()) {
        throw new SecurityException("access denied");
    }
}
```

This snippet requires implementing `accessAllowed()` appropriately. When permissions are insufficient, preventing the target from running is right. Never catch this exception and return success merely to hide errors from the client.

**Distinguish clearly:** an exception designed as a **policy decision** vs. an unintended exception from a failing telemetry/database/logger dependency. The two cases must not share the same recovery policy.

### When cleanup fails

An `@After` responsible for cleanup must clarify:

- Is cleanup mandatory to preserve consistency, or just auxiliary resource release?
- If the target already failed, should the original exception remain **primary** with the cleanup failure recorded in **suppressed/cause**?
- If the target succeeded yet cleanup failed, is reporting business success still allowed?
- Is cleanup retryable or idempotent?
- Should resource management live in business code/`try-with-resources` instead of an `@After` that lacks direct access to the original exception?

Do not default to `@After` for resources whose lifecycle requires transactional or ownership guarantees inside the business method.

## 12. When you need to preserve both target errors and cleanup errors

An outer `@Around` can intentionally retain both primary and secondary exceptions when **it owns managing both**:

```java
@Around("execution(* com.example.app.service..*.operate(..))")
public Object carefullyCleanup(ProceedingJoinPoint pjp)
        throws Throwable {

    Throwable primary = null;

    try {
        return pjp.proceed();
    } catch (Throwable failure) {
        primary = failure;
        throw failure;
    } finally {
        try {
            releaseOwnedResource();
        } catch (Throwable cleanupFailure) {
            if (primary != null) {
                if (cleanupFailure != primary) {
                    primary.addSuppressed(cleanupFailure);
                }
            } else {
                throw cleanupFailure;
            }
        }
    }
}
```

This is **valid Java pseudocode inside an advice body**, requiring `releaseOwnedResource()` and an aspect bean; use it as a mental model, not for blind copy-pasting everywhere. It intentionally:

- Keeps **primary** if the inner chain throws and attaches the cleanup error via `getSuppressed()`, instead of losing primary.
- Propagates the cleanup failure if the inner chain succeeded, since there is no other primary error.
- Avoids `addSuppressed` if it is the exact same throwable instance.

**Limitation:** catching `Throwable` here is primarily to retain and propagate, not to swallow `Error`. If `releaseOwnedResource()` does not have its lifecycle owned by the aspect, do not attempt cleanup inside the aspect.

A simpler choice is Java `try-with-resources` when the resource belongs to **the business method itself**, because Java provides standard suppressed-exception semantics for resource closing failures.

## 13. Interaction with Spring advice ordering

### 13.1. Same-aspect precedence

Spring Framework 6.2 documentation specifies precedence **from highest to lowest** among advice types in the same `@Aspect`:

```text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
```

Because `@After` uses after-finally semantics, on normal exit it actually runs **after** `@AfterReturning`; on exceptional exit it runs **after** `@AfterThrowing`, when those advice methods belong to the same aspect and match.

An exception thrown by one advice can change what **outer** layers see, but it does not cause interceptors **already exited** to re-run.

### 13.2. Cross-aspect precedence

`@Order(1)` has higher precedence than `@Order(2)`. Higher-precedence aspects **enter first and exit last** across nested calls. Therefore, an outer `@Around` can catch errors originating from the target **as well as from inner advice**.

When no ordering is declared across different matching aspects, relative order is not guaranteed; never rely on alphabetical class names or source declaration order.

### 13.3. Advice of the same type in the same aspect

Two `@After` methods matching the same method, declared as `first()` and `second()` in the same `@Aspect`, have no ordering contract based on source position. If order affects results or errors, combine the logic into one advice method or split into separate aspects with explicit `@Order`.

### 13.4. What can an outer aspect observe?

| Error location | Has outer around entered and enclosed the error site? | Can outer catch it? |
| --- | --- | --- |
| Inner target method | Yes | Yes |
| Inner `@Before` | Yes | Yes |
| Inner `@AfterReturning` | Yes | Yes |
| Inner `@AfterThrowing` | Yes | Yes |
| Inner `@After` | Yes | Yes |
| Advice sitting **outside** the outer around | No | No |
| Another object not going through a Spring AOP proxy | No | No |
| Asynchronous task on another thread after proxy returns | Not directly via synchronous `proceed()` | Cannot assume |

For that reason, calling something "outer" is only meaningful once **chain ordering has been verified**.

## 14. Spring transactions, caching, async, and retry: where advice errors cause confusion

### 14.1. Transaction advisor and errors thrown after the target

With `@Transactional`, transaction behavior is managed by a separate interceptor. If a custom `@AfterReturning` throws an exception:

- If the custom advice is **inside the transaction interceptor**, the transaction interceptor can observe the exceptional completion and decide to roll back per its rollback rules.
- If the custom advice is **outside the transaction interceptor**, the transaction interceptor may already have committed or rolled back before the custom advice threw. The caller still receives an exception, yet data may already be committed.

Therefore, **do not conclude from a client receiving an exception that the transaction definitely rolled back**. Check transaction advisor order, `rollbackFor`/`noRollbackFor`, and run integration tests against a real database when data impact matters.

### 14.2. Cache interceptor and failing advice

If `@Cacheable` serves a cache hit, the target method may not run. An outer custom advice can still observe the cached result, while advice inside the cache interceptor may not be entered. If an after-returning advice throws an error on a cache hit, the client sees a failure even though the cache held valid data.

Do not treat `@AfterReturning` as guaranteed proof that "the target method just executed."

### 14.3. Async interceptor

With `@Async` or `CompletableFuture`, an exception inside an async task is not identical to a synchronous exception caught by outer advice at the proxy call. Check:

- Is the advisor before or after the async boundary?
- Does the proxy method return `Future`/`CompletableFuture` or `void`?
- Does the error occur immediately at scheduling time or later when the task runs?
- Does the caller observe exceptions via `join()`/`get()` or a separate async handler?

An outer synchronous `@Around` cannot automatically catch late completion failures after `proceed()` has already returned a future normally.

### 14.4. Retry

If a retry interceptor retries the target multiple times, an error from an inner advice can **trigger retries** just like a business error depending on configuration. For example, if the target already wrote data and then after-returning advice throws `IllegalStateException`, retry may call the target again, causing **duplicate writes**.

Conversely, if the advice sits outside the retry interceptor, an error thrown by the advice after retry finishes may not be seen by the retry interceptor at all.

Ask: "Do we want to retry business errors, transport errors, or telemetry errors too?" Do not blindly mark every `RuntimeException` as retryable.

## 15. Logging, metrics, and tracing without losing the original error

A Spring aspect used in production should satisfy:

1. **Advise only the exact Spring beans and methods needed.** Overly broad pointcuts can intercept the logger or metrics infrastructure itself, causing loops.
2. **Never log secrets/PII.** `JoinPoint.getArgs()` can contain passwords, tokens, or sensitive payloads; select only required metadata and mask carefully.
3. **Do not throw errors just because a formatter/`toString()` failed** if tracing is best-effort.
4. **Define the advice's contract:** policy-enforcing (allowed to fail closed) vs. observability-only (should isolate secondary failures).
5. **Preserve the cause chain** if you decide to wrap a business error.
6. **Do not silently swallow all exceptions** leaving the system blind; report telemetry failures via a separate channel and health checks.
7. **Do not hold per-request state in mutable fields of a singleton aspect** without explicit synchronization or thread-safe design.
8. **Do not automatically retry the whole target because a metric failed.** Evaluate idempotency and transaction boundaries.
9. **Use `@Order`** when exception flow across aspects is a requirement.
10. **Write integration tests invoking beans from the context** to verify what the caller sees, rather than only unit-testing the advice method directly.

### When logging itself can throw exceptions

Errors do not come only from network clients. An advice can fail when:

- Calling `toString()` on a domain object (arbitrary implementation, may throw).
- Serializing cyclic or invalid objects.
- Accessing lazy-loaded properties outside a transaction.
- Writing to a logger appender encountering an I/O error.
- Recording metrics with high tag cardinality or a throwing backend client.
- Casting `JoinPoint.getArgs()[i]` to the wrong type or accessing an out-of-bounds index.
- Calling `getCause().getMessage()` without checking for `null`.
- Using a shared mutable collection in a singleton aspect without thread safety.

Hence, "the advice code is just one line of logging" does not mean "the advice cannot cause an error."

## 16. Debugging checklist when the client receives an unexpected exception

| Observation | Priority diagnosis |
| --- | --- |
| No `TARGET` log, only an exception | Did `@Before` or an outer `@Around` throw/short-circuit before the target? |
| Target logged success, yet client received 5xx | Did `@AfterReturning` / `@After` / outer `@Around` throw after the target? |
| Target threw error A, yet caller received B | Did advice wrap or override it? Are `cause`/`suppressed` preserved? |
| `@AfterThrowing` did not log error B from companion advice | Spring does not treat it as a global callback for errors thrown by other after advice |
| Cleanup log appeared and the original error vanished | Did `@After` throw a new exception from finally? |
| Error turned into success/fallback | Which `@Around` caught and returned? |
| Proxy exists, yet advice did not run | Pointcut mismatch, uninterceptable method, self-invocation, or order short-circuit |
| Operation retried even though target finished writing | Did the retry interceptor mistake an after-advice error for a target error? |
| Spring transaction committed, yet client received an exception | Did advice throw outside the transaction interceptor after commit? |
| Exception appears only in Spring Boot, not in plain tests | Different proxy strategy, advisor auto-configuration, or ordering? |
| Outer log did not see the error | Does the outer observer actually wrap the failing advice/target per `@Order`? |
| Async client did not see the error immediately | Did the failure happen after proxy return inside a future/executor? |

### Proxy inspection utility

```java
Object bean = context.getBean("scenarioService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
```

This is a snippet requiring a Spring context and importing `org.springframework.aop.support.AopUtils`. In the **complete demo**, the bean had a JDK dynamic proxy due to its interface and specific configuration. However, **having a proxy** does not prove a specific advice matches; check both pointcuts and call paths.

## 17. Testing exception propagation behavior

When writing tests for aspects, do not assert only target output. Test at least:

- **Before error:** target method execution count is 0; caller sees the error from before advice.
- **After-returning error:** target execution count is 1 and returns normally internally; caller sees the advice error instead.
- **After-throwing error:** target throws original error, advice throws wrapper; caller receives wrapper and `getCause()` matches the original error.
- **After/finally on normal return:** caller can observe the cleanup error.
- **After/finally on target error:** verify presence or absence of the original cause per the advice's policy.
- **Around wrap:** caller receives wrapper and original exception remains in the chain.
- **Healthy method:** unaffected by failing advice targeting other methods.
- **Ordering:** outer observer receives exceptions from inner advisors when configured properly.
- **Bypassing proxy:** calls on a `new` instance do not trigger Spring advice; test self-invocation separately.
- **Transaction/cache/retry:** re-test with real advisors if those are critical boundaries.

You can use JUnit 5 with `assertThrows` and `assertSame` on the cause object, but consider using an event recorder or log capture to verify **execution order**. A single business return or exception does not prove the order of all advice.

Conceptual example:

```java
IllegalStateException seen = assertThrows(
    IllegalStateException.class,
    service::scenarioThrowing
);

assertEquals("throwing advice failed", seen.getMessage());
assertInstanceOf(IllegalArgumentException.class, seen.getCause());
assertEquals("business throwing", seen.getCause().getMessage());
```

This is a **JUnit 5 snippet** requiring test dependencies/imports and a Spring bean retrieved from the context, not a standalone Java file. This test verifies that the after-throwing advice's wrapper retains the original exception.

## 18. Self-check questions

**1.** The target has not run; `@Before` throws `SecurityException`. What can the caller receive?  
**Answer:** `SecurityException` from the before advice if there is no outer handler; the target does not execute.

**2.** The target returns `"OK"`, yet `@AfterReturning` throws `IllegalStateException`. Is the client guaranteed to see `"OK"`?  
**Answer:** No. Unless the advice error is caught, the client receives the exception instead of the normal return.

**3.** The target throws `IllegalArgumentException`, and `@AfterThrowing` throws a new `IllegalStateException` without a `cause`. Is the old error guaranteed to be in `getCause()`?  
**Answer:** No. To preserve it, use a wrapper constructor taking a cause or a suppressed-exception policy at the appropriate layer.

**4.** `@After` throws an error on the `finally` path while the target is also throwing an error. Which exception can reach the caller?  
**Answer:** The new exception from `@After` can mask the target exception.

**5.** Is an `@AfterThrowing` in the same aspect guaranteed to catch exceptions thrown by a companion `@AfterReturning`?  
**Answer:** No. Spring does not define it as a general exception callback for companion after advice.

**6.** Can an outer `@Around` catch an error from an inner aspect's `@Before`?  
**Answer:** Yes, if the outer around has entered, wraps the inner advice, and `pjp.proceed()` throws that error.

**7.** If an outer `@Around` catches every `RuntimeException` and returns `"FALLBACK"`, could it accidentally swallow authorization or advice errors?  
**Answer:** Yes. Catches must be narrow and match the contract.

**8.** The target wrote to the database successfully, the client receives an error from metric advice, and then retries. What is the risk?  
**Answer:** Duplicate side effects if the operation is not idempotent; transaction and retry ordering must be checked.

**9.** An aspect contains two matching `@After` methods. Does the method written earlier in source definitely run first?  
**Answer:** There is no ordering contract based on Java source declaration position.

**10.** Does `@After` always run even when an outer `@Before` throws before the after advice's part of the chain is entered?  
**Answer:** No. An interceptor that was never entered cannot run its finally block.

**11.** Can an `@Order(1)` outer observer observe an error thrown by an `@Order(2)` inner advice?  
**Answer:** Yes, if both match, the outer around wraps the inner call, and the error is not handled before reaching the observer.

**12.** Why should a wrapped logging error retain `cause` if it must propagate?  
**Answer:** So the original error information and stack trace are not lost when the caller receives only the wrapper exception.

## 19. Official documentation

- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, `@Around`, exception semantics, `proceed()`, and *Advice Ordering*. Note the remark on `@AfterThrowing` limitations regarding errors thrown by companion after advice.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): proxy boundaries, JDK/CGLIB, and self-invocation.
- [Spring Framework 6.2 — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): aspect registration and Spring-managed auto-proxying.
- [Spring Framework 6.2 — Declarative Transactions](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative.html): transaction advice and exception/transaction relationships.
- [Spring Framework 6.2 — Understanding the Spring Transaction Abstraction](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction.html): transaction principles and rollback depending on interceptor/configuration.
