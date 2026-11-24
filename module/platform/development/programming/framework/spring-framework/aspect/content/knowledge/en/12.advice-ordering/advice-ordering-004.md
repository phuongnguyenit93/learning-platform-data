# Spring AOP — Way In and Way Out of the Interceptor Chain

## 1. Core Concept: Advice Forms Wrapping Layers Around the Target Method

In **proxy-based Spring AOP**, when a consumer invokes a method on a proxied bean, Spring checks which advisors have matching pointcuts and then executes the chain of interceptors/advice. These handlers are not a flat list executed once from top to bottom. They can form a **nested** structure:

- **Way in (inbound, before proceeding):** starts from the higher-precedence interceptor/advice in the outer layer, proceeds inward to inner interceptors, and finally reaches the target method.
- **Way out (outbound, after proceeding):** when the target returns or throws an exception, control unwinds back out through the inner interceptors and then the outer interceptors. An outer interceptor **completes after** an inner interceptor if it lets execution proceed normally.
- With `@Around`, both directions are clearly visible in the statements **before** and **after** `ProceedingJoinPoint.proceed()`.
- With `@Before`, `@AfterReturning`, `@AfterThrowing`, and `@After`, Spring applies each advice type's specific semantics within the interceptor chain, rather than simply running all `@Before` methods and reversing an arbitrary list.

A visual example:

```text
Caller
  |
  v
@Around A  — in
  |
  +--> @Around B  — in
           |
           +--> Target.work()
           |
           +<-- @Around B  — out
  |
  +<-- @Around A  — out
  |
  v
Caller receives return value
```

**Rule to remember:** *Higher-precedence aspects generally enter first and exit last.* In Spring, if two aspects are configured with `@Order(1)` and `@Order(2)`, the aspect with value `1` has higher precedence. When both use `@Around` and each calls `proceed()` once, the invocation follows the pattern:

```text
A before
B before
target
B after
A after
```

This is the foundational model for understanding Spring AOP advice ordering, logging, metrics, transactions, caching, and exception behavior.

**Scope boundary:** this lesson only covers **Spring Aspect / Spring AOP proxies**, the advisor chain, and how applications observe ordering. It does not describe AspectJ bytecode weaving as an alternative mechanism and does not present AOP at a generic conceptual level.

## 2. Why Does Spring AOP Have an Interceptor Chain?

A Spring-managed bean can be subject to multiple cross-cutting policies. For example, a single service method may have:

- timing advice;
- logging advice;
- pre-invocation validation advice;
- a transaction interceptor;
- advice observing return values or exceptions.

When a consumer calls through a **Spring AOP proxy**, matching advisors are ordered and participate in a single invocation. With wrapping interceptors, an outer layer can run code, pass control to inner layers, and then handle the result or error when the call returns.

```text
Consumer
  |
  v
Spring AOP proxy
  |
  v
Advisor/interceptor #1  [outermost]
  |    enter
  v
Advisor/interceptor #2
  |    enter
  v
Advisor/interceptor #3  [innermost]
  |    enter
  v
Target method execution
  |    return or throw
  ^
Advisor/interceptor #3
  |    exit / finally / error
  ^
Advisor/interceptor #2
  |    exit / finally / error
  ^
Advisor/interceptor #1
  |    exit / finally / error
  ^
Caller
```

In Spring AOP, `MethodInvocation.proceed()` passes execution to **the rest of the chain**, not necessarily jumping straight to the target. Similarly, `ProceedingJoinPoint.proceed()` inside an `@Around` gives inner interceptors and the target a chance to run. When the inner invocation finishes, control returns to the advice that called `proceed()`.

### 2.1. Which Calls Does a Spring AOP Proxy Intercept?

The advice chain is not present in every Java method call:

1. The target is a Spring-managed bean.
2. Spring AOP infrastructure is enabled.
3. Aspects/advisors are registered and pointcuts match the method.
4. The consumer uses **the proxy exposed by Spring**, typically via dependency injection.
5. The method is interceptable by the actual proxy type: JDK proxies rely on public interface methods; CGLIB relies on subclassing/overriding with its own limitations.

When `this.inner()` is called inside the target, the internal call **bypasses the Spring proxy**. It does not initiate a new interceptor chain for `inner()` even if a pointcut matches that method.

### 2.2. "Chain" Does Not Mean "Every Advisor Must Run"

An outer interceptor can **omit calling `proceed()`** or throw an exception early. In that case, inner interceptors and the target do not run along the normal path. An outer `@Around` can also catch an exception, return a fallback, and make the caller see success. Therefore, the full bidirectional reversal diagram only applies when each layer actually lets execution proceed.

## 3. `@Around` Is the Most Direct Way to Observe Both Directions

Two independent advice classes:

```java
@Aspect
@Component
@Order(1)
public class OuterAspect {
    @Around("execution(* demo.chain.WorkService.work(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[outer] enter");
        Object result = pjp.proceed();
        System.out.println("[outer] exit");
        return result;
    }
}
```

```java
@Aspect
@Component
@Order(2)
public class InnerAspect {
    @Around("execution(* demo.chain.WorkService.work(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[inner] enter");
        Object result = pjp.proceed();
        System.out.println("[inner] exit");
        return result;
    }
}
```

These are **two fragments**, requiring imports, a target, Spring config, and separate files. If `work()` completes normally, the trace is:

```text
[outer] enter
[inner] enter
[target] work
[inner] exit
[outer] exit
```

Not:

```text
[outer] enter
[inner] enter
[target] work
[outer] exit
[inner] exit
```

The reason lies in the call stack: `OuterAspect.trace()` **has not finished** when it calls `pjp.proceed()`; it is waiting for everything inside, including `InnerAspect.trace()`, to return control. Only after the inner advice returns does the outer advice print `exit`.

### 3.1. What Does `proceed()` Return?

In Spring AOP, `ProceedingJoinPoint.proceed()` returns an `Object` representing the result of **the rest of the chain**, which is not necessarily the raw result from the target if an inner interceptor intentionally transforms the return value.

```java
@Around("execution(* demo.chain.WorkService.work(..))")
public Object preserveResult(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    return result;
}
```

If you only want to log or measure, you must pass **the exact result** back out. If the target method returns `int`, `Object` may hold a boxed `Integer`; returning `null` can break the contract. If the target method returns `String`, having advice replace `String` with another type can cause a runtime error.

### 3.2. `try/finally` vs. Code Placed Only After `proceed()`

```java
@Around("execution(* demo.chain.WorkService.work(..))")
public Object traceFinally(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("[trace] enter");
    try {
        return pjp.proceed();
    } finally {
        System.out.println("[trace] finally");
    }
}
```

For both success and exception, `finally` **always** runs as the stack unwinds, barring abnormal situations like JVM/process termination. If instead you write:

```java
Object result = pjp.proceed();
System.out.println("[trace] exit");
return result;
```

the `exit` line only runs when `proceed()` completes normally. If `proceed()` throws an exception, Java skips subsequent statements unless caught or placed in `finally`.

**Do not write `return` inside `finally`**: it can overwrite the return value and swallow exceptions from the inner chain. When cleanup itself might throw, design it so cleanup errors do not accidentally mask the original business exception.

### 3.3. When Inner Around Advice Returns a Fallback

Suppose `InnerAspect` catches an `IllegalStateException` and returns `"FALLBACK"`, while `OuterAspect` only inspects the result after `proceed()`:

```text
outer enter
inner enter
target throws
inner catches and returns FALLBACK
outer receives FALLBACK
outer exit
caller receives FALLBACK
```

To the outer interceptor, the inner chain completed **normally** because inner recovered. You cannot say "the target threw so every outer `@AfterThrowing` is guaranteed to run": it also depends on the **position** of the observer relative to the interceptor performing recovery.

## 4. Aspect Precedence in Spring

Spring AOP follows precedence rules for advice applying to the same join point:

- Across **different aspects**, if precedence is not configured, ordering is not guaranteed. Do not guess based on class names, bean scan order, source file, or method names.
- Place `@Order(n)` on the aspect class or implement `org.springframework.core.Ordered` to set precedence.
- **Smaller order number = higher precedence**.
- On the **way in**, higher-precedence aspects run first.
- On the **way out**, higher-precedence aspects run last, because they are the outer layers.

Example:

```java
@Aspect
@Component
@Order(10)
public class AuditAspect {
    @Around("execution(* demo.chain.WorkService.work(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("audit-in");
        Object result = pjp.proceed();
        System.out.println("audit-out");
        return result;
    }
}
```

```java
@Aspect
@Component
@Order(20)
public class MetricsAspect {
    @Around("execution(* demo.chain.WorkService.work(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("metrics-in");
        Object result = pjp.proceed();
        System.out.println("metrics-out");
        return result;
    }
}
```

These are illustrative fragments. On a successful invocation:

```text
audit-in
metrics-in
target
metrics-out
audit-out
```

**Changing `@Order(10)` to `@Order(30)`** can move the aspect to an inner layer if other advisors keep their existing orders. This changes the observation point for timing, return values, and exceptions.

### `@Order` Is Not Bean Initialization Order

`@Order` here represents priority in advisor/aspect ordering; it does not mean constructors, `@PostConstruct`, scheduled tasks, or HTTP filters always run in that same order. Bean lifecycle order and Spring AOP invocation order are two separate concerns.

## 5. Which Direction Does Each Advice Type Appear In?

Not every advice type has both an "enter" and an "exit" in the same method:

| Spring Advice Type | Observation Position | Execution Condition |
| --- | --- | --- |
| `@Around` | Has parts before and after `proceed()` if authored that way | Depends on pointcut and how advice controls `proceed()` |
| `@Before` | Before target method execution | Call matching pointcut enters that branch of the chain |
| `@AfterReturning` | **Success** exit path | Associated method execution completes normally and return binding matches |
| `@AfterThrowing` | **Failure** exit path | Associated execution terminates abnormally with a matching exception type |
| `@After` | When leaving the join point with **finally** semantics | Runs on both success and error in the corresponding chain |

Thus, the exit path **does not always have just one `@After`**. If the target succeeds, `@AfterReturning` advice can run; if the target throws, `@AfterThrowing` advice can run; `@After` applies with finally semantics.

### 5.1. `@Before` Cannot Replace the Return Value

A `@Before` runs on the way in. It can inspect input arguments via `JoinPoint` and throw an exception when needed to block the call. However, it has no `ProceedingJoinPoint.proceed()` and cannot return a replacement value for the target. If `@Before` throws an exception, inner components may not have run yet, while outer interceptors can catch the error if designed to do so.

### 5.2. `@AfterReturning` and `@AfterThrowing` Are Mutually Exclusive for the Same Completion

For an execution that completes normally, the associated `@AfterReturning` can receive the return value. For an execution that throws an exception, the associated `@AfterThrowing` can receive the exception. Do not treat them as two sequential callbacks that always run together for one execution.

If the target catches its own exception and returns normally, an observer at the proxy boundary sees a **normal return**, not a target-thrown exception. If an inner `@Around` recovers before an outer advisor observes the error, the outer advisor may likewise only see a normal return. Analysis must consider chain position.

### 5.3. `@After` Is Finally, Not After-Returning

An `@After` is designed for finally-style cleanup logic; it runs whether the advised method returns or throws. Do not use `@After` assuming the target returned successfully. If you need the return value, use `@AfterReturning(returning="value")` or `@Around`.

### 5.4. Interaction When Multiple Advice Methods Live in the **Same @Aspect Class**

Spring Framework documentation states that advice types of a single `@Aspect` have their own precedence order when applying to the same join point: `@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`. However, this is **not a linear execution timeline**. Since Spring Framework 5.2.7, `@After` follows **finally semantics** and within the same aspect actually runs **after `@AfterReturning` or `@AfterThrowing`**.

Therefore, for an aspect containing `@Before`, `@AfterReturning`, `@AfterThrowing`, and `@After`, you can observe:

```text
Success:
before
target returns
afterReturning
after (finally)

Failure:
before
target throws
afterThrowing
after (finally)
```

The complete example in section 8 uses Spring Framework 6.2.x to demonstrate this exact behavior. For multiple advice methods **of the same type in the same aspect**, relative order must not be inferred from Java source declaration order because reflection does not guarantee source declaration order. When ordering is mandatory, split into separate ordered aspects or consolidate the logic.

## 6. Reading Order by Call Stack Rather Than Just Annotation Names

An invocation with three `@Around` layers:

```text
A.enter
  B.enter
    C.enter
      target()
    C.exit
  B.exit
A.exit
```

**If the target returns:** it unwinds from C, then B, then A. Nothing "runs backward" at the Java VM level; stack frames simply return according to nested function calls.

**If the target throws:**

```text
A.enter
  B.enter
    C.enter
      target throws
    C.catch/finally
  B.catch/finally
A.catch/finally
caller catches
```

If advice methods only place `println("exit")` **after** `proceed()` without catch/finally, those exit lines **do not appear** on the exception path.

**If B does not call `proceed()`:**

```text
A.enter
  B.enter
  B.return cached-value
A.exit with cached-value
caller sees cached-value
```

C and the target do not run. Any `@Before` / `@After` inside B also do not run because execution never enters their scope.

**If B calls `proceed()` twice:** C and the target can run twice, doubling side effects. Retries must be designed deliberately, controlling idempotency, backoff, and transaction scope.

### Distinguishing Method Return from Final Caller-Visible Result

Outer advice receives the result of the **inner chain**, which may be:

- the value returned directly by the target;
- a result transformed by an inner advice method;
- a cached value when inner advice skips the target;
- a fallback when inner advice catches an exception.

Therefore, measuring/logging the "raw target execution result" vs. measuring/logging the "final request result across the AOP proxy" may require **two different aspect positions**.

## 7. How Ordering Affects Spring Transactions, Caching, and Monitoring

### 7.1. Logging vs. Transaction Boundary

Spring `@Transactional` is typically implemented via a transaction advisor/interceptor that also participates in the method invocation pipeline. A logging `@Around` **outside** the transaction interceptor:

```text
logging enter
  transaction begin
    target method
  transaction commit / rollback
logging exit / catch
```

Whereas if the logging interceptor sits **inside** the transaction:

```text
transaction begin
  logging enter
    target method
  logging exit / catch
transaction commit / rollback
```

The two placements yield different durations and transaction state visibility. In practice, this also depends on the transaction manager, advisor ordering, AOP configuration, and other interceptors. **Do not** assume a transaction is open merely because `@Around` and `@Transactional` coexist.

### 7.2. Retry and Transaction

If retry advice sits **outside** transaction advice, each `proceed()` call can start a new transaction (depending on propagation settings). If the transaction wraps **outside** retry, multiple attempts may share one transaction boundary, with different consequences for rollback-only state and lock lifetime. This is a key reason to control order explicitly; do not arbitrarily tweak `@Order` to "fix" log order and accidentally change transaction behavior.

### 7.3. Cache and Timing

A caching interceptor sitting outside metrics advice can return a cache hit **before entering** the metrics/target portion. Inner metrics then do not observe cache hits. If metrics sit outside cache, they observe cache hits as well, though measured duration includes the cache lookup. Choose order based on your observability goal.

### 7.4. Security and Authorization

If an access check lives in an inner advice, an outer interceptor could return early without calling `proceed()`, preventing the inner check from running. Do not design application security assuming "the aspect always runs" if proxy bypass or outer short-circuiting is possible. Use proper Spring Security boundaries and verify the actual chain.

## 8. Java 17 Spring Framework 6.2 Maven Example — Seeing Both Directions Clearly

A complete example running on **plain Spring Framework** without Boot. We have:

- `OuterAspect`: `@Around`, `@Order(1)`, outermost.
- `InnerAspect`: `@Around`, `@Order(2)`, inside Outer.
- `EventAspect`: `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, `@Order(3)`. Four advice methods **of different types** in the same aspect to demonstrate Spring 6.2 semantics.
- `WorkService`: `work("OK")` returns normally, `work("FAIL")` throws `IllegalStateException`. `batch()` calls `this.work("INNER")`, so the internal call does not create a new interceptor chain.

The pointcuts of all three aspects **only** match `WorkService.work(..)`, not `batch()`. Every printed log is deterministic in order and does not depend on ordering among multiple advice methods of the same type.

### 8.1. File Structure

```text
spring-aop-chain-order/
├── pom.xml
└── src/main/java/demo/chain/
    ├── AppConfig.java
    ├── WorkPort.java
    ├── WorkService.java
    ├── OuterAspect.java
    ├── InnerAspect.java
    ├── EventAspect.java
    └── Main.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-chain-order</artifactId>
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

These dependencies provide Spring IoC, AOP proxies, and `@AspectJ` pointcut parsing. You do not need to enable AspectJ compile-time weaving or load-time weaving to run the example.

### 8.3. `AppConfig.java`

```java
package demo.chain;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@ComponentScan` registers the service and aspects annotated with `@Component`. `@EnableAspectJAutoProxy` enables Spring AOP auto-proxying. Because the target implements an interface and `proxyTargetClass=false`, the bean exposed by Spring in this example will be a **JDK dynamic proxy**.

### 8.4. `WorkPort.java`

```java
package demo.chain;

public interface WorkPort {
    String work(String input);
    void batch();
}
```

Consumers must inject/look up `WorkPort`, rather than casting the JDK proxy to concrete `WorkService`.

### 8.5. `WorkService.java`

```java
package demo.chain;

import org.springframework.stereotype.Service;

@Service
public class WorkService implements WorkPort {
    @Override
    public String work(String input) {
        System.out.println("[target] work " + input);
        if ("FAIL".equals(input)) {
            throw new IllegalStateException("boom");
        }
        return "DONE-" + input;
    }

    @Override
    public void batch() {
        System.out.println("[target] batch");
        this.work("INNER"); // Does not go through the Spring AOP proxy.
    }
}
```

`work("OK")` prints a line and returns `"DONE-OK"`. `work("FAIL")` prints the target line and then throws an exception with message `"boom"`. `batch()` calls `work("INNER")` from the target itself, so that call bypasses advice.

### 8.6. `OuterAspect.java` — Outer Layer `@Order(1)`

```java
package demo.chain;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(1)
public class OuterAspect {
    @Around("execution(* demo.chain.WorkService.work(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[outer] in");
        try {
            Object result = pjp.proceed();
            System.out.println("[outer] out " + result);
            return result;
        } catch (Throwable ex) {
            System.out.println("[outer] caught " + ex.getMessage());
            throw ex;
        }
    }
}
```

On the success path, outer advice prints `out` after the **entire** inner chain completes. On the error path, outer catches the exception thrown from inside, prints `caught`, and **rethrows** so the caller still receives the error. It does not recover on its own.

### 8.7. `InnerAspect.java` — Inner Layer `@Order(2)`

```java
package demo.chain;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(2)
public class InnerAspect {
    @Around("execution(* demo.chain.WorkService.work(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[inner] in");
        try {
            Object result = pjp.proceed();
            System.out.println("[inner] out " + result);
            return result;
        } catch (Throwable ex) {
            System.out.println("[inner] caught " + ex.getMessage());
            throw ex;
        }
    }
}
```

Both aspects call `proceed()` **exactly once** per invocation and pass the return value or exception outward. Because `@Order(2)` has lower precedence than `@Order(1)`, `InnerAspect` enters after Outer and exits before Outer.

### 8.8. `EventAspect.java` — Advice Grouped by Outcome

```java
package demo.chain;

import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(3)
public class EventAspect {
    @Before("execution(* demo.chain.WorkService.work(..))")
    public void beforeWork() {
        System.out.println("[event] before");
    }

    @AfterReturning(
        pointcut = "execution(* demo.chain.WorkService.work(..))",
        returning = "result"
    )
    public void returned(String result) {
        System.out.println("[event] afterReturning " + result);
    }

    @AfterThrowing(
        pointcut = "execution(* demo.chain.WorkService.work(..))",
        throwing = "ex"
    )
    public void failed(IllegalStateException ex) {
        System.out.println("[event] afterThrowing " + ex.getMessage());
    }

    @After("execution(* demo.chain.WorkService.work(..))")
    public void afterWork() {
        System.out.println("[event] after finally");
    }
}
```

Advice types and their roles:

- `@Before` prints on the way in, right before the next part of execution.
- `@AfterReturning` receives `String result` when `work(..)` returns normally.
- `@AfterThrowing` receives `IllegalStateException` when `work(..)` throws a matching exception.
- `@After` runs with finally semantics for both paths, and with Spring 6.2 in **this same aspect** is actually invoked **after the corresponding afterReturning/afterThrowing**.

Note that `@Order(3)` controls precedence **relative to other aspects**. Advice invocations inside a single `@Aspect` class also follow Spring's advice-type rules, not file declaration order.

### 8.9. `Main.java`

```java
package demo.chain;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            WorkPort service = context.getBean(WorkPort.class);
            System.out.println("jdkProxy=" + AopUtils.isJdkDynamicProxy(service));

            System.out.println("[caller] begin OK");
            String result = service.work("OK");
            System.out.println("[caller] result " + result);

            System.out.println("[caller] begin FAIL");
            try {
                service.work("FAIL");
            } catch (IllegalStateException ex) {
                System.out.println("[caller] caught " + ex.getMessage());
            }

            System.out.println("[caller] begin batch");
            service.batch();
        }
    }
}
```

Compile and run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.chain.Main
```

**Expected stdout from `System.out` in the program**, excluding any environmental build/framework logs:

```text
jdkProxy=true
[caller] begin OK
[outer] in
[inner] in
[event] before
[target] work OK
[event] afterReturning DONE-OK
[event] after finally
[inner] out DONE-OK
[outer] out DONE-OK
[caller] result DONE-OK
[caller] begin FAIL
[outer] in
[inner] in
[event] before
[target] work FAIL
[event] afterThrowing boom
[event] after finally
[inner] caught boom
[outer] caught boom
[caller] caught boom
[caller] begin batch
[target] batch
[target] work INNER
```

### 8.10. Explaining the Order of the OK Branch

1. `Main` calls `service.work("OK")` on the Spring-managed JDK proxy.
2. Highest-precedence aspect `@Order(1)` starts: `[outer] in`.
3. Outer calls `proceed()` and enters `@Order(2)`: `[inner] in`.
4. Inner calls `proceed()` and enters the advice in `EventAspect @Order(3)`: `[event] before`.
5. Target `WorkService.work("OK")` prints `[target] work OK` and returns `"DONE-OK"`.
6. `@AfterReturning` observes normal completion: `afterReturning DONE-OK`.
7. `@After` in the same aspect runs with finally semantics afterward: `after finally`.
8. Control returns to Inner, which prints `[inner] out DONE-OK` and returns the result.
9. Control returns to Outer, which prints `[outer] out DONE-OK` and returns the result.
10. Caller receives `"DONE-OK"` and prints `[caller] result DONE-OK`.

**Lesson:** the way in flows Outer → Inner → Event → target; the way out flows target → Event outcome/finally → Inner → Outer.

### 8.11. Explaining the Order of the FAIL Branch

1. Outer in → Inner in → Event before → target, same as the OK branch.
2. Target prints `[target] work FAIL` and throws `IllegalStateException("boom")`.
3. `@AfterReturning` **does not run**, because the method did not return normally.
4. `@AfterThrowing` matches `IllegalStateException` and prints `afterThrowing boom`.
5. `@After` in the same aspect runs finally and prints `after finally`.
6. The exception continues out to Inner; Inner's catch block prints `caught boom` and rethrows.
7. The exception continues out to Outer; Outer's catch prints `caught boom` and rethrows.
8. Caller catches and prints `[caller] caught boom`.

If Inner or Outer **did not catch** and only placed logging after `proceed()`, the corresponding `out` lines would not appear. If an advice throws a new exception, outer layers may see a different error type; if an advice catches and returns a fallback, outer layers may see a normal return.

### 8.12. Explaining Self-Invocation in `batch`

`batch()` does not match the aspects' pointcuts and is called through the proxy, so `Main` prints `[caller] begin batch` and then the target prints `[target] batch`. Inside the target, `this.work("INNER")` does not pass back through the proxy; it only prints `[target] work INNER`.

Consequently, there are no `[outer] in`, `[inner] in`, or `[event] before` lines for `INNER`. **Switching from JDK proxy to CGLIB does not fix self-invocation by itself**.

## 9. Experimenting with Order Changes and Outcomes

### 9.1. Swapping Outer and Inner Orders

If swapped to `OuterAspect @Order(2)` and `InnerAspect @Order(1)`, with both `@Around` aspects still registered as in the example, the success-path order will look like:

```text
[inner] in
[outer] in
[event] before
[target] work OK
[event] afterReturning DONE-OK
[event] after finally
[outer] out DONE-OK
[inner] out DONE-OK
```

Neither target logic nor pointcuts changed, yet logging order **in both directions** flips accordingly.

### 9.2. Omitting `proceed()` in Inner

Suppose Inner is changed to:

```java
@Around("execution(* demo.chain.WorkService.work(..))")
public Object cached(ProceedingJoinPoint pjp) {
    System.out.println("[inner] cached");
    return "CACHED";
}
```

This is a **replacement fragment**, not code to run alongside the old Inner body. Outer calls `proceed()` and enters Inner; Inner immediately returns `"CACHED"`, so Event and the target do not run:

```text
[outer] in
[inner] cached
[outer] out CACHED
```

This is valid for the return type because `work()` returns `String`, though it could be wrong in business terms if the real method needs side effects. If applied to a method returning `int`, returning the wrong type causes a runtime error. Do not short-circuit arbitrarily.

### 9.3. Inner Catches the Error and Recovers

If Inner uses:

```java
try {
    return pjp.proceed();
} catch (IllegalStateException ex) {
    System.out.println("[inner] recovered");
    return "FALLBACK";
}
```

this is a **fragment replacing the try/catch section in Inner**. When the target throws, `EventAspect @AfterThrowing` (sitting inside Inner) can log the exceptional exit, and then Inner catches and returns success. Outer now **sees success** and prints `out FALLBACK`; the caller receives `"FALLBACK"`. Not every outer advisor sees an exception once an inner layer has handled it.

### 9.4. `@After` Cleanup Fails

If `@After` throws its own exception, that exception can alter the outcome the caller sees and mask the earlier error. Do not let logging or cleanup in a finally advice throw casually unless the contract requires it and has an explicit exception design. Another `@AfterThrowing` in the same aspect is not a reliable "global catch" for exceptions thrown by `@After`.

### 9.5. Adding Two `@Before` Methods in the Same Aspect

If `EventAspect` has two different `@Before` methods both matching `work()`, you should not rely on the declaration order of those two methods in the Java class to predict log lines. Spring does not guarantee source declaration ordering via reflection. Merge them into a single advice in the desired sequence or split them into two aspects with different `@Order` values.

## 10. Limitations When Inferring Order from Logs

### 10.1. Multiple Proxy Layers

A Spring bean can participate in multiple proxy/advisor mechanisms. There may be nested proxies in specially configured applications, scoped bean proxies, or interceptors from other modules. When logs interleave differently from the example, verify the **exact proxy reference**, advisor chain, scope, and proxy type. Do not conclude "Spring ignored `@Order`" merely because another interceptor sits outside.

### 10.2. Asynchronous Execution and Thread Switching

If a method returns a `CompletableFuture<T>`, a reactive publisher, or runs via `@Async`, the Spring AOP proxy can return a wrapper before the async work finishes. An `@AfterReturning` at the method-execution boundary does not automatically mean "business logic finished," and log order across threads does not reflect a single call stack like the synchronous example.

If you care about future or publisher completion, use appropriate completion/error operators and context propagation. Do not use a linear synchronous chain model to deduce timelines for async operations.

### 10.3. Transaction Rollback Even When Outer Advice Returns a Fallback

If a transaction interceptor sits inside Outer, and the target method throws causing it to mark rollback before Outer catches and returns `"FALLBACK"`, Outer returning success **does not automatically undo the rollback**. Whether the transaction commits depends on boundaries, propagation, rules, and rollback-only status.

### 10.4. Same-Class Advice Precedence Differs from Inter-Aspect Order

Inside one `@Aspect` class, there is precedence logic by advice type, and notably `@After` follows finally semantics. Across **different aspect classes**, `@Order` defines ordering between aspects. Do not translate "`@Before` runs before `@After`" directly into ordering between two aspects when each aspect has different advice types—you must examine **outer/inner wrapping order** first.

### 10.5. Bean Initialization Is Not an Intercepted Business Invocation

Constructors, `@PostConstruct`, and normal lifecycle callbacks occur during target initialization before the application uses the completed proxy. Do not expect `@Order` on aspects to govern constructor order or run advice on every startup callback.

## 11. Checklist for Diagnosing Spring Aspect Ordering

| Symptom | Possible Cause | How to Check / Fix |
| --- | --- | --- |
| Outer prints `in` before Inner but `out` after Inner | Correct nested interceptor semantics | Read `proceed()` as a nested call |
| Log only shows `in` when target throws | `out` code placed after `proceed()` without catch/finally | Use `try/finally` for cleanup/logging needed even on errors |
| `@AfterReturning` does not run on error | Target/inner interceptor ended with an exception | Use `@AfterThrowing` for errors or `@After` for finally |
| `@AfterThrowing` does not run when fallback is returned | Exception was already handled by inner advice before observer saw it | Check advisor order and actual outcome at the observer |
| `@After` runs after `@AfterReturning` in the same aspect | Spring 5.2.7+ finally semantics | This is intended behavior, not accidental |
| `@Order(1)` measures longer duration than `@Order(2)` | Outer aspect measures the entire inner chain | Place metrics layer according to what you want to measure |
| Changing `@Order` leaves target logs unchanged | Target logic is independent; aspect ordering changed | Compare enter/exit/finally logs |
| Aspects without `@Order` run nondeterministically | Spring does not guarantee inter-aspect ordering | Set `@Order` if order is a requirement |
| Two `@Before` methods in the same aspect lack expected order | Java reflection does not guarantee declaration order | Merge logic or split aspects/classes |
| Target is called twice | An around advice calls `proceed()` multiple times | Review retry policy and idempotency |
| Target is not called | Outer advice short-circuited or threw before `proceed()` | Inspect cache/security/validation chain |
| `this.inner()` produces no advice logs | Self-invocation bypasses proxy | Extract into another Spring bean if separate policy is needed |
| Order changes when transactions are present | Other transaction/cache/security advisors exist | Inspect actual advisor chain and precedence |
| Code outside Spring produces no aspect logs | Object is not a Spring-managed proxy | Inject the bean through the context |
| JDK proxy does not advise a method | Method is not exposed on the interface | Use an appropriate interface API or adjust proxy configuration thoughtfully |
| CGLIB does not advise a `final` method | Cannot be overridden | Adjust method/bean boundary or use a suitable JDK interface proxy |

**Verification workflow:**

1. Confirm the target and aspects are Spring beans; AOP infrastructure is enabled.
2. Check `AopUtils.isAopProxy(bean)`, `isJdkDynamicProxy(...)`, or `isCglibProxy(...)` on the actual reference.
3. Verify the pointcut matches the method and the caller goes through the proxy.
4. List which aspects apply, whether they have `@Order` or `Ordered`, and whether multiple advice methods of the same type exist in one aspect.
5. Follow `proceed()` in each around advice: which layer logs `enter`, which catches/runs `finally`, and what result is returned.
6. Test both the success case and exception case; do not look at only one direction of the logs.
7. Check whether infrastructure interceptors such as transaction, cache, security, or async affect the order.
8. Use integration tests on a real Spring context when ordering affects business or transaction semantics.

## 12. Self-Check Questions

**1. `@Order(1)` and `@Order(2)` are both `@Around`—which enters first?** The one with `1`, because its precedence is higher. If both proceed and return normally, aspect `1` exits after aspect `2`.

**2. Does calling `pjp.proceed()` mean jumping straight to the target?** Not necessarily. It invokes the rest of the Spring AOP interceptor chain, which may contain other advice before reaching the target.

**3. Why does `println("after")` placed after `proceed()` not print when the target throws?** Because the exception skips statements after `proceed()`, unless handled via catch/finally.

**4. Is `@After` equivalent to `@AfterReturning`?** No. `@After` has finally semantics, applying to both normal and exceptional exits; `@AfterReturning` is only for normal completion.

**5. Within the same Spring `@Aspect`, can `@After` run after `@AfterThrowing`?** Yes. Spring Framework 5.2.7+ applies finally semantics, and this behavior is confirmed in the official documentation.

**6. If `InnerAspect` catches an exception and returns a fallback, does `OuterAspect` catch the original exception?** Usually no, if the fallback returns normally before reaching Outer; Outer sees the result of the inner chain.

**7. If around advice does not call `proceed()`, do inner advice methods run?** Not along that invocation path; the target can also be skipped.

**8. Does `@Order` control Java constructor order?** No. It sets precedence for the applicable ordering mechanism, not an application-wide initialization schedule.

**9. Why does `this.work()` not run the interceptor chain despite a matching pointcut?** Because self-invocation calls the target directly, bypassing the Spring AOP proxy.

**10. To measure duration including transaction commit/rollback, where should the metrics aspect sit?** Usually metrics must sit outside the transaction interceptor, though you must verify actual advisor ordering and transaction configuration.

## Official Spring Framework References

- [Spring Framework — Declaring Advice: Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Advice Ordering, @After finally semantics](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework — AOP Advice API / MethodInterceptor.proceed()](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html)
- [Spring Framework — Proxying Mechanisms, JDK/CGLIB/self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — @AspectJ support, enabling Spring AOP](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework — Declarative transaction rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
