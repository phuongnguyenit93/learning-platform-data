# Rules for Selecting a Proxy Mechanism in Spring Framework

## 1. Questions to Answer Before Configuring Spring AOP

When Spring AOP applies advice to a Spring bean, callers usually do not receive the target object directly: the container supplies a **proxy** to route calls through an interceptor chain. Spring has two main proxy types:

- **JDK dynamic proxy:** the proxy implements the target's required interfaces.
- **Class-based proxy (CGLIB):** the proxy is a subclass generated from the target class.

What you must determine is **how Spring decides which type to choose, which configurations can change that decision, and the consequences for advised methods or injectable types**.

In plain Spring Framework, the common default rule is:

> If the target has suitable interfaces to proxy, Spring prefers a **JDK dynamic proxy**. If the target has no interface to proxy, Spring uses a **class-based proxy (CGLIB)**. When `proxyTargetClass = true`, Spring **forces a class-based proxy**, even if the target has interfaces.

This is **the rule for Spring AOP proxy mechanisms under typical configurations**, not a claim that every form of proxy in Spring (scoped proxies, custom `TargetSource`, proxies built programmatically with `ProxyFactory`) shares identical selection behavior.

**Spring Boot differs from plain Spring Framework in its configuration defaults:** Boot's auto-configuration typically sets **class-based proxies as the default**. If you want JDK proxies in Boot, set `spring.aop.proxy-target-class=false` and ensure targets have suitable interfaces.

This lesson focuses on proxy selection by **Spring AOP on Spring-managed beans**, rather than covering plain Java proxy fundamentals or AspectJ weaving independent of Spring.

## 2. Why Must Spring Choose Between Two Proxy Types?

In Spring AOP, an aspect or Spring advisor describes behavior to apply to method invocations. The auto-proxy creator inspects the bean being created, finds matching advisors, and creates a proxy if needed. Choosing between JDK and CGLIB happens at **proxy creation time**, before a caller actually invokes a method.

```text
ApplicationContext registers bean definitions
                    |
                    v
     Create target bean + determine advisors
                    |
                    v
      Does target need a Spring AOP proxy?
             /                \
            No                Yes
            |                   |
       Plain bean        Force class proxy?
                            /          \
                          Yes           No
                           |             |
                         CGLIB     Target has suitable
                                       interfaces?
                                       /        \
                                     Yes         No
                                      |           |
                                     JDK        CGLIB
                                       \          /
                                        v        v
                                   Caller gets proxy
                                        |
                                        v
                                  method invocation
                                        |
                                        v
                                 advice -> target
```

The diagram shows **the default selection rule and forcing class proxies** in Spring Framework in an environment without other overriding configurations. Spring also considers explicitly configured interfaces, concurrent transaction/AOP infrastructure, `optimize` mode, specific proxy types, and target class restrictions. Therefore, actual results should be measured on beans in the `ApplicationContext`.

Important: **having an interface does not mean a bean is guaranteed to be proxied**. Spring must have an applicable advisor/advice; if there is no AOP requirement, the bean can be returned unwrapped.

## 3. Practical Decision Table

| Spring AOP context | Target implements a business interface? | Class proxy setting | Typical outcome |
| --- | --- | --- | --- |
| Plain Spring Framework, default | Yes | `proxyTargetClass=false` | **JDK dynamic proxy**. |
| Plain Spring Framework, default | No | `proxyTargetClass=false` | **CGLIB**, because a JDK proxy cannot represent a class lacking suitable interfaces. |
| Plain Spring Framework, forced class | Yes or no | `proxyTargetClass=true` | **CGLIB**, if the class can be subclassed/proxied. |
| Spring Boot default auto-configuration | Yes or no | Class-based by default | **CGLIB**, when the bean genuinely needs an AOP proxy and is proxyable. |
| Spring Boot with `spring.aop.proxy-target-class=false` | Yes | Interface proxy allowed | Usually **JDK dynamic proxy**, unless another configuration forces class proxies. |
| Spring Boot with `spring.aop.proxy-target-class=false` | No | Lets Spring default decide | **CGLIB**, due to the lack of suitable interfaces for a JDK proxy. |
| Custom Spring proxy factory | Depends on target | Depends on `proxyInterfaces`, `proxyTargetClass`, `TargetSource` | Must read the factory configuration; do not infer from the default table. |

Setting `proxyTargetClass=false` **does not mean forcing JDK proxies at all costs**. It simply does not mandate class-based proxies; Spring still must pick a valid mechanism for the target.

If no advisor applies, `AopUtils.isAopProxy(bean)` can be `false` regardless of whether the class has interfaces or whether Spring Boot has AOP configured.

## 4. Recognizing JDK Proxies and CGLIB Proxies in Spring

### 4.1. JDK Dynamic Proxy: The Interface Is the Contract for Callers to Go Through the Proxy

Example interface:

```java
public interface PaymentOperations {
    String pay(String orderId);
}
```

Implementing class:

```java
public class PaymentService implements PaymentOperations {
    @Override
    public String pay(String orderId) {
        return "paid:" + orderId;
    }

    public String implementationOnly() {
        return "internal";
    }
}
```

The two snippets above are **illustrative fragments**, without packages/imports; the complete runnable example is in section 8.

When Spring creates a **JDK dynamic proxy** for `PaymentService` against `PaymentOperations`:

- Callers can receive the proxy via `PaymentOperations` and call `pay()`.
- The proxy **is not an instance of `PaymentService`**, so casting the proxy to the concrete implementation usually fails.
- `implementationOnly()` **is not in the `PaymentOperations` interface**, so it cannot be called through that JDK proxy reference.
- Whether Spring AOP can advise a method still depends on the method belonging to the interface contract, the pointcut, and the call passing through the proxy; do not assume that merely having a method on the implementation makes it accessible on a JDK proxy.

At dependency injection boundaries, Spring recommends injecting **the interface type** when using interface proxies. If a component requests `PaymentService` by implementation type instead, a JDK proxy does not directly satisfy that type requirement; the application may fail injection/lookup depending on the declaration.

### 4.2. CGLIB: A Class Proxy Extending the Target Class

With a class-based proxy, Spring generates a subclass at runtime. Because the proxy is a subclass of `PaymentService`, `proxy instanceof PaymentService` can evaluate to `true`, and overridable methods can receive advice through the proxy.

Limitations:

- **`final` classes cannot be subclassed** to create a CGLIB class proxy.
- **`final` methods cannot be overridden**, so they cannot be advised under the class-proxy model.
- **`private` methods cannot be overridden**, so they are not viable interception points.
- Methods not visible to the subclass (for example, package-private methods on a superclass in a different package) cannot be advised by a class proxy.
- Constructors are not method executions wrapped by Spring AOP proxies; self-invocation inside the target still bypasses the proxy.

**No separate CGLIB dependency is needed just to enable Spring AOP class proxies**: Spring Framework already bundles a repackaged CGLIB variant in `spring-core`. When using `@Aspect`, you still need the Spring AOP dependencies and appropriate annotation/pointcut support, usually via a Spring Boot starter or `spring-context` and `aspectjweaver`.

### 4.3. Case of a `final` Class That Has an Interface

A `final` class implementing an interface can work via a **JDK interface proxy** because the proxy does not need to subclass that class. Having an implementing method marked `final` also does not necessarily block interception through a JDK proxy: the proxy intercepts the call at **the interface**, then delegates to the target.

However, if configuration **forces class proxies with `proxyTargetClass=true`**, having a `final` target class can prevent Spring from creating the proxy and cause the application to fail at startup. Therefore, do not use `proxyTargetClass=true` as a “fix for all AOP errors” without examining the class hierarchy.

## 5. Configuring Proxy Selection in Plain Spring Framework

### 5.1. The `@EnableAspectJAutoProxy` Annotation

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class InterfaceProxyConfig {
    // @Bean definitions or @ComponentScan
}
```

When class proxies are not forced, beans with suitable interfaces are normally proxied with JDK; beans without suitable interfaces must use CGLIB if Spring needs to proxy them.

Forcing class-based proxies:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class ClassProxyConfig {
    // @Bean definitions or @ComponentScan
}
```

These are two **alternative config fragments**; you should not enable both simultaneously and guess which annotation “wins.” Spring configuration also takes into account other places enabling AOP/transactions in the context.

### 5.2. The XML `aop` Namespace

With XML declaring the proper `aop` namespace:

```xml
<aop:aspectj-autoproxy proxy-target-class="false"/>
```

or:

```xml
<aop:aspectj-autoproxy proxy-target-class="true"/>
```

When using Spring AOP XML schema advisors:

```xml
<aop:config proxy-target-class="true">
    <!-- Application XML advisors/aspects -->
</aop:config>
```

The snippets above are **XML fragments**, not complete XML documents with namespaces/schemas. The `proxy-target-class` attribute acts similarly to requesting class-based proxies, though you must understand that Spring can merge proxy configuration with other features in the same context.

### 5.3. When AOP Configurations Are Merged

If the same `ApplicationContext` contains both an interface-proxy setting (`false`) and a class-proxy request (`true`) from Java config, XML AOP, or transaction infrastructure, Spring can merge them and apply **the stronger setting (`true`)** to the auto-proxy creator. Thus, the proxy selection table in section 3 is accurate only after verifying the effective configuration. Check all relevant configuration sources and verify the runtime proxy type with `AopUtils`, especially when using Spring Framework and Spring Boot alongside transaction AOP.

## 6. Spring Boot: Why Does the Default Differ from Plain Spring Framework?

Spring Boot provides **auto-configuration** for Spring AOP and typically defaults to class-based proxies. Example configuration in `application.properties`:

```properties
# Use interface-based proxies when possible:
spring.aop.proxy-target-class=false
```

Unless another configuration forces class-based proxies, Spring will consider JDK proxies for targets with interfaces. If a target does not implement a suitable interface, Spring still needs CGLIB when a proxy must be created.

To configure class-based proxies explicitly:

```properties
spring.aop.proxy-target-class=true
```

Do not mechanically apply the advice “Spring always chooses JDK first” to Spring Boot applications: **Boot's configured default can differ from plain Spring Framework core's default**.

Points to verify:

1. The application includes the AOP starter matching the Spring Boot line in use (for example, Boot 3.x uses `spring-boot-starter-aop`; Boot 4.x has `spring-boot-starter-aspectj`).
2. The aspect bean is managed by Spring, via `@Aspect` + `@Component` or `@Bean`; the `@Aspect` annotation alone does not register a bean.
3. Whether other Java/XML configurations such as `@EnableAspectJAutoProxy(proxyTargetClass=true)` or transaction auto-proxying override the intent to use JDK.
4. Whether the bean is actually proxied because an advisor applies; if no advisor matches, comparing JDK vs. CGLIB on that bean is meaningless.

**Scope limit of the property:** `spring.aop.proxy-target-class` adjusts Boot's auto-configuration. It does not guarantee changing every custom proxy created by other libraries or every declared scoped proxy.

## 7. Spring Framework 7: Per-Bean Proxy Tuning When Appropriate

Spring Framework **7.0+** adds the ability to choose the proxy type for a specific bean using **`@Proxyable`** with options such as `INTERFACES` and `TARGET_CLASS`, per the official documentation. This is a **7.x line** capability, not an annotation available in Spring Framework 6.1/6.2.

This feature is useful when an application defaults to class proxies overall but a specific bean needs an interface proxy, or vice versa. Check your current Spring version and the bean's contract before using it; do not copy Spring 7 configuration into a project running Spring 6.

The hands-on example in the next section **pins Spring Framework 6.1.14** to illustrate the common `proxyTargetClass` rules without using `@Proxyable`.

## 8. Runnable Java 17+ Example: Comparing JDK and CGLIB on the Same Targets

The example runs **two independent `AnnotationConfigApplicationContext` instances** with the same bean definitions and aspect:

- First context: `proxyTargetClass=false`; `PaymentService` has an interface so it uses JDK, while `ReportService` has no interface so it uses CGLIB.
- Second context: `proxyTargetClass=true`; both services use CGLIB.
- `TraceAspect` applies `@Before` to two methods; service calls go through the proxies.
- Inspect results via `AopUtils` instead of guessing from auto-generated class names.

### 8.1. Directory Structure

```text
spring-proxy-selection/
├── pom.xml
└── src/main/java/com/example/proxy/
    ├── PaymentOperations.java
    ├── PaymentService.java
    ├── ReportService.java
    ├── TraceAspect.java
    └── DemoApp.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-proxy-selection</artifactId>
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

`spring-context` transitively pulls in the core Spring modules in the corresponding graph, including Spring AOP; `aspectjweaver` enables Spring to parse `@Aspect` and pointcut expressions. Manage versions with an appropriate BOM/dependency management when transferring the example to a real application; do not mix Spring Framework versions arbitrarily.

### 8.3. `src/main/java/com/example/proxy/PaymentOperations.java`

```java
package com.example.proxy;

public interface PaymentOperations {
    String pay(String orderId);
}
```

### 8.4. `src/main/java/com/example/proxy/PaymentService.java`

```java
package com.example.proxy;

public class PaymentService implements PaymentOperations {

    @Override
    public String pay(String orderId) {
        return "paid:" + orderId;
    }

    public String implementationOnly() {
        return "implementation-only";
    }
}
```

### 8.5. `src/main/java/com/example/proxy/ReportService.java`

```java
package com.example.proxy;

public class ReportService {
    public String generate(String id) {
        return "report:" + id;
    }
}
```

`ReportService` intentionally implements no business interfaces so you can observe Spring having to use a class-based proxy when its method is advised.

### 8.6. `src/main/java/com/example/proxy/TraceAspect.java`

```java
package com.example.proxy;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {

    @Before(
        "execution(public * com.example.proxy.PaymentService.pay(..))"
        + " || execution(public * com.example.proxy.ReportService.generate(..))"
    )
    public void before(JoinPoint joinPoint) {
        System.out.println("[AOP] " + joinPoint.getSignature().getName());
    }
}
```

The `execution(...)` expressions are evaluated by Spring AOP against the method/target class. Both methods are public; advice does not run for `PaymentService.implementationOnly()` because the pointcut does not select that method.

### 8.7. `src/main/java/com/example/proxy/DemoApp.java`

```java
package com.example.proxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class DemoApp {

    @Configuration
    static class Beans {
        @Bean
        PaymentOperations paymentOperations() {
            return new PaymentService();
        }

        @Bean
        ReportService reportService() {
            return new ReportService();
        }

        @Bean
        TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    @Configuration
    @Import(Beans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    static class DefaultProxyConfig {
    }

    @Configuration
    @Import(Beans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class ClassProxyConfig {
    }

    private static void run(String label, Class<?> configClass) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(configClass)) {

            PaymentOperations payment =
                    context.getBean(PaymentOperations.class);
            ReportService report = context.getBean(ReportService.class);

            System.out.println("[" + label + "] paymentJdk="
                    + AopUtils.isJdkDynamicProxy(payment));
            System.out.println("[" + label + "] paymentCglib="
                    + AopUtils.isCglibProxy(payment));
            System.out.println("[" + label + "] reportCglib="
                    + AopUtils.isCglibProxy(report));
            System.out.println("[" + label + "] paymentIsConcrete="
                    + (payment instanceof PaymentService));

            System.out.println("[" + label + "] "
                    + payment.pay("P-1"));
            System.out.println("[" + label + "] "
                    + report.generate("R-1"));
        }
    }

    public static void main(String[] args) {
        run("DEFAULT", DefaultProxyConfig.class);
        run("CLASS", ClassProxyConfig.class);
    }
}
```

Two independent contexts ensure that `proxyTargetClass=false` and `proxyTargetClass=true` **are not merged into the same context**, avoiding skewing the comparison. `Beans` acts as a shared configuration class imported separately into each context.

### 8.8. Running the Project and Comparing Stdout

In the `spring-proxy-selection` directory with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.proxy.DemoApp
```

Lines printed by the program itself in order, excluding environment-dependent Maven/SLF4J messages:

```text
[DEFAULT] paymentJdk=true
[DEFAULT] paymentCglib=false
[DEFAULT] reportCglib=true
[DEFAULT] paymentIsConcrete=false
[AOP] pay
[DEFAULT] paid:P-1
[AOP] generate
[DEFAULT] report:R-1
[CLASS] paymentJdk=false
[CLASS] paymentCglib=true
[CLASS] reportCglib=true
[CLASS] paymentIsConcrete=true
[AOP] pay
[CLASS] paid:P-1
[AOP] generate
[CLASS] report:R-1
```

**Explanation:**

1. `PaymentService` implements `PaymentOperations`; in the DEFAULT context, Spring can use a JDK proxy to expose `PaymentOperations`. Thus `paymentJdk=true` and `paymentIsConcrete=false`.
2. `ReportService` has no business interface, yet advice matches `generate()`; Spring creates a CGLIB subclass proxy for this bean even though the DEFAULT configuration does not force class proxies.
3. In the CLASS context, `proxyTargetClass=true` forces class proxies for every target bean needing AOP, so `PaymentService` is wrapped with CGLIB and `payment instanceof PaymentService` is true.
4. Both contexts have a `TraceAspect` bean, and both methods needing advice execute through proxies. **Choosing JDK or CGLIB changes the proxy type and which methods/types are visible through the proxy; it does not alter the business results `paid:P-1` or `report:R-1`.**
5. There is no advice log line for `implementationOnly()`: the pointcut does not select that method, even though with CGLIB this method could be called through a `PaymentService`-typed reference if the application were designed to access it that way.

**Experimental note:** if you change `PaymentOperations paymentOperations()` to return type `PaymentService`, how Spring infers types during bean creation may differ, but proxy selection rules still primarily depend on the target class, interfaces, and `proxyTargetClass`. Avoid relying on an implementation type when actively choosing JDK proxies.

## 9. Proxy Strategy and Bean Injectability

This is the most noticeable impact when changing the proxy mechanism in a Spring application.

### 9.1. Injecting by Interface When Using JDK Proxies

Example Spring-managed client:

```java
public class CheckoutController {
    private final PaymentOperations payment;

    public CheckoutController(PaymentOperations payment) {
        this.payment = payment;
    }
}
```

This fragment is safe under the interface contract when the Spring bean is proxied by JDK; the client does not need to know `PaymentService` is the actual implementation.

Conversely:

```java
public class CheckoutController {
    private final PaymentService payment;

    public CheckoutController(PaymentService payment) {
        this.payment = payment;
    }
}
```

If the bean is replaced by a **JDK proxy** implementing only `PaymentOperations`, an injection requesting the concrete `PaymentService` may not be satisfied. Adjust the injection to the interface or consider class-based proxies deliberately; not every application needs `proxyTargetClass=true`.

### 9.2. Interface Methods vs. Implementation-Only Methods

When using a JDK proxy, callers using the `PaymentOperations` contract can only access `pay()`, not `implementationOnly()`. In Spring AOP, if only an implementation method is advised while callers have no path to call that method through the interface proxy, the expected behavior will not occur as intended.

Common design directions are:

- Move business methods meant to be called externally into an appropriate interface.
- If the application truly must expose the concrete type or non-interface methods, choose class-based proxies after checking class/`final` method restrictions.
- If the target only has internal methods, recognize that self-invocation still bypasses the proxy even when CGLIB is chosen.

### 9.3. CGLIB Does Not “Fix” Self-Invocation

```java
public class PaymentService {
    public void checkout() {
        audit(); // this.audit(), does not go back through the proxy.
    }

    public void audit() {
        // Method needing advice.
    }
}
```

This is an illustrative fragment. When a caller invokes `proxy.checkout()`, Spring can intercept `checkout()`; however, inside the target, `this.audit()` does not automatically go back through the proxy to trigger `audit()`'s advice. **Forcing CGLIB does not solve self-invocation either**. Typically, extract the responsibility needing advice into another bean and call it through a Spring-managed dependency.

## 10. Distinguishing AOP-Selected Proxies from Other Spring Proxies

A Spring application can contain multiple proxy mechanisms:

| Mechanism | Purpose | Do the exact rules in this lesson apply? |
| --- | --- | --- |
| Spring AOP auto-proxy for `@Aspect` | Intercepts Spring bean method calls per advisors | Yes, according to the AOP/auto-proxy creator configuration. |
| Transaction advisor/proxy | `@Transactional` via proxy | Uses closely related proxy infrastructure; shared config can affect selection. |
| Scoped proxy | Injects a shorter-lived bean into a longer-lived bean | Has its own interface/class selection settings; do not guess from `@EnableAspectJAutoProxy` alone. |
| Manually configured `ProxyFactory` or `ProxyFactoryBean` | Creates a proxy on demand for a specific target | Depends on `proxyTargetClass`, `proxyInterfaces`, and the specific factory configuration. |
| AspectJ compile-time/load-time weaving | Modifies via bytecode weaving | **Not** the JDK/CGLIB Spring proxies described in this lesson. |

One AOP proxy can hold multiple advisors (audit, transaction, security...), and Spring usually merges standard auto-proxy creator configurations. Therefore, **seeing that a bean is a CGLIB proxy does not prove a specific audit aspect was applied**, and **seeing two AOP-enabling configurations does not prove two separate proxies exist**.

## 11. Inspecting Proxy Types in a Real Application

Given a bean retrieved from the context:

```java
Object bean = context.getBean("paymentOperations");

System.out.println(org.springframework.aop.support.AopUtils.isAopProxy(bean));
System.out.println(org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean));
System.out.println(org.springframework.aop.support.AopUtils.isCglibProxy(bean));
```

This is a fragment within a program that has a `context` variable, not a standalone Java file. The three APIs answer three different questions:

- `isAopProxy`: is it a Spring AOP proxy according to Spring's checks?
- `isJdkDynamicProxy`: is it a proxy based on JDK dynamic proxy?
- `isCglibProxy`: is it a Spring CGLIB class proxy?

You can also inspect advisors in `Advised` and execute the method under test directly. Do not use `bean.getClass().getName()` as the sole evidence: generated proxy class names are runtime details that can change across versions.

A test should verify **both the proxy type and the behavioral contract**:

1. The aspect and target actually reside in the context and auto-proxy infrastructure is enabled.
2. The bean has an applicable advisor and `AopUtils` returns the expected proxy type.
3. Lookup/injection by interface/concrete type matches the design.
4. Advice runs the right number of times for matching methods and does not run for non-matching methods.
5. Business return values and exceptions are not altered unexpectedly.
6. `final`, `private`, self-invocation, or outside-context calls are not expected to act as normal Spring AOP interception points.
7. If multiple contexts or Java/XML/Boot configs exist, confirm the proxy type in **the context that actually owns the bean**, not only in an isolated test context.

## 12. Common Errors When Selecting a Proxy

| Symptom | Likely cause | How to check/fix |
| --- | --- | --- |
| `@Autowired PaymentService` fails while injecting `PaymentOperations` works | Bean was replaced with a JDK proxy that is not the implementation class. | Use interface injection, or switch to class proxies with good reason. |
| Set `proxyTargetClass=false` yet the bean still uses CGLIB | Target has no interface, or another infrastructure component requested class proxies. | Check interfaces and all proxy configs in the context. |
| Using Spring Boot and a bean with an interface is still CGLIB | Boot auto-configuration defaults to preferring class proxies. | Check `spring.aop.proxy-target-class` and other AOP settings. |
| Forced CGLIB but a `final` class causes an error | Cannot subclass a `final` class. | Design an interface proxy or remove the `final` constraint when reasonable. |
| `final` method is not advised by CGLIB | Proxy cannot override that method. | Move the interception point to an overridable method or a compatible interface proxy. |
| `@Aspect` is present yet neither JDK nor CGLIB proxy is created | Aspect is not a bean, AOP is not enabled, or no advisor matches. | Check registration, auto-proxy creator, pointcut. |
| Calling a method within the same class and advice does not run | Self-invocation bypasses the proxy. | Call through another Spring-managed bean; switching JDK/CGLIB will not fix this automatically. |
| Method exists on the implementation but cannot be called via JDK proxy | Not declared on the proxy interface. | Add the contract to the interface or deliberately choose class proxies. |
| `proxyTargetClass=false` is present yet CGLIB is still forced | Another XML/transaction/AOP config requires `true`. | Audit the context; the unified auto-proxy creator uses the stronger setting. |
| Issues with Java module system when proxying special classes | CGLIB is restricted by module visibility/open packages. | Inspect the class/module to proxy; avoid forcing subclassing by default on unopened classes. |
| Unfamiliar class name containing `$$SpringCGLIB$$` appears | This can be a valid Spring proxy class. | Use `AopUtils` and inspect advisors/methods; do not treat the class name alone as an error. |

## 13. Decision Workflow for a Specific Spring Project

When adding an aspect or fixing a proxy bug:

1. **Determine whether an AOP proxy is needed.** Is there a Spring-managed target bean and an advisor/pointcut that actually matches?
2. **Check the runtime environment:** plain Spring Framework, Spring Boot, or a custom proxy factory; read the exact defaults for that environment.
3. **Inspect the interface contract:** does the service have a business interface and are callers injecting by interface?
4. **Choose the appropriate proxy capability:** Framework's default is usually JDK if interfaces exist; use CGLIB if there are no interfaces or when forced and the class allows it.
5. **Audit all proxy settings in the context:** `@EnableAspectJAutoProxy`, XML `<aop:aspectj-autoproxy>`, `<aop:config>`, transaction support, Spring Boot properties; do not look at only one annotation.
6. **Check proxy type limitations:** concrete injection, implementation-only methods, `final` classes/methods, `private`, Java modules, and self-invocation.
7. **Verify with `AopUtils` and a real call:** proxy type, correct advice, return values, exceptions, invocation count.
8. **Maintain a reasoned choice:** only force CGLIB when concrete types/class methods are needed and the class permits subclassing; interface proxies fit when the API contract centers on interfaces.

### Official Spring Documentation

- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — AOP Proxies: https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html
- Spring Framework — @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — ProxyFactoryBean and JDK/CGLIB selection: https://docs.spring.io/spring-framework/reference/core/aop-api/pfb.html
- Spring Boot — Aspect-Oriented Programming: https://docs.spring.io/spring-boot/reference/features/aop.html

**The goal is not “as much CGLIB as possible” or “always JDK for speed,” but selecting the Spring AOP proxy that fits the interface contract, bean injection style, pointcuts, and active configuration mechanism.** Once you verify the proxy type and the real call path, you can distinguish proxy-selection bugs from aspect-registration, pointcut, or self-invocation bugs.
