# Spring AOP Limitations with the Java Module System and Class Access (JDK Proxy & CGLIB)

## 1. Context: Why Does the Same Aspect Work on the Classpath Yet Fail on the Module Path?

Spring AOP intercepts method calls through a **proxy**. A Spring bean can be wrapped by:

- **JDK dynamic proxy**: an object implementing the target's interfaces. Clients invoke methods through an interface.
- **Class-based proxy (CGLIB)**: Spring generates a subclass at runtime to override interceptable methods.

When moving a Java 9+ application onto the **Java Platform Module System (JPMS)** with `module-info.java` and `--module-path`, Java additionally enforces **which modules read which modules**, **which packages are publicly accessible**, **which packages allow deep reflection**, and **where the runtime is permitted to define proxy classes**. Consequently, AOP errors may surface only when deployed as named modules, even though the exact same source runs on the classpath.

In Spring, the right questions are:

1. Is Spring using a JDK proxy or CGLIB?
2. Which packages/modules do the bean, interface, configuration classes, and aspect belong to?
3. Are the target class/methods accessible or overridable?
4. Have the required packages been `exports`ed or `opens`ed to **the consuming modules**?
5. Has the runtime granted permission to dynamically define classes in the appropriate classloader/module?
6. Does the call pass through the Spring AOP proxy?

**Lesson scope:** proxy-based Spring Framework `@AspectJ`, JPMS consequences, and target/advice access rights. This is not a general JPMS introduction or standalone AspectJ bytecode weaving guide.

## 2. Distinguishing Four Types of Barriers

| Barrier type | Example | Relation to Spring AOP |
| --- | --- | --- |
| **Java language / class visibility** | Non-`public` class; `private` method; `final` method; package-private method invisible to a subclass in another package | Even if a module has `opens`, CGLIB still cannot override `final` or `private`; a JDK proxy only exposes methods through its interfaces. |
| **JPMS readability / exports** | Module A does not `requires` module B; package containing public API is not `exports`ed | Code in another module may fail to compile or directly access public interfaces/classes; a JDK proxy does not remove client-side API boundaries. |
| **JPMS deep reflection / opens** | Spring needs reflection to invoke non-public constructors or methods in an encapsulated package | Can hit `InaccessibleObjectException` or related access errors; must open the right package to the modules actually using reflection. |
| **Runtime-generated class / ClassLoader** | CGLIB needs to define a dynamic subclass in a strict module environment | Proxy creation may fail even for public methods; `--add-opens` does not cure every classloader or module-membership constraint. |

An often overlooked point: **`exports` and `opens` grant two different permissions**. Neither turns `private` or `final` methods into methods CGLIB can override.

## 3. How Does Spring Decide Between JDK and CGLIB?

In typical Spring AOP configuration, if the target implements suitable interfaces, Spring can use a JDK dynamic proxy; if there are no interfaces or configuration forces target-class proxying, Spring uses CGLIB.

### 3.1. Configuration in Spring Framework

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
class JdkProxyConfiguration {
    // Prefer JDK proxies when the target has suitable interfaces.
}
```

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class ClassProxyConfiguration {
    // Force target-class proxies when beans need a Spring AOP proxy.
}
```

These are **two independent illustrative snippets**; do not register both in a single context just to test two modes. When multiple Spring configurations in the same context request proxies, a `proxyTargetClass=true` setting in another mechanism such as transactions or caching can govern the actual choice.

### 3.2. Spring Boot Can Differ from Plain Spring Framework

In Spring Boot 3.3 with matching AOP auto-configuration (typically via `spring-boot-starter-aop`), class-based proxies are usually the default. You can change the preference with:

```properties
spring.aop.proxy-target-class=false
```

This property does not override every other explicit configuration in the context. Check **the actual runtime proxy**, rather than guessing from a single property.

### 3.3. Checking with Spring APIs

```java
Object bean = context.getBean("gateway");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

The snippet above is a **diagnostic snippet**: assuming a `context` variable exists and a bean named `gateway` is registered. `AopUtils` is in `org.springframework.aop.support`. If no advisor matches or the bean does not go through Spring, no AOP proxy may be created even when `@EnableAspectJAutoProxy` is enabled.

## 4. JDK Dynamic Proxies Under JPMS: What Is Allowed and What Is Not?

### 4.1. JDK Proxies Rely on Interfaces, Not Subclassing the Target

Suppose:

```java
package demo.orders.api;

public interface OrderGateway {
    String submit(String id);
}
```

```java
package demo.orders.internal;

public final class DefaultOrderGateway
        implements demo.orders.api.OrderGateway {

    @Override
    public String submit(String id) {
        return "stored:" + id;
    }
}
```

If clients are injected with **`OrderGateway`**, a JDK proxy can implement that interface even though the target class is `final`. CGLIB would be unable to subclass `DefaultOrderGateway` because the class is `final`.

However, a JDK proxy exposes only the interfaces it implements:
- Clients cannot cast a JDK proxy to `DefaultOrderGateway`.
- Methods present only on the class and **not declared on the proxy interface** cannot be invoked through that interface.
- Advised methods must still be called through the proxy; self-invocation from inside the target is not intercepted.
- Interfaces and method signatures must still be validly accessible in the client's module context.

### 4.2. JPMS Controls Interface Visibility from Other Modules

Example module model:

```java
// module-info.java of the API-providing module
module demo.orders {
    exports demo.orders.api;

    // Other requires/opens depend on the actual Spring structure.
}
```

`exports demo.orders.api` lets other modules with a valid readability relation reference public types in the API package. It **does not automatically grant deep reflection permissions to classes in internal packages**.

If `OrderGateway` is not exported to the client module, client code in another module may not be able to use the interface as a normal compile-time API. Therefore, do not rely on “a JDK proxy will show up” to bypass module boundary design.

### 4.3. Do Not Oversimplify JDK Proxy Rules

As of JDK 17, proxy classes generated by `java.lang.reflect.Proxy` follow package/module placement rules depending on the accessibility of the proxy interfaces. Specifically:
- Public interfaces in exported/open packages allow proxy classes to be placed consistently with their published accessibility.
- Public interfaces in unexported packages can result in proxy classes belonging to **a dynamic module with unexported packages**.
- Non-public interfaces carry strict constraints on sharing the same package/module when proxied together.
- Having a proxy class **does not mean** clients can reflect on constructors or access every type appearing in method signatures.

Hence, the practical recommendation with Spring is **public business interfaces in packages exported to consuming modules**, injecting by interface, and letting Spring manage the proxy. Do not hard-code assumptions about runtime-generated module names or proxy class names.

## 5. CGLIB and JPMS: What Permissions Does a Dynamic Subclass Need?

### 5.1. CGLIB Is Constrained by Inheritance and Overridability

Class-based proxies rely on a dynamic subclass of the target class.

| Target or method | JDK interface proxy | CGLIB class proxy |
| --- | --- | --- |
| `final` target class with a public interface | Can proxy via the interface | Cannot subclass a `final` class |
| `final` method on the target | Interface method can be intercepted by JDK proxy | Cannot override a `final` method |
| `private` method | Not on the proxy interface to call | Cannot be overridden |
| Package-private method of a superclass in another package | Not directly part of the interface API | Not visible to override like normal methods |
| Public non-`final` method | If the method is exposed through the interface | Can override if class/proxy generation is valid |
| Method called only via `this.otherMethod()` inside the target | Bypasses the proxy | Bypasses the proxy |

The last two rows are unrelated to JPMS: they are fundamental limits of Spring AOP proxies. Adding `opens` or `--add-opens` **does not fix self-invocation or non-overridable methods**.

### 5.2. The Module Path Can Block Subclass Definition

In Java 9+, classes defined at runtime must obey the module system and classloader rules. Spring's CGLIB subclass-generation path typically involves `MethodHandles.Lookup#defineClass` or reflective fallbacks depending on the environment. `Lookup#defineClass` can only be used under appropriate package/loader conditions. When a module or classloader does not permit defining a proxy class where required, proxy generation can fail.

An example explicitly noted in Spring documentation is **attempting to create a CGLIB proxy for a class in `java.lang` when deployed on the module path**. This is not a typical application service scenario; it demonstrates a real module-system constraint on dynamic subclassing.

Spring documentation notes that fallback cases on the classpath may require the JVM option:

```text
--add-opens=java.base/java.lang=ALL-UNNAMED
```

**Do not use that option as a universal recipe for all module-path errors:**
- `ALL-UNNAMED` opens only to **unnamed modules**, not to named modules.
- For named modules, target module names must be evaluated specifically; even when opening the right package, class-definition limits in incompatible classloaders/modules may remain.
- Widely opening `java.base/java.lang` just to force-proxy a core JDK class is usually a sign to change the proxy design. Do not apply `--add-opens=java.base/java.lang=ALL-UNNAMED` globally when the real error belongs to your application's own packages.

### 5.3. Errors Can Surface During Spring Context Initialization

If Spring finds an aspect advisor and needs a class proxy for a bean yet cannot generate the subclass, context startup can fail with exceptions related to `AopConfigException`, `CodeGenerationException`, `IllegalAccessException`, or `InaccessibleObjectException`; exact exception names depend on the call stack and version.

Do not read **only** the outermost error line. Inspect nested `Caused by` clauses to determine:
- Which module contains the class whose access was denied?
- Which package is missing `opens` or `exports`?
- Which component is attempting reflective access or class definition?
- Which bean needs a CGLIB proxy, and why did Spring select a class proxy?
- Can the bean be switched to a JDK proxy?

## 6. `exports`, `opens`, `--add-exports`, `--add-opens`: Choosing the Right Tool

| Syntax | Permission granted | Example use in a Spring context |
| --- | --- | --- |
| `exports p;` | Allows any module that **reads** it to access public types/members in package `p` via normal access | Export business API interfaces to client modules |
| `exports p to m;` | Allows module `m` to access the public API of package `p` | Restrict an API specifically to one module |
| `opens p;` | Allows other modules runtime deep reflection into package `p` | Framework needs reflection on constructors/fields/methods in the app |
| `opens p to m;` | Grants selective deep reflection to module `m` | Open package to the Spring modules that actually need access |
| `--add-exports=A/p=B` | Adds an export at compile/run time per configuration | Compatibility workaround when module `A`'s descriptor cannot be edited |
| `--add-opens=A/p=B` | Adds runtime deep reflection permission | Fix specific access errors when package open permissions are missing |

**Principle:** `exports` is not equivalent to `opens`. Public API access does not automatically grant Spring `setAccessible(true)` permission on non-public members. Conversely, `opens` grants runtime reflection access but does not replace API exports for compiling client modules.

### 6.1. Example `module-info.java` Model for an App with Spring AOP

The snippet below **illustrates module design**, not a standalone JPMS project to paste directly into the classpath Gradle example in section 8. Spring module names and `requires` lists must be adjusted to match your actual modules, dependencies, and active features.

```java
module demo.orders {
    requires spring.context;
    requires spring.beans;
    requires spring.aop;

    // Business interface visible to client modules.
    exports demo.orders.api;

    // Spring is permitted to reflect into the implementation area.
    // Choose target modules based on stack-trace evidence
    // and actual Spring dependencies.
    opens demo.orders.internal
        to spring.core, spring.beans, spring.context, spring.aop;
}
```

Here:
- `exports demo.orders.api` places the interface at the API boundary.
- `demo.orders.internal` does not become public API merely because Spring can reflect on it.
- `opens ... to ...` is a **qualified opens**: list only the necessary modules rather than opening to the entire world.
- Spring configuration may also need to open packages containing `@Configuration`, aspects, or classes instantiated/initialized via reflection. Verify the actual packages instead of assuming only `internal` needs opening.
- Module declarations alone cannot guarantee CGLIB proxy creation succeeds in every classloader or for every target class; inspect class characteristics and runtime behavior.

### 6.2. Example JVM Option When a Module Closes an Application Package

For a named module `demo.orders`, if the runtime reports that Spring module `spring.core` lacks deep reflection permission into `demo.orders.internal`, an option equivalent to editing the module descriptor (while testing) is:

```bash
java --add-opens=demo.orders/demo.orders.internal=spring.core \
     --module-path "<actual-module-path>" \
     --module demo.orders/demo.orders.Main
```

This is a **structural command illustration**, not a ready-to-run command: `<actual-module-path>` must be replaced with the real module path and `demo.orders.Main` must exist in the application. Do not treat this command as tested for every Spring app. If multiple Spring modules need reflective access, verify each target module from the specific exception.

When you control the application's source code, `module-info.java` is a more stable and reviewable place to declare permissions than adding numerous opaque JVM flags.

## 7. Runnable Spring AOP Example Comparing JDK Proxies and CGLIB

To verify **proxy types** before introducing JPMS, the following example runs on the **classpath**, using Java 17 and Spring Framework 6.1.14. It intentionally uses two **separate** contexts: one allowing JDK proxies when interfaces exist, and one forcing CGLIB. There is no `module-info.java` in this project.

### 7.1. File Structure

```text
spring-aop-proxy-access/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/jpms/
    ├── Gateway.java
    ├── GatewayImpl.java
    ├── TraceAspect.java
    └── Demo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-proxy-access'
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
    mainClass = 'demo.jpms.Demo'
}
```

### 7.2. Interface for the JDK Proxy

`src/main/java/demo/jpms/Gateway.java`:

```java
package demo.jpms;

public interface Gateway {
    String transfer(String id);
}
```

### 7.3. Target Implementing the Method

`src/main/java/demo/jpms/GatewayImpl.java`:

```java
package demo.jpms;

public class GatewayImpl implements Gateway {

    @Override
    public String transfer(String id) {
        System.out.println("target:" + id);
        return "ok:" + id;
    }
}
```

The target is non-`final` and `transfer` is public non-`final`, so it can be proxied by class or interface. This isolates the **proxy type** question from `final`-related failures.

### 7.4. Aspect Signaling Advice Ran Through the Proxy

`src/main/java/demo/jpms/TraceAspect.java`:

```java
package demo.jpms;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {

    @Before("execution(public * demo.jpms.GatewayImpl.transfer(..))")
    public void beforeTransfer(JoinPoint joinPoint) {
        System.out.println("aspect:" + joinPoint.getSignature().getName());
    }
}
```

`TraceAspect` is a Spring `@Aspect`. The lesson uses a pointcut matching the method on the **target class**; Spring will apply advice to calls going through the proxy. The aspect is registered via `@Bean` in `Demo`, without needing `@Component`.

### 7.5. Two Contexts with Different Proxy Selections

`src/main/java/demo/jpms/Demo.java`:

```java
package demo.jpms;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class Demo {

    @Configuration(proxyBeanMethods = false)
    public static class CommonBeans {

        @Bean
        public Gateway gateway() {
            return new GatewayImpl();
        }

        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(CommonBeans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class JdkConfig {
    }

    @Configuration(proxyBeanMethods = false)
    @Import(CommonBeans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class CglibConfig {
    }

    public static void main(String[] args) {
        show("JDK", JdkConfig.class);
        show("CGLIB", CglibConfig.class);
    }

    private static void show(String label, Class<?> config) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(config)) {

            Gateway bean = context.getBean(Gateway.class);

            System.out.println(label + " jdk=" +
                    AopUtils.isJdkDynamicProxy(bean) +
                    " cglib=" + AopUtils.isCglibProxy(bean) +
                    " implementsClass=" + (bean instanceof GatewayImpl));

            String result = bean.transfer(label.toLowerCase());
            System.out.println(label + " result=" + result);
        }
    }
}
```

Two `ApplicationContext` instances are created and closed separately, keeping the CGLIB case's `proxyTargetClass=true` setting from affecting the JDK case. `@Import(CommonBeans.class)` registers the required beans in the active context; `@EnableAspectJAutoProxy` creates the AOP infrastructure for each context.

### 7.6. Running and Comparing Stdout

In the directory containing `build.gradle`, using an installed Gradle:

```bash
gradle run
```

If the project has a Gradle Wrapper, use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows.

Lines **printed by the Java code**, excluding Gradle/environment logging:

```text
JDK jdk=true cglib=false implementsClass=false
aspect:transfer
target:jdk
JDK result=ok:jdk
CGLIB jdk=false cglib=true implementsClass=true
aspect:transfer
target:cglib
CGLIB result=ok:cglib
```

Meaning:
- `implementsClass=false` for the JDK proxy: the object implements `Gateway`, yet **is not an instance of `GatewayImpl`**. On the module path, having a public exported API interface aligns well with this pattern.
- `implementsClass=true` for CGLIB: the proxy is a subclass of `GatewayImpl`. When moving to named modules, subclass generation and access permissions to the target class become items to verify.
- Both cases run `aspect:transfer`: differing proxy types **do not lose advice**, provided the pointcut matches and calls go through the proxy.
- The classpath example above **does not yet prove a real JPMS configuration has sufficient `exports`/`opens`**; further testing is needed when packaging as a named module.

## 8. Moving to the Module Path: A Systematic Inspection Checklist

When an application runs on the classpath yet fails on the module path, proceed in order to pinpoint the real cause:

### Step 1 — Identify Modules and Launch Mode

Check whether `module-info.java` exists and whether the app is actually launched with `--module-path` / `--module`. Do not infer from using JDK 17 that all application classes belong to named modules. Applications launched on the normal classpath live in the unnamed module and have different access boundaries.

### Step 2 — Identify Beans Needing Proxies and Proxy Types

From nested exception causes or the startup failure point, find the Spring bean being advised. If the context starts, inspect:

```java
Object bean = context.getBean("gateway");
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

If Spring is creating a CGLIB proxy for a class that you can expose via an interface, consider interface design and setting `proxyTargetClass=false` **across all relevant configurations**. Another Spring subsystem requiring class-based proxies can override an isolated `@EnableAspectJAutoProxy` choice.

### Step 3 — Check Methods/Classes Before Modifying Modules

Even before `--add-opens`, check whether the target has a `final` class or `final`/`private` methods. For CGLIB, these are Java inheritance limits and cannot be changed with JPMS flags. For JDK proxies, ensure the methods to call are declared on an interface implemented by the proxy.

### Step 4 — Check Readability and Exported APIs

If encountering compile-time errors or `IllegalAccessError` for public APIs, check:
- Does the client module have the proper `requires <api-module>`?
- Is the package containing the public interface/class `exports`ed to the client?
- Is an interface in an unexported package accidentally being used as the API of another service module?

Do not try to satisfy public API needs by adding `opens` and expecting the Java compiler to treat the package as exported.

### Step 5 — Check Deep Reflection

If `InaccessibleObjectException` reports that a module `does not "opens ..."`, read the full **source module, package, and target module** names. Check where Spring is reflecting:
- `@Configuration` and bean factory methods;
- non-public constructors/fields/methods of Spring-managed beans;
- methods/annotations that Spring AOP or other Spring mechanisms must introspect.

Add `opens package to moduleA, moduleB` to the module descriptor **when you own the source** and it fits the requirement. In environments where descriptors cannot be modified, use narrowly scoped `--add-opens` first to confirm the hypothesis.

### Step 6 — If CGLIB Class Creation Still Fails, Inspect ClassLoaders

When errors involve `defineClass`, `MethodHandles.Lookup`, or core JDK packages, check which classloader loaded the target and where the proxy class needs to be defined. Under strict JPMS, **opening a package does not guarantee permission to define classes in an unrelated classloader**. Spring Framework has documented this limitation for certain core JDK types; the design solution is usually avoiding subclassing them, switching to an interface proxy, or shifting the Spring bean boundary.

### Step 7 — Verify Calls Actually Go Through the Proxy

After startup succeeds, if advice still does not run:
- Is the bean managed by Spring and the `@Aspect` registered as a bean?
- Is AOP auto-proxying enabled in **the right `ApplicationContext`**?
- Does the pointcut match the target's method?
- Does the client call externally through the proxy, or does the target call `this.method()`?
- Is the method actually exposed by the JDK interface proxy or overridden by CGLIB?

**JPMS is only one layer of barriers.** A Spring AOP error occurring on the module path can still be caused by ordinary pointcut config or self-invocation.

## 9. Comparing Approaches by Scenario

| Scenario | Solution to consider first | What not to do |
| --- | --- | --- |
| Only need advice on public interface methods | Keep the interface public, export the API package, and try a JDK proxy | Force CGLIB on an un-subclassable `final` implementation |
| Bean has no interface and needs CGLIB | Ensure the class is non-`final`, methods are overridable, and module/runtime permissions allow subclass creation | Use `--add-opens` as a way to unlock `final` |
| Spring reports inability to reflect on non-public constructors/methods | Open the exact package to the required Spring modules via `opens`/`--add-opens` | Export every internal package or open to `ALL-UNNAMED` indiscriminately |
| Compiling client module cannot reference the interface | Configure `exports` on the API and `requires` properly | Only `opens` without exporting the API |
| JDK proxy cannot be cast to the implementation class | Inject/look up by interface; inspect what determines the proxy type | Force-cast or rely on random proxy class names |
| Spring tries to subclass a core JDK class under named modules | Re-evaluate target/proxy design; use an application-owned interface/adapter | Open all of `java.base` expecting to fix every limitation |
| Internal calls are not advised by the aspect | Move the boundary to a collaborating bean and invoke through a Spring proxy | Edit `module-info.java` when the root cause is self-invocation |
| Spring Boot uses CGLIB even though AOP was set to `false` | Check properties, transaction/caching settings, and the actual proxy in the context | Reason from a single annotation while ignoring other configs |

## 10. Designing JPMS-Friendly Spring AOP

A clean architecture typically looks like:

```text
module demo.orders
│
├── demo.orders.api
│   └── OrderGateway          [public interface, exported as needed]
│
├── demo.orders.internal
│   └── DefaultOrderGateway   [implementation class, kept private]
│
├── demo.orders.aop
│   └── AuditAspect           [Spring @Aspect bean]
│
└── demo.orders.config
    └── SpringConfiguration   [@Configuration, registers beans]

module-info.java:
  requires only actually used modules;
  exports API packages needed by clients;
  opens packages Spring must reflect on to specific modules;
  do not open internals without a concrete need.
```

When Spring can use a JDK proxy over an interface API, you often reduce pressure to subclass implementation classes. However, that **does not eliminate** Spring IoC's reflection needs (if configurations/constructors/members of beans must be inspected) or the requirement for client modules to read the API-providing module.

Conversely, if you genuinely must advise non-interface methods, evaluate class-based proxies along both axes: *Java overridability* and *module/runtime subclassability*. Do not sacrifice JPMS encapsulation solely for the convenience of casting beans to implementation classes without a valid technical reason.

## 11. Key Takeaways

- **Spring AOP is proxy-based**: JDK proxies sit at interfaces; CGLIB sits at subclasses. Methods must be called through the proxy for advice to run.
- **`module-info.java` strengthens encapsulation**: `requires`, `exports`, and `opens` play different roles; open only the exact packages/modules Spring needs.
- **CGLIB faces two kinds of constraints**: Java forbids overriding `private`/`final`, and JPMS can block defining dynamic subclasses.
- **JDK proxies do not “bypass JPMS”**: public API interfaces and cross-module access permissions must still be valid; the JDK has its own package/module rules for proxy classes.
- **`--add-opens=java.base/java.lang=ALL-UNNAMED` is not a cure-all**: it targets unnamed modules and does not resolve every named-module or classloader case.
- **Always inspect the actual runtime**: proxy type, nested exceptions, the context owning the bean, advisor matches, and call paths; adjust module descriptors or proxy design based on evidence.

### References

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB, `final`/`private`, Java Module System limits, self-invocation.
- [Spring Framework — Component Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): `exports`/`opens` permissions when using Spring on the module path.
- [JDK 17 — java.lang.reflect.Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): package/module rules for JDK dynamic proxy classes.
- [Dev.java — Opening for Reflection](https://dev.java/learn/organizing/modules/opening-for-reflection/): difference between `exports`/`opens` and reflection access permissions.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): declaring `@Aspect` and enabling Spring AOP.
