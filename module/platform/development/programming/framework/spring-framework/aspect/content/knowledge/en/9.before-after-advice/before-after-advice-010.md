# Examples of Tracing Spring Bean Calls with Each Advice Type

## 1. Lesson Objectives

In Spring Framework, an `@Aspect` can declare advices to **record method calls on a Spring bean** at multiple points: before the call, when returning successfully, when throwing an exception, when finishing regardless of outcome, and surrounding the entire execution. The corresponding types are:

- `@Before` — before method execution.
- `@AfterReturning` — when method execution completes normally.
- `@AfterThrowing` — when method execution exits with a matching exception.
- `@After` — after method execution with *finally* semantics.
- `@Around` — surrounds method execution; can decide whether to proceed via `ProceedingJoinPoint.proceed()`.

This lesson focuses on **how to use all five advice types in Spring AOP**, Spring-managed beans, applicable pointcuts, and observable logs. It does not revisit general Aspect theory or AspectJ weaving outside Spring.

**First key point:** Spring AOP is a **proxy-based** mechanism. Every trace in this lesson is produced when a client calls a method **on a Spring bean proxy**, not when calling an object instantiated manually with `new` outside the container.

## 2. How Does a Call Through a Spring AOP Proxy Proceed?

```text
Client
  |
  | calls method on bean obtained from ApplicationContext
  v
Spring AOP proxy
  |
  | selects advisors/interceptors whose pointcut matches the method
  v
Advice chain
  |
  | runs BEFORE/AROUND entry-side logic
  v
Target.method()
  |
  | normal return or exception
  v
Advice chain
  |
  | corresponding AFTER_RETURNING / AFTER_THROWING / AFTER / AROUND
  v
Client receives result or exception
```

In Spring, an `@Aspect` class must be **registered as a Spring bean** for its advices to be recognized (for example, `@Component` scanned or `@Bean` in configuration). In plain Spring Framework, `@AspectJ` processing can be enabled with `@EnableAspectJAutoProxy`.

When an aspect has a pointcut:

```java
@Before("execution(* demo.service..*.*(..))")
public void beforeAnyServiceCall() {
    System.out.println("BEFORE service");
}
```

Spring does not weave code into every class at compile time. It creates proxies for target beans that have matching advisors; **calls passing through the proxy** are what trigger the advice. The snippet above is only a method to be placed inside a Spring-managed `@Aspect` bean, not a standalone Java program.

### Five Advice Types in One Table

| Advice Type | Recognized Event | Can Observe | Allowed to Call `proceed()`? |
| --- | --- | --- | --- |
| `@Before` | Before target method | Join point signature, arguments, proxy/target | No |
| `@AfterReturning` | Method returns normally | Return value via `returning` | No |
| `@AfterThrowing` | Method throws a matching exception | Throwable via `throwing` | No |
| `@After` | After method, whether success or failure | Cleanup / completion logging | No |
| `@Around` | Surrounds the entire remaining execution | Before, after, return, or exception | **Yes**, via `ProceedingJoinPoint` |

**Choose the simplest advice type that meets the goal.** If you only need to print one line before a method, prefer `@Before` over `@Around`, because an around advice can accidentally block the call if you forget `proceed()`.

## 3. Example 1 — Tracing Before the Call with `@Before`

A `@Before` advice runs **before the selected method executes**.

```java
@Aspect
public class CallTraceAspect {
    @Before("execution(* demo..*.beforeCase(..))")
    public void beforeCall(JoinPoint jp) {
        System.out.println("BEFORE " + jp.getSignature().getName());
    }
}
```

In this illustration, `JoinPoint.getSignature().getName()` gives the method name at the join point; you can call `jp.getArgs()` to inspect arguments when needed.

**Success path example:**

```text
BEFORE beforeCase
TARGET beforeCase false
CLIENT value=BEFORE-OK
```

**Failure path example:**

```text
BEFORE beforeCase
TARGET beforeCase true
CLIENT caught IllegalStateException:before failed
```

Points to remember:

1. `@Before` runs before the target **on both the success branch and failure branch**, provided the call went through the proxy and matched the pointcut.
2. The advice can throw an exception to stop the call, yet it does not use `proceed()` to control the rest of the execution like `@Around`.
3. If the target calls `this.beforeCase(...)` internally, that call does not re-enter the proxy; thus there is no new `@Before` invocation for that internal call alone.
4. When logging arguments, avoid writing passwords, access tokens, or sensitive data to logs.

The short code blocks in each section are **illustrative snippets**, while the complete runnable Maven example is in section 8.

## 4. Example 2 — Recording Only on Success with `@AfterReturning`

`@AfterReturning` runs when a **method execution completes normally**, including when the method returns `null` (with a compatible binding), rather than inspecting status code names or return values meaning "failure" in business logic.

```java
@AfterReturning(
    pointcut = "execution(* demo..*.successCase(..))",
    returning = "result",
    argNames = "result"
)
public void afterSuccess(String result) {
    System.out.println("AFTER_RETURNING result=" + result);
}
```

Here:

- `pointcut` selects the method execution.
- `returning = "result"` binds the return value to the parameter named `result`.
- The parameter's `String` type also **restricts which return types** can match. To accept broader types, use `Object`.
- `argNames` specifies the binding name explicitly, avoiding reliance on parameter-name inference from bytecode.

**Success branch:**

```text
TARGET successCase false
AFTER_RETURNING result=SUCCESS-OK
CLIENT value=SUCCESS-OK
```

**Throwing branch:**

```text
TARGET successCase true
CLIENT caught IllegalStateException:return failed
```

On the error branch, the `AFTER_RETURNING` line does not appear. A method returning `"FAIL"` without throwing an exception is still a **normal return** and can trigger `@AfterReturning`.

### `@AfterReturning` Is Not for Replacing Return Values

`afterSuccess(...)` is an advice that receives the result, not a factory method replacing the target's result. Returning a new value from this advice **does not change the reference the client receives**. If you need to alter the result (e.g., fallback/cache), use `@Around`.

## 5. Example 3 — Recording Exceptions with `@AfterThrowing`

`@AfterThrowing` runs when a selected execution **exits with an exception**; the `throwing` attribute lets you bind the exception object and restrict which exception types it receives.

```java
@AfterThrowing(
    pointcut = "execution(* demo..*.throwingCase(..))",
    throwing = "error",
    argNames = "error"
)
public void afterInvalid(IllegalArgumentException error) {
    System.out.println(
        "AFTER_THROWING "
            + error.getClass().getSimpleName()
            + ":" + error.getMessage()
    );
}
```

In the example, the advice receives only `IllegalArgumentException` or subclasses, not `IllegalStateException`, even though both are runtime exceptions. If you want to observe all throwable types, you can use `Throwable` (while handling `Error` cases appropriately).

**Matching exception type:**

```text
TARGET throwingCase argument
AFTER_THROWING IllegalArgumentException:bad argument
CLIENT caught IllegalArgumentException:bad argument
```

**Different exception type:**

```text
TARGET throwingCase state
CLIENT caught IllegalStateException:bad state
```

**No exception:**

```text
TARGET throwingCase ok
CLIENT value=THROW-OK
```

Spring calls the advice for matching exceptions; an advice method returning `void` **does not stop the caller from receiving the exception**. `@AfterThrowing` is for logging/metrics, not a mechanism to replace catching/recovering with a new result.

An exception caught internally by the target before returning normally **does not trigger** `@AfterThrowing`, because it never exited the method execution at the Spring AOP boundary.

## 6. Example 4 — Always Recording on Completion with `@After`

`@After` in Spring `@AspectJ` AOP carries **finally advice** semantics: it executes regardless of whether the selected method finishes normally or by throwing an exception.

```java
@After("execution(* demo..*.finallyCase(..))")
public void afterCompletion(JoinPoint jp) {
    System.out.println("AFTER_FINALLY " + jp.getSignature().getName());
}
```

**When returning normally:**

```text
TARGET finallyCase false
AFTER_FINALLY finallyCase
CLIENT value=FINALLY-OK
```

**When throwing an exception:**

```text
TARGET finallyCase true
AFTER_FINALLY finallyCase
CLIENT caught IllegalStateException:finally failed
```

`@After` is well suited for recording "method execution finished," releasing resources under a defined contract, or counting total executions. By default, it **does not indicate whether the outcome was normal or an error**; to handle each branch separately, use `@AfterReturning` / `@AfterThrowing` or `@Around`.

**Unlike `@AfterThrowing`:** `@After` still runs when the target returns normally. **Unlike `@AfterReturning`:** `@After` still runs when the target throws an exception.

## 7. Example 5 — Surrounding and Tracing Both Branches with `@Around`

`@Around` can trace before, trace after, observe values and errors, and control the remaining chain via `ProceedingJoinPoint.proceed()`.

```java
@Around("execution(* demo..*.aroundCase(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("AROUND enter");
    try {
        Object value = pjp.proceed();
        System.out.println("AROUND return " + value);
        return value;
    } catch (Throwable error) {
        System.out.println(
            "AROUND throw " + error.getClass().getSimpleName()
                + ":" + error.getMessage()
        );
        throw error;
    } finally {
        System.out.println("AROUND finally");
    }
}
```

**When the target succeeds:**

```text
AROUND enter
TARGET aroundCase false
AROUND return AROUND-OK
AROUND finally
CLIENT value=AROUND-OK
```

**When the target throws an exception:**

```text
AROUND enter
TARGET aroundCase true
AROUND throw IllegalStateException:around failed
AROUND finally
CLIENT caught IllegalStateException:around failed
```

Key highlights:

- `pjp.proceed()` **continues through the remaining interceptors** in the chain, ultimately reaching the target unless another interceptor short-circuits.
- If you omit `proceed()` and return immediately, inner advisors and the target may **not execute**. This is a major difference from the other advice kinds.
- If `proceed()` is called multiple times, the rest of the chain can execute multiple times. This only fits well-designed cases such as controlled retries; never call it repeatedly for data-writing methods arbitrarily.
- An advice returning `Object` should return the actual result of `proceed()` (or another result if intentional and compatible with the target's signature).
- `catch Throwable` logs both `Exception` and `Error` in the illustration, **and should not swallow fatal errors**; rethrowing preserves the flow unchanged.

If you only need one log line before the method, `@Before` is shorter and safer than `@Around`. Use around only when you genuinely need before/after coordination, return-value replacement, fallback, or a timer with local state.

## 8. Standalone Java 17+ Project — Five Advices with Separate Traces

To avoid guessing execution order when **multiple advice kinds match the same method**, this demo deliberately assigns **each advice type to its own method group**. That way, stdout cleanly demonstrates five independent contracts that are easy to test. The end of the lesson explains how multiple advices interact on the same method in practice.

Environment: **Java 17+, Maven, Spring Framework 6.2.6** with `spring-context`, `spring-aop`, and `aspectjweaver`. Spring beans are registered via `@Bean`, and the aspect uses `@Aspect` and `@EnableAspectJAutoProxy`.

### 8.1. File Structure

```text
spring-advice-tracing/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AdviceTracingDemo.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-advice-tracing</artifactId>
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
                    <mainClass>demo.AdviceTracingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. `src/main/java/demo/AdviceTracingDemo.java`

```java
package demo;

import java.util.function.Supplier;

import org.aspectj.lang.JoinPoint;
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

public class AdviceTracingDemo {

    public interface TaskService {
        String beforeCase(boolean fail);
        String successCase(boolean fail);
        String throwingCase(String kind);
        String finallyCase(boolean fail);
        String aroundCase(boolean fail);
    }

    public static class TaskServiceImpl implements TaskService {

        @Override
        public String beforeCase(boolean fail) {
            System.out.println("TARGET beforeCase " + fail);
            if (fail) {
                throw new IllegalStateException("before failed");
            }
            return "BEFORE-OK";
        }

        @Override
        public String successCase(boolean fail) {
            System.out.println("TARGET successCase " + fail);
            if (fail) {
                throw new IllegalStateException("return failed");
            }
            return "SUCCESS-OK";
        }

        @Override
        public String throwingCase(String kind) {
            System.out.println("TARGET throwingCase " + kind);
            if ("argument".equals(kind)) {
                throw new IllegalArgumentException("bad argument");
            }
            if ("state".equals(kind)) {
                throw new IllegalStateException("bad state");
            }
            return "THROW-OK";
        }

        @Override
        public String finallyCase(boolean fail) {
            System.out.println("TARGET finallyCase " + fail);
            if (fail) {
                throw new IllegalStateException("finally failed");
            }
            return "FINALLY-OK";
        }

        @Override
        public String aroundCase(boolean fail) {
            System.out.println("TARGET aroundCase " + fail);
            if (fail) {
                throw new IllegalStateException("around failed");
            }
            return "AROUND-OK";
        }
    }

    @Aspect
    public static class TraceAspect {

        @Before("execution(* demo..*.beforeCase(..))")
        public void before(JoinPoint jp) {
            System.out.println("BEFORE " + jp.getSignature().getName());
        }

        @AfterReturning(
            pointcut = "execution(* demo..*.successCase(..))",
            returning = "result",
            argNames = "result"
        )
        public void afterReturning(String result) {
            System.out.println("AFTER_RETURNING result=" + result);
        }

        @AfterThrowing(
            pointcut = "execution(* demo..*.throwingCase(..))",
            throwing = "error",
            argNames = "error"
        )
        public void afterThrowing(IllegalArgumentException error) {
            System.out.println(
                "AFTER_THROWING "
                    + error.getClass().getSimpleName()
                    + ":" + error.getMessage()
            );
        }

        @After("execution(* demo..*.finallyCase(..))")
        public void after(JoinPoint jp) {
            System.out.println(
                "AFTER_FINALLY " + jp.getSignature().getName()
            );
        }

        @Around("execution(* demo..*.aroundCase(..))")
        public Object around(ProceedingJoinPoint pjp) throws Throwable {
            System.out.println("AROUND enter");
            try {
                Object value = pjp.proceed();
                System.out.println("AROUND return " + value);
                return value;
            } catch (Throwable error) {
                System.out.println(
                    "AROUND throw "
                        + error.getClass().getSimpleName()
                        + ":" + error.getMessage()
                );
                throw error;
            } finally {
                System.out.println("AROUND finally");
            }
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
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    static void runCase(String label, Supplier<String> action) {
        System.out.println("=== " + label + " ===");
        try {
            System.out.println("CLIENT value=" + action.get());
        } catch (RuntimeException error) {
            System.out.println(
                "CLIENT caught "
                    + error.getClass().getSimpleName()
                    + ":" + error.getMessage()
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
            System.out.println(
                "JDK_PROXY=" + AopUtils.isJdkDynamicProxy(service)
            );

            runCase("BEFORE SUCCESS", () -> service.beforeCase(false));
            runCase("BEFORE FAILURE", () -> service.beforeCase(true));

            runCase("AFTER RETURNING SUCCESS",
                () -> service.successCase(false));
            runCase("AFTER RETURNING FAILURE",
                () -> service.successCase(true));

            runCase("AFTER THROWING INVALID",
                () -> service.throwingCase("argument"));
            runCase("AFTER THROWING STATE",
                () -> service.throwingCase("state"));
            runCase("AFTER THROWING SUCCESS",
                () -> service.throwingCase("ok"));

            runCase("AFTER FINALLY SUCCESS",
                () -> service.finallyCase(false));
            runCase("AFTER FINALLY FAILURE",
                () -> service.finallyCase(true));

            runCase("AROUND SUCCESS", () -> service.aroundCase(false));
            runCase("AROUND FAILURE", () -> service.aroundCase(true));
        }
    }
}
```

### 8.4. Run Command

In the `spring-advice-tracing` directory:

```bash
mvn -q compile exec:java
```

Stdout lines **printed by the program itself**, in expected order (excluding separate messages from Maven or framework logging):

```text
AOP_PROXY=true
JDK_PROXY=true
=== BEFORE SUCCESS ===
BEFORE beforeCase
TARGET beforeCase false
CLIENT value=BEFORE-OK
=== BEFORE FAILURE ===
BEFORE beforeCase
TARGET beforeCase true
CLIENT caught IllegalStateException:before failed
=== AFTER RETURNING SUCCESS ===
TARGET successCase false
AFTER_RETURNING result=SUCCESS-OK
CLIENT value=SUCCESS-OK
=== AFTER RETURNING FAILURE ===
TARGET successCase true
CLIENT caught IllegalStateException:return failed
=== AFTER THROWING INVALID ===
TARGET throwingCase argument
AFTER_THROWING IllegalArgumentException:bad argument
CLIENT caught IllegalArgumentException:bad argument
=== AFTER THROWING STATE ===
TARGET throwingCase state
CLIENT caught IllegalStateException:bad state
=== AFTER THROWING SUCCESS ===
TARGET throwingCase ok
CLIENT value=THROW-OK
=== AFTER FINALLY SUCCESS ===
TARGET finallyCase false
AFTER_FINALLY finallyCase
CLIENT value=FINALLY-OK
=== AFTER FINALLY FAILURE ===
TARGET finallyCase true
AFTER_FINALLY finallyCase
CLIENT caught IllegalStateException:finally failed
=== AROUND SUCCESS ===
AROUND enter
TARGET aroundCase false
AROUND return AROUND-OK
AROUND finally
CLIENT value=AROUND-OK
=== AROUND FAILURE ===
AROUND enter
TARGET aroundCase true
AROUND throw IllegalStateException:around failed
AROUND finally
CLIENT caught IllegalStateException:around failed
```

### 8.5. Why Does the Example Produce These Traces?

1. `Config` registers `TaskServiceImpl` under the `TaskService` interface. `@EnableAspectJAutoProxy(proxyTargetClass=false)` lets Spring use a JDK dynamic proxy when the target implements an interface.
2. `TraceAspect` is a Spring bean and carries `@Aspect`, so Spring discovers all five advice methods.
3. Each service method has a **different name**, and each advice has a pointcut matching only that name. Thus only one advice type applies to each test case, avoiding dependence on arbitrary ordering among advice classes.
4. The caller always retrieves `TaskService` from the context. Calls to `service.beforeCase(...)` and the others all pass through the **Spring proxy**, rather than calling `new TaskServiceImpl()` directly.
5. With `@Before`, the advice always prints before the target when the method matches, even if the target will throw an error.
6. With `@AfterReturning`, if the target throws an exception, no `AFTER_RETURNING` line appears.
7. With `@AfterThrowing(IllegalArgumentException)`, `IllegalStateException` does not satisfy the type constraint and does not run the advice.
8. With `@After`, the advice always prints after the target, on both the success and error paths.
9. With `@Around`, calling `pjp.proceed()` reaches the target; on success it takes the return branch, on error it enters `catch`; `finally` always runs before the client receives the result or error.

**Run note:** this is standalone Maven source code and the expected stdout from the example's logic. If a real project adds other advisors/aspects, different logging, or different proxy settings, traces may include extra lines or change order. Match only against the lines printed by this lesson's program.

## 9. What If You Want All Five Advice Types on the Same Method?

In practice, multiple advice types can apply to the same method, for example:

```java
@Aspect
public class CombinedTraceAspect {
    @Before("execution(* com.example.app.service..*.save(..))")
    public void before() {
        System.out.println("BEFORE");
    }

    @AfterReturning("execution(* com.example.app.service..*.save(..))")
    public void success() {
        System.out.println("RETURNED");
    }

    @AfterThrowing("execution(* com.example.app.service..*.save(..))")
    public void failure() {
        System.out.println("THREW");
    }

    @After("execution(* com.example.app.service..*.save(..))")
    public void after() {
        System.out.println("FINALLY");
    }
}
```

This is an **illustrative snippet** without a `save(..)` service to compile/run standalone. It shows that Spring can attach multiple advices to the same pointcut, though ordering must be understood:

- **Entry path:** advices run by precedence in the interceptor chain; `@Before` executes before the target.
- **Normal exit path:** `@AfterReturning` runs, `@AfterThrowing` does not; `@After` runs with finally semantics.
- **Error exit path:** `@AfterThrowing` runs for matching exceptions, `@AfterReturning` does not; `@After` still runs.
- **Ordering across different aspects:** not guaranteed by default if unconfigured; use `@Order` or `Ordered` to set precedence.
- **Within the same aspect:** Spring defines precedence by advice kind (`@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`); `@After` has finally semantics so in practice it finishes **after** after-returning/after-throwing when those advices apply.
- **Two advices of the same kind in the same aspect:** Java reflection does not guarantee source declaration order; do not use method position in the file to infer order.

If an example requires **strictly deterministic** stdout for a README or test, the approach in section 8 (separate methods) is easier to verify. When you need to observe a real nested chain, assign `@Order` to aspects and write integration tests to verify invocation order.

### Higher Advice Precedence Means Different Entry and Exit Timing

For two `@Around` advices `A` and `B` matching the target, where `A` has higher precedence:

```text
A enter
  B enter
    TARGET
  B exit
A exit
```

Thus "higher precedence" means **entering earlier and exiting later**. Shared pointcuts or alphabetical class naming do not establish precedence automatically.

## 10. Recording Join Point Information Properly

In Spring AOP, an advice can accept `JoinPoint` as its first parameter (`@Around` uses `ProceedingJoinPoint`). Useful details:

```java
@Before("execution(public * com.example.app.service..*.*(..))")
public void log(JoinPoint jp) {
    String method = jp.getSignature().getName();
    Object proxy = jp.getThis();
    Object target = jp.getTarget();
    Object[] arguments = jp.getArgs();

    System.out.println("METHOD " + method);
    System.out.println("PROXY=" + proxy.getClass().getSimpleName());
    System.out.println("TARGET=" + target.getClass().getSimpleName());
    System.out.println("ARG_COUNT=" + arguments.length);
}
```

This is a **snippet**, not a standalone runnable Java file. It can help debugging:

- `jp.getSignature()`: method / join point details.
- `jp.getArgs()`: invocation arguments.
- `jp.getThis()`: Spring AOP proxy object.
- `jp.getTarget()`: target object behind the proxy.

Do not dump all `arguments` into production logs unfiltered. If parameters contain PII, passwords, tokens, file data, or large object graphs, mask/redact them or log only necessary metadata. Calling `toString()` on input objects can also expose sensitive data or trigger unintended side effects.

When logging exceptions, include stack traces when needed for debugging, while avoiding duplicate logging of the same error across layers. A service call traversing multiple proxies/advices can emit multiple log events for one exception.

## 11. Control Experiments on the Project Trace

Try each change independently on the section 8 example, restoring the code before trying the next:

| Change | Observation | Cause |
| --- | --- | --- |
| Remove `@EnableAspectJAutoProxy` in plain Spring Framework | Target logs remain, advice logs disappear | Proxy infrastructure not enabled |
| Stop registering `TraceAspect` as a bean | Aspect logs disappear | `@Aspect` alone does not create a Spring bean |
| Call `new TaskServiceImpl()` outside context | Only target prints | Raw object has no AOP proxy |
| Change `beforeCase` pointcut to another method | `BEFORE` marker disappears from `beforeCase` | Method no longer matches the pointcut |
| Call `this.innerMethod()` inside target | No separate advice execution | Self-invocation bypasses the proxy |
| Make `@Around` return early without `proceed()` | Target does not run | Around short-circuit |

With each test, check three observables: did the target run, which advice logged, and what return/exception did the caller receive. That isolates proxy, pointcut, outcome, and chain order far better than attaching all five advice types to every service method.

When transaction/cache/retry advisors are present, run integration tests on a real `ApplicationContext` and record events with a recorder instead of relying solely on stdout line order.

## 12. Bringing Spring AOP Tracing into Real Systems

### 12.1. Log Minimally Yet Enough to Observe

Typically useful details:

- Method name and a safe operation identifier.
- Outcome classification (success / failure).
- Elapsed duration if measured in `@Around`, without hardcoding expected durations.
- Trace/correlation ID supplied by the request context.
- Exception class (and a filtered or redacted message).

**Do not log raw credentials, tokens, personal data, full request payloads, or secrets** just because `JoinPoint.getArgs()` can access them.

### 12.2. Use a Logger Instead of `System.out` in Production

In demos, `System.out.println` clarifies stdout. In real projects, use SLF4J or your application's configured logging framework:

```java
private static final org.slf4j.Logger log =
        org.slf4j.LoggerFactory.getLogger(TraceAspect.class);

@Before("execution(* com.example.app.service..*.*(..))")
public void logCall(JoinPoint jp) {
    log.debug("Invoking {}", jp.getSignature().toShortString());
}
```

This is an **additional illustrative snippet** requiring the SLF4J dependency, a `TraceAspect` class, and appropriate imports. Prefer structured logging, appropriate log levels, and sampling to avoid overhead from frequently executed advices.

### 12.3. Do Not Infer Rollback from Advice

A `@Transactional` method may have a separate advisor created by the transaction infrastructure. `@AfterThrowing` only observes matching exceptions; it **does not configure rollback**. Whether logging occurs before or after commit/rollback also depends on Spring's advisor ordering.

### 12.4. Watch Out for Async and Completion Signals

With `@Async`, a method may return `CompletableFuture`, `Future`, or execute on another thread. `@AfterReturning` at a proxy boundary may observe the **returned future object**, which does not mean the asynchronous task finished successfully. To record completion timing, observe the completion stage or an appropriate async-specific mechanism.

### 12.5. Use Integration Tests Instead of Only Reading Code

Good tests should:

1. Build a Spring context with real aspect and target beans.
2. Assert `AopUtils.isAopProxy(service)` is `true`.
3. Call through the injected bean reference, not a `new` target object.
4. Test success cases, matching and non-matching exception types, and around return/throw behavior.
5. Use a recorder/spy or controlled log capture to verify **which advices ran**, not just business results.
6. When multiple advices match together, configure explicit ordering and assert the trace matches that order.

## 13. Self-Check

**1.** A method returns `"FAIL"` without throwing an exception; does `@AfterThrowing` run?  
**Answer:** No; the method returned normally. `@AfterReturning` can run.

**2.** Is `@AfterReturning(returning="value")` valid when the advice parameter is named `result`?  
**Answer:** Binding names must match, or compatible configuration/declaration is needed; the simplest way is using the same name `value` in both the attribute and parameter (optionally adding `argNames`).

**3.** Does an `@AfterThrowing` accepting `IllegalArgumentException` run when the target throws `IllegalStateException`?  
**Answer:** No, because there is no matching subtype relationship.

**4.** Does `@After` run when the target throws an exception instead of returning normally?  
**Answer:** Yes, because `@After`'s semantics mirror `finally`.

**5.** Does `@Before` call `proceed()` to continue to the target?  
**Answer:** No. Only `@Around` uses `ProceedingJoinPoint.proceed()`; Spring automatically continues after before advice if the advice does not throw an error.

**6.** In `@Around`, if you omit `proceed()` and return a `String`, what happens?  
**Answer:** It can short-circuit the rest of the chain and the target; the caller receives the advice's returned value if compatible.

**7.** Two aspects match the same method without `@Order`. Should you predict log order from class declaration order in code?  
**Answer:** No. Relative order between aspects must be specified via precedence if it matters.

**8.** The target service calls `this.beforeCase()` inside another method of its own. Will an `@Before` advice matching only `beforeCase()` run again?  
**Answer:** There is no new proxy entry, so Spring AOP does not intercept that internal call.

**9.** An `@Around` catches an exception and returns a fallback. Is an outer `@AfterThrowing` guaranteed to see the original exception?  
**Answer:** No. If the inner advice handled it and returned normally, the outer advice may only see a normal return.

**10.** When moving from plain Spring Framework to Spring Boot, should you keep all assumptions about JDK/CGLIB proxy defaults?  
**Answer:** No. Boot auto-configuration may default to class-based proxies; check your configuration and actual runtime proxy objects.

## 14. Official Spring Framework Documentation

- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): examples and semantics of `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, and `@Around`, binding, and precedence.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): advice types and method-execution join points.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation, and interception boundaries.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): enabling AOP and registering aspect beans.
