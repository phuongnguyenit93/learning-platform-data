# `@After` with Finally Semantics in Spring AOP

## 1. Learning Outcomes and Scope

In **Spring AOP using `@AspectJ`-style annotations**, `@After` defines **after (finally) advice**: advice that runs when a **method execution matching a pointcut** finishes, regardless of whether the method returns successfully or throws an exception outward. This has semantics *analogous to a Java `finally` block* — a hook for cleanup or post-processing work that needs to happen on both branches.

Spring Aspect example:

~~~java
@Aspect
public class CleanupAspect {
    @After("execution(* example.TaskService.run*(..))")
    public void afterTask() {
        System.out.println("cleanup: method finished");
    }
}
~~~

If `runOk()` returns normally, the advice runs. If `runFail()` throws an exception, the advice also runs **when the matching call actually passes through the Spring AOP proxy**. `@After` itself does not classify success vs. failure, does not return a result in place of the method, and is not an exception handler capable of self-recovery.

After this lesson, learners should be able to:

1. Accurately describe when `@After` is triggered on a **Spring-managed target bean**.
2. Distinguish `@After` from `@Before`, `@AfterReturning`, `@AfterThrowing`, and `@Around` in a Spring application.
3. Predict the outcomes of **success, an exception exiting the method, and an exception caught inside the method**.
4. Use `JoinPoint` to log the method name without confusing it with retrieving return values/exceptions.
5. Understand Spring **proxy boundary** limits, advice ordering, cases where the advice itself throws an exception, or methods returning asynchronous values.
6. Write and run a standalone Maven/Java 17+ project demonstrating these semantics.

**Module Special Note:** focus strictly on **Spring Aspect / Spring AOP**; general Aspect knowledge belongs to another topic. Examples with `@Aspect` use **proxy-based Spring AOP**, without requiring AspectJ compile-time or load-time weaving configuration.

## 2. `@After` Semantics According to Spring Framework Documentation

Consider an advice like this:

~~~java
@After("execution(* example.TaskService.run*(..))")
public void afterCompletion(JoinPoint jp) {
    System.out.println("finished: " + jp.getSignature().getName());
}
~~~

The first requirement is that the expression must match a **method execution** on a **target bean intercepted by Spring AOP**. The second requirement is that the caller must invoke the method **through the Spring AOP proxy** so the corresponding interceptor/advisor can execute.

When both conditions hold, whenever the method execution **exits in either direction**, the advice runs:

~~~text
Caller --> Spring AOP proxy --> target method
             |                    |
             |        normal return or throw exception
             |                    |
             +--> @After advice <--+
             |
             +--> caller receives result or exception
~~~

Understand the term "finally" precisely:

- **Normal return:** `@After` runs after the target method finishes, before the caller receives the result from the proxy call.
- **Throwing an exception outward:** `@After` still runs during stack unwinding of the advised call.
- **Catching the exception inside the method:** from the proxy's perspective, the method **returns normally**; `@After` still runs, but it cannot infer that an exception occurred and was caught inside the target.
- **Method not executed through the proxy:** there is no corresponding advisory invocation, so Spring AOP's `@After` is not triggered for that call path.
- **Whether the caller catches the exception:** this step lies outside the advice call; `@After` does not alter exception propagation behavior on its own.

The Spring documentation describes `@After` as after-finally advice, commonly used for releasing resources and similar tasks. It should not be treated as a universal replacement for every resource lifecycle or transaction mechanism.

## 3. Comparing Advice Types on the Same Method

| Annotation | When does it run? | Knows the specific branch? | Suitable role |
| --- | --- | --- | --- |
| `@Before` | Before a matching method execution runs through the proxy | Neither result nor exception exists yet | Pre-call checks / tracing |
| `@AfterReturning` | After the method execution **returns normally** | Can bind the return value via `returning` | Post-processing for the success branch |
| `@AfterThrowing` | When the method execution **throws an exception outward** | Can bind the throwable via `throwing` | Recording failures by exception type |
| **`@After`** | **After method execution, on both return and throw** | Does not accept `returning` or `throwing` parameters | Cleanup / post-processing that must always run |
| `@Around` | Surrounds the method execution if the invocation enters the advice | Actively calls `proceed()`, can observe both return/throw | Flow control, timing with per-invocation state, retry/short-circuit |

Two easy-to-confuse points:

1. **`@After` is not shorthand for `@AfterReturning`.** When the target throws an exception, `@AfterReturning` does not run, yet `@After` still runs.
2. **`@AfterThrowing` does not swallow exceptions.** It is a callback on the failure branch of the join point; logging an exception does not turn the call into a normal return.

Spring recommends choosing the **least powerful advice type sufficient for the purpose**. If you only need to execute logic after the method completes in both directions, `@After` is clearer than using `@Around` just to build a `try/finally`. Conversely, if you need to measure duration with a per-invocation `startTime` variable or control return/throw behavior, `@Around` with `try/finally` may be more appropriate.

## 4. What Does Spring AOP Do with `@After` at Runtime?

For an advice to become part of the call path, the application must have all of the following:

1. **A Spring-managed aspect bean:** a class annotated with `@Aspect` and registered via `@Component` in a scanned package, `@Bean`, or another bean definition.
2. **Spring AOP support enabled:** in plain Spring Framework, typically `@EnableAspectJAutoProxy` with the required dependencies on the classpath.
3. **A matching advisor/pointcut:** Spring reads `@After` metadata and determines which method executions need advising.
4. **A target bean with a valid proxy:** Spring's auto-proxy creator wraps the target in a JDK dynamic proxy or CGLIB proxy depending on configuration.
5. **The call actually crosses the proxy boundary:** the client obtains the bean reference provided by Spring and invokes the corresponding method.

Conceptual flow:

~~~text
@Aspect bean
   -> Spring detects @After + expression
   -> Advisor/interceptor matches target class/method
   -> Spring AOP proxy for target bean
   -> Client calls method through proxy
   -> Target returns or throws exception
   -> @After advice runs with finally semantics
   -> Proxy completes call back to client
~~~

**`@Aspect` alone does not register a bean**; without `@Component`/`@Bean`, Spring may not discover the aspect to create an advisor. Likewise, putting `@After` on an arbitrary Java method in a class without `@Aspect` does not turn the method into Spring AOP advice.

Do not confuse having the `aspectjweaver` dependency in the POM with enabling weaving. This lesson uses **Spring AOP proxies**, not bytecode weaving of the target.

## 5. Runnable Java 17+ Example: Success, Failure, Caught, and Self-Invocation

The following project uses:

- **Java 17+** and Maven.
- Spring Framework **6.2.19**, AspectJ Weaver **1.9.25.1**.
- A `TaskService` Spring bean with methods that return normally, throw an exception, and catch an exception internally.
- A `LifecycleAspect` declaring **`@AfterReturning`, `@AfterThrowing`, and `@After` together in the same aspect**. This allows observing ordering under Spring 6.2.
- An internal call `this.runOk()` to demonstrate proxy boundaries.

No database, HTTP server, thread pool, or transaction manager is used.

### 5.1. Directory Structure

~~~text
spring-after-finally-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── TaskService.java
    ├── LifecycleAspect.java
    └── Main.java
~~~

### 5.2. Maven `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>spring-after-finally-demo</artifactId>
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

The Spring Framework BOM keeps Spring modules aligned on the same version set. If the project uses Spring Boot, prefer Boot's managed BOM/parent and dependencies rather than copying these versions into a differently configured project.

### 5.3. Target `TaskService.java`

~~~java
package example;

public class TaskService {

    public String runOk() {
        System.out.println("target: ok");
        return "OK";
    }

    public String runFail() {
        System.out.println("target: fail");
        throw new IllegalStateException("boom");
    }

    public String runRecovered() {
        System.out.println("target: recovered begin");
        try {
            throw new IllegalArgumentException("temporary");
        } catch (IllegalArgumentException ex) {
            System.out.println("target: caught temporary");
            return "RECOVERED";
        }
    }

    public String callInternally() {
        System.out.println("target: callInternally");
        return this.runOk();
    }
}
~~~

This is an ordinary Java class. `runOk`, `runFail`, and `runRecovered` all start with `run`; `callInternally` does not. It calls `this.runOk()` from inside the target, so it **does not go back through the Spring AOP proxy**.

### 5.4. Aspect `LifecycleAspect.java`

~~~java
package example;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class LifecycleAspect {

    private static final String METHODS =
        "execution(* example.TaskService.run*(..))";

    @AfterReturning(pointcut = METHODS, returning = "value")
    public void afterSuccess(JoinPoint jp, Object value) {
        System.out.println("after-returning: "
            + jp.getSignature().getName() + " => " + value);
    }

    @AfterThrowing(pointcut = METHODS, throwing = "problem")
    public void afterFailure(JoinPoint jp, Throwable problem) {
        System.out.println("after-throwing: "
            + jp.getSignature().getName() + " => " + problem.getMessage());
    }

    @After(METHODS)
    public void afterFinally(JoinPoint jp) {
        System.out.println("after-finally: "
            + jp.getSignature().getName());
    }
}
~~~

**Meaning of each part:**

- `METHODS` is a compile-time constant string used across all three annotations, ensuring they target the exact same expression.
- `@AfterReturning(... returning = "value")` binds the normal return value to the parameter named `value`.
- `@AfterThrowing(... throwing = "problem")` binds the exception exiting the target to the `problem` parameter; `Throwable` is used in the example so it is not limited to a single exception subtype.
- `@After(METHODS)` has neither `returning` nor `throwing`: it does not receive information about the two outcomes via bindings like the other two advice types.
- `JoinPoint jp` provides the method signature; we log only the **method name**, avoiding printing all method arguments since they could contain sensitive data.

**Why place all three advices in the same aspect?** Spring Framework 6.2 documents ordering rules for advices of **different kinds within the same `@Aspect`**; in typical cases, after-returning/after-throwing are observed **before** after-finally. If separated into three independent aspects without defining precedence, you should not rely on log lines from those aspects appearing in the same order.

### 5.5. Spring Configuration `AppConfig.java`

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public TaskService taskService() {
        return new TaskService();
    }

    @Bean
    public LifecycleAspect lifecycleAspect() {
        return new LifecycleAspect();
    }
}
~~~

- `TaskService` is registered as a **Spring bean** via `@Bean`.
- `LifecycleAspect` is also a bean; Spring detects its `@Aspect` and advice declarations.
- `@EnableAspectJAutoProxy(proxyTargetClass = true)` enables AOP and selects class-based proxies (CGLIB) when needed, so the app can call the concrete `TaskService` directly.
- **Switching from JDK proxy to CGLIB does not make `this.runOk()` advised automatically.** Internal calls still bypass the proxy.

### 5.6. Program `Main.java`

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            TaskService service = context.getBean(TaskService.class);

            System.out.println("proxy: " + AopUtils.isAopProxy(service));

            System.out.println("-- success --");
            System.out.println("caller: " + service.runOk());

            System.out.println("-- target throws --");
            try {
                service.runFail();
            } catch (IllegalStateException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }

            System.out.println("-- caught inside target --");
            System.out.println("caller: " + service.runRecovered());

            System.out.println("-- self invocation --");
            System.out.println("caller: " + service.callInternally());
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

### 5.7. Expected Output

With the files above, **the lines printed by the example**, in order:

~~~text
proxy: true
-- success --
target: ok
after-returning: runOk => OK
after-finally: runOk
caller: OK
-- target throws --
target: fail
after-throwing: runFail => boom
after-finally: runFail
caller caught: boom
-- caught inside target --
target: recovered begin
target: caught temporary
after-returning: runRecovered => RECOVERED
after-finally: runRecovered
caller: RECOVERED
-- self invocation --
target: callInternally
target: ok
caller: OK
~~~

Maven or the framework may emit additional logs of their own; the listing above covers only the `System.out.println` statements in the sample program.

### 5.8. Reading the Output

**Case 1 — `runOk()` returns successfully:**

1. Caller invokes `service.runOk()` on the **Spring AOP proxy**.
2. Target prints `target: ok` and returns the string `OK`.
3. `@AfterReturning` runs and prints the result because the method returned normally.
4. `@After` runs on the finally branch even though no exception occurred.
5. Caller prints `caller: OK` after the proxy call completes.

**Case 2 — `runFail()` throws an exception:**

1. Target prints `target: fail` and throws `IllegalStateException("boom")`.
2. `@AfterReturning` **does not run**.
3. `@AfterThrowing` runs and receives the exception information.
4. `@After` still runs because the method exited via the throw branch.
5. Caller catches the original exception and prints `caller caught: boom`. The advice does not swallow the exception.

**Case 3 — exception caught inside `runRecovered()`:**

1. Target catches an `IllegalArgumentException` inside the method itself.
2. The method returns `RECOVERED` **normally**.
3. Spring AOP observes a **normal return**. Therefore `@AfterReturning` runs, while `@AfterThrowing` does not.
4. `@After` still runs. Reading only the `@After` log **cannot tell you** whether an exception was caught inside the target.

**Case 4 — `callInternally()` and `this.runOk()`:**

- `callInternally()` does not match the `run*` expression.
- Inside the target, `this.runOk()` runs directly, **without going through the proxy**, so no after-returning/after-finally lines appear for `runOk` in this case.
- This does not mean the `runOk()` pointcut is wrong: it already ran the advice when called directly by the client **through the proxy** in Case 1.

## 6. To What Extent Is `@After` Equivalent to `finally`?

Familiar Java syntax:

~~~java
try {
    operation();
} finally {
    cleanup();
}
~~~

Similarly, after-finally advice runs when the advised method completes, **regardless of normal return or exception exit**. However, there are two major differences:

### 6.1. It Sits Outside the Method, at the Spring AOP Interception Boundary

`@After` only takes effect when Spring AOP has created an advisor and the invocation **goes through the proxy**. A `finally` block **inside the Java method body** runs under Java semantics whether or not the object belongs to the Spring container.

Example:

~~~java
public void runCleanupLocally() {
    try {
        doWork();
    } finally {
        localResource.close();
    }
}
~~~

This snippet is **illustrative only**, assuming identifiers `doWork` and `localResource` are declared. Java `finally` here is controlled directly by the resource owner. In contrast, Spring `@After` does not run when you invoke the target outside the proxy or via self-invocation bypassing the proxy.

### 6.2. The Advice Is a Java Call and Can Itself Throw an Exception

If code inside `@After` throws an exception, the outcome the caller receives can change: a target call that succeeded can turn into a failure, or the original exception can be **masked** by the exception from the advice.

Example **not recommended for default cleanup**:

~~~java
@After("execution(* example.TaskService.run*(..))")
public void riskyCleanup() {
    throw new IllegalStateException("cleanup failure");
}
~~~

If this advice runs and throws an exception, Spring AOP does not promise to preserve the original outcome. Design cleanup to be reliable, make failures observable, and verify whether business rules permit cleanup errors to propagate.

**Do not swallow errors indiscriminately.** Some systems must fail when cleanup fails, but that decision should be explicitly defined in the business contract. Do not turn a logging/metrics hook into an unintended new source of errors.

## 7. How to Use `JoinPoint` in `@After`

An advice can accept `org.aspectj.lang.JoinPoint` to inspect method execution metadata:

~~~java
@After("execution(* example.TaskService.run*(..))")
public void afterCompletion(JoinPoint jp) {
    String method = jp.getSignature().getName();
    System.out.println("completed: " + method);
}
~~~

Commonly used information:

| Call | Meaning in Spring AOP |
| --- | --- |
| `jp.getSignature().getName()` | Name of the matched method |
| `jp.getSignature().getDeclaringTypeName()` | Type name associated with the method signature |
| `jp.getArgs()` | Array of arguments presented to the join point |
| `jp.getThis()` | Proxy object at the join point, when API/configuration permits inspection |
| `jp.getTarget()` | Target object behind the proxy (may differ from the proxy) |

**Do not treat `getArgs()` as safe-by-default data to log.** Arguments may contain passwords, tokens, card numbers, or personal data. In shared advices, prefer operation names, approved request/correlation IDs, low-cardinality metric labels, and filtered fields.

**`JoinPoint` is not `ProceedingJoinPoint`:** only `@Around` uses `ProceedingJoinPoint.proceed()` to decide whether to forward the invocation. `@After` does not call `proceed()`, nor should it interfere directly with method execution from an after-finally callback.

### 7.1. `@After` Does Not Bind Return Values or Exceptions Like Specialized Annotations

There is no `returning` or `throwing` attribute on `@After`. If the business requirement is:

- **Only log successful return data:** use `@AfterReturning(pointcut=..., returning="value")`.
- **Only handle exceptions leaving the target:** use `@AfterThrowing(pointcut=..., throwing="problem")`.
- **Always release state after execution without distinguishing outcome:** use `@After`.
- **Need both outcome and execution duration in a single per-invocation state:** consider `@Around` with explicit `try/catch/finally`.

Do not try to guess the outcome by looking at the method name or via a shared mutable field on a singleton aspect; concurrent invocations can overwrite each other's state.

## 8. Ordering Between `@After`, `@AfterReturning`, and `@AfterThrowing`

Spring Framework defines precedence rules when **multiple advices of different kinds in the same `@Aspect`** apply to the same join point. In Spring Framework 6.2, `@After` has **finally semantics** and in actual execution timing is invoked **after `@AfterReturning` or `@AfterThrowing`** in that same aspect.

Therefore, in the section 5 example:

~~~text
Normal return:
  target -> @AfterReturning -> @After -> caller

Throws exception:
  target -> @AfterThrowing -> @After -> caller catches exception
~~~

However, do not extrapolate a rigid rule from this diagram for **every advice across all aspects**:

- When advices belong to **two different aspects**, precedence between aspects depends on `@Order` or `Ordered` and the interceptor chain entry/exit rules.
- If multiple advices of the **same kind** apply to one join point in the **same aspect**, order must not be inferred from method declaration order in the Java file.
- Spring AOP may also include infrastructure advisors for transactions/caching/security, so real applications have additional outer layers.
- Regarding "finally", **actual execution timing** differs from simply listing precedence levels in documentation. Always test your specific version/configuration when order affects business behavior.
- `@AfterThrowing` is not a catch-all callback for exceptions thrown by another `@After` or `@AfterReturning` advice. Each advice type has its own semantics around the join point.

### 8.1. `@Order` Does Not Turn `@After` into Success-Only

You can place `@Order(10)` on an aspect to adjust its precedence relative to other aspects, but `@After` itself still runs for **both normal and exceptional exits** of a matched method invocation. `@Order` does not change which methods a pointcut matches and does not convert `@After` into `@AfterReturning`.

## 9. Appropriate vs. Inappropriate Cleanup

### 9.1. Tasks Well Suited for `@After`

- Recording that an **operation has finished** without needing to read the return value or exception.
- Clearing a thread/correlation-context marker **previously set by a coordinating component with a well-defined lifecycle**.
- Releasing state/handles **managed by the aspect or corresponding AOP infrastructure**, when ownership is clear and cleanup applies to both branches.
- Marking the end of an instrumentation scope when the advice itself does not need to hold a per-invocation start timestamp.
- Supporting operational logging at the method/operation level without altering business behavior.

With all of these examples, verify resource creation, ownership, and release; Spring `@After` does not create or manage resources for you automatically.

### 9.2. Cases Not to Misuse

**Do not use `@After` for success-only decisions.** If cleanup is only permitted after a successful commit, `@After` at the method boundary does not prove a transaction committed. With `@Transactional`, when the transaction interceptor commits relative to your `@Aspect` advice also depends on advisor ordering.

**Do not use `@After` for retries or altering return values.** Those mechanisms require an `@Around` design / retry policy, not an after-finally callback without `proceed()`.

**Do not release resources you do not own.** For instance, a lock held by the caller across multiple methods or a connection managed by a transaction manager must not be closed indiscriminately by a generic aspect.

**Do not assume every method call triggers cleanup.** Self-invocation or a call to an object created with `new` outside Spring will bypass the Spring AOP proxy.

### 9.3. When You Need to Open and Close a Resource per Invocation

When you need to create a handle before a call and guarantee closing **that exact handle** after the call, `@Around` with a local variable and `try/finally` is usually clearer:

~~~java
// Illustrative snippet inside a Spring-managed @Aspect; not standalone runnable.
@Around("execution(* example.TaskService.run*(..))")
public Object withScope(ProceedingJoinPoint pjp) throws Throwable {
    ScopeHandle handle = scopeManager.open();
    try {
        return pjp.proceed();
    } finally {
        handle.close();
    }
}
~~~

The `ScopeHandle` and `scopeManager` types here are illustrative abstractions that the application must provide. `@Around` is considered because it provides a **per-invocation local handle variable**, not because `@After` is unsafe in all situations.

If the resource is opened **inside the target method**, a `try-with-resources` block right where the resource is created may be more idiomatic, easier to read, and independent of the AOP proxy boundary.

## 10. Limits of "Always Runs": Proxies and Call Paths

The word "finally" comes with a precondition: **an invocation matched and actually entered the Spring AOP chain**. `@After` is not a global hook running whenever the JVM executes any method with that name.

### 10.1. Self-Invocation via `this`

~~~java
public void outer() {
    this.runOk();
}
~~~

If `outer()` is called through the proxy and has no advice of its own, the target begins executing `outer()`; then `this.runOk()` still invokes the target internally. Advice targeting `runOk()` **does not run** for that internal call.

**Switching to CGLIB does not fix self-invocation either.** This is a proxy-based Spring AOP limitation under both JDK and CGLIB strategies.

Common fix: extract the behavior needing advice into another Spring bean, inject that bean, and call it through the Spring-managed proxy. Do not add `AopContext.currentProxy()` or self-injection just to avoid refactoring unless you understand the coupling and circular-dependency implications.

### 10.2. Objects Created with `new`

~~~java
TaskService service = new TaskService();
service.runFail();
~~~

This is a Java object outside the container; even though a matching Spring `@Aspect` exists in the source code, **this instance is not auto-proxied by Spring AOP**. `@After` does not run for calls on it.

### 10.3. Pointcut Does Not Match

If the advice declares:

~~~java
@After("execution(* example.TaskService.run*(..))")
~~~

then `TaskService.callInternally()` does not satisfy the `run*` method name pattern. An invocation of `callInternally()` gets no after advice simply because the bean is proxied.

### 10.4. Early Short-Circuit in an Outer Interceptor/Advice

An outer `@Around` advice can **return without calling `proceed()`**. In that case, the inner method execution never occurs, and advices attached to that execution will not necessarily run. For example, a cache hit may terminate in an outer interceptor.

Similarly, if an outer `@Before` advice throws an exception before the call chain reaches the target/`@After`, there is no guarantee that inner after-finally advices were ever entered and must run. Distinguish exceptions **thrown by the target method after the invocation reaches the target** from exceptions raised **before the target is invoked**.

### 10.5. JVM/Process Termination

Even Java `finally` has limits (such as forced process termination), and Spring `@After` should even less be described as "guaranteed under all circumstances." On a JVM crash, `kill -9`, host failure, or abrupt container shutdown, do not expect an AOP cleanup advice to run.

## 11. Consequences When Methods Return Asynchronous or Reactive Values

Spring AOP's after-finally semantics are tied to the **proxy-intercepted method execution**, not a business concept of "the work is permanently finished."

Example returning `CompletableFuture`:

~~~java
// Snippet inside a Spring-managed target bean, not a standalone program.
public CompletableFuture<String> runAsyncStyle() {
    return CompletableFuture.supplyAsync(() -> performWork());
}
~~~

If the method **returns the `CompletableFuture` immediately** while the work inside the future is still running, `@After` on that method execution can run **before the future completes**. It observes **when the method returned the `Future` object**, not a guarantee that the asynchronous work succeeded or failed.

Similarly, in reactive code returning `Mono` or `Flux`, creating the publisher and executing the pipeline upon subscription happen at two different times. `@After` on the factory method **does not automatically run when the subscription completes**.

**Design approach:** if cleanup is tied to the **future/publisher lifecycle**, use the appropriate callback/completion handler or operator (such as `CompletableFuture.whenComplete`, or Reactor `doFinally` when using Reactor), rather than treating `@After` on the factory method as a completion signal.

These future/reactive examples are solely to clarify **Spring AOP advice timing** limits, not a full lesson on concurrency or reactive programming.

## 12. Spring Boot and Enabling Advice

In plain Spring Framework, the standard way to enable it is:

~~~java
@Configuration
@EnableAspectJAutoProxy
public class AopConfig {
}
~~~

This is an illustrative snippet requiring Spring imports and an appropriate `ApplicationContext`. The `@Aspect` class must still be registered as a **Spring bean** for the advisor to be discovered.

In a Spring Boot application:

- **Boot 3.x** typically uses `spring-boot-starter-aop`.
- **Boot 4.x** uses `spring-boot-starter-aspectj` under the new starter name.
- When the classpath and Spring Boot AOP auto-configuration are active, manually writing `@EnableAspectJAutoProxy` is usually unnecessary.
- `@Aspect @Component` must lie within component-scanning scope, or a `@Bean` method must register the aspect.
- `spring.aop.proxy-target-class` adjusts the JDK/CGLIB strategy; it **does not change `@After`'s finally semantics**.
- If a project disables AOP auto-configuration or omits the required dependency, `@After` annotations in source code will not cause calls to be intercepted.

Key point: framework AOP support **does not mean** every bean is proxied or every method has `@After` advice. A matching advisor for the bean and a call passing through the proxy are both required.

## 13. Diagnosing `@After` Not Running or Running Unexpectedly

| Symptom | Possible Cause | Check / Fix |
| --- | --- | --- |
| Method returns successfully, no `@After` | Aspect is not a bean or AOP is not enabled | Check bean registration, `@ComponentScan`, `@EnableAspectJAutoProxy` / Boot auto-config |
| Method throws exception, no `@After` | Call bypassed proxy, pointcut didn't match, or target wasn't reached | Check Spring bean reference, signature, interceptor chain |
| Direct call on Spring bean logs; `this.method()` does not | **Self-invocation** | Extract the advised method into another bean and call via DI |
| Only `@AfterReturning` runs on success | Expected behavior | Use `@After` if you need both outcomes |
| `@AfterThrowing` does not run when target catches exception | Method completed normally, no throwable exited | Distinguish internal exceptions from exceptions exiting the method |
| `@After` logs after exception, yet caller still sees exception | Expected behavior | `@After` does not swallow exceptions; caller handles it next |
| `@After` throws an error and caller loses normal result | Exception originated in the advice itself | Design cleanup/logging so it does not unexpectedly break the contract |
| `@After` logs for out-of-scope methods | Pointcut is too broad | Narrow by package, class, method, bean, or annotation |
| `AopUtils.isAopProxy(bean) == true` yet advice doesn't run | Proxy may exist due to another advisor, or method doesn't match | Inspect specific advisors and pointcuts |
| `@After` log appears before/after transaction commit unexpectedly | Ordering between infrastructure advisors and `@Aspect` advice | Check `@Order`/`Ordered` and test with real transactions |
| `@After` runs before background job finishes | Method returned a future/publisher early | Track completion of async/reactive work instead of method return |
| Two `@After` lines appear for one call | Two matching aspects/advisors, duplicate bean registration, or nested proxies | Inspect registered aspect beans and the advisor chain |

### Quick Verification Checklist

1. **Does the aspect bean exist?** `ApplicationContext.getBeanNamesForType(LifecycleAspect.class)`.
2. **Is AOP enabled?** Plain Spring Framework: `@EnableAspectJAutoProxy`; Spring Boot: auto-configuration/starter matching your Boot version.
3. **Is there a real target bean/proxy?** `AopUtils.isAopProxy(context.getBean(TaskService.class))`; `true` alone is not enough to confirm the method matched.
4. **Does the pointcut match the method?** Check package, method name pattern, overloaded methods, and visibility.
5. **Does the caller hold the proxy?** Do not use `new`, and avoid unwrapping the underlying target to call it directly.
6. **Is there self-invocation?** Look for `this.runX()` calls inside the target.
7. **Is an around advice short-circuiting?** Verify whether `proceed()` is actually invoked.
8. **Is the advice throwing an exception?** Do not confuse an advice exception with a target exception.
9. **Are there multiple aspects/infrastructure advisors?** Investigate ordering before assuming stdout order.
10. **Is there async work?** Method-return time is not job-completion time.

## 14. Self-Check

**Q1.** Does `@After("execution(* TaskService.run*(..))")` run when `runFail()` throws `IllegalStateException` outward?

**Answer:** Yes, provided the invocation matches and goes through the Spring AOP proxy as in the example. After-finally advice runs on exceptional method exits.

**Q2.** `runRecovered()` catches an internal error and returns `"RECOVERED"`. Does `@AfterThrowing` run? What about `@After`?

**Answer:** `@AfterThrowing` does not run because the method did not throw an exception outward. `@After` runs because the method execution finished normally.

**Q3.** Can you use `@After` with `returning="value"` to capture the return value?

**Answer:** No. The `returning` attribute belongs to `@AfterReturning`. With `@After`, use `JoinPoint` to inspect the signature/arguments, but it does not provide return value binding like success advice.

**Q4.** `runOk()` is called via `this.runOk()` inside the target. Does `@After` run?

**Answer:** Not for that internal call, because it bypasses the Spring AOP proxy. Calling `service.runOk()` directly on the Spring proxy from another caller can trigger the advice.

**Q5.** An `@After` advice throws `IllegalStateException` after the target succeeded. Is the caller still guaranteed to receive the successful result?

**Answer:** No. An exception from the advice can turn the external call into a failure or mask an original exception if one existed. Cleanup must have an explicit error-handling policy.

**Q6.** You need to time a method using a per-invocation start variable. Should you use two mutable fields in a singleton aspect with `@Before`/`@After`?

**Answer:** No, because concurrent invocations can overwrite shared state. Use `@Around` with a local `start` variable and `try/finally`, or an instrumentation scope managed per invocation.

**Q7.** A method returns a `CompletableFuture`; the `Future` has not finished yet, but `@After` already ran. Is that a bug?

**Answer:** No. The method execution already returned the `Future`; Spring `@After` at the method boundary does not wait for the `Future` to complete.

**Q8.** Three advices—`@After`, `@AfterReturning`, and `@AfterThrowing`—live in the same aspect. Should you rely on their method declaration order in the source file?

**Answer:** No. Rely on Spring's rules by advice kind and run integration tests. In Spring 6.2, after-finally advice actually runs after after-returning or after-throwing within the same aspect on their respective invocations.

## 15. Official Spring Documentation

- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): "After (Finally) Advice" section, distinguishing after-returning/after-throwing, `JoinPoint`, and advice ordering.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): Spring AOP proxy scope and advice types.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): enabling `@EnableAspectJAutoProxy`, aspect bean requirements, and AspectJ dependencies.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation, and interception boundaries.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): method execution conditions and expressions.
- [Spring Framework — Programmatic Advice API](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html): advice contracts and notes on advices throwing exceptions.
