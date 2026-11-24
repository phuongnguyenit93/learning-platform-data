# How Does Spring Bean Scope Differ from Aspect Instantiation Models?

## 1. Two Seemingly Similar Questions That Spring Answers with Two Different Mechanisms

In Spring AOP, when seeing a class with both `@Aspect` and `@Component`, it is very easy to think that `@Scope` on that class and the argument of `@Aspect(...)` are two ways of writing the same rule. In reality, they address **two different levels**.

- **Spring bean scope** answers: *Under what lifecycle does `BeanFactory`/`ApplicationContext` supply and manage objects for a bean definition?* Common scopes are `singleton`, `prototype`, `request`, and `session`. This mechanism applies to beans in general, including service beans and beans used to declare aspects.
- **Aspect instantiation model** answers: *Which join points/proxies/targets does Spring AOP create or associate aspect instances with when executing advice?* By default, an aspect uses the **singleton** model; with `@AspectJ` syntax supported by Spring, there are also models such as `perthis` and `pertarget`.

Therefore, the same application can have **hundreds of prototype target beans** yet only **one singleton aspect instance** observing calls through proxies. Conversely, a `pertarget` aspect can own separate state instances for each matched target, even if you do not change how targets are created via `@Scope`.

This lesson focuses on **Spring Framework and proxy-based Spring AOP**: how the two mechanisms cooperate, how to configure them properly, and misconceptions that cause bugs. It does not expand into standalone weaving models outside Spring.

### Learning Objectives

After this lesson, you can:
1. Distinguish *bean definition / bean scope / Spring AOP proxy / target object / aspect instance*.
2. Explain why `@Scope("prototype")` on a service does not automatically create one aspect per service, and why `@Scope("prototype")` on an aspect is not enough by itself to express `perthis` or `pertarget`.
3. Choose the default `@Aspect` or `@Aspect("perthis(...)")` / `@Aspect("pertarget(...)")` based on state requirements.
4. Run a Java 17 example with Spring to verify the instance counts of targets and aspects.
5. Recognize tricky interactions between Spring scoped proxies, web bean lifecycles, and calls through AOP proxies.

## 2. Comparison Table: Spring Bean Scope vs. Aspect Instantiation

| Criterion | Spring bean scope | Aspect instantiation model in Spring AOP |
| --- | --- | --- |
| Primary configuration | `@Scope`, `@RequestScope`, `@SessionScope`, or scope of `@Bean` | `@Aspect` and the per-clause value inside `@Aspect("...")` |
| Managed object | Bean definitions managed by Spring IoC, including services, repositories, aspect beans | Instances **of an aspect** used by the advice framework |
| Default rule | `singleton`: one bean instance per bean definition in the container | `@Aspect` without arguments: singleton instantiation model, typically one aspect instance in the context |
| Instance multiplication | `prototype`: each time the container supplies a new bean, there is typically a new instance | `perthis`: per `this` object at a matching join point; `pertarget`: per target object at a matching join point |
| Lifecycle attachment unit | Context/bean lookup; or request, session, custom scope | Proxy/target involved in the call and **the aspect-creating pointcut condition** |
| Application condition | Valid bean definition and registered scope | AOP enabled; aspect registered as a Spring bean; advisor/pointcut has matching calls **through a proxy** |
| Creation timing | Follows bean initialization: singleton usually eager, prototype created on demand, web scope per request/session | Singleton aspect follows bean lifecycle; `perthis`/`pertarget` instantiates when the first matching join point occurs |
| What is shared? | Depends on each bean's scope, not directly dependent on AOP annotations on the target | Depends on the per-clause, not equal to the target's scope by default |
| Relationship to proxies | Scoped proxies can help inject shorter-lived beans into longer-lived beans | AOP proxies intercept method executions and invoke advice before/after the target |

**The word “singleton” does not equate every object:**
- A Spring singleton bean means **one instance per bean definition within a container**, not a single Java instance across the entire JVM.
- The default singleton aspect is the Spring AOP rule of using one shared aspect instance in the context to execute that aspect's advice. It can advise many beans, many methods, many calls, and many threads.
- If there are multiple `ApplicationContext`s or multiple distinct bean definitions, do not infer there is only one aspect instance across the entire application.

### Four Objects to View Separately

```text
ApplicationContext
│
├── Bean definition: auditAspect
│     └── aspect instance (usually singleton)
│                  │
│                  └── Spring AOP advice / advisor
│
├── Bean definition: orderService [scope=prototype]
│     ├── target instance #1 ──> Spring AOP proxy #1
│     └── target instance #2 ──> Spring AOP proxy #2
│
└── Client:
      service1.call() ──> proxy #1 ──> advice on aspect ──> target #1
      service2.call() ──> proxy #2 ──> advice on aspect ──> target #2
```

Here, proxies and targets are separate objects. Both calls can pass through **the same instance of the singleton aspect**, even though the two targets are two prototype instances. Do not count proxies and conclude the number of aspect instances.

## 3. How Does Bean Scope Affect a Bean Advised by Spring AOP?

### 3.1. `singleton` Target

Example service definition:

```java
@Bean
public OrderService orderService() {
    return new OrderService();
}
```

The bean has the default `singleton` scope. With one context and one bean definition:
- Repeated `context.getBean("orderService")` calls typically receive the same Spring-managed bean reference. If Spring AOP requires a proxy, that reference may be **the same singleton proxy**.
- All `public` calls matching the pointcut and passing through the proxy can use the same singleton aspect instance.
- Each call does not recreate the service or aspect by default.

Note: a Spring proxy is not proof that all logic inside the object has become immutable or thread-safe. Both singleton targets and singleton aspects can be accessed by multiple threads.

### 3.2. `prototype` Target

If declared:

```java
@Bean
@Scope("prototype")
public OrderService orderService() {
    return new OrderService();
}
```

each time **BeanFactory is asked to supply the bean**, a new target instance is created. If matching advice exists, Spring processes it and returns a proxy corresponding to that created bean. However:
- **A singleton aspect can still be the exact same instance** shared across all prototype targets.
- If a prototype is injected into a singleton's constructor, normal injection only happens when the singleton is created; the singleton retains that reference for subsequent calls. To obtain a new prototype at runtime, consider `ObjectProvider<OrderService>` or method injection.
- Calling multiple times through *one* retrieved prototype reference does not make Spring automatically supply a new target on each method invocation. Do not confuse this with `@Scope(proxyMode = ...)` or a provider fetching a bean each time.

### 3.3. `request`, `session`, and Scoped Proxies

`request` or `session` beans belong to the scope of a web-aware `ApplicationContext`. Example:

```java
@RequestScope
@Component
public class RequestMetadata {
    // A target bean per HTTP request in a Spring web context.
}
```

When needing to inject a request-lived bean into a singleton, Spring typically uses a **scoped proxy** to look up the target corresponding to the current request. A scoped proxy solves the problem of *bean reference and lifecycle*, whereas an AOP proxy solves the problem of *applying advice to method calls*. Both proxy types can appear in a single call path while serving different purposes.

**Do not automatically assume** that for every HTTP request Spring creates a new aspect. If the aspect is using the singleton model, it can still observe many requests with one instance. If the application needs per-request data, obtain it from method arguments, appropriate request-scoped dependencies, or the call context, rather than placing per-request data into shared mutable fields of a singleton aspect.

## 4. How Spring AOP Creates Aspect Instances

### 4.1. Default: `@Aspect` Has the Singleton Instantiation Model

```java
@Aspect
@Component
public class AuditAspect {
    @Before("execution(* com.example.service..*.*(..))")
    public void audit() {
        // Runs for beans/methods matching the pointcut,
        // but does not create a new aspect instance per matching bean.
    }
}
```

`@Component` is how the class is registered as a Spring bean. `@Aspect` describes advice/pointcuts for Spring to parse when AOP is enabled (e.g., via `@EnableAspectJAutoProxy` or Spring Boot AOP auto-configuration). `@Aspect` alone **does not automatically register a bean**.

If the aspect bean uses the default `singleton` scope, one aspect instance will be used by the framework to handle matching calls across multiple targets/proxies. This is best suited for **stateless** aspects or those with shared state designed to be thread-safe (e.g., an `AtomicLong` counter).

**Pitfall:** an `int currentUserCalls` field in a singleton aspect can be updated concurrently by multiple threads and mix data across multiple users. When advice only needs to measure the duration of each call, a local variable inside `@Around` is usually more suitable than a field on the aspect.

### 4.2. `perthis`: One Aspect Instance per Matched `this` Object

With Spring AOP, the syntax:

```java
@Aspect("perthis(execution(* com.example.service..*.*(..)))")
@Component
@Scope("prototype")
public class PerProxyAuditAspect {
    @Before("execution(* com.example.service..*.*(..))")
    public void audit() {
        // State of the aspect instance is bound to the matching this.
    }
}
```

Meaning:
1. The `perthis(...)` clause is an **instantiation pointcut** identifying the first time a `this` object participates in a matching call.
2. When the first matching call occurs, Spring can create an aspect instance associated with that `this` object; advice on this instance continues to apply to corresponding join points.
3. In proxy-based Spring AOP, `this` in a pointcut refers to **the proxy object**. Therefore, `perthis` can be intuitively understood as per appropriate *proxy identity*.
4. Spring must be able to create multiple aspect instances; therefore, the aspect bean must have a non-singleton scope (the common pattern is `@Scope("prototype")`).

This is a **syntax illustration snippet**, assuming package `com.example.service` and related beans already exist and Spring AOP is enabled. Do not paste this snippet directly into the runnable example in Section 6 because the two examples demonstrate **two different instantiation modes**.

### 4.3. `pertarget`: One Aspect Instance per Matched Target Object

```java
@Aspect("pertarget(execution(* com.example.service..*.*(..)))")
@Component
@Scope("prototype")
public class PerTargetAuditAspect {
    @Before("execution(* com.example.service..*.*(..))")
    public void audit() {
        // Separate state for the matched target object.
    }
}
```

`pertarget` also relies on the first occurrence of a matching join point, but the key associating the aspect instance is the **target object** instead of `this`. With a single simple AOP proxy wrapping one fixed target, `perthis` and `pertarget` usually yield the same instance count. They differ in meaning when proxies and targets do not have a one-to-one relationship (e.g., dynamic target source configuration or scoped proxies), so **they must not be treated as two different names for the same bean scope**.

Be careful with the phrase “per target”: this means per **actual matched target object** in the AOP mechanism, not per method call, per bean name, per thread, or per HTTP request by default.

### 4.4. Table of Models and Support by Spring Version

| Syntax | Unit of aspect instance | Notes in Spring AOP |
| --- | --- | --- |
| `@Aspect` | Default singleton in context | Suitable for stateless cross-cutting logic and most common. |
| `@Aspect("perthis(<pointcut>)")` | Per `this` of matched join point (Spring proxy) | Requires aspect bean with a scope that can supply new instances, e.g., `prototype`. |
| `@Aspect("pertarget(<pointcut>)")` | Per target object of matched join point | Requires non-singleton aspect bean such as `prototype`. |
| `@Aspect("pertypewithin(<type-pattern>)")` | Per matching type | **Version-dependent:** recent Spring Framework docs list support, while older versions' docs did not support it. Must verify the exact Spring version in use before applying. |
| `percflow(...)` / `percflowbelow(...)` | Per control flow in AspectJ | Not supported in proxy-based Spring AOP; consider other mechanisms if genuinely needed. |

The runnable example in this lesson uses **Spring Framework 6.1.14** and only demonstrates the singleton aspect model, which is reliably compatible with this version. `perthis` and `pertarget` are models described in Spring 6.1 documentation; `pertypewithin` has changed support status across documentation generations, so practical exercises are not built upon it.

### Why Is `@Scope("prototype")` on an Aspect Not Equivalent to `perthis`?

This is a particularly important point:

- `@Scope("prototype")` tells **Spring BeanFactory** that when asked to supply a bean for this definition, it may supply a new instance.
- `@Aspect("perthis(...)")` or `@Aspect("pertarget(...)")` tells **Spring AOP** when to associate a new aspect instance with which object.
- With per-instance aspects, the two configurations work together: AOP defines the association rule, and BeanFactory provides an instance whenever needed.

Merely changing to:

```java
@Aspect
@Component
@Scope("prototype")
public class SomeAspect {
    // Does not declare perthis/pertarget.
}
```

**does not mean** Spring will automatically infer “one aspect per target” or “one aspect per call”. This is still the **singleton instantiation model** because `@Aspect` has no per-clause. When needing to quantify actual instance counts, you must understand how Spring uses the aspect instance factory per version and verify at runtime, rather than guessing from the scope name.

In the opposite direction, declaring `@Aspect("pertarget(...)")` while leaving the aspect bean as default singleton is also an **invalid configuration**: Spring needs the ability to create independent aspect instances and may throw an error when detecting a singleton bean with a non-singleton instantiation model. The safe pattern is pairing the per-clause with `@Scope("prototype")`.

## 5. Scenario Matrix: Target Scope Does Not Dictate Aspect Model

Assuming all beans are created by Spring, Spring AOP is enabled, the pointcut matches public calls through proxies, and there are no unusual proxies/target sources:

| Target bean | Aspect bean / instantiation | Observed target instance count | Aspect instance count used for targets |
| --- | --- | --- | --- |
| Singleton | `@Aspect` + singleton aspect bean | One target per bean definition | One shared singleton aspect instance for matching calls |
| Prototype | `@Aspect` + singleton aspect bean | Multiple targets across multiple `getBean` calls | **Still** one shared aspect instance in the context |
| Two different singleton bean definitions | `@Aspect` + singleton aspect bean | Each definition has its own target | One aspect instance can advise both if the pointcut matches |
| Prototype | `@Aspect("perthis(...)")` + prototype aspect bean | Multiple separate targets/proxies | One aspect instance per matching proxy, not necessarily per call |
| Prototype | `@Aspect("pertarget(...)")` + prototype aspect bean | Multiple separate targets | One aspect instance per matching target |
| Request/session with scoped proxy | `@Aspect` + singleton aspect bean | Target changes per runtime scope | Aspect can still be shared across requests/sessions |
| Request/session with scoped proxy | `perthis` or `pertarget` | Proxy and target may have different lifecycles | Must inspect proxy identity, target source, and pointcut; do not infer from HTTP scope |

The instance counts in the last column are **model-level**: an aspect matching no methods will not necessarily have the same initialization behavior as when matching join points occur; actual results also depend on scope, proxy, and lifecycle configuration.

## 6. Runnable Example: Two Prototype Targets and One Singleton Aspect

To clearly see the two independent mechanisms, we build a **plain Spring Framework** application without a web server. The example uses:
- Java 17+;
- Spring Framework `6.1.14`;
- `spring-context` and `spring-aop`;
- AspectJ Weaver on the classpath so Spring parses the expression in `@Before`.

### 6.1. Project Structure and Gradle

```text
spring-aop-scope/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/aop/
    ├── ScopeDemo.java
    ├── JobService.java
    └── AuditAspect.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-scope'
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
    mainClass = 'demo.aop.ScopeDemo'
}
```

### 6.2. Target Service with a Distinct ID per Instance

`src/main/java/demo/aop/JobService.java`:

```java
package demo.aop;

import java.util.concurrent.atomic.AtomicInteger;

public class JobService {
    private static final AtomicInteger NEXT_ID = new AtomicInteger();
    private final int id = NEXT_ID.incrementAndGet();

    public void run(String name) {
        System.out.println("target#" + id + ":" + name);
    }
}
```

The `NEXT_ID` variable is a tool for observing **the number of `JobService` instances**, not an aspect variable. With two `getBean(JobService.class)` calls on a `prototype` definition, two targets are created separately and receive `id` values `1` and `2` respectively in this program.

### 6.3. Singleton Aspect with a Shared Call Counter

`src/main/java/demo/aop/AuditAspect.java`:

```java
package demo.aop;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Before("execution(public void demo.aop.JobService.run(String))")
    public void beforeRun() {
        int value = calls.incrementAndGet();
        System.out.println("advice#" + value);
    }

    public int count() {
        return calls.get();
    }
}
```

Spring reads `@Aspect` to create the advisor. `AuditAspect` will be registered as a singleton bean in config, so **the same aspect object** increments the counter when the two prototype services run. `AtomicInteger` makes incrementing thread-safe; the example still runs sequentially so stdout is deterministic. `count()` helps verify that the aspect retains cumulative state.

### 6.4. Bootstrapping the Spring Context and Comparing Instances

`src/main/java/demo/aop/ScopeDemo.java`:

```java
package demo.aop;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Scope;

public class ScopeDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class Config {

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public JobService jobService() {
            return new JobService();
        }

        @Bean
        public AuditAspect auditAspect() {
            return new AuditAspect();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JobService first = context.getBean(JobService.class);
            JobService second = context.getBean(JobService.class);

            AuditAspect one = context.getBean(AuditAspect.class);
            AuditAspect two = context.getBean(AuditAspect.class);

            System.out.println("differentTargets=" + (first != second));
            System.out.println("sameAspect=" + (one == two));
            System.out.println("firstProxied=" + AopUtils.isAopProxy(first));
            System.out.println("secondProxied=" + AopUtils.isAopProxy(second));

            first.run("alpha");
            second.run("beta");

            System.out.println("adviceCount=" + one.count());
        }
    }
}
```

**Configuration explanation:**
1. `@EnableAspectJAutoProxy(proxyTargetClass = true)` enables the Spring AOP mechanism and prefers class-based proxies, so proxies can be retrieved by type `JobService`.
2. `@Bean @Scope(PROTOTYPE)` makes each `context.getBean(JobService.class)` call create a distinct service.
3. `@Bean AuditAspect` has no `@Scope`, so it is a singleton bean by default. `@Aspect` on the class specifies the singleton aspect instantiation model.
4. `@Before` applies to `JobService.run(String)` when calls pass through a proxy. Both proxies use the same aspect bean.
5. `AopUtils.isAopProxy` distinguishes beans returned by Spring from raw targets. The `first != second` test checks the returned bean references; the IDs in `run` show the underlying targets are genuinely different.

### 6.5. Run Command and Expected Output

In the project directory, using a Gradle installation that can run the project:

```bash
gradle run
```

If a Gradle Wrapper has been generated in the project, you can use `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows).

The lines printed by **the Java program** (ignoring Gradle or environment banners/logs):

```text
differentTargets=true
sameAspect=true
firstProxied=true
secondProxied=true
advice#1
target#1:alpha
advice#2
target#2:beta
adviceCount=2
```

Observations:
- `differentTargets=true`: two prototype bean requests create two separate Spring-managed instances.
- `sameAspect=true`: two requests for the singleton aspect receive the exact same reference.
- Both `firstProxied=true` and `secondProxied=true`: prototype targets can also be Spring AOP proxied.
- The advice counter increments `1 → 2` **on the same aspect instance**, without resetting to `1` when switching to the second target.
- Advice runs *before* the target because it is `@Before`. If using `@Around` with `proceed()`, log order depends on the surrounding logic written.

This is concrete evidence for the conclusion that **“prototype target” does not mean “pertarget aspect”**.

## 7. Configuring an Aspect Bound to Targets: Two Cooperating Mechanisms

If the business requirement genuinely needs **separate state per target**, Spring AOP supports `@Aspect("pertarget(...)")`. The aspect's bean definition must allow Spring to supply multiple instances, usually via `prototype`; changing only the scope or adding only the per-clause individually is insufficient to get the right model.

```java
@Aspect("pertarget(execution(public void demo.aop.JobService.run(String)))")
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class PerTargetAuditAspect {
    @Before("execution(public void demo.aop.JobService.run(String))")
    public void beforeRun() {
        // Advice belonging to the aspect instance associated with the corresponding target.
    }
}
```

The snippet above **illustrates configuration**, needing imports and proper component scan; do not paste it into the singleton demo in Section 6. If registering the aspect via a `@Bean` method instead of `@Component`, place `@Scope(PROTOTYPE)` on the corresponding bean definition. With `perthis(...)`, Spring AOP associates instances by **proxy** instead of target. The next lesson practices all three models (`singleton`, `perthis`, `pertarget`) and how to observe object identities.

A per-clause by proxy/target is **not** a request scope or thread-local: multiple concurrent calls on the same target can still use the same aspect instance. When only per-request data is needed, prefer advice parameters or an appropriately scoped collaborator.

## 8. Common Misconceptions in Spring

| Incorrect statement | Why it is wrong | Correct understanding |
| --- | --- | --- |
| “Because the service is `prototype`, each service has its own aspect.” | Target bean scope and aspect instantiation are two axes. | A default `@Aspect` aspect can be shared across many prototype targets. |
| “`@Aspect` is a bean even without any registration.” | `@Aspect` is not a component-registration annotation. | Register the aspect via `@Component`, `@Bean`, or equivalent. |
| “`@Scope("prototype")` on an aspect means one aspect per method call.” | Scope only dictates how BeanFactory supplies beans per bean creation request; it does not express a per-method AOP rule. | Use the proper per-clause if you want instances bound to proxies/targets. |
| “`@Aspect("pertarget(...)")` alone is enough.” | The per-target instance model requires a non-singleton aspect bean. | Combine with a scope allowing multiple aspect instances, usually `prototype`. |
| “Having two singleton bean definitions of the same class yields only one object.” | Spring singleton is **per bean definition**, not per class in the JVM. | Two definitions can have two independent instances. |
| “Two HTTP requests always have two aspects.” | The HTTP request scope of the **target** does not dictate the aspect instance. | Check the aspect's model and scoped proxy configuration. |
| “A singleton aspect with a counter field is automatically safe under concurrency.” | Multiple threads can concurrently share one aspect. | Keep the aspect stateless or use synchronized/thread-safe data as needed. |
| “`@Lazy` turns a singleton into a prototype.” | `@Lazy` changes creation timing, not scope. | Scope remains singleton unless configured otherwise. |
| “AOP proxies and scoped proxies are always the same thing.” | One proxy intercepts advice; the other represents a scoped bean and selects targets. | Identify both proxy layers when debugging. |
| “Calling `this.run()` inside the target still goes through advice.” | Self-invocation normally bypasses Spring AOP proxies. | Call through the Spring proxy externally or redesign boundaries. |
| “`perthis` also means per thread.” | Spring AOP's `this` is the proxy at the join point, not the thread. | Choose the instance model by object, not by concurrency assumptions. |

### Why Do Scoped Proxies Make `perthis` and `pertarget` More Complex?

Take a `request` bean injected into a singleton via **a scoped proxy**. The singleton normally holds the same **proxy reference**, while the scoped proxy can select **different targets depending on the request**.

In that configuration:
- If a `perthis` pointcut sees the same proxy identity, one cannot assume there is a new aspect instance per request merely because the request target changes.
- `pertarget` is defined by the target object of the join point, yet specific interactions with multi-proxy chains and target sources must be verified on the exact runtime/version.
- `@RequestScope` or `@Scope(proxyMode = ...)` solves lifecycle and lookup; they are **not syntactic substitutes** for `@Aspect("perthis(...)")` or `@Aspect("pertarget(...)")`.

Therefore, when logic needs to process request data, the durable solution is usually **moving request state into an explicit request-scoped bean** or passing information into advice via `JoinPoint`/parameters, rather than relying on “the aspect will surely have as many instances as requests”.

## 9. Checklist for Diagnosing Runtime Instance Counts

When observing unexpected aspect/service behavior:

1. **Identify bean definitions**: is the service registered via `@Component` or `@Bean`? Are there multiple definitions for the same class? Are there parent–child contexts?
2. **Check bean scope**: `singleton`, `prototype`, `request`, `session`? If injecting a prototype into a singleton, when is the prototype supplied?
3. **Check the aspect bean**: has Spring registered it yet, what is its scope, and has AOP infrastructure discovered it?
4. **Check the per-clause**: default `@Aspect`, `perthis`, `pertarget`, or syntax unsupported by the current version?
5. **Check proxy and target**: `AopUtils.isAopProxy(bean)`, `AopUtils.isJdkDynamicProxy(bean)`, `AopUtils.isCglibProxy(bean)`; check whether there is an additional scoped proxy or dynamic `TargetSource`.
6. **Check the call**: does the client obtain the bean from the context and call through the proxy? Does the pointcut match the actual method execution? Is there self-invocation?
7. **Check concurrent state**: does the advice use shared mutable fields? Does a counter need `AtomicInteger`/`AtomicLong` or should state be avoided?
8. **Read startup errors**: if a per-clause needs multiple aspect instances while the bean is configured as singleton, fix the scope/model root cause; do not disable AOP just to silence the error.

Example proxy check snippet (assuming `service` is an existing Spring bean variable, not a standalone runnable program):

```java
System.out.println(AopUtils.isAopProxy(service));
System.out.println(AopUtils.isJdkDynamicProxy(service));
System.out.println(AopUtils.isCglibProxy(service));
```

These three values describe **the proxy object**, which is not enough to conclude the aspect instance count. To check aspects, cross-reference bean definitions/aspect scopes and trace instance identity when needed.

## 10. Conclusions and Design Principles

In Spring, two steps must be kept distinct:

```text
Spring IoC:
  Bean definition + @Scope
        -> creates, provides, manages target bean / aspect bean by scope

Spring AOP:
  @Aspect + per-clause + pointcut + advice
        -> selects matching proxy/target, associates aspect instance,
           executes advice when method is invoked through Spring proxy
```

**Practical rule:** Choose bean scope by the lifecycle of dependencies/targets; choose aspect instantiation model by *the lifecycle of advice state*. For most Spring AOP use cases like logging, metrics, and boundary checks, use a singleton aspect holding no per-call state. Only use `perthis`/`pertarget` when state tied to proxy/target identity is genuinely needed and has been verified in a real Spring proxy context.

### Reference Documentation

- [Spring Framework — Aspect Instantiation Models](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html): singleton, `perthis`, `pertarget` models and version-dependent support.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): `singleton`, `prototype`, web scopes, dependencies, and scoped proxies.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): enabling Spring AOP, registering aspects, and dependency requirements.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxies, `this`/target, and self-invocation.
- [Spring Framework 6.1 — BeanFactoryAspectJAdvisorsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/aop/aspectj/annotation/BeanFactoryAspectJAdvisorsBuilder.html): how Spring finds `@Aspect` beans and builds advisors.
