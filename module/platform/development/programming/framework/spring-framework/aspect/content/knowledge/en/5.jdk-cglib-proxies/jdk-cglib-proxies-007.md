# Visibility Scope of public, protected, and package-visible Methods by Proxy Mechanism in Spring AOP

## 1. Objectives

Spring AOP intercepts method invocations **that pass through a Spring proxy**. However, whether a method can be advised also depends on **the proxy type**, **method visibility**, **the type through which the client can invoke it**, and **how the call enters the bean**.

This lesson directly answers the question: for the same service bean in Spring, how do calls to **public**, **protected**, and **package-visible (package-private)** methods differ when Spring uses a **JDK dynamic proxy** vs. a **CGLIB proxy**?

After this lesson, you will be able to:

- Accurately distinguish the method surface Spring AOP can intercept for each proxy type.
- Explain why a public method present on the implementation but **not declared on the interface** is absent from a JDK proxy.
- Explain the conditions under which a class-based CGLIB proxy can intercept protected and package-visible methods.
- Identify private, final, static, package-visible methods that cannot be overridden in an inheritance hierarchy, as well as internal calls that bypass the proxy.
- Write, run, and compare a plain Spring Framework example featuring both a JDK proxy and a CGLIB proxy.
- Avoid confusing **Spring AOP @AspectJ advice** rules with specific rules of **@Transactional**.

**Scope:** Covers only **proxy-based Spring AOP**, Spring-managed service beans, and advice declared with **@Aspect**. General AOP theory or AspectJ weaving is not the primary focus.

## 2. Two Types of Spring AOP Proxies

Spring AOP selects one of two proxy creation mechanisms for a managed target:

1. **JDK dynamic proxy**: the proxy implements interfaces, intercepting calls to **public interface methods** exposed through the proxy. Under default plain Spring Framework configuration, this is the typical type used when the target implements at least one suitable interface.
2. **CGLIB proxy**: the proxy is a dynamically generated subclass of the target class. This mechanism can intercept methods that the subclass **is permitted to override** and that callers **actually invoke through the proxy**. This type is chosen when no interface exists or when **proxyTargetClass = true** is explicitly enabled.

Example:

~~~text
                        Spring ApplicationContext
                                   |
                       target: InventoryService
                                   |
                  +----------------+----------------+
                  |                                 |
              JDK proxy                         CGLIB proxy
        implements InventoryApi          extends InventoryService
                  |                                 |
         public interface API             public, protected,
                                         valid package-visible
                  |                                 |
                  +----------- client --------------+
                                  |
                        advice -> target
~~~

The diagram shows **potential interception points**; it does not mean CGLIB automatically intercepts every Java call inside the target. **Self-invocation** still goes directly to the target.

## 3. Visibility Rules Table

| Method kind | JDK dynamic proxy | CGLIB class-based proxy |
| --- | --- | --- |
| **public** and declared on an interface implemented by the proxy | Interceptable via the interface proxy | Interceptable via the class proxy |
| **public** only on the implementation, not on the proxied interface | Not exposed through the JDK interface proxy | Interceptable if non-final and called through the proxy |
| **protected** | Not present on a JDK interface proxy | Interceptable if overridable and caller has valid access through the proxy |
| **package-visible** declared in the target class itself, with proxy subclass in the same package | Not present on a JDK interface proxy | Interceptable when Java visibility permits overriding |
| **package-visible** inherited from a superclass in a **different package** | Not present on a JDK interface proxy | Cannot be advised via normal subclassing because the method is **not visible to override** |
| **private** | Cannot be exposed via an interface as an instance business method | Cannot be overridden, so cannot be advised |
| **final instance method** | If public and on the interface, a JDK proxy can still intercept **calls through the interface proxy** | Cannot be overridden, so cannot be advised via CGLIB |
| **static method** | Not an instance call going through a JDK proxy | Not an overridden instance method on the proxy; Spring AOP does not intercept static calls |
| **constructor** | Not a method-execution call on a proxy | Spring AOP proxies do not apply advice to constructor execution |

**“Interceptable” does not mean guaranteed to be intercepted.** Spring still needs an advisor matching the method, the bean must actually be exposed through a proxy, and the caller must invoke it on the proxy. Methods excluded by visibility/finality do not become interceptable merely because a pointcut expression appears to match.

A subtle point: **`final`** on the implementation does not necessarily stop a **JDK dynamic proxy** from intercepting a **public interface method** call. The JDK proxy handles the call at the interface outside the target and does not subclass/override the implementation's `final` method. CGLIB, on the other hand, relies on subclass overriding and is subject to `final` constraints.

## 4. Public via Interface: The Standard Scope of a JDK Proxy

Consider:

~~~java
package demo;

public interface InventoryApi {
    void check();
}
~~~

And the implementation:

~~~java
package demo;

public class InventoryService implements InventoryApi {

    @Override
    public void check() {
        System.out.println("TARGET check");
    }

    public void reindex() {
        System.out.println("TARGET reindex");
    }
}
~~~

If Spring creates a JDK proxy, client code typically receives:

~~~java
InventoryApi service = context.getBean(InventoryApi.class);
service.check();
~~~

The **check()** call can pass through advice; however, **service.reindex()** does not compile because the **InventoryApi** type does not have this method. Even though the real target has a public **reindex()**, a JDK proxy implementing only the proxied interface does not automatically publish all implementation methods.

Do not fix this by casting:

~~~java
InventoryService concrete = (InventoryService) service;
~~~

With a typical JDK dynamic proxy, that cast causes a **ClassCastException** because the proxy **is not a subclass of InventoryService**. If **reindex()** needs to be called through an interface proxy, design a suitable interface; if you deliberately need to proxy class-only methods, consider class-based proxies and their corresponding limits.

**A public method on an interface still requires the call to go through the proxy.** If inside `InventoryService` there is **this.check()**, standard Spring AOP does not advise that internal call as a separate invocation.

## 5. CGLIB and Method Overridability

A class-based proxy uses a runtime subclass of the target to intercept calls. Therefore, it obeys Java's overriding rules:

- **public**: generally overridable when non-final, and convenient to invoke externally through the proxy.
- **protected**: overridable; from code in the same package or an appropriate subclass, it can be called through the proxy and intercepted.
- **package-visible**: overridable if the method is actually visible from the subclass. When the target and proxy are defined in the same package, this is allowed; if the method is in a superclass in a different package, it can be **effectively private** to a subclass in the target's package.
- **private**: not inherited as an overridable method; CGLIB cannot override it.
- **final**: prevents subclass overriding; a **final** class cannot have a CGLIB subclass generated.
- **static**: a class-bound call, not overridden like an instance method.

Additional note: to call a **protected** or **package-visible** method of a bean from an external class, the calling code must still satisfy **Java access control rules**. Spring using CGLIB does not make protected or package-visible methods public. That is why the runnable example below keeps **App** and the service in **the same demo package**.

An easy-to-remember summary: **JDK proxies are bounded by the exposed interfaces; CGLIB is bounded by subclassing and overridability.** Both are also constrained by the call path.

## 6. Runnable Maven Example: Same Service, Two Proxy Types

We create two **independent ApplicationContexts**. The first context enables JDK proxies, and the second enables CGLIB. Both use the same **VisibilityService** class, the same pointcut, and the same service structure. By creating two independent contexts, we avoid switching annotations mid-run or mixing two proxy modes in a single container.

Requirements: **Java 17+**, **Maven 3.9+**, **Spring Framework 6.2.12**. This is a plain Spring console application without Spring Boot.

~~~text
spring-aop-method-visibility/
├── pom.xml
└── src/main/java/demo/
    ├── ServiceApi.java
    ├── VisibilityService.java
    ├── VisibilityAspect.java
    └── App.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-method-visibility</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**spring-context** brings along the required core container and Spring AOP modules. **aspectjweaver** supplies the AspectJ annotation and pointcut expression types used by Spring AOP; this example remains **proxy-based**, without compile-time or load-time weaving.

### 6.2. Interface Exposing Only Public Methods

**src/main/java/demo/ServiceApi.java**

~~~java
package demo;

public interface ServiceApi {
    void publicWork();
    void internalFlow();
}
~~~

The **public** Java interface exposes only **publicWork()** and **internalFlow()** to JDK proxy clients. Interfaces do not contain protected or package-visible abstract instance methods in the API-contract sense. Likewise, neither **protectedWork()** nor **packageWork()** exists on the interface.

### 6.3. Service Containing All Visibility Levels

**src/main/java/demo/VisibilityService.java**

~~~java
package demo;

public class VisibilityService implements ServiceApi {

    @Override
    public void publicWork() {
        System.out.println("TARGET publicWork");
    }

    public void implementationOnly() {
        System.out.println("TARGET implementationOnly");
    }

    protected void protectedWork() {
        System.out.println("TARGET protectedWork");
    }

    void packageWork() {
        System.out.println("TARGET packageWork");
    }

    private void privateWork() {
        System.out.println("TARGET privateWork");
    }

    @Override
    public void internalFlow() {
        System.out.println("TARGET internalFlow");
        this.protectedWork();
        this.packageWork();
        this.privateWork();
    }
}
~~~

Here:

- **publicWork()**: public and in **ServiceApi**.
- **implementationOnly()**: public but not in the interface.
- **protectedWork()**: protected, callable from **App** in the same `demo` package.
- **packageWork()**: package-visible due to having no access modifier keyword, callable from **App** in the same package.
- **privateWork()**: private, callable only inside the class; cannot be called directly on the Spring proxy from `App`.
- **internalFlow()**: public and in the interface, but invokes protected, package-visible, and private methods via **this**. None of these three internal calls pass through the proxy automatically.

### 6.4. Aspect Recording Method Names Before Entering the Target

**src/main/java/demo/VisibilityAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class VisibilityAspect {

    @Before("execution(* demo.VisibilityService.*(..))")
    public void before(JoinPoint joinPoint) {
        System.out.println(
                "ADVICE " + joinPoint.getSignature().getName());
    }
}
~~~

**@Before** is invoked by Spring AOP when a **method execution** matches the pointcut and the invocation passes through the proxy. The pattern **execution(* demo.VisibilityService.*(..))** intentionally omits the `public` keyword because this lesson also tests `protected` and package-visible methods.

A pointcut expression can name a method, yet **it does not expand the technical capabilities of a proxy**. If CGLIB cannot override a method, or if the method is called directly via **this**, advice will not run for that call.

The aspect is registered via a **@Bean** method in configuration so it does not need **@Component**; merely adding **@Aspect** without registering it as a Spring bean is not enough.

### 6.5. Running Two Independent ApplicationContexts

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class App {

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy
    static class JdkConfig {

        @Bean
        public ServiceApi service() {
            return new VisibilityService();
        }

        @Bean
        public VisibilityAspect visibilityAspect() {
            return new VisibilityAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class CglibConfig {

        @Bean
        public VisibilityService service() {
            return new VisibilityService();
        }

        @Bean
        public VisibilityAspect visibilityAspect() {
            return new VisibilityAspect();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(JdkConfig.class)) {

            ServiceApi service = context.getBean(ServiceApi.class);

            System.out.println("=== JDK ===");
            System.out.println(
                    "JDK_PROXY " + AopUtils.isJdkDynamicProxy(service));

            service.publicWork();
            service.internalFlow();
        }

        try (var context =
                     new AnnotationConfigApplicationContext(CglibConfig.class)) {

            VisibilityService service =
                    context.getBean(VisibilityService.class);

            System.out.println("=== CGLIB ===");
            System.out.println(
                    "CGLIB_PROXY " + AopUtils.isCglibProxy(service));

            service.publicWork();
            service.implementationOnly();
            service.protectedWork();
            service.packageWork();
            service.internalFlow();
        }
    }
}
~~~

Configuration explanation:

1. **JdkConfig**: returns the bean under the **ServiceApi** contract, while **@EnableAspectJAutoProxy** defaults to preferring JDK dynamic proxies when the target has interfaces. The client retrieves the service by its interface.
2. **CglibConfig**: enables **@EnableAspectJAutoProxy(proxyTargetClass = true)**, explicitly selecting class-based proxies. The client retrieves it by **VisibilityService.class**, gaining access to protected/package-visible methods within the same package.
3. Both contexts register **VisibilityAspect**, yet **each context has its own instance**, rather than two aspect beans in one context.
4. **@Bean** creates **VisibilityService** as a Spring-managed bean. Only calls through the bean returned by the container follow the Spring AOP proxy path.
5. **@Configuration(proxyBeanMethods = false)** handles only interception of **@Bean** methods in the configuration class; it **does not disable AOP mode** for services, because **@EnableAspectJAutoProxy** remains enabled.
6. **@Before** is a simple advice printing the method name so you can see exactly which methods are intercepted.

In a **Spring Boot** project, proxy-type selection can be affected by Boot AOP auto-configuration; this example uses **plain Spring Framework** to compare the two modes cleanly.

## 7. Running and Reading Stdout

In the project directory containing `pom.xml`, run:

~~~bash
mvn -q clean compile exec:java
~~~

Expected logical output, ignoring Maven messages and framework logging:

~~~text
=== JDK ===
JDK_PROXY true
ADVICE publicWork
TARGET publicWork
ADVICE internalFlow
TARGET internalFlow
TARGET protectedWork
TARGET packageWork
TARGET privateWork
=== CGLIB ===
CGLIB_PROXY true
ADVICE publicWork
TARGET publicWork
ADVICE implementationOnly
TARGET implementationOnly
ADVICE protectedWork
TARGET protectedWork
ADVICE packageWork
TARGET packageWork
ADVICE internalFlow
TARGET internalFlow
TARGET protectedWork
TARGET packageWork
TARGET privateWork
~~~

### 7.1. JDK Observations

- **JDK_PROXY true** shows Spring returned a JDK dynamic proxy.
- **publicWork()** is declared on the interface, so the client calls through the proxy and advice appears before the target.
- **internalFlow()** is also a public interface method, so the external call is advised.
- Inside **internalFlow()**, the protected/package-visible/private methods are called on the target's **this**; there are no **ADVICE protectedWork**, **ADVICE packageWork**, or **ADVICE privateWork** lines.
- **implementationOnly()** cannot be invoked on a **ServiceApi** variable. This is an API boundary of the JDK proxy, not a pointcut error.

### 7.2. CGLIB Observations

- **CGLIB_PROXY true** shows Spring returned a class-based proxy of `VisibilityService`.
- **publicWork()** is intercepted just like with JDK.
- **implementationOnly()** is intercepted when called from `App` through the class proxy, even though the method is not on the interface.
- **protectedWork()** and **packageWork()** are intercepted because they are overridable in the proxy subclass and `App` in the same **demo** package invokes them directly on the proxy.
- **internalFlow()** is intercepted on the external call. However, the three calls **this.protectedWork()**, **this.packageWork()**, and **this.privateWork()** inside the target still bypass the proxy, so only **TARGET** lines appear.

**Key takeaway:** “CGLIB can advise protected and package-visible methods” is a statement about **the ability to intercept calls passing through the proxy**, not a claim that every execution of those methods on the target triggers advice.

## 8. Why Calling `internalFlow()` Does Not Run the Three Inner Advices

Spring AOP uses proxies to intercept calls from outside:

~~~text
App
 |
 v
CGLIB proxy
 |
 +-- advice: internalFlow
 |
 v
VisibilityService.internalFlow()        <- target
 |
 +-- this.protectedWork() ------------- directly to target
 +-- this.packageWork() --------------- directly to target
 +-- this.privateWork() --------------- directly to target
~~~

The **this** keyword inside the body of **VisibilityService** refers to the currently executing target object; internal calls do not return to the proxy.

Both statements below can be true simultaneously:

- **App calls service.protectedWork() through the class-based proxy** → advice runs.
- **internalFlow() calls this.protectedWork() inside the target** → advice for `protectedWork` does not run.

To determine the exact path, you must know **which object the caller holds**. Do not look only at visibility or annotations on the method.

A controllable design when an operation needs advice is **placing that operation in another Spring bean** and calling it via an injected dependency. Avoid trying to patch self-invocation with casts or manual target instantiation.

## 9. Package-Visible: Same-Package vs. Different-Package Cases

A package-visible method has no **public/protected/private** keyword:

~~~java
package demo;

public class LocalService {
    void refreshCache() {
        System.out.println("refresh");
    }
}
~~~

Within the same `demo` package, a Spring CGLIB subclass can override **refreshCache()** if it is non-final; when a valid caller in the same package invokes it **through the proxy**, Spring AOP can run advice.

Now consider inheritance across two packages:

~~~text
src/main/java/
├── base/
│   └── BaseService.java     // package base
└── demo/
    └── DerivedService.java  // package demo, extends BaseService
~~~

**base/BaseService.java**

~~~java
package base;

public class BaseService {
    void hiddenOperation() {
        System.out.println("BASE hiddenOperation");
    }
}
~~~

**demo/DerivedService.java**

~~~java
package demo;

import base.BaseService;

public class DerivedService extends BaseService {
    public void run() {
        System.out.println("DERIVED run");
    }
}
~~~

**hiddenOperation()** is package-visible in **base**, not visible to a subclass in package **demo**. It cannot be overridden in the usual way by a CGLIB subclass in package `demo`; in this situation, it is **effectively private** from the subclass's perspective. Therefore, do not conclude “every package-private method is intercepted by CGLIB.”

The two files in this section are **Java visibility illustrations**, not wired into the `App` class or Spring configuration in section 6, and `hiddenOperation` cannot be called directly from `DerivedService` in package `demo`.

If business logic genuinely requires external calls to pass through advice, use a public method as an explicit entry point. Protected/package-visible methods are useful in narrow scopes, yet they require both Java access control and proxy overridability.

## 10. Limitations Not Caused by Visibility Levels

When comparing public/protected/package-visible, also verify **overridability** and **call paths**:

- CGLIB cannot subclass a `final class` and cannot override `final`/`private` instance methods; these methods are not advised through class-based proxies. Even a `public` method is not advised if it is `final`.
- By contrast, a JDK proxy can intercept a public interface method even when the implementation is declared `final`, because interception occurs at the interface boundary without needing to override the target method.
- `static` methods do not dispatch through an instance proxy; constructors are also not Spring AOP method-execution join points.
- Even a public overridable method skips advice when the target calls `this.method()` instead of a client calling through the proxy.

These conditions are independent of whether the caller has access rights to protected/package-visible methods. To confirm a call will be advised, check all of: proxy type, overridability, pointcut, and invocation path.

## 11. Pointcuts Can Restrict to Public, but Cannot Force Protected to Become Public

In the aspect from section 6:

~~~java
@Before("execution(* demo.VisibilityService.*(..))")
public void before(JoinPoint joinPoint) {
    // ...
}
~~~

The **execution** expression specifies no modifier, so at the pointcut level it can describe multiple visibility levels. **The proxy remains the execution boundary**.

To match only public methods:

~~~java
@Before("execution(public * demo.VisibilityService.*(..))")
public void beforePublic(JoinPoint joinPoint) {
    // ...
}
~~~

This is an **illustrative pointcut variant**; when testing, replace the annotation/method in the existing aspect or create a separate test context to avoid keeping both the old and new advice and miscounting log lines.

When running with CGLIB:

- `publicWork`, `implementationOnly`, and `internalFlow` can match **public**.
- `protectedWork` and `packageWork` **do not** match an expression specifying the **public** modifier.
- `privateWork` still cannot be advised by a Spring AOP proxy even if you write a pointcut naming it.

In AspectJ pointcut syntax, **the visibility of a `@Pointcut` method used for reusing an expression** and **the visibility of the target method in `execution()`** are two separate things. Making a **@Pointcut**-annotated method `private` does not narrow the join points its pointcut expression can match.

## 12. Distinguishing Technical AOP Rules from `@Transactional`

Spring often uses similar proxies for **@Transactional**, **@Async**, and several other features. However, each feature also has **its own method-selection and metadata rules**. Do not infer solely from CGLIB mechanics that an annotation on any non-public method will always take effect.

For example, in **Spring Framework 6+**, transaction annotation support can process **protected** and **package-visible** methods on **class-based proxies** by default; with **interface-based proxies**, transactional methods must be **public and declared on the interface**. Transaction configuration also depends on **@EnableTransactionManagement**, a transaction manager, and transaction metadata detection rules.

For **Spring AOP @AspectJ @Before** in this lesson, the core point is that Spring evaluates the **execution pointcut** on interceptable method invocations. **@Transactional** is another example using proxies, yet it adds its own layer of rules. When testing a specific feature, read that feature's documentation and do not equate “proxied” with “transaction/advice applied.”

## 13. CGLIB Does Not Automatically Expand Caller Access Rights

Suppose **App** moves to another package (for example, **client**) and does not extend `VisibilityService`; Java will not compile these calls:

~~~java
service.protectedWork();
service.packageWork();
~~~

Even if **service** is a class-based proxy, source code outside the package must still obey Java access rules. Spring wrapping a bean does not turn protected/package-visible methods into public APIs.

Therefore, in large application design:

- Public service methods are usually the easiest contracts to use and test.
- Protected is typically intended for subclass extension hooks; calling via proxy requires the right Java context.
- Package-visible makes sense within a package; it is not an exposed API across modules/packages.
- If a method needs advice when called from another module, consider creating a public entry point on a Spring-managed bean with clear pointcuts and dependencies.

## 14. Case of a Method Not on the JDK Proxy Interface

`VisibilityService` has public **implementationOnly()**, yet **ServiceApi** does not declare this method. Under a JDK proxy:

~~~java
ServiceApi proxy = context.getBean(ServiceApi.class);
proxy.publicWork();       // Valid
// proxy.implementationOnly(); // Does not compile
~~~

Two design directions:

1. **Add the method to a suitable interface** if it genuinely belongs to the business contract that should be exposed. Then the JDK proxy can expose the method.
2. **Choose CGLIB** if you need to expose public implementation methods without an interface, while accepting inheritance and final/private constraints.

Do not use **ProxyTargetClass** merely to fix a cast without weighing API design. If other consumers inject the same bean by interface, switching from JDK to CGLIB can affect type checks, pointcuts, and class-dependent behavior.

## 15. Common Misunderstandings in Spring AOP

| Claim | Accurate assessment |
| --- | --- |
| “Spring AOP only intercepts public methods in all cases.” | False in general: **CGLIB** can intercept protected/package-visible methods if overridable, caller access is valid, and calls go through the proxy |
| “Using `@Aspect` can intercept every private method.” | False: Spring AOP proxies do not override private methods |
| “CGLIB intercepts protected methods regardless of who calls.” | False: calls must go through the proxy; Java visibility still applies |
| “Package-private is intercepted even when declared in a superclass in another package.” | False: if not visible to override from the proxy subclass, the method is effectively private |
| “`final` methods can never be advised under any proxy type.” | False: `final` blocks **CGLIB overriding**; JDK interface proxies can still advise public interface calls |
| “Since the method is public on the implementation, the JDK proxy sees it.” | False: a JDK proxy exposes the proxy's interface methods, not the entire implementation |
| “CGLIB intercepts `this.protectedWork()` as well.” | False: self-invocation on the target bypasses the proxy |
| “`@EnableAspectJAutoProxy` registers services as beans automatically.” | False: component scanning, `@Bean`, or another bean registration mechanism is still needed |
| “`AopUtils.isAopProxy(bean) = true` proves this method is advised.” | Insufficient: you must verify the pointcut and actual call path |
| “Protected methods can be called from a class in any package once `proxyTargetClass` is enabled.” | False: Java access control does not change |
| “Adding `public` to an `execution` pointcut will intercept protected methods.” | False: the `public` modifier narrows the pointcut |
| “Choosing CGLIB fixes every missing transaction or advice bug.” | False: the cause may be bean registration, pointcuts, metadata, or self-invocation |

## 16. Investigation Workflow When Advice Is Missing

Follow this order to avoid guessing:

### Step 1 — Confirm the Bean Comes from ApplicationContext

~~~java
Object service = context.getBean("service");
System.out.println(
        org.springframework.aop.support.AopUtils.isAopProxy(service));
~~~

If you do **new VisibilityService()** manually and call it directly, Spring AOP does not intercept that instance. This snippet is a debug fragment requiring a valid **context** variable.

### Step 2 — Determine the Proxy Type

~~~java
System.out.println(
        org.springframework.aop.support.AopUtils.isJdkDynamicProxy(service));
System.out.println(
        org.springframework.aop.support.AopUtils.isCglibProxy(service));
~~~

If it is a JDK proxy, verify the method to call **is on an exposed interface**. If it is a CGLIB proxy, verify the method is overridable and caller access is valid.

### Step 3 — Check the Pointcut

For example, the wildcard **execution(* demo.VisibilityService.*(..))** can match eligible public/protected/package-visible methods. If the pointcut specifies **execution(public ...)**, protected/package-visible methods are excluded by the expression.

Also, the package/class in the pointcut must match the actual service. Do not assume advice runs merely by changing visibility.

### Step 4 — Trace the Call Path

Put logging in **@Before**, then compare with logs inside the target. If advice logs appear when called from `App` yet are missing when the target calls **this.method()**, it is self-invocation, not a failure of Spring to see the method.

### Step 5 — Inspect `final`, `private`, and the Inheritance Hierarchy

- `final` classes cannot create CGLIB subclasses.
- `final` or `private` methods cannot be overridden.
- Package-visible methods on a superclass in another package may not be visible to the proxy subclass.
- If the method is invoked statically, it does not go through an instance proxy.

### Step 6 — Verify Configuration

You can use:

~~~java
@EnableAspectJAutoProxy(proxyTargetClass = true)
~~~

to request class-based proxies in the corresponding context. At the same time, **@Aspect** must be registered as a Spring bean via **@Component** or **@Bean**. An annotation on the class is insufficient if the bean is not in the `ApplicationContext`.

## 17. Verification Exercises

**Exercise A — Public-only via CGLIB.** Change the pointcut to **execution(public * demo.VisibilityService.*(..))** and rerun the CGLIB context. Observe that advice appears only before public methods invoked through the proxy; protected/package-visible methods still print target lines without advice from the public-only pointcut.

**Exercise B — Add public implementation-only to the interface.** Add **void implementationOnly()** to `ServiceApi`, then call it in the JDK section. Observe that the JDK proxy now exposes the method through the interface and can run advice for that call.

**Exercise C — Make `protectedWork` final.** You cannot simultaneously declare a method `final` in the base class and override it in a subclass; CGLIB does not advise `protectedWork` by overriding. Compare with intercepting **publicWork()**, which continues working. This is a source-editing experiment to rerun, not a change to apply to production services.

**Exercise D — Move `App` to another package.** Try calling `protectedWork`/`packageWork` in `App` from another package to see compile-time errors from Java visibility. CGLIB does not replace access control rules.

**Exercise E — Call again from `internalFlow()`.** Count the advice lines before `protectedWork` or `packageWork` when called directly via the proxy, then compare against internal calls. Explain the difference via the invocation path.

## 18. Self-Check Questions

**1. Can a JDK dynamic proxy advise a public method on the implementation that is not on the proxied interface?**

Not along calls through that JDK interface proxy: the proxy does not expose implementation-only methods. To invoke through a proxy, change the interface API or choose a class-based proxy.

**2. Can CGLIB advise a `protected` method?**

Yes, when the method is overridable, within the visible scope of the proxy subclass, matched by a pointcut, and the caller actually invokes it through the proxy in a valid Java context.

**3. Which package-visible method cannot be advised by CGLIB despite matching the method name?**

An example is a package-visible method declared in a superclass in a **different package**, making the proxy subclass unable to override it because it is effectively private from the subclass's perspective.

**4. Why does `@Before` appear when `App` calls `protectedWork` through the proxy, yet does not appear when `internalFlow` calls `this.protectedWork`?**

Because `App` calls through the proxy; the **this** call inside the target is a direct internal call and does not return to the proxy.

**5. Is a `final` public method implementing an interface always outside Spring AOP?**

No. A JDK interface proxy can advise a public interface call even when the implementation method is `final`. The `final` restriction directly blocks CGLIB's overriding mechanism.

**6. Does placing a broad pointcut across an entire class make `private` methods proxy-intercepted join points?**

No. An expression being able to match a method name does not bypass overriding restrictions or Spring AOP's proxy call structure.

**7. If a service is proxied yet no advice runs on a package-visible method, what should you check?**

Determine whether the proxy is JDK or CGLIB, whether the method is visible and overridable, whether the caller invokes via the proxy or **this**, and whether the pointcut matches.

**8. What should you do to build a Spring service API that stays stable across JDK and CGLIB?**

Prefer **public service methods** with clear contracts; if interface-driven, declare methods needing interception on the interface. Rely on protected/package-visible interception only when genuinely needed and tested for the proxy type in use.

## 19. Official Spring Documentation

- Spring Framework 6.2 — **Proxying Mechanisms** (JDK proxy, CGLIB, final/private/effectively-private, and self-invocation): https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Framework — **Declaring a Pointcut** (public interface methods, public/protected/package-visible on CGLIB, and execution modifiers): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework — **AOP Proxies**: https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html
- Spring Framework — **@AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — **Using @Transactional** (visibility rules specific to transaction annotations in proxy mode): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html

**Technical conclusion:** Spring AOP's scope is determined by **proxy type + method exposure/overridability + pointcut + call path**. With a **JDK proxy**, clients use public interface methods. With **CGLIB**, calls through the proxy can be advised on public, protected, and package-visible methods when Java permits overriding and access; private/final/static methods or self-invocation cannot be handled by that same proxy mechanism.
