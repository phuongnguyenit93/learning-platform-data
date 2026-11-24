# Precedence via @Order and Ordered in Spring AOP

## 1. Lesson Objectives

A Spring bean can match multiple pieces of advice from different `@Aspect` classes. For example, before `TransferService.transfer()` executes a funds transfer, you may need auditing while also collecting metrics wrapping the same call. Without specifying order, having two aspects match the same Spring AOP join point **carries no guarantee that Spring will execute them in class declaration order, bean registration order, or source-file position**.

Spring Framework provides two familiar ways to define **precedence between aspects**:

- Annotating the aspect class with `@Order(value)` from `org.springframework.core.annotation.Order`.
- Having the aspect class implement the `org.springframework.core.Ordered` interface and return a value from `getOrder()`.

**Core rule: a smaller order value means higher precedence.** An aspect with order `10` is considered higher precedence than an aspect with order `20`. When both pieces of advice match a method invocation on a Spring proxy, the higher-precedence aspect typically runs **before entering** the inner chain, and **last when exiting**. This is an **outer-wrapper / inner-wrapper** model, not a sorting of all log lines in ascending numeric order.

This lesson focuses on **Spring Aspect / proxy-based Spring AOP** with these goals:

1. Distinguish execution order *on the way in* vs. *on the way out* of an invocation.
2. Correctly apply `@Order` and `Ordered.getOrder()` to **Spring-managed `@Aspect` beans**.
3. Understand `Ordered.HIGHEST_PRECEDENCE`, `Ordered.LOWEST_PRECEDENCE`, duplicate values, and the default when undeclared.
4. Distinguish **ordering between aspects** from **advice ordering within the same aspect**.
5. Recognize limitations involving Spring transaction/cache/security advisors, self-invocation, and short-circuiting.
6. Run a **Maven/Java 17+** example with one aspect using `@Order` and one using `Ordered`, verifying both success and exception paths.

**Special Note:** Only behavior specific to Spring Aspect/Spring AOP is explained here. General Aspect concepts are covered in other topics and are not repeated.

## 2. Where Does Spring Decide Order?

A Spring AOP call starts from the **proxy reference** the caller receives from the container, not a method on the original class instantiated directly with `new`.

~~~text
Caller
   |
   v
Spring AOP proxy
   |
   +--> Aspect A: @Around, order = 10
   |       |  A: enter
   |       v
   |    Aspect B: @Around, order = 20
   |       |  B: enter
   |       v
   |    TargetService.method()
   |       |
   |       v
   |       B: exit
   |       |
   |       v
   |       A: exit
   |
   v
Caller receives result/exception
~~~

In the diagram, both aspects have around advice and each calls `ProceedingJoinPoint.proceed()` once. Since **order 10 has higher precedence than order 20**, layer A wraps around B.

Importantly, **order belongs to the aspect/advisor**; it does not change method names, parameters, return values, or pointcuts. If B's pointcut does not match, B will not be in the chain regardless of its order value. If the caller does not go through the proxy, both pieces of advice can be bypassed.

### 2.1. "Runs Before" and "Runs After" Depend on Direction

Suppose A has order `10` and B has order `20`:

| Moment | Higher-precedence aspect: A(10) | Lower-precedence aspect: B(20) |
| --- | --- | --- |
| Entering the invocation | **Runs before B** | Runs after A |
| Forwarding via `proceed()` | Passes the call to the chain containing B | Passes the call to the target or deeper chain |
| Exiting after normal return | **Runs after B** | Runs before A |
| Exiting on an exceptional exit | A's finally/catch runs **after** B's counterpart if both entered | B's finally/catch runs before A |

Therefore, saying "`@Order(10)` always executes all its lines of code before `@Order(20)`" is **false**. It has higher precedence and acts as the **outer wrapper**; its `finally`/post-processing work happens after B has finished.

## 3. Approach 1: Using @Order on a Spring Aspect Class

Example:

~~~java
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class AuditAspect {

    @Around("execution(* example.TransferService.transfer(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("audit: enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("audit: exit");
        }
    }
}
~~~

This is an illustrative aspect class; the complete runnable example is in section 7.

- Import **`org.springframework.core.annotation.Order`**, not a similarly named annotation from another framework.
- Place `@Order(10)` on the **`@Aspect` class** when you want to specify precedence relative to other aspects.
- Spring must **register the aspect as a bean** (e.g., `@Component` under component scanning, or `@Bean` in configuration). `@Aspect` and `@Order` by themselves **do not** turn a class into a Spring bean.
- `@Order` is metadata for Spring to sort advisors/aspects when those advisors participate in the same chain.
- `@Order` does not force all target beans to be proxied: only methods/beans matched by an advisor can be advised.
- `@Order` **does not control bean startup/singleton initialization**; initialization order mainly depends on the dependency graph and `@DependsOn` when needed. That is an entirely different concern from advice precedence.

When code only needs a static priority value, `@Order` is usually simpler and clearer than `implements Ordered`.

## 4. Approach 2: Implementing Ordered and Returning getOrder()

Spring provides the interface:

~~~java
package org.springframework.core;

public interface Ordered {
    int getOrder();
}
~~~

This is a simplified signature summary of the API, not code to place into your project to redefine Spring's interface.

In a Spring aspect:

~~~java
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.Ordered;

@Aspect
public class MetricsAspect implements Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Around("execution(* example.TransferService.transfer(..))")
    public Object measure(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("metrics: enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("metrics: exit");
        }
    }
}
~~~

The value `20` being smaller or larger **does not mean "good/bad"**; Spring only compares precedence. Because `20 > 10`, `MetricsAspect` has lower precedence than `AuditAspect(10)` in this example.

**When to use `Ordered`:** when an aspect wants to provide ordering through an explicit Java contract or needs to configure the order at bean initialization time. However, do not interpret "dynamic" as changing `getOrder()` arbitrarily between calls expecting Spring to rebuild the chain automatically: advisor order is normally established when the auto-proxy infrastructure prepares the proxy/chain, so mutating the value at runtime is not a reliable way to invert precedence. If you want to change an aspect's order, configure it before the context creates proxies and re-test.

**Avoid declaring both `@Order` and `Ordered` on the same aspect** without a specific reason and verifying the Spring version's order resolution algorithm. Two different sources of truth easily confuse maintainers.

## 5. Order Value Rules

Spring `Ordered` defines the constants:

~~~java
Ordered.HIGHEST_PRECEDENCE // Integer.MIN_VALUE
Ordered.LOWEST_PRECEDENCE  // Integer.MAX_VALUE
~~~

In practice:

| Value | Relative Meaning |
| --- | --- |
| `Ordered.HIGHEST_PRECEDENCE` | Very small value; belongs to the highest-precedence group |
| `@Order(-100)` | Higher precedence than `@Order(0)` |
| `@Order(0)` | Higher precedence than `@Order(10)` |
| `@Order(10)` | Higher than `@Order(20)` |
| `Ordered.LOWEST_PRECEDENCE` | Very large value; belongs to the lowest-precedence group |

You **do not have to** always use 0 or 1. Pick an intentional range of values for each category, such as audit-tracing, business metrics, and custom policies. However, **do not claim that all infrastructure advisors always have lower or higher values than your group**: transaction/cache/security can have their own ordering and proxy configurations.

### 5.1. What If Neither @Order Nor Ordered Is Specified?

Spring has no explicit precedence information to resolve between matching aspects. Spring documentation clearly states that when advice lives in **different aspects** and no precedence is configured, **the execution order is undefined**. Therefore:

- Do not rely on Java file order, alphabetical class names, or `@Bean` method order.
- Do not observe A running before B in one run and assume it will always happen.
- If order affects behavior, declare it explicitly with `@Order` or `Ordered`.

In many Spring APIs, objects without declared order may be treated as equivalent to low precedence by the comparator. However, **that does not create a stable order among aspects at the same level**. Do not turn a comparator implementation detail into a business contract.

### 5.2. What If Two Aspects Have the Same Order?

For example, A and B both have `@Order(10)`. Without a documented, guaranteed tie-breaker, the order **between the two aspects should still not be relied upon**. If A must reliably wrap outside B, use **two distinct values** and write an integration test confirming it.

Do not assign the same order and try to control tie-breaking via bean names or configuration registration order: those approaches create implicit coupling that breaks easily on Spring upgrades.

## 6. Do @Order and Ordered Need to Use the Same Style?

No. Across **two different aspects**, one aspect with `@Order(10)` and another that `implements Ordered { getOrder() -> 20; }` can participate in the exact same precedence rule.

Example:

~~~text
AuditAspect:   @Aspect + @Order(10)
MetricsAspect: @Aspect + implements Ordered; getOrder() = 20

=> on the way in: audit before metrics
=> on the way out: metrics before audit
~~~

You do not need to convert every class to `Ordered` just because one aspect implements the interface. Still, keep conventions consistent within a codebase so readers can locate ordering configuration easily.

**Distinguishing from `@Order` elsewhere:** Spring `@Order` is also used by some APIs to sort injected bean collections, event listeners, or infrastructure components. This lesson only covers **Spring AOP aspect precedence**. Do not deduce from a bean having `@Order` that all callbacks and dependent beans will also initialize or run in that order.

## 7. Runnable Java 17+ Project: Two Aspects, Two Ordering Styles

The program below demonstrates:

- Spring Framework 6.2.19, AspectJ Weaver 1.9.25.1, Java 17+, Maven.
- A `TransferService` as a Spring-managed bean.
- `AuditAspect` using `@Order(10)` and `@Around`.
- `MetricsAspect` using `implements Ordered`, `getOrder() == 20`, and `@Around`.
- Both pointcuts target a public method `transfer(boolean fail)`.
- Normal return and exceptional exit show **ascending order on the way in** and **descending order on the way out**.
- Both advice methods call `pjp.proceed()` exactly **once**, without modifying arguments, return values, or exceptions. `finally` is used to confirm the exit path even on errors.

This is **proxy-based** Spring AOP, requiring no AspectJ weaving configuration.

### 7.1. Project Structure

~~~text
spring-aspect-order-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── TransferService.java
    ├── AuditAspect.java
    ├── MetricsAspect.java
    └── Main.java
~~~

### 7.2. Maven: pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aspect-order-demo</artifactId>
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

Use the Spring Framework BOM so Spring modules share a consistent version. For Spring Boot projects, prefer Boot's dependency management; do not manually force Spring versions in a Boot application that already has a parent/BOM.

### 7.3. TransferService.java

~~~java
package example;

public class TransferService {

    public String transfer(boolean fail) {
        System.out.println("target: begin");

        if (fail) {
            throw new IllegalArgumentException("denied");
        }

        System.out.println("target: success");
        return "OK";
    }
}
~~~

Calling `transfer(false)` returns the String `"OK"`; calling `transfer(true)` throws `IllegalArgumentException("denied")`. In both cases, the method is invoked through a Spring AOP proxy.

### 7.4. AuditAspect.java — Using @Order

~~~java
package example;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class AuditAspect {

    @Around("execution(public * example.TransferService.transfer(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("audit(10): enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("audit(10): exit");
        }
    }
}
~~~

Because `AuditAspect` has precedence **10**, it wraps outside `MetricsAspect(20)`. `@Around` returns the exact value from `proceed()` or lets the original exception propagate without short-circuiting.

### 7.5. MetricsAspect.java — Implementing Ordered

~~~java
package example;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.Ordered;

@Aspect
public class MetricsAspect implements Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Around("execution(public * example.TransferService.transfer(..))")
    public Object metrics(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("metrics(20): enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("metrics(20): exit");
        }
    }
}
~~~

`Ordered.getOrder()` supplies the precedence for this specific aspect bean. In this example, the value is hard-coded so stdout is deterministic; in real systems, it can be read from configuration when the bean is created and then kept stable.

### 7.6. AppConfig.java — Registering Aspect Beans

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public TransferService transferService() {
        return new TransferService();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    public MetricsAspect metricsAspect() {
        return new MetricsAspect();
    }
}
~~~

**Why is `@Bean` needed?** Both classes have `@Aspect` without `@Component`. `@Bean` creates **two Spring aspect beans** so the auto-proxy creator discovers their advisors. `@EnableAspectJAutoProxy` turns on Spring AOP support. With `proxyTargetClass = true`, Spring uses a class-based proxy so the client retrieves the bean by `TransferService.class`; no interface is required in this example.

**You do not need to reorder `@Bean` methods to create ordering:** `@Order(10)` and `getOrder()==20` themselves form the ordering contract between the two aspects.

### 7.7. Main.java

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            TransferService service = context.getBean(TransferService.class);
            System.out.println("spring AOP proxy: "
                + AopUtils.isAopProxy(service));

            System.out.println("-- successful transfer --");
            System.out.println("caller: " + service.transfer(false));

            System.out.println("-- failed transfer --");
            try {
                service.transfer(true);
            } catch (IllegalArgumentException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

### 7.8. Expected Stdout

~~~text
spring AOP proxy: true
-- successful transfer --
audit(10): enter
metrics(20): enter
target: begin
target: success
metrics(20): exit
audit(10): exit
caller: OK
-- failed transfer --
audit(10): enter
metrics(20): enter
target: begin
metrics(20): exit
audit(10): exit
caller caught: denied
~~~

Maven or Spring may print a few environmental messages; the output above lists only the project's `System.out.println` lines.

### 7.9. Analysis on the Way In and Way Out

**Success path:**

1. Caller invokes `service.transfer(false)` on the Spring AOP proxy.
2. `AuditAspect(10)` is entered first, printing `audit(10): enter`.
3. Audit's `pjp.proceed()` forwards to `MetricsAspect(20)`, printing `metrics(20): enter`.
4. Metrics's `pjp.proceed()` reaches the target, printing `target: begin` and `target: success`, then returns `"OK"`.
5. `MetricsAspect` runs `finally`: printing `metrics(20): exit`.
6. `AuditAspect` runs `finally`: printing `audit(10): exit`.
7. Caller receives `"OK"`. Neither aspect modified the return value.

**Failure path:**

1. `AuditAspect(10)` and then `MetricsAspect(20)` enter in the same order.
2. Target prints `target: begin` and throws `IllegalArgumentException("denied")`.
3. `MetricsAspect(20)` executes `finally` first.
4. `AuditAspect(10)` executes `finally` afterward.
5. Caller catches **the same business exception** and prints `caller caught: denied`.

Both branches confirm: higher precedence **enters first** and **exits last**. It does not mean "audit finishes all of its work before metrics begins."

## 8. Changing the Order to Verify

Change one line in `AuditAspect.java`:

~~~java
@Order(30) // Replaces @Order(10)
~~~

Keep `MetricsAspect.getOrder() == 20`. **Now `MetricsAspect(20)` has higher precedence than `AuditAspect(30)`**; meaning metrics wraps outside audit. After editing `@Order`, recompile and run a fresh context.

The inner lines of the success path have this order:

~~~text
metrics(20): enter
audit(10): enter
target: begin
target: success
audit(10): exit
metrics(20): exit
~~~

**Note on log labels:** if you only change the annotation to `@Order(30)` without **updating the `"audit(10)"` string in `System.out.println`**, `audit(10)` remains in the output—that is a literal label in the code, **not the current order**. To make the output reflect the updated configuration, update the label to `audit(30)` as well:

~~~text
metrics(20): enter
audit(30): enter
target: begin
target: success
audit(30): exit
metrics(20): exit
~~~

**This is a configuration variant**, not the default stdout of the project in section 7. Reversing the order does not necessarily require editing the source code of `MetricsAspect` or the target service.

Similarly, you could keep `@Order(10)` and have `MetricsAspect.getOrder()` return 5; then `MetricsAspect` has higher precedence than `AuditAspect`. The values and comparison direction are what decide, not whether an annotation or interface is used.

## 9. Ordering Between Aspects vs. Inside the Same @Aspect

Spring Framework has separate rules for advice methods **of different types within the same `@Aspect` class**.

According to current Spring documentation, precedence among advice types **within the same aspect** is assigned (from highest to lowest):

1. `@Around`
2. `@Before`
3. `@After`
4. `@AfterReturning`
5. `@AfterThrowing`

**Important nuance:** Even though `@After` ranks above `@AfterReturning` and `@AfterThrowing` in the same aspect, it has **finally semantics**, so at runtime on the way out it **executes after** the corresponding `@AfterReturning` or `@AfterThrowing`. Do not look at the precedence list and assume `@After` always logs before the other after advice types.

### 9.1. Multiple Advice Methods of the Same Type in the Same Aspect

If you declare **two `@Before` or two `@After` methods of the same kind**, both matching a join point in **the same `@Aspect` class**, their relative order **is not guaranteed by Spring** because Java reflection does not provide a reliable source declaration order.

Example not to rely on:

~~~java
@Aspect
public class ProblematicAspect {

    @Before("execution(* example.TransferService.transfer(..))")
    public void stepOne() {
        System.out.println("one");
    }

    @Before("execution(* example.TransferService.transfer(..))")
    public void stepTwo() {
        System.out.println("two");
    }
}
~~~

You cannot simply place `stepOne` above `stepTwo` in the source file and claim `one` will always print before `two`.

**Better fixes:**

- If two operations form a single business sequence, **merge them into one advice method** and call them in explicit order.
- If they are two independent concerns whose order truly matters, **split them into two Spring aspect classes** and use `@Order` / `Ordered` to specify precedence.
- Do not try putting `@Order` on individual advice methods assuming Spring AOP will sort those methods like two independent aspects. Ordering is defined at the **aspect** level and by **advice type**.

The snippets above illustrate a conceptual mistake and do not belong to the complete runnable project in section 7.

## 10. Advice Precedence Is Not Spring Bean Initialization Order

It is easy to confuse two different concepts:

| Question | Mechanism to Consider |
| --- | --- |
| Which aspect runs first on the way into `TransferService.transfer()`? | `@Order` / `Ordered.getOrder()` and advisor ordering |
| Is singleton bean A initialized before singleton bean B? | Dependency injection graph, `@DependsOn`, or lifecycle infrastructure |
| In what order does Spring inject multiple beans into `List<Service>`? | Dependency ordering rules/annotations at the injection point |
| Which advice runs after the target returns? | Exit direction of the interceptor chain and advice type |
| Which controller handles a request first? | Web routing/handler mapping and web configuration, not `@Order` on an aspect |
| Does one async job run before another? | Executor/scheduling/concurrency, not guaranteed by aspect precedence |

For example, `@Order(1)` on an aspect does not force Spring to instantiate that aspect bean before all service beans, nor does it guarantee that another business event handler will run in that order.

To ensure advisor registration happens reliably and predictably, ensure the aspect is managed by Spring, auto-proxying is enabled, and the configuration is fully loaded. Do not use `@DependsOn` to "patch" advice order between aspects when the real issue is precedence.

## 11. Combining with Transaction, Cache, and Security Advisors

In real applications, a Spring AOP proxy can carry both:

- Your custom aspects: audit, tracing, metrics, validation.
- Infrastructure advisors: declarative transactions, caching, method security, and other mechanisms.
- Proxies/interceptors created by framework integrations or code using `ProxyFactory`.

When you put `@Order(10)` on `AuditAspect`, you **have** described **that aspect's** precedence. However, you have not yet proven the final order between audit and **all** transaction/cache/security advisors in the system.

### 11.1. Transaction Example

Suppose:

~~~text
Caller
  -> Audit @Around
      -> Transaction interceptor
          -> TransferService.transfer()
          -> commit/rollback
      -> audit exit
~~~

In this structure, audit exit occurs after the inner transaction interceptor finishes commit/rollback. However, if the order is reversed:

~~~text
Caller
  -> Transaction interceptor
      -> Audit @Around
          -> TransferService.transfer()
      -> transaction commit/rollback
~~~

then audit exit can occur **before** commit/rollback.

Consequences:

- If audit logs "transaction committed" merely because the target returned normally, the log can be wrong when audit sits **inside** the transaction advisor and commit happens later.
- If a timing aspect needs to include commit time, sitting outside the transaction interceptor can matter.
- If a caching aspect short-circuits on the outside, inner audit/transaction advisors may never be entered.
- When a target error is handled or converted into another exception by an inner transaction advisor, outer advice may observe a different result than calling the target directly.

**Do not guess ordering** from source annotations alone: inspect transaction/cache advisor configuration and test the actual Spring context.

### 11.2. Defaults of Infrastructure Advisors

Infrastructure components may use `Ordered.LOWEST_PRECEDENCE` or configurable order values, though exact values can depend on annotations, configuration, and Spring version. For example, `@EnableTransactionManagement(order = ...)` has an `order` attribute to adjust the transaction advisor in proxy mode.

Do not arbitrarily set all aspects to `HIGHEST_PRECEDENCE`: some infrastructure mechanisms such as async, validation, transactions, or security have specific ordering constraints. State **clear business expectations**, configure accurately, and test.

## 12. Limitation: Only Aspects That Actually Enter the Call Are Ordered

`@Order` does not make advice run when basic AOP prerequisites are not met.

### 12.1. Pointcut Does Not Match

If `AuditAspect` only matches `TransferService.transfer(..)` while `MetricsAspect` only matches `PaymentService.pay(..)`, the two aspects **do not act together** on a single invocation. Comparing 10 and 20 in that case will not produce a nested trace for a single method.

### 12.2. Aspect Is Not a Spring Bean

~~~java
@Aspect
@Order(1)
public class AuditAspect {
    // ...
}
~~~

Annotations on the class alone do not put an instance into the Spring container. You need `@Component` under component scanning or `@Bean` (as in section 7), along with proper Spring AOP configuration.

### 12.3. Self-Invocation and Non-Container Targets

~~~java
public void outer() {
    this.transfer(false);
}
~~~

If an external invocation targets `outer()`, while `this.transfer(false)` is an internal call on the target, the Spring AOP proxy **is not traversed a second time**. Order values cannot rescue self-invocation. This remains true for both JDK dynamic proxies and CGLIB class-based proxies.

Similarly, `new TransferService().transfer(false)` outside the Spring container does not receive AOP advice from Spring-managed aspects.

### 12.4. Short-Circuiting Around Advice

A higher-precedence aspect can use `@Around` and **not call `proceed()`**, such as on a cache hit or policy rejection. In that case, inner aspects and the target may not run despite having lower order numbers.

~~~java
// Illustrative snippet, not part of the standalone runnable project in section 7.
@Around("execution(* example.TransferService.transfer(..))")
public Object shortCircuit(ProceedingJoinPoint pjp) {
    return "CACHED";
}
~~~

Do not assume "aspect B(20) always runs after A(10)" if A(10) returned without proceeding; B never entered that invocation at all.

### 12.5. Nested Proxies and @Order

If a developer **manually wraps an AOP proxy inside another AOP proxy** using `ProxyFactory`, those are two physical layers. `@Order` only sorts advisors where Spring manages a single appropriate chain; it does not automatically invert an outer proxy's target source pointing to an inner proxy. You must determine which proxy the client holds, then inspect its actual advisor chain and target source.

## 13. Inspecting the Advisor Chain via Spring APIs

On beans exposing `Advised`, you can inspect the advisor list at the **current proxy layer**:

~~~java
// Supplementary snippet for Main.java in section 7; not a standalone program.
import org.springframework.aop.Advisor;
import org.springframework.aop.framework.Advised;

if (service instanceof Advised advised) {
    int position = 0;
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(position++ + ": "
            + advisor.getClass().getSimpleName());
    }
}
~~~

Notes:

- This is a runtime inspection technique; **do not treat output class names as a business contract**—Spring versions can change classes and metadata.
- `Advised.getAdvisors()` lists advisors on **the proxy being inspected**, not necessarily advisors on another inner proxy.
- A Spring AOP proxy may contain special advisors or other infrastructure advisors.
- The first entry in the list is not always a business `@Aspect` advice.
- `AopUtils.isAopProxy(service) == true` does not prove every method matches an advisor.
- A proxy may be configured as opaque and not expose `Advised`; check with `instanceof` before casting.
- Do not modify `Advised` or the target source of a production proxy just to observe order.

**Testing beats guessing:** Use a real Spring `ApplicationContext`, call the method through the bean reference, record events into a thread-safe list/test sink, and assert the event sequence on both normal and exceptional paths.

## 14. Testing Precedence and Stability Across Spring Upgrades

### 14.1. Test Matrix

| Scenario | Expectation |
| --- | --- |
| Two aspects both match, A(10), B(20), target succeeds | A enter → B enter → target → B exit → A exit |
| Two aspects both match, A(10), B(20), target throws | A enter → B enter → target throw → B finally → A finally → caller catch |
| Change A to 30, keep B at 20 | B wraps outside A |
| B's pointcut does not match target | Only A's advice runs |
| A returns early without proceed | B and target are not necessarily called |
| Two aspects share the same order but need fixed order | **Do not rely on it**; assign distinct values |
| A and B are both @Before in **the same aspect** | Method order is not guaranteed by declaration order |
| Caller invokes method via `this` from target | No additional invocation through Spring proxy |
| Transaction advisor added to context | Inspect actual chain, do not assume only A and B exist |

### 14.2. Testing Beyond Stdout

In the lesson project, stdout is convenient to observe. In a larger codebase, you can push events into a `List<String>` in a test-scoped sink and assert:

~~~java
// Conceptual test snippet; requires separate configuration and test sink.
assertEquals(
    List.of(
        "audit-enter", "metrics-enter", "target",
        "metrics-exit", "audit-exit"
    ),
    events
);
~~~

For the failure path, remember to assert both **the exception type and business state**. Do not use logs printing in the right order to infer that the transaction committed properly, security ran properly, or the business operation was not called twice.

### 14.3. Define Order Through a Readable Contract

If multiple development teams write aspects together, agree on order ranges and rationale, for example:

~~~java
public final class AspectOrder {
    private AspectOrder() {}

    public static final int AUDIT = 10;
    public static final int METRICS = 20;
}
~~~

Then:

~~~java
@Aspect
@Order(AspectOrder.AUDIT)
public class AuditAspect {
    // ...
}
~~~

This is a **design snippet**, not part of the standalone project in section 7. Constants help avoid accidental duplicate "magic numbers." However, order ranges are only meaningful when reviewed alongside **infrastructure ordering**; do not treat them as Spring defaults.

## 15. Common Pitfalls

| Symptom | Misconception | Correct Resolution |
| --- | --- | --- |
| @Order(10) prints exit log after @Order(20) | @Order is inverted | Higher precedence **exits later**; normal wrapper model |
| @Order(10) and Ordered(20) do not produce expected order | Annotation and interface are incompatible | Both express precedence; check pointcuts, bean registration, and actual chain |
| @Order is present but advice does not run | Ordering decides matching | Check @Aspect bean, proxy, pointcut, and call path |
| Using @Order on advice methods in the same @Aspect | Thinking it sorts per method | Use advice-type rules, merge methods, or split into separately ordered aspects |
| Two aspects both have @Order(10) | Assuming equal orders fall back to class name | When deterministic order is needed, use distinct values and test |
| Aspect has @Order(1), service still initializes before aspect | Thinking @Order is startup order | Dependency graph/@DependsOn handles initialization; unrelated to aspect precedence |
| Audit logs "committed" but transaction rolls back later | Forgot order relative to transaction advisor | Verify whether audit is inside/outside transaction and use commit events properly |
| Metrics missing even though target ran | Pointcut mismatch or call bypassed proxy | Check target bean, pointcut, self-invocation, and actual proxy |
| Target did not run even though outer aspect printed "enter" | Inner advisor or outer around short-circuited | Look for early returns or missing `proceed()` |
| CGLIB enabled yet self-call still has no advice | Thinking class proxy intercepts all internal calls | Spring AOP is still proxy-based; call through another bean when needed |
| Changed @Order at runtime but chain did not change | Assuming Spring re-sorts on every invocation | Configure stably before proxy creation, then create a new context/test |
| Audit ran twice | Blaming @Order | Check for duplicate aspect beans, nested proxies, repeated calls, and advisors |
| Negative @Order thought to be low priority | Misinterpreting larger numbers | Smaller numbers have higher precedence |
| Advice order changed after upgrade | Relied on internals/reflection order | Write integration tests for the contract and rely on docs for the running version |

## 16. Self-Practice Questions

**Question 1.** `AuditAspect` has `@Order(5)`, `MetricsAspect` has `getOrder() == 50`. Which aspect is entered first when a caller invokes a method through the proxy and both pointcuts match?

**Answer:** `AuditAspect` has higher precedence because `5 < 50`, so it is entered first. If both use around/finally, `AuditAspect` finishes after `MetricsAspect`.

**Question 2.** Why does `@Order(5)` "enter first but exit last" rather than running all its code first?

**Answer:** Because the higher-precedence aspect wraps around the inner chain. Calling `proceed()` transfers into the remaining interceptors, and then returns/exceptions unwind back out through the wrappers.

**Question 3.** There are two `@Before` methods in the same `@Aspect`, declared as `first()` before `second()`. Does Spring guarantee `first` runs before `second`?

**Answer:** No. Java declaration order is not a sufficient contract. Merge into one advice method or split into two aspect classes with different precedences.

**Question 4.** Two different aspects both have `@Order(10)`, and in one run A prints before B. Can this rule be documented in system docs?

**Answer:** You should not. When precedence is equal, do not rely on an accidentally observed order if the business needs stability; assign two different order values.

**Question 5.** Does `@Order(1)` on an aspect force Spring to instantiate that aspect bean before all service beans?

**Answer:** No. Advice precedence differs from bean lifecycle ordering. Check the dependency graph or lifecycle/depends-on if bean creation order is needed.

**Question 6.** Aspect A(10) uses `@Around` and returns a cached value without calling `proceed()`. Is Aspect B(20) guaranteed to run?

**Answer:** No. If A wraps outside B and returns early, the invocation does not reach B; order only matters when that part of the chain is actually entered.

**Question 7.** A custom audit aspect is given `@Order(0)`. Does this guarantee audit runs after transaction commit?

**Answer:** No. You must know the precedence and position of the corresponding transaction advisor; if audit runs inside the transaction, audit exit may occur before commit.

**Question 8.** If `@After` and `@AfterReturning` appear in the same `@Aspect`, can you use inter-aspect ordering to claim `@After` runs before `@AfterReturning`?

**Answer:** No. That is an intra-aspect rule with after-finally semantics: `@After` actually runs after the corresponding after-returning or after-throwing on the way out per Spring Framework 6.2.

**Question 9.** A method is invoked via `this.method()` inside the target bean. Does changing `@Order(10)` to `@Order(-10)` make the advice run?

**Answer:** No. Self-invocation still bypasses the Spring proxy; changing precedence does not fix the call path.

**Question 10.** Why is using both `@Order` and `Ordered` on the same aspect generally discouraged?

**Answer:** It risks introducing two conflicting configuration sources. Pick one clear convention, configure the bean properly, and test precedence in a real context.

## 17. Official References

- [Spring Framework — Declaring Advice / Advice Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): precedence between aspects; using `@Order` or `Ordered`; lower order means higher precedence; way-in/way-out rules; ordering of advice types in the same aspect.
- [Spring Framework — Schema-based AOP / Advice Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/schema.html): similar rules when using AOP XML and distinguishing advisor ordering.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): declaring `@Aspect` as a Spring bean and enabling `@EnableAspectJAutoProxy`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation, and advice boundaries.
- [Spring Javadoc — Ordered](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/Ordered.html): `getOrder`, `HIGHEST_PRECEDENCE`, and `LOWEST_PRECEDENCE`.
- [Spring Javadoc — @Order](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/annotation/Order.html): precedence metadata and distinction from singleton startup order.
- [Spring Framework — Transaction Management Configuration](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): transaction advisor ordering and proxy mode limitations.
