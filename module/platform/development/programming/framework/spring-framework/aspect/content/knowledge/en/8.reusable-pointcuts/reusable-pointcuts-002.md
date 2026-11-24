# Combining Pointcuts by Architecture Layer or Functional Group in Spring AOP

## 1. Purpose of organizing pointcuts

In a Spring application, an `@Aspect` is typically allowed to intercept only a specific part of the system. For example, one aspect logs invocations in the **service layer**, another measures execution time for **repositories**, while auditing targets only **data-modifying commands**. If every advice copies a long expression directly, changing a package, naming convention, or annotation easily causes inconsistent behavior across aspects.

Spring AOP's solution is to **define small, meaningful named pointcuts and then combine them with logical operators**. One pointcut describes the architecture layer, another describes the functional group, and another describes method conditions. Pointcuts are composed into rules such as "public command in service" and reused across multiple aspects.

An example that reads like a sentence:

```java
@Pointcut("serviceLayer() && commandMethod()")
public void serviceCommand() {}
```

`serviceCommand()` means a method execution **in the service layer AND belonging to the command group**. Separating conditions makes them easier to read and modify than stuffing everything into a single `@Before` or `@Around`.

**Scope:** Organizing pointcuts in **Spring Framework with `@AspectJ` and proxy-based Spring AOP**. This lesson does not teach standalone AspectJ in full: all expressions here only take effect when Spring detects the aspect, the Spring bean is proxied, the method is called through the proxy, and the pointcut matches.

### Learning outcomes

After this lesson, you will be able to:
- Categorize pointcuts by **architecture layer**, **functional group**, **method signature**, and **metadata**.
- Use `&&`, `||`, `!` with parentheses to compose exact scopes.
- Organize a shared `CommonPointcuts` class across multiple `@Aspect` classes.
- Distinguish `within`, `execution`, `bean`, and `@annotation` for grouping.
- Run a complete Spring AOP example with a service, subpackage, repository, and two aspects.
- Test matched/unmatched conditions, handle self-invocation, and avoid unintended duplicate advice execution.

## 2. How do the architecture axis and functional axis differ?

A hypothetical structure:

```text
com.example.shop
├── web/
│   └── OrderController
├── service/
│   ├── CheckoutService
│   └── pricing/PricingService
├── repository/
│   └── OrderRepository
└── aop/
    ├── ArchitecturePointcuts
    ├── AuditAspect
    └── TraceAspect
```

| Axis | Question | Spring AOP Example |
| --- | --- | --- |
| Architecture layer | Which package does the type/method belong to? | `within(com.example.shop.service..*)`, `within(com.example.shop.repository..*)` |
| Functional group | Is the operation a read, write, payment, or admin action? | `execution(public * load*(..))`, `execution(public * place*(..))` |
| Signature | Which public method, return type, or parameters? | `execution(public * *(..))` |
| Annotation | Does the method or target type carry a business marker? | `@annotation(com.example.shop.aop.Audited)` |
| Bean name | Which naming convention does the Spring bean follow? | `bean(*Service)` |

For example, `CheckoutService` belongs to the service layer yet has both `loadOrder` (query) and `placeOrder` (command). `OrderRepository` belongs to the repository layer and may have a `save` method whose name also indicates a write operation. If the goal is to "audit commands in service", you should not use `within(service..*)` alone, because that would audit queries too. Nor should you use `execution(* place*(..))` alone if similarly named methods exist in unrelated layers.

**Core design point:** One pointcut describes the **target class/layer of interest**, while another describes the **operation to observe**. Use AND to take the intersection of the two sets.

## 3. Combining with AND, OR, NOT

### 3.1. AND — `&&`

```java
@Pointcut("within(com.example.shop.service..*)")
public void serviceLayer() {}

@Pointcut("execution(public * *(..))")
public void publicOperation() {}

@Pointcut("serviceLayer() && publicOperation()")
public void publicServiceOperation() {}
```

`publicServiceOperation` requires the method to be both in the service layer and public. The `..` in `service..*` includes the `service` package and its subpackages (for example `service.pricing`). `service.*` only selects types directly in that package.

Another requirement:

```java
@Pointcut("execution(public * load*(..))")
public void queryMethod() {}

@Pointcut("serviceLayer() && queryMethod()")
public void serviceQuery() {}
```

`queryMethod()` is defined via a naming convention; Spring does not automatically know whether a method has side effects. `serviceQuery()` restricts selection specifically to `load...` methods in the service layer.

### 3.2. OR — `||`

```java
@Pointcut("within(com.example.shop.service..*)")
public void serviceLayer() {}

@Pointcut("within(com.example.shop.repository..*)")
public void repositoryLayer() {}

@Pointcut("serviceLayer() || repositoryLayer()")
public void applicationLayer() {}
```

`applicationLayer` selects method executions in **either service or repository**. This is the union of two sets. It is appropriate when you want to record metrics for both layers, and inappropriate if you only want `save` methods of the repository.

### 3.3. NOT — `!`

```java
@Pointcut("within(com.example.shop.service..*)")
public void serviceLayer() {}

@Pointcut("within(com.example.shop.service.internal..*)")
public void internalServicePackage() {}

@Pointcut("serviceLayer() && !internalServicePackage()")
public void serviceExceptInternal() {}
```

Negation should be paired with a **positive scope**. `!within(service.internal..*)` standing alone can match almost every other bean in the application.

### 3.4. Parentheses when combining multiple conditions

```java
@Pointcut("(serviceLayer() || repositoryLayer())"
        + " && execution(public * *(..))"
        + " && !within(com.example.shop.internal..*)")
public void visibleApplicationOperations() {}
```

Meaning: **(service OR repository)** AND **public method** AND **not in the internal package**. Parentheses express clear intent and help reviewers avoid precedence mistakes.

**Remember that** logical operators determine which method executions are selected; they do not determine the execution order of multiple advice methods. Advice ordering belongs to `@Order`/`Ordered` and Spring's advisor ordering mechanism.

## 4. Named pointcuts for reuse

Turn layer/functional conditions into small pointcuts and then reference them by name in the composite pointcut:

```java
public class ArchitecturePointcuts {
    @Pointcut("within(com.example.shop.service..*)")
    public void serviceLayer() {}

    @Pointcut("execution(public * place*(..))")
    public void commandMethod() {}

    @Pointcut("serviceLayer() && commandMethod()")
    public void serviceCommand() {}
}
```

In an aspect bean, `@Before("com.example.shop.aop.ArchitecturePointcuts.serviceCommand()")` selects only public `place*` methods in the service layer. This is a snippet of a dedicated class and must be placed in the stated package. Public named pointcuts enable reuse across aspects; `@Pointcut` methods do not execute logic when matching. Details on library structure and sharing contracts are covered in the lesson **"Sharing Pointcuts Across Aspects"**.

## 5. Choosing patterns for real Spring architectures

### 5.1. Package scope with `within`

```java
@Pointcut("within(com.example.shop.web..*)")
public void webLayer() {}

@Pointcut("within(com.example.shop.service..*)")
public void serviceLayer() {}

@Pointcut("within(com.example.shop.repository..*)")
public void repositoryLayer() {}
```

`within` in Spring AOP describes method executions declared within matching types. Be careful with methods **inherited from a superclass outside the package**: declaring type criteria and runtime target type are not completely identical. If the true intent is "beans implementing a service interface", `target(ServiceInterface)` or `execution(* ServiceInterface.*(..))` may be more accurate, depending on the architecture.

### 5.2. Grouping based on method signature

```java
@Pointcut("execution(public * load*(..))"
        + " || execution(public * find*(..))")
public void queryMethods() {}

@Pointcut("execution(public * place*(..))"
        + " || execution(public * cancel*(..))")
public void commandMethods() {}
```

This is a convention established by the development team, not automatic semantics assigned by Spring. A method `loadAndMutate` with side effects still matches the query group if its name starts with `load`. For audits requiring higher precision, use a marker annotation with clear reviews/tests.

### 5.3. Grouping via annotations

Suppose `@AuditedCommand` is defined with `@Target(ElementType.METHOD)` and `@Retention(RetentionPolicy.RUNTIME)`. You can write:

```java
@Pointcut("serviceLayer()"
        + " && @annotation(com.example.shop.aop.AuditedCommand)")
public void auditedServiceCommand() {}
```

This condition selects an annotation on the **method**, rather than package or method name. It decouples command classification from naming conventions, though placing annotations on interfaces vs implementations and choosing JDK/CGLIB proxies must be verified at runtime.

Distinguish `@annotation` (annotation on the method) from `@within` (on the declaring type), `@target` (on the runtime target type), and `@args` (on the runtime type of actual arguments).

### 5.4. Grouping by bean name

Spring AOP provides `bean(*Service)`: it selects Spring beans by **name**, such as `orderService` or `pricingService`, when naming conventions fit. It is not the same as `within(...service..*)`, which checks type/package. When a bean is named `paymentGateway` even though its class is `PaymentService`, the expression `bean(*Service)` may not match. `bean` is a Spring-specific designator, not portable syntax for standalone AspectJ weaving.

### 5.5. Different bounded contexts

When code has `com.example.orders.service`, `com.example.catalog.service`, and `com.example.billing.service`, a scope pattern like `within(com.example..service..*)` can be used **only when** package naming is genuinely stable. If you want to audit only orders, define an additional `ordersServiceLayer()` instead of broadly expanding to all bounded contexts.

## 6. Standalone runnable Java 17 example on Spring Framework

The example contains two Spring aspects sharing `ArchitecturePointcuts`. It demonstrates:

1. Auditing only **service commands**.
2. Tracing only **service queries** and **repository operations**.
3. Services in a subpackage still matching `within(demo.service..*)`.
4. Self-invocation not triggering an extra advice execution, even though the internal method would match if called through the proxy.

**Environment:** Java 17+, Spring Framework `6.1.14`, Gradle, and AspectJ Weaver `1.9.22.1`. This is a plain Spring Framework application without Spring Boot auto-configuration.

### 6.1. Files and Gradle configuration

```text
spring-aop-pointcut-composition/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── DemoApplication.java
    ├── config/AppConfig.java
    ├── aop/ArchitecturePointcuts.java
    ├── aop/AuditAspect.java
    ├── aop/TraceAspect.java
    ├── service/CheckoutService.java
    ├── service/pricing/PricingService.java
    └── repository/OrderRepository.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-pointcut-composition'
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

`spring-context` provides Spring IoC and `AnnotationConfigApplicationContext`; `spring-aop` provides the auto-proxy infrastructure; `aspectjweaver` enables Spring to parse `@AspectJ` expressions.

### 6.2. Class sharing named pointcuts

`src/main/java/demo/aop/ArchitecturePointcuts.java`:

```java
package demo.aop;

import org.aspectj.lang.annotation.Pointcut;

public class ArchitecturePointcuts {

    @Pointcut("within(demo.service..*)")
    public void serviceLayer() {}

    @Pointcut("within(demo.repository..*)")
    public void repositoryLayer() {}

    @Pointcut("execution(public * *(..))")
    public void publicOperation() {}

    @Pointcut("execution(public * load*(..))")
    public void queryOperation() {}

    @Pointcut("execution(public * place*(..))")
    public void commandOperation() {}

    @Pointcut("serviceLayer() && queryOperation()")
    public void serviceQuery() {}

    @Pointcut("serviceLayer() && commandOperation()")
    public void serviceCommand() {}

    @Pointcut("repositoryLayer() && publicOperation()")
    public void repositoryOperation() {}
}
```

`ArchitecturePointcuts` only provides definitions; **it does not need to be a Spring bean**. The named pointcut `serviceQuery` is the AND of the service layer and query methods; `serviceCommand` is the AND of the service layer and command methods; `repositoryOperation` is the AND of the repository layer and public methods.

### 6.3. Target in the service package

`src/main/java/demo/service/CheckoutService.java`:

```java
package demo.service;

public class CheckoutService {

    public void placeOrder(String id) {
        System.out.println("target:placeOrder:" + id);
    }

    public void loadOrder(String id) {
        System.out.println("target:loadOrder:" + id);
    }

    public void placeWithInternalLoad(String id) {
        System.out.println("target:placeWithInternalLoad:" + id);
        loadOrder(id);
    }
}
```

`placeOrder` and `placeWithInternalLoad` are commands by the `place` prefix; `loadOrder` is a query by the `load` prefix. When `placeWithInternalLoad` calls `loadOrder` directly, that is a self-invocation on `this`: the Spring AOP proxy does not intercept the internal call.

### 6.4. Target in a service subpackage

`src/main/java/demo/service/pricing/PricingService.java`:

```java
package demo.service.pricing;

public class PricingService {

    public void loadPrice(String sku) {
        System.out.println("target:loadPrice:" + sku);
    }
}
```

`demo.service.pricing` matches `within(demo.service..*)` thanks to `..*`, and `loadPrice` matches `queryOperation`.

### 6.5. Target in repository

`src/main/java/demo/repository/OrderRepository.java`:

```java
package demo.repository;

public class OrderRepository {

    public void save(String id) {
        System.out.println("target:save:" + id);
    }
}
```

The repository lies outside the service package, yet its `save` method is public and matches `repositoryOperation`. It is not selected by `serviceCommand` merely because its name implies a write operation.

### 6.6. Two aspects referencing the same pointcut library

`src/main/java/demo/aop/AuditAspect.java`:

```java
package demo.aop;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {

    @Before("demo.aop.ArchitecturePointcuts.serviceCommand()")
    public void beforeCommand(JoinPoint joinPoint) {
        System.out.println(
            "audit:" + joinPoint.getSignature().getName());
    }
}
```

`src/main/java/demo/aop/TraceAspect.java`:

```java
package demo.aop;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {

    @Before("demo.aop.ArchitecturePointcuts.serviceQuery()")
    public void beforeQuery(JoinPoint joinPoint) {
        System.out.println(
            "trace:query:" + joinPoint.getSignature().getName());
    }

    @Before("demo.aop.ArchitecturePointcuts.repositoryOperation()")
    public void beforeRepository(JoinPoint joinPoint) {
        System.out.println(
            "trace:repository:" + joinPoint.getSignature().getName());
    }
}
```

`AuditAspect` uses the command group, while `TraceAspect` uses query and repository. They both reference named pointcuts in one place; there is no need to copy `within(...)` into each advice.

### 6.7. Spring bean configuration

`src/main/java/demo/config/AppConfig.java`:

```java
package demo.config;

import demo.aop.AuditAspect;
import demo.aop.TraceAspect;
import demo.repository.OrderRepository;
import demo.service.CheckoutService;
import demo.service.pricing.PricingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public CheckoutService checkoutService() {
        return new CheckoutService();
    }

    @Bean
    public PricingService pricingService() {
        return new PricingService();
    }

    @Bean
    public OrderRepository orderRepository() {
        return new OrderRepository();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

`@EnableAspectJAutoProxy` enables the infrastructure that reads advisors from `@Aspect`. The two aspects are created as Spring beans via `@Bean`; the pointcut-only class is not registered. `proxyTargetClass=true` ensures that the three target classes without interfaces are still proxied by Spring AOP using subclassing (CGLIB). In an application with interfaces, JDK proxies can be used if configured appropriately.

### 6.8. Main and stdout

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import demo.config.AppConfig;
import demo.repository.OrderRepository;
import demo.service.CheckoutService;
import demo.service.pricing.PricingService;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            CheckoutService checkout =
                context.getBean(CheckoutService.class);
            PricingService pricing =
                context.getBean(PricingService.class);
            OrderRepository repository =
                context.getBean(OrderRepository.class);

            checkout.placeOrder("O-1");
            checkout.loadOrder("O-1");
            pricing.loadPrice("P-2");
            repository.save("O-1");
            checkout.placeWithInternalLoad("O-2");

            System.out.println("checkoutProxy=" +
                AopUtils.isAopProxy(checkout));
            System.out.println("pricingProxy=" +
                AopUtils.isAopProxy(pricing));
            System.out.println("repositoryProxy=" +
                AopUtils.isAopProxy(repository));
        }
    }
}
```

Command to run from the directory containing `build.gradle`:

```bash
gradle run
```

If Gradle Wrapper is generated, use `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows).

**Counting only lines printed by the Java program** (excluding Gradle/logger output):

```text
audit:placeOrder
target:placeOrder:O-1
trace:query:loadOrder
target:loadOrder:O-1
trace:query:loadPrice
target:loadPrice:P-2
trace:repository:save
target:save:O-1
audit:placeWithInternalLoad
target:placeWithInternalLoad:O-2
target:loadOrder:O-2
checkoutProxy=true
pricingProxy=true
repositoryProxy=true
```

### 6.9. Explanation by pointcut matrix

| Method invocation | Layer match | Functional group | Result |
| --- | --- | --- | --- |
| `checkout.placeOrder` | `serviceLayer` | `commandOperation` | `audit:placeOrder` before target |
| `checkout.loadOrder` from main | `serviceLayer` | `queryOperation` | `trace:query:loadOrder` before target |
| `pricing.loadPrice` | `serviceLayer` (subpackage) | `queryOperation` | `trace:query:loadPrice` before target |
| `repository.save` | `repositoryLayer` | `publicOperation` | `trace:repository:save` before target |
| `checkout.placeWithInternalLoad` | `serviceLayer` | `commandOperation` | `audit:placeWithInternalLoad` before target |
| `loadOrder` called internally from `placeWithInternalLoad` | Would match query by type/signature | But is `this.loadOrder` | No second query advice |

The three `...Proxy=true` lines confirm that the three Spring beans are proxied. Each bean has at least one matching advisor. However, not every advice runs on every method; different pointcut conditions select different groups of invocations.

**Self-invocation result:** `target:loadOrder:O-2` appears, but there is no `trace:query:loadOrder` right before that line, because the call from `placeWithInternalLoad` does not go back through the Spring proxy. This is an inherent limitation of Spring AOP proxies and cannot be fixed simply by broadening `execution` or `within`.

## 7. When to use OR/NOT, and when to create a new pointcut?

Suppose the system starts adding `cancelOrder` and `findOrder`:
- If the write naming convention is `place*` or `cancel*`, you can define the command group using OR.
- If queries are `load*` or `find*`, you can define the query group using OR.
- If a `service.internal` package must be excluded, use AND with a scoped negation `!within(service.internal..*)`.
- If a group requires separate logic (e.g., auditing only payment operations), create a specifically named pointcut such as `paymentCommand`. Do not apply an overly broad "serviceCommand" to every audit rule.

Replacement example for the `commandOperation` method:

```java
@Pointcut("execution(public * place*(..))"
        + " || execution(public * cancel*(..))")
public void commandOperation() {}
```

Because `serviceCommand` already references `commandOperation`, there is no need to edit all `@Before` annotations across aspects. This is the direct benefit of organizing pointcuts.

## 8. Coordination with Spring AOP infrastructure

Several Spring-specific details to remember:

1. **An aspect must be a Spring bean.** `@Aspect` does not automatically replace `@Component` or `@Bean`.
2. **AOP must be enabled in the right context.** `@EnableAspectJAutoProxy` belongs to the `ApplicationContext` that declares it; child or other contexts are not automatically post-processed by a parent context.
3. **The auto-proxy creator selects advisors per bean.** If a service has no matching methods or no other advisors, Spring is not obligated to create a proxy for it just because you declared `@EnableAspectJAutoProxy`.
4. **Spring only intercepts method executions through proxies.** Code calling `new Service()`, constructor execution, field access, or `this.method()` does not receive advice the way calls through a Spring proxy do.
5. **Proxy type has consequences.** With JDK dynamic proxies, clients typically call through interfaces; with CGLIB, `final` classes/methods cannot be overridden to advise. Do not choose a pointcut based on an implementation class and assume every method can be intercepted.
6. **Multiple aspects can match the same invocation.** `@Order`/`Ordered` and advisor precedence affect ordering. Overlapping pointcuts may be intentional or a design mistake.
7. **The Spring-specific `bean` designator** is useful when modules organize beans by name, but it cannot be treated as equivalent to `within`/`target`.
8. **Do not use naming conventions as the sole security boundary.** If an operation is security/authorization-sensitive, appropriate Spring Security method authorization or validation and real integration tests may be required.

## 9. Testing pointcuts: both matched and unmatched cases

For `serviceLayer() && commandMethod()`, test according to a scenario table: a service with `placeOrder()` must match; a service with `loadOrder()` must not match the command condition; a bean outside service with `placeOrder()` must not match the layer condition; a method in `service.pricing` checks whether `..*` covers subpackages. Merely observing that a proxy exists is not enough: you must assert the exact advice events/counters.

Add a self-invocation case to prove internal calls do not pass back through the proxy. These tests protect the intersection's meaning before and after expression changes; the lesson **"Testing Matched and Unmatched Pointcut Cases"** implements a practical JUnit suite.

## 10. Performance, maintainability, and architecture

Spring documentation recommends combining a **kinded** designator (especially `execution`) with a **scoping** designator (`within`) when appropriate so the pointcut has a clear scope and can be matched efficiently. Naming a pointcut does not by itself make matching faster; what matters is **constraining the exact region to advise** and having a verifiable structure.

If a project migrates from `com.example.shop.service` to modules like `com.example.orders.application` or `com.example.billing.application`, centralizing layer definitions allows fixing it in one place. Still, tests are needed to confirm the new targets are actually created by Spring and advice is not unintentionally lost.

Recommended organizational conventions:
- **Meaningful names:** `serviceQuery`, `repositoryOperation`, `auditedCommand`, not just `pc1`, `pc2`.
- **No logic inside named pointcut methods:** empty body; logic runs in `@Before`/`@Around`.
- **Do not duplicate package patterns across aspects:** reuse via class/method name.
- **Do not lump everything into one overly broad expression:** split by layer and functional group.
- **Test positive and negative scopes:** ensure calls outside the layer are not advised.
- **Separate responsibilities:** the pointcuts class describes *where*; the aspects describe *what to do*.

## 11. Implementation checklist

Before applying, cross-check the architecture scope (`within`, `execution`, `bean`) against the business scope (method name/annotation); place explicit parentheses when combining `&&`, `||`, `!`; ensure aspect beans are registered and callers use Spring proxies. Test a service in the main layer, a service in a subpackage, a repository, and an out-of-scope bean. If changing `load*`/`place*` conventions, rerun both positive and negative cases to detect impact.

## 12. Conclusion

**Organizing pointcuts by architecture layer and functional group is how you turn a scattered set of AOP expressions into clear, shareable, and testable rules.** Use `within` or `execution` to describe the layer, method names or annotations to classify business groups, and combine them with `&&`, `||`, `!`. Put shared named pointcuts into a dedicated class so each `@Aspect` focuses on its advice.

Finally, always remember the Spring AOP boundary: only method calls **through a Spring proxy** on a Spring bean are advised. A pointcut with the right package/signature will not cause internal calls on `this` to be intercepted.

### Official documentation

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): combining pointcuts, naming, `CommonPointcuts`, `within`/`execution`/`bean`, and matching rules.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): declaring `@Before`, `@Around`, and advice ordering.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): enabling Spring AOP and registering `@Aspect`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB, proxy call boundary, self-invocation.
