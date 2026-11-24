# Do Not Infer Execution Order from Method Position in Spring Aspect Source Code

## 1. Core Takeaway

In Spring AOP, having one advice method placed **above** another advice method in the same `@Aspect` class **does not guarantee** the first method will run before the second.

Specifically, **two advice methods of the same type** inside **the same `@Aspect`** that both match a method execution have **undefined order**. Spring Framework cannot use Java source declaration order as a contract, because Java reflection on `javac`-compiled bytecode does not provide a reliable source declaration order.

Example:

```java
@Aspect
public class DangerousAuditAspect {
    @Before("execution(* com.example.ordering.TaskService.run(..))")
    public void validate() {
        System.out.println("VALIDATE");
    }

    @Before("execution(* com.example.ordering.TaskService.run(..))")
    public void audit() {
        System.out.println("AUDIT");
    }
}
```

**You must not conclude** `VALIDATE` will always appear before `AUDIT` merely because `validate()` is declared before `audit()` in the Java file. This is a **fragment illustrating a faulty ordering design**, not a standalone application. If auditing must strictly happen only after validation, an ordering mechanism with an explicit contract is required.

To establish ordering:

- When operations belong to **the same responsibility**, combine them into **one advice method** and call helpers in explicit Java sequence.
- When they belong to **independent cross-cutting concerns**, split them into **multiple aspect classes** and use Spring `@Order` or `Ordered`.
- When advice methods are **of different types** in the same `@Aspect`, understand **advice-type precedence rules** and `@After`'s `finally` semantics rather than guessing from declaration position.
- With **Spring XML AOP** configuration, recognize the exception: the order of advice elements within **the same `<aop:aspect>`** does matter, unlike Java `@Aspect` declaration order.

This lesson focuses exclusively on **Spring Aspects using `@AspectJ` annotations on Spring-managed beans through a Spring AOP proxy** and the related difference in Spring XML configuration; it does not dive into standalone AspectJ compile-time/load-time weaving.

## 2. Why Is Source Position Not an Ordering Rule?

Java code may display methods in a crystal-clear order inside an IDE, yet Spring reads annotation metadata from the class loaded by the JVM. `Class.getDeclaredMethods()` and similar reflection mechanisms **make no promise to preserve method order from the `.java` file**.

The following **must never** be used as a basis for advice ordering:

1. Method line numbers in source code.
2. Class method order shown by an IDE.
3. Alphabetical method names, such as `aValidate()` before `zAudit()`.
4. Order of `@Bean` methods in `@Configuration`.
5. Order in which classes are discovered by `@ComponentScan`.
6. Import order of aspect classes.
7. Log order observed in **a single test run** without an ordering contract.

Swapping two methods in a class and seeing logs "look right" is not a reliable way to control Spring AOP. A different JDK, compiler, Spring version, or class layout can yield different results if you rely on ordering the framework never promised.

**Exception to note clearly:** Starting in **5.2.7**, Spring Framework has a precedence rule among **advice of different types in the same class**. That **does not** guarantee ordering between two `@Before` or two `@After` methods in the same `@Aspect`.

## 3. Order on the Way In and Way Out Differ

Spring proxy AOP uses an interceptor chain. Picture two `@Around` advice methods in two different aspects:

```text
Caller
  -> Spring AOP proxy
     -> OuterAspect.around()       @Order(1)
        -> InnerAspect.around()    @Order(10)
           -> Target.run()
        <- InnerAspect returns
     <- OuterAspect returns
  <- Caller receives return value
```

In Spring, **a smaller `@Order` value means higher precedence**. Higher-precedence aspects execute **earlier on the way in** and **later on the way out**. This is a nested model, not a one-way linear callback list.

```text
[OUTER] enter
[INNER] enter
[TARGET] run
[INNER] exit
[OUTER] exit
```

When the caller receives an exception, the exit path likewise unwinds in reverse:

```text
[OUTER] enter
[INNER] enter
[TARGET] throw
[INNER] catch/finally
[OUTER] catch/finally
```

Thus, **you cannot read `@Order(1)` and conclude every log line from that aspect will always appear before every log line from `@Order(10)`**.

### `@Order` Applies to Aspect Classes

```java
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(1)
public class HighPriorityAspect {
    // Advice belonging to this aspect.
}
```

Another aspect:

```java
@Aspect
@Order(10)
public class LowPriorityAspect {
    // Advice belonging to this aspect.
}
```

These are class fragments. Ordering lives at the **aspect level**, not as a promise that placing `@Order` on individual advice methods will order two `@Before` methods inside the same class.

Spring also supports aspect beans implementing `org.springframework.core.Ordered`:

```java
@Aspect
public class HighPriorityAspect implements org.springframework.core.Ordered {
    @Override
    public int getOrder() {
        return 1;
    }
}
```

Choose **one clear ordering mechanism** for your aspects. If multiple aspects share the same order yet require mandatory relative ordering, use **distinct order values** and integration-test the result.

## 4. Ordering of Different Advice Types in the Same `@Aspect`

Per Spring Framework 6.x documentation, when multiple advice methods **of different types** in **the same `@Aspect` class** match a join point, precedence from **highest to lowest** is:

| Precedence | Advice | Purpose |
| --- | --- | --- |
| 1 | `@Around` | Wraps the invocation; can call `proceed()`. |
| 2 | `@Before` | Runs before inner method execution. |
| 3 | `@After` | After-finally advice. |
| 4 | `@AfterReturning` | Observes normal return. |
| 5 | `@AfterThrowing` | Observes exception path. |

**Note on `@After`:** although listed before `@AfterReturning`/`@AfterThrowing` in the precedence table, due to **after-finally** semantics `@After` **actually executes after** `@AfterReturning` or `@AfterThrowing` in the same aspect, much like a Java `finally` block.

Example:

```java
@Aspect
public class OutcomeAspect {
    @After("execution(* com.example.ordering.TaskService.run(..))")
    public void cleanup() {
        System.out.println("FINALLY");
    }

    @AfterReturning("execution(* com.example.ordering.TaskService.run(..))")
    public void success() {
        System.out.println("SUCCESS");
    }

    @Before("execution(* com.example.ordering.TaskService.run(..))")
    public void before() {
        System.out.println("BEFORE");
    }
}
```

Notice `cleanup()` is intentionally written **before** `before()` in the source. On a normally returning method with no extra advisors altering control flow, the main events of the aspect still logically occur as:

```text
BEFORE
target execution
SUCCESS
FINALLY
```

When the target throws an exception, `@AfterReturning` does not run; a compatible `@AfterThrowing` (if present) runs, and then `@After` finally runs.

**Distinguish the two rules:** precedence among **different advice types** in the same aspect is guaranteed by Spring since 5.2.7; among **two advice methods of the same type** in the same aspect, it is **undefined**. Do not lump both together into the false conclusion "no advice in the same class has any ordering."

## 5. Two `@Before` Methods in the Same Class: How to Fix the Design

Suppose a business rule requires **validate before audit**. Changing Java method positions or names only edits source text; it creates no ordering constraint in Spring.

**If they belong to one responsibility**, use a single advice method orchestrating helpers in explicit sequence:

```java
@Before("execution(* com.example.ordering.TaskService.run(..))")
public void before(JoinPoint jp) {
    validate(jp.getArgs());
    audit(jp.getSignature().getName());
}
```

This is a fragment inside an `@Aspect` class, assuming two helpers `validate` and `audit` are defined in the same class. If validation throws an error, auditing and the target do not proceed unless the code explicitly handles the exception.

**If they are two independent responsibilities**, declare two separate `@Aspect` classes: `ValidationAspect @Order(10)` and `AuditAspect @Order(20)`, each with a `@Before` matching the same method and registered as Spring beans. Spring selects `ValidationAspect` first on the way in unless advice halts the chain.

Reordering `@Bean` methods, naming methods alphabetically, or adding `@Order` onto an advice method inside the same aspect cannot replace these two approaches. The lesson on **limits among same-type advice** explores both options and testing in depth.

## 6. Runnable Maven/Java 17+ Example: Two `@Around` and One Outcome Aspect

The example uses **Spring Framework 6.1.14**, **AspectJ Weaver 1.9.22.1**, **JDK 17+**, and Maven. The code uses only **proxy-based Spring AOP**, requiring no AspectJ compile-time/load-time weaving.

Design:

- `OuterAspect` uses `@Around`, `@Order(1)`.
- `InnerAspect` uses `@Around`, `@Order(10)`.
- `OutcomeAspect` uses `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, and `@Order(20)`.
- Advice methods in `OutcomeAspect` are written **out of execution order** to prove source position does not decide.
- `TaskService.run("ok")` returns normally; `run("fail")` throws `IllegalStateException`.
- The client calls only on the **bean obtained from `ApplicationContext`**, so calls go through the Spring proxy.

### 6.1. Directory Structure

```text
spring-aspect-order/
├── pom.xml
└── src/main/java/com/example/ordering/
    ├── TaskService.java
    ├── OuterAspect.java
    ├── InnerAspect.java
    ├── OutcomeAspect.java
    ├── AppConfig.java
    └── DemoApp.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aspect-order</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides `ApplicationContext` and the relevant Spring AOP dependencies in the example's dependency tree; `aspectjweaver` enables Spring to parse `@AspectJ` pointcut expressions.

### 6.3. `src/main/java/com/example/ordering/TaskService.java`

```java
package com.example.ordering;

public class TaskService {
    public String run(String mode) {
        System.out.println("[TARGET] " + mode);
        if ("fail".equals(mode)) {
            throw new IllegalStateException("simulated");
        }
        return "ok:" + mode;
    }
}
```

The target is a class with a non-`final` public method, allowing Spring's class-based proxy to intercept it.

### 6.4. `src/main/java/com/example/ordering/OuterAspect.java`

```java
package com.example.ordering;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(1)
public class OuterAspect {
    @Around("execution(public * com.example.ordering.TaskService.run(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[OUTER] enter");
        try {
            Object result = pjp.proceed();
            System.out.println("[OUTER] return");
            return result;
        } catch (Throwable error) {
            System.out.println("[OUTER] throw "
                    + error.getClass().getSimpleName());
            throw error;
        }
    }
}
```

`@Order(1)` gives the outer aspect the highest precedence in the demo. The `return` print statement sits **after `proceed()`**, so it runs on the way out rather than at the start of the chain.

### 6.5. `src/main/java/com/example/ordering/InnerAspect.java`

```java
package com.example.ordering;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class InnerAspect {
    @Around("execution(public * com.example.ordering.TaskService.run(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[INNER] enter");
        try {
            Object result = pjp.proceed();
            System.out.println("[INNER] return");
            return result;
        } catch (Throwable error) {
            System.out.println("[INNER] throw "
                    + error.getClass().getSimpleName());
            throw error;
        }
    }
}
```

The inner aspect runs after `OuterAspect` on the way in and before `OuterAspect` on the way out.

### 6.6. `src/main/java/com/example/ordering/OutcomeAspect.java`

```java
package com.example.ordering;

import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;

@Aspect
@Order(20)
public class OutcomeAspect {
    // Finally method intentionally placed FIRST in the file.
    @After("execution(public * com.example.ordering.TaskService.run(..))")
    public void onFinally() {
        System.out.println("[EVENT] finally");
    }

    @AfterThrowing(
        pointcut = "execution(public * com.example.ordering.TaskService.run(..))",
        throwing = "error",
        argNames = "error"
    )
    public void onError(Throwable error) {
        System.out.println("[EVENT] after-throwing "
                + error.getClass().getSimpleName());
    }

    @AfterReturning("execution(public * com.example.ordering.TaskService.run(..))")
    public void onSuccess() {
        System.out.println("[EVENT] after-returning");
    }

    // Before method intentionally placed LAST in the file.
    @Before("execution(public * com.example.ordering.TaskService.run(..))")
    public void before() {
        System.out.println("[EVENT] before");
    }
}
```

**Different** advice types follow Spring's defined precedence semantics. On normal return: `before` → target → `after-returning` → `finally`. On exception: `before` → target throw → `after-throwing` → `finally`. No assumptions about method order in the file are needed.

### 6.7. `src/main/java/com/example/ordering/AppConfig.java`

```java
package com.example.ordering;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public TaskService taskService() {
        return new TaskService();
    }

    @Bean
    public OuterAspect outerAspect() {
        return new OuterAspect();
    }

    @Bean
    public InnerAspect innerAspect() {
        return new InnerAspect();
    }

    @Bean
    public OutcomeAspect outcomeAspect() {
        return new OutcomeAspect();
    }
}
```

`@EnableAspectJAutoProxy` turns on Spring's auto-proxy infrastructure. `proxyTargetClass=true` selects CGLIB for `TaskService`, which has no business interface. The `@Aspect` classes are registered as **Spring beans** via `@Bean`; `@Aspect` alone does not register a bean.

The order of `@Bean` definitions in `AppConfig` **is not** what creates advice ordering. Do not rearrange those `@Bean` methods to control the execution chain.

### 6.8. `src/main/java/com/example/ordering/DemoApp.java`

```java
package com.example.ordering;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            TaskService service = context.getBean(TaskService.class);
            System.out.println("isAopProxy="
                    + AopUtils.isAopProxy(service));

            System.out.println("[CALLER] success");
            String result = service.run("ok");
            System.out.println("[CALLER] result=" + result);

            System.out.println("[CALLER] failure");
            try {
                service.run("fail");
            } catch (IllegalStateException ex) {
                System.out.println("[CALLER] caught " + ex.getMessage());
            }
        }
    }
}
```

### 6.9. Running and Expected Stdout

In the directory containing `pom.xml` with JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.ordering.DemoApp
```

Output printed by the code itself, ignoring any Maven/Spring logs if present:

```text
isAopProxy=true
[CALLER] success
[OUTER] enter
[INNER] enter
[EVENT] before
[TARGET] ok
[EVENT] after-returning
[EVENT] finally
[INNER] return
[OUTER] return
[CALLER] result=ok:ok
[CALLER] failure
[OUTER] enter
[INNER] enter
[EVENT] before
[TARGET] fail
[EVENT] after-throwing IllegalStateException
[EVENT] finally
[INNER] throw IllegalStateException
[OUTER] throw IllegalStateException
[CALLER] caught simulated
```

Explanation:

1. `OuterAspect @Order(1)` wraps `InnerAspect @Order(10)`, and both wrap `OutcomeAspect @Order(20)`.
2. `[EVENT] before` appears **before target**, even though `before()` is written at the **bottom of the class**.
3. `[EVENT] finally` appears **after after-returning** on normal return, even though `onFinally()` is written at the top of the class.
4. The exception case runs `@AfterThrowing` and `@After`, not `@AfterReturning`.
5. Catch blocks in `InnerAspect` and then `OuterAspect` execute in **unwinding** order; higher precedence does **not** mean the outer aspect's final log prints early.
6. All calls go through the **Spring AOP proxy**; if a client calls `new TaskService()` directly, Spring advice does not apply as in the demo.

The output is derived from Spring 6.1 rules and the code shown; **it is not a live Maven run executed here**. When deploying a project, verify on your target Spring/JDK versions.

## 7. XML Configuration Exception: Order of Advice Elements Inside `<aop:aspect>`

Never say "Spring **never** uses declaration order." For the **Spring AOP XML schema**, the official documentation explicitly states:

> Within a single `<aop:aspect>`, precedence among advice declarations is determined by the order of the **XML advice elements** (from first to last).

Example:

```xml
<aop:config>
    <aop:pointcut id="operation"
        expression="execution(* com.example.ordering.TaskService.run(..))"/>

    <aop:aspect ref="xmlLoggingAspect">
        <aop:around method="around" pointcut-ref="operation"/>
        <aop:before method="before" pointcut-ref="operation"/>
    </aop:aspect>
</aop:config>
```

This is an **XML fragment**, omitting the `beans` root, namespaces/schema declarations, and `xmlLoggingAspect` bean. Inside this `<aop:aspect>`, `<aop:around>` appears before `<aop:before>` and is interpreted by Spring XML AOP as having higher precedence.

That is **fundamentally different** from two Java methods annotated with `@Before` inside the same `@Aspect`; you cannot apply the XML rule in reverse to annotation-style aspects.

Across multiple XML aspects, Spring also supports `order` on `<aop:aspect>` or `@Order`/`Ordered` on the backing aspect bean as supported. `<aop:advisor>` also has an `order` attribute. When a project mixes Java `@Aspect` and XML advisors, inspect the **entire advisor chain in the same `ApplicationContext`**, rather than inferring from text position in one file.

## 8. When `@Transactional`, Caching, or Security Advice Are Present

A service can simultaneously have `@Transactional`, `@Cacheable`, method security, and custom Spring `@Aspect` beans applied. Ordering here is not decided by annotation placement in source code.

Example:

```java
@Transactional
public String pay(String paymentId) {
    // ...
}
```

and:

```java
@Aspect
@Order(10)
public class AuditAspect {
    @Before("execution(* com.example.payment.PaymentService.pay(..))")
    public void audit() {
        // ...
    }
}
```

These are **fragments**, not a runnable demo. Answering "does audit happen before, inside, or after the transaction?" requires checking:

1. The order of the **transaction advisor** in the application.
2. The order of the custom audit aspect.
3. Whether a transaction already exists on the **caller**.
4. Which advisor wraps **outside** which.
5. Whether any `@Around` short-circuits, catches exceptions, or retries via multiple `proceed()` calls.

For instance, if a retry aspect sits **outside** the transaction interceptor and no ambient transaction exists, each retry attempt can get a new transaction boundary. If the transaction interceptor sits **outside** retry, multiple attempts can run within **one** transaction. Moving methods around inside an `@Aspect` class does nothing to answer this.

Do not treat `@AfterReturning` on a service as "after commit" in every configuration. If business logic genuinely needs an action **after transaction commit**, use Spring's appropriate transaction synchronization/event mechanism rather than guessing from advice names.

## 9. Other Cases With No Ordering Guarantee

### 9.1. Multiple Aspects Without `@Order`

Two different aspects match the same join point with **no declared precedence**: Spring docs state the order between them is **undefined**. To give an aspect explicit precedence, add `@Order` or implement `Ordered`.

### 9.2. Two Aspects With the Same Order Value

If both have `@Order(10)` and you still require A before B, equal values **do not express that requirement**. Assign distinct precedence values and test. Do not infer tie-breaking from bean names or registration order.

### 9.3. `@Around` Calling `proceed()` Multiple Times

An outer `@Around` can call `proceed()` **0, 1, or multiple times**. When called twice, inner advice and the target can run twice within **one** proxy invocation from the caller. This does not contradict `@Order`: precedence determines **chain position**, while `proceed()` logic determines **forwarding count**.

### 9.4. Exceptions Can Alter the Exit Path

If the target or inner advice throws an error, corresponding `@AfterReturning` methods may not run; `@AfterThrowing` and `@After` can run per contract. An outer `@Around` can catch and convert an exception into a return value, changing what advice outside it observes. Thus, seeing a different log sequence on the exception path than on the normal path is normal.

### 9.5. Beans/Proxies in Different Contexts

The auto-proxy creator is infrastructure of an **`ApplicationContext`**. If aspects are registered in one context while the target bean lives in another, `@Order` cannot make them apply together to one target. Before debugging order, confirm **the advice is actually present in the proxy chain**.

## 10. Verifying Precedence Through the Spring AOP Proxy

When debugging, start with the bean returned by the container:

```java
Object bean = context.getBean("taskService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

This is a fragment requiring an existing `context`. If `isAopProxy=false`, do not start debating which advice runs first: the aspect may not be a bean, the pointcut may not match, or the caller is not using the proxy.

For proxies implementing Spring `Advised`, you can inspect advisors:

```java
Object bean = context.getBean("taskService");

if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (org.springframework.aop.Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());
    }
}
```

This is an infrastructure inspection fragment. Advisor listing order aids diagnosis, yet **actual invocation tests** are needed to verify nested `@Around`, dynamic matching, exception paths, and `proceed()` counts.

### Using an Event Recorder in Integration Tests

An integration test should collect events into a list **local to the test invocation** and then assert the order:

```text
outer-enter
inner-enter
before
target
after-returning
finally
inner-return
outer-return
```

This is the right sequence for the demo's normal return branch. Do not use a shared mutable `ArrayList` in a singleton aspect while running concurrent tests and blame Spring ordering when events from multiple threads interleave.

Distinguish **request-level correlation IDs** from **advice invocations**: under parallel processing, logs from two requests can interleave even while the order within **each request** still follows precedence accurately.

A thorough test should verify:

- Success and exception branches.
- Two aspects with distinct `@Order`.
- The same join point matched by both aspects.
- Advice types and `@After` finally semantics.
- Actual target execution count.
- Calls going through the Spring-managed proxy, not via `new` or self-invocation.
- Presence of transaction/cache/security advisors if the application uses them.

## 11. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Swapped two `@Before` methods yet order stayed the same | Source order carries no precedence contract | Merge steps or split into aspects with `@Order`. |
| Test occasionally changes log order | Test relies on undefined order or events from multiple threads interleave | Declare explicit order and isolate event collectors per invocation. |
| `@Order(1)` aspect prints "exit" after `@Order(10)` | Higher-precedence aspect wraps **outside**, unwinding later | Distinguish way in from way out. |
| `@After` prints after `@AfterReturning` | `@After` is after-finally advice | This is Spring semantics; do not misread the type precedence table out of context. |
| Two different aspects have unpredictable order | Missing `@Order` or tied order | Set distinct `@Order` values when business logic depends on order. |
| `@Order` on an advice method gives unexpected results | Applied at the wrong level | Put `@Order` on the aspect class/bean or implement `Ordered`. |
| XML aspect behaves differently from Java `@Aspect` | XML advice elements derive precedence from declaration order | Apply the right rules for the right configuration style. |
| Reordered `@Bean` methods yet advice order stayed the same | Bean lifecycle is not advice chain precedence | Inspect advisors and use `@Order`. |
| `@AfterReturning` does not run on errors | Applies only to normal returns | Use `@AfterThrowing` for errors, `@After` for finally. |
| Target runs twice for one request | Outer `@Around` calls `proceed()` multiple times | Check retry/replay logic and side effects. |
| Custom audit runs outside transaction | Transaction advisor is positioned differently than assumed | Configure/test advisor precedence and transaction lifecycle. |
| No advice runs despite `@Aspect` on class | Aspect not a Spring bean, AOP disabled, pointcut mismatch, or caller bypassed proxy | Check context, `AopUtils`, call path, and bean registration. |

## 12. Checklist Before Merging Advice Ordering Changes

- [ ] Not relying on **method declaration position** in `.java` files.
- [ ] Not requiring a fixed order between **two advice methods of the same type in the same `@Aspect`**.
- [ ] If one concern needs a sequence, steps are combined into **one advice method**.
- [ ] If multiple concerns need precedence, **multiple aspects with explicit `@Order`/`Ordered`** are used.
- [ ] Remembered **smaller order value means higher precedence**.
- [ ] Understood `@Around` wraps outside and runs later during unwinding.
- [ ] Distinguished **advice-type precedence** rules from undefined ordering between same-type advice.
- [ ] Understood `@After` carries **finally semantics**, not just normal success.
- [ ] Distinguished Spring annotation-style from XML `<aop:aspect>` ordering.
- [ ] Checked transaction/cache/security advisors if sharing the proxy chain.
- [ ] Aspect and target reside in the right `ApplicationContext`; callers go through the Spring proxy.
- [ ] Integration tests verify ordering on both success and exception paths.
- [ ] If `@Around` can retry or short-circuit, verified `proceed()` counts.
- [ ] No tests depend on ordering that Spring **does not guarantee**.

### Official Documentation

- Spring Framework — **Declaring Advice / Advice Ordering**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework 6 Reference — **Advice type precedence since Spring 5.2.7**: https://docs.spring.io/spring-framework/docs/6.0.2/reference/html/core.html
- Spring Framework — **Schema-based AOP Support / XML ordering**: https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Spring Framework — **Enabling @AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring `@Order` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/annotation/Order.html

**Conclusion:** Spring AOP determines order through **advice type semantics, aspect precedence, and the interceptor chain**, not method placement in Java source. For **two advice methods of the same type in the same `@Aspect` class**, ordering is **undefined**; change the design instead of relying on an accidentally observed order.
