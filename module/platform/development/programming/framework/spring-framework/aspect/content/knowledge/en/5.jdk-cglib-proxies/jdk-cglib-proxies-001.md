# Spring AOP: JDK Dynamic Proxies Based on Interfaces and the Exposed Method Surface

## 1. The Role of JDK Proxies in Spring AOP

In Spring AOP, a **JDK dynamic proxy** is a Java proxy created by Spring to intercept calls to **public methods exposed through a bean's interfaces**. If Spring selects a JDK proxy for a target with interfaces, the caller receives a proxy object **implementing the interfaces**, while the real business object sits behind the proxy.

Example:

```java
public interface BillingPort {
    void pay(String orderId);
}

public class BillingService implements BillingPort {
    @Override
    public void pay(String orderId) {
        System.out.println("paid " + orderId);
    }

    public void implementationOnly() {
        System.out.println("internal API");
    }
}
```

This is an illustrative fragment, not a standalone runnable program. With a **JDK proxy for `BillingService`**, callers can use `BillingPort.pay(...)` on the proxy reference. The `implementationOnly()` method is declared only on the implementation, so it is **not exposed by the JDK proxy through the interface**; even though it is public and a pointcut describes it, Spring AOP via JDK proxy has no external call to this method to intercept.

Processing flow:

```text
Spring IoC container
    |
    +-- register target bean BillingService
    |           |
    |           v
    |      instantiate target
    |           |
    |       Spring AOP
    |           |
    |    advisor/pointcut matches
    |           |
    |   JDK proxy implements BillingPort
    |           |
    +------ inject proxy into consumer
                |
          port.pay("A1")
                |
            JDK proxy
                |
         interceptor/advice
                |
       BillingService.pay("A1")
```

**Important prerequisite:** simply having an interface does not mean Spring automatically creates a proxy. The target must be a Spring bean, the AOP infrastructure must be configured, and an applicable advisor/advice must match. A JDK proxy is only **a mechanism for creating a proxy when needed**, not a bean registration mechanism.

This lesson only analyzes JDK dynamic proxies in **proxy-based Spring AOP**. It does not extend to AspectJ bytecode weaving mechanisms.

## 2. What Does “Interface-Based” Mean Exactly?

### 2.1. The Proxy Implements the Interface, Not the Implementation Class

When configuration selects a JDK proxy, the object Spring exposes typically has the following properties:

- `proxy instanceof BillingPort` is `true`: the proxy fulfills the interface contract.
- `proxy instanceof BillingService` is `false`: a JDK proxy is not a subclass of `BillingService`.
- If you cast `(BillingService) proxy`, an incompatible runtime cast throws `ClassCastException`.
- If the bean is injected into a constructor accepting `BillingPort`, the types are compatible. If the constructor requires `BillingService` while Spring returns a JDK proxy, dependency resolution can fail due to type incompatibility.

In a Spring application, consumer code should accept **the interface that the proxy actually implements**:

```java
@Component
public class CheckoutHandler {
    private final BillingPort billing;

    public CheckoutHandler(BillingPort billing) {
        this.billing = billing;
    }

    public void checkout(String orderId) {
        billing.pay(orderId);
    }
}
```

This snippet illustrates constructor injection. A single constructor typically does not need `@Autowired`. For the JDK proxy to work, `CheckoutHandler` and `BillingService` must be managed by the container and Spring AOP must be enabled.

### 2.2. Which Business Methods Does the Proxy Support?

The **business method surface** of a JDK proxy is determined by the interfaces the proxy is configured to implement:

| Method / member | Callable from a JDK proxy reference? | Implications for Spring AOP |
| --- | --- | --- |
| `public void pay(...)` declared in `BillingPort` | Yes | Can be advised if a pointcut matches and the caller goes through the proxy |
| `default String channel()` in the interface | Yes | Is a public interface method; can be advised when a corresponding pointcut matches |
| Method inherited from a superinterface | Yes | Belongs to the proxy's public interface contract |
| A method from a second interface that the proxy also implements | Yes | Spring can proxy multiple interfaces; the consumer must have a compatible type to call it |
| `public void implementationOnly()` only on the target class | No, via the JDK proxy interface surface | A pointcut with the exact name will not cause the proxy to expose this method automatically |
| `protected` or package-private method only on the implementation | No | Not part of the JDK proxy's public interface contract |
| `private` method of the target | No | Not exposed and cannot be called externally via a JDK proxy |
| `static` method on an interface/class | Not as an instance proxy call | Called by type name; does not go through the AOP instance proxy |
| `private` helper method in an interface | Not from outside | Used only internally within the interface; not part of the proxy's API |

**Important exception regarding observable scope:** A JDK proxy is a Java object, so it also has `Object` methods and sometimes Spring AOP infrastructure interfaces. You should not state that `proxy.getClass().getMethods()` contains **strictly and only** the methods of a single business interface. What matters is **the methods the application can invoke according to the business interface contract**.

Having a method on an interface does not guarantee advice will run: it must also be selected by an advisor/pointcut. The interface determines **which methods callers can invoke on the proxy**; the pointcut determines **which calls are advised**.

### 2.3. Multiple Interfaces and Interface Inheritance

A target can implement multiple interfaces:

```java
interface PaymentOperations {
    void pay(String id);
}

interface AuditOperations {
    void audit(String id);
}

class PaymentEngine implements PaymentOperations, AuditOperations {
    public void pay(String id) { /* ... */ }
    public void audit(String id) { /* ... */ }
    public void internalRebuild() { /* ... */ }
}
```

If Spring uses a default JDK proxy for the target's interfaces, the proxy can implement both `PaymentOperations` and `AuditOperations`. Therefore:

- A consumer typed as `PaymentOperations` calls `pay`; a consumer typed as `AuditOperations` calls `audit`.
- A consumer holding a variable of type `PaymentOperations` cannot call `audit` through that variable unless it switches to a compatible interface type that the proxy actually implements.
- `internalRebuild` does not belong to either interface, so it cannot be called through the JDK proxy.
- With low-level Spring AOP configuration or intentional exposed-interface restrictions, the list of interfaces actually exposed by the proxy can be customized. Inspect the injected object rather than assuming.

The API surface of a JDK proxy is not **all public methods** of the implementation class. This is a key difference compared to a class-based proxy (CGLIB).

## 3. How Does Spring Choose a JDK Proxy?

### 3.1. Plain Spring Framework with `@EnableAspectJAutoProxy`

When using `@Aspect` declarations, you must register the aspect as a Spring bean and enable auto-proxying:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
@ComponentScan("demo.springjdk")
class AopConfiguration {
}
```

This is a configuration snippet. In plain Spring Framework, `proxyTargetClass=false` is the default of `@EnableAspectJAutoProxy`; for a target with suitable interfaces, Spring usually creates a JDK proxy. If the target has no interfaces, Spring can use CGLIB even when the setting is `false`.

To use `@Aspect` in plain Spring Framework, you need the Spring Context/AOP dependencies and the AspectJ library for pointcut parsing. You do not need to run the AspectJ compiler or load-time weaving to use Spring AOP proxies.

### 3.2. Spring Boot Has a Different Default

Spring Boot provides AOP auto-configuration when the appropriate dependency (such as `spring-boot-starter-aop`) is present. By default, Boot prefers **CGLIB class-based proxies**. If you want a JDK proxy for beans with interfaces, configure:

```properties
spring.aop.proxy-target-class=false
```

In plain Spring Framework, `@EnableAspectJAutoProxy(proxyTargetClass=false)` is usually enough to prefer JDK proxies. In Spring Boot, check the property above and other proxy configurations before concluding which proxy type is used.

Spring can merge multiple auto-proxy requests within the same context; a setting forcing class-based proxies from another component can cause the actual behavior to differ from expectations. Therefore, `AopUtils.isJdkDynamicProxy(bean)` is a better empirical check than simply reading a single annotation.

### 3.3. Scoped Comparison with CGLIB

| Criterion | JDK proxy in Spring AOP | CGLIB in Spring AOP |
| --- | --- | --- |
| Form | Creates an object implementing interfaces | Creates a subclass of the target class |
| Requires an interface on the target? | Requires interfaces to expose via JDK proxy | Not required |
| Consumer should inject | Interface | Interface or compatible class |
| Public method only on the implementation | Not exposed by the proxy | Can be intercepted if the call goes through the proxy and the method is overridable |
| Target is a `final class` | Can use a JDK proxy if the target implements suitable interfaces | Cannot subclass a `final class` |
| Target has a `final` implementation method declared in an interface | JDK proxy can still intercept calls **to the interface** since it does not need to override the target method | Cannot override a final method, so it cannot advise it via class proxying |
| Self-invocation `this.method()` | Bypasses the proxy | Also bypasses the proxy |

Choose a proxy type based on **the dependency contract and the method surface needing advice**; avoid forcing CGLIB just to fix an injection error if an interface already describes the right business API.

## 4. Common Confusion Between “Interface Method” and “Pointcut Match”

### 4.1. A Pointcut Can Reference an Implementation Method Exposed by an Interface

Spring AOP can evaluate pointcuts describing the executing method on the concrete target:

```java
@Before("execution(* demo.springjdk.BillingService.pay(..))")
public void beforePay() {
    System.out.println("[aop] before pay");
}
```

Even though the caller invokes `BillingPort.pay(...)` through the JDK proxy, the underlying method executing is `BillingService.pay(...)`. Spring uses target class information when evaluating pointcuts; thus an expression based on the concrete implementation like the one above can still match.

Conversely, if the pointcut selects `BillingService.implementationOnly()` and that method **is not on the proxy interface**, there is no external call through the JDK proxy to trigger advice for it. Changing the pointcut alone does not expand the interface surface of a JDK proxy.

### 4.2. `this` and `target` in Spring AOP Do Not Necessarily Have the Same Type

In Spring AOP, `this(...)` in a pointcut expression describes the **proxy object**; `target(...)` describes the **target object**. With a JDK proxy for `BillingService implements BillingPort`:

- `this(demo.springjdk.BillingPort)` can match because the proxy implements `BillingPort`.
- `this(demo.springjdk.BillingService)` does not match for a JDK proxy because the proxy does not extend that class.
- `target(demo.springjdk.BillingService)` can match because the executing object is the target class.

These are semantics **specific to Spring proxies**. You must understand them when switching an AOP configuration from CGLIB to JDK proxy or vice versa.

### 4.3. Annotations on Interfaces vs. Implementations

When working with annotations processed by Spring via AOP such as `@Transactional` or custom markers combined with `@annotation`, do not assume that placing an annotation on the interface and placing it on the implementation are always equivalent across **all proxy configurations, advice, and pointcuts**.

- An advice or infrastructure may inspect annotations on the method and target class according to its own rules.
- Some Spring infrastructure (for example, transaction metadata) looks up annotations on both the implementing method and the class.
- A specific pointcut expression such as `@annotation(...)` has its own matching behavior; verify in practice when an annotation is placed on the interface while the executing method is on the class.
- Place annotations where the relevant framework can clearly recognize them and write integration tests for calls through the proxy.

The scope of a JDK proxy still relies on the exposed interfaces, regardless of which method or class carries an annotation.

## 5. Complete Example: Interface Declares Two Methods, Implementation Has a Third

The example uses **Java 17**, **Maven**, and **Spring Framework 6.2.x** without Spring Boot. The Spring AOP infrastructure creates a **JDK proxy** for the `BillingService` bean with the `BillingPort` interface. You will observe:

1. The reference injected by Spring is a JDK proxy and is not an instance of the concrete class.
2. Calling `pay(...)` on the proxy runs the advice.
3. The `implementationOnly(...)` method exists on the target but is absent from the JDK proxy surface.
4. Calling `this.pay(...)` inside the target bypasses the proxy (self-invocation).

File structure:

```text
spring-jdk-proxy/
├── pom.xml
└── src/main/java/demo/springjdk/
    ├── AppConfig.java
    ├── BillingPort.java
    ├── BillingService.java
    ├── BillingAspect.java
    ├── ClientJob.java
    └── Main.java
```

### 5.1. File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-jdk-proxy</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.2. File `src/main/java/demo/springjdk/BillingPort.java`

```java
package demo.springjdk;

public interface BillingPort {
    void pay(String orderId);
    void submit(String orderId);
}
```

These two public methods belong to the **proxy's business API**. Because they are exposed by the interface, both `pay` and `submit` can be called on a `BillingPort` reference; however, the aspect below only advises `pay`.

### 5.3. File `src/main/java/demo/springjdk/BillingService.java`

```java
package demo.springjdk;

import org.springframework.stereotype.Service;

@Service
public class BillingService implements BillingPort {
    @Override
    public void pay(String orderId) {
        System.out.println("[service] pay " + orderId);
    }

    @Override
    public void submit(String orderId) {
        System.out.println("[service] submit " + orderId);
        this.pay(orderId); // Self-invocation: does not go through the AOP proxy.
    }

    public void implementationOnly(String orderId) {
        System.out.println("[service] implementationOnly " + orderId);
    }
}
```

Note: `implementationOnly` is a public method of the class, but it is **not in `BillingPort`**; therefore, the JDK proxy does not expose this method on the business surface.

### 5.4. File `src/main/java/demo/springjdk/BillingAspect.java`

```java
package demo.springjdk;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class BillingAspect {
    @Before("execution(* demo.springjdk.BillingService.pay(..))")
    public void beforePay() {
        System.out.println("[aspect] before pay");
    }
}
```

The aspect is discovered by Spring component scanning because it has `@Component`. The `execution` expression selects the `pay` method on the target class. Non-matching methods, such as `submit`, will not be advised merely because they are on the same proxy.

### 5.5. File `src/main/java/demo/springjdk/AppConfig.java`

```java
package demo.springjdk;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

Spring scans the entire package containing `AppConfig`. `BillingPort` is an interface, while `BillingService` has `@Service` so it is registered as a bean. `@EnableAspectJAutoProxy` enables the AOP infrastructure, and `proxyTargetClass=false` prefers a JDK dynamic proxy for this bean.

### 5.6. File `src/main/java/demo/springjdk/ClientJob.java`

```java
package demo.springjdk;

import org.springframework.aop.support.AopUtils;
import org.springframework.stereotype.Component;

@Component
public class ClientJob {
    private final BillingPort billing;

    public ClientJob(BillingPort billing) {
        this.billing = billing;
        System.out.println("[client] injectedJdkProxy="
                + AopUtils.isJdkDynamicProxy(billing));
    }

    public void run() {
        System.out.println("[client] run");
        billing.pay("ORD-1");
        billing.submit("ORD-2");
    }
}
```

`ClientJob` requests its dependency via the **interface**, so the JDK proxy reference is compatible with the constructor. `pay` runs the advice; `submit` is not selected by this aspect, and calling `this.pay(...)` inside `submit` bypasses the proxy.

### 5.7. File `src/main/java/demo/springjdk/Main.java`

```java
package demo.springjdk;

import java.util.Arrays;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            BillingPort port = context.getBean(BillingPort.class);

            System.out.println("[main] isJdkProxy="
                    + AopUtils.isJdkDynamicProxy(port));
            System.out.println("[main] isImplementation="
                    + (port instanceof BillingService));

            boolean exposesOnlyMethod =
                    Arrays.stream(port.getClass().getMethods())
                            .anyMatch(m -> m.getName().equals("implementationOnly"));
            System.out.println("[main] extraVisible=" + exposesOnlyMethod);

            context.getBean(ClientJob.class).run();

            // Create a standalone Java target; not part of a Spring AOP proxy.
            new BillingService().implementationOnly("ORD-3");
        }
    }
}
```

Using reflection here is only to **observe the proxy surface**, not how business code should call a service. `getMethods()` also includes other methods from Java `Object` and framework interfaces; the check specifically asks for the name `implementationOnly`.

### 5.8. Run Command and Output

In the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.springjdk.Main
```

The `System.out` lines from the program (excluding Maven or Spring logs if printed by the environment):

```text
[client] injectedJdkProxy=true
[main] isJdkProxy=true
[main] isImplementation=false
[main] extraVisible=false
[client] run
[aspect] before pay
[service] pay ORD-1
[service] submit ORD-2
[service] pay ORD-2
[service] implementationOnly ORD-3
```

**Step-by-step explanation:**

1. When creating the `ClientJob` singleton, Spring resolves `BillingPort` and injects the proxy. The constructor prints `injectedJdkProxy=true`.
2. `context.getBean(BillingPort.class)` retrieves the same kind of reference managed by Spring; `isJdkProxy=true` verifies the actual proxy type.
3. `isImplementation=false` shows that the proxy object is not an instance of the concrete class; `extraVisible=false` shows that the implementation-only method is not published on the JDK proxy.
4. `billing.pay("ORD-1")` through the JDK proxy causes the advice to print `before pay`, and then the target executes `pay`.
5. `billing.submit("ORD-2")` enters the proxy, but the aspect does not select `submit`. The target's `submit` uses `this.pay("ORD-2")`, bypassing the proxy, so there is **no advice** before `pay ORD-2`.
6. `new BillingService().implementationOnly("ORD-3")` calls the method directly on a manually created Java object. The method still runs, but without Spring AOP advice.

**Key distinction:** the last line does not prove that `implementationOnly` cannot run in Java. It only illustrates the bean's JDK proxy surface and that creating an object manually is not subject to Spring AOP interception.

## 6. Extended Experiments and Observed Results

### 6.1. What Needs to Change to Advise `implementationOnly`?

If you keep the JDK proxy, merely adding:

```java
@Before("execution(* demo.springjdk.BillingService.implementationOnly(..))")
public void beforeImplementationOnly() {
    System.out.println("[aspect] before implementationOnly");
}
```

to `BillingAspect` will **not be enough** for callers to access the implementation-only method via `BillingPort`. This snippet is an additional aspect method, not a standalone runnable Java file.

Two valid design directions:

1. **Add the method to the appropriate business interface**, for example adding `void implementationOnly(String id)` to `BillingPort` if it truly belongs to the public API. Then the JDK proxy can expose the method, and a matching pointcut can advise calls through the proxy.
2. **Use a class-based proxy** for cases where you intentionally expose public methods of the concrete class, provided the class/method can be proxied. In plain Spring Framework, you can configure `@EnableAspectJAutoProxy(proxyTargetClass = true)`. Consider interface design before forcing a proxy type.

Adding a method to an interface changes the API contract; do not do this solely to bring an internal helper under AOP.

### 6.2. Switching to CGLIB to Compare Surfaces

In `AppConfig`, change to:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
```

With a non-`final` `BillingService` class, Spring creates a class-based proxy. The first two check outputs will differ:

```text
[main] isJdkProxy=false
[main] isImplementation=true
```

And the `implementationOnly` check in `Main` becomes `extraVisible=true` because the proxy subclass inherits this public method. To confirm advice on the new method, you need to add a matching pointcut **and call through the Spring proxy**; merely using CGLIB does not mean every method has advice.

Note that the `ClientJob` constructor will print `injectedJdkProxy=false`, because a class-based proxy is not recognized by `isJdkDynamicProxy`.

### 6.3. Changing the Consumer to Inject the Implementation While Using a JDK Proxy

If you change the constructor to:

```java
public ClientJob(BillingService billing) {
    // ...
}
```

while Spring is creating a JDK proxy, you may encounter a bean creation or dependency resolution error because the proxy object is not a `BillingService`. This is a **type contract** error, not caused by the `pay` pointcut. Preferred approach: keep `BillingPort` as the dependency type. If you genuinely need the concrete class, consider a class proxy and its limitations.

### 6.4. What If the Target Class Is `final`?

A `final class BillingService implements BillingPort` can still have a **JDK interface proxy** applied by Spring AOP, because the proxy does not need to subclass the target. Similarly, a `final` implementation method declared by a public interface can be advised when callers invoke it through the JDK proxy: the proxy intercepts the call at the interface boundary and then delegates to the target method.

With CGLIB, a final class cannot be subclassed and a final method cannot be overridden to intercept. This is a meaningful design difference, although you should not intentionally abuse `final` just to force a proxy technology.

### 6.5. What If the Method Is Called from Inside the Target Itself?

Even when a method is on the interface, calling `this.pay()` internally inside the target still **does not go through the proxy**, so advice will not run automatically. You can move the logic that needs interception to another Spring bean and inject the dependency; this is cleaner than abusing `AopContext.currentProxy()`.

## 7. Notes When Designing Interfaces for Spring AOP

### Put Only Necessary Public Behavior into Interfaces

A small, stable interface describing a business boundary reduces consumer coupling to the implementation. Do not expose technical helper methods or private concerns just so they can be advised via a JDK proxy.

If your application has multiple interfaces, pay attention to which interfaces Spring actually exposes on the bean; technical interfaces can unintentionally widen the proxy's API beyond expectations. Use the exact required interface type at the injection point.

### Mind Interface Default Methods

An interface can declare a default method:

```java
public interface BillingPort {
    void pay(String orderId);

    default String providerName() {
        return "default";
    }
}
```

`providerName()` is a public instance method belonging to the interface, so callers of the JDK proxy can invoke it. Whether advice runs still depends on the pointcut and calling through the proxy. When a default method calls another method in the same interface, verify the actual dispatch/proxy path in the Spring version in use; do not assume advice behavior solely from the method being `default`.

Conversely, `static` methods are not instance methods on the proxy; private interface helpers are not part of the public API.

### Exceptions, Overloads, and Generics Still Follow Java Contracts

A JDK proxy reflects the signatures of its interfaces. When a caller holds a reference of type `BillingPort`, the compiler checks parameters, return types, and checked exceptions against that interface. Overloaded methods must be declared completely on the interface for callers to select the corresponding overload.

Spring AOP can advise each overload if the pointcut matches; compiling generics into erased types/bridge methods can affect how a pointcut or reflection sees a method. For complex cases, write integration tests on **the actually injected DI bean** rather than mechanically inferring from source signatures.

### Proxies Do Not Turn Objects Created with `new` into Spring Beans

If code uses `new BillingService()` and holds onto that object, Spring does not automatically provide a JDK proxy. Conversely, a `@Bean` method **invoked by Spring** can call `new BillingService()` and return the object to the container; Spring still has the opportunity to post-process and create a proxy. The deciding factor is that the object reference is managed and exposed through the container.

### Distinguishing Interface Proxies and Target Classes When Debugging

Use Spring's utility methods:

```java
AopUtils.isAopProxy(bean);
AopUtils.isJdkDynamicProxy(bean);
AopUtils.isCglibProxy(bean);
```

These are illustrative API calls on a `bean` variable obtained from the context. Do not rely on runtime class names, proxy suffixes, or `getClass()==Target.class` when determining the AOP mode. If an aspect does not run, check **the call path** (via proxy vs. self-invocation), the pointcut, surface limitations, and bean configuration.

## 8. Practical Troubleshooting Checklist

| Symptom | Common cause | How to check / resolve |
| --- | --- | --- |
| Interface injection works, concrete class injection fails | Bean is a JDK proxy implementing only interfaces | Use the interface at the injection point; check `AopUtils.isJdkDynamicProxy` |
| Service has a public helper but it cannot be called on the proxy | Helper exists only on the implementation | Add to the interface if it is truly part of the API, or consider a class proxy |
| Widening the pointcut still does not intercept an implementation-only method | Method is not exposed by the JDK proxy | First determine the proxy's surface and how callers invoke it |
| `@Aspect` is present but the bean is not proxied | Aspect is not registered as a Spring bean, AOP is not enabled, or pointcut does not match | Check `@Component`/`@Bean`, `@EnableAspectJAutoProxy`, and context |
| Assumed Spring Boot's default is JDK proxy | Boot typically defaults to CGLIB | Check `spring.aop.proxy-target-class=false` and verify the proxy |
| Spring Framework has `proxyTargetClass=false` set but still uses CGLIB | Target has no interfaces or another auto-proxy config prioritizes class proxies | Check target interfaces and shared configurations |
| Interface has `pay`, but advice does not run on `this.pay()` | Self-invocation bypasses the proxy | Invoke via another DI-managed bean |
| Aspect uses `this(ImplementationClass)` and does not match | With a JDK proxy, `this` is the proxy and does not extend the implementation | Consider `this(Interface)` or `target(ImplementationClass)` as appropriate |
| `final` method is still advised via JDK proxy | JDK proxy intercepts the interface method, does not override the target | Distinguish JDK proxy limits from CGLIB limits |
| API has multiple interfaces but consumer sees only one group of methods | The reference variable's type exposes only its declared interface | Use the appropriate interface type; verify the proxy implements the required interfaces |

Workflow for analyzing a specific issue: verify the target and aspect belong to the Spring container → confirm a proxy exists → confirm whether the proxy is JDK or CGLIB → check what reference type the caller holds → compare the invoked method against the proxy's exposed interfaces → check the pointcut → check whether the call goes through the proxy.

## 9. Self-Check Questions

**1. A class has three public methods, but its interface declares only one. With a JDK proxy, how many public business methods can a caller invoke through that interface?** One method per that interface contract (aside from `Object`/infrastructure methods when inspected via reflection). The two public methods present only on the implementation are not automatically exposed by the JDK proxy.

**2. Why does `getBean(BillingPort.class)` usually work while requesting a bean by `BillingService.class` can fail?** Because a JDK proxy implements the interface, not a subclass of the implementation.

**3. Does marking an implementation method `final` necessarily prevent AOP advice via a JDK proxy?** No. If the method is exposed by the interface and the caller invokes it through the JDK proxy, `final` on the target does not prevent interception at the interface boundary.

**4. Can a pointcut reference the concrete implementation when using a JDK proxy?** Yes. Spring considers target class information when matching pointcuts; however, only calls through methods that the proxy actually exposes will be intercepted.

**5. Does setting `proxyTargetClass=false` guarantee 100% that a JDK proxy will be used?** No, it also depends on whether the target has interfaces, other auto-proxy configurations, and the bean type. Verify the actual reference with `AopUtils`.

**6. The interface has `pay`; `submit()` inside the target calls `this.pay()`. Will advice for `pay` run?** Not through that self-invocation. Route the call through a Spring proxy reference when advice is truly required.

## Official Spring Documentation

- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-proxies.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework — @AspectJ support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html)
