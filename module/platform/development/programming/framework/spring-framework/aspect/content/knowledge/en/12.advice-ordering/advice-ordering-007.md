# `@After` as `finally` vs. `@AfterReturning` and `@AfterThrowing` in Spring AOP

## 1. Properly Distinguishing the Three Advice Types

In **Spring Framework AOP**, a method on a Spring bean can terminate in two directions:

1. **Normal return:** the method returns a value or completes normally for a `void` method.
2. **Exceptional exit:** the method exits by throwing a `Throwable` across the method execution boundary that Spring AOP is intercepting.

Three annotations are easily confused because all contain the word "After":

- **`@AfterReturning`:** runs only when the selected method execution **completes normally**. Can bind the return value via `returning`.
- **`@AfterThrowing`:** runs only when the selected method execution **exits via an exception**. Can bind the exception via `throwing` and use the parameter type to filter exceptions.
- **`@After`:** runs when the selected method execution **completes in either direction**; in Spring AOP, it is **after (finally) advice**, analogous to a `finally` block.

Therefore, if your goal is "always release resources or record that a method finished," `@After` is appropriate. If your goal is "only log success results" or "only log failure details," the other two make intent clearer.

**Scope of this lesson:** content focuses on **Spring Aspect, Spring AOP advice ordering, and calls going through a Spring proxy**, without restating general AOP knowledge or AspectJ compile-time weaving.

## 2. Event Table — Which One Actually Runs?

Suppose all three advice methods use the **same pointcut**, do not throw exceptions themselves, and the method is called by a client **through a Spring AOP proxy**:

| Method Outcome | `@AfterReturning` | `@AfterThrowing` | `@After` |
| --- | --- | --- | --- |
| `return "OK"` | Runs | Does not run | Runs |
| `return null` | Runs if binding is compatible | Does not run | Runs |
| `void` method completes | Runs if no restricting binding/type excludes it | Does not run | Runs |
| `throw IllegalArgumentException` | Does not run | Runs if exception type matches | Runs |
| `throw IOException` | Does not run | Runs if exception type matches | Runs |
| Method catches error internally and `return "RECOVERED"` | Runs | Does not run | Runs |
| Method returns an error object without `throw` | Runs | Does not run | Runs |
| Method not called via proxy, or pointcut does not match | No advice runs for that call | No advice runs for that call | No advice runs for that call |

**The condition in the last row is critical:** `@After` is not a Java mechanism that automatically injects into every method. Spring AOP creates a **proxy/advisor chain**; if a method does not pass through an advised proxy, none of these advice types are triggered by that call.

### Simple Branch Illustration

```text
                       Client calls proxy.method()
                                  |
                                  v
                           Spring AOP proxy
                                  |
                                  v
                           Target.method()
                             /         \
                            /           \
                     NORMAL RETURN    THROWS ERROR
                           |              |
                           v              v
                  @AfterReturning    @AfterThrowing
                           |              |
                           +-------+------+
                                   |
                                   v
                            @After (finally)
                                   |
                                   v
                        Client receives value/error
```

The diagram illustrates the order of **advice within a single `@Aspect` in modern Spring**, where pointcuts and binding conditions match. When multiple aspects, around advice, or infrastructure advisors intervene, you must also consider the **actual order of the interceptor chain**; do not treat this diagram as a promise that every advice in every aspect always runs in an absolute sequence.

## 3. How Is `@After` Truly Like `finally`?

The Spring documentation calls `@After` **after finally advice**. An example:

```java
@Aspect
public class CompletionAspect {

    @After("execution(* com.example.app.service..*.*(..))")
    public void completed(JoinPoint jp) {
        System.out.println("COMPLETED " + jp.getSignature().getName());
    }
}
```

This is a **snippet that must be registered as a Spring `@Aspect` bean**; `JoinPoint` comes from `org.aspectj.lang.JoinPoint`, and `@After` from `org.aspectj.lang.annotation.After`.

The `COMPLETED` line appears when a matching method execution:

- Returns normally, even when the return value is `null`.
- Terminates due to an unchecked exception.
- Terminates due to a checked exception propagated under Java/proxy contracts.
- Catches an internal exception and still returns normally: only **normal completion** of the method is observed, yet `@After` still runs because that is also a completion.

### Compared to Java `finally`

A Java method can use:

```java
try {
    // business operation
} finally {
    // cleanup inside the method itself
}
```

Spring `@After`, by contrast, is logic **outside the target method**, triggered by the proxy when the pointcut matches. The two are similar in meaning—"runs after the associated execution finishes along any exit path"—but **differ in mechanism**:

| Characteristic | Java `finally` | Spring AOP `@After` |
| --- | --- | --- |
| Where does it live? | Inside the Java code of the `try/finally` block | Inside a Spring `@Aspect` bean |
| Does it require a Spring proxy? | No | Yes (in proxy-based Spring AOP) |
| Applied to methods selected by a pointcut? | Not the purpose of the syntax | Yes |
| Runs automatically on `new Target().method()`? | Yes, if target code has `finally` | No, if the object does not go through a Spring AOP proxy |
| Runs automatically when target calls `this.inner()`? | Follows control flow inside target code | Advice on `inner()` is not triggered if self-invocation bypasses the proxy |
| Binds return value via `returning`? | Not via this annotation | No; use `@AfterReturning` |
| Binds thrown exception via `throwing`? | Not via this annotation | No; use `@AfterThrowing` |

**Important:** `@After` has no `returning` or `throwing` attributes like the two specialized advice types. If you need to distinguish success from failure and access the corresponding data, choose the specialized advice or `@Around`.

### Choosing the Right Purpose

- **Release resources / "method finished" audit:** `@After`.
- **Count only successes / inspect return value:** `@AfterReturning`.
- **Count only failures / inspect thrown exception:** `@AfterThrowing`.
- **Control execution, catch to return fallback, or alter return value:** `@Around`.

Pick the least powerful advice type sufficient for the requirement so you do not accidentally alter business method flow.

## 4. `@AfterReturning`: Runs Only on Normal Return

Declaration:

```java
@AfterReturning(
    pointcut = "execution(* com.example.app.service..*.confirm(..))",
    returning = "result",
    argNames = "result"
)
public void successful(Object result) {
    System.out.println("SUCCESS result=" + result);
}
```

This is a **sample method inside an `@Aspect` bean**.

- `returning = "result"` is the **binding parameter name** of the advice method, not a field or method name of the target.
- `argNames = "result"` helps Spring resolve the binding name unambiguously when the compiler does not retain parameter names.
- `Object result` receives the return value reference if the type is compatible. Using a more specific type restricts which methods/values match.
- The bound return value **is not a place to swap the object returned to the client**. To change the result, use `@Around`.

Target example:

```java
public String confirm(String mode) {
    if ("bad".equals(mode)) {
        throw new IllegalArgumentException("invalid");
    }
    return "OK:" + mode;
}
```

When `confirm("good")` returns `OK:good`, the advice logs `SUCCESS result=OK:good`. For `confirm("bad")`, however, this advice does not run.

### "Success" Here Means Normal Java Method Exit

If the method returns `"DECLINED"` or a `Result.failure(...)` without `throw`, Spring still treats it as a **normal return** and `@AfterReturning` can run. That does not mean the actual business transaction succeeded.

To distinguish business statuses inside a return object, inspect the returned data in appropriate advice and use clear metric names such as `method.completedNormally` rather than defaulting to `business.success`.

## 5. `@AfterThrowing`: Runs Only When an Exception Escapes the Method

Declaration:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.confirm(..))",
    throwing = "failure",
    argNames = "failure"
)
public void failed(IllegalArgumentException failure) {
    System.out.println(
        "FAILURE " + failure.getClass().getSimpleName()
            + ":" + failure.getMessage()
    );
}
```

This is a **sample method**, not a standalone class.

Points to remember:

1. `throwing="failure"` binds the throwable to the Java parameter named `failure`.
2. The **parameter type** `IllegalArgumentException` also acts as a filter condition. If the method exits with `IllegalStateException`, this advice does not run.
3. To cover any subtype of `Exception`, use `Exception`. To cover any subtype of `Throwable` (including `Error`), use `Throwable`—while considering what to log for severe errors.
4. A target call that catches its own error and returns normally **does not trigger** this advice.
5. In standard usage, this advice **does not swallow the exception**; the caller still receives the original exception after the advice runs unless the advice itself alters control flow.

### Do Not Use `@AfterThrowing` as Catch/Recovery on Behalf of the Caller

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.confirm(..))",
    throwing = "failure"
)
public void pretendRecovery(RuntimeException failure) {
    System.out.println("RECOVER?");
}
```

This is a **counterexample of a false expectation**. Logging `RECOVER?` does not turn an exception into a return value. If you want to catch `IllegalArgumentException` and return a different value, use `@Around` with `try/catch` and `pjp.proceed()`, ensuring the return value matches the method signature.

**Official Spring note:** `@AfterThrowing` is not defined as a callback catching every exception thrown by every advice in the chain. Specifically, advice within the same `@Aspect` must not assume `@AfterThrowing` will receive errors thrown by `@After` or `@AfterReturning` of that same aspect. Its intended semantics cover errors escaping from **the join point (target method execution)**.

## 6. Precedence vs. Actual Execution Order

This is the core of the lesson: **advisor precedence** differs from **log line order when a method returns**.

Per Spring Framework 6.2 documentation, for advice methods **of different types within the same `@Aspect`** matching a join point, precedence from highest to lowest is:

```text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
```

However, **`@After` uses finally semantics**, so when execution exits, an `@After` in the same aspect **is actually invoked after `@AfterReturning` or `@AfterThrowing`**.

There is no contradiction here. Precedence determines how interceptors are **nested**. Advice with `finally` semantics completes once execution **inside it** has finished:

```text
SUCCESSFUL CALL, same aspect
----------------------------------
@Around enter
  @Before
    TARGET returns normally
    @AfterReturning
  @After (finally)
@Around exit normally
CLIENT receives result

FAILED CALL, same aspect
----------------------------------
@Around enter
  @Before
    TARGET throws
    @AfterThrowing (if exception type matches)
  @After (finally)
@Around rethrows/handles
CLIENT receives exception or fallback
```

This is the **ordering model from Spring 6.2 semantics** with valid advisors, not an automatic guarantee for every aspect in a system with transaction/cache/async infrastructure and custom advisors.

### Distinguishing Three Kinds of "Order"

| Term | Meaning | Do Not Confuse With |
| --- | --- | --- |
| Precedence among **advice types in the same aspect** | Order of setting up and nesting advisors by type | Order methods appear in the Java file |
| Precedence among **aspects** | Controlled via `@Order` or `Ordered` | Sharing a pointcut meaning an implicit order exists |
| Execution timing on **return/throw branches** | Finally logic executes once the inner portion finishes | Higher-precedence advice always logging first in every direction |

Across multiple aspects, the universal rule is: **higher-precedence aspects run earlier on the way in and later on the way out** (for their corresponding advice), just like nested interceptor layers.

### How Is `@Order` Used?

```java
@Aspect
@Order(1)
public class OuterAspect {
    // outer advice
}

@Aspect
@Order(2)
public class InnerAspect {
    // inner advice when both match
}
```

These classes are **annotation examples**, requiring Spring-managed aspect beans and appropriate imports. Smaller numeric values have higher precedence.

When `OuterAspect` has `@Around`, and inside it `InnerAspect` has `@AfterReturning` and `@After`, logs can occur as:

```text
OUTER enter
TARGET
INNER afterReturning
INNER afterFinally
OUTER return
OUTER finally
```

You should not predict the order between two `@After` methods in the **same aspect** based solely on Java source declaration order; Spring does not guarantee reflection preserves declaration order. If same-type advice needs an explicit order, merge them or split into different aspects with `@Order`.

## 7. Maven Java 17+ Demo: Logging Both Success and Failure

The example below is a **runnable Spring Framework 6.2.6 project**, requiring no Spring Boot. It creates:

- Spring-managed bean `CheckoutService` with implementation `CheckoutServiceImpl`.
- `LifecycleAspect` carrying **`@Before`, `@AfterReturning`, `@AfterThrowing`, and `@After`** on the same `confirm(..)` method.
- `OuterTraceAspect` carrying `@Around`, annotated with `@Order(1)` to wrap outside `LifecycleAspect` (`@Order(2)`).
- Four call paths: success, an exception caught directly inside the target, `IllegalArgumentException` escaping the target, and `IllegalStateException` not matching `@AfterThrowing`'s parameter type.
- Tracing that distinguishes *normal completion*, *exceptional exit*, and *finally completion*.

### 7.1. Project Structure

```text
spring-after-advice-order/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AfterAdviceOrderDemo.java
```

### 7.2. The `pom.xml` File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-after-advice-order</artifactId>
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
                    <mainClass>demo.AfterAdviceOrderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. The `src/main/java/demo/AfterAdviceOrderDemo.java` File

```java
package demo;

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

public class AfterAdviceOrderDemo {

    public interface CheckoutService {
        String confirm(String mode);
    }

    public static class CheckoutServiceImpl implements CheckoutService {
        @Override
        public String confirm(String mode) {
            System.out.println("TARGET confirm " + mode);

            if ("bad".equals(mode)) {
                throw new IllegalArgumentException("invalid order");
            }
            if ("state".equals(mode)) {
                throw new IllegalStateException("unavailable");
            }
            if ("handled".equals(mode)) {
                try {
                    throw new IllegalArgumentException("internal failure");
                } catch (IllegalArgumentException ignored) {
                    System.out.println("TARGET handled internally");
                    return "RECOVERED";
                }
            }
            return "OK:" + mode;
        }
    }

    @Aspect
    @Order(1)
    public static class OuterTraceAspect {
        @Around("execution(* demo..*.confirm(..))")
        public Object around(ProceedingJoinPoint pjp) throws Throwable {
            String mode = String.valueOf(pjp.getArgs()[0]);
            System.out.println("OUTER enter " + mode);

            try {
                Object result = pjp.proceed();
                System.out.println("OUTER return " + result);
                return result;
            } catch (Throwable ex) {
                System.out.println(
                    "OUTER throw "
                        + ex.getClass().getSimpleName()
                        + ":" + ex.getMessage()
                );
                throw ex;
            } finally {
                System.out.println("OUTER finally");
            }
        }
    }

    @Aspect
    @Order(2)
    public static class LifecycleAspect {
        @Before("execution(* demo..*.confirm(..))")
        public void before() {
            System.out.println("BEFORE");
        }

        @AfterReturning(
            pointcut = "execution(* demo..*.confirm(..))",
            returning = "result",
            argNames = "result"
        )
        public void returned(String result) {
            System.out.println("AFTER_RETURNING " + result);
        }

        @AfterThrowing(
            pointcut = "execution(* demo..*.confirm(..))",
            throwing = "failure",
            argNames = "failure"
        )
        public void thrown(IllegalArgumentException failure) {
            System.out.println(
                "AFTER_THROWING "
                    + failure.getClass().getSimpleName()
                    + ":" + failure.getMessage()
            );
        }

        @After("execution(* demo..*.confirm(..))")
        public void finished() {
            System.out.println("AFTER_FINALLY");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class Config {
        @Bean
        public CheckoutService checkoutService() {
            return new CheckoutServiceImpl();
        }

        @Bean
        public OuterTraceAspect outerTraceAspect() {
            return new OuterTraceAspect();
        }

        @Bean
        public LifecycleAspect lifecycleAspect() {
            return new LifecycleAspect();
        }
    }

    private static void runCase(CheckoutService service, String mode) {
        System.out.println("=== " + mode + " ===");
        try {
            System.out.println("CLIENT result=" + service.confirm(mode));
        } catch (RuntimeException ex) {
            System.out.println(
                "CLIENT caught "
                    + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage()
            );
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            CheckoutService service = context.getBean(CheckoutService.class);
            System.out.println("AOP=" + AopUtils.isAopProxy(service));

            runCase(service, "good");
            runCase(service, "handled");
            runCase(service, "bad");
            runCase(service, "state");
        }
    }
}
```

Implementation highlights:

1. `@EnableAspectJAutoProxy(proxyTargetClass=false)` enables Spring AOP in a plain context. Because the target implements `CheckoutService`, the bean can be wrapped in a JDK dynamic proxy.
2. Aspects are explicitly registered via `@Bean`. `@Aspect` **does not auto-register a Spring bean** without component scanning or a factory method.
3. `@Order(1)` gives `OuterTraceAspect` priority over `LifecycleAspect @Order(2)` on the way in; as a result, the outer around advice wraps the inner processing.
4. In `LifecycleAspect`, the advice methods share `execution(* demo..*.confirm(..))`. Only the appropriate exit branches trigger `@AfterReturning` or `@AfterThrowing`, whereas `@After` triggers for both.
5. `@AfterThrowing` specifically accepts `IllegalArgumentException`, so `IllegalStateException` does not trigger that advice.
6. Both business code and advice methods print distinct prefixes so the order is directly observable.

### 7.4. Running the Program

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

The **stdout printed by the program itself** based on the declared flow and aspect order (excluding separate Maven/Spring logs):

```text
AOP=true
=== good ===
OUTER enter good
BEFORE
TARGET confirm good
AFTER_RETURNING OK:good
AFTER_FINALLY
OUTER return OK:good
OUTER finally
CLIENT result=OK:good
=== handled ===
OUTER enter handled
BEFORE
TARGET confirm handled
TARGET handled internally
AFTER_RETURNING RECOVERED
AFTER_FINALLY
OUTER return RECOVERED
OUTER finally
CLIENT result=RECOVERED
=== bad ===
OUTER enter bad
BEFORE
TARGET confirm bad
AFTER_THROWING IllegalArgumentException:invalid order
AFTER_FINALLY
OUTER throw IllegalArgumentException:invalid order
OUTER finally
CLIENT caught IllegalArgumentException:invalid order
=== state ===
OUTER enter state
BEFORE
TARGET confirm state
AFTER_FINALLY
OUTER throw IllegalStateException:unavailable
OUTER finally
CLIENT caught IllegalStateException:unavailable
```

**Note:** this is the expected stdout from the Spring Framework 6.2 code shown, not a claim that a Maven session was executed here. Logging libraries or different versions/configurations may add logs; the example does not hardcode runtime proxy class names.

### 7.5. Case-by-Case Analysis

**`good` branch:** the target method returns `OK:good`. `@AfterReturning` receives the value; `@AfterThrowing` is skipped; `@After` prints `AFTER_FINALLY` **after** `AFTER_RETURNING`. Afterward, the outer around advice logs its return and finally, and then the caller receives the result.

**`handled` branch:** the target method throws `IllegalArgumentException` internally, yet catches it immediately in `catch` and returns `RECOVERED`. Because the exception **does not escape the method execution**, Spring AOP observes a normal return: `@AfterReturning` runs, `@AfterThrowing` does not run, and `@After` still runs.

**`bad` branch:** the target throws `IllegalArgumentException` outward. `@AfterReturning` does not run; `@AfterThrowing` binds the matching exception type and logs; `@After` runs next even though the method failed. The outer advice catches solely to log and then **rethrows the original error**, so the caller still catches it.

**`state` branch:** the target throws `IllegalStateException`. `@AfterThrowing`'s pointcut matches the method but **does not match the exception type**, so no `AFTER_THROWING` line appears. Nevertheless, `@After` still runs due to finally semantics. The caller receives the exception as before.

The difference between the two error branches highlights that **`@After` needs no knowledge of exception type**, whereas `@AfterThrowing(IllegalArgumentException)` filters by type in addition to pointcut matching.

## 8. Why Must `@After` Execute After `@AfterReturning` / `@AfterThrowing`?

Spring builds each advice into an advisor/interceptor arranged in an **invocation chain**. For advice within the same aspect, Spring 6.2 documents precedence across different types. Because `@After` has finally semantics, its implementation performs cleanup after the inner invocation completes—including any matching inner after-returning or after-throwing handlers.

You can picture it as Java pseudocode (not actual Spring code):

```java
Object invokeInnerAdviceAndTarget() throws Throwable {
    try {
        // before advice
        // target execution
        Object result = target();
        // after-returning advice if normal return
        return result;
    } catch (Throwable targetFailure) {
        // after-throwing advice if targetFailure matches
        throw targetFailure;
    }
}

Object invokeAfterFinally() throws Throwable {
    try {
        return invokeInnerAdviceAndTarget();
    } finally {
        // @After runs here
        afterFinally();
    }
}
```

This is **pseudocode for nesting semantics**, not Spring API or source code; do not try to compile it. It underscores two points:

1. Final cleanup inside `finally` runs **after** the inner call finishes or is exiting due to an error.
2. Something with higher precedence on the **way in** does not necessarily log earlier on the **way out**.

### Do Not Confuse `@After` with a Callback "After the Client Already Received the Result"

`AFTER_FINALLY` runs **before the proxy call hands control completely back to the client**, not as an asynchronous callback running after the client receives the result. Synchronous advice executes within the current call's invocation stack. Unless the advice code explicitly performs an async handoff, all side effects happen before the client proceeds past that call.

## 9. When Multiple Aspects Exist: `@Order` and Nesting

Suppose there are two aspects:

```java
@Aspect
@Order(1)
class SecurityTracingAspect {
    // @Around
}

@Aspect
@Order(2)
class BusinessEventsAspect {
    // @After, @AfterReturning, @AfterThrowing
}
```

These are non-standalone **snippets**. In Spring, smaller order numbers have higher priority:

```text
SecurityTracingAspect @Order(1)
     |
     +-- enter
     |
     +---- BusinessEventsAspect @Order(2)
     |             |
     |             +-- TARGET
     |             +-- @AfterReturning or @AfterThrowing
     |             +-- @After (finally)
     |
     +-- exit
```

If precedence is reversed, log order can change because the interceptor chain nests in the opposite direction.

### `@Order` Does Not Order Individual Advice Methods Inside the Same Aspect

Within an `@Aspect` bean, `@Order` sets the precedence of **the aspect** relative to other aspects. Precedence among advice types in **the same aspect** follows Spring's rules; advice methods **of the same type** in one aspect have no guaranteed order based on method position in source code.

For a stable sequence:

- If multiple `@After` actions want to perform cleanup at one join point, consider **one** `@After` method orchestrating them in explicit order.
- If two independent cleanup concerns need different precedences, put them in **two aspects** with appropriate `@Order` annotations.
- Write integration tests verifying log/event sequences whenever order actually impacts behavior.

Do not treat method names like `firstAfter()`, `secondAfter()` or top-to-bottom file placement as an ordering contract.

## 10. Special Exception Cases

### 10.1. Exception Caught Internally by the Target

```java
public String work() {
    try {
        throw new IllegalStateException("transient");
    } catch (IllegalStateException ignored) {
        return "RECOVERED";
    }
}
```

When called through a Spring proxy:

- `@AfterReturning` runs because the method returns normally.
- `@AfterThrowing` does not receive this exception.
- `@After` still runs.

**Do not count "exceptions thrown inside the method body" using `@AfterThrowing`.** The advice only observes an exceptional exit of the join point.

### 10.2. `@AfterThrowing` Filtering by Type

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app..*.work(..))",
    throwing = "failure",
    argNames = "failure"
)
public void onlyIo(IOException failure) {
    // Receives only IOException and its subtypes.
}
```

This is a snippet; it requires importing `java.io.IOException`. If the target throws `IllegalArgumentException`, the advice does not run. Meanwhile, an `@After` with the same pointcut still runs if execution terminates via an exception of any type.

**`throwing` is not `throws`.** `throwing="failure"` is a binding name; the `IOException` advice parameter is a runtime type-matching filter on the throwable. A method declaring `throws IOException` that returns normally does not trigger `@AfterThrowing`.

### 10.3. What If `@AfterReturning` Advice Throws an Exception?

An `@AfterReturning` method can encounter an internal failure while recording metrics, sending a network request, or accessing a recorder. That error belongs to the **advice**, not the original exceptional exit of the target method. Spring documentation states that `@AfterThrowing` must not be viewed as a general callback receiving exceptions from companion `@After` or `@AfterReturning` methods in the same aspect.

From the client's perspective, a new exception from advice can still cause the proxy call to terminate abnormally. Therefore:

- Do not assume a sibling `@AfterThrowing` in the same aspect will log errors thrown by `@AfterReturning`.
- Do not let a secondary telemetry error accidentally mask an important business result or error.
- If you need to manage error flow **across the entire interceptor chain**, an outer `@Around` with `try/catch/finally` and explicit ordering has broader visibility; even then, never catch and swallow exceptions carelessly.

### 10.4. What If `@After` Itself Throws an Exception?

In Java `finally`, an exception thrown inside `finally` can replace the exception or return value currently propagating. With Spring `@After`, throwing an error from the advice can similarly affect the exception/result the client receives. Thus cleanup in `@After` should be simple and have a clear error-handling strategy.

Example **to avoid doing carelessly**:

```java
@After("execution(* com.example.app..*.work(..))")
public void cleanup() {
    throw new IllegalStateException("telemetry unavailable");
}
```

This is an **anti-pattern**: a logging/metric failure can turn a valid business call into an error or hide the root exception. Do not use `@After` as a place that throws exceptions indiscriminately.

### 10.5. Does `@After` Run If `@Before` Throws an Exception?

The answer depends on **position in the interceptor chain**. Within an aspect having different-type precedence, a before advice can sit outside an after/finally advice. If `@Before` throws an exception **before the chain enters the `@After` advisor**, the inner `@After` was never entered, so it is not guaranteed to run.

Hence the accurate statement is: `@After` runs when **the matched join point execution it wraps** finishes along either the normal or exception path; not "it always runs for any error raised by any advice in every configuration."

If cleanup is required even when **an outer precondition advice** fails before the target is called, design an outermost `@Around` with `try/finally`, explicit ordering, and dedicated tests.

## 11. Scenarios Involving Spring Transactions, Caching, and Async

### 11.1. `@Transactional`: When Does `@After` Run Relative to Commit/Rollback?

Spring transactions use a dedicated **transaction interceptor/advisor**. `@After` and `@AfterThrowing` declared in your custom aspect are **separate advisors** in the same or another proxy chain.

If your custom aspect sits **inside** the transaction advice, after/finally logs may appear **before the transaction interceptor finishes committing or rolling back**. If it sits outside, it can observe a different outcome. Do not infer from the word `After` that "the transaction has definitely committed or rolled back."

Nor should you assume that `@AfterThrowing` running forces Spring to roll back. Transaction rollback rules depend on exception types and settings like `rollbackFor` / `noRollbackFor`.

### 11.2. `@Cacheable`: Cache Hits Can Skip the Target

The caching advisor can return a value from cache **without calling the target method**. What custom after advice observes depends on its position relative to the caching interceptor:

- If custom advice sits **outside** the cache interceptor, it sees a cache hit as a normal return from the inner chain.
- If custom advice sits **inside** and a cache hit prevents the inner chain from being invoked, the custom advice may not run at all.

Do not assume `@AfterReturning` always means "the target method executed" when caching, fallbacks, or outer around advice exist.

### 11.3. `@Async`: Proxy Return Is Not Necessarily Task Completion

An `@Async` method can return a `Future` or `CompletableFuture`, or run on an executor thread. `@AfterReturning` at a proxy boundary may be invoked when receiving the **future object** or whatever state the advisor exposes—not meaning the business task actually succeeded.

Similarly, `@After` meaning "method execution at the proxy boundary ended" does not replace a completion callback on a future. When measuring task completion, attach `whenComplete` or an appropriate async-specific hook.

### 11.4. Retry: How Many Times Does `@After` Run?

A retry interceptor or outer around advice can invoke the inner chain/target multiple times. If a custom `@After` sits **inside the retry loop**, it can run after every attempt. If it sits **outside**, it can run once for the client call after retries finish.

Therefore, metric definitions must be clear: **attempt count** vs. **logical client call count**, and interceptor ordering must align with the measurement goal.

## 12. Using `@After` for Cleanup Without Breaking Business Logic

A cleanup aspect should pay attention to:

1. **Idempotency:** cleanup side effects may execute multiple times with retries or layered service proxies.
2. **Do not break flow on logger/metric failures:** telemetry code needs its own error policy; avoid unintended throws in `finally`.
3. **Avoid unsafe shared mutable state:** `@Aspect` beans are typically singletons; do not store per-call "start time" or method-specific state in shared fields when multiple threads call concurrently.
4. **Per-invocation data:** for timing, prefer local variables inside `@Around` with `try/finally`. Separating `@Before` and `@After` methods requires proper context storage and thread propagation.
5. **Do not log secrets:** `JoinPoint.getArgs()` may contain credentials or PII; log only safe metadata, never dump entire argument objects.
6. **Narrow pointcut scope:** target specific beans, service packages, or annotations to avoid accidentally proxying logging infrastructure itself.
7. **Write positive and negative tests:** normal return, checked/unchecked exceptions, internally caught exceptions, non-matching advice, and self-invocation.
8. **Understand transaction/cache/async ordering:** "after method" does not always mean "after all transaction or async business events."

A pure event-recording cleanup example:

```java
@Aspect
public class CompletionAspect {
    @After("execution(public * com.example.app.service..*.*(..))")
    public void onExit(JoinPoint jp) {
        System.out.println(
            "COMPLETE " + jp.getSignature().toShortString()
        );
    }
}
```

This is a snippet in a Spring environment with `@AspectJ` enabled; not a full configuration. It logs events **on both return and throw branches**, without binding the result or exception.

## 13. Diagnosing Unexpected Logs

| Symptom | Check |
| --- | --- |
| `@After` does not run even though method was called | Is there a Spring AOP proxy? Does the pointcut match? Did the caller use `new` or self-invocation? |
| `@AfterReturning` does not run | Did the method throw an exception? Does the `returning` parameter type restrict matching? |
| `@AfterThrowing` does not run | Did an error escape the method? Is the binding parameter a supertype of the exception? |
| `AFTER_FINALLY` appears even though `@AfterThrowing` did not run | Does the exception type not match `throwing`? This may be the intended behavior |
| `AFTER_FINALLY` appears after `AFTER_RETURNING` | This is Spring 6.2 after-finally semantics within the same aspect |
| Order between two aspects is not as desired | Check `@Order`/`Ordered`, advisor precedence, and way-in/way-out ordering |
| Two `@After` methods in the same aspect print out of source order | Source declaration order is not an ordering contract; merge or split aspects |
| Exception from logging hides target error | Did `@After` or another advice throw a new error? |
| `@After` reports completion before transaction commits | Check relative ordering with the transaction interceptor |
| Cache hit does not log the same as cache miss | Check ordering between caching interceptor and custom advice |
| Async method logs too early | Proxy return differs from task completion; observe future/executor |
| Retry logs multiple times | Is the advice inside or outside the retry loop? |
| JDK vs. CGLIB behaves differently | Check interface methods/`final`/`private`, `AopUtils.isJdkDynamicProxy` / `isCglibProxy` |

### Verifying Whether a Spring Bean Is Proxied

```java
Object bean = context.getBean("checkoutService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean).getName());
```

This snippet **is not a standalone program**. It uses `org.springframework.aop.support.AopUtils`, and `context` must be a valid Spring context. Being a proxy does not mean **every method** on the bean matches custom advice; verify the pointcut and actual caller path.

### Most Important Integration Tests

To prove the semantics:

- Call the Spring bean through a real `ApplicationContext`.
- Verify success: `@AfterReturning` → `@After`.
- Verify matching failure: `@AfterThrowing` → `@After`.
- Verify non-matching failure: **`@After` only**, without the specific `@AfterThrowing`.
- Verify handled exception: `@AfterReturning` → `@After` because the target recovered.
- Test adding a higher-`@Order` aspect to verify nesting across multiple aspects.
- Avoid asserting solely on business return values; use a recorder/mock/spy or captured logger to assert **advice events**.

## 14. Self-Check

**Question 1.** A method returns `null` normally. Which advice types can run?  
**Answer:** `@AfterReturning` (if binding is compatible) and `@After`. `@AfterThrowing` does not run merely because the return value is null.

**Question 2.** The target throws `IllegalArgumentException` to the client; `@AfterThrowing` accepts `IllegalArgumentException` and `@After` uses the same pointcut. Which runs?  
**Answer:** Both; within the same modern Spring aspect, the matching `@AfterThrowing` runs and then `@After` runs as finally.

**Question 3.** The target throws `IllegalStateException`, while `@AfterThrowing` only accepts `IllegalArgumentException`. Does `@After` run?  
**Answer:** Yes, because exception type does not restrict `@After`; `@AfterThrowing` is filtered out by its parameter type.

**Question 4.** The target throws an exception inside a `try` block, catches it itself, and returns `"OK"`. Does `@AfterThrowing` run?  
**Answer:** No; target method execution completed normally, so `@AfterReturning` and `@After` can run.

**Question 5.** In Spring 6.2, the same aspect has `@After` and `@AfterReturning`. Does `@After` log before `@AfterReturning` just because it has higher precedence?  
**Answer:** No. Under after-finally semantics, `@After` is called after the matching after-returning on the way out.

**Question 6.** Does `@AfterThrowing` receive every exception thrown by an `@AfterReturning` advice in the same aspect?  
**Answer:** No. Spring does not define it as a general exception callback for companion after advice.

**Question 7.** Does putting `@After` in an `@Aspect` bean mean every Java method in the application gets cleaned up?  
**Answer:** No. You need a Spring-managed target, AOP proxy entry, and a matching pointcut.

**Question 8.** Can two `@After` methods in the same aspect be ordered by the order they are written in the Java file?  
**Answer:** There is no guarantee. Merge the logic or split into aspects with explicit `@Order`.

**Question 9.** An outer `@Around` catches an error and returns a fallback. Is an outer `@AfterThrowing` guaranteed to see the original exception?  
**Answer:** No, because part of the chain may have converted the exceptional exit into a normal return before the outer advice observed it.

**Question 10.** Does `@After` running prove that the database transaction has committed or rolled back?  
**Answer:** No. You must check relative transaction interceptor order and rollback rules.

## 15. Official Spring Framework Documentation

- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): semantics of `@After`, `@AfterReturning`, `@AfterThrowing`, and the *Advice Ordering* section describing advice-type precedence and actual after-finally behavior.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): distinguishing after returning, after throwing, after finally, and around advice.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): registering Spring `@Aspect` beans and enabling Spring AOP.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): proxy limitations, JDK/CGLIB, and self-invocation.
- [Spring Framework — Declarative Transaction Rollback](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html): rollback rules separate from custom aspects observing exceptions.
