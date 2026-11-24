# Mapping Aspects, Advice, and Pointcuts to Spring AOP Mechanics

## 1. Objectives and Scope

This article explains **how Spring Framework executes an aspect declared with `@Aspect`**: how Spring detects an aspect bean, translates pointcut expressions and advice methods into internal AOP configuration, selects which Spring beans need proxying, and invokes advice when a matching method is called through a proxy. The focus is on **proxy-based Spring AOP**, without going deep into general AOP theory or standalone AspectJ weaving mechanisms.

After this lesson, you will be able to:
- Identify the specific roles of `@Aspect`, `@Pointcut`, advice annotations, `Advisor`, `Pointcut`, and `MethodInterceptor` in Spring.
- Explain the path of a method call from the client to the Spring proxy, advice chain, and target object.
- Write, run, and inspect an aspect using Spring Boot with `spring-boot-starter-aop`.
- Diagnose cases where a pointcut looks right but advice does not run because the call does not pass through a Spring proxy.

## 2. What Does Spring Interpret an `@Aspect` Declaration Into?

Suppose an application has a Spring bean `OrderService` and a bean `TraceAspect`. When programming, we write three visible components:

| Declared Component | Role When Using Spring | Corresponding Spring Mechanism |
| --- | --- | --- |
| `@Aspect` on `TraceAspect` | Marks a class containing advice rules | Spring recognizes an **aspect bean** and parses its advice methods. Simply annotating with `@Aspect` does not automatically register the class as a bean. |
| `@Pointcut("...")` | Gives a name to a method-selection condition | The expression is parsed and applied via `AspectJExpressionPointcut`; the `void` pointcut method only defines the matching pattern and holds no business processing. |
| `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, `@Around` | Declares additional logic at different points in execution | Spring creates corresponding advice objects; during a call through a proxy, they participate in the interceptor chain. |
| `Advisor` | Pairs a **matching condition** with **runtime behavior** | A proxy can hold multiple advisors; each advisor decides whether to apply its advice to a specific call. |
| `Pointcut` (API `org.springframework.aop.Pointcut`) | Checks the target class and method | Consists of `ClassFilter` and `MethodMatcher`; some conditions may also need to inspect arguments at call time. |
| Spring AOP proxy | The object Spring hands to the caller instead of the direct target bean | Intercepts method calls, selects matching interceptors, and forwards to the target. |
| Target object | The bean executing the original business logic | Runs when the interceptor chain proceeds to the target method. |

**Easy-to-confuse distinction:** `@Aspect` is the developer's declarative model; `Advisor` and `Advice` are the components Spring uses to build and operate proxies. One aspect with multiple advices can contribute multiple advisors. `@Pointcut` by itself does not execute code on a call, and no call is generated automatically just because you declared a `@Pointcut`.

Another bean can also receive advice from Spring infrastructure through an advisor/interceptor without needing a custom `@Aspect` class you wrote. For example, declarative transaction infrastructure via `@Transactional` has its own advisor/interceptor mechanism. Therefore, you should not equate every proxy in Spring with a specific `@Aspect` class.

## 3. How Does Spring Activate and Create Proxies?

### 3.1. Registration Conditions

With Spring Boot having the required AspectJ library on the classpath (typically via `spring-boot-starter-aop`), Boot auto-configures proxy support for `@Aspect`; the Boot example below **does not need** `@EnableAspectJAutoProxy`. In a plain Spring Framework application, you can explicitly enable it with `@EnableAspectJAutoProxy` on a configuration class and register the aspect as a Spring bean (for example, `@Component` or `@Bean`).

`@Aspect` is **not** a bean auto-scanning stereotype: the aspect class must be registered in `ApplicationContext`. Having the annotation dependency without the auto-proxy mechanism is also insufficient for advice to run.

### 3.2. From Bean Definition to Actual Call

```text
ApplicationContext creates AOP infrastructure
    |
    +-- detects aspect beans and existing advisors
    |       |
    |       +-- parses @Pointcut / matching expressions
    |       +-- converts @Before/@Around/... methods into advice
    |
    +-- during bean creation, auto-proxy creator evaluates matching advisors
            |
            +-- no advice needed --> use regular bean
            |
            +-- matching advisors found --> create Spring proxy for bean
                                        |
Client retrieves bean from container --> calls method through proxy
                                        |
                              selects matching interceptors
                                        |
                               runs advice along the chain
                                        |
                               calls target method
                                        |
                            returns result or throws exception
```

Spring uses the `BeanPostProcessor` mechanism, typically an auto-proxy creator such as `AnnotationAwareAspectJAutoProxyCreator`, to inspect beans and apply matching advisors. When a method is called through a proxy, Spring selects the interceptor chain for that method; the chain runs through the advice and then to the target according to each advice's semantics. Creating a proxy **does not mean** every method on the bean gets advised: the pointcut and proxy limitations still determine whether a call is intercepted.

### 3.3. Two Proxy Forms to Recognize

- **JDK dynamic proxy** implements the proxied interfaces. Client calls go through the public interface provided by the proxy; if you inject the bean by its implementation class instead of its interface, it may not be compatible with this proxy type.
- **Class-based proxy (CGLIB)** creates a subclass to intercept overridable calls. It cannot override `final` methods; `final` classes also cannot be subclassed to be proxied this way. `private` methods cannot be advised by this proxy form.

With **Spring Boot 3.3**, auto-configuration defaults to class-based proxying; set `spring.aop.proxy-target-class=false` to use JDK proxies when a bean has a suitable interface. With direct Spring Framework configuration, the `proxyTargetClass` attribute in `@EnableAspectJAutoProxy` controls the corresponding preference. Do not infer the proxy type merely from the presence of `@Aspect`: inspect the actual proxy.

## 4. Matching Points in Spring AOP: From Pointcut Expression to Method Execution

Proxy-based Spring AOP supports **method-execution join points on Spring beans**. Example:

```java
@Pointcut("execution(public * com.example.app.service..*.*(..))")
public void publicServiceMethod() { }
```

- `execution(...)`: filters method execution calls; here it matches `public` methods, any return type, in package `com.example.app.service` and its subpackages.
- `publicServiceMethod()`: a pointcut name that can be reused across advices in the same aspect; the Java method is declared `void` with an empty body.
- The expression only describes the **selection condition**. No statements inside the `publicServiceMethod()` method are executed when a service method matches.

Useful designators in Spring:

| Expression | Meaning in Spring AOP |
| --- | --- |
| `execution(* com.example.app.service..*.*(..))` | Methods within the specified signature/class scope. |
| `within(com.example.app.service..*)` | Restricts target methods to types within that package/package hierarchy. |
| `@annotation(com.example.app.TrackAction)` | Executing methods that carry the specified annotation. |
| `bean(*Service)` | Selects beans by **Spring bean name** matching the pattern; this is a Spring AOP-specific extension. |
| `this(com.example.app.OrderApi)` | Checks whether the **Spring proxy** has the specified type. |
| `target(com.example.app.OrderService)` | Checks whether the **target object** behind the proxy has the specified type. |
| `args(java.lang.String, ..)` | Inspects the actual argument types when calling the method. |

Combine conditions using `&&`, `||`, and `!`. For example, apply only to methods that have the annotation and reside in the service layer:

```java
@Pointcut("within(com.example.app.service..*)"
        + " && @annotation(com.example.app.TrackAction)")
public void annotatedServiceOperation() { }
```

You can point advice to the pointcut name: `@Around("annotatedServiceOperation()")`. When referencing a pointcut declared in another class, use the fully qualified path to the pointcut method per Spring's rules.

**Important limitation:** expressions such as `call(...)`, `get(...)`, `set(...)`, and many other AspectJ join point kinds are not supported by proxy-based Spring AOP. Seeing AspectJ syntax in an annotation does not mean Spring has enabled the AspectJ compiler or weaving. In Spring, `this` is the proxy while `target` is the target object, so the two values can differ.

## 5. How Does Advice Fit into the Invocation Chain?

| Advice Annotation | When Logic Runs When a Call Is Intercepted by a Proxy | Practical Capabilities/Limitations |
| --- | --- | --- |
| `@Before` | Before the target method | Commonly used for checks/logging; cannot directly replace the return value; throwing an exception prevents the call from continuing. |
| `@AfterReturning` | When the method completes normally | Can read the result via `returning`, but cannot replace the result merely by reassigning the advice parameter variable. |
| `@AfterThrowing` | When the method exits via an exception | Can read the exception via `throwing`; narrow the exception type appropriately to catch the intended cases. |
| `@After` | After the method finishes, whether normally or by exception | Close to `finally` behavior; does not imply success. |
| `@Around` | Wraps the rest of the invocation chain and the target | Receives `ProceedingJoinPoint`; calls `proceed()` to continue, can measure duration, return a result, or handle errors intentionally. |

Example of signatures receiving information provided by Spring (standalone illustrative snippets, not merged into the runnable example in the next section):

```java
@Before("execution(* com.example.app.service..*.*(..))")
public void beforeCall(org.aspectj.lang.JoinPoint joinPoint) {
    System.out.println(joinPoint.getSignature().getName());
}

@AfterReturning(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    returning = "result"
)
public void afterSuccess(Object result) {
    System.out.println("result=" + result);
}

@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "error"
)
public void afterFailure(Throwable error) {
    System.out.println("error=" + error.getClass().getSimpleName());
}
```

In `@Around`, calling `proceed()` is the boundary into the rest of the chain and ultimately the target; avoid forgetting to call it when the business logic needs to run. `@Around` can decide not to call `proceed()`, call it multiple times, or change the return value, but should only do so intentionally while preserving the method contract. If the advice only needs to observe before/after, choose a simpler advice type.

When there are **multiple aspects**, advice ordering is affected by advisor ordering, advice type, and `@Order`/`Ordered`. Do not write examples that depend on an unconfigured order; if a specific order is required, specify and test it.

## 6. Runnable Example: `@Aspect` + `@Pointcut` + `@Around` on Spring Boot

The example uses **Java 21, Spring Boot 3.3.x, and Gradle**. The intent is to trace methods annotated with `@TrackAction` in a Spring bean. All Java classes reside in package `com.example.demo` to be detected by component scanning.

### 6.1. Gradle Configuration

File `settings.gradle`:

```groovy
rootProject.name = 'spring-aop-mapping'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

`spring-boot-starter-aop` supplies the Spring AOP infrastructure and the AspectJ library needed for Spring to interpret annotations and pointcut expressions. The following source code uses Spring proxies and does not configure AspectJ compile-time weaving/load-time weaving.

File `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=OFF
```

### 6.2. Annotation Marking the Methods to Trace

File `src/main/java/com/example/demo/TrackAction.java`:

```java
package com.example.demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface TrackAction {
}
```

### 6.3. Target Spring Bean with Selected Methods

File `src/main/java/com/example/demo/OrderService.java`:

```java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    @TrackAction
    public String place(String productId) {
        return "stored:" + productId;
    }

    public String status() {
        return "ok";
    }
}
```

`place(...)` has `@TrackAction`; `status()` has no annotation, so it does not match the pointcut in this example. Both are methods of the same Spring bean.

### 6.4. Aspect Declaring Pointcut and Advice

File `src/main/java/com/example/demo/TraceAspect.java`:

```java
package com.example.demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {
    @Pointcut("@annotation(com.example.demo.TrackAction)")
    public void trackedAction() {
    }

    @Around("trackedAction()")
    public Object trace(ProceedingJoinPoint joinPoint) throws Throwable {
        String method = joinPoint.getSignature().getName();
        System.out.println("enter " + method);
        try {
            Object result = joinPoint.proceed();
            System.out.println("exit " + method);
            return result;
        } catch (Throwable error) {
            System.out.println("failed " + method);
            throw error;
        }
    }
}
```

Mapping from code to Spring:
1. `@Component` registers `TraceAspect` as a bean; `@Aspect` tells the AOP infrastructure that this class holds advice.
2. `@Pointcut` names the pattern of methods with `@TrackAction` as `trackedAction`.
3. `@Around("trackedAction()")` binds the `trace` method to that pointcut. Spring supplies the `ProceedingJoinPoint` for the intercepted call.
4. The auto-proxy creator inspects `OrderService` and can create a proxy applying the corresponding advisor; calling `place(...)` **through the proxy** triggers `trace`.
5. `joinPoint.proceed()` executes the rest of the chain/target; `trace` returns the original result or rethrows the exception.

### 6.5. Running and Observing the Proxy

File `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {
            OrderService service = context.getBean(OrderService.class);
            System.out.println(service.place("P-100"));
            System.out.println("isProxy=" + AopUtils.isAopProxy(service));
            System.out.println(service.status());
        }
    }
}
```

In the project directory with Gradle installed or Gradle Wrapper, run `gradle bootRun` or `./gradlew bootRun` accordingly. With the logging configuration above, the lines printed by the program are:

```text
enter place
exit place
stored:P-100
isProxy=true
ok
```

`enter place` / `exit place` appear around the annotated call. `status()` still runs, but **does not** emit the two advice lines because it does not match `@annotation(TrackAction)`. `isProxy=true` proves the bean obtained from the container is a Spring AOP proxy. The code does not rely on proxy class names, which can differ across configurations and versions.

**An easy mistake to make:** calling `new OrderService().place("P-100")` will not run the advice, because an object created with `new` is not a proxy supplied by Spring. The interception point is a call **passing through a Spring proxy**, not the annotation itself executing logic.

## 7. Verifying the `@Aspect` → Advisor → Proxy Mapping

When advice does not run, look for the **missing mapping link** before editing the pointcut expression. Check in order: whether the `@Aspect` class is registered as a bean; whether auto-proxy support is enabled; whether the expression produces an advisor for that type/method; and whether Spring provided a proxy to the caller.

For instance, `@Pointcut("@annotation(com.example.demo.TrackAction)")` only selects methods carrying the matching annotation; it executes no processing. `@Around("trackedAction()")` is what supplies the behavior, converted by Spring into advice in the interceptor chain. If you remove `@Component` from `TraceAspect`, there is no aspect bean for the infrastructure to discover; if you remove the annotation from `place()`, the pointcut does not select the method even though the service remains in the container.

Seeing `AopUtils.isAopProxy(service) == true` only confirms the reference is a proxy; you must still verify **whether the advisor matches the specific call**. Calling `this.place()` from inside the target or manually instantiating the service with `new` can bypass the proxy path. If using a JDK proxy, the caller must access methods exposed via the interface; with a subclass proxy, overridability must be considered.

A useful test: call an annotated method and an unannotated method through the same proxy, record the trace of advice and target, then compare against the declared pointcut. The result helps distinguish **no proxy created**, **advisor mismatch**, and **proxy bypassed**.

## 8. Systematic Verification and Practical Application

When debugging is needed, proceed in order:

1. **Bean:** confirm both the aspect and the service exist in `ApplicationContext`; Spring Boot has received the AOP dependency.
2. **Proxy:** check `AopUtils.isAopProxy(service)`, and when needed also check `AopUtils.isJdkDynamicProxy(service)` / `AopUtils.isCglibProxy(service)`.
3. **Pointcut:** match exact package/method annotations and `this`, `target`, `bean` conditions; the narrower the expression, the more predictable it is.
4. **Call path:** ensure the client retrieves the bean from Spring and calls from outside through the proxy; distinguish calling another method from self-invocation.
5. **Advice semantics:** verify whether the method returns normally or throws; with `@Around`, check `proceed()` and return/exception-throwing rules.

Suitable practical uses: timing a group of Spring service methods, logging operations with a dedicated annotation, tracking exceptions at service boundaries, or checking internal conventions. Limit logging sensitive data in advice; choose clear pointcuts to avoid applying broadly across many beans and adding unnecessary overhead. For transaction, security, or caching needs, prefer Spring's dedicated declarative mechanisms when they already satisfy the requirement.

## 9. Summary of Mechanics to Remember

`@Aspect` and advice annotations are **declarative inputs**. Spring parses pointcuts/advices, pairs conditions with handlers into advisors, selects beans needing proxies, and uses an interceptor chain to run advice when method calls pass through the proxy. `@Pointcut` defines where advice applies; `@Around` and other advices define behavior at the corresponding point. Understanding the boundary **Spring-managed bean → proxy → advice chain → target** is the key to explaining why an aspect runs, runs at the wrong time, or does not run.

Official Spring documentation for cross-reference:
- Spring Framework — [AOP in Spring](https://docs.spring.io/spring-framework/reference/core/aop.html).
- Spring Framework — [Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html).
- Spring Framework — [Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html).
- Spring Boot 3.3 — [AOP auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/aop.html).