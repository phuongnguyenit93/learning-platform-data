# `@AfterThrowing` and Exception Type Binding in Spring AOP

## 1. What Is `@AfterThrowing` Used For?

In Spring AOP, `@AfterThrowing` declares **advice that runs when a method execution selected by a pointcut exits by throwing an exception**. It is commonly used for error logging, recording metrics, incident auditing, or emitting observability signals *after* the target method fails.

Example:

```java
@Aspect
@Component
public class FailureAspect {

    @AfterThrowing(
        pointcut = "execution(* com.example.app.service..*.*(..))",
        throwing = "error"
    )
    public void recordFailure(Exception error) {
        System.out.println("SERVICE FAILED: " + error.getMessage());
    }
}
```

This is an **illustrative Spring AOP snippet**, not a standalone runnable program: it requires imports, a Spring context, and real service beans.

In this snippet:

- `@Aspect` marks the class declaring the advice; `@Component` enables component scanning to register the aspect as a Spring bean when the package is scanned.
- `pointcut` specifies which service method executions can be matched.
- `throwing = "error"` **binds the thrown exception** to the advice parameter named `error`.
- The `Exception` parameter type also serves as an **exception-type filter**. This advice will not receive throwables that are not subtypes of `Exception`, such as some `Error` instances.

**Core conclusion:** `@AfterThrowing` combines a **method execution condition** and an **exiting exception type condition**. Only when both match does the advice run.

This lesson focuses exclusively on Spring Framework and proxy-based Spring AOP advice; it does not expand into general Exception theory or general Aspect concepts.

## 2. Execution Flow When a Method Throws an Exception

Imagine a client calling a Spring bean through a proxy:

```text
Client
  |
  | service.placeOrder(...)
  v
Spring AOP proxy
  |
  +--> matching advices/interceptors
  |
  v
Target.placeOrder(...)
  |
  +--> succeeds --> return
  |                    |
  |                    +--> @AfterThrowing does NOT run
  |
  +--> throw IllegalArgumentException
                       |
                       v
          Does @AfterThrowing have matching
          pointcut and compatible exception type?
                 /              \
               YES               NO
                |                 |
                v                 |
          advice runs             |
                |                 |
                +--------+--------+
                         |
                         v
             Exception propagates to caller
              if the advice does not alter it
```

With typical usage, Spring invokes `@AfterThrowing` **when the target execution exits with a matching exception**, and then the exception continues propagating to the client. The advice method does not call `proceed()`.

### Cases Where It Does Not Trigger

`@AfterThrowing` does not run when:

1. The method returns normally, even if the return value is `null`, `false`, or an object representing a failure.
2. The method catches the exception internally, handles it, and then **returns normally**.
3. An exception is thrown, but the **pointcut does not match the method execution**.
4. The exiting exception is incompatible with the **advice parameter type**.
5. The call does not go through a Spring AOP proxy, such as an object created with `new` or an internal `this.method()` call on the target.
6. An outer interceptor short-circuits before reaching the join point, preventing the target method from executing.

**Important note from the Spring docs:** `@AfterThrowing` is not a callback that catches every error in the interceptor chain. Semantically, it handles errors originating from the **join point (the target method)**, and should not be understood as a mechanism that automatically catches exceptions thrown by an accompanying `@After` or `@AfterReturning` advice.

## 3. Annotation Syntax and the `throwing` Parameter

### 3.1. Only Needing to Know the Method Failed

If you only need to perform a side effect when the method throws an exception without capturing the exception object:

```java
@AfterThrowing("execution(* com.example.app.service..*.*(..))")
public void countFailure() {
    System.out.println("FAILED");
}
```

This is a **sample method** that must be placed inside an `@Aspect` bean. It applies to any throwable type that can cause the selected method execution to terminate abnormally, within the advice's semantics.

### 3.2. Needing Access to the Exception Object

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "cause"
)
public void afterFailure(Throwable cause) {
    System.out.println(cause.getClass().getSimpleName());
}
```

In Spring, the string `"cause"` in the `throwing` attribute must match the **parameter name** receiving the exception in the Java advice method. This is a **binding variable name**, not an Exception class name and not an arbitrary name ignored by Spring.

You can specify `argNames` for clarity when the compiler does not preserve parameter names:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "cause",
    argNames = "cause"
)
public void afterFailure(Throwable cause) {
    System.out.println(cause.getMessage());
}
```

**Meaning of the `Throwable` type:** this is the supertype of both `Exception` and `Error`, so it **does not narrow the exception type** the way more specific parameters do. However, the method must still match the pointcut, go through the proxy, and exit with a throwable.

### 3.3. `throwing` Differs from Java's Method `throws`

Compare:

```java
public void importFile() throws IOException {
    // ...
}
```

with:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.importFile(..))",
    throwing = "error"
)
public void onImportError(IOException error) {
    // ...
}
```

`throws IOException` in the Java method signature is a **declaration of potential checked exceptions**. `throwing = "error"` in the advice is a **binding name** for the actual throwable exiting the call. The `IOException` type in the advice is a runtime type-matching condition, not merely whether the Java method declares `throws IOException`.

A method declaring `throws IOException` that returns normally **does not trigger** the advice. Conversely, an unchecked exception does not need to be in `throws` and can still be matched by type in the advice.

## 4. How Exception Type Constraints Work

When using `throwing`, the **declared type of the advice parameter** narrows which exceptions can match:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "error"
)
public void onInvalidInput(IllegalArgumentException error) {
    System.out.println("INVALID: " + error.getMessage());
}
```

If the target method throws `new IllegalArgumentException(...)`, the advice above can run; if it throws `new IllegalStateException(...)`, that advice **does not run**, even though both are `RuntimeException` subclasses.

| Advice parameter type | Type-compatible throwables | Non-matching examples |
| --- | --- | --- |
| `Throwable` | Any subtype of `Throwable` | No `Throwable` subclass is excluded by type alone |
| `Exception` | Checked exceptions, `RuntimeException`, and subtypes | `Error` (not an `Exception`) |
| `RuntimeException` | Runtime exceptions and subtypes | `IOException`, `Error` |
| `IllegalArgumentException` | `IllegalArgumentException` and subclasses | `IllegalStateException` |
| `IOException` | `IOException` and subclasses | `IllegalArgumentException` |
| `FileNotFoundException` | `FileNotFoundException` and subclasses | `IOException` (not a subtype of `FileNotFoundException`) |

**Comparison uses inheritance relationships, not necessarily exact class equality.** For example, if `MissingFieldException extends IllegalArgumentException`, an advice accepting `IllegalArgumentException` can still be invoked when the runtime throwable is `MissingFieldException`.

Note: the runtime exception type condition is **different** from the target service class/subtype condition in `target(Type)` or `this(Type)`. `throwing` refers to the throwable object leaving the join point, not the target bean's class.

## 5. Java 17+ Demo: Matching `IllegalArgumentException` and `IOException`

This example creates a Spring AOP proxy for a service and uses **two advice methods with different pointcuts** to avoid ambiguity in ordering between advices:

- `onIllegalArgument(...)` selects executions of `process(..)`, accepting only `IllegalArgumentException`.
- `onIOException(...)` selects executions of `load(..)`, accepting only `IOException`.
- Calling `process("ok")` succeeds.
- Calling `process("handled")` raises an internal exception but **catches it before returning**; the advice does not run.
- Calling `process("bad")` throws `IllegalArgumentException`; the first advice runs.
- Calling `process("state")` throws `IllegalStateException`; the first advice **does not** run because it is not a matching subtype.
- Calling `load()` throws checked `IOException`; the second advice runs.

The application uses **Java 17+, Maven, Spring Framework 6.2.6**; Spring Boot is not needed. `@Bean` is used so Spring registers beans explicitly.

### 5.1. File Structure

```text
spring-aop-after-throwing/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AfterThrowingDemo.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-after-throwing</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.6</version>
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
                    <mainClass>demo.AfterThrowingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. `src/main/java/demo/AfterThrowingDemo.java`

```java
package demo;

import java.io.IOException;

import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class AfterThrowingDemo {

    public interface TaskService {
        String process(String scenario);
        void load() throws IOException;
    }

    public static class TaskServiceImpl implements TaskService {
        @Override
        public String process(String scenario) {
            System.out.println("TARGET process " + scenario);

            if ("bad".equals(scenario)) {
                throw new IllegalArgumentException("missing id");
            }

            if ("state".equals(scenario)) {
                throw new IllegalStateException("unavailable");
            }

            if ("handled".equals(scenario)) {
                try {
                    throw new IllegalArgumentException("internal");
                } catch (IllegalArgumentException ex) {
                    return "RECOVERED";
                }
            }

            return "OK";
        }

        @Override
        public void load() throws IOException {
            System.out.println("TARGET load");
            throw new IOException("cannot read file");
        }
    }

    @Aspect
    public static class FailureAspect {
        @AfterThrowing(
            pointcut = "execution(* demo..*.process(..))",
            throwing = "failure",
            argNames = "failure"
        )
        public void onIllegalArgument(IllegalArgumentException failure) {
            System.out.println("ADVICE illegal " + failure.getMessage());
        }

        @AfterThrowing(
            pointcut = "execution(* demo..*.load(..))",
            throwing = "failure",
            argNames = "failure"
        )
        public void onIOException(IOException failure) {
            System.out.println("ADVICE io " + failure.getMessage());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class Config {
        @Bean
        public TaskService taskService() {
            return new TaskServiceImpl();
        }

        @Bean
        public FailureAspect failureAspect() {
            return new FailureAspect();
        }
    }

    private static void callProcess(TaskService service, String scenario) {
        try {
            System.out.println(
                "CLIENT result=" + service.process(scenario)
            );
        } catch (RuntimeException ex) {
            System.out.println(
                "CLIENT caught " + ex.getClass().getSimpleName()
                        + ":" + ex.getMessage()
            );
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            TaskService service = context.getBean(TaskService.class);
            System.out.println(
                "AOP_PROXY=" + AopUtils.isAopProxy(service)
            );

            callProcess(service, "ok");
            callProcess(service, "handled");
            callProcess(service, "bad");
            callProcess(service, "state");

            try {
                service.load();
            } catch (IOException ex) {
                System.out.println(
                    "CLIENT caught IOException:" + ex.getMessage()
                );
            }
        }
    }
}
```

### 5.4. Running the Project

From the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Lines **printed by the program itself, in order** (excluding any Maven/Spring logging):

```text
AOP_PROXY=true
TARGET process ok
CLIENT result=OK
TARGET process handled
CLIENT result=RECOVERED
TARGET process bad
ADVICE illegal missing id
CLIENT caught IllegalArgumentException:missing id
TARGET process state
CLIENT caught IllegalStateException:unavailable
TARGET load
ADVICE io cannot read file
CLIENT caught IOException:cannot read file
```

### 5.5. Explaining Each Branch

**Branch `ok`:** the target returns normally, so `@AfterThrowing` does not run. This remains true even if the method returns `null` or an object representing a business-level error without throwing an exception.

**Branch `handled`:** the target threw `IllegalArgumentException` **internally**, but caught it and returned `"RECOVERED"`. From the method execution boundary that Spring AOP sees, the method completed normally, so the advice does not receive that internal exception.

**Branch `bad`:** the target throws `IllegalArgumentException`. The `process(..)` pointcut matches and the `IllegalArgumentException` parameter type is compatible, so `onIllegalArgument(...)` runs before the caller receives the exception. The advice only logs and returns `void`; it **does not swallow the error**. Thus the caller still catches the exact exception.

**Branch `state`:** the target throws `IllegalStateException`. It is a subtype of `RuntimeException` but **not** a subtype of `IllegalArgumentException`. `onIllegalArgument(...)` does not run; the exception still exits to the client.

**Branch `load`:** the target throws `IOException`, and the method declares `throws IOException` for the Java compiler. Advice `onIOException(IOException failure)` runs because both the method match and the thrown exception type fit.

The example has two `@AfterThrowing` advices in one aspect, but they match **two different methods**, so they do not depend on the undefined ordering of multiple advices of the same kind on a single join point.

## 6. Deep Dive: Exception Hierarchy and Choosing the Parameter Type

An example diagram of type relationships:

```text
Throwable
├── Error
└── Exception
    ├── IOException
    │   └── FileNotFoundException
    └── RuntimeException
        ├── IllegalArgumentException
        └── IllegalStateException
```

When you declare:

```java
@AfterThrowing(
    pointcut = "execution(* com.example..service..*.*(..))",
    throwing = "failure"
)
public void onFailure(RuntimeException failure) {
    System.out.println(failure.getClass().getName());
}
```

the advice is selected for methods matching the pointcut that throw **`RuntimeException` or a subclass**, such as `IllegalArgumentException` / `IllegalStateException`. However, it does not run for checked `IOException`.

If you need to distinguish multiple groups without contending over advice ordering, you can:

1. Use one advice with a broad `Throwable` parameter and branch on subtypes when needed.
2. Use multiple aspects with distinct pointcut/throwing types, establishing order with `@Order` if multiple advices match the same join point.
3. Choose a sufficiently narrow type if the behavior only serves one exception group.

Example of a general advice:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "failure"
)
public void report(Throwable failure) {
    if (failure instanceof IllegalArgumentException) {
        System.out.println("BAD-INPUT");
    } else if (failure instanceof IOException) {
        System.out.println("IO");
    } else {
        System.out.println("OTHER-FAILURE");
    }
}
```

This is a **snippet** for an `@Aspect` bean, not a standalone program. Do not use `Throwable` reflexively if the system only cares about `Exception` types; you might accidentally log critical `Error`s without a proper response strategy.

### Exception Subclasses Still Match

```java
public class InvalidOrderException extends IllegalArgumentException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

When the target method throws `InvalidOrderException`, an advice with parameter `IllegalArgumentException` **still matches** because it is a valid subtype. Binding does not require the thrown exception's exact class to equal the parameter type.

## 7. `@AfterThrowing` Is Not an Error-Handling `catch` Block

A common misconception: placing `@AfterThrowing` to **catch an error and return a fallback to the caller**.

```java
@AfterThrowing(
    pointcut = "execution(* com.example..*.find(..))",
    throwing = "error"
)
public void recover(IllegalStateException error) {
    System.out.println("FALLBACK?");
}
```

This is a **snippet with no fallback logic**. The advice method returns `void` and has no authority to replace the target's outcome with a return value from the advice. It is designed to run after the join point exits with an error.

If you need to **intercept an exception, translate an exception, or return a fallback**, use `@Around`:

```java
@Around("execution(* com.example.app.service..*.find(..))")
public Object fallback(ProceedingJoinPoint joinPoint) throws Throwable {
    try {
        return joinPoint.proceed();
    } catch (IllegalStateException ex) {
        return "FALLBACK";
    }
}
```

The `@Around` snippet above is an **illustrative pattern**: it must reside in an `@Aspect` bean and the `String` return type must be compatible with the target method. It allows the call to continue via `proceed()`, catches exceptions thrown inside, and returns a different value.

If an around advice swallows an exception at one position in the chain, an `@AfterThrowing` advice sitting **outside** it may not observe the original error, because the inner portion returned normally. Therefore, when multiple advisors exist, examine the **nesting order** and check what result/exception each advice sees.

### Throwing Another Exception Inside the Advice

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.save(..))",
    throwing = "error"
)
public void logFailure(RuntimeException error) {
    // Can log or emit metrics; avoid arbitrarily throwing a new exception here.
}
```

If the advice itself throws an exception, the new exception can affect the error path the client receives. This is not the standard way to wrap or recover from business errors. When explicit exception mapping is needed, `@Around` controlling the flow is usually easier to read and test.

## 8. Comparing `@AfterThrowing` with Other Advice Types

| Advice | When does it run in Spring AOP? | Binds exception? | Controls flow via `proceed()`? |
| --- | --- | --- | --- |
| `@Before` | Before matched method execution | Does not bind throwables from method outcome | No |
| `@AfterReturning` | Method execution returns normally | No; binds return value via `returning` if needed | No |
| `@AfterThrowing` | Method execution throws a matching exception | **Yes, via `throwing`** | No |
| `@After` | After method execution, whether normal or exceptional exit | Does not bind exceptions like `@AfterThrowing` | No |
| `@Around` | Surrounds inner execution/interceptors | Can `catch` exceptions from `proceed()` directly | **Yes** |

In Spring, `@After` is used with **finally** semantics: suitable for cleanup that must always run. `@AfterThrowing` runs only on the error branch, making it suitable for error-only logging/metrics. If you need to turn an error into a result or perform retries, consider around advice.

### Advice Ordering Matters

For example, if a method is advised by multiple aspects:

```text
Outer @Around: enter
    Target: throws IllegalArgumentException
    Inner @AfterThrowing: log error (if conditions match)
Outer @Around: catch -> return fallback
Client: receives fallback
```

This is **one possible ordering scenario**, not a fixed default order. If `@Around` handles the exception before an outer `@AfterThrowing` receives it, the outer advice may not run. Spring provides `@Order` / `Ordered` to determine precedence between aspects, but you must test with the effective configured order.

Do not rely on the declaration order of two `@AfterThrowing` methods of the same kind in the same aspect to predict execution order if they match the same join point. The Spring docs state there is no guaranteed order based on Java source order for advices of the same kind; when order matters, refactor or split aspects and declare explicit precedence.

## 9. Common Binding Mistakes

### 9.1. Name in `throwing` Does Not Match the Advice Parameter Name

Wrong:

```java
@AfterThrowing(
    pointcut = "execution(* com.example..*.save(..))",
    throwing = "cause"
)
public void onFailure(IOException error) {
    // Name in throwing and parameter do not match.
}
```

This is **incorrect code for illustration**. Spring needs to bind `cause`, but the Java method declares parameter `error`. If the name cannot be resolved/matched properly, the context may fail with a binding/pointcut error when creating the advisor or invoking it.

Right:

```java
@AfterThrowing(
    pointcut = "execution(* com.example..*.save(..))",
    throwing = "error",
    argNames = "error"
)
public void onFailure(IOException error) {
    // Can read the bound exception.
}
```

With additional parameters such as `JoinPoint` or multiple bindings, provide full `argNames` and matching parameter count/types so Spring does not infer names incorrectly when Java bytecode omits parameter names.

### 9.2. Using a Non-`Throwable` Method Parameter Type

Do not write a `throwing` advice accepting `String` expecting `error.getMessage()` or automatic string conversion of the thrown exception. With `@AfterThrowing`, the `throwing` parameter must use a throwable type compatible with what you intend to match.

### 9.3. Using a Narrower Type Than the Actual Exception

For example, `onFailure(FileNotFoundException e)` will not run for every `IOException`. It only runs when the runtime exception is `FileNotFoundException` or a subtype. This is type-based filtering by design, not a Spring bug.

### 9.4. Forgetting to Register the Aspect as a Spring Bean

Having only `@Aspect` on a class does not ensure Spring automatically scans and registers it. Combine `@Component` with component scanning or register via `@Bean`; also enable `@AspectJ` processing with `@EnableAspectJAutoProxy` in plain Spring Framework or the appropriate Spring Boot auto-configuration.

### 9.5. Pointcut Does Not Match Method Name/Package

If the right exception type is thrown but `execution(...)` selects a different package, the advice still will not run. When debugging, temporarily use an explicit method pointcut and then narrow by package/annotation to identify which condition fails to match.

### 9.6. Method Catches the Exception Internally

This is standard method execution semantics, not a binding bug. Spring AOP only sees that the **method exited normally**, so it does not run `@AfterThrowing` for an exception caught inside the target before returning successfully.

## 10. Practical Spring Applications: Auditing, Metrics, Transactions, Async

### 10.1. Auditing and Metrics on the Error Branch

An advice can record events by exception type:

```java
@AfterThrowing(
    pointcut = "execution(public * com.example.app.service..*.*(..))",
    throwing = "error"
)
public void recordFailure(Exception error) {
    metrics.increment("service.failure", error.getClass().getSimpleName());
}
```

This is an **architectural pattern** requiring a Spring-injected `metrics` dependency and an appropriate recorder API. Do not assume every metrics library has an `increment(...)` signature like the illustration.

If the aspect calls a collaborator that is itself advised, verify that the pointcut does not accidentally cover that collaborator and create a recursive call loop. Restrict pointcuts cleanly to the service boundary.

### 10.2. Spring Transactions and Exceptions

A `@Transactional` method is normally intercepted by its own transaction advisor. Your `@AfterThrowing` is simply another advisor if the pointcut matches; **when logging occurs relative to transaction rollback** depends on advisor ordering. Do not assume that whenever `@AfterThrowing` runs, the transaction has already rolled back.

Spring's transaction rollback rules also depend on the exception type and `rollbackFor` / `noRollbackFor` settings. `@AfterThrowing` does not configure rollback behavior.

### 10.3. Checked Exceptions and JDK Dynamic Proxies

When using a JDK dynamic proxy, declaring checked `IOException` on the interface method is the direct way for callers to catch `IOException` per contract. For checked exceptions **not declared** on the interface method that are thrown through a JDK dynamic proxy, Java proxy semantics can wrap them in `UndeclaredThrowableException`. That differs from what `@AfterThrowing` **observes at target execution**, where it binds by the runtime throwable type.

Avoid thinking "checked/unchecked is determined by `@AfterThrowing`." This annotation does not exempt Java from checked-exception declaration rules.

### 10.4. Async Execution

With `@Async`, the real method may run on an executor thread and represent outcomes via `Future` / `CompletableFuture` or a dedicated `void` error handler. An exception occurring on an async thread **is not automatically equivalent** to a synchronous exception exiting the proxy call seen by an outer advice. When auditing async errors, consider advisor placement, the async method's contract, and the future's completion/error-handling mechanism.

### 10.5. Retries and Fallbacks

If retry advice is used (for example via an `@Around` or Spring Retry as appropriate), **a single client call can trigger multiple target executions**. An `@AfterThrowing` inside the retry loop can be invoked on each failed attempt, whereas an advice outside the loop only sees the final failure after retries are exhausted. When metrics need "attempt count" vs. "failed client requests," configure advisor ordering carefully or count at the right boundary.

## 11. Optimizing Advice Design for Error Events

A well-designed `@AfterThrowing` usually:

1. **Keeps side effects concise and bounded**, such as logging/metrics/auditing; avoid long synchronous network calls when error-path latency matters.
2. **Avoids leaking unnecessary sensitive data** in logs. `Exception.getMessage()` may contain client-supplied input or internal database/path details.
3. **Does not arbitrarily throw new exceptions** just because logging/metrics failed. If telemetry failure also breaks the error path, the real root cause can be obscured.
4. **Keeps pointcuts sufficiently narrow**, e.g., public service methods only, avoiding duplicate recording across unintended proxies or infrastructure beans.
5. **Avoids duplicate logs** across every service layer when an overly broad pointcut catches the same exception propagating through multiple proxy calls. Pick one appropriate recording boundary (a service boundary or outer request boundary) and include a correlation ID if needed.
6. **Chooses the exception type intentionally**: `IllegalArgumentException` for specific validation groups, `RuntimeException` for runtime failures, and `Throwable` only if `Error`s are genuinely needed.
7. **Verifies the proxy path** with integration tests, especially regarding self-invocation and JDK/CGLIB choices.
8. **Includes positive/negative tests**: test matching subtype errors, non-matching subtypes, successful returns, and exceptions handled inside the target.

If you want to transform an exception into an API response, place that handling at the appropriate layer (such as a web-layer exception handler) rather than expecting `@AfterThrowing` to return a new value for the failed method.

## 12. Self-Check Questions

**Q1.** An advised method returns `"ERROR"` without throwing an exception. Does `@AfterThrowing` run?  
**Answer:** No. At the Spring AOP method-execution level, that is a normal return.

**Q2.** An advice uses `throwing="ex"`, while the Java method declares parameter `IOException error`. What is wrong?  
**Answer:** The binding names do not match. You need `throwing="error"` or to rename the advice parameter accordingly, adding `argNames` if needed.

**Q3.** Does `@AfterThrowing` with an `IllegalArgumentException` parameter receive `IllegalStateException`?  
**Answer:** No. Both classes are separate branches under `RuntimeException`.

**Q4.** An `InvalidOrderException extends IllegalArgumentException` is thrown by the target. Does an advice accepting `IllegalArgumentException` match?  
**Answer:** Yes, provided the method execution and pointcut conditions match.

**Q5.** The target catches `IOException` and returns `false`. Does an advice accepting `IOException` run?  
**Answer:** No. The exception never exited the method execution.

**Q6.** Can `@AfterThrowing` be used to return the string `"FALLBACK"` to the caller?  
**Answer:** No, not under this advice's contract. To control return/exception flow, use `@Around` or handling at the appropriate business layer.

**Q7.** When `process()` calls `this.load()` inside the same target, is the `load()` call independently advised by Spring AOP?  
**Answer:** There is no new proxy boundary during self-invocation; advice matching only `load()` will not automatically run for that internal call.

**Q8.** When `@AfterThrowing` runs, is it guaranteed that the transaction has already rolled back?  
**Answer:** Not conclusively. You must examine transaction advisor ordering and rollback rules.

**Q9.** One advice uses `Throwable` and another uses `RuntimeException`, and both match `IllegalArgumentException`. Can you rely on source declaration order to determine their execution order?  
**Answer:** No. If order matters, design/separate aspects clearly and declare appropriate precedence.

## 13. Quick Diagnostic Checklist

| Symptom | Check First |
| --- | --- |
| Advice does not run when method fails | Does the call go through the proxy? Does `execution(...)` match the package/method? |
| One exception type runs, another does not | Is the `throwing` parameter type a supertype of the thrown exception? |
| Advice receives a different exception than expected | Is an inner interceptor wrapping exceptions? Is JDK proxy checked-exception wrapping involved? |
| Advice does not run even though method has `throw` | Is the exception caught before the method exits? |
| Spring reports a binding error | Are `throwing`, the method parameter, and `argNames` consistent? |
| Error logs are duplicated | Does the pointcut span multiple service boundaries or retry attempts? |
| Method switches from throwing to returning a fallback | Did an inner `@Around` catch the exception and return normally? |
| Final error is replaced by a logging error | Is the advice itself throwing an exception when logging/metrics fail? |
| Advice runs, but rollback is not as expected | Check transaction ordering and rollback rules; `@AfterThrowing` does not control them |
| Difference occurs only on async methods | Inspect the executor, future completion, and async/advisor ordering |

## 14. Official Spring Framework References

- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `@AfterThrowing`, `throwing` binding, exception type filtering, after-finally/around, and precedence.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation, and method limitations.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): enabling Spring AOP `@AspectJ`-style processing and registering aspect beans.
- [Spring Framework — AspectJ Advice API and Parameters](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): binding advice parameters, `argNames`, and method arguments.
