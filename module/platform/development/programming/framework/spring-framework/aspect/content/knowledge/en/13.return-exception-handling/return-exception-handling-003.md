# Checked Exceptions, Unchecked Exceptions, and Proxy Interface Signatures in Spring AOP

## 1. Why can the same exception change type when passing through a Spring proxy?

When using Spring `@Aspect`, you can encounter a seemingly paradoxical situation:

- Inside an `@Around` advice, `throw new IOException("...")` is executed.
- Yet the service caller catches **`java.lang.reflect.UndeclaredThrowableException`**, not `IOException` directly.
- With `IllegalStateException`, the caller receives the original exception directly.
- If the interface method declares `throws IOException`, `IOException` can pass through a JDK proxy without being wrapped.

This difference is directly tied to the **`throws` contract of the method invoked on a JDK dynamic proxy**. Spring AOP uses proxies to intercept method executions on Spring-managed beans; when a **JDK dynamic proxy** is chosen, the proxy implements Java interfaces. JVM/JDK-generated proxies follow very specific rules for checked exceptions thrown by an `InvocationHandler`.

The general rule:

> A JDK proxy can pass through unchecked `RuntimeException`/`Error` directly as well as checked exceptions **compatible with the `throws` clause declared on the proxy interface method**. If the invocation handler throws a checked exception incompatible with that contract, calling the proxy throws `java.lang.reflect.UndeclaredThrowableException` wrapping the original exception.

This is a JDK proxy rule that Spring AOP must operate within—**not every `IOException` in Spring is automatically wrapped**.

**Scope:** How Spring `@AspectJ` advice affects exceptions through a **Spring AOP proxy**, specifically interface methods, JDK proxies, class-based CGLIB proxies, `@Around`, and `@AfterThrowing`. It does not go into general Java exception theory unrelated to Spring, nor AspectJ bytecode weaving outside Spring.

### Learning outcomes

After this lesson, you will be able to:

1. Distinguish checked `Exception` from unchecked `RuntimeException`/`Error` **when propagating through a Spring JDK proxy**.
2. Understand the difference between `throws` on the **proxy interface method**, `throws` on the implementation method, and `throws Throwable` on advice.
3. Explain accurately when `java.lang.reflect.UndeclaredThrowableException` appears and how to find the original cause.
4. Write observational/rethrowing `@Around` advice without inadvertently altering the exception contract.
5. Bind `@AfterThrowing(throwing="...")` correctly and understand how advisor position affects which exception the advice observes.
6. Distinguish JDK proxy limitations from class-based CGLIB proxies without overgeneralizing.
7. Run a complete Java 17/Spring Framework demo: normal return, declared checked exception, undeclared checked exception from advice, and unchecked exception.
8. Diagnose exception issues alongside proxy type, self-invocation, transactions, and multiple advisors.

## 2. Three contract layers involved in a call

Suppose the caller executes:

```java
ReportApi api = context.getBean(ReportApi.class);
api.load();
```

In Spring AOP there are three layers to separate:

| Layer | Example | Role |
| --- | --- | --- |
| **Proxy interface API** | `interface ReportApi { String load() throws IOException; }` | Contract used by the caller; the JDK-generated proxy method lists the permitted declared checked exceptions |
| **Target implementation** | `class ReportService implements ReportApi` | Contains the business Java code; may return a result or throw |
| **Spring advice/interceptor** | `@Around ... throws Throwable` | May call `proceed()`, catch/rethrow, or throw a new exception before/after the target |

Typical flow:

```text
Caller (type ReportApi)
    |
    v
JDK-generated Spring AOP proxy
    |
    v
JdkDynamicAopProxy / InvocationHandler
    |
    +--> Spring advisor/interceptor chain
    |       |
    |       +--> @Around advice (throws Throwable)
    |       |
    |       +--> other advisors, if any
    |       |
    |       +--> target method
    |
    v
Proxy method boundary checks outgoing Throwable
    |
    +--> checked exception compatible with interface throws: pass through
    +--> RuntimeException / Error: pass through
    +--> undeclared checked exception: wrap in UndeclaredThrowableException
    |
    v
Caller
```

The key point is that **`throws Throwable` on advice does not "widen" the signature of `ReportApi.load()`**. Java source allows advice to declare `throws Throwable` because `ProceedingJoinPoint.proceed()` throws `Throwable`, but the proxy interface still has its own `throws` contract.

## 3. Checked and unchecked exceptions in the JDK proxy contract

### 3.1. Checked exception declared by the interface

```java
public interface ReportApi {
    String load() throws IOException;
}
```

`IOException` is a checked exception declared by the interface method. If the target or advice throws `IOException` and no other interceptor transforms it, the JDK proxy can propagate `IOException` directly to the caller.

If the method declares `throws Exception`, `IOException` is also compatible (because it is a subtype of `Exception`). If it only declares `throws FileNotFoundException`, a general `IOException` does not automatically match because it is not a subtype of `FileNotFoundException`.

An interface declaring `throws IOException` **does not force** every call to throw `IOException`; it only states that the method may throw it. `RuntimeException`/`Error` can still be thrown without being listed in `throws`.

### 3.2. Unchecked exceptions do not need to be declared in the interface

```java
public interface ReportApi {
    String load();
}
```

If the target or advice throws `IllegalStateException`, it is a subtype of `RuntimeException`, so it is not constrained by the JDK proxy's checked-exception signature rule.

Likewise, `Error` and its subtypes are unchecked. You should not proactively catch all `Error` instances and convert them into success states; severe system errors must be propagated/monitored appropriately.

### 3.3. Checked exception absent from the proxy interface throws clause

```java
public interface ReportApi {
    String load();
}
```

If a **Spring `@Around` advice** throws `new IOException("from advice")` when `load()` does not declare `throws IOException`, the JDK-generated proxy cannot expose it as a valid checked exception on the interface method. It wraps the original exception:

```text
java.lang.reflect.UndeclaredThrowableException
    |
    +-- getUndeclaredThrowable() -> java.io.IOException("from advice")
```

The caller can inspect `ex.getUndeclaredThrowable()` or the cause to find the original error, but the sustainable fix is not "always unwrap at the caller": **you need to design the error contract of the service and advice properly**.

### 3.4. Expected outcomes table with JDK dynamic proxy

| Throwable exiting the interceptor chain | `interface method throws` | Caller typically receives |
| --- | --- | --- |
| `new IOException("disk")` | `throws IOException` | `IOException` |
| `new FileNotFoundException("file")` | `throws IOException` | `FileNotFoundException` |
| `new IOException("disk")` | no checked exception declared | `UndeclaredThrowableException` containing `IOException` |
| `new IOException("disk")` | `throws SQLException` | `UndeclaredThrowableException` containing `IOException` |
| `new IllegalStateException("bad")` | no `throws` | `IllegalStateException` |
| `new AssertionError("broken")` | no `throws` | `AssertionError` |
| `new IOException("disk")` | `throws Exception` | `IOException` |

**Assumptions:** This describes `java.lang.reflect.Proxy` via a Spring JDK proxy, where the exception actually escapes the invocation handler and is not altered by another advisor before the boundary. When multiple interfaces share the same method signature with different `throws` constraints, carefully examine the contract of each corresponding proxy method; avoid relying on one interface view while ignoring other proxied interfaces.

## 4. Crucial mistake: an implementation cannot widen checked throws on its own

Suppose:

```java
interface JobApi {
    void run();
}
```

The implementation below is **invalid at compile time**:

```java
class JobService implements JobApi {
    @Override
    public void run() throws IOException {
        throw new IOException("disk");
    }
}
```

Java does not allow an overriding method to add **new, broader, or incompatible checked exceptions** relative to the interface method's contract. This is a `javac` error, **not a Spring proxy runtime error**.

So where does an undeclared `IOException` come from when the interface still does not declare it? Practical sources include:
- An `@Around` advice throwing `IOException` itself under its `throws Throwable` signature.
- `@Before`, `@After`, `@AfterThrowing` advice, or a custom interceptor throwing a checked exception incompatible with the interface.
- A library, reflection, or sneaky-throw technique passing a checked exception along a path not checked by the compiler as a source-level override.
- An advisor translating a declared exception into another incompatible checked exception.

**Pattern to avoid:** changing an exception inside an aspect and expecting caller `catch(IOException)` to always catch it even when the interface method does not declare `throws IOException`.

## 5. @Around: proceed() and proper rethrowing to preserve the contract

```java
@Aspect
public class ExceptionAspect {

    @Around("execution(* com.example.app.service..*.*(..))")
    public Object observe(ProceedingJoinPoint pjp) throws Throwable {
        try {
            return pjp.proceed();
        } catch (Throwable error) {
            System.out.println(
                "aspect:saw:" + error.getClass().getSimpleName());
            throw error;
        }
    }
}
```

This is an illustrative snippet without complete Spring configuration; full runnable code is in section 9.

**Why declare `throws Throwable`?** `ProceedingJoinPoint.proceed()` declares `throws Throwable`. Advice may observe and rethrow the original `Throwable`; however, whether the caller ultimately receives the direct exception or a wrapper still depends on **the proxy method contract and any other advisors**.

Do not write:

```java
catch (Throwable error) {
    throw new IOException("wrapped", error);
}
```

if the advice pointcut covers many service methods where some do not declare `IOException`. With a JDK proxy, most of those calls can start producing `UndeclaredThrowableException` at the caller.

### 5.1. Errors created **before** proceed

```java
@Around("execution(* com.example.api.JobApi.run(..))")
public Object validate(ProceedingJoinPoint pjp) throws Throwable {
    throw new IOException("validation infrastructure failure");
}
```

This snippet assumes an interface method `run()` exists without declaring the checked exception. If a Spring JDK proxy executes a method without `throws IOException`, the advice has thrown a checked exception and **the target never ran**; the caller can receive an `UndeclaredThrowableException` wrapper.

### 5.2. Target errors vs. advice errors are distinct

In logging, distinguish between:
- `target_failure`: target business logic actually threw an exception;
- `advice_failure`: an instrumentation/logging/auditing aspect itself threw an exception;
- `proxy_boundary_wrapping`: the JDK proxy converted an exception **emitted out of the interceptor chain** into a wrapper due to incompatible `throws`.

Note that `UndeclaredThrowableException` **does not prove the target threw an error**. It may simply be evidence that an aspect threw a contract-violating checked exception while the target was never even called.

### 5.3. Do not turn catch-all into exception swallowing

```java
catch (Throwable error) {
    return null;
}
```

is not the way to fix `UndeclaredThrowableException`. If the target returns a primitive or requires a non-null result, `null` will break the caller differently. If the operation mutates business state, returning normally after an error can break transaction rollback and application behavior. Use an intentional exception policy rather than concealing the cause.

## 6. What does @AfterThrowing observe?

Spring `@AfterThrowing` runs when a **matched join point exits by throwing an exception**, and can bind the exception via `throwing`:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "cause",
    argNames = "cause"
)
public void onThrown(Throwable cause) {
    System.out.println(cause.getClass().getSimpleName());
}
```

This snippet resides in a Spring `@Aspect` bean. With `Throwable`, binding does not filter out checked exceptions; changing it to `RuntimeException` restricts the advice to exceptions in the runtime hierarchy.

**Subtlety:** With a JDK proxy, `java.lang.reflect.UndeclaredThrowableException` can be created **at the proxy/generated method layer after the Spring AOP interceptor chain has already thrown `IOException` outward**. An `@AfterThrowing` **inside** the Spring AOP chain may observe the original `IOException`, while the caller outside receives `UndeclaredThrowableException`. Do not treat `@AfterThrowing` logs as a guarantee of the caller's final exception type.

Conversely, if an inner advisor already created a wrapper before `@AfterThrowing` ran, the advice may see the wrapper. What is actually observed always depends on **interceptor position**.

### 6.1. Binding does not change the exception type

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "error",
    argNames = "error"
)
public void onChecked(IOException error) {
    // Only observe matching IOException; does not automatically turn
    // IOException into RuntimeException.
}
```

An `@AfterThrowing` that only logs and returns normally **does not swallow the original exception**. If the advice throws a new exception itself, the new exception can override the previous one. Check `throws` compatibility on the proxy method before throwing checked exceptions from advice itself.

### 6.2. What if the target catches IOException itself and returns?

```java
public String safeLoad() {
    try {
        return fetch();
    } catch (IOException ex) {
        return "FALLBACK";
    }
}
```

This is an illustrative snippet where `fetch()` is not defined. If the exception is caught by the target and the method returns normally, `@AfterThrowing` for `safeLoad` **does not run** because there is no exceptional completion of the method execution, even though `IOException` was thrown inside the source.

### 6.3. @AfterReturning and @After

- `@AfterReturning` handles normal completion; `null` is still a normal return.
- `@AfterThrowing` handles exceptional completion exiting the join point.
- `@After` has finally semantics across both normal and exceptional exits.
- `@Around` controls `proceed()`, and can catch/rethrow/fallback, so the outcome outside the chain can differ from the target's outcome.

All four only take effect when Spring AOP intercepts the call through the proxy.

## 7. JDK proxy vs. CGLIB: accurately comparing limitations

Spring Framework supports two common proxy mechanisms:

| Criterion | JDK dynamic proxy | CGLIB class-based proxy |
| --- | --- | --- |
| Proxy created via | `java.lang.reflect.Proxy` / interface implementations | Runtime subclass of the target class |
| Methods clients can call via proxy | Methods exposed by proxied interfaces | Accessible/overridable methods per class proxy |
| Relationship to target implementation class | Proxy is usually **not instanceof** implementation | Proxy is a subclass of implementation |
| Undeclared checked exception check | JDK `InvocationHandler` rule: checked incompatible with `throws` produces `java.lang.reflect.UndeclaredThrowableException` | Does not automatically apply JDK `java.lang.reflect.Proxy` rules; actual behavior depends on generated method/interceptor and must be tested |
| `final` class | Can proxy via interface if the final target class implements a suitable interface | Cannot subclass a final class |
| `final` / `private` target method | JDK proxy can intercept exposed interface methods (does not override target class methods) | Cannot override `final`/`private` methods |
| Self-invocation | Bypasses Spring AOP proxy | Bypasses Spring AOP proxy |

**Do not conclude "CGLIB guarantees every checked exception is thrown directly unwrapped."** CGLIB has its own interceptors/code generation and has CGLIB or framework wrappers of its own. The specific `java.lang.reflect.UndeclaredThrowableException` rule above is guaranteed by the JDK standard for **JDK dynamic proxies**. If you choose CGLIB, empirically test the exception type and cause on your application's Spring version and specific target signatures.

Also **do not switch to CGLIB merely to hide a broken interface throws contract**. If an API has a checked-exception contract issue, fixing the interface, revising the exception policy, or translating to a meaningful unchecked exception is a more sustainable design.

### 7.1. Spring configuration reference

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class JdkProxyConfig {
}
```

In an appropriate Spring context, `proxyTargetClass=false` allows choosing a JDK proxy when the target implements an interface. To request class-based proxies:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class CglibProxyConfig {
}
```

These are **two alternative configuration snippets**; do not import both configurations into the same context and expect each bean to get a different proxy type, as class-based proxy settings can be merged across auto-proxy mechanisms. The runnable example below uses only JDK proxies so the outcome can be deduced with certainty from the `InvocationHandler` Javadoc.

## 8. Checked exceptions in API design and Spring aspects

### 8.1. Keep the contract explicit when the caller truly handles the error

If the caller needs to catch and recover from `IOException`:

```java
public interface DocumentApi {
    byte[] load(String id) throws IOException;
}
```

The implementation may throw `IOException` or a subtype. Inside `@Around`, if the service method and advice rethrow `IOException`, the JDK proxy sees an exception matching `throws`.

An API declaring `throws Exception` would also permit `IOException`, but it is overly broad and pushes error-handling burden onto callers. Choose a specific checked type when the contract genuinely needs to represent a recoverable error.

### 8.2. When checked exceptions cannot or should not be declared

You can choose a clear **unchecked domain exception**:

```java
public class ReportUnavailableException extends RuntimeException {
    public ReportUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Inside Spring advice:

```java
try {
    return pjp.proceed();
} catch (IOException ex) {
    throw new ReportUnavailableException("Cannot load report", ex);
}
```

Both are **snippets meant for a real project**; do not paste them into the demo without updating the code and expected stdout. Switching to an unchecked domain exception is an **intentional change to the error contract**. Do not use a generic `RuntimeException` without message/cause; preserve `ex` as the cause for debugging.

### 8.3. Do not widen throws just to accommodate a logging aspect

A `@Before` logging advice should not throw `IOException` merely because a log sink failed and then force all service interfaces to declare `throws IOException`. For non-critical instrumentation, consider internal logging fallback/retry and an instrumentation error metric. For mandatory auditing, design the contract and controlled failure explicitly rather than accidentally changing exception types at the JDK proxy boundary.

### 8.4. When multiple interfaces share the same method

A JDK proxy can implement **multiple** interfaces. If they have methods with the same name and parameter signature but different `throws` clauses, the allowed exception types have additional constraints. Do not inspect only the interface the caller happens to cast to; check all relevant proxied interfaces, compiler/JDK proxy rules for duplicate method signatures, and write integration tests against the actual proxy.

## 9. Complete Java 17 + Spring Framework example

The example uses a Spring service implementing an interface with four operations:

1. `success()`: returns normally.
2. `declaredChecked() throws IOException`: target throws a validly declared `IOException`.
3. `undeclaredChecked()`: **has no `throws IOException`**, yet `@Around` throws `IOException` before the target is called.
4. `failUnchecked()`: target throws `IllegalStateException` (unchecked).

Key takeaway: the difference between **permitted checked** and **unpermitted checked** appears at the **JDK dynamic proxy** method boundary, without needing to write invalid Java implementation code.

**Environment**: Java 17+, Spring Framework `6.1.14`, AspectJ Weaver `1.9.22.1`, Gradle. Uses plain Spring Framework without Spring Boot auto-configuration dependencies.

### 9.1. Project structure

```text
spring-aop-exception-contract/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/proxycase/
    ├── ReportApi.java
    ├── ReportService.java
    ├── CheckedAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 9.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-exception-contract'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.proxycase.DemoApplication'
}
```

### 9.3. Interface contract

`src/main/java/demo/proxycase/ReportApi.java`:

```java
package demo.proxycase;

import java.io.IOException;

public interface ReportApi {
    String success();

    String declaredChecked() throws IOException;

    String undeclaredChecked();

    String failUnchecked();
}
```

Among the four methods, **only `declaredChecked()` declares `throws IOException`**. This is the detail that governs JDK proxy behavior in the verification section.

### 9.4. Target implementation

`src/main/java/demo/proxycase/ReportService.java`:

```java
package demo.proxycase;

import java.io.IOException;

public class ReportService implements ReportApi {

    @Override
    public String success() {
        System.out.println("target:success");
        return "OK";
    }

    @Override
    public String declaredChecked() throws IOException {
        System.out.println("target:declaredChecked");
        throw new IOException("disk");
    }

    @Override
    public String undeclaredChecked() {
        System.out.println("target:undeclaredChecked");
        return "UNEXPECTED";
    }

    @Override
    public String failUnchecked() {
        System.out.println("target:failUnchecked");
        throw new IllegalStateException("boom");
    }
}
```

`undeclaredChecked` is written **validly**: it neither declares nor throws a checked exception itself. In the demo, the undeclared checked exception originates from Spring `@Around`, not from an illegal Java override.

### 9.5. Aspect that creates and observes the exception paths

`src/main/java/demo/proxycase/CheckedAspect.java`:

```java
package demo.proxycase;

import java.io.IOException;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class CheckedAspect {

    @Around(
        "target(demo.proxycase.ReportService)"
        + " && execution(public * *(..))"
    )
    public Object observe(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();

        System.out.println("around:enter:" + method);

        try {
            if ("undeclaredChecked".equals(method)) {
                throw new IOException("advice-checked");
            }
            return pjp.proceed();
        } catch (Throwable error) {
            System.out.println(
                "around:throw:" + method
                + ":" + error.getClass().getSimpleName());
            throw error;
        } finally {
            System.out.println("around:finally:" + method);
        }
    }
}
```

**Why does declaring `throws Throwable` on `@Around` not violate Java compilation?** This is a separate advice method, not an implementation of `ReportApi`. Spring invokes it in the interceptor chain, and `proceed()` has a `throws Throwable` contract. When the exception exits **outside** the chain for the JDK proxy to return to the caller, the **`ReportApi` method's `throws` clause** is the boundary that matters.

**What the demo intentionally does:** For `undeclaredChecked`, the aspect throws `IOException` *before calling `proceed()`*. Hence there is **no** `target:undeclaredChecked` line in stdout. If that line appeared, the advice would have entered the target and the demo would no longer illustrate "checked exception created by advice before target" as intended.

### 9.6. Spring configuration

`src/main/java/demo/proxycase/AppConfig.java`:

```java
package demo.proxycase;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {

    @Bean
    public ReportApi reportApi() {
        return new ReportService();
    }

    @Bean
    public CheckedAspect checkedAspect() {
        return new CheckedAspect();
    }
}
```

`@Bean reportApi()` returns interface `ReportApi`; the actual runtime object is `ReportService` implementing the interface. `@EnableAspectJAutoProxy(proxyTargetClass = false)` uses interface-based proxies in this configuration.

`@Bean checkedAspect()` registers the aspect; `@Aspect` alone does not turn a Java class into a Spring bean. Because the pointcut targets `ReportService`, the advice applies to service method executions via the proxy, without advising Spring infrastructure or the aspect itself.

### 9.7. Main verifying exceptions on the caller side

`src/main/java/demo/proxycase/DemoApplication.java`:

```java
package demo.proxycase;

import java.io.IOException;
import java.lang.reflect.UndeclaredThrowableException;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            ReportApi api = context.getBean(ReportApi.class);
            System.out.println(
                "jdkProxy=" + AopUtils.isJdkDynamicProxy(api));

            System.out.println("caller:success:" + api.success());

            try {
                api.declaredChecked();
            } catch (IOException ex) {
                System.out.println("caller:declared:"
                    + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
            }

            try {
                api.undeclaredChecked();
            } catch (UndeclaredThrowableException ex) {
                Throwable original = ex.getUndeclaredThrowable();
                System.out.println("caller:undeclared:"
                    + ex.getClass().getSimpleName()
                    + ":" + original.getClass().getSimpleName()
                    + ":" + original.getMessage());
            }

            try {
                api.failUnchecked();
            } catch (IllegalStateException ex) {
                System.out.println("caller:unchecked:"
                    + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
            }
        }
    }
}
```

**Design note:** The caller of `api.undeclaredChecked()` **cannot** write `catch(IOException ex)` around that call alone in Java source if no other statement in the try block can throw `IOException`: the compiler would report that the checked exception is "never thrown". Therefore, the demo catches `UndeclaredThrowableException`, which is a `RuntimeException`.

In production error handling, you should usually design a consistent interface/advice contract so callers do not have to unwrap wrappers. Calling `getUndeclaredThrowable()` here is solely to **demonstrate the root cause**.

### 9.8. Running the project

In the directory containing `build.gradle`:

```bash
gradle run
```

If the project includes the Gradle Wrapper, use `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows).

### 9.9. Expected stdout from the Java code

```text
jdkProxy=true
around:enter:success
target:success
around:finally:success
caller:success:OK
around:enter:declaredChecked
target:declaredChecked
around:throw:declaredChecked:IOException
around:finally:declaredChecked
caller:declared:IOException:disk
around:enter:undeclaredChecked
around:throw:undeclaredChecked:IOException
around:finally:undeclaredChecked
caller:undeclared:UndeclaredThrowableException:IOException:advice-checked
around:enter:failUnchecked
target:failUnchecked
around:throw:failUnchecked:IllegalStateException
around:finally:failUnchecked
caller:unchecked:IllegalStateException:boom
```

These are the lines printed by the Java code itself, excluding Gradle, Spring logging, or other environment output.

### 9.10. Analyzing the output by interface signature

| Method | Checked `throws` on `ReportApi` | Original exception in advice/target | Caller receives |
| --- | --- | --- | --- |
| `success()` | None | None | `"OK"` |
| `declaredChecked()` | `IOException` | `IOException("disk")` from target | `IOException("disk")` |
| `undeclaredChecked()` | None | `IOException("advice-checked")` from `@Around` | `java.lang.reflect.UndeclaredThrowableException` |
| `failUnchecked()` | None | `IllegalStateException("boom")` from target | `IllegalStateException("boom")` |

Three key observations:

1. The log `around:throw:undeclaredChecked:IOException` appears **before** the line where the caller receives `UndeclaredThrowableException`. The advice sees the original exception, while the JDK proxy boundary changes the exception's form.
2. There is no `target:undeclaredChecked`: the checked exception was created **inside the aspect**, and the target never ran. Thus you must not conclude the target failed solely because the caller received `UndeclaredThrowableException`.
3. `failUnchecked` passes through as `IllegalStateException` because it is unchecked; the interface method does not need to list `throws IllegalStateException`.

This is the outcome of the JDK proxy demo configuration. If you add another aspect that catches, wraps, or swallows exceptions before reaching the generated proxy, the output must be re-evaluated according to the new advisor ordering.

## 10. When does @Around unexpectedly produce UndeclaredThrowableException?

There are several common error patterns.

### 10.1. Logging aspect throws a new checked exception

```java
@Around("execution(* demo.proxycase..*.*(..))")
public Object log(ProceedingJoinPoint pjp) throws Throwable {
    auditSink.write("start"); // suppose this can throw IOException
    return pjp.proceed();
}
```

This is a **non-standalone** snippet: `auditSink` is a hypothetical dependency. If `auditSink.write` throws checked `IOException` and the advised proxy interface method does not declare `IOException`, the JDK proxy can wrap it. In fact, the target may not even have run.

Mitigation: define an explicit **audit failure policy**. If auditing is mandatory, express the failure in the service contract or as a domain unchecked exception. If auditing is non-critical, handle/log instrumentation errors internally instead of accidentally causing every API to throw wrapped exceptions.

### 10.2. After-throwing advice replaces the original exception with a different checked type

```java
@AfterThrowing(
    pointcut = "execution(* demo.proxycase..*.*(..))",
    throwing = "error",
    argNames = "error"
)
public void changeFailure(Throwable error) throws IOException {
    throw new IOException("audit failed", error);
}
```

This snippet is **not recommended**. When the target threw `IllegalStateException` but after-throwing advice turns it into checked `IOException` that the interface method does not declare, the JDK proxy can wrap `IOException`. The caller loses direct visibility of the target failure; the original exception is buried as a cause. An error-observing advice should log and return, not throw a new exception unless an explicit policy calls for it.

### 10.3. The misconception that "advice throws Throwable is enough"

`throws Throwable` on advice only lets the Java compiler accept exceptions passing through `proceed()`. It **does not modify the interface method's bytecode signature** and does not tell callers to catch `IOException`. Evaluate the API interface layer and the advice layer separately.

### 10.4. Always unwrapping at the caller instead of fixing the contract

Unwrapping `UndeclaredThrowableException` can be useful in diagnostics, but if the application has to unwrap at every call site because an aspect keeps throwing checked exceptions incompatible with interface contracts, that is a design smell. Align on:
- Which checked exceptions callers need to handle;
- Which unchecked domain exceptions describe unrecoverable failures at this layer;
- Which instrumentation errors should not break operations;
- The order of advisors permitted to catch or wrap.

## 11. Spring transactions and rollback: distinct from checked/unchecked proxy wrapping

In Spring Framework 6.1, Spring declarative transactions default to rolling back on `RuntimeException` or `Error`; checked `Exception` typically does not trigger rollback automatically unless `rollbackFor` is configured appropriately.

**This is a transaction rule**, **distinct** from the JDK proxy wrapping rule:

- The JDK proxy determines whether the caller sees a direct checked exception or `UndeclaredThrowableException` based on interface `throws`.
- The Spring transaction interceptor decides rollback based on the exception **it observes at its position in the advisor chain** and the rollback rules.
- A checked exception might be caught and converted to unchecked by `@Around`—or vice versa—before the transaction interceptor sees it, depending on order.
- Once the transaction interceptor has decided to roll back, an outer advice converting the exception into a fallback does not automatically undo that rollback decision.

Do not conclude "because the caller saw `UndeclaredThrowableException`, the transaction definitely rolled back." Inspect the transaction advisor's position and the exact exception it received.

### Domain policy example

If a database write must roll back when `BusinessCheckedException` escapes, you can declare:

```java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void applyChanges() throws BusinessCheckedException {
    // ...
}
```

This illustrative snippet requires `@Transactional`, the `BusinessCheckedException` class, a Spring transaction manager, and transaction AOP configuration. It does not automatically add `throws BusinessCheckedException` to a JDK proxy interface. If the service is invoked through a JDK proxy interface, the interface contract must still be compatible for the caller to see the checked exception directly.

## 12. Does Spring always use a JDK proxy when an interface exists?

In Spring AOP, if a target implements an interface, JDK dynamic proxy is typically the default, but **you cannot conclude that solely by seeing "an interface exists"**:
- `@EnableAspectJAutoProxy(proxyTargetClass = true)` forces class-based proxies;
- Spring Boot may provide a different default depending on version, properties, or configuration;
- Auto-proxy creators in the same context can merge configuration;
- A custom `ProxyFactory` may have `setProxyTargetClass(true)` configured.

Check at runtime:

```java
Object proxy = context.getBean("reportApi");
System.out.println(AopUtils.isAopProxy(proxy));
System.out.println(AopUtils.isJdkDynamicProxy(proxy));
System.out.println(AopUtils.isCglibProxy(proxy));
```

This is a diagnostic snippet requiring `context` and importing `AopUtils`, not a standalone runnable Java file.

With JDK proxies, the best practice is usually to inject the interface and keep the checked `throws` contract clear. With CGLIB, clients can receive a class-based proxy, but you must understand `final`/`private` constraints and not expect identical checked-exception wrapping as JDK proxies.

## 13. Self-invocation and exceptions: bypassing the proxy boundary

Suppose the target implementation is:

```java
public void outer() {
    inner();
}

public void inner() {
    throw new IllegalStateException("boom");
}
```

If the caller invokes `outer()` through the Spring proxy:
- Advice matching `outer()` can run.
- The `this.inner()` call **inside the target** does not go through the proxy, so advice matching only `inner()` is not triggered for the internal call.
- The exception from `inner()` can still propagate out through `outer()` to the proxy caller, where the exception/proxy interface signature rules apply to **the invoked `outer()` method**.

That is the difference between "Spring advice did not run" and "the Java exception did not propagate". Self-invocation does not suppress Java exceptions; it only bypasses the Spring AOP interceptor chain for the internal call.

If you want advice on `inner()`, extract it to a Spring-managed collaborator and invoke it through the collaborator's proxy. Do not use `getTarget()` to call directly and expect transaction/logging interceptors to still run.

## 14. Quick troubleshooting table

| Symptom | Possible explanation | How to fix |
| --- | --- | --- |
| Caller sees `UndeclaredThrowableException` after a JDK proxy call | Checked exception incompatible with `throws` of the proxied interface method | Inspect `getUndeclaredThrowable()`, identify the advice/target throwing it, fix the API/policy |
| Aspect logs `IOException` but caller sees a wrapper | Wrapping happens at the JDK-generated proxy boundary after the inner chain | Distinguish the exception inside the aspect from the caller-visible exception |
| `IllegalStateException` passes through proxy unwrapped | Unchecked exceptions do not require `throws` | This is normal behavior |
| Declared `throws IOException` on advice yet still wrapped | Advice signature does not alter the interface signature | Declare the checked type on the interface if the contract permits |
| Implementation adds `throws IOException` when interface does not allow it; build fails | Java override rule forbids broadening checked exceptions | Fix interface/implementation design, not Spring config |
| `@AfterThrowing` misses errors from an outer aspect | Advice did not cross that pointcut/interceptor, or exception arose outside its observation point | Check advisor chain/order |
| Target did not run yet caller sees an `IOException` wrapper | `@Around`/`@Before` threw before `proceed()` | Inspect instrumentation code and lines before proceed |
| Caller `catch(IOException)` does not compile for undeclared API | Java compiler checks the method contract | Catch the `RuntimeException` wrapper for debugging, then fix the API |
| Switching to CGLIB changes the error behavior | Actual proxy type changed; class-based proxies use a different interception mechanism | Test exception/cause; do not hide contract bugs by switching proxy type |
| Spring transaction does not roll back even though aspect logged an exception | Checked exception, or catch/fallback and advisor order/rules | Check transaction advisor position and `rollbackFor` |
| Exception thrown internally yet after-throwing did not run | Target caught it and returned, or self-invocation bypassed the proxy | Check target call/return paths |
| Replacing exception inside `@AfterThrowing` loses the original error | Advice threw a new error replacing the prior one | Preserve the original exception/cause and log safely |
| JDK proxy does not expose extra implementation methods | Interface did not declare the method | Design the public service API or use class proxies if genuinely needed |
| Unexpected proxy type observed | `proxyTargetClass`/Boot/custom infrastructure differs from expectation | Use `AopUtils.isJdkDynamicProxy` and `isCglibProxy` |

## 15. Checklist for designing @Aspect exception handling

- [ ] Verify whether the proxy is a **JDK dynamic proxy** or **CGLIB**; do not guess from the target class name.
- [ ] For JDK proxies, check `throws` on the **interface method the caller invokes**.
- [ ] Do not try to declare broader checked exceptions in implementation overrides.
- [ ] By default `@Around` should `return pjp.proceed()`, log, and **rethrow the original exception** unless a fallback policy applies.
- [ ] `@Before`/`@AfterThrowing`/`@After` must not accidentally throw new checked exceptions disallowed by the interface.
- [ ] Do not use `throws Throwable` on advice as a way to "widen" the interface exception contract.
- [ ] When encountering `UndeclaredThrowableException`, inspect the underlying checked cause before diagnosing business failure.
- [ ] Preserve `cause` when intentionally translating into a domain unchecked exception.
- [ ] Do not dangerously log-and-swallow `Throwable` broadly; consider `Error` and fatal problems.
- [ ] When using `@AfterThrowing`, know exactly where it sits in the advisor chain and which exceptions it observes.
- [ ] With transactions, configure rollback rules properly and test against a real Spring proxy.
- [ ] Have tests for normal, declared checked, undeclared checked, and unchecked exceptions.
- [ ] Have tests for proxy type and interface exposure when the application can change AOP config.
- [ ] Do not forget self-invocation: `this.method()` does not create a new Spring AOP intercepted invocation.
- [ ] With multi-interface duplicate signatures, test checked-exception contracts against the actual generated proxy.

## 16. Conclusion

In Spring AOP, the exception a caller sees is determined **jointly** by:

1. **The outcome of the target/advice/interceptor chain** — does it throw the original exception or return normally?
2. **The proxy type** — JDK dynamic proxy or class-based CGLIB?
3. **The method contract at the proxy boundary** — for JDK proxies, is the checked exception compatible with the interface method's `throws` list?

**`IOException` is a checked exception; `IllegalStateException` is unchecked.** A checked exception matching the interface's `throws` can pass straight through a JDK proxy; a checked exception thrown by Spring advice that is not permitted by the interface method can be wrapped into **`java.lang.reflect.UndeclaredThrowableException`**. Unchecked exceptions generally pass straight through.

**`throws Throwable` on `@Around` does not change the interface's `throws` contract.** Therefore, do not try to fix errors merely by changing the advice signature. Design interfaces, domain exceptions, proxy configuration, and advisor ordering deliberately; when debugging, inspect both the exception inside the advice and the exception on the caller side.

### References

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK dynamic proxy, CGLIB, proxy selection, and limitations.
- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html): default interface-based proxies, class-based proxies.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `@Around`, `@AfterThrowing`, propagation, and binding.
- [Spring Framework — Advice API](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html): behavior when advice throws a checked exception not compatible with the signature.
- [Java SE 17 — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): `throws` rules from handler and `UndeclaredThrowableException`.
- [Java SE 17 — UndeclaredThrowableException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html): `RuntimeException` wrapper for undeclared checked exceptions.
- [Spring Framework — Declarative Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules independent of JDK proxy wrapping rules.
