# Using within to Restrict the Target Bean Class or Package in Spring AOP

## 1. What Problem Does within Solve in Spring?

When using `@Aspect` to add logging, tracing, auditing, or convention checks to Spring services, we usually do not want advice applied to every Spring bean. We need to precisely restrict the **group of classes or packages containing the methods to be intercepted**.

In Spring AOP, `within(TypePattern)` is a **pointcut designator** used to limit method-execution join points to those within types matching `TypePattern`. According to Spring Framework's description, that is **the execution of methods declared in a matching type**. In applications organized by package, `within` is especially useful for confining aspect logic to the service, controller, or repository layer.

Example:

```java
@Pointcut("within(com.example.orders.service..*)")
public void serviceLayer() {
}
```

The expression above selects method-execution join points belonging to types in package `com.example.orders.service` **and its subpackages**. In Spring AOP, it only takes effect when the method call goes through the **Spring AOP proxy of a Spring-managed bean** and satisfies accompanying conditions.

**Key point:** `within` is a condition based on **type/method-declaration scope**, not a direct condition on the **Spring bean name**, not a scan of Java files on disk, and not a mechanism to automatically register additional Spring beans. A class whose name/package matches but is not managed by Spring will not automatically receive advice from Spring AOP.

This lesson focuses on `within` in Spring Framework under the proxy model, without revisiting general AspectJ syntax or constructor/field-access weaving outside Spring AOP.

### Learning Objectives

After this lesson, you will be able to:

1. Write `within` correctly to select a single class, a single package, or multiple subpackages.
2. Explain the differences between `within`, `execution`, `target`, `this`, `bean`, and `@within` when using Spring AOP.
3. Combine `within` with `execution` to filter both **layer/type** and **method signature**.
4. Understand why a method in a matching package may still not execute advice if the call bypasses the proxy.
5. Write and run a Spring Framework/Java 17 example testing a service in a root package, a service in a subpackage, and a repository outside the scope.

## 2. TypePattern Syntax of within

Commonly used expression:

```text
within(com.example.app.service..*)
```

Where:
- `within(...)` places a constraint on the type containing the method-execution join point.
- `com.example.app.service` is the package path.
- `..` allows subpackage levels, including zero subpackage levels.
- `*` is a wildcard matching type names according to the pattern.

Comparison examples:

| Pointcut | Meaning in Spring AOP | Notes |
| --- | --- | --- |
| `within(com.example.app.service.OrderService)` | Method-execution join points in type `OrderService` | Selects a specific type; the class must still be an eligible target of an AOP proxy |
| `within(com.example.app.service.*)` | Types directly in package `service` | Does not automatically cover package `service.internal` |
| `within(com.example.app.service..*)` | Types in `service` and subpackages at any depth | Common pattern for the service layer |
| `within(com.example.app..*)` | Types across the entire `com.example.app` package tree | Easily too broad if the application has multiple layers |
| `within(com.example.app.service..*) && execution(public * *(..))` | Only public method executions belonging to the service layer | Combines scope and method signature conditions |
| `within(com.example.app.service..*) && !within(com.example.app.service.internal..*)` | Service layer, excluding a specific package tree | Excludes a group of types using the `!` operator |

### 2.1. Difference Between a Single Dot and Two Dots

Suppose the code has this structure:

```text
com.example.app.service.OrderService
com.example.app.service.OrderQuery
com.example.app.service.internal.PriceService
com.example.app.service.internal.impl.LocalCalculator
com.example.app.repository.OrderRepository
```

- `within(com.example.app.service.*)` targets types directly in `service`, such as `OrderService` and `OrderQuery`.
- `within(com.example.app.service..*)` also covers `service.internal.PriceService` and `service.internal.impl.LocalCalculator`.
- Both expressions **do not** select `com.example.app.repository.OrderRepository` because the repository is outside the `service` package tree.

The `..` does not mean "add only one subpackage". It allows multiple package levels; in the `service..*` pattern, it also includes types directly in `service`.

### 2.2. A Specific Class

```java
@Before("within(com.example.app.service.OrderService)")
public void beforeOrderService() {
    System.out.println("inside OrderService");
}
```

This is an illustrative snippet, assuming an `@Aspect` Spring bean and an appropriate `OrderService` class. The pointcut itself does not require methods named `save`, `cancel`, or `find`; it narrows by type. If you want only a specific API, combine it with `execution`.

### 2.3. Do Not Use within to Express Bean Names

Spring bean names such as `orderService` or `pricingService` do not appear in a `within` expression; Java package names do not have to match bean names either. If the requirement is to select beans whose names match `*Service`, Spring AOP provides a dedicated pointcut designator `bean(*Service)`. Both approaches can be combined, but they check different conditions.

## 3. within Is Only a Selection Condition, Not a Proxy Creation Mechanism

An aspect in Spring is typically declared as follows:

```java
@Aspect
@Component
public class ServiceAspect {

    @Pointcut("within(com.example.app.service..*)")
    public void serviceLayer() {
    }

    @Before("serviceLayer()")
    public void beforeServiceMethod() {
        System.out.println("service call");
    }
}
```

In a Spring application with `@AspectJ` support enabled:
1. `@Component` or `@Bean` causes `ServiceAspect` to be registered as a Spring bean. `@Aspect` does **not** automatically act like `@Component`.
2. Spring parses `@Pointcut` and the advice method, then builds the appropriate advisor.
3. The auto-proxy creator evaluates which Spring beans the advisor can apply to.
4. When other code calls through the proxy, Spring checks whether the current method execution falls under `within(com.example.app.service..*)`.
5. Only when both the pointcut and the proxy boundary allow it does `beforeServiceMethod()` run.

**Not every object created via `new` is managed by Spring AOP.** For example:

```java
new OrderService().placeOrder();
```

does not go through a Spring proxy, even though the class is in the `service` package. Likewise, a Spring bean may reside in a matching package yet not be proxied because AOP is not enabled, the aspect is not registered, or no method is eligible.

### Conditions Supported by Spring AOP

Proxy-based Spring AOP supports **method-execution join points on Spring beans**. It does not use `within` to intercept field access (`get`/`set`), constructor execution, or calls between two methods inside the same target in the Java source-code sense. This is the operating boundary of Spring proxies, not a `within` syntax error.

## 4. within vs. execution, target, this, bean, and @within

These designators are easily confused because all of them can be used to restrict aspect scope.

| Designator | What does Spring AOP inspect? | When should it be used? |
| --- | --- | --- |
| `within(TypePattern)` | Method execution declared in a type matching the pattern | Restricting by package, class, or layer |
| `execution(MethodPattern)` | Method execution signature matching the pattern | Selecting method name, return type, visibility, parameters, declaring type |
| `target(TypePattern)` | The **target object behind the proxy** is an instance of the type | Selecting by the actual type of the target object |
| `this(TypePattern)` | The **Spring proxy** is an instance of the type | When inspecting the type or interface exposed by the proxy |
| `bean(NamePattern)` | Spring bean name matches the pattern | Selecting bean groups by naming convention |
| `@within(AnnotationType)` | Method execution declared in a type with a matching annotation | Selecting by a type-level marker annotation |
| `@annotation(AnnotationType)` | Method execution has a matching annotation on the method | Selecting operations by method annotation |

### 4.1. within and execution

The following two pointcuts look similar but have different design goals:

```java
@Pointcut("within(com.example.app.service..*)")
public void inServiceLayer() {
}

@Pointcut("execution(public * com.example.app.service..*.*(..))")
public void publicServiceSignatures() {
}
```

- `within` emphasizes the **type region**, without directly requiring public methods.
- `execution` specifies the method signature—in the example, public methods with any return type, name, and arguments within the indicated declaring-type scope.
- Because Spring AOP intercepts calls through proxies, which methods are actually intercepted also depends on JDK/CGLIB and the call path.

A **readable and maintainable** pattern is separating the two conditions:

```java
@Pointcut("within(com.example.app.service..*)")
public void serviceLayer() {
}

@Pointcut("execution(public * *(..))")
public void publicMethod() {
}

@Pointcut("serviceLayer() && publicMethod()")
public void publicServiceMethod() {
}
```

Here `serviceLayer` is the scope condition, `publicMethod` is the signature condition, and `publicServiceMethod` combines both. This named pointcut can be reused across multiple advices without duplicating long expressions.

### 4.2. within and target

Suppose `com.example.app.service.SpecialOrderService` inherits a method from a superclass located **outside** the `service` package. Distinguish:
- `within(service..*)` describes the **declaring type to which the method execution belongs**.
- `target(SpecialOrderService)` describes the **runtime target instance type**.

You should not make an absolute statement like "every method callable on an instance of `SpecialOrderService` definitely matches `within(service..*)`". For **inherited methods from a superclass declared in another package**, the method/declaring-type evaluation behavior may produce unexpected results. If you need to constrain by runtime target class/hierarchy, `target(...)` or a carefully designed `execution(...)` may be more suitable; test with the actual JDK/CGLIB proxy in use.

### 4.3. within and this

In Spring proxy AOP:
- `this(Type)` looks at the **proxy**.
- `target(Type)` looks at the **target object**.

A JDK proxy only implements the relevant interfaces and is generally **not** an instance of the implementation class. A CGLIB class proxy is a subclass of the implementation class. Therefore, a `this(com.example.app.service.OrderService)` pointcut can depend on the proxy type while `target(...)` is evaluated on the real target.

`within` classifies **method execution by type pattern**. It is not a syntax replacement for `this` or `target`.

### 4.4. within and bean

Example:

```java
@Pointcut("within(com.example.app.service..*) && bean(*Service)")
public void namedServiceInServicePackage() {
}
```

Meaning: selects only invocations that both belong to the service layer by type pattern and originate from a bean whose Spring name matches `*Service`. In Spring AOP, `bean(...)` is a specific extension for bean instances, not a standard designator for AspectJ weaving.

Pay attention to actual naming conventions: a bean named `orderGateway` might reside in the `service` package yet not match `bean(*Service)`.

### 4.5. within and @within

`within(com.example.app.service..*)` filters by **type/package name**. Meanwhile, `@within(com.example.app.Monitored)` filters method executions declared in types bearing a matching annotation. Marker annotations allow types in different packages to still be selected.

The form:

```java
@Pointcut("within(com.example.app.service..*)"
        + " && @annotation(com.example.app.Audited)")
public void auditedServiceOperation() {
}
```

restricts by layer and annotation **on the method**, so it differs from `@within` which is an annotation **on the type**. This is a syntax illustration; a real application must have the `Audited` annotation and a registered aspect.

## 5. Combining in Spring: Operators and Named Pointcuts

Spring supports combining pointcuts with:
- `&&`: both conditions must match.
- `||`: either condition matches.
- `!`: negates the condition.

Example:

```java
@Pointcut("within(com.example.app.service..*)"
        + " && execution(public * *(..))"
        + " && !within(com.example.app.service.internal..*)")
public void publicExternalServiceMethods() {
}
```

This expression selects public method executions in the service layer, while excluding types in the `internal` package and all its subpackages. In addition to evaluating the pointcut, the method must still be called through a Spring proxy for advice to run.

If multiple aspects need to share a definition, you can place pointcuts in a shared class:

```java
package com.example.app.aop;

import org.aspectj.lang.annotation.Pointcut;

public final class LayerPointcuts {
    private LayerPointcuts() {
    }

    @Pointcut("within(com.example.app.service..*)")
    public static void inService() {
    }
}
```

**Note:** The snippet above only illustrates sharing pointcut definitions, not a recommended pattern for registering beans. In practice, named pointcuts shown in official examples are **methods on a pointcut-defining class**, typically declared non-static with an empty body. If you choose to use `@Pointcut` in a non-`@Aspect` class, verify pointcut referencing behavior with your specific library/version setup. A simpler and safer approach is to declare named pointcuts in the same `@Aspect` class as in the runnable example below.

## 6. Full Runnable Example: Root Package, Subpackage, and Out-of-Scope Repository

Goals of the example:
1. A method in `demo.service` receives advice.
2. A method in `demo.service.internal` also receives advice because `..*` covers subpackages.
3. Bean `demo.repository.InventoryRepository` does not receive advice because it is outside `within(demo.service..*)`.
4. The internal call `this.reserve(...)` inside the target shows that Spring AOP only intercepts **calls through the proxy**.

The example uses **Java 17+, Spring Framework 6.1.14, Gradle**. We create a plain Spring Framework application using `@EnableAspectJAutoProxy(proxyTargetClass=true)` so services without interfaces also get class-based proxies. No Spring Boot or database is needed.

### 6.1. Project Structure

```text
spring-aop-within/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── DemoApplication.java
    ├── config/AppConfig.java
    ├── aop/LayerAspect.java
    ├── service/InventoryService.java
    ├── service/internal/PricingService.java
    └── repository/InventoryRepository.java
```

### 6.2. Gradle Configuration

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-within'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.DemoApplication'
}
```

`spring-context` provides `AnnotationConfigApplicationContext` and Spring bean configuration. `spring-aop` provides the AOP infrastructure, and `aspectjweaver` provides the AspectJ library needed for Spring to parse `@AspectJ` pointcut expressions.

### 6.3. Spring Service in the Root Package

File `src/main/java/demo/service/InventoryService.java`:

```java
package demo.service;

public class InventoryService {

    public String reserve(String sku) {
        System.out.println("service:reserve:" + sku);
        return "reserved:" + sku;
    }

    public void reserveInternally() {
        System.out.println("service:reserveInternally");
        reserve("SELF");
    }
}
```

Both `reserve` and `reserveInternally` are declared in a type belonging to `demo.service`. Both methods are public and non-final, so a Spring CGLIB proxy can intercept calls **from clients through the proxy**.

In `reserveInternally()`, the line `reserve("SELF")` is a **self-invocation on the target**; it does not go back through the proxy. Therefore, when a client calls `reserveInternally()`, advice runs only for `reserveInternally` (the outer call), not a second time for the inner `reserve`.

### 6.4. Spring Service in a Subpackage

File `src/main/java/demo/service/internal/PricingService.java`:

```java
package demo.service.internal;

public class PricingService {

    public int price(String sku) {
        System.out.println("service.internal:price:" + sku);
        return 10;
    }
}
```

Type `PricingService` resides under `demo.service.internal`. The expression `within(demo.service..*)` **covers subpackages**, so the `price` method will match when a client calls it through the Spring proxy.

### 6.5. Repository Outside the Service Layer

File `src/main/java/demo/repository/InventoryRepository.java`:

```java
package demo.repository;

public class InventoryRepository {

    public void save(String sku) {
        System.out.println("repository:save:" + sku);
    }
}
```

`InventoryRepository` is also a Spring bean, but its package is `demo.repository`, outside the `demo.service` tree. Therefore, an aspect restricted with `within(demo.service..*)` does not advise the `save` method. This proves **pointcut scoping**, not that the repository is unmanaged by Spring.

### 6.6. Aspect Declared in a Separate Package

File `src/main/java/demo/aop/LayerAspect.java`:

```java
package demo.aop;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class LayerAspect {

    @Pointcut("within(demo.service..*)")
    public void serviceTypes() {
    }

    @Pointcut("execution(public * *(..))")
    public void publicMethods() {
    }

    @Before("serviceTypes() && publicMethods()")
    public void beforeServiceCall(JoinPoint joinPoint) {
        String type = joinPoint.getTarget().getClass().getSimpleName();
        String method = joinPoint.getSignature().getName();
        System.out.println("advice:" + type + "." + method);
    }
}
```

Here:
- `serviceTypes()` specifies the Java type scope in `service` and subpackages.
- `publicMethods()` requires public method execution.
- `@Before("serviceTypes() && publicMethods()")` runs only if **both** conditions match.
- `JoinPoint.getTarget()` returns the target object, so `getClass().getSimpleName()` displays a stable implementation name in the example.
- `LayerAspect` does not need to be in the same package as the services. The **aspect's package** is not what `within(demo.service..*)` checks.

### 6.7. Registering Beans and Enabling Spring AOP

File `src/main/java/demo/config/AppConfig.java`:

```java
package demo.config;

import demo.aop.LayerAspect;
import demo.repository.InventoryRepository;
import demo.service.InventoryService;
import demo.service.internal.PricingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public InventoryService inventoryService() {
        return new InventoryService();
    }

    @Bean
    public PricingService pricingService() {
        return new PricingService();
    }

    @Bean
    public InventoryRepository inventoryRepository() {
        return new InventoryRepository();
    }

    @Bean
    public LayerAspect layerAspect() {
        return new LayerAspect();
    }
}
```

`@EnableAspectJAutoProxy` enables Spring to detect `@Aspect` declarations. `LayerAspect` is registered with `@Bean`, because `@Aspect` itself does not create a Spring bean. Component scanning is omitted so the example has only the listed beans.

Enabling `proxyTargetClass=true` ensures service classes without interfaces still receive class-based AOP proxies, but it does not force `InventoryRepository` to become an AOP proxy if it has no matching advisor.

### 6.8. Main Program and Run Command

File `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import demo.config.AppConfig;
import demo.repository.InventoryRepository;
import demo.service.InventoryService;
import demo.service.internal.PricingService;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            InventoryService inventory =
                    context.getBean(InventoryService.class);
            PricingService pricing =
                    context.getBean(PricingService.class);
            InventoryRepository repository =
                    context.getBean(InventoryRepository.class);

            System.out.println("result=" + inventory.reserve("P-7"));
            System.out.println("price=" + pricing.price("P-7"));
            repository.save("P-7");

            inventory.reserveInternally();

            System.out.println("serviceProxy=" +
                    AopUtils.isAopProxy(inventory));
            System.out.println("childProxy=" +
                    AopUtils.isAopProxy(pricing));
            System.out.println("repositoryProxy=" +
                    AopUtils.isAopProxy(repository));
        }
    }
}
```

From the project directory, run using an installed Gradle:

```bash
gradle run
```

If the project includes the Gradle Wrapper, use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows.

Lines printed by the **Java application**, excluding Gradle build/logging or environment messages:

```text
advice:InventoryService.reserve
service:reserve:P-7
result=reserved:P-7
advice:PricingService.price
service.internal:price:P-7
price=10
repository:save:P-7
advice:InventoryService.reserveInternally
service:reserveInternally
service:reserve:SELF
serviceProxy=true
childProxy=true
repositoryProxy=false
```

### 6.9. Explaining the Results

- `advice:InventoryService.reserve` appears before `service:reserve:P-7`: the method belongs to `demo.service` and is called by the client through the Spring AOP proxy.
- `advice:PricingService.price` appears before `service.internal:price:P-7`: `..*` covers types in the `demo.service.internal` subpackage.
- `repository:save:P-7` has no preceding advice line: the repository is outside the `within(demo.service..*)` scope.
- `advice:InventoryService.reserveInternally` appears when the client calls that public method through the proxy.
- There is **no** second `advice:InventoryService.reserve` before `service:reserve:SELF`: the internal call `this.reserve(...)` does not go through the proxy.
- `serviceProxy=true` and `childProxy=true` prove the two services actually received Spring AOP proxies.
- `repositoryProxy=false` shows the repository did not need an AOP proxy in the example configuration. It is still a Spring bean managed by the context.

With this simple configuration, the example does not depend on multiple aspect ordering or cache/transaction state. In a real application with other advisors, a repository could still be proxied for another reason even if it does not match `LayerAspect`'s pointcut.

## 7. When Does within Not Match as Expected?

### 7.1. Matching Package but Instantiated Directly with new

```java
InventoryService service = new InventoryService();
service.reserve("MANUAL");
```

This is a plain Java object. No Spring AOP proxy is used, so `LayerAspect` provides no advice even though the package name matches completely. Obtain a Spring-managed reference from the context or inject it via Spring.

### 7.2. Matching Package but Self-Invocation

`within` can accurately describe both `reserve()` and `reserveInternally()`. However, when the target executes `this.reserve(...)`, the call does not go through the AOP proxy. Switching to `@Around` or broadening the package pattern does not fix that limitation.

If both methods need advice, design another collaborating bean and call it through that bean's Spring-managed proxy. Use self-proxy access only when there is a clear reason and you understand the Spring AOP coupling cost.

### 7.3. Using Only a Single-Dot Wildcard

`within(demo.service.*)` does not select types in `demo.service.internal`. When subpackage structures grow regularly, consider `within(demo.service..*)` if the requirement truly covers the entire service layer.

Conversely, if you only want classes directly in `demo.service`, using `.*` can be more precise. Do not automatically use `..*` across the entire application if there are utility, infrastructure, or internal implementation packages you do not want advised.

### 7.4. Method Inherited by Target from a Type Declared in Another Package

For example, a method implemented in `com.example.common.BaseService` is inherited by a target in `com.example.app.service`. The pointcut `within(com.example.app.service..*)` and a condition selecting the runtime target are not always equivalent. What needs checking is the **method implementation/declaring type evaluated by Spring** when building the interceptor chain.

To select a **target of a service type** rather than restricting the method declaration scope, consider `target(com.example.app.service.SomeService)` or add other constraints and test them. For JDK dynamic proxies, methods exposed via an interface can also differ from implementation methods, so an integration test on the actual proxy type is more reliable evidence than inferring from package names alone.

### 7.5. private/final Methods or Constructors

Proxy-based Spring AOP does not advise constructor executions. Class-based proxies cannot override `final` and `private` methods; JDK proxies only expose methods belonging to proxied interfaces. `within` does not turn uninterceptable calls into join points intercepted by Spring.

To inspect the proxy type:

```java
AopUtils.isJdkDynamicProxy(bean);
AopUtils.isCglibProxy(bean);
```

This is a diagnostic snippet; it requires `bean` to be a Spring-managed bean and importing `AopUtils`. Do not rely on proxy class names because naming can change across versions.

### 7.6. Confusing Annotation/Service Scanning with Pointcuts

`@ComponentScan("com.example.app.service")` is a **bean discovery** configuration. `within(com.example.app.service..*)` is a Spring AOP **method join point selection** configuration. Writing a correct pointcut when the bean is not registered does not create the bean. Conversely, scanning all services into Spring beans does not automatically enable Spring AOP if the required infrastructure/aspect is missing.

## 8. Aligning within with Layered Architecture

Suppose an application has three layers:

```text
com.example.shop
├── web
│   ├── OrderController
│   └── admin/AdminController
├── service
│   ├── OrderService
│   └── pricing/PriceService
└── repository
    ├── OrderRepository
    └── jdbc/JdbcOrderRepository
```

Named pointcuts can be created per layer:

```java
@Pointcut("within(com.example.shop.web..*)")
public void webLayer() {
}

@Pointcut("within(com.example.shop.service..*)")
public void serviceLayer() {
}

@Pointcut("within(com.example.shop.repository..*)")
public void repositoryLayer() {
}

@Pointcut("serviceLayer() && execution(public * *(..))")
public void publicServiceOperation() {
}
```

This is a **snippet inside an `@Aspect` class**, not a standalone program; the methods have empty bodies and return type `void`. The benefit of naming them is that if the package layout changes, you only need to edit the expression in one place.

However, a "layer" is an application design decision:
- An `OrderService` class in the `service` package registered multiple times under different bean names still falls within the corresponding `within` scope.
- A bean named `orderService` whose class resides in an infrastructure package **does not automatically** match `within(service..*)`.
- An aspect placed in `com.example.shop.aop` can still advise services/repositories, because the pointcut inspects the target's method executions rather than requiring the aspect to be in the same package.

If service APIs are defined by interfaces located in different modules/packages from their implementations, combining `within` with `execution`/`target` or designing pointcuts around business interfaces may be clearer. Official Spring documentation also distinguishes between **layer-scoped** pointcuts and pointcuts targeting **methods on service interfaces**.

## 9. Performance and Scope of Application

The `within` pointcut can help the Spring/AspectJ expression matcher exclude out-of-scope classes early, reducing how much needs to be evaluated for other conditions. This is especially useful when an aspect has many advisors or complex expressions.

Even so, `within` should not be treated as a standalone performance optimization:
- Application overhead also depends on the number of beans/proxies, number of method calls, advice type, logging I/O, and work done inside the advice.
- Overly broad pointcuts like `within(com.example..*)` can advise unintended beans.
- Runtime conditions such as `args` or binding annotations may require more evaluation than static type/method conditions.
- Measure on real workloads when performance requirements exist; do not invent fixed speedup numbers.

Good practice is to **restrict by type/package first**, then combine method signature or annotation conditions for precision. For example:

```java
@Pointcut("within(com.example.shop.service..*)"
        + " && execution(public * *(..))"
        + " && @annotation(com.example.shop.Traceable)")
public void tracedPublicServiceMethod() {
}
```

If `Traceable` is a runtime annotation on observed methods, the expression above restricts advice to those exact operations in the service layer. When an annotation is unnecessary, do not add extra conditions just to make the expression look more complex.

## 10. Quick Diagnostic Table

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| Service in subpackage has no advice | Used `within(service.*)` instead of `within(service..*)` | Check full package of target and expression |
| Repository also receives advice while filtering service | Another aspect or advisor also matches; repository was accidentally placed in service package | Inspect advisor chain and actual package |
| Bean in service package is not proxied | Aspect is not a bean yet, AOP is not enabled, or no advisor matches | Check Spring context, `@EnableAspectJAutoProxy`, `AopUtils` |
| Same method advice runs from controller but not from internal method | Self-invocation bypasses proxy | Compare call paths and split into separate bean if needed |
| Bean created via `new` has no advice | Object is not managed by container | Inject or `getBean` from Spring |
| Public superclass call does not match as expected | Method declaring type and runtime target type differ | Try `target` or `execution`; test on actual proxy |
| Only want bean names ending in `Service` | `within` filters types, not bean names | Use `bean(*Service)` or combine conditions |
| Want classes with annotation regardless of package | Package filtering via `within` cannot express annotation requirement | Use `@within` or `@target` per desired semantics |
| `private`/`final` method has no advice under CGLIB | Cannot be overridden | Change boundary/API or choose appropriate model |
| Service is scanned but `@Before` does not print | Bean scanning differs from enabling AOP; pointcut might be wrong | Check aspect registration, proxy, method, and package |
| AOP uses JDK proxy but client tries casting to implementation | JDK proxy implements interface, not subclass | Inject interface or review proxy type config |

## 11. Checklist Before Using within in an Application

1. **Determine the exact package tree.** Do you need types in only that exact package or also subpackages?
2. **Determine which methods need advice.** Every public method or only specific names/annotations?
3. **Register the aspect as a Spring bean.** `@Aspect` does not replace `@Component` or `@Bean`.
4. **Enable AOP in the ApplicationContext owning the target.** With plain Spring Framework use `@EnableAspectJAutoProxy`; Spring Boot can auto-configure when dependencies are present.
5. **Check the proxy type.** JDK/CGLIB affects interceptable methods; for type inheritance, test specifically.
6. **Run tests via a Spring-managed reference.** `new` and self-invocation do not verify whether advice matches.
7. **Observe one matching method and one non-matching method.** Include both a subpackage example and an out-of-service example to prove the scope.
8. **Keep expressions sufficiently narrow.** Do not apply logging, security validation, or tracing to an entire package tree without reason.

## 12. Conclusion

`within` is a clear way to express **class and package boundaries** for Spring AOP. The pattern `within(com.example.service..*)` restricts method-execution join points to the service layer, including subpackages, while `within(com.example.service.*)` is narrower to the exact package. Combining `within` with `execution` or annotations restricts both the layer and the operation.

However, **a matching type pattern is not enough for advice to run**: the bean must be Spring-managed, AOP must be enabled, a proxy must be created, and calls must go through the proxy. With JDK/CGLIB, inherited methods, and self-invocation, verify actual runtime behavior rather than looking solely at package paths in source code.

### Official Spring Documentation

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): `within`, `execution`, `this`, `target`, `bean`, wildcards, and combining pointcuts.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): registering `@Aspect` and enabling Spring AOP.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): Spring AOP proxy limitations and self-invocation.
- [Spring Framework — Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html): `ClassFilter`, `MethodMatcher`, and `AspectJExpressionPointcut`.
