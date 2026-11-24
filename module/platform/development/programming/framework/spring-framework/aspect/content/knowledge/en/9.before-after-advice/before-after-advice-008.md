# Spring AOP: Limitations of `@AfterThrowing` When Attempting Error Recovery

## 1. Practical Question: Does Recording an Error Mean Handling the Error?

In Spring Framework, `@AfterThrowing` is an advice type in the `@AspectJ` style. It is invoked when a **method execution selected by a pointcut terminates abnormally by throwing an exception** within an interceptable Spring AOP proxy flow.

The single most important point: **`@AfterThrowing` can observe an exception, but it is not a mechanism for catching an exception and returning a successful result in place of the target.**

```java
@Aspect
@Component
public class FailureAspect {
    @AfterThrowing(
        pointcut = "execution(* demo.recovery.CatalogService.find(..))",
        throwing = "ex"
    )
    public void onFailure(IllegalStateException ex) {
        System.out.println("[afterThrowing] " + ex.getMessage());
        // Normal completion of the advice does not make the target's exception disappear.
    }
}
```

This is a fragment; imports, the service, and the full program are in section 7. When a caller invokes `find("DOWN")` **through the proxy**, the target method throws `IllegalStateException`:

1. Spring AOP lets the call reach the target.
2. The target terminates with an exception matching `@AfterThrowing`.
3. The advice receives the exception and can log, record metrics, alert, or perform auxiliary work.
4. If the advice itself finishes normally, **the original exception still continues propagating to the caller**.
5. `onFailure(...)` is a `void` Java method; it provides no `return "DEFAULT"` mechanism to replace the result of `find(...)`.

Do not infer from method names like `doRecoveryActions` in some documentation examples that this advice heals the exception flow by itself. A "recovery action" can be a **side effect** (logging, emitting an event, alerting), not **turning a failed call into a successful call**.

This lesson focuses entirely on **Spring Aspect, Spring AOP proxies, and advice semantics**. General AOP concepts or AspectJ bytecode weaving are out of scope.

## 2. Position of `@AfterThrowing` in the Execution Flow

```text
Caller invokes Spring bean proxy
           |
           v
    Spring AOP proxy
           |
   Advisor/pointcut match
           |
           v
    Target.find("DOWN")
           |
           +-- throws IllegalStateException
                      |
                      v
               @AfterThrowing
               - reads exception
               - log / alert / metrics
               - finishes normally
                      |
                      v
              exception propagates
                      |
                      v
              Caller receives error
```

If the target method **returns normally**, `@AfterThrowing` does not run because there is no exceptional method exit. This holds even when the method has internal "error handling" logic, as long as it ultimately returns normally.

```java
public String find(String key) {
    try {
        return externalStore.load(key);
    } catch (IllegalStateException ex) {
        return "LOCAL-DEFAULT";
    }
}
```

The snippet above is a fragment assuming `externalStore` exists; because the exception is **caught by the target itself and returned normally**, an `@AfterThrowing` advice applied to `find()` is not invoked for this execution. If you need to observe all outcomes, use `@AfterReturning`, `@After`, or `@Around` as required.

### "Throwing" Differs from "Returning a Value That Indicates Failure"

If the target returns `null`, `Optional.empty()`, `Result.failure(...)`, or an error HTTP response **without throwing an exception out of the AOP-observed execution**, `@AfterThrowing` will not trigger. It observes **exceptional exits** of the join point, not business status inside a return value.

## 3. Why Cannot `@AfterThrowing` Be Used to Swallow Exceptions?

Compare the following three scenarios.

### 3.1. Advice Logs the Exception and Returns Normally

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "ex"
)
public void logFailure(IllegalStateException ex) {
    System.out.println("failed: " + ex.getMessage());
}
```

The advice body has return type `void` and finishes normally. **The target threw an exception**; Spring does not receive a new success value from the advice. Therefore, the caller still receives the exception.

You cannot fix this by changing `void logFailure` to a `String logFailure(...)` method and doing `return "DEFAULT"`. `@AfterThrowing` has no return-value replacement contract. Spring uses `@Around`, or error handling at the caller/service layer, when real recovery is required.

### 3.2. Advice Itself Throws Another Exception

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "ex"
)
public void translate(IllegalStateException ex) {
    throw new CatalogUnavailableException("catalog offline", ex);
}
```

This is a fragment assuming `CatalogUnavailableException` is an actual application exception type. The advice can cause a new exception to propagate through the interceptor chain in place of the old one. **This is still an error termination**, not a successful recovery.

If consistent translation is needed, consider exception mapping at the service boundary or an appropriate infrastructure layer. In Spring, mechanisms like repository exception translation, transactions, and web exception resolution each have their own contracts; they do not mean `@AfterThrowing` can return fallbacks.

**Important note:** a new exception thrown by an advice can hide the original exception if `cause` is omitted. If exception translation is unavoidable, pass the original exception as the cause and pick an exception type compatible with the method signature and caller contract. With JDK dynamic proxies, unchecked exceptions and undeclared checked exceptions behave differently.

### 3.3. Advice Catches Exceptions with Its Own `try/catch`

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "ex"
)
public void observe(IllegalStateException ex) {
    try {
        diagnosticService.record(ex);
    } catch (RuntimeException loggingFailure) {
        // Do not let failures in the observability subsystem mask the original business error.
    }
}
```

This is a fragment using a hypothetical `diagnosticService` collaborator. The `try/catch` inside the advice only catches exceptions raised by **the operations invoked inside the advice itself** (e.g., metric recording failing). It cannot rewind to before the target threw to "re-catch" the target's exception and change the invocation outcome.

Even if the advice swallows an error from `diagnosticService.record(...)`, the target's original exception **still goes back to the caller**.

## 4. `throwing` Both Binds the Exception and Constrains the Exception Type

A declaration:

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "ex"
)
public void onIllegalState(IllegalStateException ex) {
    System.out.println("state error: " + ex.getMessage());
}
```

has two linked effects:

1. `throwing = "ex"` binds the exception value to the advice parameter named `ex`.
2. The `IllegalStateException` parameter type restricts the advice to run only when the thrown exception **has a compatible type** (including matching subclasses).

An `IllegalArgumentException` is also a `RuntimeException` yet **not** an `IllegalStateException`, so the advice above will not receive it. If you want to observe many exception types, you can use `Throwable`:

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "ex"
)
public void observeAll(Throwable ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

However, "all exceptions" here still means **exceptional exits within the join point/advice scope observed by the Spring AOP proxy**. It does not become a global exception handler for the entire JVM or all framework interceptors.

### 4.1. Binding Name Must Match Exactly

```java
@AfterThrowing(pointcut = "execution(* demo.recovery..*Service.*(..))",
               throwing = "failure")
public void logFailure(Throwable failure) {
    System.out.println(failure.getMessage());
}
```

`throwing="failure"` must point to the advice method's `failure` parameter. If the annotation uses `throwing="ex"` while the method only has a parameter named `failure`, Spring may fail when creating the advice or resolving parameter bindings.

Projects built without preserving Java parameter names may need explicit `argNames`, for example:

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "failure",
    argNames = "failure"
)
public void report(Throwable failure) {
    System.out.println(failure.getMessage());
}
```

When adding `JoinPoint`, it is typically the special first parameter:

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "ex",
    argNames = "ex"
)
public void report(JoinPoint joinPoint, Throwable ex) {
    System.out.println(joinPoint.getSignature().getName()
            + " failed: " + ex.getClass().getSimpleName());
}
```

These two snippets are alternative options; do not include both in the same runnable example unless duplicate logs are desired.

### 4.2. Advice Is Not a "Catch-All Error" Callback

The Spring documentation notes that `@AfterThrowing` is **not a general exception-handling callback**. Specifically, this advice is defined to receive exceptional exits from the **user-declared target method (join point)**, rather than automatically firing whenever a companion `@After` or `@AfterReturning` throws an exception.

With multiple aspects and complex interceptor chains, an exception thrown by another advisor may traverse different outer layers depending on precedence. Therefore, do not build designs assuming "every exception from anywhere arrives here." Explicitly identify the **advised method**, the **exception source**, and **advisor ordering**.

## 5. When Real Recovery Is Needed: Appropriate Approaches

### 5.1. Handle Inside the Target or Caller

If fallback is part of the operation's business logic, it can be handled directly inside the service method:

```java
public String findWithFallback(String key) {
    try {
        return externalStore.load(key);
    } catch (IllegalStateException ex) {
        return "DEFAULT";
    }
}
```

This is a fragment assuming `externalStore`. The call finishes normally, so an `@AfterThrowing` on `findWithFallback()` will **not run** for the internally caught error. This approach is clean when the fallback belongs to domain logic and does not require a shared cross-cutting policy.

Similarly, the caller itself can wrap the Spring bean proxy call in `try/catch` and return an alternative result, provided the contract allows it:

```java
try {
    return catalog.find(key);
} catch (IllegalStateException ex) {
    return "DEFAULT";
}
```

This is a fragment inside a method returning `String`; `catalog` is a Spring-managed dependency. Once the target method throws, an `@AfterThrowing` inside the proxy still gets a chance to observe the error before the exception reaches the catching caller, while the caller remains responsible for deciding the fallback.

### 5.2. Use `@Around` to Wrap and Control `proceed()`

In Spring AOP, `@Around` receives `ProceedingJoinPoint`; it has the power to:

- Call `proceed()` to execute the rest of the chain/target.
- Catch exceptions thrown from `proceed()`.
- Return a fallback value **compatible with the method's return type**.
- Where requirements allow, skip the target, retry under a clear policy, or replace the return value.

```java
@Around("execution(* demo.recovery.CatalogService.findWithFallback(..))")
public Object recover(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return "DEFAULT";
    }
}
```

If `findWithFallback(..)` returns `String`, `"DEFAULT"` is a valid value. But if the return type is primitive `int`, `void`, `CompletableFuture<T>`, or a domain-specific result, the fallback must match the contract—otherwise type/unboxing errors or broken semantics can occur.

**Do not confuse catching an exception in `@Around` with automatic transaction recovery:** if a transaction interceptor inside the advice has already marked the transaction rollback-only, catching the exception outside and returning normally does not mean the transaction can commit. Likewise, in reactive/asynchronous methods, errors can occur inside the publisher/future **after the method has returned**; `@AfterThrowing` at the method-execution boundary does not automatically receive those asynchronous errors.

### 5.3. Choosing Retries or Fallbacks with Explicit Policies

A retry is only justified when the operation is **safe to re-execute**, has proper timeouts/backoff/circuit breakers, and does not cause duplicate side effects. You cannot call `proceed()` repeatedly in `@AfterThrowing` because it does not receive `ProceedingJoinPoint`. If retries are required, consider Spring Retry or appropriate Spring Framework resilience facilities instead of hand-rolled code lacking safeguards.

For operations that transfer funds, place orders, or send emails, unbounded retries or returning a fake "success" fallback can be far more dangerous than propagating the error. Choose policy based on the **business contract**; use `@Around` only with clear justification and testing.

## 6. Comparison Table of Advice Types in Error Scenarios

| Advice | When does it run in Spring AOP? | What can it do with an error? | Can it turn an exception into a normal return? |
| --- | --- | --- | --- |
| `@Before` | Before proxy-intercepted method execution | Validate/log beforehand; throw an exception itself to block execution | Cannot via `proceed()`; target has not returned |
| `@AfterReturning` | When execution finishes normally | Observe return value | Cannot be used to return a brand-new reference in place of target |
| `@AfterThrowing` | When execution exits with a matching exception | Log, metric, alert, observe exception; can throw a different exception | **No** — does not swallow errors or return fallbacks |
| `@After` | When execution ends with finally semantics | Cleanup regardless of success/failure | Not a recovery mechanism |
| `@Around` | Surrounds method execution | Catch exceptions from `proceed()`, retry/skip if appropriate, return fallback | **Possible** if contract permits and chain/transactions align |

For example, an `@AfterThrowing` advice that logs and completes does not make the call "successful"; returning success requires an interception point **surrounding** the exceptional execution, or handling at the appropriate caller/target layer.

## 7. Runnable Java 17 + Spring Framework 6.2 Project

Plain Spring Framework example, without Spring Boot. Two calls are intentionally separated onto **two distinct target methods** for clear observation:

- `find()` has `@AfterThrowing` for `IllegalStateException`: the advice logs, yet **the caller still receives the exception**.
- `findWithFallback()` has `@Around`: the advice catches `IllegalStateException` and returns `"DEFAULT"`.
- `findFromInside()` calls `this.find()` from the target: **bypasses the Spring proxy**, so even though `find()` has a matching pointcut, `@AfterThrowing` **does not run** for the internal call.
- `find("OK")` succeeds: `@AfterThrowing` does not run.

### 7.1. Directory Structure

```text
spring-after-throwing-recovery/
├── pom.xml
└── src/main/java/demo/recovery/
    ├── AppConfig.java
    ├── CatalogOperations.java
    ├── CatalogService.java
    ├── RecoveryAspect.java
    └── Main.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-after-throwing-recovery</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. `AppConfig.java`

```java
package demo.recovery;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@ComponentScan` locates components in the `demo.recovery` package. `@EnableAspectJAutoProxy` enables Spring AOP's auto-proxy creator. With `CatalogService implements CatalogOperations` and `proxyTargetClass=false`, the example uses a **JDK dynamic proxy**.

### 7.4. `CatalogOperations.java`

```java
package demo.recovery;

public interface CatalogOperations {
    String find(String key);
    String findWithFallback(String key);
    String findFromInside(String key);
}
```

All three business methods are exposed on the interface so callers can invoke them on the JDK proxy.

### 7.5. `CatalogService.java`

```java
package demo.recovery;

import org.springframework.stereotype.Service;

@Service
public class CatalogService implements CatalogOperations {
    @Override
    public String find(String key) {
        System.out.println("[target] find " + key);
        if ("DOWN".equals(key)) {
            throw new IllegalStateException("storage unavailable");
        }
        return "ITEM-" + key;
    }

    @Override
    public String findWithFallback(String key) {
        System.out.println("[target] findWithFallback " + key);
        if ("DOWN".equals(key)) {
            throw new IllegalStateException("storage unavailable");
        }
        return "ITEM-" + key;
    }

    @Override
    public String findFromInside(String key) {
        System.out.println("[target] findFromInside " + key);
        try {
            return this.find(key); // Does not go through the Spring AOP proxy.
        } catch (IllegalStateException ex) {
            System.out.println("[target] internal fallback");
            return "LOCAL-DEFAULT";
        }
    }
}
```

The service illustrates three execution paths:

- `find` can throw `IllegalStateException` out of the target.
- `findWithFallback` performs no recovery in the target itself; catching is handled by `@Around`.
- `findFromInside` catches errors from `this.find()` internally. That call does not go through the proxy, so `@AfterThrowing` on `find()` does not receive it.

### 7.6. `RecoveryAspect.java`

```java
package demo.recovery;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class RecoveryAspect {
    @AfterThrowing(
        pointcut = "execution(* demo.recovery.CatalogService.find(..))",
        throwing = "ex"
    )
    public void onFindFailure(IllegalStateException ex) {
        System.out.println("[afterThrowing] " + ex.getMessage());
    }

    @Around("execution(* demo.recovery.CatalogService.findWithFallback(..))")
    public Object recoverFind(ProceedingJoinPoint pjp) throws Throwable {
        try {
            return pjp.proceed();
        } catch (IllegalStateException ex) {
            System.out.println("[around] recovered " + ex.getMessage());
            return "DEFAULT";
        }
    }
}
```

The two advices have **separate pointcuts** and do not compete for precedence on the same invocation:

- `@AfterThrowing` applies to `find(..)`, logs the error, and completes normally; the error **still propagates to the caller**.
- `@Around` applies to `findWithFallback(..)`, catches the exception from `proceed()`, and returns `"DEFAULT"` (valid because the method returns `String`).
- Both apply only when the method call goes through the Spring proxy.
- `@Component` registers the aspect as a Spring bean; `@Aspect` alone is not enough.

### 7.7. `Main.java`

```java
package demo.recovery;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            CatalogOperations catalog =
                    context.getBean(CatalogOperations.class);

            System.out.println("jdkProxy="
                    + AopUtils.isJdkDynamicProxy(catalog));

            System.out.println("success=" + catalog.find("OK"));

            try {
                catalog.find("DOWN");
            } catch (IllegalStateException ex) {
                System.out.println("caller caught=" + ex.getMessage());
            }

            System.out.println("fallback="
                    + catalog.findWithFallback("DOWN"));
            System.out.println("internal="
                    + catalog.findFromInside("DOWN"));
            System.out.println("fallbackSuccess="
                    + catalog.findWithFallback("OK"));
        }
    }
}
```

Run from the directory containing `pom.xml` using Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.recovery.Main
```

Program `System.out` lines in order in the example (excluding separate Maven/Spring logs if any):

```text
jdkProxy=true
[target] find OK
success=ITEM-OK
[target] find DOWN
[afterThrowing] storage unavailable
caller caught=storage unavailable
[target] findWithFallback DOWN
[around] recovered storage unavailable
fallback=DEFAULT
[target] findFromInside DOWN
[target] find DOWN
[target] internal fallback
internal=LOCAL-DEFAULT
[target] findWithFallback OK
fallbackSuccess=ITEM-OK
```

### 7.8. Analyzing the Results

| Operation | Target | `@AfterThrowing` | `@Around` | Caller Receives |
| --- | --- | --- | --- | --- |
| `catalog.find("OK")` | Returns `"ITEM-OK"` | Does not run | Does not apply | `"ITEM-OK"` |
| `catalog.find("DOWN")` | Throws `IllegalStateException` | Logs `storage unavailable` | Does not apply | **Exception** |
| `catalog.findWithFallback("DOWN")` | Throws exception | Does not match this pointcut | Catches and returns `"DEFAULT"` | **Success value `"DEFAULT"`** |
| `catalog.findFromInside("DOWN")` | Catches internal error from `this.find()` | Does not see nested `find` due to self-invocation | Does not apply | `"LOCAL-DEFAULT"` |
| `catalog.findWithFallback("OK")` | Returns `"ITEM-OK"` | Does not match | Returns original `proceed()` result | `"ITEM-OK"` |

**Reading two key lines:**

```text
[afterThrowing] storage unavailable
caller caught=storage unavailable
```

They prove the advice **observed the error** without **recovering from it**. By contrast:

```text
[around] recovered storage unavailable
fallback=DEFAULT
```

is an example of **catch + return fallback** inside around advice.

There are no async calls, no transactions, and the two advices select two different methods, so the example does not depend on execution order between different advices on the same join point.

## 8. Why Might `@AfterThrowing` Not Run Even Though an Error Occurred?

### 8.1. Target Catches the Error and Returns Normally

```java
public String find(String key) {
    try {
        return gateway.load(key);
    } catch (IllegalStateException ex) {
        return "CACHED";
    }
}
```

This fragment assumes `gateway`. The `find` method execution finishes normally, so `@AfterThrowing` **does not trigger** for the exception caught by the target. If you want an advice to process errors that occurred **inside the method and were already caught**, you must move the boundary or change the event/reporting contract; a Spring proxy cannot observe individual `throw` statements caught within the target.

### 8.2. Exception Does Not Match the Parameter Type

```java
@AfterThrowing(pointcut = "execution(* demo.recovery..*Service.*(..))",
               throwing = "ex")
public void observe(IllegalStateException ex) {
    // Only catches exceptions compatible with IllegalStateException.
}
```

If the method throws `IllegalArgumentException`, this advice does not receive it. To observe multiple types, consider `Throwable`, while avoiding logging sensitive data or treating every exception as a business error.

### 8.3. Call Does Not Go Through the Spring AOP Proxy

```java
new CatalogService().find("DOWN");
```

This is a manually created object, not a Spring bean proxy; Spring AOP advice **does not run**. Likewise, self-invocation `this.find("DOWN")` from inside the target creates no new interception.

### 8.4. Pointcut Has Wrong Signature, Package, or Bean

An expression `execution(* demo.other.CatalogService.find(..))` does not match a target in `demo.recovery`. Or the aspect class has `@Aspect` but has not been registered as a Spring bean via `@Component`/`@Bean`. In those cases Spring has no valid advisor to run `@AfterThrowing`.

### 8.5. Method Cannot Be Intercepted by the Proxy

With a JDK proxy, the method must belong to the public interface methods exposed by the proxy. With CGLIB, `private`/`final` methods cannot be advised via overriding and `final` classes cannot be subclassed. `static` methods are not invoked through an instance proxy.

### 8.6. Exception Occurs After the Method Returns

A method returning `CompletableFuture<T>` or reactive `Mono<T>` can **return a wrapper normally** while the error only occurs when the future completes or the publisher is subscribed to. `@AfterThrowing` on regular method execution does not automatically know about errors occurring after return time. To handle async/reactive errors, use appropriate APIs such as completion handlers, Reactor error operators, or corresponding framework support.

### 8.7. Another Advice Already Recovered Before the Exception Reached the Observer

When multiple advisors apply, an `@Around` can catch an exception from the inner chain and return normally; an outer advisor will only see the normal result. Depending on precedence, an inner advice might still have observed the exception before the outer advice recovered. Do not state absolute rules like "`@AfterThrowing` always runs before/after `@Around`" without examining the specific advisor ordering.

## 9. Limits When Combining with Transactions, Retries, and Web Errors

### 9.1. `@Transactional` and Rollback

Spring declarative transactions are typically implemented via an interceptor. If a method throws an exception passing through the transaction interceptor, Spring may mark the transaction for rollback per rollback rules, and only then does an outer `@Around` catch the exception and return a fallback. **Catching outside does not erase the rollback flag.**

If caught before the exception crosses the transaction boundary, the transaction interceptor may see only a normal return; however, the transaction may already have been marked rollback-only along other paths. When clear rollback/recovery behavior is needed, configure the transaction boundary and advisor ordering deliberately, and add integration tests checking real commit/rollback state.

In particular, never use an `@AfterThrowing` just to assume "the error was handled so the transaction will commit." It is solely an advice on exceptional execution and never restores a rolled-back transaction.

### 9.2. Retries: Side-Effect Risks

If you want to automatically re-invoke an operation, `@AfterThrowing` has no `ProceedingJoinPoint` and cannot re-run target execution. Use an appropriate retry mechanism (such as Spring Retry when used by the project) or `@Around`, ensuring:

- the operation is idempotent or has deduplication protection;
- retry limits, backoff, and timeouts are enforced;
- logging/metrics avoid uncontrolled duplication;
- transaction boundaries align cleanly with each attempt;
- the final exception follows a clear contract.

Do not automatically retry a money-transfer or order-creation method just because an aspect observed an exception.

### 9.3. HTTP Exception Responses Are Not Spring AOP Recovery

In Spring MVC, a service error can be handled at the web boundary using `@ExceptionHandler`/`@ControllerAdvice` or other exception-handling mechanisms. That translates **the exception into an HTTP response** for the client, but it does not mean the service's `@AfterThrowing` returned a fallback to the service caller.

These responsibilities are distinct:

- Spring AOP `@AfterThrowing`: observes **exceptional method execution**.
- Spring MVC exception resolver: translates application errors into an appropriate **web response**.
- Service/caller/`@Around`: can decide a **domain fallback** if the contract allows it.

## 10. Diagnostic Checklist

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Advice logs the error, yet caller still receives the exception | Expected behavior of `@AfterThrowing` | If fallback is needed, handle in caller/target or `@Around` |
| Tried `return "DEFAULT"` in after-throwing method | Not the return-replacement contract of this advice | Use `@Around` with the proper return type |
| Advice throws a different exception and original error disappears | Advice exception may mask the original error | Pass original as cause and preserve exception contract |
| `@AfterThrowing` does not run for `IllegalArgumentException` | `IllegalStateException`-typed binding parameter filters it out | Fix parameter constraint or handle corresponding exception |
| `@AfterThrowing` does not run when target already caught error | Execution returned normally | Move the error-handling boundary |
| `@AfterThrowing` does not run on `this.method()` | Self-invocation bypasses proxy | Extract method to another bean and inject it |
| `@AfterThrowing` does not run on `new` object | Object outside Spring container | Use a Spring-managed bean |
| Advice misses exceptions from a companion `@AfterReturning` | `@AfterThrowing` is not a global exception callback | Check exact join point, error source, and ordering |
| Advice misses `CompletableFuture` failures | Method returned normally before future failed | Use completion/error handlers |
| `@Around` returns fallback yet transaction still rolls back | Transaction boundary already saw exception or rollback-only | Design advisor/transaction ordering and test rollback |
| Using `Throwable`, error logs appear multiple times | Multiple aspects, retries, or multiple proxy boundaries | Designate one logging/observability boundary, avoid double counting |
| `@AfterThrowing` runs on the wrong method | Pointcut too broad or different target bean | Narrow expression and verify bean/target |
| No Spring proxy exists | Aspect/target not Spring beans, auto-proxy not enabled | Check `@Aspect @Component` and `@EnableAspectJAutoProxy`/Boot AOP |

### Systematic Verification Workflow

1. Verify both target and aspect are Spring-managed and Spring AOP infrastructure is enabled.
2. On the actual reference from DI/context, verify `AopUtils.isAopProxy(...)`.
3. Verify the method is invoked by the caller through the proxy, not via `this` or an object created with `new`.
4. Inspect the pointcut and the exception type of the `throwing` binding.
5. Distinguish exceptions **exiting the target method** from exceptions caught inside the target or async errors occurring after return.
6. Check whether `@AfterThrowing` only logs or throws a new exception.
7. If the caller must receive a successful fallback, place exception handling at the right point: target, caller, or `@Around`.
8. For transactions, retries, async, and web exceptions, test behavior at the respective boundary rather than guessing from a single advice log line.

## 11. Self-Assessment Questions

**1. `@AfterThrowing` logs an exception and returns normally; what does the caller receive?** The caller still receives the exception from the target (unless an interceptor at another layer handles it). The advice does not automatically turn an exception into a normal return.

**2. Can an `@AfterThrowing` method be declared to return `String` to replace the return value?** No. This advice has no contract to control `proceed()` or the join point's return value; use `@Around` when recovery is needed.

**3. Why doesn't `@AfterThrowing(..., throwing="ex")` with `IllegalStateException ex` run when the target throws `IllegalArgumentException`?** Because the advice parameter's exception type restricts matching.

**4. If the target method catches internally and returns `"CACHED"`, does `@AfterThrowing` on that method run?** No. The execution completed normally; the exception never exited the join point.

**5. What is the difference between `@Around` and `@AfterThrowing` regarding recovery?** `@Around` can catch exceptions from `proceed()` and return a valid fallback; `@AfterThrowing` primarily observes exceptional execution and cannot turn it into success.

**6. If `@AfterThrowing` throws a new exception, is that recovery?** No. The caller still receives an error, even if the error type differs; preserve the original cause when translating exceptions.

**7. Why isn't self-invocation `this.find()` intercepted by `@AfterThrowing`?** The call does not go through the Spring AOP proxy, even if the pointcut matches the method signature.

**8. Does `@AfterThrowing` automatically catch every exception thrown by an accompanying `@AfterReturning`?** Do not assume so. Spring explicitly states it is not a general exception-handling callback; inspect the exception source and advisor chain.

**9. Will a `CompletableFuture` failing after the method returns automatically trigger `@AfterThrowing` on that method?** Not for a method execution that already returned the future normally; an async/future error-handling mechanism is required.

## Official Spring Documentation

- [Spring Framework — Declaring Advice, After Throwing Advice, and Around Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework — AOP Concepts: After Throwing Advice](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html)
- [Spring Framework — Spring AOP Advice API (Throws Advice)](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html)
- [Spring Framework — Proxying Mechanisms and Self-Invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework — Declarative Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
