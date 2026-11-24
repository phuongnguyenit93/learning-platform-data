# Distinguishing Exceptions from the Target Method vs. Other Advice in Spring AOP

## 1. Goals and scenarios

In Spring Framework AOP, a service call through a proxy can fail because of the **target method** or because of **an advisor/advice running before, after, or around the target**. For example:

- `@Before` checks permissions and throws an exception **before the target runs**.
- The target method throws an exception itself during business processing.
- The target **returns a result normally**, yet `@AfterReturning` throws an exception while processing the result.
- `@Around` catches an exception from the continuation and **translates it into another exception**, or swallows the error and returns a fallback.
- `@After` runs cleanup and throws a new error, sometimes masking the original exception.
- `TransactionInterceptor` or an exception-translation interceptor may create/transform an exception **outside the target method body**.

Therefore, **the final exception the caller receives from the Spring proxy does not prove the target body threw that exception**. This impacts logging, auditing, metrics, retries, and error diagnosis.

After this lesson, you will know how to:

1. Distinguish **throw site**, **observation site**, **final exception**, and **target execution outcome**.
2. Understand that `@AfterThrowing` is designed by Spring for exceptions from method execution, **not as a global catch for all other advice**.
3. Know that `@Around` catches exceptions from the **inner continuation**, which may include inner advice.
4. Use `@Order` to control the scope observed by each advice.
5. Test four scenarios with Spring Framework 6.2.x, Java 17+, and Maven: normal; target throw; before-advice throw; after-returning-advice throw.
6. Design instrumentation so it does not falsely log "target failed" when an advice actually failed.
7. Recognize proxy limits, checked-exception wrapping, transaction commits, and secondary exceptions.

**Scope limit:** Focuses solely on **Spring-managed `@Aspect` and Spring proxy-based AOP**, without going into AspectJ weaving or general AOP concepts unnecessary for Spring scenarios.

## 2. Placing each error source in the right interceptor chain position

The demo in section 6 uses **four separate aspects**, with explicit `@Order`:

~~~text
Client → Spring proxy
       → OuterTraceAspect @Around (0)
       → BeforeGateAspect @Before (10)
       → AfterResultAspect @AfterReturning (20)
       → TargetFailureAspect @AfterThrowing (30)
       → JobService.execute(...) (target)
~~~

Outer aspects can see errors emerging from inner layers when calling `proceed()`. However, if `BeforeGateAspect` throws an error, the target and deeper advisors have not run; if `AfterResultAspect` throws after the target returns, `TargetFailureAspect` inside it has already completed normally. This is the **intentional ordering of the demo**, not the default order of every Spring application.

| Scenario | First error origin | Did target run? | What do observers in this demo see? |
| --- | --- | --- | --- |
| `BEFORE` | Outer `@Before` | No | Outer `@Around` catches; inner `@AfterThrowing` is never entered |
| `TARGET` | `JobService.execute()` | Yes, but threw | Inner `@AfterThrowing` logs; outer `@Around` catches |
| `AFTER` | Outer `@AfterReturning` | Yes, already returned | Outer `@Around` catches; inner `@AfterThrowing` already finished |
| `OK` | No error | Yes, already returned | Outer `@Around` returns normal result |

## 3. Error attribution: distinguishing throw site, observation site, and caller outcome

| Signal | Question to verify |
| --- | --- |
| **Throw site** | Which Java code actually created and threw the original Throwable? |
| **Target outcome** | Did the method body execute, and did it return or throw? |
| **Observation site** | Which advisor saw the error as the Throwable traversed that layer? |
| **Final exception** | Which Throwable ultimately exited the Spring proxy to the caller? |

A target may throw `IllegalArgumentException`, yet an inner `@Around` translates it to `ServiceException` keeping the old error as `cause`. Then outer observers and callers see `ServiceException`; this **does not prove** the target threw the new exception type. Use `getCause()`, suppressed exceptions, and structured trace/correlation IDs to trace the origin. `JoinPoint.getSignature()` only identifies the advised join point, **not the throw site**.

## 4. Boundary of `@AfterThrowing`

~~~java
@AfterThrowing(
    pointcut = "execution(* demo.JobApi.execute(..))",
    throwing = "ex"
)
public void onFailure(RuntimeException ex) {
    System.out.println("AFTER_THROWING " + ex.getClass().getSimpleName());
}
~~~

This is a fragment inside a Spring `@Aspect`. `throwing = "ex"` must match the advice parameter name; the `RuntimeException` type binds only errors of that type (you can use `Throwable` if a broader scope is needed). Logging and returning `void` **does not swallow the error**.

According to Spring Framework, `@AfterThrowing` serves exceptions from the advised method execution, **not as a general callback for exceptions thrown by companion `@After`/`@AfterReturning` advice**. Which Throwables it observes also depends on advisor position, typed binding, and whether the continuation reached that advisor. If the observer itself throws an additional error, the caller may see the new error and lose the initial cause.

## 5. `@Around` observes the continuation, not the error origin

~~~java
@Around("execution(* demo.JobApi.execute(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (RuntimeException ex) {
        System.out.println("OUTER caught " + ex.getClass().getName());
        throw ex;
    }
}
~~~

When this is the outermost advisor, `catch` can receive errors from an inner `@Before`, the target, an inner `@AfterReturning`, `@After`, transaction commit, or another interceptor. The log `OUTER caught` only proves **the inner continuation failed**, not that the target body failed. If the outer `@Around` itself throws before `proceed()`, inner layers may never have run at all.

## 6. Complete Spring Framework demo: three distinct error origins

Environment:

- **Java 17+**
- **Maven 3.9+**
- **Spring Framework 6.2.12**
- **AspectJ Weaver 1.9.24**

Each concern lives in its own Spring `@Aspect` class with a distinct `@Order`, avoiding unguaranteed ordering between two advice methods of the same kind in one aspect. The project uses **plain Spring Framework**, requiring no Spring Boot, DB, or server.

### 6.1. Structure

~~~text
spring-aop-exception-origin/
├── pom.xml
└── src/main/java/demo/
    ├── JobApi.java
    ├── Failures.java
    ├── JobService.java
    ├── OuterTraceAspect.java
    ├── BeforeGateAspect.java
    ├── AfterResultAspect.java
    ├── TargetFailureAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-exception-origin</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` pulls in the required Spring AOP modules; `aspectjweaver` provides annotations and pointcut expressions for Spring `@AspectJ` style. Neither the AspectJ compiler nor weaving is used here.

### 6.3. JobApi.java

~~~java
package demo;

public interface JobApi {
    String execute(String scenario);
}
~~~

The interface ensures callers can retrieve the bean by type `JobApi`. Spring AOP can use a JDK dynamic proxy when an implementation has an interface.

### 6.4. Failures.java

~~~java
package demo;

public final class Failures {

    private Failures() {
    }

    public static final class TargetFailure
            extends RuntimeException {
    }

    public static final class BeforeFailure
            extends RuntimeException {
    }

    public static final class AfterFailure
            extends RuntimeException {
    }
}
~~~

Three distinct custom exceptions help the demo identify the **throw origin by design**. In production, a type name does not by itself prove the throw origin: any component could throw the same type, or an exception could be translated.

### 6.5. JobService.java

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class JobService implements JobApi {

    @Override
    public String execute(String scenario) {
        System.out.println("TARGET enter " + scenario);

        if ("TARGET".equals(scenario)) {
            throw new Failures.TargetFailure();
        }

        return "done:" + scenario;
    }
}
~~~

The target throws only in the `TARGET` scenario. For `AFTER`, it **has already run and returned normally** before another advice can cause an exception.

### 6.6. OuterTraceAspect.java

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(0)
public class OuterTraceAspect {

    @Around("execution(* demo.JobApi.execute(..))")
    public Object observe(ProceedingJoinPoint pjp) throws Throwable {
        String scenario = (String) pjp.getArgs()[0];

        System.out.println("OUTER enter " + scenario);

        try {
            Object result = pjp.proceed();
            System.out.println("OUTER success " + scenario);
            return result;
        } catch (RuntimeException ex) {
            System.out.println(
                    "OUTER caught " + ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
~~~

Because `@Order(0)` has higher precedence than the remaining aspects in the demo, outer around sits outside and observes **before**, **target**, and **after-returning** in the continuation.

`pjp.proceed()` is called exactly once; the advice does not short-circuit. The `catch` here intentionally catches only the `RuntimeException`s of the three scenarios, not a general policy for catching `Error` or checked exceptions.

### 6.7. BeforeGateAspect.java

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(10)
public class BeforeGateAspect {

    @Before("execution(* demo.JobApi.execute(..))")
    public void before(JoinPoint jp) {
        String scenario = (String) jp.getArgs()[0];
        System.out.println("BEFORE enter " + scenario);

        if ("BEFORE".equals(scenario)) {
            throw new Failures.BeforeFailure();
        }
    }
}
~~~

With input `BEFORE`, the advice throws **before the target or inner advisors are reached**. The caller still sees an exception when calling `JobApi`, yet the target threw nothing because the target never ran.

### 6.8. AfterResultAspect.java

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(20)
public class AfterResultAspect {

    @AfterReturning(
        pointcut = "execution(* demo.JobApi.execute(..))",
        returning = "result"
    )
    public void after(JoinPoint jp, Object result) {
        String scenario = (String) jp.getArgs()[0];
        System.out.println("AFTER_RETURNING " + scenario);

        if ("AFTER".equals(scenario)) {
            throw new Failures.AfterFailure();
        }
    }
}
~~~

With `AFTER`, the target returns `done:AFTER` and then the advice throws `AfterFailure`. Thus **the target succeeded, yet the proxy invocation failed**. `returning="result"` binds the return value to the parameter of the same name; `Object` accepts `String` in this project.

### 6.9. TargetFailureAspect.java

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(30)
public class TargetFailureAspect {

    @AfterThrowing(
        pointcut = "execution(* demo.JobApi.execute(..))",
        throwing = "ex"
    )
    public void afterThrow(JoinPoint jp, RuntimeException ex) {
        System.out.println(
                "AFTER_THROWING " + ex.getClass().getSimpleName());
    }
}
~~~

This aspect is placed **inside** the demo's before and after-returning aspects:

- `TARGET`: target throws, exception passes through `@AfterThrowing`, log appears.
- `BEFORE`: call is blocked before reaching this advisor, so no log.
- `AFTER`: this advisor already completed normally when the target returned; the after-returning advice outside it threw the exception afterwards, so no log.
- `OK`: target returns normally, so no log.

This is the **result of the ordering designed and verified in the demo**, not a claim that every `@AfterThrowing` automatically knows the throw origin in every Spring context.

### 6.10. AppConfig.java

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
~~~

`@Aspect` does not register an object as a bean by itself. Each aspect in the demo also carries `@Component`, and `@ComponentScan` covers the package. `@EnableAspectJAutoProxy` enables the proxy-creation infrastructure.

### 6.11. App.java

~~~java
package demo;

import java.util.List;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JobApi jobs = context.getBean(JobApi.class);
            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(jobs));

            for (String scenario :
                    List.of("OK", "TARGET", "BEFORE", "AFTER")) {
                System.out.println("=== " + scenario + " ===");

                try {
                    String result = jobs.execute(scenario);
                    System.out.println("CALLER result " + result);
                } catch (RuntimeException ex) {
                    System.out.println(
                            "CALLER caught " +
                            ex.getClass().getSimpleName());
                }
            }
        }
    }
}
~~~

The program retrieves the **Spring-managed proxy**; it does not instantiate `JobService` with `new`. Each exception is caught in the caller so subsequent scenarios still run.

Run in the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

### 6.12. Expected logical stdout

~~~text
IS_PROXY true
=== OK ===
OUTER enter OK
BEFORE enter OK
TARGET enter OK
AFTER_RETURNING OK
OUTER success OK
CALLER result done:OK
=== TARGET ===
OUTER enter TARGET
BEFORE enter TARGET
TARGET enter TARGET
AFTER_THROWING TargetFailure
OUTER caught TargetFailure
CALLER caught TargetFailure
=== BEFORE ===
OUTER enter BEFORE
BEFORE enter BEFORE
OUTER caught BeforeFailure
CALLER caught BeforeFailure
=== AFTER ===
OUTER enter AFTER
BEFORE enter AFTER
TARGET enter AFTER
AFTER_RETURNING AFTER
OUTER caught AfterFailure
CALLER caught AfterFailure
~~~

This is the **expected logical stdout**, excluding Maven/Spring's own logs. The aspects have distinct precedences so the output does not depend on unspecified ordering of multiple advice methods of the same kind in the same class.

### 6.13. Result deduction table

| Scenario | `@Before` | Target ran | Target threw | `@AfterReturning` | Inner `@AfterThrowing` log | Caller |
| --- | --- | --- | --- | --- | --- | --- |
| **OK** | ran | yes | no | ran | no | `done:OK` |
| **TARGET** | ran | yes | yes | did not run | **TargetFailure** | `TargetFailure` |
| **BEFORE** | ran then threw | **no** | no | did not run | no | `BeforeFailure` |
| **AFTER** | ran | yes and returned | no | ran then threw | no | `AfterFailure` |

All three error branches have `OUTER caught ...`. Thus **the outer `@Around` observes errors from multiple components**, while the inner `@AfterThrowing` observes only target errors in this controlled configuration.

## 7. Logging/metrics accurately by phase

Do not use a single `target_exception_count` counter incremented whenever a generic outer `@Around` catches an exception. A more informative approach:

| Metadata field | Meaning |
| --- | --- |
| `proxy.outcome` | Did the caller receive a result or an exception? |
| `target.reached` | Is there evidence that execution entered the target body? |
| `target.outcome` | Did the target body return or throw? |
| `advice.phase` | before, after-returning, after-throwing, around, transaction, etc. |
| `exception.type` | Observed exception class |
| `exception.cause` | Cause chain if wrapped |
| `operation.id` | Correlation ID of the logical invocation |
| `advisor.order` | Relevant position/precedence |

`pjp.getTarget()` identifies the target object, **not proof that the target method ran**. `MethodSignature.getMethod()` tells the method name/signature, **not where the exception originated**. If you need certainty that the target executed, use instrumentation **inside the target or at the target boundary**, or integration-test with a spy/counter.

## 8. @Around transforming, swallowing, or preserving exceptions

### 8.1. Translating and preserving cause

~~~java
@Around("execution(* demo.JobApi.execute(..))")
public Object translate(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (Failures.TargetFailure ex) {
        throw new IllegalStateException("Service failed", ex);
    }
}
~~~

This fragment shows how an aspect **creates a new exception** while preserving the original under `getCause()`. An outer observer will directly see `IllegalStateException`, not `TargetFailure`.

### 8.2. Swallowing the exception and returning a fallback

~~~java
@Around("execution(* demo.JobApi.execute(..))")
public Object fallback(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (Failures.TargetFailure ex) {
        return "fallback";
    }
}
~~~

If the fallback is allowed by contract, the caller may see **proxy success** even though the target threw an error. Never record `target.success=true` based solely on an outer `@Around`'s outcome.

### 8.3. A new error inside finally

~~~java
try {
    return pjp.proceed();
} finally {
    auditWriter.write();
}
~~~

This is a fragment. If `pjp.proceed()` throws error X yet `auditWriter.write()` also throws error Y from `finally`, Y can **mask X**. If auditing is best-effort, catch the audit error separately to preserve the original exception; if auditing is mandatory, define explicit error-priority rules.

**Do not paste these three fragments all at once into the section 6 demo** if you want to preserve the expected stdout: they are alternative patterns for practice.

## 9. @AfterThrowing throwing itself can also mask the original error

Example:

~~~java
@AfterThrowing(
    pointcut = "execution(* demo.JobApi.execute(..))",
    throwing = "original"
)
public void audit(RuntimeException original) {
    auditWriter.write(original);
}
~~~

If the target throws `TargetFailure`, yet `auditWriter.write` throws `AuditStorageFailure`, the caller may receive `AuditStorageFailure` instead of the initial error. `@AfterThrowing` is not a harmless observer if the code inside it can throw.

For a policy that **preserves the business error**, you can use this fragment:

~~~java
try {
    return pjp.proceed();
} catch (RuntimeException original) {
    try {
        auditWriter.write(original);
    } catch (RuntimeException auditError) {
        original.addSuppressed(auditError);
    }
    throw original;
}
~~~

This pattern keeps `original` and attaches the audit error to the suppressed list. However, it does not fit every system, especially where an audit failure must change the business outcome; define the policy clearly.

A recorder Spring bean called by an aspect must also **lie outside that aspect's own pointcut** to avoid recursive advice loops through the collaborator.

## 10. Transactions and exception translation: errors after the target

In Spring, alongside custom `@Aspect` beans, there are interceptors such as:

- `TransactionInterceptor` for matching `@Transactional` methods.
- Method security advisors.
- Spring persistence exception translation for configured repositories.
- Cache/retry advisors provided by the application or libraries.

For example:

~~~text
Client -> OuterTraceAspect -> TransactionInterceptor
                                   |
                                   +-- begin transaction
                                   +-- Target method RETURN
                                   +-- COMMIT throws exception
                    |
                    +-- OuterTraceAspect catches commit error
~~~

The target body **may have returned normally**, yet the proxy returns an error because commit failed. Therefore distinguish:

- `target.body.success`
- `transaction.commit.success`
- `proxy.invocation.success`

They are not always the same. If `@AfterReturning` sits **inside** the transaction advisor, the callback may run before commit; if it sits **outside**, it can observe a post-transaction outcome. Verify this order against the real context.

Spring exception translation can also cause callers to see `DataAccessException` instead of the low-level exception raised inside a repository, depending on translators and configuration. Do not assert that every `@Repository` automatically translates every exception without the proper advisor/translator configured.

## 11. Java checked exceptions and JDK proxies

Interface:

~~~java
public interface FileApi {
    String read(String path) throws java.io.IOException;
}
~~~

This is an interface fragment, not a file from the section 6 demo. If the target throws a declared `IOException`, callers can catch that type normally.

If an advice throws a **checked exception not belonging to the method's throws contract**, a JDK dynamic proxy can wrap it in `UndeclaredThrowableException`. Then the final exception differs from the one thrown by the advice, and callers would have to inspect the cause carefully.

Practical guidelines:

- Prefer exception types compatible with the Java interface contract.
- Do not use `catch(Throwable)` and blindly retry everything.
- Do not assume a single exception class at the caller identifies where the error started.
- When logging, retain cause/suppressed data if domain rules permit.
- Test both JDK and CGLIB proxies if the application depends on proxy type.

The complete demo uses only **unchecked exceptions** for easy observation without mixing in checked-exception mechanics.

## 12. Short-circuiting and self-invocation

An outer `@Around` can intentionally throw an error or return a fallback **without calling `proceed()`**:

~~~java
if (maintenanceMode) {
    throw new IllegalStateException("Rejected by outer advice");
}
return pjp.proceed();
~~~

This is a fragment. In the maintenance branch, inner advisors and the target are never reached. An inner `@AfterThrowing` will **not observe the error thrown by the outer advice before proceed**.

Conversely, self-invocation:

~~~java
public void outer() {
    this.inner();
}
~~~

can **bypass the Spring proxy**, so advice for `inner` does not run automatically, even though `inner`'s body still executes. This is not `@Around` short-circuiting; here the AOP join point for `inner` **was never intercepted by the proxy in the first place**.

Distinguish the two situations:

1. **Did not enter proxy**: advice does not run.
2. **Entered proxy then threw before target**: some advice ran, target did not run.

## 13. Advice ordering is part of the conclusion

In Spring `@AspectJ` style:

- `@Order` or `Ordered` configures precedence across aspects.
- Smaller numbers generally indicate higher precedence.
- On entry, outer aspects run first.
- On exit, inner aspects finish before outer aspects when continuation runs normally.
- Two advice methods **of the same kind in the same `@Aspect` class** matching the same join point have no guaranteed source order.
- `@After` has finally semantics; it does not mean "always runs before `@AfterReturning`" solely due to cross-kind precedence.

An outer observer can see more error sources than an inner observer. Changing `@Order` can change which exceptions an observer sees, so tests must combine **source, type, order, and invocation path**.

## 14. Debugging checklist when a proxy invocation fails

1. Confirm whether the caller invokes a **Spring-managed proxy**; `AopUtils.isAopProxy(bean)` is a helpful first check.
2. List **all active advisors**: custom aspects, transaction, security, cache, and translation.
3. Determine actual precedence; do not infer it from method order in source.
4. Record **target entry** and **target exit** if you need to confirm whether the target body ran.
5. Place an outer observer for the **proxy outcome**, while logging stages of suspected advice.
6. Test target throw, before throw, and after-returning throw separately.
7. Inspect `getCause()` / suppressed exceptions if wrapping occurred.
8. Check transaction commit/rollback and external side effects.
9. Never replace the original exception with an unintended metrics/audit error.
10. Categorize logs: target failure, advice failure, transaction failure, and proxy outcome.

## 15. Common mistakes

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Logged "target error" when before advice blocked permission | Attributing every proxy exception to the target | Track target-entry and phase |
| Target printed "return" yet caller received an exception | AfterReturning/transaction interceptor threw after target | Inspect exit-path advisors |
| `@AfterThrowing` did not log even though caller caught error | Exception arose outside advisor scope or was filtered by type | Check `@Order` and binding type |
| `@AfterThrowing` did not catch error from another `@AfterReturning` | Not a generic catch for companion advice | Use an outer `@Around` if you need to observe the continuation |
| Outer `@Around` saw TargetFailure yet caller saw ServiceException | Inner advice translated the error | Preserve cause and log the exception chain |
| Caller received success even though target failed | Inner around returned a fallback | Separate proxy outcome from target outcome |
| Audit error masked business failure | Audit advice threw a secondary exception | Priority policy, cause/suppressed |
| Different exception type when JDK proxy is used | Undeclared checked exception wrapping | Fix contract and inspect cause |
| Advisors ran in the wrong order after refactoring | `@Order` unclear or duplicated | Configure precedence and integration test |
| No advice seen on self-call | `this.method()` bypasses proxy | Refactor into a Spring bean dependency |
| Logging aspect loops when calling recorder | Recorder also matches pointcut | Exclude technical collaborators |

## 16. Tests you should have

For the section 6 demo:

- **OK:** lines `TARGET enter OK`, `AFTER_RETURNING OK`, and caller receives `done:OK`.
- **TARGET:** target entry, `AFTER_THROWING TargetFailure`, and caller catches `TargetFailure`.
- **BEFORE:** `BEFORE enter BEFORE` appears, but **not** `TARGET enter BEFORE`.
- **AFTER:** `TARGET enter AFTER`, `AFTER_RETURNING AFTER` appear, yet caller catches `AfterFailure`.
- Outer around records all three exceptions.
- `TargetFailureAspect` does not log `BeforeFailure` or `AfterFailure` in the demo's ordering.
- If order changes or advisors are added, expected events must be re-evaluated for the new chain.

A code-fragment check:

~~~java
try {
    jobs.execute("BEFORE");
    throw new AssertionError("Should fail in before advice");
} catch (Failures.BeforeFailure expected) {
    // Use a spy/counter to assert that target was not invoked.
}
~~~

This is a test fragment, not a standalone class. Do not merely assert the exception type and assume the target definitely did not run; instrument the target with a counter/spy in an integration test for proof.

## 17. Self-assessment questions

**1. Does an outer `@Around` catching a RuntimeException prove the target threw it?**

No. An inner before, after-returning, or transaction advisor could also have thrown.

**2. Is `@AfterThrowing` a generic catcher for all advice?**

No. Spring defines it for method execution exceptions and notes it is not a general callback for errors from companion after/after-returning advice.

**3. If `@Before` throws before the target, does the target run?**

No, not through that blocked invocation.

**4. Target returns normally yet `@AfterReturning` throws; what does the proxy return?**

The proxy can return the advice's exception, even though the target threw nothing.

**5. Does a `void` `@AfterThrowing` swallow the target error?**

No. The error continues propagating unless handled by an outer layer.

**6. When you want to catch, wrap, retry, or fallback, which advice do you use?**

`@Around`, with `proceed()` and an explicit error-handling policy.

**7. Why does TargetFailureAspect in the example see only target errors?**

Because `@Order(30)` places it inside the before and after-returning aspects: BEFORE errors occur before reaching it, and AFTER errors occur after it has finished normally.

**8. Is a transaction commit failure after target return a target-body exception?**

No. It is an exception at the transaction interceptor/commit boundary.

**9. Why does exception cause matter?**

Advice can wrap errors; cause preserves information about the initial failure.

**10. Why shouldn't exception names alone determine the origin every time?**

The same type can be thrown by multiple layers, or an exception can be translated/wrapped.

## 18. Official Spring Framework documentation

- **Spring Framework — Declaring Advice, After Throwing, and Ordering:** https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html
- **Spring Framework — AOP Concepts:** https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html
- **Spring Framework — Advice API:** https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html
- **Spring Framework — Proxying Mechanisms:** https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Framework — @AspectJ Support:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- **Spring Framework — Declarative Transaction Management:** https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html

**Conclusion:** An exception exiting a **Spring AOP proxy** does not necessarily come from the **target method**. `@Before` can block before the target; `@AfterReturning` can fail after the target; `@Around` can observe, translate, swallow, or replace exceptions; transactions and other advisors also participate. To classify failures accurately, **place observers at appropriate boundaries, control `@Order`, mark target execution, and preserve exception causes** rather than guessing from a single catch or log line.
