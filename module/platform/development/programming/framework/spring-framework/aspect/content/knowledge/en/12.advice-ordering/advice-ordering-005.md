# Order Among Advice Types Within the Same Spring AOP @Aspect

## 1. The Question to Resolve

A single Spring `@Aspect` can simultaneously contain multiple methods annotated with `@Around`, `@Before`, `@After`, `@AfterReturning`, and `@AfterThrowing`. When all of those advice methods have pointcuts matching a service call, **which advice runs first, which runs later, and why does `@After` appear last despite having higher precedence than `@AfterReturning`?**

This is a question about **ordering in the Spring AOP interceptor chain**, not simply the order methods are written in a Java file.

According to modern Spring Framework documentation, when **different advice types within the same `@Aspect` class** match the same method-execution join point, Spring assigns **precedence from highest to lowest**:

1. `@Around`
2. `@Before`
3. `@After`
4. `@AfterReturning`
5. `@AfterThrowing`

**Commonly misunderstood exception:** `@After` has *after finally* semantics, so when the method finishes, **`@After` is actually invoked after `@AfterReturning` or `@AfterThrowing` in the same aspect**. Precedence determines **the advice's position in the interceptor chain**, not a chronological list of printed log lines.

In a normal method invocation, you typically observe:

```text
@Around (before proceed)
    @Before
        target method
    @AfterReturning
    @After
@Around (after proceed / finally)
```

If the target method throws an exception:

```text
@Around (before proceed)
    @Before
        target method -> throw
    @AfterThrowing
    @After
@Around (catch/finally)
```

These two flows apply to **a single `@Aspect` class with the corresponding advice types**, all targeting one Spring bean method, where `@Around` calls `proceed()` once without intentionally altering the result or exception.

**Scope:** Spring Framework `@AspectJ`-style **proxy-based AOP**. This lesson only covers how Spring creates and runs advisors/interceptors from an `@Aspect`; it does not extend to bytecode weaving, constructor, or field join point ordering in the standalone AspectJ compiler.

### Lesson Goals

- Know the precedence among **advice types** within **the same `@Aspect`**.
- Distinguish precedence **on the way in** from callback timing **on the way out**.
- Explain why `@After` runs after `@AfterReturning` or `@AfterThrowing`.
- Know that the order of **two advice methods of the same type in the same `@Aspect` is undefined**.
- Distinguish ordering within the **same aspect** from `@Order`/`Ordered` used across **multiple aspects**.
- Run a Java 17 / Spring Framework 6.1 demo covering normal return, `null`, thrown exception, and an exception caught inside the target.
- Understand limitations: self-invocation, `@Around` skipping `proceed()`, other advisors blocking the call path, and exceptions thrown from other advice.

## 2. Precedence Is Not Line-of-Code Order

### 2.1. "On the Way In" and "On the Way Out"

Spring AOP builds an **interceptor chain** behind a Spring-managed proxy. When a call travels from the client toward the target:

- Advice with **higher precedence** sits on the **outside** of the chain.
- Outer advice can observe the call **before** inner advice.
- When the inner chain completes and the call stack unwinds, outer advice is normally returned to **last**.

Suppose two hypothetical around interceptors have precedence A higher than B:

```text
A:before
    B:before
        target
    B:after
A:after
```

A is invoked first "on the way in" and last "on the way out." This is the general rule for nested interceptors.

However, each advice type has its own semantics. A `@Before` runs at the front of the invocation, while `@AfterReturning` only runs when the matching join point **returns normally**. You cannot deduce log order merely by reading the precedence list as a FIFO queue.

### 2.2. Standard Order Within an @Aspect (Spring Framework 6.1)

| Precedence | Advice Type | Execution Timing |
| ---: | --- | --- |
| 1 — highest | `@Around` | Starts before the rest of the chain; calls `proceed()` to continue; can observe results/exceptions afterward |
| 2 | `@Before` | Runs before target method execution when the interceptor chain reaches it |
| 3 | `@After` | Holds higher precedence position than specialized after advice, yet its callback runs as `finally`, **after** `@AfterReturning`/`@AfterThrowing` of the same aspect |
| 4 | `@AfterReturning` | Runs only if execution completes **normally**, including returning `null` or `void` |
| 5 — lowest | `@AfterThrowing` | Runs only if execution terminates with an **escaping exception** |

**Version note:** The precedence rule categorizing advice types within a single `@Aspect` was clarified by Spring Framework starting in **5.2.7** and continues to be documented in 5.3/6.x. Do not apply the statement "the order of all advice in the same aspect is undefined" from older Spring documentation to modern versions. **Two advice methods of the same type** remain undefined, as covered in section 7.

### 2.3. Why Does @After Have Higher Precedence Yet Run Later?

Spring handles `@After` with semantics equivalent to:

```java
try {
    // Pass the call down to inner interceptors.
} finally {
    // Execute @After.
}
```

The inner `@AfterReturning`/`@AfterThrowing` complete only as the inner chain unwinds, after which `@After`'s `finally` executes.

Therefore, **ranking `@After` third in precedence while seeing `@After`'s log appear after the specialized after advice is completely consistent**. That is the difference between:
- **Precedence:** the ordering of the **interceptor chain**;
- **Event timing:** the actual callback timing as the call stack runs and unwinds.

Do not change `@Order` just to force `@After` to print before `@AfterReturning` within the same aspect. `@Order` is primarily used to set precedence **between different aspects**, not to alter after-finally semantics.

## 3. Two Main Completion Paths: Normal and Throwing

### 3.1. Method Returns Normally

A method can return:
- A `String` or non-null object value.
- `null`.
- No value if the return type is `void`.
- A business failure status like `"REJECTED"` without throwing an exception.

All of these are **normal completion** to Spring AOP as long as no exception escapes the method execution. When all advice in the same aspect matches and `@Around` calls `proceed()`, the normal path flows through:

```text
around:enter
before
target returns value
afterReturning(value)
after
around:return(value)
around:finally
caller sees value
```

`@AfterThrowing` does not run on this path.

**Do not equate normal return with business success.** `return null` or `return "DECLINED"` is still a normal completion in Java terms, even if it represents a business failure. Use metric names that reflect true semantics, rather than labeling every `@AfterReturning` a "business success."

### 3.2. Method Throws an Exception Outward

If the target throws `IllegalStateException` and the exception propagates out through the interceptor chain:

```text
around:enter
before
target throws
afterThrowing(exception)
after
around:catch(exception)
around:finally
caller sees exception
```

`@AfterReturning` does not run on this path. `@AfterThrowing` can bind the exception using its `throwing` parameter, and `@After` still runs afterward per after-finally semantics.

`@Around` on the outside can catch/rethrow the exception; `around:catch` appears after `after` in this example because `proceed()` has finished unwinding the inner interceptors.

### 3.3. Target Catches the Exception Internally and Returns

Example:

```java
public String safeWork() {
    try {
        return remoteOperation();
    } catch (IOException ex) {
        return "FALLBACK";
    }
}
```

This is an illustrative snippet; `remoteOperation` is not defined here. If an exception is caught internally by the target and the method **returns normally**, Spring AOP only observes normal completion of the join point:
- `@AfterReturning` runs;
- `@AfterThrowing` does not run for the caught exception;
- `@After` runs.

Spring AOP does not intercept individual `throw`/`catch` statements *inside* a method. That is not an advice ordering bug.

### 3.4. Throwing from Another Advice Is Not the Same as Throwing from Target

Spring documentation warns: advice types within a single aspect are designed **to apply to the join point**, so `@AfterThrowing` should not be treated as "a catcher for any exception from `@After` or `@AfterReturning` in that same aspect."

For instance, `@AfterReturning` throws an exception while processing the result. Do not design `@AfterThrowing` in the same aspect expecting it to catch that exception as a general error handler. Handle instrumentation errors within the advice itself, preserve the original business outcome when needed, or establish an explicit exception policy with `@Around`. Interaction with advisors in **other aspects** depends on chain position.

## 4. @Around Wraps the Outside and Can Alter Flow

`@Around` is the highest-precedence advice within the same aspect, and has the ability to **control** whether the target runs.

### 4.1. Outcome-Preserving Form

```java
@Around("execution(* com.example.app.service..*.*(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("around:enter");
    try {
        return pjp.proceed();
    } finally {
        System.out.println("around:finally");
    }
}
```

This is a snippet inside a Spring `@Aspect`, requiring imports and Spring AOP configuration. `proceed()` continues the inner chain exactly once. `finally` runs when `proceed()` returns or throws per standard Java semantics.

### 4.2. @Around Without Calling proceed

```java
@Around("execution(public String com.example.app.service.LookupService.lookup(..))")
public Object shortCircuit(ProceedingJoinPoint pjp) {
    return "CACHED";
}
```

If code returns a result without calling `proceed()`, **inner** advice does not run, and the target method is not executed. That outcome is not "Spring randomly ignoring `@Before`"; the around advice deliberately stopped the chain.

If your logging code expects `@Before`, `@AfterReturning`, and `@After` to run, **do not short-circuit in an around advice outside them**.

### 4.3. @Around Catches and Returns a Fallback

```java
@Around("execution(public String com.example.app.service.LookupService.lookup(..))")
public Object recover(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return "FALLBACK";
    }
}
```

This is an illustrative snippet. If the target throws `IllegalStateException`, inner advice of the **same aspect** may already have observed `@AfterThrowing` before the outer around advice catches it and returns `"FALLBACK"`. From outside the around advice, the call completes normally. Thus:
- **Target/inner chain outcome:** exception.
- **Caller-visible proxy outcome:** normal return `"FALLBACK"`.

Do not interpret every `@AfterThrowing` log entry as an exception guaranteed to reach the caller. When fallback, caching, transactions, or retries exist, define the exact **measurement point** for each metric.

### 4.4. @Around Throws Before proceed

If around advice throws an exception **before** calling `proceed()`, inner advice has not been entered yet. Hence `@AfterThrowing` in the same aspect will not run for an exception thrown by the outer around advice itself. Do not try using one advice in the same aspect as a global error handler for all other advice.

## 5. Runnable Example: Observing Exact Order via Stdout

The following example uses:
- **Java 17+**;
- **Spring Framework 6.1.14**;
- **AspectJ Weaver 1.9.22.1**;
- Gradle;
- One `@Aspect` with all **five different advice types** targeting the same target method.

Four scenarios:
1. `work("ok")` returns `"OK"`.
2. `work("empty")` returns `null`.
3. `work("fail")` throws `IllegalStateException`.
4. `work("recovered")` catches `IllegalStateException` internally and returns `"FALLBACK"`.

All calls from `main` go through the Spring-managed AOP proxy. The example intentionally **avoids multiple advice methods of the same type**, so the log order is governed by Spring 6.1 semantics rather than falling into undefined ordering.

### 5.1. Project Structure

```text
spring-aop-advice-order/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/order/
    ├── WorkService.java
    ├── OrderingAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 5.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-advice-order'
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
    mainClass = 'demo.order.DemoApplication'
}
```

`spring-context` provides `AnnotationConfigApplicationContext` and Java configuration; `spring-aop` provides proxy infrastructure; `aspectjweaver` lets Spring parse `@Aspect` pointcuts. This is plain Spring Framework without Spring Boot logging or auto-configuration to clutter the example.

### 5.3. Service with Three Outcome Types

`src/main/java/demo/order/WorkService.java`:

```java
package demo.order;

public class WorkService {

    public String work(String mode) {
        System.out.println("target:" + mode);

        if ("ok".equals(mode)) {
            return "OK";
        }
        if ("empty".equals(mode)) {
            return null;
        }
        if ("fail".equals(mode)) {
            throw new IllegalStateException("broken");
        }
        if ("recovered".equals(mode)) {
            try {
                throw new IllegalStateException("temporary");
            } catch (IllegalStateException ex) {
                return "FALLBACK";
            }
        }
        return "UNKNOWN";
    }
}
```

The `recovered` branch intentionally catches inside the target, so the method execution **does not** throw an exception out of the Spring AOP proxy. This tests the distinction between "a throw occurred inside Java code" and "the method execution ended with an exception."

### 5.4. One @Aspect with Exactly Five Advice Types

`src/main/java/demo/order/OrderingAspect.java`:

```java
package demo.order;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class OrderingAspect {

    private static final String POINTCUT =
        "execution(public String demo.order.WorkService.work(String))";

    @Around(POINTCUT)
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String mode = (String) pjp.getArgs()[0];
        System.out.println("around:enter:" + mode);

        try {
            Object result = pjp.proceed();
            System.out.println(
                "around:return:" + String.valueOf(result));
            return result;
        } catch (Throwable ex) {
            System.out.println(
                "around:catch:" + ex.getClass().getSimpleName());
            throw ex;
        } finally {
            System.out.println("around:finally:" + mode);
        }
    }

    @Before(POINTCUT)
    public void before(JoinPoint jp) {
        String mode = (String) jp.getArgs()[0];
        System.out.println("before:" + mode);
    }

    @AfterReturning(
        pointcut = POINTCUT,
        returning = "result",
        argNames = "result"
    )
    public void afterReturning(Object result) {
        System.out.println(
            "afterReturning:" + String.valueOf(result));
    }

    @AfterThrowing(
        pointcut = POINTCUT,
        throwing = "error",
        argNames = "error"
    )
    public void afterThrowing(Throwable error) {
        System.out.println(
            "afterThrowing:" + error.getClass().getSimpleName());
    }

    @After(POINTCUT)
    public void afterFinally(JoinPoint jp) {
        String mode = (String) jp.getArgs()[0];
        System.out.println("after:" + mode);
    }
}
```

**Why does this example not depend on `-parameters`?**
- `@Around` only accepts `ProceedingJoinPoint`.
- `@Before`/`@After` only accept `JoinPoint` as the first parameter.
- `@AfterReturning` explicitly declares `returning="result"` and `argNames="result"`.
- `@AfterThrowing` explicitly declares `throwing="error"` and `argNames="error"`.

From the Spring AOP standpoint:
- `@Around` opens the entry path and is the last to unwind in this example.
- `@Before` runs before the target is invoked.
- `@AfterReturning` runs for `ok`, `empty`, and `recovered`.
- `@AfterThrowing` runs only for `fail`.
- `@After` runs after the return/throw-branch advice, yet before `proceed()` completes and `@Around` prints its trailing lines.

**Note:** Using `private static final String POINTCUT` above is valid because an annotation attribute must be a compile-time constant (`static final String` composed of string literals). This is not a runtime-computed variable.

### 5.5. Enabling Spring AOP and Registering Beans

`src/main/java/demo/order/AppConfig.java`:

```java
package demo.order;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public WorkService workService() {
        return new WorkService();
    }

    @Bean
    public OrderingAspect orderingAspect() {
        return new OrderingAspect();
    }
}
```

`@Aspect` **does not** automatically register a bean; here `@Bean orderingAspect()` does so. `@EnableAspectJAutoProxy(proxyTargetClass = true)` activates Spring AOP and uses a class-based proxy because `WorkService` does not implement an interface in the demo.

### 5.6. Entry Point

`src/main/java/demo/order/DemoApplication.java`:

```java
package demo.order;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            WorkService service = context.getBean(WorkService.class);
            System.out.println("proxy=" + AopUtils.isAopProxy(service));

            invoke(service, "ok");
            invoke(service, "empty");
            invoke(service, "fail");
            invoke(service, "recovered");
        }
    }

    private static void invoke(WorkService service, String mode) {
        try {
            String result = service.work(mode);
            System.out.println("caller:" + mode + ":" + result);
        } catch (IllegalStateException ex) {
            System.out.println(
                "caller:" + mode + ":throws:"
                + ex.getClass().getSimpleName());
        }
    }
}
```

### 5.7. Running the Application

In the directory containing `build.gradle`, using Gradle with Java 17 support:

```bash
gradle run
```

If using the Gradle Wrapper, run `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows).

**Output printed by the Java program**, excluding Gradle lines or environmental logging:

```text
proxy=true
around:enter:ok
before:ok
target:ok
afterReturning:OK
after:ok
around:return:OK
around:finally:ok
caller:ok:OK
around:enter:empty
before:empty
target:empty
afterReturning:null
after:empty
around:return:null
around:finally:empty
caller:empty:null
around:enter:fail
before:fail
target:fail
afterThrowing:IllegalStateException
after:fail
around:catch:IllegalStateException
around:finally:fail
caller:fail:throws:IllegalStateException
around:enter:recovered
before:recovered
target:recovered
afterReturning:FALLBACK
after:recovered
around:return:FALLBACK
around:finally:recovered
caller:recovered:FALLBACK
```

### 5.8. Interpreting the Results

| Input | `@Before` | Completion Branch | `@After` | `@Around` Path |
| --- | --- | --- | --- | --- |
| `ok` | `before:ok` | `afterReturning:OK` | `after:ok` | `enter` → `return:OK` → `finally` |
| `empty` | `before:empty` | `afterReturning:null` | `after:empty` | `enter` → `return:null` → `finally` |
| `fail` | `before:fail` | `afterThrowing:IllegalStateException` | `after:fail` | `enter` → `catch` → `finally` |
| `recovered` | `before:recovered` | `afterReturning:FALLBACK` | `after:recovered` | `enter` → `return:FALLBACK` → `finally` |

Directly verifiable conclusions:

1. `@Around` prints `around:enter` **before** `@Before`; after the target and inner advice in the chain finish, around prints `return/catch/finally`.
2. `@After` appears **after** `@AfterReturning` or `@AfterThrowing`, even though it ranks higher in the precedence table.
3. `return null` is still a normal return and does not trigger `@AfterThrowing`.
4. An exception caught by the target and turned into `"FALLBACK"` does not escape the method execution, so it takes the `@AfterReturning` path.
5. `IllegalStateException` from `fail` is observed by `@AfterThrowing` and still reaches the caller because `@Around` rethrows the original exception.
6. The output only proves ordering within **the same `@Aspect`** with **each advice type appearing once**; it does not prove ordering between two different `@Before` methods in the same aspect.

## 6. Interceptor Chain Model Explaining the Output

Spring processes the call through a combined chain. For this demo, it can be visualized simply as:

```text
Client
  |
  v
Spring AOP proxy
  |
  +-- Around interceptor [precedence 1]
  |       enter
  |       try {
  |           |
  |           +-- Before interceptor [2]
  |           |       before
  |           |       |
  |           |       +-- After(finally) interceptor [3]
  |           |       |       try {
  |           |       |           |
  |           |       |           +-- AfterReturning [4]
  |           |       |           |      |
  |           |       |           |      +-- AfterThrowing [5]
  |           |       |           |              |
  |           |       |           |              v
  |           |       |           |            target
  |           |       |           |
  |           |       |           +-- normal: afterReturning
  |           |       |           +-- throw: afterThrowing
  |           |       |       } finally {
  |           |       |           after
  |           |       |       }
  |           |       |
  |       } finally {
  |           around:finally
  |       }
  |
  v
Caller
```

This is a **semantic explanation diagram**, not an internal implementation model guaranteed to match node-for-node across every Spring version or interceptor implementation. However, for Spring `@AspectJ` advice ordering as documented, the model accurately shows why `@After` logs after completion-specific advice.

### Why Not Write "@After Runs Before @AfterReturning"?

Because that statement relies solely on the precedence list and ignores the `finally` mechanism. **Higher precedence** means the advice wraps *outside* lower-precedence advice; with after-finally, the callback sits on the **exit step** of that outer scope, so it is actually invoked later.

### Why Not Write "@After Is Always the Last Line"?

Because `@Around` has higher precedence, wraps outside `@After`, and can perform work after `proceed()`; in the example it prints `around:return` and `around:finally` **after `@After`**. If other aspects, transaction/cache/retry, or custom interceptors are present, log placement can change too.

## 7. Two Advice Methods of the Same Type in the Same @Aspect: Undefined Order

Another easy point of confusion:

```java
@Aspect
public class DoubleBeforeAspect {

    @Before("execution(* demo.order.WorkService.work(..))")
    public void firstLog() {
        System.out.println("A");
    }

    @Before("execution(* demo.order.WorkService.work(..))")
    public void secondLog() {
        System.out.println("B");
    }
}
```

This is an **illustrative snippet**; do not paste it into the section 5 project if you want to keep the exact stdout.

Never promise `A` will always print before `B` just because `firstLog()` is written above `secondLog()` in the Java source. For two advice methods of the same type within the same `@Aspect`, the Spring reference states **ordering is undefined**, because Java reflection on `javac`-compiled classes does not provide a reliable source declaration order.

### How to Fix It

**Option 1 — Merge into one advice** if two actions must always go together:

```java
@Before("execution(* demo.order.WorkService.work(..))")
public void logInOrder() {
    System.out.println("A");
    System.out.println("B");
}
```

Now the order `A` then `B` is the order of **statements within a single Java method**, which is unambiguous.

**Option 2 — Split into two aspects** if independent policies and ordering via `@Order` are needed:

```java
@Aspect
@Order(10)
public class FirstAspect {
    @Before("execution(* demo.order.WorkService.work(..))")
    public void first() { System.out.println("A"); }
}
```

```java
@Aspect
@Order(20)
public class SecondAspect {
    @Before("execution(* demo.order.WorkService.work(..))")
    public void second() { System.out.println("B"); }
}
```

These are illustrative snippets requiring `@Aspect`, `@Order`, `@Before` imports and registering both as Spring beans. The aspect with the **lower** `@Order` value has **higher** precedence: `FirstAspect` is called first on the way in.

**What does NOT solve it:** Putting `@Order(1)` on **one aspect containing both `@Before` methods** does not make the order between two same-type advice methods in that class deterministic. Aspect-level `@Order` is not an annotation that numbers individual methods inside the same `@Aspect`.

## 8. Same Aspect vs. Multiple Aspects: Do Not Conflate Them

### 8.1. Rule Within One Aspect

Within **one** `@Aspect` class and across **different advice types**, Spring assigns precedence by advice type:

```text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
```

That is **precedence**, not after-phase log print order. `@After` actually runs after completion-specific advice due to finally semantics.

### 8.2. Rule Across Aspects

Between **two or more `@Aspect` classes**, if unspecified, Spring does not guarantee ordering between aspects when multiple advice methods match.

Use:
- `@Order(int)` on the aspect class;
- Or implement `org.springframework.core.Ordered` on the aspect bean.

**Smaller order values have higher precedence.** With two around aspects:

```text
@Order(1): around A before
    @Order(2): around B before
        target
    @Order(2): around B after
@Order(1): around A after
```

Intra-aspect advice precedence and aspect-level ordering are **two related but non-identical classification dimensions**. When writing integration tests, be explicit about which dimension is being tested.

### 8.3. When Transactions, Caching, and Retries Are Present

`@Transactional`/`@Cacheable` in proxy mode contribute interceptors/advisors from other Spring infrastructure. Those advisors are not necessarily advice methods inside **your own `@Aspect` class**. Hence you cannot take the 5-advice-type precedence table and declare that logging is always outside transactions or always inside cache.

In a proxy with multiple advisors:
- Spring `@Order` and infrastructure advisor ordering can affect timing scope.
- A cache hit can short-circuit before an inner advice runs.
- Retry can execute the target multiple times even though the caller called the proxy once.
- Transaction rollback depends on exception rules and the order in which the transaction interceptor observes the outcome.

Inspect advisor ordering or test with the real `ApplicationContext`, rather than guessing from code order.

## 9. @AfterReturning, @AfterThrowing, and @After Do Not Replace Each Other

### 9.1. @AfterReturning Only on Normal Completion

```java
@AfterReturning(
    pointcut = "execution(* demo.order.WorkService.work(..))",
    returning = "value",
    argNames = "value"
)
public void completed(Object value) {
    // Even null is a normal completion.
}
```

`returning` can bind the result; the advice parameter type acts as a type constraint. Changing `Object` to `String` narrows which cases match. Do not use after-returning to swap the reference returned to the caller; use `@Around` if you need to alter the result.

### 9.2. @AfterThrowing Only on Exceptional Completion

```java
@AfterThrowing(
    pointcut = "execution(* demo.order.WorkService.work(..))",
    throwing = "error",
    argNames = "error"
)
public void failed(Throwable error) {
    // Exception escaping from execution.
}
```

If the target method catches an exception before returning a fallback, `@AfterThrowing` is not called for the exception caught inside the target. If the advice parameter is typed as `IllegalArgumentException`, other exceptions will not bind. Use `Throwable` when observing both checked and unchecked errors, and do not swallow errors in advice meant only for logging.

### 9.3. @After Follows Finally

```java
@After("execution(* demo.order.WorkService.work(..))")
public void finished() {
    // Both normal and exceptional completion.
}
```

`@After` does not know whether the final outcome was business success or failure; it merely acts as a finally hook. If you need both the result and exception in one scope, use `@Around` and manage `proceed()` carefully.

### 9.4. What If a @Before Throws an Exception?

`@Before` can throw an exception, stopping the inner chain from proceeding. In that case, the target method may **not have run yet**, and completion advice sitting inside may not be invoked. Do not assume every call that entered the proxy is guaranteed to produce all `@After`/`@AfterThrowing` lines of the same aspect if the chain was cut short before entering them.

A more accurate statement is: "`@After` has finally semantics **if Spring has entered its corresponding interceptor**." Not: "`@After` always runs for every exception at any position in the proxy."

## 10. Very Common Log-Reading Mistakes

| Symptom | Correct Understanding | How to Check |
| --- | --- | --- |
| `@After` logs after `@AfterReturning` despite higher precedence | After-finally interceptor wraps completion advice | Distinguish chain precedence from callback event timing |
| `@Around` logs after `@After` | Around advice is unwinding after `proceed()` | Inspect `try/finally` inside `@Around` |
| `@AfterThrowing` does not run when returning `null` | `null` is a normal return | Check whether the method actually throws outward |
| `@AfterThrowing` misses an exception caught by target | Exception did not escape method execution | Record inside target's catch block if needed |
| Two `@Before` methods in the same aspect swap order across environments | Same-type advice ordering is undefined | Merge methods or split into aspects with `@Order` |
| Placed `@Order` on an aspect yet two same-type methods still fluctuate | `@Order` manages precedence between aspects, not same-type methods | Redesign advice organization |
| `@After` does not run when `@Before` throws an exception | Chain never entered the after-finally interceptor | Check which part of the chain ran |
| `@After` does not run when around returns before `proceed` | Inner advisors were never reached | Inspect short-circuit branch |
| Log order differs due to transaction/cache | Infrastructure advisors have their own precedence | Check `Advised.getAdvisors()` and effective order |
| `@AfterThrowing` in the same aspect does not catch an exception thrown by `@AfterReturning` | Advice types apply to the join point, not as a global error handler | Handle errors inside the throwing advice or at an appropriate outer boundary |
| Calling `this.otherMethod()` produces no advice | Self-invocation bypasses the Spring proxy | Extract a bean or call through a proxied dependency |
| Aspect works on one method, not another | Different pointcut/visibility/proxy type | Verify method signature, `final`/`private`, JDK vs. CGLIB |
| `@Aspect` annotation present yet advice does not run | Aspect is not a Spring bean, AOP not enabled, or target bean unproxied | Register `@Bean`/`@Component` and enable `@EnableAspectJAutoProxy` |

## 11. Properly Testing Ordering Within the Same @Aspect

### 11.1. Intentional Testing

In an integration test, record an event list, for example:

```text
around.enter
before
target
afterReturning
after
around.exit
```

Then compare against expected events **on a Spring-managed proxy**. Do not unit test `new WorkService()` directly and expect event entries from `@Aspect` to appear.

In the exception case:

```text
around.enter
before
target.throw
afterThrowing
after
around.catch
around.finally
```

Do not assert relative order between two advice methods of the same type unless you guaranteed it by merging code or splitting aspects.

### 11.2. Is @Order Needed Inside the Same Aspect?

It is not needed to achieve precedence **by advice type** as in section 2. If there is only one `@Around`, one `@Before`, one `@After`, one `@AfterReturning`, and one `@AfterThrowing` matching the join point, Spring applies the advice-type rules. `@Order` only matters when **multiple other aspects/advisors** need relative positioning.

### 11.3. How to Inspect the Advisor Chain

If a bean has a Spring AOP proxy supporting `Advised`, you can diagnose:

```java
import org.springframework.aop.framework.Advised;
import org.springframework.aop.Advisor;

Object bean = context.getBean("workService");

if (bean instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());
    }
}
```

This is a **diagnostic snippet** needing an existing `context` variable, not a standalone file. It shows which advisors are in the chain; infrastructure class names or `toString()` output can depend on the Spring version, so **do not** treat generated class names as a logic contract. For deeper analysis, inspect advisor instances and pointcuts alongside actual event logs.

### 11.4. Test Null, Exceptions, and Side Effects

For real systems, add tests verifying:
- Does `return null` enter `@AfterReturning`?
- Are checked/unchecked exceptions bound by `@AfterThrowing` with the right type?
- Is catching an exception inside the target and returning counted as normal completion?
- Does `@Around` preserve the result/exception when there is no fallback policy?
- When multiple advisors include transaction/cache/retry, is event order accurately described at the observation point?
- When `@Before` throws or `@Around` skips `proceed()`, are inner advice methods skipped as expected?
- When multiple `@Aspect` beans exist, is `@Order` precedence registered properly?

## 12. Version Notes and Guarantee Scope

### 12.1. Spring Framework 5.2.7 and Later

The advice-type precedence rule within a single `@Aspect` has been clearly stated by Spring since version **5.2.7**:

```text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
```

Where `@After` has after-finally semantics, so **its callback runs after completion-specific advice**. If you maintain a very old application, read the Spring reference for that exact version before drawing conclusions about ordering.

### 12.2. Spring Framework 6.x

The project in section 5 uses `spring-context:6.1.14` and `spring-aop:6.1.14`, so it does not rely on Spring Boot defaults. For Spring 6.2 or 7.0, check the matching version's documentation for any edge cases, though the principle of **distinguishing precedence from finally callback timing** is preserved in modern Spring docs.

### 12.3. Spring Boot Does Not Change @After Semantics

Spring Boot can auto-configure Spring AOP when dependencies are present and offers properties affecting proxy type. However, Boot does not turn `@After` into a callback before `@AfterReturning`, nor does it turn source declaration order of advice methods into a guaranteed ordering mechanism.

### 12.4. Difference Between @AspectJ Style and XML AOP

For an `@Aspect` class using annotation style, Spring reference specifies precedence by advice type as above. In **schema-based XML AOP**, ordering advice elements inside an `<aop:aspect>` has its own rule based on **the declaration order of XML elements**. Do not mix the two mechanisms and conclude that because XML has declaration order, Java `@Aspect` methods must also run in source method order.

## 13. Checklist When Building a Multi-Advice @Aspect

- [ ] Use only the advice types genuinely needed for the cross-cutting concern.
- [ ] Know the precedence within an `@Aspect`: `@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`.
- [ ] Remember `@After` runs **after** `@AfterReturning`/`@AfterThrowing` of the same aspect during unwinding.
- [ ] For normal returns—including `null`—use `@AfterReturning`; for escaping exceptions, use `@AfterThrowing`.
- [ ] Do not infer business success solely from `@AfterReturning`.
- [ ] Have `@Around` call `proceed()` when the target and inner chain must run; do not swallow exceptions unless policy requires it.
- [ ] Do not place two advice methods of the same type needing a fixed order in **the same** `@Aspect`; merge them or split aspects.
- [ ] Use `@Order`/`Ordered` when controlling precedence **between** aspects.
- [ ] Distinguish source code order from advisor precedence.
- [ ] Maintain integration tests through the Spring-managed proxy covering normal, null, thrown, and recovered completions.
- [ ] Do not confuse transaction/cache/retry advisors with advice methods in the same `@Aspect`.
- [ ] Test or observe self-invocation, short-circuiting, and exceptions thrown by other advice.
- [ ] Do not alter logic just to "force" logs to match the precedence list; understanding call-stack entry/exit is foundational.

## 14. Conclusion

Within **the same Spring `@Aspect`**, the **precedence** order among advice types from highest to lowest is:

**`@Around` → `@Before` → `@After` → `@AfterReturning` → `@AfterThrowing`.**

Yet when the method finishes, **`@After` executes after `@AfterReturning` or `@AfterThrowing`**, because it is a finally-style advice wrapping the two completion branches. `@Around` can still perform cleanup/catch work after `proceed()` returns. That is why precedence cannot be read as "logs always appear strictly from left to right."

For **two advice methods of the same type within the same `@Aspect`**, ordering is not guaranteed; merge them if an order dependency exists, or split them into `@Aspect` classes with appropriate `@Order` values. Across **different aspects**, consider aspect ordering, other advisors, and call paths through the Spring proxy.

### Official Documentation

- [Spring Framework — Declaring Advice / Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): precedence of advice types in an `@Aspect`, after-finally semantics, undefined same-type order, and `@Order` across aspects.
- [Spring Framework 5.3 — AOP Advice Ordering](https://docs.spring.io/spring-framework/docs/5.3.x/reference/html/core.html): the 5.2.7 clarification milestone and advice-type ordering.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, and `@Around`.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): enabling Spring AOP and registering `@Aspect` as a Spring bean.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxy boundaries and self-invocation.
- [Spring Framework — Schema-based AOP Support](https://docs.spring.io/spring-framework/reference/core/aop/schema.html): note on how `<aop:aspect>` XML advice element ordering differs from annotation-based `@Aspect`.
