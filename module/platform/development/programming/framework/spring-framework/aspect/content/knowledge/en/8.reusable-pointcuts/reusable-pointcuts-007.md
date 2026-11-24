# Excluding Infrastructure Beans, Aspects, and Shared Logging Code in Spring AOP

## 1. Goal

An `@Aspect` in Spring typically handles cross-cutting concerns such as auditing, logging, timing, or tracing calls on **Spring service beans**. If a pointcut is too broad, advice will run not only on business code but also on **recorders, infrastructure adapters, loggers, and metrics collectors** — the very beans that the advice itself has to call.

Consider an advice used by Spring to record every invocation:

~~~text
Client -> OrderService proxy
              |
              +-> @Before advice
                       |
                       +-> AuditRecorder.record()
                                    |
                                    +-> If recorder is also advised
                                           |
                                           +-> @Before advice
                                                  |
                                                  +-> AuditRecorder.record()
                                                           |
                                                           +-> ...
~~~

If the recorder is called **through a Spring AOP proxy** and also matches that same advisor, the advice can re-enter uncontrollably and lead to an infinite loop or `StackOverflowError`. Configurations with circular dependencies among the aspect, recorder, and service can also cause errors during container startup.

This lesson focuses on **organizing pointcuts in Spring Framework** to properly exclude technical beans. Upon completion, you will:

- Accurately distinguish **business beans**, **infrastructure beans**, **aspect beans**, and **shared recorder beans**.
- Know that Spring AOP **automatically excludes `@Aspect` classes from auto-proxying as targets**, yet **does not automatically exclude every collaborator** injected into an aspect.
- Build business **allowlists** and negation expressions using `within`, `bean`, and `execution`.
- Combine and share named `@Pointcut` declarations with `&&`, `||`, `!`.
- Write a pure Spring Framework, **Java 17+** example with output verifying that the service is proxied while the recorder, inspector, and aspect are not proxied by this concern.
- Identify the limits of exclusions by bean name, package, class, annotation, and other advisors.

**Scope:** Covers only **proxy-based Spring AOP**, without switching to AspectJ weaving or re-presenting general AOP theory.

## 2. Four bean categories and pointcut responsibilities

| Category | Example | Desired behavior for business audit |
| --- | --- | --- |
| Business Spring bean | `OrderService`, `InvoiceService` | Advised when method falls within audit scope |
| Application infrastructure bean | `HealthInspector`, `CacheSupport` | Usually excluded, unless observing infrastructure is intended |
| `@Aspect` bean | `LoggingAspect` | Spring AOP does not treat it as a target for other aspects to advise |
| Shared recording bean | `AuditRecorder`, `MetricsSink` | Should be excluded from the very advisor that calls it |

**Note:** `AuditRecorder` is an ordinary Spring bean. Merely being named "recorder" or being injected into `LoggingAspect` **does not mean Spring automatically excludes it from every advisor**. If `AuditRecorder.record()` matches the pointcut, the recorder can be wrapped in a proxy.

Conversely, according to the official documentation on **Declaring an Aspect**, a class marked with `@Aspect` is recognized by Spring AOP as an aspect and **excluded from auto-proxying as a target**. This does not remove the aspect's advice; Spring still extracts advice from the aspect bean to apply to matching business beans.

For **application-defined** infrastructure beans, do not assume every bean annotated with `@Component`, `@Configuration`, or named ending in `Manager` is exempted from advice by the framework. Certain internal Spring infrastructure types are created/processed in special phases, yet they do not replace the application's pointcut exclusion policy.

## 3. Two approaches: selecting accurately upfront vs negating afterward

### 3.1. Overly broad pointcut

~~~java
@Before("execution(public * demo..*.*(..))")
public void beforeAnyPublicMethod(JoinPoint jp) {
    recorder.record(jp.getSignature().getName());
}
~~~

This is a **risk-illustration fragment**, not a standalone runnable Java file. The expression can cover many public methods across beans in the `demo` namespace: business services, recorders, helpers, health checks, and application configuration. If the recorder is also proxied by Spring due to this advisor, calling `record` from the advice can trigger that very advice.

Do not try this dangerous expression in production just to "see if it loops". Evaluate it in isolated tests, or fix the pointcut using the approaches below.

### 3.2. Allowlist: selecting only business code

~~~java
@Pointcut("execution(public * demo.business..*.*(..))")
public void businessMethods() {
}
~~~

An allowlist like the one above selects public methods whose type pattern belongs to `demo.business` and its subpackages. Beans like `demo.shared.AuditRecorder` and `demo.infra.HealthInspector` **are outside the selection scope from the start**.

Advantages:

1. When the application adds a new recorder outside `demo.business`, there is no need to update every exclusion list.
2. Looking at the expression tells you **what kind of code is monitored**.
3. The condition can be reused for logging, metrics, and auditing if those concerns share the same scope.
4. Tests can be written to assert that **business methods are advised**, and **technical methods are not advised**.

Disadvantage: package organization becomes part of the architectural contract. If a technical bean is misplaced in `demo.business`, it can still be selected; if a business service moves to another package, it can be missed. Therefore tests are still required.

### 3.3. Denylist: when legacy modules are hard to split by package

When packages cannot yet be refactored, you can use:

~~~java
@Pointcut(
    "execution(public * demo..*.*(..)) && " +
    "!within(demo.infra..*) && " +
    "!within(demo.shared..*) && " +
    "!within(demo.aop..*)"
)
public void applicationExceptTechnical() {
}
~~~

The condition starts from a broad scope and excludes types in technical packages. It is useful for incremental progress, yet the **risk of missing a newly added technical package** is higher than with a business allowlist.

## 4. Excluding by type/package: !within(...)

Spring supports the `within(...)` pointcut designator to restrict the scope of types containing method executions. The `!` operator negates the condition.

Example:

~~~text
execution(public * demo..*.*(..))
&& !within(demo.shared..*)
&& !within(demo.infra..*)
~~~

How to read it:

- `execution(public * demo..*.*(..))`: filters public method signatures in type patterns under `demo` and its subpackages.
- `!within(demo.shared..*)`: excludes method executions belonging to types in `demo.shared` and its subpackages.
- `!within(demo.infra..*)`: excludes the application infrastructure group.

You can exclude a single class:

~~~text
!within(demo.shared.AuditRecorder)
~~~

However, if `MetricRecorder` or `TraceWriter` is added later, the policy must be updated. Filtering by whole package is usually easier to maintain in well-organized modules.

Some complex hierarchies (method on an interface, implementation in another package, inheritance/bridge methods) make the **declaring type** and the method inspected by the proxy less obvious. If you need to exclude an object by **runtime target type**, consider `target(demo.shared.SomeType)` as a condition, and test it on real beans/proxies.

No package negation condition overcomes the fundamental boundary: Spring AOP intercepts only **calls through a Spring proxy** and only on methods valid under JDK/CGLIB.

## 5. Excluding by bean name: !bean(...)

`bean(...)` is a **Spring AOP-specific** designator matching bean names in the Spring container. It supports exact names and `*` wildcards in bean names.

~~~text
!bean(auditRecorder)
!bean(*Recorder)
!bean(healthInspector)
~~~

They can be combined:

~~~text
execution(public * demo..*.*(..))
&& !bean(*Recorder)
&& !bean(healthInspector)
~~~

Difference from `within`:

| Condition | Decides based on | Strength | Risk |
| --- | --- | --- | --- |
| `!within(demo.shared..*)` | Type/package of method execution | Protects an entire group of technical classes | Depends on package structure |
| `!within(demo.shared.AuditRecorder)` | Specific type | Exact by class | Easy to forget other recorders |
| `!bean(auditRecorder)` | Spring bean name | Selects/excludes a specific registration | Renaming the bean alters matching |
| `!bean(*Recorder)` | Spring bean naming convention | Excludes multiple recorders following convention | Does not exclude a bean named `auditSink` |

`bean` operates at the **Spring bean name** level, not the Java method name, and is **not** part of `execution` syntax. Native AspectJ weaving has no Spring bean factory to match this designator; avoid carrying this expression into weaving mode.

Verify actual bean names when using `@Component("...")`, `@Bean(name = "...")`, aliases, and custom naming strategies. Never infer the bean name solely from the class name across all configurations.

## 6. Excluding via annotations and business contracts

Another strategy is **opt-in**: advise only methods with an intentional annotation.

~~~text
@annotation(demo.audit.AuditedOperation)
~~~

Where `demo.audit.AuditedOperation` is a custom annotation created by the application, with runtime retention and METHOD target. Example definition:

~~~java
package demo.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface AuditedOperation {
}
~~~

A marked service:

~~~java
@AuditedOperation
public void submit(String id) {
    // Business method that requires auditing
}
~~~

The `submit` snippet is a **method fragment**, needing an appropriate class and imports; it is not yet a standalone Java file. Spring AOP can use `@annotation` to select marked methods.

If the annotation is placed on an interface rather than the implementation, or if there are complex proxies/inheritance, integration-test how Spring resolves annotation metadata. Do not assume that merely putting an annotation on an interface yields the same result for every proxy type.

The `@within` option can constrain annotations on a type. Consider it carefully because it differs from `@annotation` on a method. For application infrastructure classes, lacking the business annotation also acts as a natural allowlist.

## 7. Named @Pointcut: encapsulating conditions instead of duplicating them

Spring supports operators:

| Operator | Meaning |
| --- | --- |
| `&&` | Intersection: all conditions true |
| `||` | Union: at least one condition true |
| `!` | Negates condition |
| `(...)` | Groups conditions when needed |

You can write:

~~~java
@Pointcut("execution(public * demo..*.*(..))")
public void publicApplicationMethod() {
}

@Pointcut(
    "!within(demo.shared..*) && !within(demo.infra..*)"
)
public void notTechnicalType() {
}

@Pointcut("!bean(*Recorder)")
public void notRecorderName() {
}

@Pointcut(
    "publicApplicationMethod() && " +
    "notTechnicalType() && notRecorderName()"
)
public void auditableMethod() {
}
~~~

This is a **fragment of methods placed inside a pointcut class** importing `org.aspectj.lang.annotation.Pointcut`, not a standalone file. `@Pointcut` methods have a **`void` return type and empty body**: Spring reads metadata rather than invoking the methods as business logic.

You can place pointcut methods in `CommonPointcuts` and reference them by fully qualified name from an aspect:

~~~java
@Before("demo.aop.CommonPointcuts.auditableMethod()")
public void beforeBusiness(JoinPoint jp) {
    // ...
}
~~~

A pointcut method referenced from another class must have suitable Java visibility, such as `public`. Extracting into a shared policy class helps the team avoid each aspect maintaining its own version of the denylist.

## 8. Runnable Java 17+ project

We use **Spring Framework 6.2.12**, **Java 17+**, **Maven 3.9+**, without Spring Boot. The project has two services, one recorder, one infrastructure bean, and one `@Aspect`. The pointcut is broad enough for exclusions to matter, while clearly separating groups that must not be advised.

### 8.1. Project structure

~~~text
spring-aop-exclusion/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── config/AppConfig.java
    ├── business/OrderService.java
    ├── business/ReportService.java
    ├── shared/AuditRecorder.java
    ├── infra/HealthInspector.java
    ├── aop/CommonPointcuts.java
    └── aop/LoggingAspect.java
~~~

### 8.2. Maven

**pom.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-exclusion</artifactId>
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

`spring-context` provides `ApplicationContext` and the appropriate Spring AOP dependency; `aspectjweaver` supports parsing `@AspectJ` expressions/annotations. The example uses **proxy-based Spring AOP**, not AspectJ compile-time or load-time weaving.

### 8.3. Two business beans

**src/main/java/demo/business/OrderService.java**

~~~java
package demo.business;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    public void place(String orderId) {
        System.out.println("BUSINESS place " + orderId);
    }
}
~~~

**src/main/java/demo/business/ReportService.java**

~~~java
package demo.business;

import org.springframework.stereotype.Service;

@Service
public class ReportService {

    public void generate(String period) {
        System.out.println("BUSINESS generate " + period);
    }
}
~~~

Both are **Spring-managed service beans** registered by component scanning. Neither class is final and their public methods are non-final, so Spring can use a **class-based CGLIB proxy** when an advisor matches. They do not implement interfaces; we retrieve the beans directly by concrete class.

### 8.4. Recorder bean used by the aspect

**src/main/java/demo/shared/AuditRecorder.java**

~~~java
package demo.shared;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class AuditRecorder {

    private final AtomicInteger count = new AtomicInteger();

    public void record(String event) {
        count.incrementAndGet();
        System.out.println("AUDIT " + event);
    }

    public int size() {
        return count.get();
    }
}
~~~

`AuditRecorder` is an ordinary Spring `@Component`, created by Spring with default singleton scope. It is not automatically excluded from every advisor. The exclusion conditions for `demo.shared` and bean name `*Recorder` will prevent **LoggingAspect itself** from targeting it with advice in this example.

`AtomicInteger` is used for safe counting at the single-increment level. For a real audit system, choose appropriate storage and concurrency/error handling; do not use a singleton counter as a production audit store.

### 8.5. Ordinary infrastructure bean

**src/main/java/demo/infra/HealthInspector.java**

~~~java
package demo.infra;

import org.springframework.stereotype.Component;

@Component
public class HealthInspector {

    public void ping() {
        System.out.println("INFRA ping");
    }
}
~~~

The goal is to prove that a technical `@Component` is still managed by Spring yet **does not have to be audited**. `HealthInspector` carries no `@Aspect` annotation; it is excluded by application policy, not by the aspect auto-exclusion mechanism.

### 8.6. CommonPointcuts shared across aspects

**src/main/java/demo/aop/CommonPointcuts.java**

~~~java
package demo.aop;

import org.aspectj.lang.annotation.Pointcut;

public class CommonPointcuts {

    @Pointcut("execution(public * demo..*.*(..))")
    public void publicApplicationMethod() {
    }

    @Pointcut(
        "!within(demo.infra..*) && " +
        "!within(demo.shared..*) && " +
        "!within(demo.aop..*) && " +
        "!within(demo.config..*)"
    )
    public void notTechnicalType() {
    }

    @Pointcut("!bean(*Recorder) && !bean(healthInspector)")
    public void notTechnicalBeanName() {
    }

    @Pointcut(
        "publicApplicationMethod() && " +
        "notTechnicalType() && notTechnicalBeanName()"
    )
    public void auditableApplicationMethod() {
    }
}
~~~

**How to read it**:

1. `publicApplicationMethod` defines the initial scope: public method executions of types under `demo`.
2. `notTechnicalType` excludes four technical packages: infrastructure, recorder/shared, AOP helpers, and config.
3. `notTechnicalBeanName` excludes bean names matching the `*Recorder` wildcard and the exact bean `healthInspector`.
4. `auditableApplicationMethod` combines all three conditions via **logical intersection**.

The bean-name condition **partially overlaps** with the package condition in this simple example. This is intentional to demonstrate **two layers of defense**; there is no rule requiring both in every Spring application.

`CommonPointcuts` **does not need** to be a Spring bean or carry `@Aspect`. It is a class holding public named `@Pointcut` definitions so other aspects can reference them by fully qualified class name. Pointcut methods have empty bodies and are not called directly as business methods.

### 8.7. LoggingAspect injecting the recorder

**src/main/java/demo/aop/LoggingAspect.java**

~~~java
package demo.aop;

import demo.shared.AuditRecorder;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class LoggingAspect {

    private final AuditRecorder recorder;

    public LoggingAspect(AuditRecorder recorder) {
        this.recorder = recorder;
    }

    @Before("demo.aop.CommonPointcuts.auditableApplicationMethod()")
    public void beforeBusiness(JoinPoint jp) {
        recorder.record("before " + jp.getSignature().getName());
    }
}
~~~

Spring injects an `AuditRecorder` instance into the aspect constructor. The advice uses that instance to record an event **before each matched business method**. Calling `recorder.record(...)` is not advised by **this advisor itself** because the recorder lies outside the pointcut scope.

**Note:** Spring AOP automatically avoids auto-proxying an aspect bean as a target, while `!within(demo.aop..*)` also applies to **other helper beans in the same package** if those helpers are not annotated with `@Aspect`.

### 8.8. ApplicationContext and AOP

**src/main/java/demo/config/AppConfig.java**

~~~java
package demo.config;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

`@ComponentScan` registers the two business beans, recorder, inspector, and aspect. `@EnableAspectJAutoProxy` enables the infrastructure that automatically discovers advice and creates proxies when an advisor matches. `@Aspect` alone does not register a bean; in this example `LoggingAspect` also has `@Component`.

### 8.9. Main testing both targets and exclusions

**src/main/java/demo/App.java**

~~~java
package demo;

import demo.aop.LoggingAspect;
import demo.business.OrderService;
import demo.business.ReportService;
import demo.config.AppConfig;
import demo.infra.HealthInspector;
import demo.shared.AuditRecorder;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService orders = context.getBean(OrderService.class);
            ReportService reports = context.getBean(ReportService.class);
            AuditRecorder recorder = context.getBean(AuditRecorder.class);
            HealthInspector inspector = context.getBean(HealthInspector.class);
            LoggingAspect aspect = context.getBean(LoggingAspect.class);

            System.out.println(
                    "SERVICE_PROXY " + AopUtils.isAopProxy(orders));
            System.out.println(
                    "RECORDER_PROXY " + AopUtils.isAopProxy(recorder));
            System.out.println(
                    "INFRA_PROXY " + AopUtils.isAopProxy(inspector));
            System.out.println(
                    "ASPECT_PROXY " + AopUtils.isAopProxy(aspect));

            orders.place("INV-105");
            reports.generate("weekly");

            recorder.record("manual");
            inspector.ping();

            System.out.println("AUDIT_COUNT " + recorder.size());
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

**Expected logical stdout**, excluding Maven or framework logging lines:

~~~text
SERVICE_PROXY true
RECORDER_PROXY false
INFRA_PROXY false
ASPECT_PROXY false
AUDIT before place
BUSINESS place INV-105
AUDIT before generate
BUSINESS generate weekly
AUDIT manual
INFRA ping
AUDIT_COUNT 3
~~~

**Result explanation**:

- `SERVICE_PROXY true`: `OrderService` has a method matching the pointcut and is wrapped in a Spring AOP proxy.
- `RECORDER_PROXY false` and `INFRA_PROXY false`: no advisor in the demo context applies to those technical beans.
- `ASPECT_PROXY false`: consistent with Spring AOP not auto-proxying `@Aspect` classes as targets.
- `AUDIT before place` and `AUDIT before generate`: `LoggingAspect` itself is invoked by Spring before both service methods.
- `AUDIT manual`: `App` invokes the recorder directly; there is no `AUDIT before record` because the recorder does not match the audit advisor.
- `INFRA ping`: the inspector receives no audit advice.
- `AUDIT_COUNT 3`: two events from the aspect and one manual event; no recursion occurs from the recorder.

The result `RECORDER_PROXY false` is **not** a universal rule for every context. If a real application also has a security or transaction advisor applying to the recorder, `AopUtils.isAopProxy(recorder)` can be true even though `LoggingAspect`'s pointcut properly excluded the recorder. You must test the **behavior of the specific advisor under test** rather than assuming no proxy exists at all.

## 9. Why separate packages help prevent advice re-entrancy

Error-prone design:

~~~text
demo.service.OrderService
demo.service.ReportService
demo.service.AuditRecorder
demo.service.MetricWriter
~~~

Pointcut:

~~~text
execution(public * demo.service..*.*(..))
~~~

can select both the recorder and writer because all of them live in the same `service` package. When the aspect calls the recorder through a Spring proxy, it can hit its own advisor.

Cleaner design:

~~~text
demo.business.OrderService
demo.business.ReportService
demo.observability.AuditRecorder
demo.observability.MetricWriter
demo.infra.HealthInspector
demo.aop.LoggingAspect
~~~

You may only need:

~~~text
execution(public * demo.business..*.*(..))
~~~

to form a **positive allowlist**. Newly added technical beans in `demo.observability` will not be selected by accident.

If a legacy system does not yet permit package refactoring, use `!within` and `!bean` temporarily alongside integration tests, then plan to narrow the expression to the business layer.

## 10. Do not confuse excluding @Aspect with excluding aspect dependencies

Spring recognizes `@Aspect` and does not use that bean as a target for other Spring aspects to proxy. **However, the recorder is not automatically exempted**, even if created solely to serve the aspect.

An aspect commonly injects:

- `AuditRecorder`: records events.
- `EventPublisher`: publishes notifications.
- `Clock`: reads current time.
- `LogFormatter`: formats events.
- `MetricRegistry`: records metrics.

If the pointcut is broad enough and these dependencies are Spring-managed, Spring can treat them as advisor targets. You must analyze the **entire dependency graph of the advice**, not just the aspect class name.

The fact that `LoggingAspect` itself is not proxied **does not** prevent `AuditRecorder` from being proxied and looping the advice. This is why excluding shared observability code is a crucial part of **pointcut policy**.

## 11. Another advisor can still proxy a technical bean

A pointcut governs the scope **of one advisor**, not a ban on all proxying mechanisms. For example:

- Your audit aspect excludes `AuditRecorder`.
- Another transaction/security advisor applies to the `record` method.
- `AuditRecorder` can still be a Spring AOP proxy.
- Yet if the audit aspect's advice does not match the recorder, the audit concern alone will not re-enter on that method.

Therefore, do not set a goal that "every recorder bean must always have `AopUtils.isAopProxy == false`" in an application with multiple advisors. The right goals are:

1. Services requiring auditing are intercepted by the audit advisor.
2. Recorder methods are not selected by **the same audit advisor**.
3. Event counts match the expected number of business operations.
4. No call cycle occurs from the advice back into itself through its dependencies.

Distinguish **proxy presence** from **matching a specific pointcut**.

## 12. Positive and negative integration testing

To validate the policy, do not just read the expression. Using the same context as the example, you can write a test check inside a Java method:

~~~java
if (!AopUtils.isAopProxy(orders)) {
    throw new AssertionError("OrderService must be proxied");
}
if (AopUtils.isAopProxy(recorder)) {
    throw new AssertionError("Recorder should not be proxied here");
}
if (AopUtils.isAopProxy(inspector)) {
    throw new AssertionError("Inspector should not be proxied here");
}
if (AopUtils.isAopProxy(aspect)) {
    throw new AssertionError("Aspect should not be proxied");
}

int before = recorder.size();
orders.place("T-1");
int after = recorder.size();

if (after != before + 1) {
    throw new AssertionError("Expected one audit event");
}
~~~

This is a **test fragment**, requiring `orders`, `recorder`, `inspector`, and `aspect` retrieved from the context and importing `AopUtils` inside a valid Java class. Do not run the fragment directly from the command line as a standalone program.

In a real application with multiple advisors, asserting that the recorder is not proxied at all may be too strong. In that case, record the exact effect of **`LoggingAspect`** (for example, a dedicated counter on the advice) to confirm the recorder does not trigger additional invocations of that aspect.

### Cases to test

| Case | Expectation |
| --- | --- |
| Call business method via Spring bean | Advice runs the exact expected number of times |
| Call `AuditRecorder.record()` directly | Does not trigger `LoggingAspect` |
| Call `HealthInspector.ping()` | Does not trigger `LoggingAspect` |
| Call method on helper outside business package | Does not trigger business audit policy |
| Call `this.method()` internally on target | Do not assume advice runs; verify proxy boundary |
| Add a bean named `sharedAuditSink` | Check package/type policy, since `*Recorder` does not match that name |
| Rename `@Component` bean name | Rerun tests because `bean(...)` may change |
| Move service to a new package | Rerun allowlist tests so business logic is not missed |

## 13. @Order and @Around are not tools for excluding beans

`@Order` can decide **advisor/aspect precedence** when multiple advice methods match the same invocation. It does not change whether a recorder method matches a pointcut.

Similarly:

- Switching `@Before` to `@Around` does not prevent a loop if the advice still calls a recorder intercepted by an advisor for the same concern.
- `ProceedingJoinPoint.proceed()` continues the current invocation; it is not a magic "skip all other advice" switch.
- Increasing thread-safety of the recorder with `AtomicInteger` does not resolve a proxy call loop.
- Enabling `proxyTargetClass = true` switches to CGLIB but is not a way to exclude the recorder from the pointcut.
- Disabling `@EnableAspectJAutoProxy` to avoid advising the recorder will also disable Spring AOP infrastructure in that context, affecting services that need auditing.

The proper fix is to **narrow the pointcut scope**, while reviewing the dependency graph and call paths.

## 14. When to use !within, !bean, or @annotation?

| Context | Preference |
| --- | --- |
| Clear business package exists | `execution(public * demo.business..*.*(..))` |
| Legacy module mixes business and technical types | Allowlist if possible; otherwise precise `!within` negations |
| Same class with multiple Spring bean registrations having different roles | `bean(...)` to select or exclude specific bean names |
| Audit only operations explicitly marked by developers | `@annotation` with a business annotation |
| Multiple aspects share the same business layer | Public named methods in `CommonPointcuts` |
| Recorder is advised by the very aspect calling it | Start by excluding the recorder from that pointcut, then inspect the graph |
| Only want "aspect not advised by another aspect" | Spring AOP already has auto-exclusion for `@Aspect`; do not treat this as a recorder-exclusion policy |

Do not pick one single strategy for every project. Systems with diverse modules and naming conventions may need a combination of type/package and bean-name filters; what matters is **stating intent clearly and testing on a real context**.

## 15. Common mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Continuous log loop or `StackOverflowError` | Advice calls recorder; recorder matches the same advisor | Narrow business allowlist or explicitly exclude recorder |
| Startup dependency error between aspect and service | Circular dependency through collaborator | Draw dependency graph, decouple recorder from advised services |
| Aspect is not a proxy | Spring AOP auto-exclusion for `@Aspect` beans | Normal behavior, not a bug |
| Recorder is still proxied after audit exclusion | Another advisor selects the recorder | Inspect specific advisors; do not rely on a generic proxy boolean |
| `!bean(*Recorder)` fails to exclude audit bean | Bean name differs from `*Recorder` convention | Check actual bean name, use type/package, or align convention |
| `!within(demo.shared..*)` fails to exclude implementation elsewhere | Type/package matching differs from runtime target type | Test hierarchy/proxies, consider target/type restrictions |
| New service is missing audit | Package or annotation allowlist does not cover it | Update policy/tests when adding or moving services |
| All infrastructure beans are proxied | Pointcut too broad, missing boundaries | Separate packages and filter by business operations |
| Changing `@Order` still repeats advice | Ordering does not change match scope | Fix the pointcut |
| `@Aspect` class exists but advice never runs | Aspect not registered as bean or missing infrastructure | `@Component`/`@Bean`, `@EnableAspectJAutoProxy` |
| Method matches signature yet advice does not run | Self-invocation or caller holds a `new` instance | Check call path through the Spring proxy |
| Copying `bean(...)` to weaving mode | Spring bean designator does not exist in native AspectJ | Use only in Spring AOP pointcuts |

## 16. Pointcut design checklist to avoid logging the logging code

1. Identify **every dependency the advice calls**, not only business targets.
2. Sketch the call graph: Service proxy → Aspect → Recorder/Publisher → downstream dependencies.
3. Start with a **positive business allowlist** if the architecture permits.
4. For broad scopes, add `!within` for technical packages/types and `!bean` for relevant registrations.
5. Do not expect the framework to exempt helper `@Component` beans just because they serve an aspect.
6. Do not add sprawling exclusions if essential services might get dropped; use readable named pointcuts.
7. Verify `@Aspect` is registered as a Spring bean and AOP is enabled.
8. Test **both cases that should match and cases that should not match** in integration tests.
9. Do not treat `AopUtils.isAopProxy` as proof that a specific advisor is or is not running.
10. Whenever packages, bean names, annotations, or aspect dependencies change, rerun tests to verify policy.
11. Avoid having the recorder itself call back into advised services unintentionally, as that can also cause re-entrancy via another business path.
12. With multiple concerns, design a separate pointcut scope per concern rather than one ultra-broad pointcut for everything.

## 17. Self-assessment questions

**1. Why does Spring not automatically exclude `AuditRecorder` from every Spring aspect?**

Because `AuditRecorder` is an ordinary Spring bean. Spring cannot tell from a class name which advisor is allowed to intercept which recorder; the application must define the pointcut policy.

**2. Does Spring AOP exclude beans annotated with `@Aspect` from auto-proxying as targets?**

Yes. However, that bean still supplies advice to business beans, and the aspect's dependencies are not similarly exempted.

**3. How does `!within(demo.shared..*)` differ from `!bean(*Recorder)`?**

One excludes by method-execution package/type, while the other excludes by Spring bean name and naming convention.

**4. Why is an allowlist like `demo.business` usually easier to maintain than negating dozens of packages?**

It opens scope explicitly to business types, preventing new technical beans outside the package from being accidentally matched.

**5. Must `AopUtils.isAopProxy(recorder)` always be false after you exclude it from the audit aspect?**

No. Other advisors can still proxy the recorder. What must be verified is whether the audit advisor runs when the recorder is invoked.

**6. Does using `@Order` stop an advice from calling the recorder recursively?**

No. `@Order` only adjusts ordering; it does not change the set of join points matched by the pointcut.

**7. Can multiple conditions be grouped into a `CommonPointcuts` class?**

Yes. Use public named `@Pointcut` methods and have aspects reference them by fully qualified name.

**8. Should every infrastructure bean be marked `@Aspect` so Spring skips proxying them?**

No. `@Aspect` denotes a true AOP role; abusing it to skip auto-proxying breaks the model. Fix the policy using `execution`, `within`, `bean`, or appropriate annotations.

## 18. Spring Framework documentation

- Spring Framework 6.2 — **Declaring a Pointcut** (`execution`, `within`, `bean`, logical operators, named pointcuts): https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html
- Spring Framework 6.2 — **Declaring an Aspect** (aspect beans excluded from auto-proxying as targets): https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/at-aspectj.html
- Spring Framework — **@AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — **Declaring Advice**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html

**Conclusion:** Spring AOP recognizes `@Aspect` and does not turn an aspect bean into a target proxy for other aspects. However, **recorders, helpers, and infrastructure `@Component`s remain ordinary beans eligible for advisors**. To prevent advice from wrapping its own recording code, start with a **business-method allowlist**, organize `CommonPointcuts`, add `!within`/`!bean` where needed, and test both matched targets and excluded beans.
