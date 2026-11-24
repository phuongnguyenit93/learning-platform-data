# AopContext.currentProxy(), exposeProxy, and why to limit their use in Spring AOP

## 1. Lesson objectives

In Spring AOP, advice is applied only to **calls passing through an AOP proxy**. A service may be returned by the container as a proxy, yet inside the target itself, a **`this.method()`** call does not go back out through the proxy. That is why a method with an annotation, or matching a pointcut, can still fail to run advice when invoked internally.

Spring provides two mechanisms directly related to this situation:

- **`AopContext.currentProxy()`**: retrieves the **proxy of the active Spring AOP invocation** on the current thread.
- **`exposeProxy = true`**: configures Spring to store the active proxy in thread context so `currentProxy()` can retrieve it.

This mechanism can turn an internal call into a proxied call, yet it is **not a recommended design direction**. It creates a dependency between business code and Spring AOP, requires special configuration, depends on the call path and thread, and adds overhead.

After this lesson, you will:

1. Distinguish the target's **`this`** from the **Spring AOP proxy**.
2. Understand the conditions under which **`AopContext.currentProxy()`** returns a proxy or throws **`IllegalStateException`**.
3. Use **`@EnableAspectJAutoProxy(exposeProxy = true)`** in plain Spring Framework configuration.
4. Run a Java 17+ example showing **`this.inner()`** bypasses advice while **`((ServiceApi) AopContext.currentProxy()).inner()`** goes through advice.
5. Recognize limitations involving JDK dynamic proxies, CGLIB, callbacks, new threads, self-invocation, `final`/`private`, and recursion.
6. Prefer refactoring into **two Spring beans with explicit dependencies**, rather than pulling `AopContext` into services.

**Scope:** Discusses only **Spring Framework proxy-based AOP** and how `currentProxy`/`exposeProxy` affect calls on Spring-managed beans. Does not delve into general Aspect theory or AspectJ weaving.

## 2. Root problem: self-invocation bypasses the proxy

Suppose Spring returns proxy P for target T:

~~~text
Client
   |
   v
Spring AOP proxy P
   |
   +-- evaluates advisor/pointcut
   +-- runs matching advice
   |
   v
Target T.outer()
   |
   +-- this.inner() ------> T.inner()
                             |
                             +-- does not return to proxy P
~~~

When a client calls **`outer()`** through the proxy, the outer call is handled by Spring AOP. Yet when **`T.outer()`** calls **`this.inner()`**, **`this`** refers to **target T**, not P. Therefore, advice attached to **`inner()`** receives no new proxy invocation to execute.

Example:

~~~java
public class OrderService {
    public void place() {
        this.validate();
    }

    public void validate() {
        // Order validation logic
    }
}
~~~

This is an **illustrative self-invocation snippet**, without Spring bean or standalone aspect configuration. If advice matches only **`validate()`**, the call from **`place()`** to **`this.validate()`** will not run that advice when Spring uses proxy-based AOP.

Two important points:

- **A proxied bean** does not mean **every method invocation** passes through the proxy.
- **A CGLIB proxy** does not automatically cure self-invocation. Even though the proxy is a subclass, Spring AOP still has a call boundary: a call originating inside the target that does not loop back through the proxy bypasses advice.

When an operation needs advice, good design usually **calls that operation through a Spring-managed dependency on another bean**.

## 3. What is `AopContext.currentProxy()`?

Spring provides the API:

~~~java
org.springframework.aop.framework.AopContext.currentProxy()
~~~

This static method returns **`Object`**, representing the **AOP proxy currently exposed by Spring on the current thread**. It takes no bean name or target class; thus it is **not an API for looking up an arbitrary bean from `ApplicationContext`**.

Successful use requires all of the following conditions simultaneously:

1. Execution is currently inside **a call through a Spring AOP proxy** with proxy exposure enabled.
2. That proxy is configured with **`exposeProxy = true`**.
3. The call to **`currentProxy()`** happens **on the same thread** as the exposed invocation, while that invocation is still active.
4. The returned object is the current proxy; when casting, the type must be compatible with the interfaces/class exposed by the proxy.

If no corresponding proxy is active, `currentProxy()` **throws `IllegalStateException`**, rather than returning **`null`** as a signal you can casually ignore.

Examples that fail these conditions:

- Calling `currentProxy()` inside **`main()`**, outside any Spring AOP invocation.
- Calling inside a constructor or **`@PostConstruct`** expecting the current proxy to already exist.
- Calling on a target created directly with **`new`** and used outside the container.
- Calling from code running on a **different thread** than the invocation (such as work offloaded to an executor) without a new proxy invocation on that thread.
- The proxy was created, yet **`exposeProxy`** remains at its default **`false`**.

**`AopContext`** uses a **`ThreadLocal`**-based holder. Spring manages setting the current proxy, restoring the previous proxy after the call, and clearing the holder when appropriate; applications must not assume they can hold that object as a cross-thread or cross-request context, or use it after the invocation has ended.

## 4. What is `exposeProxy` and where is it enabled?

**`exposeProxy`** is an attribute of Spring AOP proxy configuration; it defaults to **`false`**. When enabled, Spring publishes the proxy handling the invocation so **`AopContext.currentProxy()`** can access it.

With **plain Spring Framework** and annotation-based AOP:

~~~java
@Configuration
@EnableAspectJAutoProxy(exposeProxy = true)
public class AppConfig {
}
~~~

You still must **register the aspect and service as Spring beans** via **`@ComponentScan`**, **`@Bean`**, or an equivalent mechanism. The annotation above is only a configuration snippet; it does not create services, aspects, or pointcuts by itself.

Compare:

~~~java
@EnableAspectJAutoProxy
~~~

and:

~~~java
@EnableAspectJAutoProxy(exposeProxy = true)
~~~

Both enable Spring AOP auto-proxying in the corresponding context. The second line **adds exposing the current proxy**. It does not alter the meaning of **`@Before`**, **`@Around`**, pointcut matching conditions, bean registration, or a class-based proxy's inability to intercept **`private`/`final`** methods.

Another easily confused setting:

~~~java
@EnableAspectJAutoProxy(proxyTargetClass = true)
~~~

The **`proxyTargetClass`** attribute selects class-based proxies (CGLIB) instead of defaulting to JDK dynamic proxies when applicable. The **`exposeProxy`** attribute determines whether the current proxy is exposed via `AopContext`. The two attributes are **independent in purpose**:

~~~java
@EnableAspectJAutoProxy(
    proxyTargetClass = true,
    exposeProxy = true
)
~~~

When using **`ProxyFactory`** programmatically instead of annotation-based auto-proxying:

~~~java
factory.setExposeProxy(true);
~~~

is the equivalent setting **on that proxy factory**. This snippet assumes **`factory`** is an already created **`org.springframework.aop.framework.ProxyFactory`** instance configured with target/advice; it is not a standalone Java file.

## 5. Complete Java 17+ example: `this.inner()` vs. calling back through the proxy

We build a project with **Spring Framework 6.2.12, Java 17+, Maven 3.9+**. The example needs no Spring Boot, database, or web server. One service has three methods:

- **`direct()`**: calls **`this.inner("direct")`**, advice for `inner` **does not run**.
- **`viaProxy()`**: calls **`((Operations) AopContext.currentProxy()).inner("viaProxy")`**, advice for `inner` **runs** when `exposeProxy` is enabled and the outer call passes through the proxy.
- **`inner(String)`**: the method selected by the pointcut.

### 5.1. Directory structure

~~~text
spring-aop-current-proxy/
├── pom.xml
└── src/main/java/demo/
    ├── Operations.java
    ├── OperationsImpl.java
    ├── InnerAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 5.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-current-proxy</artifactId>
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

**`spring-context`** provides Spring `ApplicationContext` and pulls in Spring AOP. **`aspectjweaver`** provides AspectJ annotation/pointcut support so Spring can process **`@AspectJ`-style advice**. This is **still Spring AOP proxying**, not AspectJ compile-time or load-time weaving.

### 5.3. Service interface

**`src/main/java/demo/Operations.java`**

~~~java
package demo;

public interface Operations {
    void direct();
    void viaProxy();
    void inner(String source);
}
~~~

All three methods are placed on the interface so the example works with the default **JDK dynamic proxy**. When **`AopContext.currentProxy()`** returns a JDK proxy, casting to **`Operations`** is valid; casting to **`OperationsImpl`** is unsafe.

### 5.4. Service implementing both call paths

**`src/main/java/demo/OperationsImpl.java`**

~~~java
package demo;

import org.springframework.aop.framework.AopContext;
import org.springframework.stereotype.Service;

@Service
public class OperationsImpl implements Operations {

    @Override
    public void direct() {
        System.out.println("OUTER direct");
        this.inner("direct");
    }

    @Override
    public void viaProxy() {
        System.out.println("OUTER viaProxy");
        Operations proxy = (Operations) AopContext.currentProxy();
        proxy.inner("viaProxy");
    }

    @Override
    public void inner(String source) {
        System.out.println("TARGET inner " + source);
    }
}
~~~

The only difference between the two entry methods is **the receiver of the `inner()` call**:

- In **`direct()`**, the receiver is **`this`**, meaning the current target. There is no second call entering the proxy.
- In **`viaProxy()`**, the receiver is the **`proxy`** Spring is exposing. The `inner()` call loops back through the proxy and is evaluated by advisors.

Note: **`AopContext.currentProxy()`** is valid only along a call path meeting all conditions described in section 3. Thus this code is **no longer a standalone POJO**: it depends specifically on Spring AOP.

### 5.5. Aspect matching only `inner()`

**`src/main/java/demo/InnerAspect.java`**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class InnerAspect {

    @Before("execution(* demo.OperationsImpl.inner(..))")
    public void beforeInner(JoinPoint joinPoint) {
        Object source = joinPoint.getArgs()[0];
        System.out.println("ADVICE inner " + source);
    }
}
~~~

This is a **Spring-managed aspect bean**:

- **`@Aspect`**: declares advice.
- **`@Component`**: lets component scanning register the aspect bean.
- **`@Before`**: matches only **`inner(...)`** on the implementation; **`direct()`** and **`viaProxy()`** have no dedicated advice in this example.

This highlights a subtle point: **`viaProxy()`** does not need its own **`@Before` advice** for `currentProxy()` to work, as long as the **`Operations` bean is genuinely a proxy** and the outer call is running inside a proxy invocation configured with `exposeProxy`. Spring still passes through the proxy layer when the client calls **`viaProxy()`**, even if the interceptor list for that specific method is empty.

### 5.6. Enabling component scan and `exposeProxy`

**`src/main/java/demo/AppConfig.java`**

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy(exposeProxy = true)
public class AppConfig {
}
~~~

The configuration does three independent things:

1. **`@Configuration`**: Java configuration class for Spring.
2. **`@ComponentScan`**: registers **`OperationsImpl`** and **`InnerAspect`** as Spring beans.
3. **`@EnableAspectJAutoProxy(exposeProxy = true)`**: enables Spring AOP infrastructure and exposes the current proxy to `AopContext`.

Keeping **`exposeProxy = true`** without any advisor applying to a service does not cause Spring to create a proxy for every bean automatically. In this example, an advisor matches `inner()`, so **`OperationsImpl`** is eligible to be Spring-proxied.

### 5.7. Running `App` and verifying the error outside an AOP invocation

**`src/main/java/demo/App.java`**

~~~java
package demo;

import org.springframework.aop.framework.AopContext;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            Operations operations = context.getBean(Operations.class);
            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(operations));

            System.out.println("=== direct ===");
            operations.direct();

            System.out.println("=== via proxy ===");
            operations.viaProxy();

            System.out.println("=== outside ===");
            try {
                AopContext.currentProxy();
                System.out.println("OUTSIDE unexpected success");
            } catch (IllegalStateException expected) {
                System.out.println("OUTSIDE IllegalStateException");
            }
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

Expected **logical stdout** lines, excluding separate messages from Maven or logging configuration:

~~~text
IS_PROXY true
=== direct ===
OUTER direct
TARGET inner direct
=== via proxy ===
OUTER viaProxy
ADVICE inner viaProxy
TARGET inner viaProxy
=== outside ===
OUTSIDE IllegalStateException
~~~

Order explanation:

1. **`IS_PROXY true`**: Spring returns the **`Operations`** bean as an AOP proxy with an advisor applying to **`inner`**.
2. When calling **`operations.direct()`**, Spring passes through the proxy for `direct`; then the target calls **`this.inner()`**. There is no **`ADVICE inner direct`**.
3. When calling **`operations.viaProxy()`**, the target accesses the current proxy and calls **`inner()`** on that proxy. Advice runs before the target, producing **`ADVICE inner viaProxy`**.
4. After the **`viaProxy()`** invocation ends, Spring restores the proxy state in `ThreadLocal`. Code in **`main()`** is no longer inside an AOP invocation, so **`AopContext.currentProxy()`** throws **`IllegalStateException`** even though `exposeProxy` is enabled in the context.

The **`OUTSIDE IllegalStateException`** line is printed by an intentional catch to demonstrate the API contract. In real applications, do not rely on exceptions as a casual way to probe beans/proxies.

## 6. Self-checking the effect of `exposeProxy`

### 6.1. Turning off `exposeProxy` while keeping AOP

In **`AppConfig.java`**, change:

~~~java
@EnableAspectJAutoProxy(exposeProxy = true)
~~~

to:

~~~java
@EnableAspectJAutoProxy
~~~

Restart the same application. Spring still creates the AOP proxy to apply advice to **`inner()`**, yet does not expose the proxy on the thread.

When **`operations.direct()`** runs, behavior remains the same:

~~~text
=== direct ===
OUTER direct
TARGET inner direct
~~~

When **`operations.viaProxy()`** runs:

~~~text
=== via proxy ===
OUTER viaProxy
~~~

Then **`AopContext.currentProxy()` throws `IllegalStateException`** because `exposeProxy` is not enabled. In **`App.java`** from section 5, there is no `try/catch` around **`operations.viaProxy()`**, so **`main()` will terminate with an error** instead of printing the **`=== outside ===`** section. That is the **expected outcome of the failure experiment**, not a guaranteed full stdout from a Maven run.

To keep the program running and observe the outside section too, you can temporarily replace that call with:

~~~java
try {
    operations.viaProxy();
} catch (IllegalStateException expected) {
    System.out.println("VIA_PROXY IllegalStateException");
}
~~~

This is a **replacement snippet inside `App.main`**, not to be used simultaneously with the old call. After verifying, restore **`exposeProxy = true`** to rerun the complete version.

Conclusion: **having a Spring proxy** and **having a current proxy available for `currentProxy()`** are two separate conditions.

### 6.2. Calling an object created with `new`

Illustrative snippet:

~~~java
OperationsImpl direct = new OperationsImpl();
direct.direct();
~~~

Prints:

~~~text
OUTER direct
TARGET inner direct
~~~

That object was not obtained from the Spring `ApplicationContext`; **`direct()`** does not need `AopContext` so it still runs, yet there is no Spring AOP advice.

If you call:

~~~java
direct.viaProxy();
~~~

and no matching AOP invocation is active on the thread, `currentProxy()` will throw **`IllegalStateException`**. Creating objects via **`new`** does not activate Spring AOP.

### 6.3. Calling from another thread

Example illustrating the idea:

~~~java
Thread thread = new Thread(() -> {
    AopContext.currentProxy();
});
thread.start();
~~~

This is an **illustrative fragment** without exception handling on the new thread. The new thread **does not automatically inherit** the AOP proxy exposed in the calling thread's `ThreadLocal`. Unless a new AOP proxy invocation is created on that other thread, `currentProxy()` throws **`IllegalStateException`**.

Scenarios like **`@Async`**, executors, `CompletableFuture`, or asynchronous callbacks must all be analyzed by their actual execution thread. Even when the proxy is exposed on the outer call, that **does not turn `AopContext` into a request-scoped or asynchronous context**.

## 7. Why does calling via `AopContext` trigger advice?

Consider what ran in section 5:

~~~text
App
 |
 v
Operations proxy P: direct()
 |
 v
OperationsImpl target T: direct()
 |
 +-- this.inner() --> T.inner()
                        |
                        +-- inner advice does not run
~~~

The other path:

~~~text
App
 |
 v
Operations proxy P: viaProxy()
 |
 v
OperationsImpl target T: viaProxy()
 |
 +-- AopContext.currentProxy() --> proxy P
                                    |
                                    +-- P.inner("viaProxy")
                                             |
                                             +-- inner advice
                                             |
                                             +-- T.inner("viaProxy")
~~~

In the second case, a call originating from the target **is turned into a call to proxy P**. Spring AOP once again receives a valid **`inner()`** method invocation, so the advisor can apply.

This **does not alter the bytecode of `inner()`**, does not change the pointcut, and does not trigger advice for the earlier direct **`this.inner()`** call. The entire difference lies in **the receiver of the call**.

That is also why great caution is needed when writing **`currentProxy().someMethod()`**: accidentally calling the currently executing method can create an unwanted recursion chain.

## 8. Risk of infinite recursion or repeated advice execution

Suppose inside **`viaProxy()`** you mistakenly write:

~~~java
@Override
public void viaProxy() {
    Operations proxy = (Operations) AopContext.currentProxy();
    proxy.viaProxy();
}
~~~

This is an **erroneous code example**; do not replace the runnable file in section 5 unless intentionally testing the failure.

The call chain becomes:

~~~text
proxy.viaProxy()
  -> target.viaProxy()
      -> currentProxy().viaProxy()
          -> target.viaProxy()
              -> currentProxy().viaProxy()
                  -> ...
~~~

The code keeps calling the same entry method through the proxy, likely ending with **`StackOverflowError`**. If that method is also advised, advice can execute repeatedly on every iteration.

With **`@Around`** advice, there is another source of loops: re-invoking an advised method through the proxy without a recursion guard, or confusing **`ProceedingJoinPoint.proceed()`** with starting a new proxy invocation. **`proceed()`** continues the current invocation down the interceptor chain; **`currentProxy().someMethod()`** initiates a separate proxy call. The two operations are not equivalent.

Do not replace **`this`** calls with `currentProxy` mechanically. First identify exactly which method needs advice, which entry points are safe, and the resulting call graph after the change.

## 9. `currentProxy()` is not a way to fetch a target or an arbitrary bean

This API returns **the proxy of the current invocation**, not a `BeanFactory`, not a service locator, and not the raw target.

| Need | Appropriate API |
| --- | --- |
| Obtain a Spring bean from the container | Constructor injection, **`@Bean`** method parameter, or **`ApplicationContext.getBean(...)`** when justified |
| Continue the current advised invocation | **`ProceedingJoinPoint.proceed()`** inside **`@Around`** advice |
| Access the active proxy in the current invocation | **`AopContext.currentProxy()`**, only when `exposeProxy` is enabled |
| Verify whether an object is an AOP proxy | **`AopUtils.isAopProxy(object)`** |
| Determine whether a proxy uses JDK or CGLIB | **`AopUtils.isJdkDynamicProxy`** / **`AopUtils.isCglibProxy`** |
| Separate logic into a cleanly advised operation | Create another Spring bean and inject the dependency |
| Access the underlying target from AOP infrastructure | Use infrastructure APIs only when genuinely needed; do not treat `currentProxy` as the target |

Suppose **`currentProxy()`** returns a **JDK dynamic proxy** for **`Operations`**. Do not cast:

~~~java
OperationsImpl impl =
        (OperationsImpl) AopContext.currentProxy();
~~~

With a JDK proxy, this cast can throw **`ClassCastException`**. That is why the main example casts to **`Operations`**, the interface actually implemented by the proxy.

With CGLIB, the proxy is a subclass of the target if configuration and class modifiers allow it; casting to the target class can be valid, yet **it does not remove self-invocation, `final`/`private`, or `exposeProxy` constraints**.

## 10. Why does Spring recommend limiting its use?

The Spring Framework documentation on **Proxying Mechanisms** regards **`AopContext.currentProxy()`** as something to avoid when a better alternative exists. There are three practical groups of reasons.

### 10.1. Coupling between business logic and Spring AOP

A normal service only needs to implement its interface and call dependencies:

~~~java
public void process() {
    collaborator.run();
}
~~~

When changed to:

~~~java
public void process() {
    ((Operations) AopContext.currentProxy()).inner("work");
}
~~~

the service now knows it must execute under a **Spring AOP proxy** with `exposeProxy`. This reduces reusability outside Spring AOP environments, complicates plain Java unit tests, and can cause code to fail unexpectedly if proxy configuration changes.

This **hidden dependency** is absent from the service's constructor or interface. Someone reading the class may not realize that calling **`process()`** requires entering through a specially configured proxy.

### 10.2. Fragile runtime conditions

`currentProxy()` depends on **the current thread and invocation**. A service may work when called via a controller/injected proxy yet fail when:

- called directly in a unit test;
- instantiated via **`new`**;
- called inside a constructor/init callback;
- called from a callback executing after the proxy invocation has completed;
- dispatched to another thread;
- called in a context or proxy without `exposeProxy` enabled;
- advisors are reconfigured so the bean is no longer Spring-proxied.

The issue may surface only on one specific call path, making testing and diagnosis harder than with normal dependency injection.

### 10.3. Cost and blast radius of `exposeProxy`

Spring **does not expose the proxy by default**, partly because updating and restoring the `ThreadLocal` for proxy invocations incurs **extra overhead**. Do not quote percentage performance numbers without benchmarking under realistic load.

Enabling `exposeProxy` is not a "free" switch for every auto-proxied bean; avoid enabling it broadly just because one method has self-invocation. This matters especially when a system has many advice layers, deep nesting, or high throughput.

### 10.4. Possibility of getting the wrong current proxy in nested call chains

Suppose proxy A calls proxy B on the same thread; inside B's call, **`currentProxy()`** points to **the proxy of the active invocation B**, not necessarily A. When B finishes, Spring restores the previous proxy state. Code that blindly casts or caches `currentProxy()` without understanding nested contexts can end up with the wrong proxy type.

Thus `currentProxy()` is not equivalent to **"give me the proxy of this class at all times"**. Its exact meaning is **the proxy currently exposed by the active invocation on the current thread**.

## 11. Preferred alternative: splitting into two Spring beans

The lowest-coupling solution is **not calling back into an AOP-needed method on the same target**. Instead, create a bean that performs that method, and inject it into the orchestrating bean.

Example of an alternative design for order processing:

~~~text
OrderOrchestrator bean
         |
         | constructor injection
         v
OrderValidation bean/proxy
         |
         +-- matching @Before advice
         |
         v
OrderValidationImpl.validate(...)
~~~

Complete illustrative Java code for the main classes:

**`src/main/java/demo/ValidationApi.java`**

~~~java
package demo;

public interface ValidationApi {
    void validate(String id);
}
~~~

**`src/main/java/demo/ValidationService.java`**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class ValidationService implements ValidationApi {

    @Override
    public void validate(String id) {
        System.out.println("VALIDATE " + id);
    }
}
~~~

**`src/main/java/demo/OrderOrchestrator.java`**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OrderOrchestrator {

    private final ValidationApi validation;

    public OrderOrchestrator(ValidationApi validation) {
        this.validation = validation;
    }

    public void process(String id) {
        System.out.println("PROCESS " + id);
        validation.validate(id);
    }
}
~~~

**`src/main/java/demo/ValidationAspect.java`**

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class ValidationAspect {

    @Before("execution(* demo.ValidationService.validate(..))")
    public void beforeValidation() {
        System.out.println("ADVICE validate");
    }
}
~~~

These classes represent an **alternative architectural design**, not files to drop simultaneously into the **`spring-aop-current-proxy`** project while expecting section 5's exact stdout; adding them to the same `demo` package would cause the context to discover extra beans and advisors.

With a context having **`@ComponentScan("demo")`** and **`@EnableAspectJAutoProxy`** (without `exposeProxy`), retrieving **`OrderOrchestrator`** from Spring and calling **`process("A-1")`** on the bean is expected to produce these logical lines:

~~~text
PROCESS A-1
ADVICE validate
VALIDATE A-1
~~~

Why this is better:

1. **`OrderOrchestrator`** depends on **`ValidationApi`**, a plain Java contract.
2. **`ValidationService`** is an independent Spring bean and can be proxied when the pointcut matches.
3. The **`validation.validate(...)`** call from the orchestrator goes through an injected dependency, giving Spring the opportunity to supply an **AOP proxy**.
4. No `AopContext`, no `exposeProxy`, and no `ThreadLocal` dependency.
5. Unit tests can pass a fake **`ValidationApi`** via the constructor without booting Spring.
6. Business responsibilities and Spring AOP join points are cleanly separated.

This is the solution to prefer even when it means adding a small bean or interface.

## 12. Self-injection: another option, but handle with care

Another approach is letting the service receive a reference to **the bean's own Spring-managed interface**, then calling through that reference instead of **`this`**. Example **illustrating the idea**:

~~~java
@Service
public class ExampleService implements ExampleApi {

    private final ExampleApi self;

    public ExampleService(@Lazy ExampleApi self) {
        this.self = self;
    }

    @Override
    public void outer() {
        self.inner();
    }

    @Override
    public void inner() {
        // ...
    }
}
~~~

The fragment above requires an **`ExampleApi`** interface and imports for **`@Service`**, **`@Lazy`**, plus AOP configuration; it is not part of section 5's runnable project. **`@Lazy`** at the injection point can have Spring create a lazy-resolution proxy and resolve the bean later; this approach requires careful testing.

Its advantage over `AopContext` is avoiding static API calls and `exposeProxy`. However, it introduces a **self-reference** into the dependency graph, which can create circular dependencies or subtle initialization scenarios; you must also stay aware of whether the bean is proxied by interface or class. Spring documentation mentions this as an alternative, yet **refactoring to avoid self-invocation** remains cleaner.

**Do not** automatically add self-injection to every service. In particular, a direct constructor dependency cycle is not justified merely to make advice run on an internal method.

## 13. An important scenario: `@Transactional` and other advice

Spring also uses proxies for features like declarative transactions, security, caching, or custom aspects. Self-invocation consequences can be similar when a feature operates in **proxy mode**:

~~~java
public void outer() {
    this.innerTransactional();
}
~~~

If **`innerTransactional()`** only receives transaction advice when called through a proxy, **`this.innerTransactional()`** is not processed by proxy advice as an independent invocation. Still, distinguish carefully:

- If **`outer()`** already has a transaction or advice, the internal call can **continue executing within the existing transaction/context**. "No extra advice ran" does not mean "no transaction exists".
- If using **`currentProxy()`** to call `innerTransactional` through the proxy, the advisor can be re-evaluated; the outcome still depends on transaction propagation, annotation metadata, proxy type, and whether the method is interceptable.
- Turning on `exposeProxy` just to patch an architecturally misplaced transaction boundary is not recommended; extract the method to another bean, review transaction service boundaries, and test the real outcome.

This example **solely explains the consequences of the Spring proxy boundary**; it does not replace documentation on configuring transaction managers or `@Transactional` rules.

## 14. How does `currentProxy()` differ between JDK proxy and CGLIB?

**`AopContext.currentProxy()`** returns **the actual proxy object** of the invocation, so valid casts depend on how Spring created the proxy.

### 14.1. JDK dynamic proxy

When the target has interfaces and Spring chooses a JDK proxy, the returned object implements the interfaces exposed by the proxy. In section 5's example, using:

~~~java
Operations proxy = (Operations) AopContext.currentProxy();
proxy.inner("X");
~~~

is valid. Do not assume casting to **`OperationsImpl`** works.

A JDK dynamic proxy exposes only methods belonging to the proxied interfaces; public methods present only on the implementation class are not automatically exposed by that interface proxy.

### 14.2. CGLIB class-based proxy

When using:

~~~java
@EnableAspectJAutoProxy(
    proxyTargetClass = true,
    exposeProxy = true
)
~~~

Spring can create a subclass proxy. `currentProxy()` can then be cast to the target class if configuration and class modifiers permit; yet `protected`/package-visible methods still follow Java visibility rules, `final`/`private` cannot be overridden, and self-invocation still bypasses the proxy.

Do not try to rescue an unadvisable method merely by enabling **`exposeProxy`**. If a method is `private` or `final` on a class-based proxy, switching the receiver to the proxy does not make an impossible override valid.

## 15. Common mistakes

| Symptom | Common cause | How to inspect or resolve |
| --- | --- | --- |
| **`AopContext.currentProxy()`** throws `IllegalStateException` | `exposeProxy` not enabled or no matching invocation on current thread | Check `@EnableAspectJAutoProxy(exposeProxy=true)`, proxy call path, and thread |
| Bean is an AOP proxy yet `currentProxy()` still fails | Having a proxy does not mean the proxy is exposed | Verify `exposeProxy` setting and invocation timing |
| Works through Spring, fails in unit test using `new` | Test uses raw target instead of Spring-managed proxy | Test pure logic without `AopContext`, or use context-backed integration tests |
| `ClassCastException` when casting `currentProxy()` | JDK proxy is not a subclass of the implementation | Cast to an interface actually implemented by the proxy |
| `currentProxy()` fails in async task | `ThreadLocal` does not propagate to another thread automatically | Place the appropriate AOP boundary on the executing thread or refactor |
| Proxy exists yet inner call does not run advice | `this.inner()` bypasses proxy, or pointcut mismatch | Check receiver, pointcut, method visibility, and finality |
| `currentProxy()` returns proxy yet advice does not run | New call through proxy has no matching advisor | Check whether method matches and is interceptable |
| `StackOverflowError` after using `currentProxy` | Repeated proxy calls back into the same entry method | Analyze call graph, avoid unbounded recursion |
| Advice runs more times than expected | Re-invoking method via proxy or nested invocations add extra advice | Count proxy entries, inspect advisor order and conditions |
| `exposeProxy` enabled yet target is not proxied | No matching advisor or bean is not Spring-managed | Check bean registration, `@Aspect`, and pointcut |
| Bean initialization fails with self-injection | Dependency cycle or bean not ready | Refactor into two independent beans without relying on constructor cycles |
| Relying on `currentProxy` for request state | `AopContext` is bound only to the invocation/thread, not request context | Use request scope or a dedicated context if truly needed |

## 16. Checklist when forced to consider `currentProxy()`

Before accepting this approach, ask yourself:

1. **Why can't the method needing advice be extracted to another bean?** If refactoring is feasible, do that first.
2. **Is the bean always obtained through Spring `ApplicationContext`?** If any code path constructs a raw target manually, `currentProxy` is unreliable.
3. **Is the caller guaranteed to enter through the AOP proxy before calling `currentProxy()`?** By default, interface methods should be clearly exposed.
4. **Does the proxy have `exposeProxy` enabled?** Setting this attribute does not create advisors or beans on its own.
5. **Does the code run on the same thread while the invocation is still active?** Never rely on async `ThreadLocal` propagation.
6. **Is the cast type valid for JDK/CGLIB?** Use an exposed proxy interface whenever possible.
7. **Is the re-invoked method interceptable and matched by the pointcut?** `private`/`final` methods or other self-invocations will still bypass advice.
8. **Is there a risk of recursively calling the same entry method?** Inspect the call graph, especially with `@Around`, retry, and transaction advice.
9. **Are there integration tests verifying both `exposeProxy` enabled and disabled cases?** Assert actual advice execution, not just `isAopProxy`.
10. **Is a benchmark needed under high call volume?** Exposing the proxy adds `ThreadLocal` overhead; measure in a realistic application context.

If you still have to use it, isolate the `currentProxy`-dependent path to one well-documented place rather than adopting it as a service-layer coding convention.

## 17. Self-assessment questions

**Q1. Why does `this.inner()` not run `@Before` for `inner()`?**

Because **`this`** is the target and an internal call does not create a new call passing through the Spring AOP proxy. `inner`'s advice is not evaluated separately for that call.

**Q2. If a Spring AOP proxy already exists, why can `AopContext.currentProxy()` still throw an error?**

Because the current proxy must **be exposed** and the method must be running inside an **AOP invocation on the same thread**. Simply having a proxy in the context is not enough.

**Q3. Does `@EnableAspectJAutoProxy(exposeProxy = true)` turn every bean into a proxy?**

No. Spring still requires registered beans and matching advisors/pointcuts to create corresponding proxies.

**Q4. With a JDK proxy, what type should `currentProxy()`'s result be cast to?**

To an **interface actually implemented by the proxy**, such as **`Operations`**, not arbitrarily to **`OperationsImpl`**.

**Q5. Should `currentProxy()` be used inside a constructor or `@PostConstruct`?**

No, not by default. Those callbacks are not guaranteed to run inside an AOP proxy invocation with `exposeProxy`; there is also the risk of the bean not being fully initialized.

**Q6. Can `currentProxy()` be used in a new thread spawned from a proxied method?**

A new thread does not automatically inherit the calling thread's `ThreadLocal` proxy; a separate invocation on that thread or a different design is required.

**Q7. Why is refactoring into two Spring beans preferred?**

Because calling an injected dependency explicitly traverses the proxy, reduces coupling to static Spring AOP APIs, eases testing, and needs no `exposeProxy`.

**Q8. When calling `currentProxy().inner()`, is advice guaranteed to run?**

No. The method must have a matching advisor/pointcut, be interceptable under JDK/CGLIB, and be invoked through the right proxy; `exposeProxy` only makes **getting the current proxy** possible.

**Q9. When proxy A calls proxy B in a nested call, which proxy does `currentProxy()` return inside B?**

It returns the proxy exposed by the **currently active invocation** on the thread — typically B while B is running — and Spring restores the previous proxy when B finishes.

**Q10. Does CGLIB eliminate the self-invocation issue?**

No. Class-based proxies do not cause direct **`this.method()`** calls inside the target to route back through the Spring AOP proxy.

## 18. Official Spring Framework documentation

- **Spring Framework 6.2 — Proxying Mechanisms and self-invocation:** https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- **Spring Framework 6.2.12 — AopContext Javadoc:** https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/aop/framework/AopContext.html
- **Spring Framework — @AspectJ Support:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- **Spring Framework — JDK dynamic proxies and CGLIB:** https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Framework — Annotation-based AOP configuration:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/autoproxy.html

**Conclusion:** **`AopContext.currentProxy()`** provides access to the current proxy to handle certain internal calls in Spring AOP when **`exposeProxy=true`**. It works under the right invocation, thread, proxy type, and pointcut, yet tightly couples code to Spring AOP. **Do not use it as the default solution for self-invocation**; prefer moving the functionality needing advice to another Spring bean and invoking it via dependency injection.