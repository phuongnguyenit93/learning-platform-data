# Do Not Treat `@AfterThrowing` as Proof That All Errors Were Handled in Spring AOP

## 1. Core idea: observing an exception differs from handling an exception

In Spring Framework, an advice declared with `@AfterThrowing` can run when a **method execution matching a pointcut** on a Spring-managed bean **exits by throwing an exception** through a Spring AOP proxy. It is a good place for error logging, metrics, auditing, or diagnostics; **it is not proof that the error has been resolved**.

Example:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.OrderService.submit(..))",
    throwing = "error",
    argNames = "error"
)
public void observedFailure(IllegalArgumentException error) {
    System.out.println("observed: " + error.getMessage());
}
~~~

Suppose `OrderService.submit(...)` throws `IllegalArgumentException("invalid-order")`. In a properly configured Spring AOP application, the advice may print `observed: invalid-order`, **and then the caller still receives that exact exception**. Recording an exception does not automatically turn it into a success result, an HTTP status, a user response, a transaction rollback, or a repaired record.

**Three concepts must be separated:**

- **Observed:** the advice saw a Throwable exiting a matching method execution.
- **Handled:** some component actually decided how to recover, translate the error, return a response, or propagate in a controlled manner.
- **Resolved:** the system satisfies its business contract after the failure, such as a valid state, consistent resources, or a successful retry/fallback flow.

`@AfterThrowing` primarily supplies an **exceptional-exit observation signal**; it proves neither of the latter two states.

This lesson focuses strictly on **Spring Aspect/proxy-based Spring AOP**, matching the module's Special Note. It does not repeat general Aspect theory.

## 2. Official semantics of @AfterThrowing in Spring

Spring Framework describes `@AfterThrowing` as advice that runs when a **matched method execution exits by throwing an exception**. Specifically:

1. The class containing the advice must be registered with Spring as an **`@Aspect` bean**.
2. Spring AOP must be enabled (e.g., `@EnableAspectJAutoProxy` in plain Spring Framework).
3. The pointcut must match the **method execution** on the target bean.
4. The caller must go through the **Spring AOP proxy**, not invoke the target directly outside the container.
5. The invocation must end with an exception **escaping the advised boundary**, not merely an exception created and caught internally.
6. If `throwing = "error"` is used with a typed parameter, the Throwable must be **compatible with that type**.

If all conditions hold, the advice can run. However, when the advice method simply logs and returns normally, **the original exception continues propagating**, unless another interceptor or the caller actively handles it.

~~~text
Caller
   |
   v
Spring AOP proxy
   |
   +--> matched target method
   |        |
   |        +-- throw IllegalArgumentException("invalid-order")
   |        |
   +--> @AfterThrowing advice
   |        |
   |        +-- log / metrics / audit (does NOT handle by itself)
   |
   +--> exception exits proxy
   |
   v
Caller must catch or keep propagating
~~~

The crux is that **`@AfterThrowing` happens along the exception propagation path**, and does not convert an *exceptional exit* into a *normal return*. Nor does it cover every error from other advice: Spring documentation notes it is not a **general exception handling callback** for exceptions caused by companion `@After` or `@AfterReturning` advice.

## 3. What does one log line tell you—and what does it not?

Suppose you observe:

~~~text
AOP observed: submit -> invalid-order
~~~

Valid conclusions:

- An invocation occurred where the advice was triggered.
- At the observation boundary, the method execution exited via an exception path matching the binding.
- Code inside the advice printed the log line.
- If the log came from the `Throwable` parameter, we know the throwable was passed into the advice **per binding semantics**.

**You cannot conclude from this line alone that:**

- The caller caught the exception.
- The HTTP endpoint returned an appropriate status.
- The transaction rolled back or committed as intended.
- The database was recovered.
- The client received a helpful message.
- A retry succeeded.
- All other application exceptions were observed.
- The error disappeared from the system.
- Every inner/outer interceptor ran.
- The event was successfully delivered to an external logging/metrics backend.

A test asserting only `logs.contains("AOP observed")` is an **observation test**, not a business-success or exception-handling test.

## 4. Comparing @AfterThrowing with other Spring mechanisms

| Tool / location | Primary function | Automatically turns an error into a valid result? |
| --- | --- | --- |
| `@AfterThrowing` on `@Aspect` | Observes exceptions exiting a method execution per pointcut and binding type | **No** |
| `@After` | Runs after-finally whether the method returns normally or throws | No |
| `@AfterReturning` | Receives a callback when the method execution returns normally | No; does not run if an error escapes the method |
| `@Around` with `try/catch` and `proceed()` | Can catch, rethrow, translate, or return a fallback per contract | **Possible**, when code intentionally does so |
| `try/catch` in the service | Handles errors where business logic ownership lives | **Possible** |
| Caller `try/catch` | Handles exceptions at the method-call boundary | **Possible** |
| Spring MVC `@ExceptionHandler` or `@ControllerAdvice` | Converts exceptions in the web request lifecycle into appropriate HTTP responses | **Possible**, per configuration |
| Spring transaction interceptor | Applies rollback/commit policy at the transaction boundary | Can roll back; **not synonymous with exception being handled** |
| Spring Retry / resilience policy | Can retry/fallback per its own rules | Depends on configuration, idempotency, and actual outcome |

**Do not conflate concepts:** "exception was logged", "exception was caught", "request got an HTTP response", "transaction rolled back", and "business operation recovered" are **different events**.

For example, Spring MVC may turn an exception into HTTP 400 via `@ExceptionHandler` while Spring AOP `@AfterThrowing` merely logs the error at the service layer. Or a caller may catch the exception itself with no web layer involved.

## 5. `throwing` binding observes only compatible error types

An advice:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.OrderService.*(..))",
    throwing = "error",
    argNames = "error"
)
public void afterInvalidOrder(IllegalArgumentException error) {
    // Only exceptions compatible with IllegalArgumentException.
}
~~~

is constrained by **both conditions**:

1. The pointcut selects method executions on `OrderService`.
2. The exception exiting the method must be compatible with `IllegalArgumentException`.

Comparison:

| Advice parameter | Errors that can bind | Not automatically received |
| --- | --- | --- |
| `IllegalArgumentException error` | `IllegalArgumentException` and subclasses | `IllegalStateException` on a separate branch |
| `IllegalStateException error` | `IllegalStateException` and subclasses | `IllegalArgumentException` |
| `RuntimeException error` | `RuntimeException` and subclasses | Checked `IOException`, `AssertionError` |
| `Exception error` | `Exception` and subclasses | `Error` that is not an `Exception` |
| `Throwable error` | Matching Throwables from the method join point | Does not prove errors elsewhere pass through the pointcut |

**Using `Throwable` does not turn the advice into a global handler.** It only widens the **bindable exception types**, not across all beans, all join points, or invocations bypassing the Spring proxy.

The name in `throwing = "error"` must match the Java advice parameter name. `argNames = "error"` declares the binding explicitly to avoid relying on how the compiler retains parameter names. If `JoinPoint` is the first parameter, Spring allows omitting the `JoinPoint` parameter name from `argNames` per documented binding rules.

## 6. Internally caught exceptions: @AfterThrowing receives no signal

A Spring bean target:

~~~java
public String recoverInternally() {
    try {
        throw new IllegalArgumentException("temporary");
    } catch (IllegalArgumentException ex) {
        return "RECOVERED";
    }
}
~~~

If a caller invokes `recoverInternally()` through the proxy:

- Inside the target, an exception was thrown and **caught right inside the method**.
- From Spring AOP method execution's viewpoint, the method **returned `"RECOVERED"` normally**.
- `@AfterThrowing` **does not run** for an internally handled exception.
- A matching `@AfterReturning` can run, since there was a normal return.
- That **does not** prove no error occurred inside the method.

Therefore, **no `@AfterThrowing` log does not mean no error occurred**, especially when code uses catch/fallback.

The converse also matters: **having an `@AfterThrowing` log does not mean the error was handled**. Neither inference works automatically in reverse.

## 7. Caller catch and @AfterThrowing do not conflict

Caller code:

~~~java
try {
    service.submit(true);
} catch (IllegalArgumentException ex) {
    System.out.println("caller caught: " + ex.getMessage());
}
~~~

If `submit(true)` is called through a Spring proxy and matches the pointcut and throwing type, the sequence can be:

~~~text
target: submit
advice observed: submit -> invalid-order
caller caught: invalid-order
~~~

At the moment `@AfterThrowing` logs, the exception is **exiting the matched method execution**. The caller can still catch it **afterwards**. Hence the advice running and the caller catching **are not mutually exclusive**.

**Do not mistakenly conclude the advice handled the error on behalf of the caller.** If you remove `try/catch` at the caller with no other handling layer, the exception still propagates per standard Java/Spring rules.

Nor should you conclude the caller caught the right exception type just because the advice used typed binding. Each layer can have a different contract; callers should have their own tests for propagation and error responses.

## 8. Spring AOP example with an outer interceptor handling fallback

An `@Around` advice can intentionally catch exceptions:

~~~java
// Snippet inside an @Aspect class registered as a Spring bean.
@Around("execution(* example.OrderService.submit(..))")
public Object recoverAtBoundary(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalArgumentException ex) {
        return "FALLBACK";
    }
}
~~~

This snippet demonstrates what `@AfterThrowing` **does not do by default**: turning an exception into a normal return. When applied, however, it **changes the business contract**, so it is valid only when the fallback is accepted by business requirements.

You must also consider **position in the advisor chain**:

- If `@Around` sits **outside** `@AfterThrowing`, the inner after-throwing advice can observe the exception first, then the outer catch returns the fallback; the caller sees only success.
- If `@Around` sits **inside** `@AfterThrowing` and catches the exception to return a fallback, the outer after-throwing advice may **not run** because it sees a normal return.
- If multiple aspects have equal precedence or no declared order, never rely on accidental ordering.

**Warning:** A fallback `@Around` must not arbitrarily swallow all `Throwable`s in a shared aspect. It can mask system errors, change HTTP statuses, break retry/rollback semantics, and leave data in unintended states.

## 9. Runnable Maven/Java 17+ project: observation ≠ handling

The project uses **Java 17+**, Spring Framework **6.2.19**, AspectJ Weaver **1.9.25.1**. A Spring service has five call paths designed to distinguish:

1. Normal return: no exceptional exit.
2. Throwing `IllegalArgumentException` to the caller: `@AfterThrowing` records it but **does not catch on behalf of the caller**.
3. Catching the exception inside the target: the aspect sees no exceptional exit.
4. Throwing a different exception type `IllegalStateException`: typed advice does not match.
5. Outer method calling `this.submit(true)` internally: the proxy sees only the exceptional exit of the **outer method**, creating no separate invocation for the inner method.

The project needs no Spring Boot, HTTP server, database, or transaction manager.

### 9.1. Directory structure

~~~text
spring-after-throwing-not-handled/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── OrderService.java
    ├── FailureObserverAspect.java
    └── Main.java
~~~

### 9.2. Maven `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-after-throwing-not-handled</artifactId>
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

The project uses the Spring Framework BOM so Spring modules share consistent versions. For real Spring Boot applications, prefer letting Boot manage starter/library versions; do not force a learning project's versions onto another application.

### 9.3. `OrderService.java` — business target

~~~java
package example;

public class OrderService {

    public String submit(boolean invalid) {
        System.out.println("target: submit");
        if (invalid) {
            throw new IllegalArgumentException("invalid-order");
        }
        return "ACCEPTED";
    }

    public String recoverInternally() {
        System.out.println("target: recover");
        try {
            throw new IllegalArgumentException("temporary");
        } catch (IllegalArgumentException ex) {
            System.out.println("target: recovered temporary");
            return "RECOVERED";
        }
    }

    public void failState() {
        System.out.println("target: failState");
        throw new IllegalStateException("storage");
    }

    public String forwardInternally() {
        System.out.println("target: forwardInternally");
        return this.submit(true);
    }
}
~~~

Here `submit(true)` throws an error and `submit(false)` succeeds. `recoverInternally()` catches the error right inside. `failState()` throws a different exception type. `forwardInternally()` calls `this.submit(true)` directly, an **internal call on the target** that does not pass through the Spring AOP proxy a second time.

### 9.4. `FailureObserverAspect.java` — observational-only aspect

~~~java
package example;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class FailureObserverAspect {

    private final CopyOnWriteArrayList<String> observed =
        new CopyOnWriteArrayList<>();

    @AfterThrowing(
        pointcut = "execution(* example.OrderService.*(..))",
        throwing = "failure",
        argNames = "failure"
    )
    public void observe(JoinPoint jp, IllegalArgumentException failure) {
        String method = jp.getSignature().getName();
        String value = method + ":" + failure.getMessage();
        observed.add(value);
        System.out.println("advice observed: " + method
            + " -> " + failure.getMessage());
    }

    public List<String> observations() {
        return List.copyOf(observed);
    }
}
~~~

**Why doesn't the advice "handle" the exception?**

- It records an entry and logs; there is no `try/catch` enclosing the target execution.
- A `void`-returning advice method does not turn a target exception into success.
- The advice has no `return` to replace the target's return value.
- For `IllegalStateException`, the typed parameter `IllegalArgumentException` is **incompatible**, so the advice does not run.
- In `recoverInternally()`, no exception escapes, so it does not run either.
- `observations()` returns only a copy of events **recorded by the observer**, not a list of **all handled errors**.

`CopyOnWriteArrayList` makes a convenient testing example, but in production do not accumulate error messages in memory indefinitely, and do not log raw messages if the data can be sensitive.

### 9.5. `AppConfig.java` — registering Spring-managed beans

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public FailureObserverAspect failureObserverAspect() {
        return new FailureObserverAspect();
    }
}
~~~

- `@EnableAspectJAutoProxy` turns on Spring AOP support for `@AspectJ` in a plain context.
- `@Bean` registers both the target and the aspect in the Spring container; `@Aspect` alone on a class does not register a bean.
- `proxyTargetClass = true` lets the demo retrieve the bean by concrete class through a CGLIB proxy.
- The pointcut is scoped to `OrderService`, not automatically applied to all beans.
- Proxy-based Spring AOP still has the self-invocation limitation even with CGLIB selected.

### 9.6. `Main.java` — five scenarios and assertions

~~~java
package example;

import java.util.List;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService orders = context.getBean(OrderService.class);
            FailureObserverAspect observer =
                context.getBean(FailureObserverAspect.class);

            System.out.println("spring AOP proxy: "
                + AopUtils.isAopProxy(orders));

            System.out.println("-- normal return --");
            System.out.println("caller: " + orders.submit(false));

            System.out.println("-- exception still reaches caller --");
            try {
                orders.submit(true);
            } catch (IllegalArgumentException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }

            System.out.println("-- exception caught inside target --");
            System.out.println("caller: " + orders.recoverInternally());

            System.out.println("-- different exception type --");
            try {
                orders.failState();
            } catch (IllegalStateException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }

            System.out.println("-- self invocation --");
            try {
                orders.forwardInternally();
            } catch (IllegalArgumentException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }

            List<String> expected = List.of(
                "submit:invalid-order",
                "forwardInternally:invalid-order"
            );
            if (!expected.equals(observer.observations())) {
                throw new AssertionError(
                    "Unexpected observations: " + observer.observations()
                );
            }
            System.out.println("verified observed count: "
                + observer.observations().size());
        }
    }
}
~~~

The `caller caught` lines prove **the caller** caught the exceptions, not the aspect. The assertion verifies the exact exceptional exits **that the Spring aspect observed**.

### 9.7. Run command

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

**Stdout of the `System.out.println` statements in the project:**

~~~text
spring AOP proxy: true
-- normal return --
target: submit
caller: ACCEPTED
-- exception still reaches caller --
target: submit
advice observed: submit -> invalid-order
caller caught: invalid-order
-- exception caught inside target --
target: recover
target: recovered temporary
caller: RECOVERED
-- different exception type --
target: failState
caller caught: storage
-- self invocation --
target: forwardInternally
target: submit
advice observed: forwardInternally -> invalid-order
caller caught: invalid-order
verified observed count: 2
~~~

Maven or the runtime may emit additional logs outside the example code; the lines above accurately describe the output printed by the sample classes.

### 9.8. Analysis of each scenario

**Normal return:** `submit(false)` returns `ACCEPTED`; there is no `@AfterThrowing`. This proves only that the method **did not exit via an exception** at the proxy boundary; it does not prove every side effect succeeded in external components.

**Exception still reaches caller:** `submit(true)` throws `IllegalArgumentException`. The aspect records it, and then the caller catches it. If you remove the catch in `Main`, the exception propagates to outer call layers; the advice is not responsible for "resolving" exceptions.

**Caught inside target:** `recoverInternally()` had an error internally, handled it with a local `catch`, and returned `RECOVERED`. There is no after-throwing observation because the exception never exited the method. This is a counterexample to **"no `@AfterThrowing` log ⇒ no error occurred"**.

**Different type:** `failState()` throws `IllegalStateException`, incompatible with parameter `IllegalArgumentException failure`; the aspect does not record it, yet the caller still receives the error. This is a counterexample to **"this observer sees every exception"**.

**Self-invocation:** the caller invokes `forwardInternally()` through the proxy. The target calls `this.submit(true)` directly, **not through the proxy for `submit`**; the exception exits from `forwardInternally()` itself. Thus the callback records **`forwardInternally`**, not a separate callback for the inner `submit`. This illustrates observing the **method join point at the proxy boundary**, not merely where the Throwable was created.

## 10. Outcome table: logged or not, who actually handled it?

| Call | Exceptional exit at proxy? | Did typed `@AfterThrowing(IllegalArgumentException)` run? | Actual handler / handling point |
| --- | --- | --- | --- |
| `orders.submit(false)` | No | No | Normal return; no exception catch needed |
| `orders.submit(true)` | Yes, `IllegalArgumentException` | **Yes**, logged `submit` | `Main.catch(IllegalArgumentException)` |
| `orders.recoverInternally()` | No, caught internally | No | `OrderService.recoverInternally()` |
| `orders.failState()` | Yes, `IllegalStateException` | **No** due to binding type | `Main.catch(IllegalStateException)` |
| `orders.forwardInternally()` | Yes, `IllegalArgumentException` on outer method | **Yes**, logged `forwardInternally` | `Main.catch(IllegalArgumentException)` |
| `new OrderService().submit(true)` outside Spring | Does not go through Spring proxy | No | External caller must catch or propagate |

**Takeaway:** an observable callback does not tell you **who handled the error**. To prove handling, verify the behavior of the responsible layer: service fallback, caller catch, web response, transaction rollback policy, etc.

## 11. Exceptions thrown by advice itself can make everything worse

An after-throwing advice can throw a new exception:

~~~java
@AfterThrowing(
    pointcut = "execution(* example.OrderService.submit(..))",
    throwing = "failure",
    argNames = "failure"
)
public void dangerous(IllegalArgumentException failure) {
    throw new IllegalStateException("logging backend unavailable");
}
~~~

This is a **warning snippet**, not part of the section 9 demo. If run:

- The target may have thrown `IllegalArgumentException("invalid-order")`.
- The advice itself throws `IllegalStateException("logging backend unavailable")`.
- The caller may see the **advice's error instead of the original exception**, losing diagnostic capability or changing transaction/retry semantics.

Therefore, logging/metrics inside `@AfterThrowing` should have a clear **failure policy**. If the goal is best-effort observation, do not let the observability backend throw unchecked exceptions that alter business outcomes. Yet also avoid a silent system-wide `catch(Throwable)` that hides all problems; adopt an appropriate policy for recording instrumentation failures.

The same applies to `@AfterReturning`, `@After`, and `@Around`: advice is real code, so it can throw errors of its own.

## 12. @AfterThrowing is not a global callback for errors from other advice

Spring documentation states clearly: after-throwing advice is for exceptions from the **join point (user-declared target method)**, not a general callback catching errors from a companion `@After` or `@AfterReturning`.

Example:

~~~java
@Aspect
public class ConfusingAspect {

    @AfterReturning("execution(* example.OrderService.submit(..))")
    public void afterSuccess() {
        throw new IllegalStateException("observer failed");
    }

    @AfterThrowing(
        pointcut = "execution(* example.OrderService.submit(..))",
        throwing = "failure",
        argNames = "failure"
    )
    public void afterThrown(Throwable failure) {
        // Do not assume this runs just because afterSuccess() threw.
    }
}
~~~

This is an **explanatory snippet**, not a demo file. Even though an exception escapes the entire Spring proxy when another advice fails, Spring does not guarantee that `@AfterThrowing` in the same aspect acts as a general exception observer for errors from companion advice in that aspect.

If you need to monitor errors at **the boundary of the entire chain**, you can build an `@Around` observer enclosing the layers to watch, using `try/catch(Throwable t)` and `throw t`. However, you must control ordering so the observer genuinely sits outside, and even such wrapping is **not monitoring every error in the JVM**.

## 13. @AfterThrowing and Spring transactions: observation does not prove rollback

In Spring, transactions are typically implemented via a separate advisor/interceptor around `@Transactional` methods. A trace might look like:

~~~text
Caller
  -> Audit/Failure Aspect
      -> TransactionInterceptor
          -> TargetService.method()
          <- throw IllegalStateException
      <- TransactionInterceptor marks rollback / rolls back per policy
  <- Audit/Failure Aspect records exception
  <- Caller
~~~

However, **the order can differ** if the audit/failure aspect sits inside the transaction interceptor or other infrastructure advisors are configured. Do not rely on a single diagram for all applications.

More importantly:

- `@AfterThrowing` **does not command a rollback itself**.
- Spring transaction rollback follows **rules by exception type**, `rollbackFor`/`noRollbackFor` settings, the transaction manager, and propagation.
- An exception **caught and not rethrown** before reaching the transaction interceptor may cause the transaction layer to see a normal return; handling depends on business logic and configuration.
- A transaction can fail during the **commit phase** after the target method returns, at a different point in the interceptor chain.
- A transaction rollback **does not mean the business error was recovered** or the HTTP request was handled.
- An `@AfterThrowing` log entry **cannot by itself assert data consistency**.

**Proper testing:** use integration tests with a real transaction manager and persistence; invoke Spring beans through the proxy and assert exception/HTTP behavior **plus** database state before and after the transaction. Never assert only that a log line exists.

## 14. The web layer handles exceptions via a different mechanism

In Spring MVC, when you need to turn a service exception into an intentional HTTP response, you can use `@ExceptionHandler` in a controller or `@RestControllerAdvice`.

Example **Spring MVC snippet**:

~~~java
@RestControllerAdvice
public class ApiExceptionMapping {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> invalidInput(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body("Invalid request");
    }
}
~~~

This snippet requires the Spring Web/MVC module, appropriate imports, and a web application context; **it does not belong to the standalone Maven project in section 9**.

What happens when a controller calls `OrderService.submit(true)` through a Spring AOP proxy:

1. The target service throws `IllegalArgumentException`.
2. Spring `@AfterThrowing` records the service's exceptional exit.
3. The exception continues to the controller/web exception resolution layer.
4. `@ExceptionHandler` converts the exception into HTTP 400 with a specific response.

Here **@ExceptionHandler** is the layer converting errors into HTTP responses. `@AfterThrowing` is merely an observer at the service join point. Do not confuse the two annotations' responsibilities just because both involve exceptions.

Similarly, command-line apps, message consumers, scheduled tasks, or gRPC services must have **appropriate handling mechanisms at their own boundaries**; `@AfterThrowing` does not replace them.

## 15. AOP proxy boundaries and observation blind spots

### 15.1. Objects created outside Spring

~~~java
new OrderService().submit(true);
~~~

There is no Spring-managed proxy on this call. Regardless of any `@Aspect` class registered in an application context, **this manually `new`-ed instance is not automatically advised by AOP**.

### 15.2. Self-invocation

~~~java
public String forwardInternally() {
    return this.submit(true);
}
~~~

Spring AOP does not automatically intercept an internal method call on `this` while target code is executing. If `forwardInternally()` is called by a client through the proxy and also matches the pointcut, after-throwing sees **the exception exiting `forwardInternally`**, not a new join point for the inner `submit`.

### 15.3. JDK/CGLIB and non-advisable methods

- JDK dynamic proxies are interface-based; callers usually inject through the exposed interface.
- CGLIB proxies are subclass-based; `final`/`private` methods cannot be overridden or advised in the usual way.
- Switching from JDK to CGLIB **does not solve self-invocation** in Spring AOP proxy mode.
- Having a bean proxy where a pointcut matches only certain methods **does not mean every method emits after-throwing events**.

### 15.4. Asynchronous methods

If a method returns `CompletableFuture<T>` or a reactive publisher, errors occurring **after the method has already returned the Future/Publisher** may not produce an immediate exceptional exit at the Spring AOP method boundary as you expect. For asynchronous/reactive applications, instrument **future completion / reactive subscriber lifecycles** or use dedicated observability tooling.

**Do not use `@AfterThrowing` callback counts as total end-to-end error counts** in a system with async tasks without defining the exact observation boundary.

## 16. Counting errors via @AfterThrowing can be wrong in both directions

### 16.1. Undercounting

- Exception caught **inside the target**.
- Exception handled by an inner `@Around` returning a fallback.
- Exception differs from the `throwing` binding type.
- Pointcut does not match the class/method.
- Invocation bypasses the Spring proxy.
- Error occurs after method return in an async/future/publisher.
- Error arises in an infrastructure component or another advice, rather than the matched user-declared target join point.

### 16.2. Overcounting

- A single error crosses **multiple service-layer proxy boundaries** all observed by the aspect.
- Multiple `@Aspect` beans or advisors record the same exception at different layers.
- Retries call the target multiple times, each attempt throwing and being logged separately.
- Nested proxies cause the same failure to appear in multiple interceptor chains.
- An outer method and an inner method **both called via Spring proxies** both observe the same failure across two distinct method invocations.

**Therefore, the metric "`@AfterThrowing` triggered N times" does not equal "N business operations failed."** Define the **unit of counting**: method invocation, attempt, request, transaction, business command, or end-to-end outcome.

For reliable statistics, use a correlation ID/invocation ID (without sensitive data), avoid double-counting within one logical operation, and add end-to-end outcome metrics where needed.

## 17. Testing: do not assert only that the callback was invoked

A test suite needs multiple layers of verification.

### 17.1. Required test matrix

| Case | Can advice observe? | Business behavior to assert |
| --- | --- | --- |
| Method returns normally | No `@AfterThrowing` | Correct return value |
| Method throws matching exception type | Yes, if pointcut/proxy match | Caller still receives the exact Throwable when unhandled |
| Method throws non-matching exception type | Typed observer does not run | Caller still sees the appropriate exception |
| Exception caught internally | No exceptional exit at method boundary | Correct fallback and consistent state |
| Caller catches exception | Observer may run **before** catch | Catch branch executed |
| Self-invocation | No extra inner proxy invocation | Inner join point not falsely recorded |
| Outer `@Around` returns fallback | Depends on advisor ordering | Return/fallback matches contract |
| `@AfterThrowing` itself throws | Risk of masking original exception | Instrumentation failure policy tested |
| `@Transactional` service throws | Depends on pointcut, order, and rollback policy | Assert real database state/transaction outcome |
| Web controller hits error | Observer may log at service | Assert HTTP response/status/body separately |
| Retrying the same operation | May log multiple attempts | Assert a single logical operation outcome where appropriate |
| Future/publisher fails late | Method boundary may miss it | Assert completion/cancellation outcome via matching API |

### 17.2. Testing exact exception type and message

Conceptual JUnit 5 example, requiring `junit-jupiter` and Spring test dependencies if used in a real project:

~~~java
IllegalArgumentException ex = assertThrows(
    IllegalArgumentException.class,
    () -> orders.submit(true)
);
assertEquals("invalid-order", ex.getMessage());
~~~

This is a **test snippet** and must not be pasted verbatim into section 9's `Main.java` if you want to preserve stdout. If a test checks only `observer.observations().size() == 1` without `assertThrows` or state/response checks, it fails to prove proper propagation.

### 17.3. Testing "handled successfully" at the actual handling site

If the service has `recoverInternally()`, assert `"RECOVERED"` and its postconditions. If the controller uses `@ExceptionHandler`, use MockMvc/WebTestClient appropriately to assert the HTTP status. If transaction rollback is required, run a test with real transaction/persistence configuration and verify DB state; `@AfterThrowing` logs alone are insufficient.

**Testing principle:** a test for **observability** and a test for **business handling** are two distinct verifications.

## 18. Common mistakes and fixes

| Symptom / false inference | Accurate explanation | Appropriate action |
| --- | --- | --- |
| "Logged in `@AfterThrowing`, so the error is handled" | Logging does not catch, translate, or fall back | Identify the real handler and test caller outcomes |
| "No `@AfterThrowing`, so no error occurred" | Error may be caught internally, or type/pointcut mismatched | Check boundaries, exception paths, and negative cases |
| "`@AfterThrowing` receives all exceptions" | Only matched method executions and typed bindings | Scope pointcuts/throwables clearly; add observability at the right layer |
| "`throwing=error` catches the exception automatically" | `throwing` only binds the exception to an advice parameter | Put catch/fallback at the layer owning the contract |
| "Void advice means the exception was swallowed" | Completing a void callback does not turn an exceptional exit into success | Assert `assertThrows`/caller catch |
| "A `Throwable` parameter suffices to monitor all JVM errors" | Does not bypass proxy, pointcut, or join point limits | Add application-level error handling and monitoring |
| "Spring transaction surely rolled back when after-throwing logged" | Rollback is governed by tx policy/order/config | Test transaction outcomes and rollback rules |
| "`@AfterThrowing` will catch errors from `@AfterReturning` in the same aspect" | Not a general exception callback | Check docs and use a clearly scoped outer observer if needed |
| "Self-calls always give the inner method AOP advice" | Self-invocation bypasses the proxy | Extract to another bean or route calls through the proxy |
| "Multiple logs mean multiple independent business errors" | One failure can cross multiple boundaries/attempts | Correlate by logical operation |
| "No web handler needed because there's an aspect" | AOP observers do not produce HTTP responses | Use `@ExceptionHandler`/`@ControllerAdvice` appropriately |
| "Adding `catch Throwable` in `@Around` is always safe" | Can swallow `Error`, hide failures, or block rollback | Catch only per defined policy; rethrow when required |
| "Logged exception messages are always safe" | May contain PII or secrets | Standardize event schemas and limit logged data |
| "Measuring exceptions in async methods works like synchronous ones" | Futures/publishers have different completion boundaries | Hook into actual async/reactive lifecycles |
| "Pointcut matching a bean is enough" | Individual methods are the unit of advice | Verify method-level matching and proxy references |

### Practical diagnostic workflow

1. **Verify the aspect bean:** `@Aspect` is registered via `@Component` or `@Bean`; AOP is enabled.
2. **Verify the target bean:** caller gets the Spring-managed proxy, not `new` or an unwrapped target.
3. **Verify the pointcut:** does the method/class/package actually match?
4. **Verify the throwing type:** `Throwable`, `Exception`, or a specialized type?
5. **Verify the error origin:** target method, outer advice, transaction commit, or async completion?
6. **Verify who catches:** target, inner interceptor, outer `@Around`, caller, or MVC exception resolver?
7. **Verify propagation:** test exception type, message, and identity if needed.
8. **Verify side effects and data state:** did rollback/commit/fallback behave accurately?
9. **Verify counts:** one observer event may not correspond to one logical error.
10. **Verify log security:** record only necessary information; never leak request payloads or credentials.

## 19. Practice exercises

**Question 1.** An `@AfterThrowing` logs `IllegalArgumentException("bad")` and returns `void`. If the caller does not catch it, what happens to the exception?

**Answer:** The exception continues propagating along the normal Spring AOP call path unless another layer actively handles it. Returning `void` from advice does not erase the exception.

**Question 2.** The target method has a `try/catch` that catches an error and returns `"RECOVERED"`. Why does the after-throwing observer not run?

**Answer:** At the Spring AOP method boundary, that is a **normal return**, not an exceptional exit. The error existed inside the method but was caught before exiting.

**Question 3.** The advice binds `IllegalArgumentException error`. The target throws `IllegalStateException`. Does the observer not logging prove the system has no error?

**Answer:** No. The typed binding is incompatible with that exception; the caller can still receive the error.

**Question 4.** A request returned HTTP 400, and service after-throwing also logged the error. Which component handled the HTTP response?

**Answer:** The web exception resolution component, such as `@ExceptionHandler`/`@RestControllerAdvice`. A service-layer observer does not produce HTTP 400 on its own.

**Question 5.** `@AfterThrowing` logged an exception inside a `@Transactional` method. Can we assert the DB definitely rolled back successfully?

**Answer:** No. Rollback is controlled by the transaction interceptor, rollback rules, manager, and advisor ordering; you must test DB state and tx outcomes.

**Question 6.** Why might `this.submit(true)` produce no log for `submit` while still producing a log for the outer method `forwardInternally`?

**Answer:** Self-invocation bypasses the proxy for `submit`; when the exception escapes `forwardInternally` invoked by the caller through the proxy, after-throwing observes **the `forwardInternally` join point**.

**Question 7.** An outer `@Around` catches an error and returns a fallback. Could an inner `@AfterThrowing` still have run?

**Answer:** Yes. The inner observer may have seen the error before the outer catch. In that case the outer caller sees a normal return, even though the inner observer recorded an exception.

**Question 8.** An `@AfterThrowing` advice throws a new exception because the logging backend failed. What is the danger?

**Answer:** The new exception can mask the original business error and alter behavior or transaction semantics. Instrumentation needs an explicit failure policy.

**Question 9.** A method returns a `CompletableFuture` immediately, and the future later completes exceptionally. Can `@AfterThrowing` on the method serve as the sole source of truth for failures?

**Answer:** No. Completion errors can occur after method return and belong to the async lifecycle; observe completion with the appropriate API.

**Question 10.** What is the right way to prove an exception was handled?

**Answer:** Identify the layer owning handling, and then assert the **actual outcome**: caller receives fallback, right HTTP status, valid transaction/DB state, or recovered business state—rather than merely looking for an AOP log line.

## 20. Official Spring documentation

- [Spring Framework — Declaring Advice: After Throwing Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): semantics when a method exits by throwing, `throwing` typed binding, and the note that it is **not a general exception handling callback**.
- [Spring Framework — After Returning / After (Finally) Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): distinguishing normal return, exceptional exit, and finally semantics.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB AOP proxies, self-invocation, and call boundaries.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): registering aspect beans and enabling Spring AOP.
- [Spring Framework — Declaring Pointcuts](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): scoping method executions in Spring-managed beans.
- [Spring Framework — Declarative Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules distinct from aspect exception observation.
- [Spring Framework — MVC Exception Handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): using `@ExceptionHandler` to handle exceptions at the web layer.
