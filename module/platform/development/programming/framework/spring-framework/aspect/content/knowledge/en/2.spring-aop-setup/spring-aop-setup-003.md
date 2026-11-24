# Enabling @AspectJ Support with @EnableAspectJAutoProxy in Spring

## 1. Purpose of the configuration

When using **Spring Framework** with Java configuration, the `@EnableAspectJAutoProxy` annotation instructs Spring to detect **Spring beans** annotated with `@Aspect`, turn pointcut/advice declarations into Spring AOP advisors, and **automatically create proxies** for beans whose methods have applicable advisors.

This is the step that sets up **Spring AOP infrastructure using @AspectJ syntax**. The word "AspectJ" in the annotation name refers to the **aspect declaration style**, not that the application automatically uses AspectJ compile-time weaving or load-time weaving. When enabled this way, the regular interception mechanism remains **Spring proxies on method calls to Spring-managed beans**.

Minimal example:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy
public class AopConfig {
}
```

This is a **configuration snippet**, which only takes effect when `AopConfig` is registered in an appropriate `ApplicationContext`; this annotation alone does not trigger advice calls without an `@Aspect` bean and a matching target bean/pointcut.

**When do you need to learn manual enablement?** Mainly in self-configured Spring Framework applications, modules using `AnnotationConfigApplicationContext`, child contexts with independent configuration, or when you need a clear understanding of proxy types. In **Spring Boot projects with AOP auto-configuration enabled**, you normally do not need to repeat this annotation; see section 7.

## 2. Prerequisites for the configuration to actually work

For `@EnableAspectJAutoProxy` to take effect, all of the following must be present simultaneously:

1. **A Spring context processing the configuration annotation:** the class carrying `@Configuration` and `@EnableAspectJAutoProxy` is registered, such as `new AnnotationConfigApplicationContext(AopConfig.class)`. Placing the annotation on an arbitrary class not loaded by Spring will not change the container.
2. **Spring AOP infrastructure and the AspectJ pointcut library:** compatible `spring-aop` and `org.aspectj:aspectjweaver` must be on the classpath. `aspectjweaver` is used by Spring for `@AspectJ` pointcut expressions; you do not need to start the JVM with `-javaagent` to run proxy examples.
3. **An aspect declared as a Spring bean:** `@Aspect` describes the class as an aspect, and **does not automatically get the class registered by component scan**. Use `@Aspect` + `@Component` (when an appropriate `@ComponentScan` is active) or a `@Bean` method returning the aspect instance.
4. **A target Spring bean:** the business class is managed by the container, not an object created with `new` outside the container.
5. **The pointcut matches the method and the call goes through the proxy:** advice only executes if the bean/method matches and the caller actually invokes the proxy returned by Spring.

Example of two ways to register an **aspect** — choose **one** approach for a single instance:

```java
// Approach A: component scan finds a class with both @Aspect and @Component
@Aspect
@Component
public class LoggingAspect {
    // advice
}
```

```java
// Approach B: explicit registration, allowing no @Component annotation
@Configuration
@EnableAspectJAutoProxy
class AopConfig {
    @Bean
    LoggingAspect loggingAspect() {
        return new LoggingAspect();
    }
}
```

The snippets above illustrate registration styles and are not standalone programs. If `LoggingAspect` is already registered via component scan, do not accidentally add a duplicate `@Bean`. **Do not use `@Aspect` alone as a substitute for `@Component`** in a component-scan setup.

## 3. What does `@EnableAspectJAutoProxy` do in the Spring container?

When `ApplicationContext` reads the `@Configuration` class, `@EnableAspectJAutoProxy` imports `AspectJAutoProxyRegistrar` to register the appropriate auto-proxy mechanism (typically `AnnotationAwareAspectJAutoProxyCreator`). Spring uses bean post-processing infrastructure to inspect beans and advisors derived from Spring `@Aspect` beans.

Overview:

```text
@Configuration + @EnableAspectJAutoProxy
             |
             v
Spring registers @AspectJ auto-proxy infrastructure
             |
     Registers @Aspect beans
             |
             v
Creates / initializes Spring target beans
             |
             v
Evaluates advisors + pointcuts against target bean
             |
     +-------+-----------------+
     |                         |
Matching advice           No matching advice
     |                         |
     v                         v
Returns bean as proxy     Ordinary bean
     |
Caller invokes method via proxy
     |
Advice -> target method -> advice/result
```

Technical distinctions to keep clear:

- The annotation **enables infrastructure**; it **does not turn every bean into a proxy** and does not attach advice to every method. Matching still depends on pointcuts and targets.
- The aspect must be a **Spring-managed bean**; a class with only `@Aspect` outside the context will not be used by the auto-proxy infrastructure.
- Proxy creation happens during container lifecycle, so avoid assuming methods called from a constructor or bean initialization logic are guaranteed to be intercepted. Focus on calls through an initialized bean reference injected or looked up from the context.
- When a target is proxied, **internal calls like `this.otherMethod()` do not go back through the proxy**, so advice attached to `otherMethod()` may not run for that call path.
- `@EnableAspectJAutoProxy` itself **does not enable** `@Transactional`, `@Async`, method security, or cache annotations; those capabilities have their own activation mechanisms. They can coexist and share Spring's proxying foundation.

### Differences from AspectJ weaving

| Question | Enabling Spring `@AspectJ` with `@EnableAspectJAutoProxy` |
| --- | --- |
| Interception mechanism | Spring AOP creates a JDK proxy or subclass proxy |
| Applicable targets | Spring-managed beans, with method calls going through the proxy |
| Intercept constructor/field access? | No, outside the capabilities of proxy-based Spring AOP |
| Intercept internal `this.method()`? | No; the call does not pass through the proxy |
| Need AspectJ compiler/agent? | No; requires the declaration/pointcut support library (`aspectjweaver`) on the classpath |
| Automatically enable `@Aspect` outside container? | No; must still be registered as a bean |

If the goal requires bytecode weaving, this lesson's configuration is not enough. That is a different technical choice requiring separate setup.

## 4. Two important parameters of the annotation

`@EnableAspectJAutoProxy` has two boolean attributes:

```java
@Configuration
@EnableAspectJAutoProxy(
    proxyTargetClass = true,
    exposeProxy = false
)
public class AopConfig {
}
```

### `proxyTargetClass`

The default on `@EnableAspectJAutoProxy` itself is `false`. This prefers interface-based proxies when a suitable interface exists; if the target has no interface to proxy, Spring may still have to use a subclass proxy.

| Value | How to interpret | Practical impact |
| --- | --- | --- |
| `proxyTargetClass = false` (annotation default) | Prefer JDK dynamic proxy when a suitable interface exists | Callers normally use the interface type implemented by the proxy; methods outside the interface are not exposed through a JDK proxy. |
| `proxyTargetClass = true` | Request class-based proxy (Spring uses CGLIB) | Can inject/call by class type, though still subject to `final` class/method, `private` method, and subclassing limitations. |

Example:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class ClassProxyConfig {
}
```

This **does not** fix self-invocation. Do not overuse class-based proxies hoping to intercept `private` or `final` methods: a subclass cannot override those methods. Certain JVM/module path restrictions may also affect subclass proxy creation.

**Interaction with other configurations:** within the same context, multiple parts of Spring that configure auto-proxying (such as `@EnableTransactionManagement`) can merge into one auto-proxy creator and adopt the stronger proxy setting. In Spring Boot, the default proxy-target-class setting may differ from the annotation's default. Therefore, determine the proxy type from **actual configuration or runtime inspection**, not from a single annotation alone.

### `exposeProxy`

Default is `false`: Spring does not expose the current proxy via `AopContext.currentProxy()` for business code to access. If set to:

```java
@Configuration
@EnableAspectJAutoProxy(exposeProxy = true)
class ExposedProxyConfig {
}
```

Spring can provide the current proxy within the **context of a call passing through the proxy** using a Spring AOP `ThreadLocal`. This is an advanced setting used when you understand the dependency on proxy context; it is **not a requirement for regular advice to work**.

Example of a self-calling method needing interception:

```java
// Illustrates accessing an exposed proxy; not a standalone Java file
((MyService) AopContext.currentProxy()).otherMethod();
```

The snippet above also requires importing `org.springframework.aop.framework.AopContext`, `MyService` being accessible through the proxy, `exposeProxy=true`, and executing inside a proxied call. Outside that context, `currentProxy()` can throw `IllegalStateException`. A usually more maintainable design is to **extract the intercepted method into another Spring bean and inject it**, creating an explicit proxy boundary. This `ThreadLocal` also does not propagate automatically across threads/async tasks.

## 5. Plain Spring Framework demo: enabling @AspectJ with the annotation

The following example runs on **Java 17+**, Spring Framework **6.2.19**, Gradle, and AspectJ Weaver **1.9.25.1**. It proves three things: enabling infrastructure via `@EnableAspectJAutoProxy`, Spring creating a proxy for a matching target, and self-invocation bypassing the proxy.

### 5.1. File structure

```text
aspectj-enable-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/lesson/
    ├── Main.java
    ├── AppConfig.java
    ├── BillingService.java
    └── AuditAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'aspectj-enable-demo'
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
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.lesson.Main'
}
```

This is a standalone Spring Framework application, **without Spring Boot**. A Spring Boot project should let Boot's BOM/dependency management handle versions instead of copying these pinned versions into another project.

### 5.2. Create the Spring configuration

**`AppConfig.java`**

```java
package com.example.lesson;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = Main.class)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
}
```

`@ComponentScan` locates `BillingService` and `AuditAspect` in the same package. `proxyTargetClass=true` makes class proxying explicit in the example because `BillingService` defines no interface. The parameter can be omitted in this case and Spring can still choose a class proxy.

### 5.3. Create the target service

**`BillingService.java`**

```java
package com.example.lesson;

import org.springframework.stereotype.Service;

@Service
public class BillingService {
    public String charge(String orderId) {
        return "charged:" + orderId;
    }

    public String internalCharge(String orderId) {
        // Call on the target itself, not through the Spring proxy of charge().
        return charge(orderId);
    }
}
```

### 5.4. Create the Spring-managed aspect

**`AuditAspect.java`**

```java
package com.example.lesson;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("execution(* com.example.lesson.BillingService.charge(..))")
    public void beforeCharge(JoinPoint joinPoint) {
        System.out.println("intercepted:" + joinPoint.getSignature().getName());
    }
}
```

`@Aspect` marks the class as providing advice; `@Component` brings it into component scan. The pointcut targets **only the `BillingService.charge(..)` method**. `@Before` prints a line when a call passes through the proxy to that method.

### 5.5. Bootstrapping and calling the service via the context

**`Main.java`**

```java
package com.example.lesson;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            BillingService service = context.getBean(BillingService.class);

            System.out.println("isProxy=" + AopUtils.isAopProxy(service));
            System.out.println(service.charge("A-1"));
            System.out.println(service.internalCharge("B-2"));
        }
    }
}
```

From the project directory, run with an installed Gradle:

```bash
gradle run --quiet
```

If the project has the Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

**Three print calls and one advice produce these exact four lines** (excluding log warnings from the JVM, Gradle, or environment):

```text
isProxy=true
intercepted:charge
charged:A-1
charged:B-2
```

Line-by-line explanation:

1. `isProxy=true`: the context returned a Spring AOP proxy of `BillingService`, because this bean has a method matching an advisor.
2. `intercepted:charge`: `service.charge("A-1")` calls from `Main` into the Spring bean **through the proxy**, so `@Before` runs.
3. `charged:A-1`: the original call still executes and returns the string from the target.
4. `charged:B-2`: `service.internalCharge("B-2")` enters via the proxy at the entry method, but inside it calls `this.charge(..)` directly on the target, so **there is no second `intercepted:charge` line**.

**Valid control experiment:** try removing `@EnableAspectJAutoProxy` from `AppConfig` in this plain Spring Framework project when no other AOP configuration is present; the aspect can still be a bean, but it is not processed into advice by an auto-proxy creator. The expected application output is now:

```text
isProxy=false
charged:A-1
charged:B-2
```

That clearly separates **registering an aspect bean** from **enabling auto-proxy infrastructure**. If another part of the same context already enabled AOP, this control is no longer isolated and a proxy may still appear.

## 6. How to verify configuration when advice does not run

Each check below aims to pinpoint a specific cause, rather than adding annotations at random.

| Symptom | What to check | Resolution |
| --- | --- | --- |
| No advice line, `isAopProxy(bean) == false` | Is the `@Configuration` class with `@EnableAspectJAutoProxy` loaded in the current context? | Bring the right config in via `@Import`, `@ComponentScan`, or `AnnotationConfigApplicationContext`. |
| Class has `@Aspect` but no advice runs | Is the aspect a bean? Does it have `@Component` and get scanned in the right package, or `@Bean`? | Register the aspect bean explicitly. |
| Startup fails with missing AspectJ class | Is a compatible `org.aspectj:aspectjweaver` present? | Add the dependency to the classpath in the proper module/runtime. |
| `isAopProxy(bean)==false` even though infrastructure is enabled | Does the pointcut match the method/class? Is the target a Spring bean? | Fix the expression/annotation and test a proxyable method. |
| Advice runs for calls from other beans but not on `this.method()` | Self-invocation bypasses the proxy. | Extract the logic into another Spring bean or change the call boundary. |
| Proxy exists, but casting to the concrete class fails | Is an interface-based JDK proxy being used? | Inject by interface or consider class-based proxying if appropriate. |
| Proxy does not intercept the method as expected | Is the method `private`/`final`, class `final`, or non-public with a JDK proxy? | Choose an interceptable public service contract; do not rely on subclassing to override `final`/`private`. |
| Advice runs, yet log lines appear multiple times | Are there duplicate aspect/advisor beans, multiple matching rules, or multiple contexts? | Check bean registration, advisor chain, and avoid registering duplicate aspects. |
| Running in Spring Boot and removing `@EnableAspectJAutoProxy` still runs advice | Boot is auto-enabling AOP when the classpath qualifies. | This is expected behavior; see the Boot configuration section below. |

To inspect the proxy while debugging:

```java
// Illustrative snippet inside code with access to a Spring bean
boolean anyProxy = AopUtils.isAopProxy(service);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(service);
boolean cglibProxy = AopUtils.isCglibProxy(service);
```

Import `org.springframework.aop.support.AopUtils`. The result of `isAopProxy` only tells **whether the bean is a proxy**, not that every method matches a pointcut. Verify advice via an observable behavior or an integration test running against a real context.

### Sample test with a real context

A proper test should initialize `AnnotationConfigApplicationContext` or `@SpringJUnitConfig` to obtain the bean from the Spring container, then assert both **proxy presence** and **advice side effect**. A test that creates `new BillingService()` only tests target code, **not interception**. When an aspect prints to the console, the demo uses stdout for readability; in real tests, replace `System.out` with a recorder/mock/test sink so you can assert how many times the advice ran.

## 7. Spring Boot: why is `@EnableAspectJAutoProxy` usually unnecessary?

When a **Spring Boot** application has the appropriate AspectJ/Spring AOP dependencies and has not disabled AOP auto-configuration, Boot automatically configures AOP equivalently to enabling `@EnableAspectJAutoProxy`. Thus, a typical Boot application can use `@Aspect` + `@Component` right away without placing `@EnableAspectJAutoProxy` on the main class.

Dependency examples **chosen by Boot major version**:

```gradle
// In Spring Boot 3.x, with Boot plugin/BOM configured
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

```gradle
// In Spring Boot 4.x, with Boot plugin/BOM configured
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

Pick **exactly one configuration matching your project version**; the two blocks above are **alternatives**, do not put both in the same `build.gradle`. With Boot, dependency management handles compatible versions. Do not read the name `starter-aspectj` in Boot 4.x as proof that AspectJ bytecode weaving is automatically enabled: `@AspectJ` in Spring AOP still normally runs via proxies.

Related Boot configuration:

```properties
# Usually auto-configures AOP by default when conditions are met
spring.aop.auto=true

# Boot usually uses subclass-based proxies by default
spring.aop.proxy-target-class=true
```

Change to:

```properties
spring.aop.proxy-target-class=false
```

to have Boot prefer JDK interface proxies when applicable. The `spring.aop.auto=false` property disables **Boot's AOP auto-configuration part**, not a command that removes every auto-proxy creator registered by other Spring configurations. If the application manually adds `@EnableAspectJAutoProxy`, Boot is no longer the sole place deciding whether AOP is enabled. When you want manual control over AOP in Boot, inspect the **combined** effective configuration rather than treating the two mechanisms as independent on/off switches.

**Comparison table:**

| Environment | How to enable `@AspectJ` support | Points to remember |
| --- | --- | --- |
| Standalone Spring Framework Java config | Add `@EnableAspectJAutoProxy` to a loaded `@Configuration` | Must have `aspectjweaver`, Spring AOP, aspect bean, and target bean. |
| Spring Boot with AOP auto-configuration | Usually **no** manual declaration needed | Use the starter for your major version and `spring.aop.*` if needed. |
| Traditional Spring XML configuration | `<aop:aspectj-autoproxy/>` | Same goal of enabling Spring AOP `@AspectJ` in XML style. |
| Multiple separate ApplicationContexts | Place the enable config in the context where the advised beans live | The annotation is scoped to the local context and does not automatically propagate to other contexts. |

### Multiple ApplicationContexts scope

Spring can have a **root context** and independent **child contexts** (for instance, legacy web context hierarchies). The Javadoc of `@EnableAspectJAutoProxy` specifies that the annotation applies within the **local application context**. If proxies are needed across multiple contexts, you must configure enablement in each corresponding context and ensure aspect/target beans exist in the right places. Do not assume enabling it in one context makes advisors process beans in another context.

## 8. Common setup mistakes

1. **Confusing `@Aspect` with a Spring stereotype.** `@Aspect` does not replace `@Component`/`@Bean`; an aspect absent from the context is not used.
2. **Enabling the annotation while missing `aspectjweaver`.** `@EnableAspectJAutoProxy` requires this library to support pointcut declarations.
3. **Adding the annotation to a class not scanned/loaded by Spring.** Only an annotation in a context's active configuration enables the infrastructure.
4. **Assuming every bean becomes a proxy.** A bean with no applicable advisor can remain a plain object.
5. **Using `proxyTargetClass=true` expecting to intercept `this.method()`.** Self-invocation still bypasses the proxy regardless of JDK or subclass proxying.
6. **Setting `exposeProxy=true` to "fix" every call.** The attribute only exposes the current proxy within supported contexts; it does not make code outside the container intercepted automatically.
7. **Treating `@EnableAspectJAutoProxy` as enabling transactions/caching/async.** Those capabilities have separate activation configurations and can interact with auto-proxying, requiring case-by-case inspection.
8. **Treating `@EnableAspectJAutoProxy` as AspectJ weaving.** It enables Spring's proxy-based `@AspectJ` mechanism; it does not intercept constructors/fields or arbitrary objects.
9. **Repeating the annotation in Boot without checking auto-config.** Usually unnecessary and easily causes confusion when adjusting proxy settings.
10. **Forgetting advisor order when combining multiple Spring interceptions.** `@Order` on aspects and the order of other advisors can change when advice runs relative to transactions/security; check actual order before inferring "success" or rollback conditions.

## 9. Completion checklist

- [ ] The `@Configuration` class carrying `@EnableAspectJAutoProxy` is loaded into the right Spring `ApplicationContext`.
- [ ] Compatible Spring AOP and AspectJ Weaver are in dependencies; no accidental mixing of Spring Framework/Boot versions.
- [ ] The `@Aspect` class is already a Spring bean via `@Component` + scan or `@Bean`.
- [ ] The target method belongs to a Spring bean; the pointcut matches the exact intended scope.
- [ ] Callers receive the bean via DI/context and invoke **through the proxy**; `this.method()` and `new`-instantiated objects have been checked.
- [ ] `proxyTargetClass` fits the bean/API types, `final`, `private`, interfaces, and injection style.
- [ ] `exposeProxy` is only enabled when there is an actual need and `ThreadLocal` semantics are understood.
- [ ] In Boot, AOP auto-configuration and `spring.aop.auto`/`spring.aop.proxy-target-class` have been checked before adding manual enablement.
- [ ] If multiple contexts exist, enablement is placed in the right one.
- [ ] An integration test has been run confirming both the proxy **and** the advice side effect; normal calls, self-invocation, and non-matching pointcuts have been checked.

**Key takeaway:** `@EnableAspectJAutoProxy` handles the step of **allowing Spring to process `@Aspect` beans and create proxies for matching targets** within a context. It does not register all aspects automatically, turn all beans into proxies, overcome self-invocation limits, or need repeating when Spring Boot already auto-configures it properly.

## Spring reference documentation

- [Spring Framework — EnableAspectJAutoProxy Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableAspectJAutoProxy.html)
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Boot — AOP Auto-configuration](https://docs.spring.io/spring-boot/reference/features/aop.html)
