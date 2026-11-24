# Spring AOP: Private, Static, and Non-Overridable Method Calls

## 1. The Problem: Having an Aspect and Pointcut Yet Advice Still Does Not Run

Spring AOP is a **proxy-based AOP** mechanism for method calls on Spring-managed beans. When a service is wrapped in a proxy, calls from consumers passing through the proxy can be intercepted by advisors/advice. However, there are calls that the proxy **cannot observe**, even if the pointcut expression looks correct at a glance:

- `private` methods are not on the externally callable method surface and cannot be overridden by a subclass.
- `static` methods belong to the class; calling them by class name is not an instance call through a Spring AOP proxy.
- `final` instance methods cannot be overridden by a CGLIB subclass; with a **JDK interface proxy**, the rule differs: the proxy can still intercept calls through the interface method, even when the implementation method is `final`.
- A `final` class cannot be subclassed by CGLIB to create a proxy. If the class implements a suitable interface, Spring can select a JDK interface proxy.
- Methods with visibility that prevents subclass access/overriding, such as a package-private method inherited from a class in a different package, may not be advised by CGLIB.
- **Self-invocation** such as `this.publicMethod()` bypasses the proxy, even though the method is public and overridable. This is a **different** cause from a method being non-overridable.

You must distinguish two questions:

1. **Can the proxy create an interception point for this method?** Depends on JDK proxy vs. CGLIB, interfaces, visibility, and overridability.
2. **Does the specific call go through the proxy?** Depends on the reference the caller uses. Even a normal public method will not be advised if the target calls itself via `this`.

This lesson focuses strictly on **limitations in Spring AOP** and how to handle them when using Spring IoC, dependency injection, and Spring AOP proxies; it does not expand into general AOP theory.

## 2. Where Does Spring AOP Intercept Calls?

### 2.1. Call Path Through the Proxy

```text
Consumer (Spring bean or code retrieving bean from ApplicationContext)
            |
            | service.publicOperation()
            v
        Spring AOP proxy
            |
            | checks advisor/pointcut
            v
        Interceptor / advice
            |
            v
        Target.publicOperation()
```

The target and the proxy can be separate objects. When another bean injects the service, Spring supplies **the bean reference published by the container**; if wrapped by AOP, that is usually the proxy. For a target created manually with `new` outside the container, this Spring AOP proxy publishing process does not happen.

### 2.2. Call Paths That Bypass the Proxy

```text
Target.publicOperation()
      |
      +---- this.otherPublic()   ---> directly to target
      |
      +---- privateHelper()      ---> directly to target
      |
      +---- finalMethod()        ---> directly to target
      |
      +---- SomeClass.staticOp() ---> class, not proxy instance
```

**Self-invocation:** entering through the proxy at the start of a flow does not mean every internal method it calls also goes through the proxy. Once the target has control, calling `this.otherPublic()` is a call on the target itself and does not return to the Spring proxy.

**Overridability:** specifically, CGLIB creates a subclass to intercept eligible calls. It cannot override `private` and `final` methods. However, a public overridable method can still miss advice due to self-invocation.

**Pointcut limitations:** Spring AOP only supports **method execution join points on Spring beans**; it does not support join points like `call`, `get`, `set`, constructor execution, or static initialization in Spring AOP's usage of `@AspectJ` pointcuts. A pointcut string that appears to target a method will not help the proxy intercept a call that the proxy never receives.

## 3. Private Methods: No Call Path Through the Spring Proxy

Consider this service:

```java
@Service
public class AccountService {
    public void register(String id) {
        validate(id); // private method on the target itself
        System.out.println("Registered " + id);
    }

    private void validate(String id) {
        if (id.isBlank()) {
            throw new IllegalArgumentException("Empty id");
        }
    }
}
```

This is an **illustrative fragment**, not a standalone runnable application. If an aspect is set up to advise `register(...)`, calls from another bean into `register(...)` through the Spring proxy can be intercepted. However, `validate(...)` is `private`:

- External callers cannot invoke `validate` directly via the service's public API.
- A JDK proxy can only expose public methods on interfaces; `private` methods of the target do not belong to that surface.
- A CGLIB proxy subclass cannot override a private method. Therefore, Spring AOP proxy advice cannot be used to intercept `validate()`.
- Adding annotations to a private method or writing a pointcut targeting only that method **does not turn** a private call into a proxied call.
- Calling a private method on the target via reflection also does not make it pass through an AOP proxy.

**How to handle it:** if only internal input validation is needed, keep the helper private and apply advice to **the public service boundary**. If the private logic genuinely needs its own advice such as transactions/caching/auditing, consider moving that logic into a public method of **another Spring bean**, then injecting that bean and calling it from the service.

Example:

```java
@Service
public class RegistrationService {
    private final ValidatorService validator;

    public RegistrationService(ValidatorService validator) {
        this.validator = validator;
    }

    public void register(String id) {
        validator.validate(id); // Call through a Spring-injected bean.
    }
}

@Service
public class ValidatorService {
    public void validate(String id) {
        if (id.isBlank()) {
            throw new IllegalArgumentException("Empty id");
        }
    }
}
```

The two classes above are design fragments requiring `org.springframework.stereotype.Service` imports and placement in appropriate files. The call to `ValidatorService` can pass through a Spring AOP proxy if an aspect/advisor selects the `validate` method. Extracting beans should be based on sensible responsibilities, rather than creating extra beans that break encapsulation when advice at the public boundary suffices.

## 4. Static Methods: Calls Bound to the Class, No Instance Proxy

In Java, `static` methods are invoked on the class:

```java
public class FeeRules {
    public static long calculate(long subtotal) {
        return subtotal * 5 / 100;
    }
}
```

Calling `FeeRules.calculate(1000)` does not enter a Spring bean proxy. Even if `FeeRules` or another object is registered as a bean, static methods remain bound to **the class**.

With Spring AOP proxies:

- A **JDK dynamic proxy** intercepts method calls on the proxy object through interfaces. Static interface methods are not instance methods inherited by implementing classes and are not methods on the proxy instance.
- A **CGLIB proxy** is a subclass of the target. Static methods in Java are **hidden** (method hiding), not polymorphically overridden; override-based interception cannot be used to advise a static method.
- Annotating a static method, or writing `execution(* ...staticMethod(..))` in a pointcut, does not create a Spring proxy interception point for static calls.
- Putting `@Component` on a class containing static helpers does not change how Java dispatches static calls.

If you want to add logging, caching, transactions, or policies via Spring AOP, convert the behavior needing interception into **an instance method on a Spring-managed bean**:

```java
@Service
public class FeeService {
    public long calculate(long subtotal) {
        return subtotal * 5 / 100;
    }
}
```

Then consumers receive `FeeService` via constructor injection and call it through the Spring-provided reference. If a static method is purely a utility with no need for advice, keeping it static is a completely normal choice.

**Common misunderstanding:** it is not that “static doesn't work in Spring.” Static methods still run normally in Java; they simply do not pass through **Spring AOP proxy method interception**.

## 5. Final Methods and Final Classes: Differences Between JDK Proxies and CGLIB

### 5.1. With CGLIB: Requires Subclassing and Overriding

Spring uses a CGLIB class-based proxy when the target has no suitable interface or configuration forces class proxies. Mechanically, the proxy is a subclass of the target; therefore:

- A `final class` cannot be subclassed, so a **CGLIB proxy** cannot be created for that class.
- A `final instance method` cannot be overridden by a subclass, so it **is not advised via CGLIB**.
- A `private method` also cannot be overridden.
- Methods inaccessible from the subclass, such as a package-private method declared in a supertype in a different package, also cannot be intercepted by the proxy subclass in the usual way.

Example:

```java
public class JobService {
    public void run() {
        System.out.println("run");
    }

    public final void locked() {
        System.out.println("locked");
    }
}
```

With a CGLIB proxy, `run()` can be advised if called externally through the proxy and an advisor matches. `locked()` still executes its Java logic, but without subclass-style proxy advice. Renaming the pointcut alone cannot overcome the `final` limitation.

An important practical note: with a CGLIB proxy, a call to a `final` method can execute the inherited method directly on **the proxy subclass object**, without passing through interceptor/delegation to the target like overridden methods do. If the `final` method accesses mutable fields or dependencies initialized on the target, behavior can be surprising in some proxy setups. Do not design business logic around calling `final` methods on a class proxy; if advice is needed, choose a proxyable method or change bean boundaries.

### 5.2. With JDK Proxies: A `final` Method on the Implementation Can Be Advised

A JDK dynamic proxy **is not a subclass of the target**. It creates an object implementing the interfaces Spring chooses to proxy, handling calls to public interface methods before forwarding to the target. Therefore, a `final` method on the target **does not prevent** intercepting calls through the corresponding interface.

```java
public interface JobPort {
    void locked();
}

public final class FinalJobService implements JobPort {
    @Override
    public final void locked() {
        System.out.println("locked");
    }
}
```

This is a standalone Java type fragment without a Spring context/aspect yet. If `FinalJobService` is registered as a Spring bean, has an advisor for `locked()`, and is used via a **JDK proxy of `JobPort`**, advice can run even though both the class and the implementing method are `final`.

Never conclude that “every `final` method cannot be advised by Spring AOP.” The accurate statement is that **CGLIB cannot advise a `final` method via overriding**, whereas a JDK proxy can intercept public interface methods before reaching the `final` target implementation.

If the target class is `final` and has no suitable interface, Spring cannot create a subclass proxy to advise methods of that class; when the bean truly needs a class-based proxy, proxy creation can fail.

### 5.3. Decision Table

| Method or class kind | Spring JDK dynamic proxy | Spring CGLIB class-based proxy |
| --- | --- | --- |
| Public method declared on an interface implemented by the proxy | Advisable if pointcut matches | Advisable if method is overridable |
| Public method only on the concrete class | Not exposed by the JDK proxy via the interface | Advisable if method is overridable |
| `private` method of the target | No | No |
| `static` method of the target/interface | No | No |
| Public `final` method declared on the interface | Advisable via interface call | Cannot override to advise |
| `final` class implementing an interface | Can create a JDK proxy via the interface | Cannot subclass the class |
| `final` class without a suitable interface | No suitable interface proxy surface | Cannot subclass |
| `protected`/package-private instance method on the target | Not part of the public interface proxy surface | Possible depending on access rights/overridability; not considered public API |
| Package-private method declared in a supertype in another package | Not on the public interface | May not be accessible/overridable |
| Public, non-final method called via `this.method()` | Does not advise self-invocation calls | Also does not advise self-invocation calls |

*Table assumes the target belongs to the Spring container, AOP is enabled, and an appropriate advisor exists. “Advisable” always requires calling through the proxy; it is not a guarantee that advice runs automatically.*

## 6. Self-Invocation and the Case of “Completely Overridable Methods”

This is the most common mistake that makes learners confuse it with `private`/`final` limits:

```java
@Service
public class TransferService {
    public void transfer() {
        this.audit(); // Still bypasses the Spring proxy.
    }

    public void audit() {
        System.out.println("audit");
    }
}
```

`audit()` is public, non-final, and overridable. If a consumer calls `transferService.audit()` on the Spring proxy, advice for `audit()` can run. But when the target calls `this.audit()`, the call on **the target** does not go back through the proxy. Both JDK and CGLIB proxies share this self-invocation limitation in Spring AOP.

Distinguish accurately:

- **Private/final/static:** inherent limitations of the proxy type or Java dispatch, so even an external-like call cannot produce interception via CGLIB/instance proxies.
- **Self-invocation:** the method can still be advised when called **from another bean through the proxy**, whereas calls from the target itself do not pass through the proxy.
- **Constructors and initialization callbacks:** logic runs while constructing the target, before the bean is used through the final proxy; do not expect `@Transactional` or other advice to be triggered from `@PostConstruct` or constructors.

**Preferred solution:** extract the method needing a separate policy into a Spring bean with clear responsibilities, inject it via constructor, and invoke through that reference. For special needs, `AopContext.currentProxy()` can expose the current proxy to code if `exposeProxy=true` is configured and the call is already inside a proxied invocation; this approach couples business code to Spring AOP and does not make private/static/final methods interceptable.

## 7. Complete Runnable Example — Spring Framework 6.2 and Java 17

The example shows a target service using a **CGLIB proxy**, containing an overridable public method, a private helper, a `final` method, a `static` method, and a public method called via `this`. The pointcut is intentionally broad to observe precisely **which calls the Spring AOP proxy can intercept**.

Structure:

```text
spring-method-limits/
├── pom.xml
└── src/main/java/demo/limits/
    ├── AppConfig.java
    ├── VisibilityService.java
    ├── TraceAspect.java
    └── Demo.java
```

### 7.1. Maven Dependencies

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-method-limits</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

The project uses plain Spring Framework without Spring Boot. `aspectjweaver` provides support for parsing `@AspectJ` pointcuts for Spring AOP. You do not need to enable the AspectJ compiler or load-time weaving to run this example.

### 7.2. Auto-Proxy Configuration

File `src/main/java/demo/limits/AppConfig.java`:

```java
package demo.limits;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
}
```

`proxyTargetClass=true` forces class-based proxies. The target below has no interfaces; the example uses CGLIB to clearly demonstrate overriding limits. `@ComponentScan` scans the `demo.limits` package, finding the target and aspect.

### 7.3. Target with Public/Private/Final/Static Methods

File `src/main/java/demo/limits/VisibilityService.java`:

```java
package demo.limits;

import org.springframework.stereotype.Service;

@Service
public class VisibilityService {
    public void publicAction() {
        System.out.println("[target] publicAction");
    }

    public void route() {
        System.out.println("[target] route");
        this.publicAction(); // Public but self-invocation.
        privateAction();      // Private, cannot be overridden.
        finalAction();        // Final, cannot be overridden.
        staticAction();       // Static, does not go through proxy.
    }

    private void privateAction() {
        System.out.println("[target] privateAction");
    }

    public final void finalAction() {
        System.out.println("[target] finalAction");
    }

    public static void staticAction() {
        System.out.println("[target] staticAction");
    }
}
```

The class is non-`final`, so CGLIB can create a subclass. `publicAction()` and `route()` are overridable. `finalAction()` is made public so callers can attempt to invoke it from outside; it still cannot be advised by CGLIB.

### 7.4. Aspect with a Broad Pointcut

File `src/main/java/demo/limits/TraceAspect.java`:

```java
package demo.limits;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {
    @Before("execution(* demo.limits.VisibilityService.*(..))")
    public void before(JoinPoint joinPoint) {
        System.out.println("[advice] " + joinPoint.getSignature().getName());
    }
}
```

The expression `execution(* ...VisibilityService.*(..))` matches methods matching the class's signatures at the pointcut level, yet **cannot turn private/static/final calls into calls intercepted by a CGLIB proxy**. Only the two external calls to public, non-final methods through the proxy trigger advice in this example.

### 7.5. Main Retrieving the Spring Bean and Making Calls

File `src/main/java/demo/limits/Demo.java`:

```java
package demo.limits;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Demo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            VisibilityService service = context.getBean(VisibilityService.class);

            System.out.println("cglibProxy="
                    + AopUtils.isCglibProxy(service));

            service.publicAction();
            service.route();
            service.finalAction();
            VisibilityService.staticAction();
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.limits.Demo
```

Standard lines printed by the program (Maven/Spring may emit additional logs/warnings):

```text
cglibProxy=true
[advice] publicAction
[target] publicAction
[advice] route
[target] route
[target] publicAction
[target] privateAction
[target] finalAction
[target] staticAction
[target] finalAction
[target] staticAction
```

**Reading the output by call path:**

1. `AopUtils.isCglibProxy(service)` returns `true` because the service is advised and `proxyTargetClass=true`.
2. `service.publicAction()` from `Demo` goes through the proxy. `@Before` prints `[advice] publicAction` before the target.
3. `service.route()` also goes through the proxy. Advice prints `[advice] route`.
4. Inside `route()`, calling `this.publicAction()` **does not go through the proxy**, even though it is public and overridable: only `[target] publicAction` is printed.
5. `privateAction()` cannot be overridden or advised by CGLIB; only the target output prints.
6. `finalAction()` cannot be overridden by CGLIB. Both the call inside `route()` and the direct call from `Demo` print **no** advice.
7. `staticAction()` is called inside `route()` and directly via class name. Both are Java static method calls, not proxy instance invocations.

Because the example holds no state in the target, output order is not skewed by target/proxy instance differences on `final` methods. **Do not generalize** that `final` methods can safely access all state of a CGLIB-proxied object.

### 7.6. Trying a Pointcut That Selects Only the `final` Method

If you change the advice to:

```java
@Before("execution(* demo.limits.VisibilityService.finalAction(..))")
public void beforeFinal() {
    System.out.println("[advice] final");
}
```

this is a snippet **replacing the method in `TraceAspect`**, not a separate source file. Spring cannot intercept calls to a `final` method with CGLIB. When only this advisor exists and no advisor intercepts any other proxyable method, do not assume a bean is guaranteed to receive a proxy. AOP configuration and how advisors select candidate beans can affect the proxy creation decision; even if a proxy is created, `finalAction()` still will not be overridden/advised.

### 7.7. Trying `static` or `private` Methods with Annotations

A `private` method such as:

```java
@Transactional
private void storeAudit() {
    // ...
}
```

or `static` such as:

```java
@Transactional
public static void storeAudit() {
    // ...
}
```

are **illustrative fragments** and require importing `org.springframework.transaction.annotation.Transactional` in an application using the transaction module. When Spring transactions are configured in normal **proxy** mode, that annotation **does not make Spring AOP intercept** `private`/`static` methods. Before concluding a transaction annotation “is broken,” check method visibility, call paths through the proxy, and bean boundaries.

## 8. Side Example: A JDK Proxy Still Advises Implementation `final` Methods

Because this lesson sits in the JDK and CGLIB group, it is important to distinguish an important exception regarding `final`. Do not reuse `VisibilityService` from the example above to illustrate a JDK proxy because that class has no interface.

The following Java code is an **illustrative fragment** of two type/interface files:

```java
public interface WorkPort {
    void finish();
}

public final class FinalWorker implements WorkPort {
    @Override
    public final void finish() {
        System.out.println("finished");
    }
}
```

Register `FinalWorker` as a Spring bean, enable AOP selecting JDK proxies (in plain Spring Framework, `@EnableAspectJAutoProxy(proxyTargetClass=false)`), have an advisor matching `finish()`, and inject `WorkPort` into a consumer. When the consumer calls `port.finish()`, the interceptor runs **on the interface proxy before delegating** to the target. Because a JDK proxy does not need to subclass `FinalWorker`, `final class` and `final method` on the implementation do not prevent advice.

However, if a consumer demands injecting `FinalWorker` directly while Spring returns a JDK proxy, a type error can occur, because the proxy is not an instance of the concrete class. Use the `WorkPort` interface as the dependency contract.

**Never apply JDK proxy conclusions to CGLIB:** CGLIB still cannot subclass a `final` class or override a `final` method.

## 9. When You Need Advice for Behavior Currently Inside a Private/Static/Final Method

### 9.1. Place Advice on a Public Entry Point

If the requirement is “every account registration call must be audited,” advise the public method `RegistrationService.register()`. It can call multiple private helpers, while calls to the entry point are already advised before/after the entire operation according to the configured advice timing. This is usually the minimal and most controllable solution.

If a transaction is needed around a sequence of operations, place the transaction boundary on a public service method called by another bean through the proxy, rather than on an internally invoked private helper.

### 9.2. Extract the Policy Boundary into a Separate Bean

If a helper needs its own policy, it can be extracted into a dedicated bean:

```java
@Service
public class ApprovalService {
    private final AuditService auditService;

    public ApprovalService(AuditService auditService) {
        this.auditService = auditService;
    }

    public void approve(String id) {
        auditService.record(id); // Method invocation via Spring dependency.
    }
}

@Service
public class AuditService {
    public void record(String id) {
        System.out.println("audit " + id);
    }
}
```

This is an illustrative design fragment requiring appropriate imports/packages and Spring configuration. When `AuditService` is proxied because an advisor matches `record()`, calls through the dependency are intercepted. This approach also makes unit testing easier and avoids coupling to `AopContext.currentProxy()`.

### 9.3. Choose a JDK Proxy If an Interface Contract Fits

If the target class must be `final` by design yet still has a public interface, consider JDK-proxy-based Spring AOP. Spring Boot AOP auto-configuration usually defaults to CGLIB; if you want to prefer JDK proxies, you can set:

```properties
spring.aop.proxy-target-class=false
```

In plain Spring Framework, `@EnableAspectJAutoProxy(proxyTargetClass=false)` is the annotation's default. A value of `false` does not guarantee a JDK proxy if the bean has no interfaces or another auto-proxy configuration forces class-based proxies.

Use `AopUtils.isJdkDynamicProxy(bean)` and `AopUtils.isCglibProxy(bean)` to check at runtime on the reference Spring injects/returns from `getBean`; do not rely solely on class names or a single annotation.

### 9.4. When Is a Mechanism Outside Spring AOP Proxies Needed?

If the requirement strictly demands intercepting private/static/constructor/field-access calls or self-invocation at the bytecode level, **Spring AOP proxies do not support it**. That is a different scope, potentially requiring compile-time/load-time AspectJ weaving with separate configuration, or changing the design to express the operation through a public Spring bean boundary. You cannot achieve the same result merely by changing pointcuts or setting `proxyTargetClass=true`.

## 10. Diagnosing “The Pointcut Is Right Yet Advice Does Not Run”

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| `private` method has `@Transactional` yet no transaction opens | Private methods are not on the proxy surface | Place the boundary on a proxyable method or extract a bean |
| `static` method has a name-matching pointcut yet advice does not run | Static calls do not go through an instance proxy | Convert to an instance method on a Spring bean if advice is needed |
| `public final` method on a CGLIB proxy is not advised | Cannot override `final` methods | Remove `final` if design allows, use a JDK interface proxy, or extract a bean |
| Target class is `final` and class proxy is forced | CGLIB cannot subclass it | Use an interface/JDK proxy or change the design |
| Public non-final method called via `this` is not advised | Self-invocation bypasses the proxy | Call via another DI-managed bean |
| Package-private method in a base class from another package is not advised | Not visible/overridable in the proxy subclass | Place the API on an appropriate public/protected method |
| Interface exists yet runtime proxy is CGLIB | Spring Boot defaults to class-based proxies or merged config exists | Check `spring.aop.proxy-target-class` and `AopUtils` |
| Manually called `new Service()` then invoked method | Object is not managed by Spring | Inject the bean from the container instead of creating the target manually |
| `@Aspect` is present yet no advice runs anywhere | Aspect is not a Spring bean, AOP is not enabled, or pointcut does not match | Verify `@Component`/`@Bean` and `@EnableAspectJAutoProxy`/Boot AOP |
| Advice runs on `outer()` yet not on internally called methods | Caller entered the proxy once, then target used `this` | Trace the actual call path; extract a separate bean when needed |

### Repeatable Inspection Workflow

1. Confirm the target is a Spring-managed bean, the aspect is registered, and AOP infrastructure is enabled.
2. Retrieve **the actual reference** at the injection point or via `ApplicationContext.getBean(...)`.
3. Check with `AopUtils.isAopProxy(bean)`; if needed, distinguish `isJdkDynamicProxy` and `isCglibProxy`.
4. Determine whether the method is instance or static, public/protected/private, `final` or overridable, and whether the target class is `final`.
5. If JDK proxy, verify the method belongs to an interface exposed by the proxy; if CGLIB, verify subclass visibility/overridability.
6. Trace **the call path**: from consumer through proxy vs. via `this`/a `new` object/initialization callbacks.
7. Only after that should you adjust the pointcut. Do not broaden a pointcut to fix an error caused by call path or proxy type.

## 11. Self-Check

**1. Why can't CGLIB advise a `private` method even when `execution(* my.pkg.Service.helper(..))` looks accurate?** Because the proxy subclass cannot override private methods and cannot receive a private call through the proxy.

**2. Is a `public final` implementation method always outside Spring AOP?** No. A JDK proxy can intercept a public interface invocation targeting a `final` implementation. CGLIB, however, cannot override a `final` method.

**3. A service has a public instance method, yet an aspect does not run when called from another method in the same class. Why?** Self-invocation executes on the target `this` and does not pass through the proxy; it is unrelated to whether the method is `final`.

**4. Does enabling `proxyTargetClass=true` help intercept `static` methods?** No. Static methods are not overridden and are not instance invocations through the proxy.

**5. Why can a `final class` run AOP via a JDK proxy but not via CGLIB?** A JDK proxy implements an interface; CGLIB needs to subclass the target, which Java forbids for `final` classes.

**6. When should private logic be extracted into a separate bean?** When that business operation genuinely needs its own policy via Spring AOP and has a clear responsibility boundary; if it is purely an internal helper, advice at the public entry point is usually sufficient.

## Official Spring Documentation

- [Spring Framework — Proxying Mechanisms (JDK, CGLIB, private/final, and self-invocation)](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Declaring a Pointcut (scope of method execution join points)](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework — ProxyFactoryBean and class-based proxies](https://docs.spring.io/spring-framework/reference/core/aop-api/pfb.html)
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html)
