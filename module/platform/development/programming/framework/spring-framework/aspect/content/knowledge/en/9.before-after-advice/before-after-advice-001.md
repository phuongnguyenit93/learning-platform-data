# Spring AOP `@Before` — Behavior Before Target Method Execution

## 1. Meaning of `@Before` in a Spring Aspect

`@Before` belongs to `org.aspectj.lang.annotation.Before`, used in `@AspectJ`-style Spring AOP to declare **advice that runs before a method execution selected by a pointcut**, when the actual call goes through a **Spring AOP proxy**.

```java
@Aspect
@Component
public class TraceAspect {
    @Before("execution(* demo.before.SubmissionService.submit(..))")
    public void beforeSubmit() {
        System.out.println("[advice] before submit");
    }
}
```

The snippet above is an **illustrative fragment** excluding imports/package and the Spring target object. Meaning:

- `@Aspect` marks the class that declares the aspect; `@Component` or a `@Bean` method makes the aspect a **Spring-managed bean**.
- The expression `execution(* demo.before.SubmissionService.submit(..))` selects the `submit(..)` method on the corresponding target class; it does not select every method in the application.
- When a consumer invokes the method **through the proxy** and the pointcut matches, Spring runs `beforeSubmit()` before letting execution continue to the target method.
- If the advice completes normally, Spring continues the interceptor chain and typically proceeds to the target method, unless another interceptor alters the flow.
- If `beforeSubmit()` **throws an exception**, the call does not continue normally to the target method; the exception propagates to the caller, unless another interceptor handles it.

**Scope:** Proxy-based Spring AOP, Spring IoC beans, pointcuts, and `@Aspect`. This is not a general AOP concept or AspectJ compile-time/load-time weaving mechanism.

## 2. When Does "Before Calling the Target Method" Occur?

In Spring AOP, the primary supported join point is **method execution** on a Spring-managed bean. `@Before` advice runs before the target method body executes in an invocation intercepted by the proxy, not before every Java operation leading up to the method call.

```text
Consumer / controller (Spring-injected service)
             |
             | service.submit("S-001")
             v
       Spring AOP proxy
             |
     check advisor/pointcut
             |
       interceptor chain
             |
         @Before advice
             |
       (advice completes normally)
             |
             v
       Target.submit("S-001")
             |
             v
          Return / throw
             |
             v
         Return to caller
```

Specific observations:

1. **Argument expressions at the call site** have already been evaluated by Java before the method invocation reaches the proxy. `@Before` does not run before creating arguments, for example `service.submit(buildRequest())`.
2. The target Spring bean has already gone through initialization and proxy publication (following the normal lifecycle); `@Before` is **not** a callback before the constructor or before `@PostConstruct`.
3. Other advices/interceptors may exist in the chain. `@Before` runs **before target execution**, but there is no guarantee that it is the very first component to run for the entire request.
4. The advice is invoked for **each intercepted and matched invocation**, not just once at context startup.
5. If the target has a matched method but the caller invokes `this.submit()` from inside the target itself, this call **does not go through the Spring proxy** and `@Before` will not be triggered separately for that internal call.

A Spring method can still be called normally **without** advice if the bean is not proxied, the pointcut does not match, or the call bypasses the proxy.

## 3. Conditions for `@Before` to Work

In a Spring Framework application using annotation-style AOP, all of the following are required:

1. **The target is a Spring bean**: for example, a class annotated with `@Service` discovered via component scanning or registered via `@Bean`.
2. **The aspect is also a Spring bean**: typically `@Aspect @Component` or `@Bean`. `@Aspect` alone does not cause the component scanner to automatically register the bean.
3. **Spring AOP infrastructure is enabled**: for example, `@EnableAspectJAutoProxy` in a plain Spring Framework `@Configuration`; Spring Boot has auto-configuration when the appropriate dependency is available.
4. **The pointcut matches the method**: the target method must satisfy the class/package, name, visibility, and argument/annotation constraints described by the expression.
5. **The call goes through the proxy**: the consumer uses the reference provided by Spring (via DI or `ApplicationContext.getBean(...)`), rather than creating an object with `new` and calling it directly.
6. **The method can be intercepted by the actual proxy type**: JDK dynamic proxies primarily intercept public interface methods; CGLIB class proxies depend on subclassing/overriding capabilities and have limitations with `final`/`private`.

### Configuration in Plain Spring Framework

```java
package demo.before;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy
public class AppConfig {
}
```

For Java 17+ Spring Framework 6.x applications using `@AspectJ`, dependencies typically include Spring Context, Spring AOP, and `aspectjweaver` so Spring can parse pointcuts. Neither the AspectJ compiler nor the AspectJ load-time weaver is required to run a **Spring AOP proxy**.

In Spring Boot, the AOP starter can enable the AOP infrastructure. Spring Boot typically defaults to CGLIB class-based proxies when AOP is auto-configured; plain Spring Framework with `@EnableAspectJAutoProxy(proxyTargetClass=false)` prefers JDK proxies if the target implements an interface. Regardless of the proxy type, calls must still go **through the proxy** and the pointcut must match.

## 4. How to Write Expressions for `@Before`

The annotation value accepts a **pointcut expression** directly or the name of a declared `@Pointcut`.

### 4.1. Inline Pointcut

```java
@Before("execution(public * demo.before.SubmissionService.submit(..))")
public void beforeSubmit() {
    System.out.println("before submit");
}
```

In the expression:

- `execution(...)`: selects method execution.
- `public`: only public methods.
- `*`: any return type.
- `demo.before.SubmissionService.submit`: target type and method name.
- `(..)`: accepts any list of argument types.

If an exact single argument of type `String` is needed, you can use:

```java
@Before("execution(* demo.before.SubmissionService.submit(java.lang.String))")
public void beforeSubmitString() {
    System.out.println("before String submit");
}
```

These snippets are separate illustrative options, not meant to be used simultaneously with another advice from the same example unless multiple advices are intentionally desired.

### 4.2. Using a Named Pointcut

```java
@Pointcut("execution(* demo.before.SubmissionService.submit(..))")
private void submissionOperation() {}

@Before("submissionOperation()")
public void auditSubmission() {
    System.out.println("before submission");
}
```

These are methods located **inside the aspect**. The `submissionOperation()` method is just a pointcut declaration name; Java code in its body is not executed as business logic when Spring evaluates the pointcut.

The `private` visibility of the `@Pointcut` method only affects reference access to the named pointcut under Java rules; it **does not restrict target methods to private**.

### 4.3. Combining Multiple Conditions with `&&`, `||`, `!`

```java
@Before(
    "within(demo.before..*)"
  + " && (execution(* submit*(..)) || execution(* cancel*(..)))"
  + " && !execution(* *Internal(..))"
)
public void beforePublicApi(JoinPoint joinPoint) {
    System.out.println(joinPoint.getSignature().getName());
}
```

This snippet illustrates conditional logic. To restrict to **public only**, add `&& execution(public * *(..))`; naming the method `beforePublicApi` does not automatically create a visibility constraint in the expression.

Parentheses matter: `A || B && !C` is interpreted as `A || (B && !C)`, which is **different** from `(A || B) && !C`. A negation condition missing parentheses can mistakenly exclude or include methods.

### 4.4. Matching by Spring Bean or Annotation

Spring has its own pointcut designator `bean(...)` (filtering by bean name):

```java
@Before("bean(*SubmissionService) && execution(* submit(..))")
public void beforeNamedBeans() {
    System.out.println("before named bean");
}
```

This is just an example expression: the actual bean name must match the pattern; by default `@Service` on `SubmissionService` usually produces the bean name `submissionService`, differing in letter case. The pattern `*SubmissionService` will not automatically match the `submissionService` bean if character casing rules do not match. With the default bean name, you can replace it with `bean(submissionService)`. Therefore, always verify the actual bean name.

For custom method annotations, you can use `@annotation(com.example.Audited)` to select methods that have an annotation recognized according to pointcut rules. The annotation must be a valid type, registered/placed where the framework can observe it; for example, do not assume a custom annotation has behavior before an aspect exists.

## 5. Data Advice Can Read Using `JoinPoint`

Spring AOP can pass `org.aspectj.lang.JoinPoint` as the **first parameter** in before advice:

```java
@Before("execution(* demo.before.SubmissionService.submit(..))")
public void beforeSubmit(JoinPoint joinPoint) {
    String methodName = joinPoint.getSignature().getName();
    Object[] args = joinPoint.getArgs();
    System.out.println("[advice] " + methodName + ": " + args.length);
}
```

With `JoinPoint`:

| API | Meaning in Spring AOP |
| --- | --- |
| `joinPoint.getSignature()` | Method signature, including the method name |
| `joinPoint.getArgs()` | Array containing the argument values of the current invocation |
| `joinPoint.getThis()` | Reference to the **Spring AOP proxy** |
| `joinPoint.getTarget()` | The target object behind the proxy |

Note that `getThis()` and `getTarget()` can be **two different objects** when Spring uses a proxy. With a JDK proxy, `getThis()` has the proxy interface type, not the concrete implementation. Do not arbitrarily cast it to the implementation class.

`getArgs()` allows reading arguments for logging, metrics, or validation; do not arbitrarily log passwords, tokens, personal data, or entire sensitive payloads. It does not establish a stable contract to **modify the arguments the target will receive** by reassigning elements in the array returned by `getArgs()`.

### Binding Arguments via `args(...)`

Instead of manually reading the array, you can bind arguments to advice parameters:

```java
@Before(
    value = "execution(* demo.before.SubmissionService.submit(..)) && args(orderId)",
    argNames = "orderId"
)
public void beforeSubmit(JoinPoint joinPoint, String orderId) {
    System.out.println("[advice] submit " + orderId);
}
```

This is an alternative fragment. `JoinPoint` is the special first parameter; `argNames` explicitly specifies how to bind `orderId` for cases where Java parameter-name metadata is absent. If the actual pointcut has multiple arguments, a matching `args(...)` expression and signature are needed. Do not assume the annotation automatically knows argument names when proper metadata/binding is not provided.

### What Data Is Not Available Before Execution?

Before advice does not have the **return value** or the **exception the target is about to throw** because the target has not run yet. Therefore:

- To process the return value after a method succeeds, use `@AfterReturning`.
- To handle an exception thrown by the target method, use `@AfterThrowing`.
- To run code after a method regardless of success or failure, use `@After` with finally semantics.
- To actively control whether `proceed()` runs, change arguments when proceeding, or replace the return value according to a contract, consider `@Around`.

`@Before` is the clearest choice when you only need to prepare, log, start timing, validate a condition, and let the method continue normally.

## 6. What Happens If `@Before` Throws an Exception?

The rule "advice runs before the method" often leads learners to think before advice **cannot** prevent the method from executing. Spring describes it accurately: before advice **cannot actively decide to skip execution** like `@Around`; **the only exception is when the advice throws an exception**, which interrupts the normal execution flow.

Example:

```java
@Before("execution(* demo.before.SubmissionService.submit(..))")
public void validateBefore(JoinPoint jp) {
    String id = (String) jp.getArgs()[0];
    if ("DENY".equals(id)) {
        throw new IllegalArgumentException("blocked by before advice");
    }
}
```

This snippet is an illustrative advice option, not a complete standalone example. When the caller invokes `service.submit("DENY")` through the proxy:

1. The pointcut matches and the advice starts.
2. The advice throws `IllegalArgumentException`.
3. Target `submit("DENY")` **is not called** in the normal flow of this invocation.
4. The exception propagates back through the interceptor chain, where outer interceptors may observe/handle it.
5. Any `@AfterThrowing` advice applied to the **target method** also behaves depending on the interceptor/advice chain and exception type; you should not assume all after-throwing advices log in a single fixed order unless ordering is configured.

**Key point not to confuse:** throwing an exception in before advice can reject the call, but this does not turn before advice into `@Around`. Before advice has no `ProceedingJoinPoint.proceed()` and cannot choose a replacement return value for the caller.

Be cautious when using `@Before` for authorization: methods that do not go through the proxy (self-invocation, manually instantiated objects) **are not checked by the aspect**. Security enforcement should rely on trusted boundary architectures and Spring Security or appropriate complementary controls, rather than treating a custom `@Before` as the sole safeguard.

## 7. Runnable Example — Java 17 + Spring Framework 6.2 + Maven

The example below does not use Spring Boot in order to clearly show the conditions for creating a Spring AOP proxy. Behaviors verified through logs:

1. `@Before` runs before `submit("OK")`.
2. `@Before` can **throw an exception**, preventing `submit("DENY")` from running.
3. If the **target itself throws an exception** after before advice finishes, the before advice still ran.
4. The pointcut does not match `cancel(...)`, so no advice runs for it.
5. Target `runBatch()` calls `this.submit("INNER")` internally, so that internal call bypasses the proxy.

### 7.1. File Structure

```text
spring-before-advice/
├── pom.xml
└── src/main/java/demo/before/
    ├── AppConfig.java
    ├── SubmissionOperations.java
    ├── SubmissionService.java
    ├── AuditAspect.java
    └── Main.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-before-advice</artifactId>
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

These libraries are sufficient for a plain Spring Framework application using `@AspectJ` in Spring AOP proxy style. Maven and JDK 17+ with access to download dependencies from the repository are required.

### 7.3. `AppConfig.java`

```java
package demo.before;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@ComponentScan` discovers the `@Service` target and the `@Component` aspect. `@EnableAspectJAutoProxy` enables the AOP proxy creation infrastructure. With a target that has an interface and `proxyTargetClass=false`, the example uses a **JDK dynamic proxy**.

### 7.4. `SubmissionOperations.java`

```java
package demo.before;

public interface SubmissionOperations {
    void submit(String id);
    void cancel(String id);
    void runBatch();
}
```

Spring can create a JDK proxy implementing this interface. Consumers receive the dependency typed as `SubmissionOperations` rather than assuming the proxy extends the `SubmissionService` class.

### 7.5. `SubmissionService.java`

```java
package demo.before;

import org.springframework.stereotype.Service;

@Service
public class SubmissionService implements SubmissionOperations {
    @Override
    public void submit(String id) {
        System.out.println("[target] submit " + id);
        if ("TARGET_FAIL".equals(id)) {
            throw new IllegalStateException("target failed");
        }
    }

    @Override
    public void cancel(String id) {
        System.out.println("[target] cancel " + id);
    }

    @Override
    public void runBatch() {
        System.out.println("[target] batch");
        this.submit("INNER");
    }
}
```

The `submit("TARGET_FAIL")` method **prints the target line first**, then throws an exception. This allows comparing the order of `@Before` against the target logic. `this.submit("INNER")` is a self-invocation, so it will not go through the proxy on its own.

### 7.6. `AuditAspect.java`

```java
package demo.before;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("execution(* demo.before.SubmissionService.submit(..))")
    public void beforeSubmit(JoinPoint joinPoint) {
        String id = (String) joinPoint.getArgs()[0];

        System.out.println("[advice] before submit " + id);

        if ("DENY".equals(id)) {
            throw new IllegalArgumentException("blocked by before advice");
        }
    }
}
```

The aspect has exactly one declaration and only matches `submit(..)`. It does not match `cancel()` or `runBatch()`. To illustrate rejecting a call, the advice throws an exception when `id` is `"DENY"`. In production, do not log user data indiscriminately and do not treat a custom aspect as a complete replacement for security.

### 7.7. `Main.java`

```java
package demo.before;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            SubmissionOperations service =
                    context.getBean(SubmissionOperations.class);

            System.out.println("[main] jdkProxy="
                    + AopUtils.isJdkDynamicProxy(service));

            service.submit("OK");

            try {
                service.submit("DENY");
            } catch (IllegalArgumentException ex) {
                System.out.println("[caller] " + ex.getMessage());
            }

            try {
                service.submit("TARGET_FAIL");
            } catch (IllegalStateException ex) {
                System.out.println("[caller] " + ex.getMessage());
            }

            service.cancel("C-1");
            service.runBatch();
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.before.Main
```

**Stdout from the program's `System.out` statements** (excluding Maven/Spring logs that may appear depending on the environment):

```text
[main] jdkProxy=true
[advice] before submit OK
[target] submit OK
[advice] before submit DENY
[caller] blocked by before advice
[advice] before submit TARGET_FAIL
[target] submit TARGET_FAIL
[caller] target failed
[target] cancel C-1
[target] batch
[target] submit INNER
```

### 7.8. Call-by-Call Stdout Analysis

| Call from `Main` | `@Before` Advice | Target | Result |
| --- | --- | --- | --- |
| `submit("OK")` | Prints `before submit OK` | Prints `submit OK` | Completes normally |
| `submit("DENY")` | Prints `before submit DENY` then throws exception | **Does not run** | Caller catches `IllegalArgumentException` |
| `submit("TARGET_FAIL")` | Prints `before submit TARGET_FAIL` | Prints `submit TARGET_FAIL` then throws exception | Caller catches `IllegalStateException` |
| `cancel("C-1")` | Does not match pointcut | Prints `cancel C-1` | Completes normally |
| `runBatch()` | Does not match this method's pointcut | Prints `batch` | Internally calls `this.submit("INNER")` |
| `this.submit("INNER")` inside target | **Does not run** | Prints `submit INNER` | Self-invocation bypasses proxy |

The example intentionally has only one advice for the `submit()` method to avoid depending on the ordering of multiple before advices. The code does not automatically run the advice on `this.submit()` from the target because that call does not go through the Spring proxy.

### 7.9. Self-Check Experiments

**Experiment A — Change the pointcut to `cancel(..)`**

Replace the annotation in `AuditAspect` with:

```java
@Before("execution(* demo.before.SubmissionService.cancel(..))")
```

When re-run, only `cancel("C-1")` from the caller through the proxy triggers the advice. Note that the current example still has the log label "before submit" and the DENY logic: **those are just the old label/logic of the advice**; when running a real experiment you should rename the log and validation to correspond to `cancel`. Do not infer that log data automatically changes based on the pointcut.

**Experiment B — Remove `@Component` from the aspect**

If the aspect is no longer managed by Spring via `@Component` or `@Bean`, the advice is not registered. The target can still be a Spring bean, but this before advice will no longer exist.

**Experiment C — Use `new SubmissionService()`**

```java
SubmissionOperations outsideSpring = new SubmissionService();
outsideSpring.submit("OK");
```

The snippet above creates a Java object that is not a Spring bean proxy. The line `[target] submit OK` still appears, but there is no `[advice]` before it.

**Experiment D — Switch to CGLIB**

Change to `@EnableAspectJAutoProxy(proxyTargetClass = true)`. Because the target is non-final, a class proxy is valid. In `Main`, `isJdkDynamicProxy(service)` becomes `false`, but `@Before` can still run through the proxy; `this.submit("INNER")` still bypasses it.

## 8. `@Before` Compared to Other Advice Types in Spring

| Advice in Spring AOP | Timing | Has target return/exception? | Control capabilities |
| --- | --- | --- | --- |
| `@Before` | Before the method execution selected by the pointcut | Target return/exception not yet available | Cannot actively `proceed()`/replace return; can interrupt by throwing an exception |
| `@AfterReturning` | After the target completes normally | Can bind the return value | Observes successful result; not used like `@Around` to replace return directly |
| `@AfterThrowing` | When execution ends with an exception | Can bind the exception | Logs or performs error-related handling |
| `@After` | After execution regardless of normal or exceptional completion, following finally semantics | Not used to replace return | Cleanup / final tasks |
| `@Around` | Surrounds the join point | Can observe return/exception via `proceed()` | Actively decides when/whether to call `proceed()` and what to return |

What does the goal before the method **actually need to do?**

- If you only need to log or record metrics before the target starts, `@Before` is a clear choice.
- If you need to accurately measure duration **including the method outcome**, an `@Around` with `try/finally` may be more appropriate.
- If you need to change the return value, skip the method without throwing an exception, or alter arguments when proceeding, that is `@Around` behavior, not `@Before`.
- If you need to handle exceptions after the target runs, do not try to guess future exceptions in before advice; use the appropriate advice type.

Use the **least powerful** advice type that satisfies the requirement to keep Spring applications readable and less error-prone.

## 9. Ordering of Multiple Before Advices

When a method is matched by multiple aspects/advisors, you cannot infer the log order from class location in directories, bean scan order, or source code declaration order.

Spring supports specifying precedence for different aspects using `@Order` or the `Ordered` interface. **A lower order value indicates higher precedence** wherever Spring applies this ordering rule.

```java
@Aspect
@Component
@Order(1)
public class FirstAspect {
    @Before("execution(* demo.before.SubmissionService.submit(..))")
    public void first() {
        System.out.println("[first] before");
    }
}
```

```java
@Aspect
@Component
@Order(2)
public class SecondAspect {
    @Before("execution(* demo.before.SubmissionService.submit(..))")
    public void second() {
        System.out.println("[second] before");
    }
}
```

These are two fragments requiring imports for `org.springframework.core.annotation.Order`, `org.aspectj.lang.annotation.Aspect`, `org.aspectj.lang.annotation.Before`, and `org.springframework.stereotype.Component`. If both are registered and the target method matches, the higher-precedence aspect usually runs earlier on the way in. However, other interceptors such as transaction/security and the advisor chain order must also be considered in a real system.

For multiple advices within the **same aspect class**, do not rely on **source code order** as a stable contract. When ordering has business significance, organize responsibilities clearly and test the actual chain.

**Do not equate `@Order` with bean initialization order.** It is used in the applicable ordering mechanism and does not guarantee constructor or `@PostConstruct` execution in that order.

## 10. Common Pitfalls in Spring

### 10.1. `@Aspect` Is Not Yet a Spring Bean

```java
@Aspect
public class BeforeAspect {
    @Before("execution(* demo.before..*Service.*(..))")
    public void log() {}
}
```

If you only create a class like the above without registering it as a Spring bean, the AOP auto-proxy creator will not necessarily use that aspect. You need `@Component` within the scan scope or registration via `@Bean`. Do not call `new BeforeAspect()` in your own code hoping Spring will discover it automatically.

### 10.2. Self-Invocation and Objects Outside Spring

```java
public void outer() {
    this.inner(); // Does not go through the AOP proxy.
}
```

Even if `inner()` is public and the pointcut matches, self-invocation bypasses the proxy. A maintainable solution is to extract `inner()` into a method of **another bean**, inject it, and call it through the Spring reference, rather than merely enabling CGLIB.

### 10.3. Private, Static, Final, and Methods Not Exposed via an Interface

- Private methods cannot be advised by JDK proxies or CGLIB.
- Static methods are not instance proxy invocations.
- With CGLIB, a `final method` cannot be overridden to intercept; a `final class` cannot be subclassed.
- With a JDK proxy, a **public method on the interface** can be intercepted even if the implementation method is `final`, because the proxy intercepts at the interface boundary.
- A public method that exists only on the implementation (not on the interface) is not exposed by a JDK proxy to interface consumers.

You cannot bypass these boundaries simply by writing a broader `@Before("execution(...")` expression.

### 10.4. Pointcut Does Not Match the Target

If you use `execution(* demo.before.OtherService.submit(..))` when the actual bean is `SubmissionService`, Spring will not run the advice for the desired method. Check the exact class/package, proxy type, method signature, visibility, and additional conditions.

### 10.5. Pitfalls When Logging Input in Before Advice

In production, use structured logging and **redaction** for sensitive parameters. `JoinPoint.getArgs()` may contain mutable objects, streams, files, tokens, or large request data. Do not blindly call `toString()` on all arguments and do not use logging as an access-control mechanism.

### 10.6. Before Advice Exceptions Are Not Target Exceptions

If `@Before` throws an exception, the target has not run. When debugging, distinguish from the stack trace and logs whether the error originated **from the advice** or **later in the target**. If a target error occurs, the before advice still completed before it. Do not conclude "the advice didn't run" just because the method ultimately threw an exception.

### 10.7. Does `@Before` Run Once or Multiple Times?

It runs on every matched invocation **through the proxy**. For example, if an API endpoint is called 10 times causing the business method to run through the proxy 10 times, the before advice can run 10 times accordingly; it is not "run once beforehand during Spring startup." However, if the target internally calls the same method using `this`, those calls do not count as new Spring proxy interceptions.

### 10.8. Do Not Assume `@Before` and `@Transactional` Have a Fixed Order

Spring declarative transactions also typically use a proxy/interceptor. If a before advice sits **outside** the transaction interceptor, it can run before the transaction starts; if it sits **inside**, it can run when the transaction is already open. The order depends on advisor ordering and cannot be inferred solely from both annotations being present. If an aspect requires an active transaction, design the order explicitly and test it.

## 11. Diagnostic Checklist for "`@Before` Not Running"

| Symptom | How to Check / Solution |
| --- | --- |
| Service method runs but no `@Before` log | Verify the target is a Spring bean, the aspect is registered, and `@EnableAspectJAutoProxy` or Boot AOP auto-config is active |
| `@Aspect` exists but no advice runs | Register the aspect via `@Component`/`@Bean`, and ensure component scanning covers its package |
| AOP proxy exists but `@Before` doesn't run for method A | Pointcut does not match A, or the call to A bypasses the proxy |
| `this.method()` has no advice | Self-invocation; call through another injected bean instead |
| `new SomeService().method()` has no advice | Object outside the container, has no Spring proxy |
| JDK proxy does not expose a specific method | Inject via an interface containing the method, or consider CGLIB if appropriate |
| CGLIB `final`/`private` method is not advised | Cannot be overridden; change the method/bean boundary |
| Method is blocked without seeing target logs | Before advice may be throwing an exception before the target |
| Before log appears but target throws an exception | Normal behavior: before runs prior to the target |
| Need the return value inside before advice | Switch to `@AfterReturning` or `@Around` |
| Want advice to modify arguments or skip the target | Consider `@Around` and `ProceedingJoinPoint` |
| Multiple advices do not run in source-code order | Use `@Order`/`Ordered` across aspects and write integration tests |
| Advice seen on direct calls but missing on calls from a batch | Internal call inside the target uses `this`, bypassing the proxy |

**Useful Investigation Workflow:**

1. Verify the target bean is created/retrieved by Spring rather than `new`.
2. Confirm the aspect is also a Spring bean and `@Before` references the right pointcut.
3. Check the auto-proxy creator / AOP enablement and `AopUtils.isAopProxy(bean)` on the **actual reference the consumer receives**.
4. If using JDK proxies, check that the method is on the interface; if using CGLIB, check that the method can be overridden.
5. Check whether the caller invokes **through the proxy** or via `this` inside the target.
6. Place observation points in the advice and target method; test the normal case, the case where the advice throws, and the case where the target throws.
7. If multiple advices/interceptors are present, verify the actual ordering before concluding the order is wrong.
8. Keep logic in before advice small, with controllable side effects and safe logging.

## 12. Self-Assessment Questions

**1. Does `@Before` run before the arguments of a Java call are created?** No. It runs after the invocation reaches the proxy with arguments already evaluated by Java, but before the target method begins executing.

**2. Can `@Before` advice retrieve the target's return value for logging?** No, the target has not run yet. Use `@AfterReturning` or `@Around` when the return value is required.

**3. Can `@Before` prevent a method from running?** It has no `proceed()` to choose to skip execution, but if the advice **throws an exception**, the target is not invoked on the normal execution path.

**4. Why isn't `this.submit()` intercepted even though `@Before` is configured?** Spring AOP only intercepts calls going through the proxy; `this.submit()` is a call directly on the target.

**5. Is `@Aspect` enough for Spring to automatically register an aspect bean?** No. It must be registered via component scanning with `@Component` or an appropriate bean definition/`@Bean`.

**6. When `submit()` is called three times through the proxy, how many times does the before advice run?** If all three match and are not skipped by a prior interceptor, the before advice typically runs three times (once per invocation); not once at startup.

**7. Are `JoinPoint.getThis()` and `getTarget()` always identical?** No. With a Spring AOP proxy, `getThis()` represents the proxy and `getTarget()` represents the target; they can be two different Java objects.

**8. Can `@Order` be used to guarantee that all constructors, post-construct callbacks, transactions, and before advices follow the exact same order?** No. Advice/advisor ordering differs from bean lifecycle initialization; understand each mechanism separately and test.

## Official Spring Documentation References

- [Spring Framework — Declaring Advice / Before Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework — AOP Concepts, Before Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-defn.html)
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework — Ordering Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html#advice-ordering)
