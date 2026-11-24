# Limitations of final Classes and final Methods When Using CGLIB in Spring AOP

## 1. The Problem to Recognize

In Spring AOP, a target bean can be wrapped by Spring in a **JDK dynamic proxy** via an interface, or a **class-based proxy** using CGLIB. When Spring configuration uses class-based proxies, Spring must generate a **subclass** of the target class to intercept overridable methods.

Two critical limitations arise directly from how Spring uses CGLIB:

- **`final class`:** cannot be subclassed, so **a CGLIB AOP proxy cannot be created** for that class. When a bean genuinely needs an advisor applied and Spring mandates a class proxy, proxy creation / context initialization can fail.
- **`final method` in a non-final class:** Spring can still create a CGLIB proxy for the class, **but cannot intercept/advise the `final` method itself** because the subclass cannot override it. Other non-final methods can still be advised.

This lesson focuses on **Spring AOP behavior**, error conditions, configuration, and proxy verification. Basic Java `final` concepts are mentioned only to the extent needed to understand Spring proxy constraints.

Key point to remember immediately: **“The bean is proxied” is different from “every method on the bean is advised.”** Checking only `AopUtils.isAopProxy(bean) == true` does not prove `finalMethod()` has its advisor running.

## 2. When Does Spring Create a JDK Proxy vs. a CGLIB Proxy?

| Condition in Spring | Selectable proxy type | Consequence with `final` |
| --- | --- | --- |
| Target implements a business interface, `proxyTargetClass=false`, config does not force class proxies | Usually **JDK dynamic proxy**, proxy object implements the interface | Target class can be `final`; Java target class does not need to be subclassed. A `final` public target method can be advised **via the proxied interface method**, if an advisor matches. |
| Target has no suitable interface | **CGLIB/class-based proxy** is used when a proxy is needed | Class cannot be `final`; `final` methods cannot be advised via subclassing. |
| `@EnableAspectJAutoProxy(proxyTargetClass=true)` or config forcing class proxies | **CGLIB** even if target has interfaces | `final class` cannot be subclassed; `final method` skips interception. |
| Spring Boot using class proxies by default configuration | Usually class-based, depending on `spring.aop.proxy-target-class` and related configs | A `final` target can hit CGLIB limits even when declaring an interface. |
| Switching to JDK proxy when callers only know the concrete implementation | Callers cannot inject/cast a JDK proxy to the implementation class | Must inject via interface; JDK proxy only exposes methods belonging to the proxied interfaces. |

In **Spring Framework** configuring `@EnableAspectJAutoProxy`, `proxyTargetClass` defaults to `false`; for targets with business interfaces, Spring usually prefers JDK proxies. In **Spring Boot** with AOP auto-configuration, `spring.aop.proxy-target-class` typically defaults to `true`, so check the specific environment.

### Call Path Diagram

```text
CGLIB for a non-final class:

Client
  |
  v
ClassService$$SpringCGLIB$$...
  ├─ open()         -> overridable method -> advice -> target.open()
  └─ final locked() -> not overridable    -> does not go through advice

CGLIB for a final class:

final class FinalService
  |
  └─ Spring cannot create a subclass => class-based proxy is not feasible

JDK interface proxy for a final target class:

Client (holds ServicePort interface)
  |
  v
jdk.proxy...$Proxy
  |
  +-- ServicePort.call() -> advice -> final target implementation.call()
```

The CGLIB diagram is a conceptual model of interception; exact proxy mechanics are managed by Spring. Do not rely on auto-generated proxy class names, as names can change across runtime versions.

## 3. Why Do `final class` and `final method` Cause Two Different Symptoms?

### 3.1. Entire Class `final`: Usually Fails When a CGLIB Proxy Is Required

Suppose in Spring:

```java
public final class FinalInvoiceService {
    public String issue(String id) {
        return "issued:" + id;
    }
}
```

An advisor wants to intercept `issue(..)`, while `@EnableAspectJAutoProxy(proxyTargetClass=true)` forces Spring to create a class proxy. Because the class is `final`, CGLIB cannot create a subclass. When Spring **actually has to apply an AOP proxy** to this bean, the application can throw an error such as `AopConfigException` / `BeanCreationException`, with an underlying cause stating the `final class` cannot be subclassed.

**Do not claim Spring always fails simply because a `final` bean exists.** If a `final` bean is not targeted by any advisor and Spring does not need to create a proxy, the bean can still operate normally. The error arises from an actual class-proxy requirement, not when the compiler reads the `final` keyword.

### 3.2. Non-final Class, One `final` Method: Proxy Exists but Advice Skips That Method

```java
public class InvoiceService {
    public String issue(String id) {
        return "issued:" + id;
    }

    public final String summary(String id) {
        return "summary:" + id;
    }
}
```

A CGLIB proxy can override `issue(..)` to run advisors, yet **cannot override** `summary(..)`. Consequently, a pointcut can match **by name/signature** while calling `summary()` still **does not trigger Spring AOP advice**.

This is a more dangerous bug because **the application can still start up**, many methods get advised as expected, and only the `final` method lacks the advice's side effects.

Be especially cautious when using `@Transactional`, `@Cacheable`, method security, or `@Async` via the proxy mechanism: a `final` method under a class proxy may skip the interceptor that the code author assumed was active. Do not use “the bean is an AOP proxy” to conclude that transactions/security/caching on a `final` method are safe.

### 3.3. Not Only `final`

By the same subclassing principle:

- `private` methods cannot be overridden, so they cannot be advised by CGLIB.
- Methods invisible to the subclass, such as package-private methods on a parent class in another package, may also fail to be intercepted.
- `this.otherMethod()` inside the target is **self-invocation**: it does not route back through the proxy; advice is skipped even if `otherMethod()` is not `final`.
- Constructor invocations or field reads/writes do not become Spring AOP proxy method join points.
- The Java Platform Module System can restrict class proxies for unopened packages; that is a separate constraint and cannot be resolved merely by removing `final`.

The issues above have distinct root causes. Do not automatically enable `proxyTargetClass=true` or `exposeProxy=true` whenever a method lacks advice.

## 4. Running a CGLIB Demo: Advice Runs on Regular Methods, Skips `final` Methods

This is a **plain Spring Framework** project with **Java 17+**, **Spring Framework 6.2.19**, and **AspectJ Weaver 1.9.25.1**. The example uses Java configuration with `@EnableAspectJAutoProxy` so it does not depend on Spring Boot auto-configuration.

### 4.1. Project Structure

```text
spring-final-proxy-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/finalproxy/
    ├── App.java
    ├── ClassProxyConfig.java
    ├── CglibService.java
    └── TraceAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-final-proxy-demo'
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
    mainClass = 'com.example.finalproxy.App'
}
```

In Spring Framework 6.x, CGLIB is already repackaged by Spring inside `spring-core`; you do not need to add a separate CGLIB dependency. `aspectjweaver` is a dependency used by Spring AOP for `@AspectJ` pointcut parsing; **it does not mean the application uses AspectJ load-time weaving**.

### 4.2. Non-final Target Class with One `final` Method

**`CglibService.java`**

```java
package com.example.finalproxy;

public class CglibService {
    public String open(String id) {
        return "open:" + id;
    }

    public final String locked(String id) {
        return "locked:" + id;
    }
}
```

`open(..)` can be overridden by a subclass. `locked(..)` cannot be overridden. To observe the limitation clearly, both methods return simple strings without depending on instance fields.

**An advanced note:** a `final` method invoked directly on a CGLIB proxy can access state on **the proxy object** instead of the dispatch path Spring uses to invoke the target. Therefore, when a class has state, calling a `final` method on a proxy can cause surprising behavior, even seeing uninitialized field values contrary to expectations. It is not merely “missing advice logs”; avoid implementing stateful beans and expecting `final` methods on CGLIB proxies to behave like every other public method.

### 4.3. Registering the Spring Aspect and Pointcut

**`TraceAspect.java`**

```java
package com.example.finalproxy;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    @Before("execution(public * com.example.finalproxy.CglibService.*(..))")
    public void beforeService(JoinPoint joinPoint) {
        System.out.println("advice:" + joinPoint.getSignature().getName());
    }
}
```

The `execution(...)` expression covers **the signatures of both `open(..)` and `locked(..)`**, yet advice only runs when the invocation is intercepted by the Spring proxy. This is the exact distinction the example illustrates.

### 4.4. Enabling Class-Based Proxies

**`ClassProxyConfig.java`**

```java
package com.example.finalproxy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class ClassProxyConfig {
    @Bean
    TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    CglibService cglibService() {
        return new CglibService();
    }
}
```

`TraceAspect` is a Spring bean via `@Bean`, without needing `@Component`. `@EnableAspectJAutoProxy(proxyTargetClass=true)` requests class proxies for matching beans. `CglibService` is not `final`, so Spring can generate a subclass proxy.

### 4.5. Main, Run Command, and Stdout

**`App.java`**

```java
package com.example.finalproxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {
    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(ClassProxyConfig.class)) {
            CglibService service = context.getBean(CglibService.class);

            System.out.println(
                "classProxy=" + AopUtils.isCglibProxy(service)
            );
            System.out.println(service.open("A"));
            System.out.println(service.locked("B"));
        }
    }
}
```

Run in the project directory with Gradle installed:

```bash
gradle run --quiet
```

If using the Gradle Wrapper: `./gradlew run --quiet` (Linux/macOS) or `gradlew.bat run --quiet` (Windows).

**Lines printed by the program code in exact order** (excluding logger/build tool messages):

```text
classProxy=true
advice:open
open:A
locked:B
```

Explanation:

1. `classProxy=true`: Spring returns a CGLIB Spring AOP proxy.
2. `advice:open`: `open(..)` is not `final`; CGLIB overrides it and routes through the advice.
3. `open:A`: the target method is still invoked and returns its result.
4. `locked:B`: `locked(..)` is still invoked, but **there is no `advice:locked`**, even though the pointcut matches its signature.

If you change the whole class to `final` while keeping class proxies and a matching advisor, treat that as **a separate startup-failure experiment**, not an edit needed to make the standard example run.

## 5. When the Target Class Is `final`: Consider a JDK Interface Proxy

A JDK dynamic proxy differs from CGLIB in one decisive respect: Spring creates **an object implementing the interface** and then delegates to the target. It **does not need to subclass** the target. Therefore, a `final` target class can still work with Spring AOP if:

- The target **implements a suitable business interface**.
- Spring configuration uses interface-based proxies (`proxyTargetClass=false` and not overridden by another config forcing class-based proxies).
- Callers retrieve/inject the bean by **the interface type**.
- Advice matches method calls on the proxy interface; if another method exists only on the implementation and is not on the proxied interface, callers cannot invoke it through the JDK proxy in the usual way.

### 5.1. Interface and `final` Class

Add **three files** to the same `com.example.finalproxy` package of the project above.

**`Api.java`**

```java
package com.example.finalproxy;

public interface Api {
    String call(String id);
}
```

**`FinalApi.java`**

```java
package com.example.finalproxy;

public final class FinalApi implements Api {
    @Override
    public final String call(String id) {
        return "api:" + id;
    }
}
```

Here **both the class and the implementing method are `final`**; however, the JDK proxy implements `Api` and intercepts `Api.call(..)` **before delegating** to the target. `final` on the target does not stop an interface proxy from intercepting the call.

**`InterfaceProxyConfig.java`**

```java
package com.example.finalproxy;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class InterfaceProxyConfig {
    @Bean
    Api api() {
        return new FinalApi();
    }

    @Bean
    ApiTraceAspect apiTraceAspect() {
        return new ApiTraceAspect();
    }

    @Aspect
    public static class ApiTraceAspect {
        @Before("execution(* com.example.finalproxy.Api+.call(..))")
        public void beforeCall() {
            System.out.println("advice:api");
        }
    }
}
```

`Api+` in the AspectJ expression selects the `Api` interface and matching subtypes/implementations. `@Bean` registers the aspect in the Spring context; `proxyTargetClass=false` ensures we are not explicitly forcing class proxies for the target. **Do not import both `ClassProxyConfig` and `InterfaceProxyConfig` into the same context**, as auto-proxy settings can merge and the class-proxy setting will win.

### 5.2. Separate Main for JDK Proxy

**`InterfaceApp.java`**

```java
package com.example.finalproxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class InterfaceApp {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                InterfaceProxyConfig.class)) {
            Api service = context.getBean(Api.class);

            System.out.println("jdkProxy=" + AopUtils.isJdkDynamicProxy(service));
            System.out.println(service.call("C"));
        }
    }
}
```

Create an additional Gradle task in `build.gradle`:

```gradle
tasks.register('runJdkProxy', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.finalproxy.InterfaceApp'
}
```

Run:

```bash
gradle runJdkProxy --quiet
```

**Stdout of the JDK proxy demo:**

```text
jdkProxy=true
advice:api
api:C
```

Even though both `FinalApi` and `FinalApi.call(..)` are `final`, advice can run because the entry call goes through **the JDK interface proxy**, not a subclass of `FinalApi`.

Do not try:

```java
FinalApi service = context.getBean(FinalApi.class);
```

in this JDK proxy configuration expecting to receive a target bean directly assignable to the implementation type. Spring returns a proxy implementing `Api`; the runtime type of the proxy is not a subclass of `FinalApi`. If the client must inject by concrete class, you must change the design/select an appropriate proxy type; a `final` target makes class proxies infeasible.

**Limitation:** a JDK proxy only intercepts at **methods on the proxy's interfaces**. Another `final` method declared only on the implementation class, not present on the interface, is not exposed on the JDK proxy for callers to use.

## 6. Failure Experiment When Forcing CGLIB on a `final` Class

This is **a snippet illustrating a failure scenario**; do not add it to the standard runnable project in section 4 or section 5:

```java
// Intentionally invalid example: final class required to create a class proxy
public final class FinalBillingService {
    public String bill(String id) {
        return id;
    }
}

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class InvalidConfig {
    @Bean
    FinalBillingService finalBillingService() {
        return new FinalBillingService();
    }

    @Bean
    Object tracingAspect() {
        // Explanatory placeholder only, DO NOT use as a real @Aspect.
        return new Object();
    }
}
```

The snippet above **only illustrates the `final` class and forced-proxy configuration; it is not yet an error-inducing test** because no advisor matches `FinalBillingService`. To reproduce the error, you need a **Spring advisor that actually matches the `final` bean**. Logical example:

```java
@Aspect
class BillingAspect {
    @Before("execution(* FinalBillingService.bill(..))")
    public void beforeBilling() {
        // ...
    }
}
```

This is also **illustrative syntax**, not a standalone file: the type must use the fully qualified name matching its package and the aspect class must be registered as a Spring bean.

With an actually applicable advisor, Spring must proxy that final bean; CGLIB cannot subclass a `final` class. Exact output depends on version and configuration path, so **do not lock onto a verbatim exception message**; inspect the `BeanCreationException` / `AopConfigException` chain and the root cause related to the `final` class.

**Important:** Do not use `@EnableAspectJAutoProxy(proxyTargetClass=false)` to “auto-fix” every `final class`. If the class has no interface, Spring still needs a class proxy; if the application concurrently uses configs forcing class proxies (such as transaction/cache AOP or a Boot context), the effective setting may still be CGLIB.

## 7. Spring Boot Configuration and Auto-Proxy Advisors

In **Spring Boot** with AOP auto-configuration, the common property is:

```properties
# Spring Boot AOP: default is usually true
spring.aop.proxy-target-class=true
```

For a `final` target that already implements an interface, you can consider:

```properties
spring.aop.proxy-target-class=false
```

to prefer JDK proxies when infrastructure and other configurations allow. **Check the actual proxy using `AopUtils.isJdkDynamicProxy`/`isCglibProxy`**, because a Spring context can merge auto-proxy requests from multiple places and take the stronger proxy setting.

Dependency selection by Spring Boot major version (e.g., Gradle already using Boot's BOM/dependency management):

```gradle
// Boot 3.x
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

```gradle
// Boot 4.x
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

These two blocks are **version-specific alternatives**, not to be applied together. CGLIB is bundled by Spring via `spring-core`; there is no need to declare a separate `cglib:cglib` dependency for modern Spring AOP.

Spring annotations that commonly use proxies/interceptors and carry similar `final` method risks under class-proxy mode:

| Spring feature | Risk with `final` methods on a CGLIB proxy | Proper verification |
| --- | --- | --- |
| `@Transactional` | Transaction interceptor does not run through the `final` method as expected | Observe the active transaction, rollback/commit outcome, and place annotations on interceptable entry methods. |
| `@Cacheable`/`@CacheEvict` | Cache advice may not run on `final` methods | Verify actual cache hit/miss/eviction behavior, not just annotations. |
| `@Async` | `final` invocation does not route into the async interceptor | Check the actual thread, return type, and completion. |
| Method security such as `@PreAuthorize` | Security advice may be bypassed on `final` methods | Must test access permissions through the real Spring proxy; this case is especially severe. |
| Custom `@Aspect` logging/metrics/audit | Missing logging/audit on `final` methods | Check observed events when calling the method through the container. |

The annotations above **all require their own activation configuration** (transaction management, caching, async, method security). `@EnableAspectJAutoProxy` only enables Spring AOP `@AspectJ` support; it does not replace configuration for those other features.

When security enforcement is required, always write external tests with unauthorized credentials and verify the method is protected; missing or present trace logs cannot substitute for an authorization test.

## 8. How to Handle Systems Where a `final` Class Is Required

### Option A — Keep `final`, Use an Interface Proxy If Suitable

Appropriate when:

- The public API is expressed by a clear interface.
- Callers inject/look up by the interface.
- The methods needing interception are on the interface.
- No other configuration forces class-based proxies.
- Using JDK proxies has been tested with the application's specific AOP features.

For example, a `final` Spring bean implements `PaymentPort`. Clients inject `PaymentPort`, and Spring uses a JDK proxy to intercept methods on the contract. **Do not rely on the `final` implementation type for injection**.

### Option B — Allow Subclassing, Keep Methods Needing Advice Non-`final`

If the application needs class proxies or the API has no interface yet, design the target class to be subclassable:

```java
public class PaymentService {
    public Receipt pay(String orderId) {
        // Public overridable method, suitable as an AOP entry method.
        return new Receipt(orderId);
    }
}
```

Illustrative snippet, assuming `Receipt` is a project-defined type. For real tests/application code to work, add Spring bean registration and corresponding proxy infrastructure.

Remove `final` only from **entry methods needing advice**, maintaining business immutability via dependency design and encapsulation rather than locking methods Spring needs to override. You do not need to remove `final` from internal helpers if they are not intercepted by advisors and do not go through the proxy.

### Option C — Explicit Decorator/Service Boundary

When the class cannot be modified, has no interface, or needs explicit sequencing rather than implicit interception:

```java
public final class FixedGateway {
    public String send(String text) {
        return "sent:" + text;
    }
}

public class AuditedGateway {
    private final FixedGateway delegate;

    public AuditedGateway(FixedGateway delegate) {
        this.delegate = delegate;
    }

    public String send(String text) {
        System.out.println("audit:send");
        return delegate.send(text);
    }
}
```

This is a **structural illustration**, not a standalone runnable AOP example. Registering `AuditedGateway` as a Spring bean and injecting it into callers establishes an explicit boundary for logging/auditing. If you still want Spring AOP on the decorator, the decorator class itself and its entry method must be proxyable.

### Option D — Requiring Interception Beyond Proxy Capabilities

If the requirement truly demands intercepting constructors, field access, or self-invocation inside an unmodifiable class, Spring AOP proxies are insufficient. You can consider **AspectJ compile-time/load-time weaving** with its own configuration, or refactor the requirement into explicit calls. This is not a feature enabled merely by `@EnableAspectJAutoProxy`. Evaluate deployment complexity, debuggability, and bytecode constraints before adopting weaving.

## 9. Special Notes for Kotlin, Records, and Special Class Types

- **Kotlin:** classes/methods are `final` by default unless declared `open`. In Spring apps using class proxies, you can use the Kotlin `kotlin-spring` compiler plugin (an `all-open` preset) to open classes/methods carrying appropriate Spring annotations; or design clear interfaces and use JDK proxies. Inspect the actual build/bytecode output, especially with custom annotations outside the plugin's default list.
- **Java `record`:** a `record` is a `final` class; it cannot be subclassed to create a CGLIB AOP proxy. Records fit better as immutable data carriers than as Spring business services needing method interception.
- **Java `sealed` hierarchy:** a dynamically generated subclass proxy can hit permitted-subclass constraints; do not assume every `sealed` class is proxyable. Test proxy types empirically on the Spring and JVM versions in use.
- **JDK module path:** CGLIB sometimes requires open access to packages; module access restrictions are an independent cause separate from `final`.
- **Methods marked `final` by other bytecode tools:** Lombok, the Kotlin compiler, or bytecode-generating libraries can make classes/methods `final` even when source code does not look like it. When hard to diagnose, inspect bytecode with `javap -p -v` and confirm modifiers.

Do not apply the same solution to every root cause. For example, Kotlin `all-open` resolves build-time override constraints for opened classes; it does not fix self-invocation.

## 10. Diagnostics with Spring APIs

### 10.1. Checking the Proxy Type

```java
Object bean = context.getBean("serviceBean");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

**Illustrative** snippet requiring `org.springframework.aop.support.AopUtils` imported and a suitable `context` variable. Interpretation:

- `isAopProxy`: whether the object returned by the container is a Spring AOP proxy.
- `isJdkDynamicProxy`: whether the proxy is created as a JDK interface proxy.
- `isCglibProxy`: whether it is a class-based proxy created by Spring.
- **None of the three confirms a `final` method was advised.** Invoke the method through the proxy bean and verify side effects/recorders.

### 10.2. Checking Modifiers via Reflection

```java
import java.lang.reflect.Modifier;

Class<?> type = CglibService.class;

System.out.println("classFinal=" + Modifier.isFinal(type.getModifiers()));
System.out.println(
    "lockedFinal=" + Modifier.isFinal(
        type.getMethod("locked", String.class).getModifiers()
    )
);
```

This is an **illustrative Java snippet**, not a standalone program, since it depends on `CglibService` from the example. In the demo, it prints:

```text
classFinal=false
lockedFinal=true
```

Inspect modifiers of the **target type** before/after checking the proxy: the runtime type of a CGLIB proxy can carry a generated name rather than the source class. To retrieve the actual target class, you can use `AopUtils.getTargetClass(bean)`.

### 10.3. Practical Verification Matrix

| Check | Expectation with CGLIB | Expectation with JDK proxy |
| --- | --- | --- |
| Target bean class is `final`, advisor matches | Cannot create class subclass proxy | Can work if the target implements suitable interfaces. |
| Target bean class is non-final, `final` method matches advisor | Proxy can exist, but `final` method is not advised | If call enters the proxied interface method and advisor matches: can be advised despite `final` implementation. |
| Method outside interface | CGLIB can intercept if overridable | Does not expose that method via JDK proxy. |
| Self-invocation `this.method()` | Advice does not run for internal calls | Advice does not run for internal calls. |
| `AopUtils.isAopProxy(bean)` | Can be `true` even when a `final` method is not advised | Can be `true`, though the pointcut/method must still match. |
| Caller injects by implementation | Usually works when class is subclassable | Not recommended; proxy only implements interfaces. |

### 10.4. Project Troubleshooting Checklist

1. Identify the Spring bean and **entry method** invoked by callers: where are annotations placed, and which bean is the target?
2. Call `context.getBean(...)` with a supported type and confirm the **actual proxy type** before drawing conclusions.
3. Use reflection/bytecode inspection to see whether the **target class** is `final` or the **entry method** is `final`/`private`.
4. Review all configurations affecting proxies: `@EnableAspectJAutoProxy`, `@EnableTransactionManagement`, Boot's `spring.aop.proxy-target-class`, and other advisor-creating modules.
5. Check whether callers go through the proxy, call `this.method()`, or invoke a target object created with `new`.
6. Check whether the method belongs to the interface if using JDK proxies; clients should inject interfaces.
7. Invoke a normal method and a `final` method sharing the same policy through the Spring bean; assert **advice appears in the right places**.
8. For security/transactions/caching, test actual business outcomes (deny, rollback, hit/miss) rather than relying on proxy logs.
9. If no proxy approach fits, refactor the entry point or replace with a decorator/explicit call.

## 11. Misconceptions Causing Hard-to-Spot Bugs

1. **“With `@Aspect` and a matching pointcut, every method is intercepted.”** Spring AOP also depends on the proxy, method signature, and call path.
2. **“Enable `proxyTargetClass=true` so even `final` methods get intercepted.”** False: choosing class proxies turns `final` into a direct overriding constraint.
3. **“A `final` class can never have Spring AOP.”** False: a JDK dynamic proxy can wrap an **interface** of a `final` target class.
4. **“Simply having an interface makes Spring use a JDK proxy.”** Not enough: configs forcing CGLIB and Boot's AOP defaults can change the selection.
5. **“A `final` method causes a startup error just like a `final` class.”** Usually false: the class can still be subclassed, so the proxy can be created; only the `final` method skips interception.
6. **“Every call to a `final` method through a CGLIB proxy is safe because the original method still runs.”** Do not assume so, especially with stateful targets; `final` methods are not overridden/delegated by Spring along the advice path and may see unexpected state on the proxy.
7. **“CGLIB proxy = AspectJ weaving.”** False: it is still a Spring proxy and does not automatically intercept internal target bytecode or constructors.
8. **“Seeing `isAopProxy=true` means `@Transactional` definitely works.”** False: you must verify actual invocation and transactional outcomes.
9. **“Missing advice due to a `final` method? Add `exposeProxy=true`.”** Wrong cause: exposing the proxy does not make a `final` method overridable.
10. **“Removing `final` in Kotlin source is always enough.”** You must inspect compiler plugins, Java bytecode, method visibility, proxy config, interface injection, and call paths.

## 12. Decision Rules

- **Want to keep the class `final` and still use Spring AOP?** Design an interface as the contract, select JDK proxies, inject by interface, and confirm actual config does not force CGLIB.
- **Want class-based Spring proxies?** The class must be subclassable; methods needing advice must be overridable, not `final`/`private`, and callers must go through the proxy.
- **Seeing the bean is a proxy yet the policy on a `final` method does not work?** This is a predictable outcome of CGLIB; change the entry boundary before adding more annotations.
- **Need to intercept internals/fields/constructors?** Spring proxies cannot satisfy this; consider a different design or separate AspectJ weaving with appropriate configuration.
- **Security or transaction policies?** Require integration tests confirming business behavior, specifically testing `final` methods and bean injection styles.

**Remember:** Spring AOP's CGLIB **requires subclassing**. A `final class` makes class-proxy creation impossible; a `final method` prevents advice on that specific method even though the bean has a proxy. A **JDK interface proxy** can resolve `final` target cases when the API and configuration suit it, but it does not solve self-invocation or methods outside the interface.

## Official Spring Documentation

- [Spring Framework 6.2 — Proxying Mechanisms (`final` limits and JDK/CGLIB)](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — AOP Proxies](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-proxies.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — ProxyFactoryBean and JDK/CGLIB](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/pfb.html)
- [Spring Boot — Spring AOP auto-configuration](https://docs.spring.io/spring-boot/reference/features/aop.html)
