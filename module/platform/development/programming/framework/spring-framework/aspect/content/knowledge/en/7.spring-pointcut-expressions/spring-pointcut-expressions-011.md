# Choosing the Right Pointcut Width to Avoid Intercepting Unintended Beans in Spring AOP

## 1. Why Must You Control Pointcut Width?

In **Spring AOP**, a pointcut describes **which method executions on Spring beans** an advice can apply to. A syntactically valid expression can still be **far too broad for the business intent**. For example, an audit advice designed only for payment operations ends up matching report generation services, synchronization services, or other supporting beans.

When an advisor matches additional unintended beans, consequences can include:

- **Mis-scoped logs/metrics:** call counts and latency are recorded for methods outside the business flow being monitored.
- **Increased processing cost:** unnecessary advice runs on too many calls; if the advice performs I/O, overhead can be significant.
- **Wrong behavior:** `@Around` can alter results, handle exceptions, retry, or short-circuit methods that should never be affected.
- **Data exposure:** advice that unconditionally logs arguments or return values can leak sensitive information into logs.
- **Harder debugging:** an aspect thought to serve only module A unexpectedly affects module B, especially when new beans are added later.
- **Proxying more beans than necessary:** beans matching an advisor can be auto-proxied by Spring AOP, changing runtime types, call paths, and proxy constraints.

Goal of this lesson: learn how to scope accurately by **package, class, method, annotation, target type, and Spring bean name**, while also testing **items that must not match**. This is a guide specifically for **proxy-based Spring Aspect / Spring AOP**, without repeating general aspect theory.

## 2. Two-Step Model: Advisor Applies to Bean, Advice Applies to Invocation

An expression such as:

```java
@Before("execution(public * example.service..*Service.*(..))")
```

can cause Spring to detect many classes in the system with matching public methods. Spring AOP auto-proxying checks whether an advisor can apply to a **target class** during bean initialization, then evaluates matching methods and invocation conditions.

```text
Spring @Aspect bean --> @Before / @Around and pointcut expression
                                   |
                            candidate advisor
                                   |
          Spring AOP evaluates bean by type, method, bean name...
                                   |
                    does target bean have matching advisor?
                         /                         \
                       yes                         no
                       |                            |
                 Can create proxy           No proxy from that advisor
                       |
                Caller invokes method
                       |
              Method / runtime match?
                    /       \
                  yes        no
                  |           |
             Advice runs   Skip this advice
                  |
             Target method
```

**Do not equate the following statements:**

1. `AopUtils.isAopProxy(bean) == true`: the bean is a Spring AOP proxy; it does **not** prove every method runs an advice.
2. Advisor *is applicable to the class*: at least one method/condition can match; it does **not** prove every call is intercepted.
3. Pointcut matches a method: advice runs only when the invocation goes **through the Spring proxy** and all dynamic conditions hold.

Conversely, if a pointcut is too broad, Spring can proxy **more target beans** than expected, including beans added in the future whose class/method names happen to fit the rule.

## 3. Which Dimensions Determine Pointcut Width?

| Selection dimension | Typical Spring AOP syntax | What to watch out for |
| --- | --- | --- |
| Package and class scope | `within(com.acme.payment..*)` | Restricts method executions of types in that package and subpackages; does not imply a single bean |
| Method signature | `execution(public * com.acme.payment.PaymentService.pay(..))` | Restricts public, class, method name, parameters; clearer expressions mis-match less |
| Bean name | `bean(paymentService)` | Spring-specific PCD; bean name must match IoC configuration |
| Method annotation | `@annotation(com.acme.audit.Audited)` | Matches only methods bearing the annotation per Spring AOP semantics |
| Type annotation | `@within(com.acme.audit.AuditedType)` | Restricts to methods of annotated types; check inheritance/interface semantics |
| Target type | `target(com.acme.payment.PaymentService)` | Type of the target object; differs from `this(...)` under JDK proxies |
| Runtime arguments | `args(java.lang.String)` | Can depend on actual argument types at invocation, not just signature |
| Intersection | `execution(...) && within(...) && bean(...)` | Intersects match sets: all conditions must hold |
| Union | `execution(...) || @annotation(...)` | Unions match sets: usually **broader**, test out-of-scope cases |
| Exclusion | `!within(com.acme.internal..*)` | Subtracts a group; exclusion alone does not form a safe allowlist |

**Spring scope:** `execution`, `within`, `this`, `target`, `args`, `@annotation`, `@within`, and `bean` are common ways to restrict scope. Spring AOP only supports **method execution join points on Spring-managed beans**. Do not use `call()`, `get()`, `set()`, or AspectJ-weaving-only PCDs in a Spring AOP expression because they are not supported here.

## 4. From a Dangerous Pointcut to an Intentional Pointcut

Suppose a project has two bean types:

- `PaymentService`: payment logic, containing `pay()` and `status()`.
- `ReportService`: report generation, containing `generate()`.

Business requirement: **record audit logs only before `PaymentService.pay()` on the `paymentService` bean**.

### 4.1. Overly Broad Expression

```java
@Before("execution(public * example.service..*Service.*(..))")
```

This condition selects **every public method** on classes whose names match `*Service` in and under package `example.service`. Because both `PaymentService` and `ReportService` match, advice runs on all three methods: `pay()`, `status()`, and `generate()`.

Real-world risk: another team adds `TaxService`, `EmailService`, or `HealthService` into a similar package. **Without touching the aspect**, the advisor can start intercepting the new beans if the pointcut matches. The syntax is valid, yet the **business scope is wrong**.

### 4.2. Restricting Only by Package

```java
@Before("execution(public * example.service.payment..*.*(..))")
```

This expression excludes reporting in `example.service.report`, yet **still matches every public method** of every class in the payment area. If you only need `pay()`, it is still too broad.

### 4.3. Restricting to the Exact Method and Bean

```java
@Before(
    "execution(public * example.service.payment.PaymentService.pay(..))" +
    " && bean(paymentService)"
)
```

The condition above selects a specific method signature **and** the exact named Spring bean. This is especially useful when multiple beans share a class or you are targeting a specific Spring-managed object/tenant/adapter.

Note `bean(paymentService)` is a Spring-specific pointcut designator: it has meaning **within Spring AOP**, and should not be copied verbatim to an AspectJ compiler/weaver expecting support.

If the application renames the bean during refactoring, the pointcut must be updated. When a bean name is not a stable contract, use **class types, modules/packages, or dedicated annotations** to express intent instead of tying it to a name.

### 4.4. Do Not Add Multiple Conditions Just to Make It Longer

Not every pointcut needs `execution`, `within`, and `bean` at once. When a single signature already pinpoints the business logic and package, extra conditions may be redundant or make config overly fragile to change. The goal is the **narrowest scope that expresses intent while remaining stable**, not the expression with the most operators.

A helpful rule of thumb: pick **module/package scope** first, then restrict the **kind of method** needing advice; add `bean` or `@annotation` only when truly part of the contract.

## 5. Runnable Maven/Java 17+ Example: Broad vs. Narrow

This example creates **two independent Spring ApplicationContexts** to compare two pointcuts over **the same service classes**. Separating contexts prevents mixing the two aspects and avoids depending on advisor order.

Uses **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**. In real projects, prefer the Spring Framework or Spring Boot BOM for version management; the example pins versions for standalone reproducibility.

### 5.1. Directory Structure

```text
pointcut-width-demo/
├── pom.xml
└── src/main/java/example/
    ├── Main.java
    ├── service/
    │   ├── payment/PaymentService.java
    │   └── report/ReportService.java
    ├── aop/
    │   ├── BroadAspect.java
    │   └── NarrowAspect.java
    └── config/
        ├── ServicesConfig.java
        ├── BroadConfig.java
        └── NarrowConfig.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>pointcut-width-demo</artifactId>
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
```

### 5.3. PaymentService

**`src/main/java/example/service/payment/PaymentService.java`**

```java
package example.service.payment;

public class PaymentService {

    public void pay() {
        System.out.println("payment: pay");
    }

    public void status() {
        System.out.println("payment: status");
    }
}
```

### 5.4. ReportService

**`src/main/java/example/service/report/ReportService.java`**

```java
package example.service.report;

public class ReportService {

    public void generate() {
        System.out.println("report: generate");
    }
}
```

### 5.5. Overly Broad Aspect

**`src/main/java/example/aop/BroadAspect.java`**

```java
package example.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class BroadAspect {

    @Before("execution(public * example.service..*Service.*(..))")
    public void beforeAnyServiceMethod() {
        System.out.println("broad: before");
    }
}
```

It has no `@Component` because it will be registered via `@Bean` in `BroadConfig`. The expression intentionally matches both payment and report services. This is an **example demonstrating a scoping mistake**, not a recommendation for broad production use.

### 5.6. Properly Scoped Aspect

**`src/main/java/example/aop/NarrowAspect.java`**

```java
package example.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class NarrowAspect {

    @Before(
        "execution(public * example.service.payment.PaymentService.pay(..))"
        + " && bean(paymentService)"
    )
    public void beforePayment() {
        System.out.println("narrow: before payment pay");
    }
}
```

This pointcut does not target `PaymentService.status()`, `ReportService.generate()`, or another bean that happens to have a method named `pay()`.

### 5.7. Shared Beans Configuration

**`src/main/java/example/config/ServicesConfig.java`**

```java
package example.config;

import example.service.payment.PaymentService;
import example.service.report.ReportService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ServicesConfig {

    @Bean
    public PaymentService paymentService() {
        return new PaymentService();
    }

    @Bean
    public ReportService reportService() {
        return new ReportService();
    }
}
```

Because the `@Bean` method name is `paymentService`, the bean has that name in the context, matching `bean(paymentService)`. If you rename the bean, update the pointcut or drop the name constraint.

### 5.8. Context Using the Broad Pointcut

**`src/main/java/example/config/BroadConfig.java`**

```java
package example.config;

import example.aop.BroadAspect;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@Import(ServicesConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class BroadConfig {

    @Bean
    public BroadAspect broadAspect() {
        return new BroadAspect();
    }
}
```

### 5.9. Context Using the Narrow Pointcut

**`src/main/java/example/config/NarrowConfig.java`**

```java
package example.config;

import example.aop.NarrowAspect;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@Import(ServicesConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class NarrowConfig {

    @Bean
    public NarrowAspect narrowAspect() {
        return new NarrowAspect();
    }
}
```

Both contexts use `@EnableAspectJAutoProxy` while registering **a different aspect**. With `proxyTargetClass=true`, the demo can retrieve services by concrete class without worrying about JDK proxy interface typing; this is not a requirement for narrowing pointcuts.

### 5.10. Running and Comparing

**`src/main/java/example/Main.java`**

```java
package example;

import example.config.BroadConfig;
import example.config.NarrowConfig;
import example.service.payment.PaymentService;
import example.service.report.ReportService;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        System.out.println("-- BROAD --");
        try (var ctx = new AnnotationConfigApplicationContext(BroadConfig.class)) {
            PaymentService payment = ctx.getBean(PaymentService.class);
            ReportService report = ctx.getBean(ReportService.class);

            System.out.println("payment proxy: " + AopUtils.isAopProxy(payment));
            System.out.println("report proxy: " + AopUtils.isAopProxy(report));

            payment.pay();
            payment.status();
            report.generate();
        }

        System.out.println("-- NARROW --");
        try (var ctx = new AnnotationConfigApplicationContext(NarrowConfig.class)) {
            PaymentService payment = ctx.getBean(PaymentService.class);
            ReportService report = ctx.getBean(ReportService.class);

            System.out.println("payment proxy: " + AopUtils.isAopProxy(payment));
            System.out.println("report proxy: " + AopUtils.isAopProxy(report));

            payment.pay();
            payment.status();
            report.generate();
        }
    }
}
```

In the project directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

**Output of the `System.out.println` statements for those exact files:**

```text
-- BROAD --
payment proxy: true
report proxy: true
broad: before
payment: pay
broad: before
payment: status
broad: before
report: generate
-- NARROW --
payment proxy: true
report proxy: false
narrow: before payment pay
payment: pay
payment: status
report: generate
```

Other Maven or framework build/runtime logs may appear; this block lists only the lines printed by the sample program.

### 5.11. Meaning of the Results

- **BROAD:** both `PaymentService` and `ReportService` match the pointcut, so both have Spring AOP proxies. Advice runs before `pay()`, `status()`, and `generate()`. Thus three calls are audited when the original need was only one.
- **NARROW:** only `paymentService.pay()` qualifies, so `PaymentService` gets a proxy. `payment.status()` is called on the same proxy yet **does not run the narrow advice**, because the method does not match. `ReportService` needs no proxy **for the example's advisor**, and `AopUtils.isAopProxy(report)` is `false` in this context.
- Without changing target classes, changing only **pointcut width** changed which beans and calls were actually intercepted.
- Do not infer from `isAopProxy(payment) == true` that every method on `PaymentService` runs advice. **Bean level** and **method level** have separate decisions.

If the application adds other advisors (transactions, caching, etc.), a bean not matching the narrow advice can still be a proxy due to **those other advisors**. The `report proxy: false` result is predicted specifically for this minimal demo setup.

## 6. Writing Pointcuts by Module/Package Instead of Matching the Whole Application

In a multi-module codebase, packages form natural boundaries. For example, a real application has:

```text
com.acme.payment.service
com.acme.payment.repository
com.acme.reporting.service
com.acme.inventory.service
```

If advice is meant only for payment services, choose:

```java
@Pointcut("within(com.acme.payment.service..*)")
public void inPaymentServiceLayer() {}

@Pointcut("execution(public * *(..))")
public void anyPublicMethod() {}

@Pointcut("inPaymentServiceLayer() && anyPublicMethod()")
public void paymentPublicOperations() {}
```

This is a **snippet inside an `@Aspect` class**, not a standalone Java program. It uses **named pointcuts** to name the intent. `within(com.acme.payment.service..*)` restricts to types in that code region; `execution(public * *(..))` restricts to public methods; their intersection expresses "public operations in the payment service layer".

Avoid:

```java
@Before("execution(* com.acme..*(..))")
```

Expressions like this have a very wide scope and are hard to reason about or control. They can also pull classes/methods outside the business domain into AOP evaluation as the application grows.

**Note:** Just because a package is named `service` does not mean every method in it needs advice. Package scoping is a first step, **not a substitute for constraining to the exact functionality needing interception**.

## 7. When Should You Use an Annotation as an Opt-In Contract?

When methods needing advice are scattered across multiple packages, or only **a few** business methods are selected, a dedicated annotation can express intent more durably than method or bean names.

**`AuditedOperation.java` — complete illustrative annotation type:**

```java
package com.acme.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditedOperation {
}
```

A service can mark the **exact methods requiring audit**:

```java
// Snippet inside a Spring-managed service.
@AuditedOperation
public void approvePayment() {
    // ...
}

public void previewPayment() {
    // No audit annotation.
}
```

The aspect selects the marker within the module scope:

```java
@Aspect
public class PaymentAuditAspect {
    @Before(
        "within(com.acme.payment..*)"
        + " && @annotation(com.acme.audit.AuditedOperation)"
    )
    public void beforeAuditedPayment() {
        // Only marked methods inside the payment module.
    }
}
```

This is a **supplementary snippet**: in a real application the aspect class must be registered as a Spring bean, AOP must be enabled, and the annotation class must be on the classpath. Do not assume `@Aspect` auto-registers via component scanning.

**Benefits:** anyone reading the code can see which methods *opt in* to advice. If a method is renamed or refactored to another class while keeping the annotation within an allowed module, the intent is preserved.

**Limitations:** Agree on annotation placement when proxying interfaces vs. implementations, and write tests confirming the pointcut actually matches under the active JDK/CGLIB strategy. `@annotation` matches **method** annotations, not annotations on arbitrary classes or fields.

A marker annotation cannot protect sensitive data if the advice still logs parameters indiscriminately; design log contents separately.

## 8. The `bean()` Condition: Precise Yet Coupled

Spring provides `bean(idOrNamePattern)`, a pointcut designator **specific to Spring AOP**. Example:

```java
@Before("bean(paymentService) && execution(public * *.pay(..))")
```

When different beans implement the same payment interface or share a class, the bean name can isolate the target to audit. Use `bean()` when the **bean name is part of the deployment contract**, such as an intentionally configured adapter.

Notes:

- Bean name patterns can use `*`, e.g., `bean(*PaymentService)`. The expression uses the bean name, **not** the Java class name.
- If component names are inferred automatically by Spring or altered by a naming strategy, the expression may stop matching.
- When using bean aliases, `FactoryBean`, or parent-child contexts, check how actual bean names are resolved.
- A plain `AopUtils.canApply(pointcut, SomeClass.class)` check **does not replace** testing in a real context with concrete bean names.
- `bean()` is Spring-specific and not part of PCDs directly supported by AspectJ weaving.

In many systems, type + annotation is a more stable contract than bean name; do not turn bean names into the default rule for every aspect.

## 9. Combining `&&`, `||`, and `!` Without Accidental Expansion

Suppose:

- `A` = public method in the payment module.
- `B` = method annotated with `@AuditedOperation`.
- `C` = method named `pay`.

| Expression | Matched set |
| --- | --- |
| `A && B` | Only methods satisfying both; usually **narrower** than A or B |
| `A && C` | Public methods in payment with matching name |
| `A || B` | Methods in A **or** marked B **anywhere**; can be surprisingly broad |
| `A && !C` | All methods in A except C; can still be very broad |
| `A && (B || C)` | Remains restricted to A, then selects marked or matching-named methods |

When using negation, remember `!within(com.acme.internal..*)` only removes the `internal` area; it **still includes the entire rest of the application** unless paired with a positive allowlist condition.

Easy-to-get-wrong example:

```java
@Before(
    "within(com.acme.payment..*)"
    + " || @annotation(com.acme.audit.AuditedOperation)"
)
```

Read accurately: **all methods of the payment module**, plus **every annotated method in any other package**. If you wanted only annotated methods **inside the payment module**, you must use `&&`:

```java
@Before(
    "within(com.acme.payment..*)"
    + " && @annotation(com.acme.audit.AuditedOperation)"
)
```

Do not casually switch `&&` to `||` just to "cover more", especially for advices with side effects.

## 10. Testing Both Matching and Non-Matching Cases

An accurate pointcut must be verified with both **positive cases** and **negative cases**.

### 10.1. Scope Test Matrix

For `NarrowAspect` in section 5:

| Call case via Spring bean reference | Expect narrow advice to run? | Reason |
| --- | --- | --- |
| `paymentService.pay()` | **Yes** | Matches class, method, and bean name |
| `paymentService.status()` | **No** | Different method |
| `reportService.generate()` | **No** | Different class/package and bean name |
| A `backupPaymentService` bean of the same class, if registered | **No** | Does not match `bean(paymentService)` |
| `new PaymentService().pay()` outside Spring | **No** | No Spring AOP proxy |
| `this.pay()` internally on target | **No** for that internal call | Self-invocation bypasses Spring proxy |

Do not assert only "advice ran once" for the happy path. A pointcut change can keep advice running on the right case **while also** running on wrong cases, leaving old tests green.

### 10.2. Verifying via Spring Integration Tests

You can attach a counter or test sink to the advice instead of `System.out.println`, build a Spring context, and invoke methods. For the broad/narrow demo:

1. Assert narrow advice runs **exactly once** when calling `payment.pay()`.
2. Assert the counter **does not increment** when calling `payment.status()`.
3. Assert the counter **does not increment** when calling `report.generate()`.
4. If using `bean()`, register another bean of the same type with a different name and confirm it is not advised.
5. If changing package scope, add a similar test class in a neighboring package to verify isolation.

Counting logs in the example suffices to learn the mechanism; production projects should write **JUnit integration tests** and use test profiles/dependencies to verify zero out-of-scope side effects.

### 10.3. Checking Pointcuts with the Spring API

Spring AOP provides `org.springframework.aop.aspectj.AspectJExpressionPointcut` to evaluate a specific expression:

```java
// Illustrative snippet; not a standalone program.
AspectJExpressionPointcut pointcut = new AspectJExpressionPointcut();
pointcut.setExpression(
    "execution(public * example.service.payment.PaymentService.pay(..))"
);

boolean paymentClassCanMatch =
    AopUtils.canApply(pointcut, PaymentService.class);

boolean reportClassCanMatch =
    AopUtils.canApply(pointcut, ReportService.class);
```

With the indicated signature expression, expected results are `true` and `false` respectively. Import `AspectJExpressionPointcut`, `AopUtils`, and the model classes.

**Limitation:** `canApply` here answers whether a class can have matching methods. It does not confirm a specific proxy installed the advisor, cannot evaluate bean names without factory context, and does not replace runtime invocation tests. For pointcuts using `bean()`, evaluate inside a Spring bean factory/context and check which advisors were actually selected by the auto-proxy creator.

## 11. Broad Pointcuts Also Alter Proxy Types and Framework Interactions

A broad aspect can create proxies for beans that were previously raw objects. This can cause:

- Callers previously injecting by **concrete implementation type** to fail when AOP switches to JDK dynamic proxies.
- Beans with `final` methods not being intercepted under class-based proxies even though the bean is proxied.
- Methods called internally via `this` still bypassing Spring AOP, creating uneven effective coverage.
- Transaction/cache/security advisors sharing one proxy, making interceptor ordering harder to trace.
- `equals()`, `toString()`, introspection, or runtime class inspection tools behaving differently from plain Java objects.
- An `@Around` advice with bugs in `proceed()`/return/exception flow affecting methods completely outside the original business domain.

**Important:** Creating a proxy does not mean *all* of those consequences automatically occur. They are risks to verify when **expanding AOP scope**. The most effective prevention is crafting pointcuts that match exact, well-defined classes/methods/beans.

## 12. Spring Boot: Auto-Enabled AOP Does Not Mean You Should Use Broad Pointcuts

In Spring Boot, when an AOP/AspectJ starter and auto-configuration are active, the system can enable `@AspectJ` proxy support automatically without writing `@EnableAspectJAutoProxy`. However, how Spring picks beans/methods to advise **still depends on your pointcut**.

- **Spring Boot 3.x:** typically uses `spring-boot-starter-aop`.
- **Spring Boot 4.x:** the corresponding starter is renamed `spring-boot-starter-aspectj`.
- An `@Aspect` class must be registered as a Spring bean (usually `@Component` or `@Bean`).
- `spring.aop.proxy-target-class` affects JDK/CGLIB strategy; it **does not narrow pointcuts**.
- An aspect using `execution(* *(..))` can match many methods satisfying Spring AOP rules, even if the project previously had no AOP proxies on those beans.

In particular, never copy an overly broad demo pointcut from a small Spring Framework sample into a full Spring Boot application containing many service and infrastructure beans.

## 13. Preventing Bugs When Upgrading or Expanding an Application

### 13.1. Adding New Classes/Methods

Name-based patterns such as `*Service` or `save*` can automatically cover new classes/methods even when authors are unaware of the aspect. Review pointcut expressions like **public API boundaries**; whenever adding a new module/package, review shared pointcuts.

### 13.2. Renaming Packages or Bean Names

Pointcuts overly specific to class/bean names can break after refactoring. To balance safety and maintainability:

- Use named pointcuts tied to **module semantics** instead of repeating long strings.
- Use opt-in annotations when methods needing advice lack stable naming/package patterns.
- If using bean names, name them explicitly and guard with integration tests.
- Never fall back to `execution(* *(..))` just to keep tests "from failing" after refactoring.

### 13.3. Advice with Side Effects

Audit, retry, transaction, or security advices deserve extra care because mis-matching can corrupt business outcomes. You can use two layers of protection:

1. A **strictly bounded** pointcut on module/type/method.
2. Advice logic that **does not log secrets** and behaves safely on unexpected arguments.

However, conditional guards inside advice **do not replace** a narrow pointcut: proxies/advisors can still wrap unnecessary beans/methods.

### 13.4. Runtime Arguments and Performance

Pointcuts relying on `args(...)` or runtime-dependent conditions may need per-invocation evaluation. Choose expressions by semantics rather than premature optimization. Spring supports `ClassFilter`, `MethodMatcher`, and static/dynamic checks; **narrow scoping** helps cut down candidate checks. Do not guess cost from expression length; benchmark on the real application if advice sits on a hot path.

## 14. Pointcut Design Checklist

Before merging a Spring Aspect, answer:

1. **Specific intent:** which business operation is the advice meant to affect?
2. **Allowlist:** which packages, types, methods, or annotations define the exact scope?
3. **Must not touch:** which beans/packages/methods must never match?
4. **Future changes:** could adding a `*Service` class or moving a package cause surprise matches?
5. **Proxy boundary:** do callers go through a Spring proxy, and are the methods proxiable?
6. **Bean name:** are names stable if the pointcut uses `bean(...)`?
7. **Advice behavior:** does it log secrets, retry, alter return values, suppress exceptions, or cause transaction side effects?
8. **Tests:** are there both positive **and** negative integration tests?
9. **Framework:** could transaction/cache/async advisors keep a bean proxied even when your custom aspect does not match?
10. **Maintainability:** do named pointcuts, intent comments, and tests help others understand the expression?

Only widen scope after the list above is clear. "It runs" differs from "it runs only in the right places".

## 15. Exercises

**Scenario A.** Audit is required only for `PaymentService.pay()`. The aspect uses `execution(public * example.service..*Service.*(..))`. A new `ReportService.generate()` is created in `example.service.report`. Can the advice run?

**Answer:** Yes. Type name `ReportService` and public method `generate()` satisfy the broad pattern, despite not belonging to payments. Narrow the class/method or add another scope constraint.

**Scenario B.** Does `within(example.service.payment..*)` guarantee matching only `pay()`?

**Answer:** No. It selects method executions in types within that package, including other methods. Add method or annotation constraints.

**Scenario C.** You have expression `A || B`, where A selects payment services and B selects any method with an audit annotation application-wide. Can it select methods outside payments?

**Answer:** Yes. A method in another package can still satisfy B. To enforce payment scope, use `A && B` if that matches your intent.

**Scenario D.** A narrow pointcut is configured properly. `paymentService` is an AOP proxy, yet calling `status()` prints no audit log. Is there a contradiction?

**Answer:** No. The proxy exists at the bean level because at least one method has an advisor; the advice for `pay()` does not match `status()`.

**Scenario E.** A pointcut uses only `bean(paymentService)` to log every method. What is the issue?

**Answer:** It constrains by bean, yet **not** by method. If you only need `pay()`, it is still too broad; add `execution(...)` or an appropriate annotation.

**Scenario F.** After refactoring renames bean `paymentService` to `primaryPaymentService`, advice stops running. Should you change it to match all service beans?

**Answer:** No. Update the bean name contract accurately or switch to explicit annotations/types and add tests. Uncontrolled widening risks intercepting unintended beans.

## 16. Official Spring Reference Sources

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): PCDs supported by Spring AOP, `bean()`, combining named pointcuts, and recommendations for narrow pointcuts.
- [Spring Framework — Spring Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html): `ClassFilter`, `MethodMatcher`, static/dynamic matching.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy boundaries, JDK/CGLIB, self-invocation.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): enabling Spring AOP and aspect bean requirements.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): combining advice with pointcuts and declaring `@Before`, `@Around`.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): AOP auto-configuration and proxy strategy in Spring Boot.
