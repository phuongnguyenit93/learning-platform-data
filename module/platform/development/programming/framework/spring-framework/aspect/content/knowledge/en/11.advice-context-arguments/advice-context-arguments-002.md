# getThis() and getTarget(): Distinguishing the Spring AOP Proxy from the Target Object

## 1. The core question inside an @Aspect

In a Spring `@Aspect`, when a method is invoked through a proxy, we may be looking at **two different Java objects**:

1. **Spring AOP proxy**: the object that the client obtains from `ApplicationContext` or that is injected into another bean. It receives the call, looks up the matching advisors/interceptors, and coordinates execution.
2. **Target object**: the real object containing the business logic, to which the proxy delegates the call after running the necessary advice.

Spring provides two APIs on `JoinPoint`/`ProceedingJoinPoint`:

- **`joinPoint.getThis()` returns the current Spring AOP proxy.**
- **`joinPoint.getTarget()` returns the current Spring AOP target**, i.e. the object behind the proxy (in special cases where a proxy has no target, the result can be `null`).

These are not merely two ways to get a class name. They have **different identity, runtime class, interface exposure, and method invocation paths**. Choosing the wrong one can lead to logging the wrong type, failed casts, calls bypassing aspects, or even accidentally invoking advice recursively.

Visualizing example:

```text
ApplicationContext
      |
      v
 Spring AOP proxy  <-------------  joinPoint.getThis()
      |
      |  Advisor A -> Advisor B -> ...
      |
      v
 Business target   <-------------  joinPoint.getTarget()
      |
      v
 Method implementation
```

**Lesson scope:** `getThis()`/`getTarget()` and their meaning **in proxy-based Spring AOP**, especially when using `@Aspect` with Spring Framework. We do not extend into standalone AspectJ compiler/weaver semantics, because Spring's use of proxies is precisely what creates the important distinction between these two objects.

### After this lesson, you will

- Understand `this`, `target`, and the objects Spring AOP uses when intercepting a method.
- Distinguish `getThis()`/`getTarget()` from the Java `this` keyword inside the target and inside the aspect.
- Predict results with a JDK dynamic proxy versus a class-based CGLIB proxy.
- Understand `this(TypePattern)` and `target(TypePattern)` in Spring pointcuts.
- Know why you should **not use `getTarget()` and call a method to "proceed"**, and why calling through `getThis()` inside advice risks recursion.
- Run a Java 17/Spring Framework example yourself with two separate contexts and observable output.
- Diagnose self-invocation, proxy casting, targetless proxies, and dynamic target sources without making false assumptions about identity.

## 2. Spring AOP mechanism: client calls proxy, proxy calls target

A Spring bean may be instantiated first as a target, and then a `BeanPostProcessor` belonging to the auto-proxy creator infrastructure decides whether to return a proxy instead of the target when the bean is exposed through the container.

When a bean needs advice:

```text
Caller
   |
   | injected JobApi bean
   v
Proxy [identity P]
   |
   | interceptor chain
   v
Target JobService [identity T]
   |
   | execute perform("A")
   v
Return
```

Normally, `P !== T` in terms of **reference identity (`==` in Java)**. The proxy stands in for the target in front of the caller, but it is not the target itself. Two objects may have custom `equals`/`hashCode` implementations; when studying AOP boundaries, use `==` rather than `equals` to compare identity.

### Different roles

| Property | `getThis()` | `getTarget()` |
| --- | --- | --- |
| What does it return in Spring AOP? | Current proxy | Current target behind the proxy |
| Calling a method via this reference | Can pass through the Spring AOP advisor chain | Calls directly on the target, bypassing that proxy's advisors |
| Typical runtime class | JDK-generated proxy or CGLIB subclass | Actual implementation class |
| Same as `context.getBean(...)`? | In typical Spring proxy cases, it is the proxy reference the client uses | Usually not, when the bean is proxied |
| Can it be `null`? | No for Spring AOP's `MethodInvocationProceedingJoinPoint` | Yes when the proxy has no target object |
| Always castable to implementation class? | **No** for JDK proxies | Usually the target implementation instance if a target exists |
| Always a permanently fixed singleton? | Should not be assumed outside a specific bean/proxy configuration | No: target sources/scopes can swap the target per invocation |
| Used to continue current `@Around`? | Not the chain-continuation API | Not the chain-continuation API |
| Correct API to continue `@Around` | **`ProceedingJoinPoint.proceed()`** | **`ProceedingJoinPoint.proceed()`** |

Spring explicitly documents that `getThis()` returns the proxy and `getTarget()` returns the target POJO behind the proxy, which does not carry the proxy's advice on that reference. In `@Around`, to continue the current invocation, **`proceed()` is the right method**.

## 3. getThis() is not synonymous with Java `this` of the target or aspect

There are three `this` contexts that are easy to confuse:

### 3.1. `this` inside an `@Aspect` class

```java
@Aspect
public class InspectAspect {

    @Around("execution(* com.example.service..*.*(..))")
    public Object inspect(ProceedingJoinPoint pjp) throws Throwable {
        Object aspectInstance = this;
        Object proxy = pjp.getThis();
        Object target = pjp.getTarget();

        System.out.println(aspectInstance == proxy); // usually false
        System.out.println(proxy == target);         // usually false
        return pjp.proceed();
    }
}
```

This is an illustrative snippet; it requires imports, Spring bean registration, and a matching target. `this` in the source of `InspectAspect` is the **aspect instance**. `pjp.getThis()` is the **proxy of the advised Spring bean**. These two objects serve completely different roles.

### 3.2. `this` inside the target implementation

```java
public class JobService {
    public void outer() {
        this.inner();
    }

    public void inner() {
        System.out.println("inner");
    }
}
```

Once `outer()` has been dispatched by the proxy to the target, `this` inside `JobService.outer()` points to the **target object**. Calling `this.inner()` **does not go back through the Spring proxy**, so advice intended specifically for `inner()` does not run automatically.

### 3.3. `this` in a Spring pointcut expression

```java
@Pointcut("this(com.example.api.JobApi)")
public void proxyImplementsJobApi() {}
```

The `this(TypePattern)` designator evaluates the **proxy object** in Spring AOP, not the Java `this` variable inside the aspect source. `target(TypePattern)` evaluates the **target object**. Section 6 goes deeper into this difference.

## 4. JDK dynamic proxy: proxy and implementation have different types

When the target implements a suitable interface and Spring is not forced to use class-based proxies, Spring AOP typically creates a **JDK dynamic proxy**.

Example:

```java
package demo.identity;

public interface JobApi {
    String perform(String id);
}
```

```java
package demo.identity;

public class JobService implements JobApi {
    @Override
    public String perform(String id) {
        return "done:" + id;
    }
}
```

The bean is injected via `JobApi`. With a JDK proxy:
- `getThis() instanceof JobApi` is `true`.
- `getThis() instanceof JobService` is `false`: a JDK proxy implements the interface but **is not a subclass of `JobService`**.
- `getTarget() instanceof JobService` is `true` if the target is `JobService`.
- `getThis() == getTarget()` is typically `false`.
- Even though the proxy is not an instance of the implementation, a Spring pointcut can still match execution of the appropriate target method.

A real-world mistake:

```java
JobService service = (JobService) context.getBean(JobApi.class);
```

If the actual bean is a JDK proxy, the cast above can throw `ClassCastException`. That is not a bug in `getTarget()`; it happens because **the client is casting the proxy to the implementation**. Normal practice is to inject/retrieve the bean by the **`JobApi` interface** or revisit why a class-based proxy is needed.

### JDK proxies only expose methods through the appropriate interface

If the implementation has an extra method `internalOnly()` not declared on the proxied interface, clients cannot call that method via a `JobApi` reference. Do not use `getTarget()` as a workaround to call non-interface methods while still expecting Spring advice to run. If business logic requires a method to be advised, design the service contract and proxy boundary accordingly.

## 5. CGLIB class-based proxy: instanceof matches, yet identity still differs

If the target has no interface, or `proxyTargetClass=true` forces class-based proxying, Spring typically uses **CGLIB** to generate a subclass of the implementation.

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfiguration {
}
```

This is a configuration snippet, not a standalone application. When `JobService` is Spring AOP class-proxied:
- `getThis() instanceof JobApi` is `true` if the implementation has that interface.
- `getThis() instanceof JobService` is also `true` because the CGLIB proxy is a subclass.
- `getTarget() instanceof JobService` is `true`.
- **`getThis() == getTarget()` is still typically `false`**: inheritance does not make the proxy and target the same object.
- `getThis().getClass()` can return a CGLIB-generated class; `getTarget().getClass()` returns the implementation class.

Because `getThis() instanceof JobService` is true with CGLIB, learners easily conclude that `getThis()` and `getTarget()` are the same object. That conclusion is wrong: **`instanceof` checks type relationships, whereas `==` checks identity**.

### Class-based proxy limitations

CGLIB must create a subclass to override methods. It cannot advise via overriding for:
- `final` classes;
- `final` methods;
- `private` methods;
- certain methods not visible for subclass overriding.

Furthermore, self-invocation from the target still bypasses Spring AOP even when the proxy is CGLIB. Switching from JDK proxy to CGLIB **is not a fix** for the `this.inner()` problem.

## 6. this(TypePattern) vs. target(TypePattern) in Spring pointcuts

Spring Framework clearly distinguishes between **proxy** and **target**:

- `this(TypePattern)`: matches when the **proxy** is an instance of the specified type.
- `target(TypePattern)`: matches when the **target object** is an instance of the specified type.

### 6.1. With an interface

```java
@Pointcut("this(demo.identity.JobApi)")
public void proxyIsJobApi() {}

@Pointcut("target(demo.identity.JobApi)")
public void targetIsJobApi() {}
```

When the target `JobService implements JobApi` and the proxy implements `JobApi`, both usually match. Do not use this example to prove they are equivalent **in every configuration**.

### 6.2. With an implementation class

```java
@Pointcut("this(demo.identity.JobService)")
public void proxyIsJobService() {}

@Pointcut("target(demo.identity.JobService)")
public void targetIsJobService() {}
```

With a **JDK proxy**:
- `this(JobService)` usually does not match because the proxy does not subclass `JobService`.
- `target(JobService)` can match because the target itself is `JobService`.

With a **CGLIB proxy**:
- Both `this(JobService)` and `target(JobService)` usually match because the proxy is a subclass and the target is an implementation instance.

### 6.3. Quick matrix

Assume the target is `JobService implements JobApi` with a Spring AOP proxy as described:

| Question / condition | JDK proxy | CGLIB proxy |
| --- | --- | --- |
| `getThis() instanceof JobApi` | `true` | `true` |
| `getTarget() instanceof JobApi` | `true` | `true` |
| `getThis() instanceof JobService` | `false` | `true` |
| `getTarget() instanceof JobService` | `true` | `true` |
| `getThis() == getTarget()` | `false` | `false` |
| `this(JobService)` | Does not match | Can match |
| `target(JobService)` | Can match | Can match |
| `this(JobApi)` | Can match | Can match |
| `target(JobApi)` | Can match | Can match |

"Can match" in the pointcut rows also depends on whether the method is actually intercepted by Spring AOP, whether the type pattern is valid, and whether bean/advisor configuration is appropriate. The matrix describes the **type relationship of the two objects**, without claiming every call in Java gets advised.

### 6.4. When choosing a type pattern, avoid confusing with `@target`

`target(SomeType)` checks the target's type relationship. Meanwhile:
- `@target(MyAnnotation)` checks the **annotation** on the runtime target type.
- `@within(MyAnnotation)` checks the annotation on the declaring type of the method execution.
- `within(PackageOrTypePattern)` restricts by the type/package declaring the execution.
- `@annotation(MyAnnotation)` checks the method annotation.

These designators address different requirements. If you only want to log what kind of Spring bean is being advised, use `pjp.getTarget()` to inspect the object; if you want to constrain an advisor by target type, use `target(...)` per Spring pointcut semantics.

## 7. Complete runnable example: comparing JDK proxy and CGLIB in two contexts

The plain Spring Framework example below uses **Java 17**, **Spring Framework 6.1.14**, **AspectJ Weaver 1.9.22.1**, and Gradle. We create two separate `ApplicationContext` instances so that a `proxyTargetClass=true` setting in the CGLIB context does not affect the JDK context.

Goals:
- Print the proxy kind created by Spring (via `AopUtils`, rather than printing random generated class names).
- Inside `@Around` itself, compare `pjp.getThis()` and `pjp.getTarget()`.
- Check `instanceof JobService` for both proxy and target.
- Run one method called from outside and one method that calls another method inside the target.
- Observe that self-invocation does not trigger an extra nested advice.

### 7.1. Project structure

```text
spring-aop-proxy-identity/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/identity/
    ├── JobApi.java
    ├── JobService.java
    ├── InspectAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 7.2. Gradle configuration

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-proxy-identity'
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
    mainClass = 'demo.identity.DemoApplication'
}
```

`spring-context` provides `AnnotationConfigApplicationContext`; `spring-aop` contains the AOP proxy infrastructure, `AopUtils`, and interceptor integration; `aspectjweaver` enables Spring to parse `@Aspect` pointcut expressions.

### 7.3. Public interface

File `src/main/java/demo/identity/JobApi.java`:

```java
package demo.identity;

public interface JobApi {
    String perform(String task);
    void runInside();
}
```

Both `perform` and `runInside` are declared on the interface so a **JDK dynamic proxy** can expose both methods. In the CGLIB case, the proxy is also a subclass of the implementation.

### 7.4. Target implementation

File `src/main/java/demo/identity/JobService.java`:

```java
package demo.identity;

public class JobService implements JobApi {

    @Override
    public String perform(String task) {
        System.out.println("target:perform:" + task);
        return "done:" + task;
    }

    @Override
    public void runInside() {
        System.out.println("target:runInside");
        perform("inside");
    }
}
```

`perform("inside")` is an internal call on the target (`this.perform(...)`), not a call going back through the Spring proxy. Therefore, even though the pointcut can match the `perform` method, this call does not trigger `@Around` again.

### 7.5. Aspect inspecting proxy and target with ProceedingJoinPoint

File `src/main/java/demo/identity/InspectAspect.java`:

```java
package demo.identity;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.aop.support.AopUtils;

@Aspect
public class InspectAspect {

    @Around(
        "execution(public * demo.identity..*.perform(..))"
        + " || execution(public * demo.identity..*.runInside(..))"
    )
    public Object inspect(ProceedingJoinPoint pjp) throws Throwable {
        Object proxy = pjp.getThis();
        Object target = pjp.getTarget();

        System.out.println("aspect:" + pjp.getSignature().getName());
        System.out.println("proxyKind="
            + (AopUtils.isJdkDynamicProxy(proxy) ? "JDK" : "CGLIB"));
        System.out.println("sameObject=" + (proxy == target));
        System.out.println("proxyIsJobService="
            + (proxy instanceof JobService));
        System.out.println("targetIsJobService="
            + (target instanceof JobService));
        System.out.println("targetAopProxy="
            + AopUtils.isAopProxy(target));

        return pjp.proceed();
    }
}
```

**Detailed explanation:**
- `pjp.getThis()` is the proxy. `AopUtils.isJdkDynamicProxy(proxy)` lets us print stable **JDK** or **CGLIB** labels across the two test configurations; we avoid extracting strings from generated class names.
- `pjp.getTarget()` is the `JobService` target in the example, not another nested proxy.
- `sameObject=false` shows that the proxy and target do not share the same Java reference identity.
- `proxyIsJobService` differs between JDK and CGLIB: the JDK proxy does not inherit from the implementation; the CGLIB subclass satisfies `instanceof`.
- `targetIsJobService=true` in both cases because Spring uses `JobService` as the target.
- `targetAopProxy=false` because the target is a plain object in this example, not a Spring AOP proxy; do not treat this as an absolute rule for every custom nested-proxy setup.
- `return pjp.proceed();` is what **continues the current invocation**. We do not call `((JobService) target).perform(...)` directly, and we do not use `((JobApi) proxy).perform(...)` to replace `proceed()`.

The pointcut uses `execution(public * demo.identity..*.perform(..))` or `runInside(..)`; only methods with matching names and package/type are advised. Both methods on the same target are matched when the client invokes them through the proxy.

### 7.6. Two contexts configuring two proxy styles

File `src/main/java/demo/identity/AppConfig.java`:

```java
package demo.identity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class AppConfig {

    @Configuration(proxyBeanMethods = false)
    public static class CommonBeans {

        @Bean
        public JobApi jobService() {
            return new JobService();
        }

        @Bean
        public InspectAspect inspectAspect() {
            return new InspectAspect();
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
}
```

- `CommonBeans` registers `JobService` with return type `JobApi` and registers the aspect via `@Bean`. `@Aspect` alone does not cause Spring to create a bean for the class.
- `JdkConfig` enables Spring AOP with `proxyTargetClass=false`. Since the target implements `JobApi`, this standard setup uses a JDK dynamic proxy.
- `CglibConfig` forces class-based proxying with `proxyTargetClass=true`.
- The two contexts are created **separately** rather than importing both configs into one context. If multiple Spring infrastructure features request class-based proxying in a single context, setting `true` can dominate the shared choice.
- A `@Bean` method declaring return type `JobApi` still lets Spring retain the concrete `JobService` target to create a class-based proxy when needed. The client in the demo retrieves the bean by `JobApi.class`, which works in both contexts.

### 7.7. Main and run command

File `src/main/java/demo/identity/DemoApplication.java`:

```java
package demo.identity;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        run("JDK", AppConfig.JdkConfig.class);
        run("CGLIB", AppConfig.CglibConfig.class);
    }

    private static void run(String label, Class<?> config) {
        System.out.println("==" + label + "==");

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(config)) {

            JobApi bean = context.getBean(JobApi.class);
            System.out.println("isAopProxy=" + AopUtils.isAopProxy(bean));
            System.out.println("result=" + bean.perform("outside"));
            bean.runInside();
        }
    }
}
```

Run in the directory containing `build.gradle`:

```bash
gradle run
```

If Gradle Wrapper is present, run `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows.

### 7.8. Stdout from Java code

```text
==JDK==
isAopProxy=true
aspect:perform
proxyKind=JDK
sameObject=false
proxyIsJobService=false
targetIsJobService=true
targetAopProxy=false
target:perform:outside
result=done:outside
aspect:runInside
proxyKind=JDK
sameObject=false
proxyIsJobService=false
targetIsJobService=true
targetAopProxy=false
target:runInside
target:perform:inside
==CGLIB==
isAopProxy=true
aspect:perform
proxyKind=CGLIB
sameObject=false
proxyIsJobService=true
targetIsJobService=true
targetAopProxy=false
target:perform:outside
result=done:outside
aspect:runInside
proxyKind=CGLIB
sameObject=false
proxyIsJobService=true
targetIsJobService=true
targetAopProxy=false
target:runInside
target:perform:inside
```

These are the lines printed by the code itself, excluding Gradle output, system logging, or environment banners.

### 7.9. Explaining each result

**In the JDK branch:**

`isAopProxy=true` proves the reference from Spring is a proxy. `proxyKind=JDK` shows the proxy implements the interface rather than subclassing `JobService`. Therefore `proxyIsJobService=false` while `targetIsJobService=true`. Spring still runs the advice and then delegates to `JobService.perform("outside")`.

**In the CGLIB branch:**

`proxyKind=CGLIB` indicates a class-based proxy. `proxyIsJobService=true` thanks to inheritance, yet `sameObject=false`: the proxy and target are still two different objects. This is important to remember when checking code with `instanceof`.

**In both branches:**

`aspect:runInside` appears because the caller invokes `bean.runInside()` through the Spring proxy. Then `target:runInside` and `target:perform:inside` appear, **without a second `aspect:perform`**: the call `perform("inside")` originates inside the target and does not pass through the proxy.

If you only inspected target method logs without checking advice logs, you might think `perform` was advised twice. Separating the two log types in the output proves that is not actually the case.

## 8. Do not use `getTarget()` to continue a method in `@Around`

A serious mistake is using the target reference to call the method again yourself:

```java
@Around("execution(* demo.identity.JobService.perform(..))")
public Object broken(ProceedingJoinPoint pjp) {
    JobService target = (JobService) pjp.getTarget();
    return target.perform("manually");
}
```

This is an **illustrative anti-pattern**, not to be placed in a runnable project. This method skips `pjp.proceed()` and calls `target.perform` directly. Consequently:
- The invocation from the caller reached the advice, but **does not continue through inner interceptors**.
- If there are transaction, cache, security, tracing, or other advisors further inside, they can be bypassed.
- It replaces the argument with `"manually"`, potentially violating the method contract and business expectations.
- If there is a special target source or targetless proxy, casting or dereferencing can fail.

To keep the original flow:

```java
return pjp.proceed();
```

To intentionally change arguments:

```java
Object[] modified = pjp.getArgs().clone();
modified[0] = "normalized";
return pjp.proceed(modified);
```

In Spring AOP, `proceed(Object[])` takes method arguments matching the count, order, and types; there is no reason to invoke the target directly via reflection. This is an illustrative snippet inside `@Around` for a method taking at least one `String` parameter.

## 9. Be careful when calling back through `getThis()`

The Spring Javadoc notes: if you **want a call to be advised**, call through the proxy rather than calling the target directly. However, **that does not mean the right advice is to replace `proceed()` by calling the method on `pjp.getThis()` right inside the `@Around` advice itself**.

Dangerous example:

```java
@Around("execution(* demo.identity.JobService.perform(..))")
public Object recursive(ProceedingJoinPoint pjp) {
    JobApi proxy = (JobApi) pjp.getThis();
    return proxy.perform("again");
}
```

Calling `proxy.perform("again")` creates a **new** invocation passing through the same proxy. If the pointcut still matches, the advice runs again, calls the proxy again, and can create unbounded recursion ending in `StackOverflowError`.

`pjp.proceed()` is the API for continuing the **current invocation**; calling through the proxy is only appropriate when you genuinely need to initiate **a new call** from elsewhere and have designed against recursion/circular aspect behavior.

### Does `getThis()` require `exposeProxy=true`?

**No.** Inside an `@Aspect` method running under Spring AOP, `pjp.getThis()` supplies the current proxy as part of `JoinPoint`.

A different mechanism is:

```java
Object proxy = AopContext.currentProxy();
```

`AopContext.currentProxy()` accesses the proxy from a thread-local context and typically requires enabling `exposeProxy=true`; it introduces explicit coupling to Spring AOP and is not recommended as a routine way to design business logic. **Do not confuse the requirements of `AopContext.currentProxy()` with `pjp.getThis()`.**

## 10. `getTarget()` can be null or change per invocation

### 10.1. Targetless proxy

Spring AOP Javadoc permits `getTarget() == null` when there is no target instance. This is not the case for the service target in the demo, but it matters when a custom proxy/`TargetSource` provides no target.

Therefore, in logging or library infrastructure, avoid writing:

```java
String targetClass = pjp.getTarget().getClass().getName();
```

if you cannot guarantee a target exists. A safer diagnostic approach:

```java
Object target = pjp.getTarget();
String name = target != null
    ? target.getClass().getName()
    : "<no target>";
```

### 10.2. Scoped target and dynamic TargetSource

With special proxy configurations such as a scoped proxy or custom `TargetSource`, one proxy can represent **different target instances at different times**. For example, a request-scoped target can differ across requests, even though the dependency injected into a singleton service is a stable proxy.

Therefore:
- Do not cache `pjp.getTarget()` from the first invocation and treat it as a permanent target.
- Do not assume `getTarget()` always returns the same identity across all calls.
- Do not turn the target reference into a new Spring bean injected elsewhere.
- Be careful with object lifecycle/scopes: holding onto a raw target can extend a reference's lifetime beyond its intended scope.

**In the standard singleton demo**, the target is a stable `JobService`, but that is a property of the demo configuration, not a universal contract for every Spring proxy.

### 10.3. Nested/custom proxies

In systems that add custom `ProxyFactory`, custom `BeanPostProcessor`, or proxy layers from another library, the object immediately behind the outer proxy may **itself be another proxy**. In that case, a single `getTarget()` call is not guaranteed to return the "final business POJO".

`AopUtils.isAopProxy(target)` or `Advised` can help inspect the structure, but you must respect the target source lifecycle; do not repeatedly unwrap/cast inside business advice. For typical type logging, Spring utilities can be used to determine the target class, yet **reading type metadata is not equivalent to grabbing the target object and invoking it directly**.

## 11. Observing class, bean name, and method signature properly

### 11.1. The proxy's class is not the business class

`pjp.getThis().getClass().getName()` can produce generated JDK or CGLIB class names that vary by version and runtime. Do not use substrings of generated class names for business conditions.

To inspect the proxy type:

```java
Object proxy = pjp.getThis();

boolean jdk = AopUtils.isJdkDynamicProxy(proxy);
boolean cglib = AopUtils.isCglibProxy(proxy);
Class<?> targetClass = AopUtils.getTargetClass(proxy);
```

This is a snippet inside advice requiring `import org.springframework.aop.support.AopUtils`. `getTargetClass` returns **type metadata** from the proxy when available, not the business target object; `pjp.getTarget()` is what returns the target object at the join point.

### 11.2. `getSignature()` to identify the method

```java
String methodName = pjp.getSignature().getName();
```

When you need the return type, parameter types, or method annotations, you can use:

```java
import org.aspectj.lang.reflect.MethodSignature;

MethodSignature sig = (MethodSignature) pjp.getSignature();
Class<?> returnType = sig.getReturnType();
Class<?>[] parameterTypes = sig.getParameterTypes();
```

These are snippets inside Spring `@Around` method-execution advice. With a JDK proxy, the described method may belong to the interface declaration while the implementation method has different metadata. When reading annotations on the implementation, resolve the specific method on the target type using the appropriate utility and verify with tests.

### 11.3. `getArgs()` is not `getTarget()`

`pjp.getArgs()` returns the **actual arguments** of the invocation, not the target bean. In the `perform("outside")` example, `getArgs()[0]` is the string `"outside"`. Do not confuse the Spring proxy's "target object" with the "argument objects" passed into the method.

### 11.4. `getThis()` is not the Spring bean name either

`getThis()` returns a proxy reference, not a bean name. One target class can be registered under multiple Spring bean definitions or with aliases. If business logic needs to categorize by Spring bean name, consider Spring AOP's `bean(namePattern)` pointcut or appropriate bean metadata APIs; do not guess the bean name from the proxy's generated class.

## 12. Impact on transactions, caching, and other advice

A service method may be wrapped by multiple advisors: `@Aspect` logging, Spring transactions, and caching. Keep two things clear:

1. **The proxy** receives the call from the client and orchestrates the entire chain.
2. **The target** executes the business method once the chain reaches it.

Example:

```text
Caller
  |
  v
Spring AOP proxy (getThis)
  |
  +-- Audit @Around
  +-- TransactionInterceptor
  +-- CacheInterceptor
  |
  v
Service target (getTarget)
```

This is an **illustrative order** diagram, not a mandatory default precedence.

If you call `pjp.getTarget().perform(...)` directly inside logging advice, inner transaction/cache advisors can be skipped. If you call `pjp.proceed()`, the rest of the interceptor chain continues in its configured order. If the cache interceptor sits outside and there is a cache hit, the logging advice might **not be invoked** on that call.

### Can you call another method on the target directly to avoid AOP?

You can call a method directly on a raw target under Java semantics, but doing so **bypasses cross-cutting concerns** and should not be used as a hidden "optimization". If a method genuinely does not need advice, choose a narrower pointcut or design the interface/service boundary appropriately.

### Self-invocation and `@Transactional`

`this.saveTransactional()` from the target also bypasses the transaction proxy in `AdviceMode.PROXY`. This can make `@Transactional` appear "not to work" even though the bean was properly proxied. Good design moves the transactional operation to a collaborating Spring bean, injects that bean's proxy, and calls through the dependency.

The same applies to `@Cacheable` and `@Async` in proxy mode: calling on the raw target does not pass through that bean's interceptors.

## 13. Common errors and fixes

| Symptom | Cause | How to check or fix |
| --- | --- | --- |
| `getThis() instanceof Implementation` is false | A JDK dynamic proxy is being used | Inject/call via the interface or evaluate the need for a class-based proxy |
| `getThis() instanceof Implementation` is true, but `getThis()==getTarget()` is false | CGLIB proxy is a separate-instance subclass | Distinguish `instanceof` from reference identity |
| Casting a Spring bean proxy to the implementation class fails | JDK proxy does not subclass the implementation | Inject the interface; avoid unnecessary casts |
| Calling a method via `getTarget()` skips transaction/audit | Bypasses the advisor chain | Inside `@Around`, use `pjp.proceed()` |
| Calling the advised method via `getThis()` causes stack overflow | New invocation repeats the same advisor | Do not replace `proceed()` with a call through the proxy |
| `AopContext.currentProxy()` reports no proxy | `exposeProxy` is not enabled or not inside a proxied call | Use `pjp.getThis()` inside advice; avoid thread-local coupling if unnecessary |
| `getTarget().getClass()` throws `NullPointerException` | Targetless proxy / custom target source | Null-check before dereferencing |
| Target instance changes between requests | Scoped proxy / dynamic target source | Do not cache target references; manage scopes properly |
| `this(JobService)` does not match, while `target(JobService)` matches | JDK proxy only implements the interface | Use the type pattern matching proxy vs. target semantics |
| CGLIB proxy does not advise `final` methods | Method cannot be overridden | Adjust class/method design or use an appropriate interface proxy |
| Method A is advised, but A calls B internally and B's advice is missing | Self-invocation on the target | Move B to a collaborating Spring bean and call through the proxy |
| Logger prints varying generated proxy class names | Logging runtime proxy class instead of target type | Use `AopUtils.getTargetClass`/supported metadata |
| Aspect does not run despite being in the right package | Aspect is not a Spring bean, AOP is not enabled, or call skips proxy | Check bean registration, `AopUtils.isAopProxy`, pointcut, and call path |
| Both proxy and target are proxies | Nested proxies from custom infrastructure | Inspect proxy layers; do not assume single-level unwrapping |
| Inspecting `pjp.getTarget()` and storing it long-term in a singleton | Target scope may change | Only use the reference within the invocation scope when genuinely needed |

## 14. Debugging workflow for getThis/getTarget

1. **Confirm the right context.** Was the bean created by the `ApplicationContext` that has `@EnableAspectJAutoProxy`?
2. **Confirm the aspect is a Spring bean.** `@Aspect` does not register a component by itself; `@Component`/`@Bean` is required.
3. **Retrieve the proxy from the container.** Do not instantiate the service with `new` and expect AOP to work.
4. **Check the proxy type.** `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy`.
5. **Inside advice, print types safely.** Use `getThis()` for the proxy; null-check `getTarget()` if infrastructure can be targetless.
6. **Compare with `==` instead of `equals`** to verify object identity.
7. **Check the pointcut.** Is `this(Type)` selecting the proxy or `target(Type)` selecting the target? Does it match a real method execution?
8. **Trace the call path.** Does the client call the proxy, or does the target call `this.method()`?
9. **Do not use the raw target to "fix" casting.** Calling methods on the target bypasses AOP.
10. **Do not use the proxy to simulate proceed.** In `@Around`, always favor `ProceedingJoinPoint.proceed()`.
11. **If using scoped proxies/TargetSource**, determine identity per invocation and avoid singleton assumptions.
12. **If caching/transaction/retry is involved**, check advisor ordering and whether the method is actually reached.
13. **Write integration tests** against the Spring context under both JDK and CGLIB configurations if the application can run in both modes.

### A diagnostic snippet to run after startup

```java
Object bean = context.getBean("jobService");
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean).getName());
```

This snippet depends on the `context` variable and importing `AopUtils`; it is not a standalone Java file. The boolean outputs show the proxy type; `getTargetClass` provides class metadata, not the target instance.

## 15. Conclusion

In **Spring AOP**:

- **`getThis()` is the Spring AOP proxy** — the entry point the client calls, where advisors/interceptors have the opportunity to run.
- **`getTarget()` is the current target object** — the object containing the actual method implementation, which may be `null` in targetless configurations or vary with a dynamic target source.
- **`getThis() == getTarget()` is typically false**, even with CGLIB. A JDK proxy is not an instance of the implementation; a CGLIB proxy can be an instance of the implementation via subclassing, yet identity still differs.
- **`this(TypePattern)` checks the proxy**, while **`target(TypePattern)` checks the target** in Spring pointcuts.
- **`pjp.proceed()` is the proper way to continue the current around-advice invocation**. Calling directly on the target bypasses advice; calling again on the proxy can create a new invocation and recursion.
- **Target self-invocation bypasses the proxy**; it cannot be fixed merely by switching from JDK to CGLIB.

The deepest takeaway is not how to print class names, but **the path of the call**. When the Spring proxy and target are treated as one object, logging, transactions, caching, retries, and other aspects can be skipped or duplicated in hard-to-predict ways.

### Official documentation

- [Spring Framework 6.1 Javadoc — MethodInvocationProceedingJoinPoint](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/aop/aspectj/MethodInvocationProceedingJoinPoint.html): describes `getThis()` returning the Spring proxy, `getTarget()` returning the target, and the possibility of target being `null`.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): distinguishes `this`/`target` in Spring AOP proxy-based systems.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, interception rules, and self-invocation.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `JoinPoint`, `ProceedingJoinPoint`, and `proceed()`.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): registering `@Aspect` and enabling Spring AOP.
