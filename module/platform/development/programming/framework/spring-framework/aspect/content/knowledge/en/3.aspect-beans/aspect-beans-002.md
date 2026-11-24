# Registering an Aspect with @Component or a @Bean Method in Spring

## 1. Problem to Solve

In Spring AOP with the `@AspectJ` declaration style, a class annotated with `@Aspect` **does not automatically become a Spring bean**. For Spring to read its advice and use them when creating proxies for target beans, we must **register an instance of the aspect class in the right Spring `ApplicationContext`**. Two common Java configuration approaches are:

1. **`@Aspect` + `@Component`**, allowing `@ComponentScan` to find and register the aspect by convention.
2. **`@Aspect` + `@Bean` method**, allowing Spring configuration to explicitly create, name, and supply dependencies to the aspect.

Both serve **the same Spring AOP infrastructure**. Choose one approach that fits how the application manages beans; only one aspect instance needs to be registered for a single configuration pattern, avoiding creating two instances with the same advice and causing duplicate advice execution.

Lesson boundary: focuses on **aspect bean registration in Spring**, interaction with component scan, configuration and dependency injection, and verifying proxies/advice. It does not repeat general AOP or switch to AspectJ weaving mechanisms.

## 2. Distinguishing Three Easily Confused Roles

| Component | Main function in Spring | Is it enough for advice to run? |
| --- | --- | --- |
| `@Aspect` on a class | Declares that the class contains `@AspectJ`-style pointcuts/advice. | **No**. Not a stereotype that default component scan treats as a bean candidate. |
| `@Component` on an aspect class | Marks the class as a Spring component candidate to scan and create a bean. | **Not enough** without `@Aspect`, auto-proxy infrastructure, or a matching pointcut/call. |
| `@Bean` on a `@Configuration` method | Registers the object returned by the factory method as a Spring bean, without needing `@Component` on the object's class. | **Not enough** if the object does not belong to an `@Aspect` class or `@AspectJ` support is not enabled. |
| `@EnableAspectJAutoProxy` | In Spring Framework Java config, enables detecting advisors from aspect beans and creating proxies for targets when matched. | Requires proper context configuration, AspectJ Weaver on the classpath, and appropriate target/calls. |
| `@Service`, `@Repository`, `@Controller` on a target | Brings business logic/adapters into the container via corresponding component scan. | Target must be managed by Spring and the call must go through a proxy to be intercepted. |

**Two separate verification dimensions:**

- **Does the aspect bean exist yet?** `context.getBeansOfType(AuditAspect.class)` or the list of bean names proves the container knows about the aspect.
- **Is the Spring AOP infrastructure using that aspect yet?** A target can be proxied and matching method calls run advice. You need to observe behavior, not infer it from bean creation alone.

Even when an aspect is a Spring bean, a method on the target may still not be advised because it does not match the pointcut, due to internal calls, because the target is not a Spring bean, or because AOP configuration is not enabled.

## 3. Approach 1: `@Aspect` Combined with `@Component`

Use when the aspect is a class owned by the application, fitting the component scanning mechanism already used to register `@Service` and other Spring components.

```java
package com.example.aspectdemo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("execution(public * com.example.aspectdemo.OrderService.place(..))")
    public void beforePlace() {
        System.out.println("audit:place");
    }
}
```

Important conditions:

1. `@Aspect` makes Spring recognize pointcut/advice metadata on the class.
2. `@Component` allows **default component scan** to register that class as a bean.
3. `@ComponentScan` must be enabled for the right package, or in Spring Boot, the class must be placed under the package scanned by `@SpringBootApplication`.
4. `@EnableAspectJAutoProxy` in plain Spring Framework (or corresponding auto-configuration in Boot) converts metadata from aspect beans into Spring AOP advisors.
5. The target must be a Spring bean, the pointcut must match, and the caller must go through the Spring proxy.

### Scan Scope Is a Practical Requirement

Example:

```java
@Configuration
@EnableAspectJAutoProxy
@ComponentScan(basePackages = "com.example.aspectdemo")
class AppConfig {
}
```

Suppose `AuditAspect` belongs to `com.example.aspectdemo`; the config above allows finding the aspect. If only `com.example.api` is scanned, the aspect in `com.example.aspectdemo` will not appear automatically. When running Spring Boot, the package containing the `@SpringBootApplication` class determines the default scan area; aspects outside that scope need explicit scan/import declarations.

**Note:** `@Aspect` is **not** a meta-annotation of `@Component`; a class with only `@Aspect` is not registered by component scan by default. You can define a custom stereotype based on `@Component`, but there is no need to do so for ordinary examples.

### Dependency Injection When Using `@Component`

Because an aspect is a Spring bean, it can receive dependencies via **constructor injection** just like other components:

```java
@Aspect
@Component
public class AuditAspect {
    private final AuditSink sink;

    public AuditAspect(AuditSink sink) {
        this.sink = sink;
    }

    @Before("execution(public * com.example.aspectdemo.OrderService.place(..))")
    public void beforePlace() {
        sink.record("place");
    }
}
```

Here `AuditSink` must also be registered by Spring. Spring resolves the constructor when creating the aspect bean. There is no need to instantiate the aspect with `new` in business code. Constructor injection makes dependencies explicit, easy to test, and avoids ambiguous field injection.

## 4. Approach 2: Declaring an Aspect via a `@Bean` Method

Use when you want to **manage aspect creation explicitly**: when needing complex constructors, configuration dependencies, selecting aspects by profile/condition, or when the aspect class should not or cannot be annotated with `@Component`.

```java
package com.example.aspectdemo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AuditSink sink;

    public AuditAspect(AuditSink sink) {
        this.sink = sink;
    }

    @Before("execution(public * com.example.aspectdemo.OrderService.place(..))")
    public void beforePlace() {
        sink.record("place");
    }
}
```

The class above **intentionally does not have `@Component`**. In Java configuration:

```java
package com.example.aspectdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public AuditAspect auditAspect(AuditSink sink) {
        return new AuditAspect(sink);
    }
}
```

This is an **illustrative configuration** snippet, assuming `AuditSink` and the target service are already registered in this same context. Spring will inject `AuditSink` into the **factory method parameter** when calling `auditAspect(...)`. The returned object becomes a Spring bean with the default name `auditAspect`; Spring reads `@Aspect` on the object's class to discover advisors.

Note: the `@Bean` method must be processed by Spring in the context, for example residing in a registered `@Configuration`. Calling `new AuditAspect(sink)` **inside a `@Bean` factory method** is valid because the **return value is registered by the container**. Conversely, running `new AuditAspect(sink)` outside the container without registering a bean will not cause Spring AOP to automatically recognize that aspect.

### Dependencies of `@Bean` Must Also Be Spring Beans

Two valid choices:

- Component scan creates `AuditSink` and `OrderService`, while `@Bean` only creates `AuditAspect`.
- Do not use component scan; declare sink, service, and aspect with separate `@Bean` methods.

Example of the second approach, inside a `@Configuration`:

```java
@Bean
AuditSink auditSink() {
    return new AuditSink();
}

@Bean
OrderService orderService() {
    return new OrderService();
}

@Bean
AuditAspect auditAspect(AuditSink sink) {
    return new AuditAspect(sink);
}
```

When Spring creates `AuditAspect`, it takes the `AuditSink` bean to pass into the parameter. With full `@Configuration`, factory methods can be managed by the container for scope and dependencies like other bean definitions; prefer method-parameter injection for transparent dependencies.

### Scope, Bean Name, Lifecycle

Both `@Component` and `@Bean` create **singletons per bean definition** by default in Spring. The default bean name is usually the class name with a lowercase first letter for components (`auditAspect`), and the method name for `@Bean` (`auditAspect`). You can specify a name explicitly:

```java
@Component("businessAuditAspect")
@Aspect
class AuditAspect {
    // ...
}
```

or:

```java
@Bean("businessAuditAspect")
AuditAspect auditAspect(AuditSink sink) {
    return new AuditAspect(sink);
}
```

These two examples are **independent alternatives**; do not apply both simultaneously to create two beans with the same name. The bean name affects lookup and certain bean-name pointcut selections, but does not make `@Aspect` take effect if it has not been created by the container. If an aspect holds mutable state, a singleton can cause race conditions in multithreaded applications; in most cases, an aspect should be **stateless** and delegate storage/auditing to a separate service. Do not switch the scope to prototype arbitrarily: Spring AOP has specific handling for aspect instantiation, and behavior must be verified carefully.

## 5. Full Runnable Demo: Registering via `@Component` Then Switching to `@Bean`

The example uses **Spring Framework 6.2.15**, **AspectJ Weaver 1.9.24**, Gradle, and **Java 17+**. Spring Boot is not used so the roles of `@EnableAspectJAutoProxy`, `@ComponentScan`, and `@Bean` are clearly visible.

Test objective: with exactly **one** aspect bean, one target method is intercepted and another method is not intercepted. Both registration approaches yield **the same result** when the other beans and pointcut remain unchanged.

### 5.1. Directory Tree

```text
aspect-registration-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/aspectdemo/
    ├── Application.java
    ├── AppConfig.java
    ├── OrderService.java
    ├── AuditSink.java
    └── AuditAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'aspect-registration-demo'
```

**`build.gradle`**

```gradle
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
    implementation 'org.springframework:spring-context:6.2.15'
    implementation 'org.springframework:spring-aop:6.2.15'
    implementation 'org.aspectj:aspectjweaver:1.9.24'
}

application {
    mainClass = 'com.example.aspectdemo.Application'
}
```

Spring Framework 6.x requires Java 17 or higher. The dependencies are pinned so the example is standalone and easily reproducible; real-world Spring Boot projects should rely on Boot's dependency management/BOM to choose compatible versions.

### 5.2. Target Service

**`OrderService.java`**

```java
package com.example.aspectdemo;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String place(String orderId) {
        return "placed:" + orderId;
    }

    public String status() {
        return "status:ok";
    }
}
```

The service is a Spring bean created by component scan. The `place` method matches the pointcut; the `status` method does not match. Both methods are public to easily demonstrate interception via a class proxy.

### 5.3. Aspect Dependency

**`AuditSink.java`**

```java
package com.example.aspectdemo;

import org.springframework.stereotype.Component;

@Component
public class AuditSink {
    public void record(String operation) {
        System.out.println("audit:" + operation);
    }
}
```

Separating the sink from the aspect shows that a Spring-managed aspect also has dependencies like a normal bean.

### 5.4. Aspect Registered via `@Component`

**`AuditAspect.java`**

```java
package com.example.aspectdemo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    private final AuditSink sink;

    public AuditAspect(AuditSink sink) {
        this.sink = sink;
    }

    @Before("execution(public * com.example.aspectdemo.OrderService.place(..))")
    public void beforePlace() {
        sink.record("place");
    }
}
```

Spring scans this class thanks to `@Component`. Spring AOP parses its advice thanks to `@Aspect`. There is no need to create `AuditAspect` with another factory method.

**`AppConfig.java`**

```java
package com.example.aspectdemo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = OrderService.class)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
}
```

`basePackageClasses = OrderService.class` tells Spring to scan **the package containing `OrderService`**, which is also the package of `AuditSink` and `AuditAspect` in the demo. `@EnableAspectJAutoProxy` enables processing aspect beans into Spring AOP advisors; `proxyTargetClass=true` allows looking up `OrderService` by its concrete class type. In this simple demo, choosing a subclass proxy keeps results predictable.

### 5.5. Bootstrap, Verifying Aspect Count and Proxy Effect

**`Application.java`**

```java
package com.example.aspectdemo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Application {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);

            System.out.println(
                "aspectBeans=" + context.getBeansOfType(AuditAspect.class).size()
            );
            System.out.println(
                "serviceProxied=" + AopUtils.isAopProxy(service)
            );
            System.out.println(service.place("INV-1"));
            System.out.println(service.status());
        }
    }
}
```

Run in the project directory once Gradle and JDK 17+ are available:

```bash
gradle run --quiet
```

If using the Gradle Wrapper, use `./gradlew run --quiet` (Linux/macOS) or `gradlew.bat run --quiet` (Windows). The lines printed by the application **in exact order** are:

```text
aspectBeans=1
serviceProxied=true
audit:place
placed:INV-1
status:ok
```

Explanation:

- `aspectBeans=1`: the context detects **one** `AuditAspect` bean from component scan.
- `serviceProxied=true`: the target `OrderService` matches the aspect's advisor so Spring returns it as an AOP proxy.
- `audit:place` appears **before** `placed:INV-1` because the `@Before` advice runs when calling `place` through the proxy.
- `status:ok` has no extra `audit` line because the pointcut only matches `place(..)`.
- The demo's `System.out` does not include framework logs or Gradle output generated separately by the environment.

**Key takeaway proven:** The aspect runs because it **is registered as a Spring bean**, the AOP infrastructure is enabled, and the caller invokes a matching target method **through the Spring proxy**.

### 5.6. Switching the Same Demo to the `@Bean` Approach

Keep `Application.java`, `OrderService.java`, `AuditSink.java`, `build.gradle`, and `settings.gradle` unchanged. Replace the **entire contents** of the following two files; this is an **alternative variant**, not to be run simultaneously with the `@Component` variant.

**`AuditAspect.java` — remove `@Component`, keep `@Aspect`:**

```java
package com.example.aspectdemo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AuditSink sink;

    public AuditAspect(AuditSink sink) {
        this.sink = sink;
    }

    @Before("execution(public * com.example.aspectdemo.OrderService.place(..))")
    public void beforePlace() {
        sink.record("place");
    }
}
```

**`AppConfig.java` — add a `@Bean` factory method:**

```java
package com.example.aspectdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = OrderService.class)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public AuditAspect auditAspect(AuditSink sink) {
        return new AuditAspect(sink);
    }
}
```

`@ComponentScan` still creates `OrderService` and `AuditSink`; it **does not create `AuditAspect` via scan** because the aspect class does not have `@Component`. Instead, `@Bean auditAspect(...)` creates exactly one aspect bean, managed by the container with `AuditSink` injected. The statement `new AuditAspect(sink)` inside the bean factory method is completely valid.

Run again:

```bash
gradle run --quiet
```

**Stdout printed by the program does not change**:

```text
aspectBeans=1
serviceProxied=true
audit:place
placed:INV-1
status:ok
```

Thus, the two approaches differ only in the **aspect bean registration mechanism**. The pointcut, advice, dependency, proxy type, and business calls remain the same, so the observed effect is identical.

## 6. Comparing and Choosing a Registration Approach

| Criterion | `@Aspect` + `@Component` | `@Aspect` + `@Bean` |
| --- | --- | --- |
| Who instantiates the bean? | The Spring container creates it from the class discovered by component scan. | The Spring container uses the return value of the factory method. |
| Does the aspect class need `@Component`? | **Yes**, or a custom stereotype meta-annotated with `@Component`. | **No**; only the aspect class needs to be annotated with `@Aspect`. |
| Condition to find the aspect | Scan must cover the package and not exclude the class. | `@Configuration`/`@Bean` must be loaded by the context. |
| Constructor injection | Spring automatically resolves constructor parameters. | Spring resolves parameters of the factory method; the method can pass dependencies into the constructor. |
| Control over instance creation | Usually relies on constructor and component model. | Explicit in the factory method; easy to choose factories/dependencies based on configuration. |
| Default bean name | Usually the class name with a lowercase initial letter. | Based on the factory method name. |
| Conditions/feature flags | Can use `@Profile`, `@Conditional` on the component when appropriate. | Can place `@Profile`/`@Conditional` on `@Bean` or config, easy to trace when beans are created. |
| Embedding an aspect from another module/library | Requires the package to be scanned or imported. | Suitable when library users explicitly register an `@Aspect` class with `@Bean`. |
| Commonly used when | The aspect is application code and the project has a consistent scanning convention. | Explicit wiring is desired, there are multiple configurations, or avoiding reliance on package scanning is preferred. |

**Choose `@Component`** if the aspect is a normal component of the module, lies within a controlled scan area, and has simple dependency injection.

**Choose `@Bean`** if you want Spring configuration to explicitly state “which aspect is activated”, want to configure constructors per environment, or are integrating an aspect class that should not carry a Spring stereotype.

The two approaches **do not differ in Spring AOP interception capability**: once properly registered, Spring proxies still have limitations such as self-invocation, `private`/`final` methods, proxy interfaces/classes, pointcuts, and when the target is invoked. Do not switch from `@Component` to `@Bean` trying to fix an internal self-invocation issue.

## 7. Cases That Cause Duplicate Registration or Missing Aspects

### 7.1. Adding `@Component` While Also Writing `@Bean`

Example of **what not to do** in the same context that scans the package:

```java
@Aspect
@Component
class AuditAspect {
    // advice...
}

@Configuration
@ComponentScan("com.example.aspectdemo")
class AppConfig {
    @Bean
    AuditAspect customAuditAspect() {
        return new AuditAspect();
    }
}
```

This is **illustrative code showing incorrect registration**, not a runnable project from the demo because the class has a different constructor. If the factory method creates a bean named `customAuditAspect`, while component scan creates `auditAspect`, the context has **two beans** of the same aspect type. If both have advice matching the target, side effects may run twice. If the same name is chosen, the result depends on bean-definition overriding/collision policy and may cause startup failure. Do not rely on matching names to eliminate one bean. Choose exactly one registration source and check the instance count.

### 7.2. Only Adding `@Aspect`

```java
@Aspect
public class AuditAspect {
    // advice...
}
```

This class does not appear automatically when default component scan runs. You must add the `@Component` stereotype **or** declare `@Bean`. This can cause a situation where the application starts up normally but no advice runs.

### 7.3. Aspect Lies Outside the Scan Scope

`@ComponentScan("com.example.web")` does not automatically scan `com.example.audit`. Consider:

- Adjusting the scanned packages to include the aspect without blindly scanning unintended areas.
- Registering the aspect via `@Import` of configuration or `@Bean`.
- In Spring Boot, checking the root package of `@SpringBootApplication` and the default scan scope before fixing.

### 7.4. `@Bean` Placed in an Unimported Config

Writing a factory method on a configuration class without bringing that class into the ApplicationContext also does not create an aspect bean. Check where `@SpringBootApplication`, `@Import`, or configuration classes registered via `AnnotationConfigApplicationContext` are declared.

### 7.5. Calling a Method via `this` or an Object Outside the Container

Even when `AuditAspect` is properly registered:

```java
@Service
class OrderService {
    public String batch() {
        return place("INV-2");  // self-invocation: bypasses the proxy of place()
    }

    public String place(String id) {
        return "placed:" + id;
    }
}
```

This is an **illustrative snippet**, not replacing the earlier demo files. The pointcut on `place(..)` will not run for the call from `batch()` on the target. Similarly, `new OrderService().place("INV-2")` is not automatically intercepted. If advice is needed, call through a Spring bean/proxy (usually via another bean); do not add another aspect bean hoping to fix self-invocation.

### 7.6. Multiple Contexts

`@ComponentScan` and `@Bean` register beans in the ApplicationContext where they run. The auto-proxy creator of `@EnableAspectJAutoProxy` also has a local context scope. For applications with root/child contexts, verify that the aspect, target bean, and AOP infrastructure are in the appropriate matching context. An aspect created in one context does not automatically apply to all target beans in another context.

### 7.7. Too Much State in a Singleton Aspect

Aspect beans are singletons by default like normal Spring beans. Do not store `currentUser`, `currentOrderId`, or mutable request data directly in fields of a singleton aspect, because multiple requests may invoke the advice concurrently. If request context is needed, use the appropriate request/security/observation API; if audit logging is needed, delegate to a thread-safe service/sink.

## 8. Spring Boot and Automatic Aspect Registration

In Spring Boot with AOP auto-configuration and corresponding dependencies, you usually do not need to write `@EnableAspectJAutoProxy` manually; however, you **still must create the aspect bean** via `@Component` (scanned) or `@Bean` (in a loaded config).

Boot example:

```java
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

If `AuditAspect` has both `@Aspect` and `@Component` and lies within the component scan scope, Boot AOP can detect it when the appropriate dependencies/infrastructure are present. With the `@Bean` approach, a `@Configuration` loaded by Boot returns `AuditAspect` and the infrastructure handles it similarly.

**Dependencies by major version:**

```gradle
// Spring Boot 3.x, with Boot dependency management
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

```gradle
// Spring Boot 4.x, with Boot dependency management
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

These two blocks are **version-specific choices**, not used simultaneously. The dependency name does not replace the requirement to **register an aspect bean**. Spring Boot may use class proxies by default; check `spring.aop.auto` and `spring.aop.proxy-target-class` when diagnosing, and remember that other proxy configurations can affect the outcome. The aspect is still a Spring bean, not bytecode weaving simply because the module includes `aspectjweaver`.

## 9. How to QA: Distinguishing “Bean Exists” from “Advice Executes”

When verifying, check in the following order:

### Step 1 — Is the aspect registered exactly once?

```java
String[] aspectBeanNames = context.getBeanNamesForType(AuditAspect.class);
System.out.println(java.util.Arrays.toString(aspectBeanNames));
```

In the demo, the default name for both registration approaches is `auditAspect`, so the illustrative output line is:

```text
[auditAspect]
```

If there is no name: forgot `@Component`, scanned the wrong package, or the `@Bean` config was not loaded. If there are two names: risk of duplicate registration.

### Step 2 — Is the target proxied by Spring?

```java
OrderService service = context.getBean(OrderService.class);
System.out.println(AopUtils.isAopProxy(service));
```

In the demo, the result is:

```text
true
```

If false, review the AOP configuration, AspectJ Weaver classpath, pointcut, and whether the target was retrieved through the container. Proxy true only says **at least one** advisor applies to the bean; it does not yet prove a specific method will run advice.

### Step 3 — Does the method matching the pointcut have side effects?

Call `service.place("INV-1")` via the reference obtained from the Spring container; confirm `audit:place` prints exactly once before the result, and `status()` does not trigger auditing. If both approaches are used simultaneously, the advice execution count may differ; that is a registration error, not a Java method issue.

### Step 4 — Verify wiring like an integration test

Write a test that creates a real context and asserts:

- There is exactly one `AuditAspect` bean.
- `OrderService` is an AOP proxy.
- Calling the method matched by the pointcut produces exactly one audit event.
- Methods outside the pointcut do not record an audit.
- When switching from component scan to `@Bean`, the assertions remain the same.
- If there are exceptions/transactions, verify when the advice runs and that errors are not swallowed.

Tests that only use `new AuditAspect(...)` or `new OrderService()` do not replace a Spring proxy integration test. To keep tests clean, `AuditSink` should have a mock/test implementation instead of printing to the console.

## 10. Quick Diagnostic Questions

| Symptom | Likely Spring cause | How to verify |
| --- | --- | --- |
| No `AuditAspect` bean | Only `@Aspect` used, missing `@Component` or `@Bean` config not loaded. | `getBeanNamesForType(AuditAspect.class)`; check scan/import. |
| Aspect bean exists, advice does not run | Missing AOP enable/auto-config, missing AspectJ Weaver, pointcut mismatch, self-invocation, or target is not a bean. | `AopUtils.isAopProxy`, call externally through proxy and observe advice. |
| Advice runs twice | Duplicate aspect bean registration or another advisor also applies. | List bean names and advisor chain. |
| Spring throws `NoUniqueBeanDefinitionException` when injecting `AuditAspect` | Multiple beans of the same type, usually from scan plus `@Bean`. | Check `getBeanNamesForType` and remove the redundant registration source; `@Qualifier` only resolves bean selection when multiple instances are genuinely needed. |
| Has `@Bean` but missing `AuditSink` | Factory method has a dependency not yet created in the context. | Check `@ComponentScan`/`@Bean` creating sink, startup errors. |
| Switched to `@Bean` but bean name/ordering changed | Method name or `@Bean("...")` changed; multiple aspects and `@Order`. | Check bean name, advisor order, and pointcut. |
| Injecting target by concrete type fails | JDK interface proxy cannot be assigned to implementation type. | Inject by interface or configure class-based proxy appropriately. |
| Advice does not run from internal call | Call goes through `this` on the target. | Try calling the method via injected Spring bean from another class. |

## 11. Pre-Completion Checklist

- [ ] Aspect class has `@Aspect`, choosing **one** registration source: `@Component` **or** `@Bean`.
- [ ] If choosing `@Component`: right package scan, not excluded by filters.
- [ ] If choosing `@Bean`: config is in the context; constructor/factory method injects dependencies from Spring.
- [ ] Exactly the intended number of aspect instances exists (usually one), avoiding duplicate advice side effects.
- [ ] Spring AOP `@AspectJ` support is enabled: `@EnableAspectJAutoProxy` for plain Framework or appropriate Boot AOP auto-configuration.
- [ ] AspectJ Weaver is on the classpath and compatible with the Spring version.
- [ ] Target bean is retrieved from the container, pointcut matches the method, external calls go through the proxy.
- [ ] Proxy type, method interceptability, bean scope, and advisor order meet requirements.
- [ ] Aspect does not hold unsafe mutable request state; dependencies/sinks are used via DI.
- [ ] Integration test confirms bean count **and** that advice runs exactly once, not just checking that the class has the annotation.

**Point to remember:** In Spring AOP, `@Aspect` defines **what the aspect is**, while `@Component` or `@Bean` determines **how Spring manages the aspect instance**. Only after it is a Spring bean does Spring's `@AspectJ` infrastructure use that advice to create proxies for matching target beans. The two registration approaches are two wiring choices and do not change the nature of interception via Spring proxies.

## Official Documentation

- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html)
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring Framework — Component Scanning](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
