# Sharing Pointcuts Across Aspects in Spring AOP

## 1. The problem to solve

In a Spring application, multiple `@Aspect` classes may care about the same set of invocations, such as public methods in the service layer:

- `AuditAspect` records an entry before an operation runs.
- `MetricsAspect` records the operation outcome.
- Another aspect might measure duration or add tracing information.

If each aspect copies its own `execution(...)` string, simply changing a package or method name easily leads to inconsistent pointcut definitions. Spring AOP lets you **define a named pointcut** with the `@Pointcut` annotation and **reuse that name across multiple advice methods, even in different aspects**.

Key points to remember:

1. The method annotated with `@Pointcut` represents the **pointcut signature**; the expression inside the annotation determines which method executions are selected.
2. The pointcut method body is normally **empty**, with a `void` return type.
3. Advice can use `"package.ClassName.pointcutName()"` instead of copying long expressions.
4. A shared pointcut does not merge advice into a single advice: Spring still creates and orders an advisor corresponding to each advice.
5. Even with a shared pointcut, Spring AOP proxy boundaries still apply: only method executions invoked through a Spring proxy and selected by the matcher are advised.

This lesson considers only **Spring Framework / Spring AOP mechanisms**. AspectJ weaving and general Aspect theory are not expanded here.

## 2. How is a named pointcut declared?

The `@Pointcut` syntax names an expression so that other advice can use the **same definition** without copying the raw string:

```java
public class SharedPointcuts {
    @Pointcut("execution(public * demo.service..*.*(..))")
    public void serviceMethod() {}

    @Pointcut("execution(* demo.service..*.submit(..))")
    public void submitMethod() {}

    @Pointcut("serviceMethod() && submitMethod()")
    public void submission() {}
}
```

In another aspect, reference `@Before("demo.pointcut.SharedPointcuts.submission()")` if the actual class is in package `demo.pointcut`. The method signature must return `void`, include `()` when referenced, and normally have an empty body. The lesson **"Declaring Named Pointcuts with `@Pointcut`"** explains its structure and parameter binding in detail.

## 3. Organizing a shared pointcut library

A large application typically has clear architectural boundaries: public service operations, repository operations, methods requiring auditing, or a set of methods in a specific subsystem. Spring documentation recommends creating a **dedicated class** to describe these boundaries using named pointcuts.

A reference structure:

```text
com.example.app/
├── pointcut/
│   └── ApplicationPointcuts.java
├── aspect/
│   ├── AuditAspect.java
│   └── MetricsAspect.java
└── service/
    ├── OrderService.java
    └── OrderServiceImpl.java
```

In the catalog, prefer:

- Names that express **business or architectural intent**: `serviceOperation()`, `orderSubmission()`.
- Small pointcuts that can be combined with `&&`, `||`, and `!`.
- Scopes tight enough: prefer constraining method signatures and packages/types, avoiding accidentally selecting every method in the entire application.
- Not injecting business services just to "execute" a pointcut. The catalog is a home for **metadata expressions**, not business execution.
- Having integration tests to see which methods are actually selected when packages or service APIs change.

### How to combine named pointcuts

```java
@Pointcut("execution(public * com.example.app..service..*.*(..))")
public void publicServiceMethod() {
}

@Pointcut("execution(* com.example.app..*.submit(..))")
public void submitMethod() {
}

@Pointcut("publicServiceMethod() && submitMethod()")
public void publicSubmission() {
}

@Pointcut("publicServiceMethod() && !submitMethod()")
public void serviceOtherThanSubmit() {
}
```

The snippet above **must reside inside the corresponding `@Aspect` class**, not as a standalone Java program. When another pointcut uses `publicSubmission()`, Spring treats it as a combined expression; the method body does not need and should not contain logic.

If only one aspect needs an extra condition, that aspect can append `&& bean(*Service)` or `&& @annotation(...)` to the catalog reference. Advice methods are not required to have **identical matching sets** just because they share part of a pointcut.

## 4. Visibility rules when sharing pointcuts

The requirement for reusing a named pointcut from another class is that **the pointcut name and declaring type must be accessible** under Java visibility rules. A `private @Pointcut` method is suitable when advice in the same declaring class uses it internally; package-private and `protected` have package/hierarchy limits; `public` is suitable for a catalog in another package.

The modifier on the `@Pointcut` method does not alter the set of matched methods; to select public target methods, a condition such as `execution(public * *(..))` must be in the expression. The two lessons **"Pointcut Method Visibility and Reuse Scope"** and **"Distinguishing Pointcut Declaration Visibility..."** analyze Java scope and JDK/CGLIB proxy limits in full.

## 5. Runnable example: two aspects sharing a pointcut catalog

The project uses **Java 17+, Maven, and Spring Framework 6.2.6**. We create:

- `SharedPointcuts` with two basic pointcuts and one combined pointcut.
- `AuditAspect` using that named pointcut in `@Before`.
- `MetricsAspect` using the **same named pointcut** in `@AfterReturning`.
- `OrderServiceImpl` with `submit()` and `status()`. Only `submit()` is selected by both advice methods.

The example uses `AnnotationConfigApplicationContext`, without Spring Boot. Both the aspects and the catalog are registered as Spring beans via `@Bean`, avoiding component-scan assumptions.

### 5.1. File structure

```text
spring-shared-pointcuts/
├── pom.xml
└── src/main/java/demo/
    ├── SharedPointcutDemo.java
    ├── pointcut/
    │   └── SharedPointcuts.java
    ├── service/
    │   ├── OrderService.java
    │   └── OrderServiceImpl.java
    └── aspect/
        ├── AuditAspect.java
        └── MetricsAspect.java
```

### 5.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-shared-pointcuts</artifactId>
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
                    <mainClass>demo.SharedPointcutDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. File src/main/java/demo/pointcut/SharedPointcuts.java

```java
package demo.pointcut;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class SharedPointcuts {

    @Pointcut("execution(public * demo.service..*.*(..))")
    public void serviceMethod() {
    }

    @Pointcut("execution(* demo.service..*.submit(..))")
    public void submitMethod() {
    }

    @Pointcut("serviceMethod() && submitMethod()")
    public void submission() {
    }
}
```

These three methods return `void`, have empty bodies, and are all `public`. The `submission()` expression selects the **intersection**: public methods in the service package named `submit`. The catalog is a class declaring pointcuts, not a service executing business logic.

### 5.4. File src/main/java/demo/service/OrderService.java

```java
package demo.service;

public interface OrderService {
    String submit(String id);
    String status();
}
```

### 5.5. File src/main/java/demo/service/OrderServiceImpl.java

```java
package demo.service;

public class OrderServiceImpl implements OrderService {

    @Override
    public String submit(String id) {
        System.out.println("TARGET submit " + id);
        return "ACCEPTED:" + id;
    }

    @Override
    public String status() {
        System.out.println("TARGET status");
        return "READY";
    }
}
```

### 5.6. File src/main/java/demo/aspect/AuditAspect.java

```java
package demo.aspect;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {

    @Before("demo.pointcut.SharedPointcuts.submission()")
    public void before(JoinPoint joinPoint) {
        System.out.println(
            "AUDIT " + joinPoint.getSignature().getName()
        );
    }
}
```

### 5.7. File src/main/java/demo/aspect/MetricsAspect.java

```java
package demo.aspect;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.AfterReturning;

@Aspect
public class MetricsAspect {

    @AfterReturning(
        pointcut = "demo.pointcut.SharedPointcuts.submission()",
        returning = "result"
    )
    public void after(Object result) {
        System.out.println("METRIC return " + result);
    }
}
```

Both `AuditAspect` and `MetricsAspect` use the exact same **qualified pointcut reference**. Their advice execution differs by annotation: `@Before` before the target, `@AfterReturning` after the method completes normally.

### 5.8. File src/main/java/demo/SharedPointcutDemo.java

```java
package demo;

import demo.aspect.AuditAspect;
import demo.aspect.MetricsAspect;
import demo.pointcut.SharedPointcuts;
import demo.service.OrderService;
import demo.service.OrderServiceImpl;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class SharedPointcutDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class Config {

        @Bean
        public OrderService orderService() {
            return new OrderServiceImpl();
        }

        @Bean
        public SharedPointcuts sharedPointcuts() {
            return new SharedPointcuts();
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

    public static void main(String[] args) {
        try (var ctx =
                new AnnotationConfigApplicationContext(Config.class)) {

            OrderService service = ctx.getBean(OrderService.class);
            System.out.println(
                "AOP_PROXY=" + AopUtils.isAopProxy(service)
            );
            System.out.println("CLIENT " + service.submit("A01"));
            System.out.println("CLIENT " + service.status());
        }
    }
}
```

Run in the `spring-shared-pointcuts` directory:

```bash
mvn -q compile exec:java
```

Lines **printed by the program**, excluding separate Maven or Spring logging:

```text
AOP_PROXY=true
AUDIT submit
TARGET submit A01
METRIC return ACCEPTED:A01
CLIENT ACCEPTED:A01
TARGET status
CLIENT READY
```

Result explanation:

1. `@EnableAspectJAutoProxy` enables Spring AOP with `@AspectJ` declaration style; the `@Bean` methods register the target, catalog, and two advice aspects.
2. The advisors of `AuditAspect` and `MetricsAspect` both use `SharedPointcuts.submission()`. Target `submit()` matches, so a proxy is created and both advice methods participate in the invocation.
3. `@Before` runs before the target; after the target returns `ACCEPTED:A01`, `@AfterReturning` observes the result; finally, the client prints the result.
4. `status()` is in the service package but is not `submit()`. It does not match `SharedPointcuts.submitMethod()`, so neither advice runs for the `status()` call.
5. Runtime proxy names/classes are not hardcoded in the output. `AopUtils.isAopProxy(...)` checks the actual bean provided by the context.

**Note:** in a more complex context, a bean can still have other advisors such as transaction or caching. In the demo, only the declared aspects are present to keep the illustrative output clear.

## 6. Adding aspect-specific conditions without modifying the catalog

Aspect A can use the whole catalog, while aspect B adds a condition:

```java
@Aspect
public class BeanScopedAudit {

    @Before(
        "demo.pointcut.SharedPointcuts.serviceMethod() " +
        "&& bean(*Service)"
    )
    public void auditNamedBeans() {
        System.out.println("AUDIT NAMED SERVICE");
    }
}
```

This is a **snippet**; to run, it must be registered as a Spring bean and have bean names matching the pattern. `bean(*Service)` is a pointcut designator **specific to Spring AOP**, selecting by Spring bean name rather than method/class.

Another snippet selects only executions carrying an annotation:

```java
@Aspect
public class AnnotatedAudit {

    @Before(
        "demo.pointcut.SharedPointcuts.serviceMethod() " +
        "&& @annotation(com.example.app.Audited)"
    )
    public void auditAnnotated() {
        System.out.println("AUDITED");
    }
}
```

This is a **pattern** requiring the `com.example.app.Audited` annotation definition and testing how the matcher looks up method annotations. The shared `serviceMethod()` part is still reused. Aspects can **broaden or narrow** their join point sets relative to each other without changing the foundational boundary.

Do not force every aspect-specific condition into the shared catalog if doing so couples other aspects to unrelated details.

## 7. Sharing a pointcut is not sharing advice execution

A catalog only defines a **set of join points**. The aspects referencing the catalog still have their own advice methods, their own ordering, and each advice is adapted by Spring into a corresponding interceptor/advisor.

```text
         SharedPointcuts.submission()
                    |
          +---------+----------+
          |                    |
          v                    v
    AuditAspect           MetricsAspect
    @Before               @AfterReturning
          |                    |
          +---------+----------+
                    |
             Spring AOP proxy
                    |
                    v
             OrderService.submit()
```

**Advice ordering is not decided by the shared pointcut.** If two `@Around` advice methods match the same method, Spring processes them by precedence/ordering; to establish deterministic order between aspects, use `@Order` or `Ordered` where appropriate. On entry, higher-priority advice runs first; on exit, the order is usually reversed due to nested interceptors.

Do not use catalog sharing as a substitute for advice ordering mechanisms.

## 8. Spring AOP-specific characteristics and limitations

### 8.1. Pointcuts must be recognized by Spring in the context

In the `@AspectJ` configuration style, Spring scans/discovers `@Aspect` classes registered as Spring beans to build advisors. The demo registers `SharedPointcuts` and the two aspects via `@Bean`. In a Boot application with the AOP starter, auto-configuration can enable equivalent processing, yet aspects must still be known to the container (e.g., `@Component` within component scan scope).

### 8.2. Proxy boundary does not change

A shared pointcut only enables **reusing expressions**, not expanding join point kinds. With Spring AOP, callers must go through the proxy; `this.otherMethod()` inside the target (self-invocation) does not automatically become a new call through the proxy. Switching from JDK proxy to CGLIB does not solve self-invocation.

### 8.3. JDK/CGLIB does not automatically make every method interceptable

JDK proxies expose interface methods; CGLIB subclass proxies are restricted by `final` classes, `final`/`private` methods, and Java visibility. If the catalog matches a method without a valid call through a Spring proxy, the advice still will not run.

### 8.4. Spring's `bean(...)` does not belong to native AspectJ weaving

Spring AOP has the `bean(namePattern)` extension thanks to its integration with `BeanFactory`. It can be combined with named pointcuts in Spring `@AspectJ` configuration. However, do not copy an expression containing `bean(...)` into an AspectJ compile-time/load-time weaving environment and assume the syntax will behave like Spring AOP.

### 8.5. Do not solve security solely with pointcuts

Even when shared by multiple aspects, a pointcut is still just a call-selection mechanism. Never treat it as an absolute security boundary when callers can hold raw target references, invoke internal methods, or take a code path bypassing the Spring proxy. For access control, define genuine security boundaries and write tests for those call paths.

## 9. Refactoring the catalog and common pitfalls

When renaming `SharedPointcuts`, the method name `submission()`, or package `demo.pointcut`, search for all string references in `@Before`, `@AfterReturning`, `@Around`, and XML configuration. Fully qualified names are not automatically protected by the Java compiler like normal method calls; a mistyped string can prevent an advisor from initializing or cause matching to drop.

After changing the expression itself inside the catalog, retest **the advice of both aspects**: `submit()` must trigger audit/metrics the expected number of times, and `status()` must not run those policies. If one aspect adds `&& @annotation(...)`, that aspect's matched set may be narrower than the catalog; keep separate expectations.

## 10. Parameterized named pointcuts

An application may want to share a pointcut that **binds a runtime argument** so multiple advice methods receive the same kind of context. For example, a named pointcut with a `String` parameter:

```java
@Aspect
public class ArgumentPointcuts {

    @Pointcut("args(orderId)")
    public void withOrderId(String orderId) {
    }
}
```

Then another aspect uses the binding form:

```java
@Aspect
public class ArgumentAuditAspect {

    @Before(
        value =
            "demo.pointcut.ArgumentPointcuts.withOrderId(id) " +
            "&& execution(* demo.service..*.submit(..))",
        argNames = "id"
    )
    public void beforeSubmit(String id) {
        System.out.println("ID=" + id);
    }
}
```

These are **two advanced snippets, not part of the standalone runnable demo**. Running them requires declaring the proper packages/classes and registering the pointcut/aspect beans; `args(...)` binds runtime method arguments by signature. Spring does not invoke the Java method `withOrderId(String)` to fetch data. When sharing this type of pointcut, pay close attention to parameter names, `argNames`, type compatibility, and the target's method signature.

## 11. Proper testing

A true sharing test must invoke the target bean through the Spring proxy, record events/counters **separately per aspect**, and prove the selected method triggers both policies according to their respective advice types. Call an out-of-rule method to confirm no extra events occur. Also test scenarios where the pointcut expression is updated while aspects still reference the right symbol, along with `@Order` ordering if multiple advice methods have ordering dependencies.

`AopUtils.isAopProxy()` is a secondary check: a proxy can exist due to another advisor, so it never replaces assertions on each individual advice.

## 12. Self-check questions

**1.** Two aspects want to use the same `execution(...)`; how do you avoid repeating the long expression?  
**Answer:** Define a named `@Pointcut` in a catalog and reference it using `package.ClassName.pointcutName()`.

**2.** Does Spring invoke the body of a `@Pointcut` method when a business method matches?  
**Answer:** No. That method is a signature/metadata for the expression; the advice is what Spring executes.

**3.** Does changing `public void serviceMethod()` to `private void serviceMethod()` make the expression match fewer methods?  
**Answer:** The expression itself does not change, but the pointcut can no longer be referenced by aspects outside the class under visibility rules.

**4.** In the demo, why does `submit()` run audit and metrics, while `status()` does not?  
**Answer:** The catalog combines `serviceMethod() && submitMethod()`; only `submit()` satisfies both conditions.

**5.** If one aspect uses `SharedPointcuts.serviceMethod()` and another uses `SharedPointcuts.serviceMethod() && @annotation(...)`, are their selected method sets identical?  
**Answer:** Not necessarily, because the second aspect adds an annotation condition.

**6.** Does a shared pointcut specify the execution order of two `@Around` advice methods?  
**Answer:** No. Advisor/advice ordering is a separate Spring mechanism; use `@Order` if ordering is required.

**7.** Why does a shared pointcut not resolve self-invocation?  
**Answer:** Internal calls on the target do not pass through the Spring proxy, so there is no new interception for the pointcut to evaluate.

**8.** Can Spring's `bean(*Service)` expression be used in every kind of AspectJ weaving?  
**Answer:** No. It is a Spring AOP-specific designator tied to bean naming.

## 13. Official documentation

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): pointcut signatures, qualified references, visibility, shared pointcut definitions, and composition.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): Spring registering and reading `@Aspect` beans.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `@Before`, `@AfterReturning`, precedence.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, proxy boundary, and self-invocation.
