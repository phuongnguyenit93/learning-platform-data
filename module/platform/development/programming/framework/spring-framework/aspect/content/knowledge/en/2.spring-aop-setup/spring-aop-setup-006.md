# Effective Scope of Spring AOP Configuration Across ApplicationContexts

## 1. Problem to understand when setting up Spring AOP

A Spring application may have a single `ApplicationContext`, yet it can also have **multiple independent contexts or parent–child relationships**. When using `@EnableAspectJAutoProxy`, the key question is not merely "is AOP enabled in the application?", but **in which context is AOP enabled and which context creates the bean to be proxied?**

**Core rule:** In explicit Spring Framework configuration, `@EnableAspectJAutoProxy` applies to the **local `ApplicationContext` containing that configuration**. If there are multiple contexts and each must proxy its own beans, `@AspectJ` support must be enabled in each corresponding context. Enabling it in the parent **does not automatically propagate** down to the child; enabling it in the child **does not re-process** beans already created by the parent.

This lesson only covers **proxy-based Spring AOP** and how to configure it in Spring IoC, especially `@EnableAspectJAutoProxy`. General AOP concepts do not need to be repeated.

After this lesson, you will:
- Identify the context owning a bean, the context holding auto-proxy infrastructure, and the context holding an aspect.
- Predict which beans actually receive a proxy when two `ApplicationContext`s are used.
- Distinguish **visibility of beans/aspects across a parent–child relationship** from **bean post-processing to create proxies**.
- Write a verification example using `AopUtils.isAopProxy(...)`.
- Apply these principles to multi-context Spring MVC setups and Spring Boot with AOP auto-configuration.

## 2. What does `@EnableAspectJAutoProxy` do in a context?

In a plain Spring Framework application, the following configuration lets Spring read Spring beans annotated with `@Aspect`, build advisors, and automatically create AOP proxies when needed:

```java
@Configuration
@EnableAspectJAutoProxy
public class AopConfig {
}
```

This configuration requires the `aspectjweaver` library on the classpath so Spring can parse `@AspectJ` pointcut expressions. Putting `@Aspect` on a class **is not enough** to have an aspect bean: the class must be registered via `@Component`, `@Bean`, or another suitable Spring bean registration mechanism.

In an enabled context, Spring infrastructure registers an **auto-proxy creator** (a `BeanPostProcessor`). When the context creates beans, this processor evaluates applicable advisors and can return a proxy instead of the raw target.

Single-context diagram:

```text
ApplicationContext A
├── @Configuration + @EnableAspectJAutoProxy
│    └── registers AOP auto-proxy creator in A
├── @Bean / @Component: AuditAspect
│    └── Spring parses advice/pointcuts into advisors
└── @Bean / @Service: BillingService
     └── A creates BillingService → A applies bean post-processors
                                     └── matching advisor?
                                           ├── yes → return proxy
                                           └── no → return original bean
```

For advice to actually execute, **the method must match a pointcut and the call must go through the proxy**. Enabling AOP does not force every bean to have a proxy and does not turn internal method calls on `this` into proxied calls.

### Multiple configurations in the same context

If multiple `@Configuration` classes in the **same context** declare auto-proxy options, Spring merges the appropriate auto-proxy infrastructure within that context; options like `proxyTargetClass` can affect the context's shared proxy configuration. This **does not turn** contexts in a parent–child tree into a single unified AOP infrastructure.

## 3. Parent–child contexts: two separate scopes

Example with two contexts:

```text
Parent ApplicationContext
├── parentService     (created by parent)
├── parentAspect      (registered by parent)
└── parent AOP creator?  ← only if parent enables AOP

                 ↑ child can look up some beans from parent
                 │
Child ApplicationContext
├── childService      (created by child)
├── childAspect       (registered by child)
└── child AOP creator?   ← only if child enables AOP
```

In this relationship:
1. **Beans defined and initialized by the parent** are processed by the parent's `BeanPostProcessor`s. If the parent creates a Spring AOP proxy, the child receives that exact proxy when looking up the parent bean.
2. **Beans defined and initialized by the child** are processed by the child's `BeanPostProcessor`s. A processor residing only in the parent does not automatically post-process child beans.
3. A child can normally look up parent beans if the name/type matches and is not shadowed by a local definition. The parent cannot look up beans defined only in the child.
4. **Seeing an aspect/advisor from an ancestor does not mean the ancestor's auto-proxy creator runs in the child.** Conversely, an auto-proxy creator inside the child can use advisors/aspects that its bean-lookup mechanism sees in the parent to advise beans **created by the child**, if pointcuts match. These are two separate aspects.
5. If the child registers a bean with the same name as a parent bean, the local bean normally shadows the parent bean in name-based lookups. Do not infer that the two beans become the same instance or share the same proxy.

**Why?** A `BeanPostProcessor` operates **per bean factory/container**. The AOP auto-proxy creator is a `BeanPostProcessor`. When the child calls `getBean(...)` and obtains a bean managed by the parent, finding that bean does not cause the child to use its own auto-proxy creator to recreate or re-wrap the parent-owned instance.

This is the difference between **bean ownership boundaries** and **bean lookup visibility**.

## 4. Parent and child AOP enablement matrix

To make the matrix verifiable, assume:
- Parent owns a `ParentService` bean and an aspect with a pointcut matching only `ParentService.work()`.
- Child owns a `ChildService` bean and an aspect with a pointcut matching only `ChildService.work()`.
- Both services are non-`final` classes with `public` methods, called externally via beans obtained from Spring.
- No other auto-proxy creator is configured; hence results in the table speak only about **AOP enabled via `@EnableAspectJAutoProxy`**.

| AOP enabled in parent | AOP enabled in child | `ParentService` has Spring AOP proxy? | `ChildService` has Spring AOP proxy? | Explanation |
| --- | --- | --- | --- | --- |
| No | No | No | No | Neither context has an auto-proxy creator for `@AspectJ`. |
| Yes | No | Yes | No | Parent processes parent's beans; child lacks the corresponding auto-proxy creator. |
| No | Yes | No | Yes | Child processes child's beans; parent's bean is not retroactively proxied by child. |
| Yes | Yes | Yes | Yes | Each context actively processes its own beans. |

The matrix states **proxy status** in the isolated model above. In real systems, other mechanisms (such as declarative transactions or another AOP configuration) can also create proxies; inspect specific beans rather than inferring solely from the presence of `@EnableAspectJAutoProxy`.

### An easily misunderstood case

Suppose **only the child enables AOP**, and then you run:

```java
ParentService inherited = childContext.getBean(ParentService.class);
```

The `inherited` variable still points to the bean (or proxy if any) created by the parent. It is **not automatically turned into a child proxy**. Conversely, if the parent already enabled AOP and returned a proxy for `ParentService`, the child sees that parent proxy even when the child does not enable AOP.

## 5. Standalone Java example: verifying all four cases

The example uses **Java 17+, Spring Framework 6.1.14, and Gradle**. This is a plain Spring Framework program, intentionally **without Spring Boot**, to clearly control which context has `@EnableAspectJAutoProxy`. The classes do not use component scanning so beans are not accidentally registered into the wrong context.

### 5.1. Create the Gradle project

Structure:

```text
spring-aop-context-scope/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/scope/
    ├── ContextScopeDemo.java
    ├── ParentService.java
    ├── ChildService.java
    ├── ParentTrace.java
    └── ChildTrace.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-context-scope'
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
    mainClass = 'demo.scope.ContextScopeDemo'
}
```

`spring-aop` contains proxy creation infrastructure; `spring-context` provides `ApplicationContext` and Java configuration; `aspectjweaver` is the library Spring needs to handle `@AspectJ` and pointcut expressions. The presence of these three dependencies **does not automatically enable** `@EnableAspectJAutoProxy` in this plain Framework example.

### 5.2. Two services belonging to two contexts

`src/main/java/demo/scope/ParentService.java`:

```java
package demo.scope;

public class ParentService {
    public String work() {
        return "parent-result";
    }
}
```

`src/main/java/demo/scope/ChildService.java`:

```java
package demo.scope;

public class ChildService {
    public String work() {
        return "child-result";
    }
}
```

### 5.3. Two aspects with separate match targets

`src/main/java/demo/scope/ParentTrace.java`:

```java
package demo.scope;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class ParentTrace {
    @Before("execution(public * demo.scope.ParentService.work(..))")
    public void beforeWork() {
        System.out.println("advice:parent");
    }
}
```

`src/main/java/demo/scope/ChildTrace.java`:

```java
package demo.scope;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class ChildTrace {
    @Before("execution(public * demo.scope.ChildService.work(..))")
    public void beforeWork() {
        System.out.println("advice:child");
    }
}
```

Both aspects are ordinary `@Aspect` classes; they will be registered into Spring via `@Bean` in the next part. The parent's pointcut does not match `ChildService` and vice versa. Thus, even when the child sees `ParentTrace` through the parent, logs for `ChildService` are produced only by `ChildTrace`. This design clearly shows **in which context the proxy is created**, without relying on the false assumption that a child cannot see parent aspects at all.

### 5.4. Registering beans and AOP enablement per context

`src/main/java/demo/scope/ContextScopeDemo.java`:

```java
package demo.scope;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class ContextScopeDemo {

    @Configuration(proxyBeanMethods = false)
    static class ParentBeans {
        @Bean
        ParentService parentService() {
            return new ParentService();
        }

        @Bean
        ParentTrace parentTrace() {
            return new ParentTrace();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ChildBeans {
        @Bean
        ChildService childService() {
            return new ChildService();
        }

        @Bean
        ChildTrace childTrace() {
            return new ChildTrace();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy
    static class EnableParentAop {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy
    static class EnableChildAop {
    }

    public static void main(String[] args) {
        runCase("NONE", false, false);
        runCase("PARENT_ONLY", true, false);
        runCase("CHILD_ONLY", false, true);
        runCase("BOTH", true, true);
    }

    private static void runCase(String name,
                                boolean enableParent,
                                boolean enableChild) {
        try (AnnotationConfigApplicationContext parent =
                 new AnnotationConfigApplicationContext()) {

            parent.register(ParentBeans.class);
            if (enableParent) {
                parent.register(EnableParentAop.class);
            }
            parent.refresh();

            try (AnnotationConfigApplicationContext child =
                     new AnnotationConfigApplicationContext()) {

                child.setParent(parent);
                child.register(ChildBeans.class);
                if (enableChild) {
                    child.register(EnableChildAop.class);
                }
                child.refresh();

                ParentService p = parent.getBean(ParentService.class);
                ChildService c = child.getBean(ChildService.class);
                ParentService inherited =
                    child.getBean(ParentService.class);

                System.out.printf(
                    "%s parentProxy=%s childProxy=%s sameParent=%s%n",
                    name,
                    AopUtils.isAopProxy(p),
                    AopUtils.isAopProxy(c),
                    p == inherited
                );

                System.out.println("parent=" + p.work());
                System.out.println("child=" + c.work());
            }
        }
    }
}
```

**Exact explanation of each class's role:**
- `ParentBeans` registers `ParentService` and `ParentTrace` **into the parent**, regardless of whether the parent enables AOP.
- `ChildBeans` registers `ChildService` and `ChildTrace` **into the child**.
- `EnableParentAop` and `EnableChildAop` carry the same annotation, yet are registered into **two different contexts**, giving them two independent configuration scopes.
- `child.setParent(parent)` establishes parent-bean lookup access from the child; it does not turn the auto-proxy creator into a shared `BeanPostProcessor`.
- `AopUtils.isAopProxy(...)` tells whether the retrieved object is a Spring AOP proxy. Comparing `p == inherited` proves the child receives the **exact instance provided by the parent**.

### 5.5. Running the program and verifying the output

From the directory containing `build.gradle`:

```bash
gradle run
```

Or, if the project already has the Gradle Wrapper, use `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows).

Lines printed by **application code** (excluding Gradle build output or environment loggers) in order:

```text
NONE parentProxy=false childProxy=false sameParent=true
parent=parent-result
child=child-result
PARENT_ONLY parentProxy=true childProxy=false sameParent=true
advice:parent
parent=parent-result
child=child-result
CHILD_ONLY parentProxy=false childProxy=true sameParent=true
parent=parent-result
advice:child
child=child-result
BOTH parentProxy=true childProxy=true sameParent=true
advice:parent
parent=parent-result
advice:child
child=child-result
```

**Reading the output:**
- `NONE`: both services are still Spring beans, yet have no AOP proxy because auto-proxy is not enabled.
- `PARENT_ONLY`: the parent's advice runs for `ParentService`; `ChildService` remains a plain bean, even though the child's parent has AOP enabled.
- `CHILD_ONLY`: `ChildService` receives advice; `ParentService` is not re-processed by the child and `sameParent=true`.
- `BOTH`: each context creates a proxy for the service it owns, and each advice appears at the exact call matching its pointcut.

This example demonstrates **`@AspectJ` configuration boundaries**, not running AOP on objects created with `new` outside Spring. All calls use beans returned by the container.

## 6. Applying this to Spring MVC with root context and DispatcherServlet

In a traditionally configured Spring MVC web application, you may have:

```text
Root WebApplicationContext
├── Service, Repository, shared infrastructure
├── @Aspect used for services
└── RootAopConfig (@EnableAspectJAutoProxy)
          |
          +--> DispatcherServlet A child WebApplicationContext
          |    ├── Controllers of servlet A
          |    └── ServletAopConfig (@EnableAspectJAutoProxy) if needed
          |
          +--> DispatcherServlet B child WebApplicationContext
               ├── Controllers of servlet B
               └── ServletAopConfig (@EnableAspectJAutoProxy) if needed
```

If pointcuts target **services created in the root**, Spring AOP configuration should exist in the **root context** so root can proxy those services. If pointcuts target **controllers created by a `DispatcherServlet` context**, ensure that servlet's context also has appropriate auto-proxy support.

Configuring `@EnableAspectJAutoProxy` **only in the root** will not automatically make all controllers in child servlets receive proxies. Conversely, placing the annotation only in the child has no retroactive effect on services already created by the root.

A concise configuration pattern where each config is **loaded into the right context**:

```java
// Loaded in the root context (configuration illustration, not a standalone app).
@Configuration
@EnableAspectJAutoProxy
public class RootAopConfig {
}

// Loaded in a DispatcherServlet context if needed
// to advise beans created by that servlet context itself.
@Configuration
@EnableAspectJAutoProxy
public class ServletAopConfig {
}
```

Do not accidentally register duplicate services/controllers/aspects across multiple contexts just to "enable AOP globally". Determine up front which beans belong to the root, which belong to each servlet, and whether pointcuts match the intended beans.

### Checking actual scope

You can log or assert directly:

```java
Object service = rootContext.getBean("orderService");
Object controller = servletContext.getBean("orderController");

System.out.println(AopUtils.isAopProxy(service));
System.out.println(AopUtils.isAopProxy(controller));
```

The snippet above only illustrates how to check, assuming two beans with those names are already registered. A `false` result **does not automatically prove a configuration bug**: the pointcut might not match, no corresponding advisor may exist, or the bean might not be proxyable under the chosen mechanism.

## 7. Spring Boot: auto-enabling does not erase context boundaries

Spring Boot provides **AOP auto-configuration**. When suitable AspectJ dependencies are present (typically via `spring-boot-starter-aop`), Boot can enable `@AspectJ` auto-proxying automatically without requiring the application to write `@EnableAspectJAutoProxy` manually.

Example Gradle dependency of a Boot application:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

With Spring Boot 3.3:
- `spring.aop.auto=true` is the default auto-configuration behavior when conditions are met; set `spring.aop.auto=false` to disable this AOP auto-configuration mechanism.
- `spring.aop.proxy-target-class=true` is Boot's default for class-based proxying; set `false` to prefer JDK proxies when appropriate.
- When an application has only **one** context, you usually do not need to worry about multiple container scopes.
- If a system creates **multiple** contexts (such as child contexts or a custom web hierarchy), inspect **which auto-configuration actually runs in each context**, which beans belong to which context, and which proxies are created there. Do not assume that because Boot enabled AOP in the main context, AOP automatically applies to every custom context you create.

**Do not confuse `@EnableAspectJAutoProxy` with Spring Boot properties:** the annotation is an explicit enablement in one context; Boot properties control the auto-configuration managed by Boot. Setting `spring.aop.auto=false` is not a guarantee that all proxies registered by manual configurations or other Spring mechanisms are disabled.

## 8. Common misconfigurations and misconceptions

| Scenario | Common misconception | How to diagnose/fix |
| --- | --- | --- |
| `@EnableAspectJAutoProxy` in parent; aspect/target in child | "Child automatically inherits AOP from parent" | Check for an auto-proxy creator in the child; enable AOP in the child when child beans need advising. |
| `@EnableAspectJAutoProxy` only in child; target bean from parent | "Child will wrap the parent bean with an extra proxy" | Identify the context owning the bean; configure AOP in the parent if proxying is needed when parent creates the bean. |
| Aspect in parent, target in child | "Cannot use parent aspect because it's a different context" | Distinguish child seeing ancestor beans/aspects from child having an auto-proxy creator; verify the specific pointcut. |
| Aspect only in child, target in parent | "Parent can see child aspect" | Parent cannot automatically see child beans; move the aspect/advisor logic to parent if the target belongs to parent. |
| Two child contexts sharing one parent | "Enabling AOP in child A also enables it for child B" | Each child has its own BeanFactory; configure each child independently as needed. |
| Same bean name in parent and child | "`getBean` in child definitely returns the parent bean" | Inspect local bean definitions, bean shadowing, and which context actually created the instance. |
| Moved AOP `@Configuration` to a different component scan | "Bean is still in the old context" | Verify `@ComponentScan` / `@Import` scope, where each config is registered, and where beans are created. |
| `isAopProxy(bean) == false` | "`@EnableAspectJAutoProxy` isn't working" | Check aspect bean, pointcut, method visibility, bean creation timing, and other proxy infrastructure. |
| `isAopProxy(bean) == true` yet advice prints nothing | "A proxy always runs all advice" | Verify pointcut/method match and that the call passes through the proxy; check self-invocation. |

### Why not check only the annotation?

`@EnableAspectJAutoProxy` may be placed on a config class, yet that config **is not registered in the context under inspection**. Furthermore, a service can be created by the parent and injected into the child; observing the injection site does not tell you where the proxy was created. When drawing conclusions, inspect **runtime beans and the owning context**, not just packages or Java class locations.

### Do `proxyTargetClass` or `exposeProxy` propagate across contexts?

Attributes such as:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true, exposeProxy = true)
```

are declared for the infrastructure in the corresponding context. `proxyTargetClass=true` prefers class-based proxies; `exposeProxy=true` permits accessing the current proxy via `AopContext` while inside a qualifying proxied call. They **do not** make the auto-proxy creator in this context post-process beans created by another context, and `exposeProxy` does not create an "application-wide proxy" shared across contexts.

Proxy limitations such as self-invocation, `final`, and `private` still apply regardless of how contexts are organized; they belong to proxy-based Spring AOP mechanics, not configuration inheritance bugs.

## 9. Diagnostic workflow when AOP fails to run across multiple contexts

1. **List the contexts:** How many `ApplicationContext`s exist? Which is parent, child, or sibling? Which have called `refresh()`?
2. **Identify bean ownership:** In which context is the target bean defined and created? If obtained via a child, check whether it is inherited from the parent.
3. **Check AOP enablement:** Into which context is `@EnableAspectJAutoProxy` loaded? With Boot, is AOP auto-configuration running there?
4. **Check aspect/advisor:** Does the aspect bean exist and is it visible to the corresponding auto-proxy creator? Does the pointcut match the exact target method?
5. **Check actual proxy:** Use `AopUtils.isAopProxy`; if needed, use `AopUtils.isJdkDynamicProxy` / `AopUtils.isCglibProxy`.
6. **Check the call path:** Does the client call through the Spring proxy or directly on target/`this`? Is the method compatible with the proxy type?
7. **Check timing:** Changing configuration after the context has created a bean does not automatically re-proxy that bean; fix startup configuration and restart the context to verify.

When deeply debugging a proxied bean, you can inspect the `Advisor`s Spring attached to the object if the proxy implements `org.springframework.aop.framework.Advised`:

```java
if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (org.springframework.aop.Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor);
    }
}
```

This is a diagnostic snippet for when you already have a `bean` variable obtained from Spring; it is not a standalone Java program. It helps distinguish "the bean is proxied" from "the proxy has the expected advisor". Some proxies or special configurations may not expose/allow modifying advisors through this interface, so conclusions should also rely on behavioral tests.

## 10. Practical conclusion

In Spring, **auto-proxy configuration belongs to each individual `ApplicationContext`**, while **beans, aspects, and advisors have their own ownership and lookup rules**. For parent–child hierarchies, remember:

- Enable `@EnableAspectJAutoProxy` in the **context that creates the target beans needing advice**.
- Do not treat the child's ability to look up a parent bean as proof that the child re-proxies that bean.
- When advising beans across multiple contexts, check the AOP mechanism in **each context holding target beans** and determine which aspects/advisors are visible to that context.
- Use `AopUtils.isAopProxy(...)` and method calls through Spring beans to verify hypotheses at runtime.

### Official Spring documentation

- [Spring Framework 6.0 Javadoc — `@EnableAspectJAutoProxy`](https://docs.spring.io/spring-framework/docs/6.0.23/javadoc-api/org/springframework/context/annotation/EnableAspectJAutoProxy.html): explicitly notes the annotation applies only to the local application context, including root/`DispatcherServlet` examples.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): enabling `@AspectJ` support and dependency requirements.
- [Spring Framework — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): per-container scope of `BeanPostProcessor`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy mechanics, proxy type configuration, and limitations.
- [Spring Boot 3.3 — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/3.3/reference/features/aop.html): Boot's AOP auto-configuration.
