# Reference Types When Injecting Dependencies via Interface or Concrete Class in Spring AOP

## 1. Why Does Spring AOP Affect the Injected Type?

An application may declare `PaymentServiceImpl implements PaymentService` and inject the dependency in two ways:

```java
private final PaymentService paymentService;         // by interface
private final PaymentServiceImpl paymentServiceImpl; // by implementation class
```

When **Spring AOP auto-proxying** applies advice to that bean, the object the container supplies to other beans may **no longer be a direct instance of `PaymentServiceImpl`**. Depending on the proxy strategy:

- **JDK dynamic proxy:** the proxy object implements the exposed interfaces, such as `PaymentService`, but **does not extend `PaymentServiceImpl`**. Interface-based injection works; casting or injecting by the implementation class can fail.
- **CGLIB class-based proxy:** the proxy object is a **subclass** of `PaymentServiceImpl`. Therefore, the proxy is assignable to both the `PaymentService` interface and the concrete `PaymentServiceImpl` type, provided creating the proxy subclass is valid.

This lesson focuses on **Spring AOP and dependency injection**: choosing constructor parameter/field types, the effect of `proxyTargetClass` configuration, runtime behavior, and debugging techniques. General Aspect theory is not the focus.

## 2. Illustrating the Real Target vs. the Object Supplied by Spring

Suppose:

```java
public interface PaymentService {
    void pay();
}

public class PaymentServiceImpl implements PaymentService {
    @Override
    public void pay() {
        // payment processing
    }
}
```

Two forms Spring can create when an advisor matches:

```text
                      Spring IoC container
                              |
                  target: PaymentServiceImpl
                              |
           +------------------+------------------+
           |                                     |
      JDK proxy                              CGLIB proxy
   implements PaymentService          extends PaymentServiceImpl
           |                                     |
     instanceof PaymentService: true       instanceof PaymentService: true
     instanceof PaymentServiceImpl: false  instanceof PaymentServiceImpl: true
           |                                     |
        advice -> target.pay()                  advice -> target.pay()
```

Both columns are **Spring AOP proxies** when created by Spring AOP. The critical difference for dependency injection is **which types the proxy object is assignable to**.

| Test on the object returned from the context | JDK proxy of `PaymentService` | CGLIB proxy of `PaymentServiceImpl` |
| --- | --- | --- |
| `proxy instanceof PaymentService` | `true` | `true` |
| `proxy instanceof PaymentServiceImpl` | `false` | `true` |
| `AopUtils.isAopProxy(proxy)` | `true` | `true` |
| `AopUtils.isJdkDynamicProxy(proxy)` | `true` | `false` |
| `AopUtils.isCglibProxy(proxy)` | `false` | `true` |
| Can be referenced by `PaymentService` interface | Yes | Yes |
| Can be referenced by concrete `PaymentServiceImpl` | **No**, not with that JDK proxy | Yes, if the class proxy was created successfully |

The table assumes an AOP proxy was created for that bean, with no nested proxies or unusual bean replacements. **Not every Spring bean has an AOP proxy:** if no advisor applies, Spring may return the raw target; in that case, concrete-class dependency injection can still work even if the project sets `proxyTargetClass=false`.

## 3. JDK Dynamic Proxy: Injecting via Interface

### 3.1. How Spring Chooses a JDK Proxy

In a typical Spring AOP configuration, if the target implements an interface and **is not forced to use a class-based proxy**, Spring can use a JDK dynamic proxy. This proxy implements **the business interfaces** along with some Spring internal interfaces, but does not extend the implementation class.

Recommended constructor injection example:

```java
@Service
public class CheckoutController {
    private final PaymentService paymentService;

    public CheckoutController(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
```

This is an **illustrative snippet**, assuming `PaymentService` and its implementing bean are registered, `@Service` is component-scanned, and a single `PaymentService` bean is injectable.

When Spring provides a JDK proxy for the implementing bean, it is still a `PaymentService`. Code invokes `paymentService.pay()` through the interface reference, routing the call through the proxy and matching advisors.

**Do not do this:**

```java
PaymentServiceImpl impl =
    (PaymentServiceImpl) context.getBean("paymentService");
```

If the bean is wrapped in a JDK proxy, this cast can throw `ClassCastException`. `getBean("paymentService", PaymentServiceImpl.class)` can throw `BeanNotOfRequiredTypeException` because the type of **the returned proxy object** is incompatible with `PaymentServiceImpl`.

### 3.2. What Happens When Injecting the Implementation Directly?

```java
@Service
public class CheckoutController {
    private final PaymentServiceImpl implementation;

    public CheckoutController(PaymentServiceImpl implementation) {
        this.implementation = implementation;
    }
}
```

If Spring attempts to supply a **JDK proxy** for the `PaymentServiceImpl` bean, the dependency requesting the **concrete type** is not satisfied by the JDK proxy itself. Application context creation can fail with a dependency resolution error, such as `UnsatisfiedDependencyException`, `BeanNotOfRequiredTypeException`, or an exception containing an incompatible-type cause.

The exact error depends on how beans are declared, when dependencies are resolved, and the Spring version. Do not expect a single identical exception across every project; the essence of the error is that **the proxy is not assignable to the requested type**.

**Fix properly at the API contract**: switch the constructor/field to the interface if the caller only needs methods declared on the interface. If the caller genuinely needs the implementation class API, consider **class-based proxies**, redesigning the interface to expose the needed capability, or separating responsibilities into another bean.

### 3.3. Methods Present Only on the Implementation

```java
public interface PaymentService {
    void pay();
}

public class PaymentServiceImpl implements PaymentService {
    @Override
    public void pay() {}

    public void retryFailedPayments() {}
}
```

`retryFailedPayments()` is not in `PaymentService`. With a JDK proxy declared for `PaymentService`, callers **cannot** invoke `retryFailedPayments()` through that interface. When AOP advice is needed for this method, decide whether the method belongs on a **suitable interface** or whether a class-proxy strategy is required. Do not cast to the implementation, because a JDK proxy is not the implementation class.

## 4. CGLIB Class-Based Proxy: Injectable via Concrete Class

When Spring AOP uses CGLIB, a subclass of the target is generated at runtime. Because a subclass is a valid instance of its parent class, Spring can supply it to a constructor requesting `PaymentServiceImpl`:

```java
@Service
public class ReconciliationJob {
    private final PaymentServiceImpl paymentService;

    public ReconciliationJob(PaymentServiceImpl paymentService) {
        this.paymentService = paymentService;
    }

    public void run() {
        paymentService.pay();
    }
}
```

This snippet **can work** if the actual proxy is class-based, the types are valid, and there is a single matching bean.

However, CGLIB has important limitations:

- **`final class`:** cannot be subclassed, so a CGLIB AOP proxy cannot be created for that class.
- **`final method`:** cannot be overridden; calls to that method are not advised by Spring CGLIB via overriding.
- **`private method`:** cannot be overridden, cannot be advised by Spring proxies.
- **Methods invisible to the subclass** (such as package-private methods on a parent in a different package) also cannot be intercepted.
- **Self-invocation:** `this.method()` inside the target still bypasses the proxy, even when the proxy uses CGLIB.
- Spring repackaging CGLIB inside `spring-core` means modern Spring Framework applications usually do not need a separate `cglib` dependency to use class-based Spring AOP.

**Design conclusion:** Injecting concrete types can be useful in legacy codebases or when no stable interface exists, but it couples the contract to the implementation structure and proxy choice. Interface injection is generally easier to keep stable when refactoring or changing proxy types.

## 5. Complete Example: Two Contexts, Same Target, Two Injection Styles

This project uses **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, and Maven. It intentionally creates **two separate `AnnotationConfigApplicationContext` instances** so proxy-forcing configurations do not affect one another:

- **Context A:** `@EnableAspectJAutoProxy(proxyTargetClass = false)` → JDK proxy for the interface-backed target; client injects the interface.
- **Context B:** `@EnableAspectJAutoProxy(proxyTargetClass = true)` → CGLIB proxy; client injects the implementation class.

### 5.1. Structure

```text
proxy-type-injection/
├── pom.xml
└── src/main/java/example/
    ├── GreetingPort.java
    ├── GreetingService.java
    ├── TraceAspect.java
    ├── InterfaceClient.java
    ├── ConcreteClient.java
    ├── JdkConfig.java
    ├── ClassConfig.java
    └── Main.java
```

### 5.2. Maven

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>proxy-type-injection</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. Business Interface and Implementation

**`GreetingPort.java`**:

```java
package example;

public interface GreetingPort {
    String greet(String name);
}
```

**`GreetingService.java`**:

```java
package example;

public class GreetingService implements GreetingPort {
    @Override
    public String greet(String name) {
        return "Hello " + name;
    }
}
```

### 5.4. One `@Aspect` Shared Across Both Contexts

**`TraceAspect.java`**:

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    @Before("execution(* example.GreetingService.greet(..))")
    public void beforeGreet() {
        System.out.println("advice: before greet");
    }
}
```

The pointcut applies to **the `GreetingService.greet` method**. The aspect class is registered as a separate bean in both contexts via `@Bean`; `@Aspect` alone on the class **does not register a bean automatically**.

### 5.5. Clients Depending on the Interface or the Concrete Class

**`InterfaceClient.java`**:

```java
package example;

public class InterfaceClient {
    private final GreetingPort service;

    public InterfaceClient(GreetingPort service) {
        this.service = service;
    }

    public void run() {
        System.out.println("interface client: " + service.greet("Lan"));
    }
}
```

**`ConcreteClient.java`**:

```java
package example;

public class ConcreteClient {
    private final GreetingService service;

    public ConcreteClient(GreetingService service) {
        this.service = service;
    }

    public void run() {
        System.out.println("concrete client: " + service.greet("Minh"));
    }
}
```

Neither client manually queries the context or casts the proxy. Each client receives its dependency via constructor, letting Spring resolve it according to the declared type.

### 5.6. Context A: JDK Proxy, Interface Injection

**`JdkConfig.java`**:

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class JdkConfig {
    @Bean
    public GreetingPort greetingService() {
        return new GreetingService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    public InterfaceClient interfaceClient(GreetingPort service) {
        return new InterfaceClient(service);
    }
}
```

The `greetingService` bean is declared with **return type `GreetingPort`**. With a Spring AOP JDK proxy, the final object still implements this interface. `InterfaceClient` is injected with the reference supplied by Spring, so its calls receive advice.

### 5.7. Context B: CGLIB Proxy, Concrete Class Injection

**`ClassConfig.java`**:

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class ClassConfig {
    @Bean
    public GreetingService greetingService() {
        return new GreetingService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    public ConcreteClient concreteClient(GreetingService service) {
        return new ConcreteClient(service);
    }
}
```

Spring is instructed to use **class-based proxies**, so the object injected into `ConcreteClient` is a valid subtype of `GreetingService`, provided the class is proxyable.

### 5.8. Running and Verifying Object Types

**`Main.java`**:

```java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.BeanNotOfRequiredTypeException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(JdkConfig.class)) {
            Object bean = context.getBean("greetingService");

            System.out.println("jdk proxy: " + AopUtils.isJdkDynamicProxy(bean));
            System.out.println("jdk is concrete: " + (bean instanceof GreetingService));

            try {
                context.getBean("greetingService", GreetingService.class);
                System.out.println("concrete lookup: succeeded");
            } catch (BeanNotOfRequiredTypeException ex) {
                System.out.println("concrete lookup: failed");
            }

            context.getBean(InterfaceClient.class).run();
        }

        try (var context = new AnnotationConfigApplicationContext(ClassConfig.class)) {
            Object bean = context.getBean("greetingService");

            System.out.println("cglib proxy: " + AopUtils.isCglibProxy(bean));
            System.out.println("cglib is concrete: " + (bean instanceof GreetingService));
            context.getBean(ConcreteClient.class).run();
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

Lines printed by `Main` and `TraceAspect`/clients in the example configuration:

```text
jdk proxy: true
jdk is concrete: false
concrete lookup: failed
advice: before greet
interface client: Hello Lan
cglib proxy: true
cglib is concrete: true
advice: before greet
concrete client: Hello Minh
```

**Explanation of output:**

1. Spring AOP finds `TraceAspect`, sees the pointcut matches `GreetingService.greet`, and creates an AOP proxy for the target bean.
2. In `JdkConfig`, the proxy implements `GreetingPort` but does not extend `GreetingService`. Hence lookup by `GreetingService.class` is rejected, while the constructor requiring `GreetingPort` receives a compatible dependency.
3. When `InterfaceClient.run()` calls `service.greet("Lan")`, the call through the **JDK proxy** executes advice before the target method returns the string.
4. In `ClassConfig`, the proxy is a CGLIB subclass of `GreetingService`; `ConcreteClient` is injected by the concrete type and still invokes through the proxy.
5. Each `ApplicationContext` has its own beans and configuration, so the example does not let one context's `proxyTargetClass=true` force the other context into CGLIB.

The example has **one advisor matching one method**. Adding other advisors or auto-proxy infrastructure can change the proxy type and advice order; in that case, inspect the actual runtime state.

## 6. Issues with `@Autowired`: The Injected Type Is a Contract

### 6.1. Choose an Interface When the Caller Only Needs the Business API

```java
@Service
public class InvoiceController {
    private final InvoiceService service;

    public InvoiceController(InvoiceService service) {
        this.service = service;
    }
}
```

This example assumes `InvoiceService` is an **interface** and Spring provides a single candidate bean (or `@Qualifier`/`@Primary` is used when needed). This reduces coupling between the controller and implementation/proxy details.

Whether Spring configures a JDK or CGLIB proxy, both can implement that interface. Using an interface **does not guarantee AOP by itself**: the method must match an advisor and be called through the bean proxy.

### 6.2. When Is Concrete Class Injection Still Valid?

Concrete class injection is valid when the container actually returns a compatible object. For example:

- The bean is **not proxied** and the original object belongs to the implementation class.
- The bean uses a **CGLIB proxy** without hitting class/method restrictions.
- The project has an explicit convention for class-based proxies and tests verifying the relevant beans.

What to avoid is writing code that depends on a concrete type while **not controlling the proxy strategy**. A change in AOP config or a Spring Boot property can cause the exact same injection code to fail.

### 6.3. `@Bean` Return Types Are Related but Do Not Replace Proxy Types

In Java configuration:

```java
@Bean
public PaymentService paymentService() {
    return new PaymentServiceImpl();
}
```

Spring gets type metadata from the `@Bean` declaration; the runtime instance may be `PaymentServiceImpl` before post-processing. However, if Spring subsequently creates a **JDK proxy**, the final object is assignable only to the interfaces exposed by the proxy.

Conversely:

```java
@Bean
public PaymentServiceImpl paymentService() {
    return new PaymentServiceImpl();
}
```

Declaring a concrete return type **does not force Spring AOP to use CGLIB**. `proxyTargetClass` configuration and proxy eligibility determine the strategy. Do not rely on the factory method's return type to cast a JDK proxy to the implementation.

## 7. Configuring Proxy Strategy in Spring

### 7.1. Plain Spring Framework

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class InterfaceProxyConfig {
}
```

For targets with business interfaces, this example **prefers JDK proxies** under Spring AOP rules. `false` does not guarantee every bean uses JDK: if a target has no suitable interface, Spring may still need a class-based proxy.

When CGLIB is needed:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class ClassProxyConfig {
}
```

This selects class-based proxies for eligible AOP beans within the configuration scope. It is not a way to make a `final` class proxyable.

### 7.2. Spring Boot

Per Spring Boot documentation, AOP auto-configuration **defaults to class-based (CGLIB) proxies**. To prefer JDK proxies when targets have interfaces:

```properties
spring.aop.proxy-target-class=false
```

To keep the class-based default or declare it explicitly:

```properties
spring.aop.proxy-target-class=true
```

When AspectJ is on the classpath and auto-configuration is enabled, Spring Boot usually does not need `@EnableAspectJAutoProxy` added to work. However, the aspect must still be registered as a Spring bean.

An important difference: **plain Spring Framework** typically defaults to JDK proxies when interfaces exist; **Spring Boot auto-configuration** defaults to CGLIB. Do not apply results from a Boot application to every plain Spring Framework application.

### 7.3. Proxy Configuration Can Affect Other AOP Infrastructure

Spring can merge several auto-proxy creator configurations, and the **stronger `proxyTargetClass=true` setting** can affect proxies created by transaction or other AOP infrastructure in the same context. Therefore:

- Avoid adding `@EnableAspectJAutoProxy(proxyTargetClass=true)` just to “fix” an injection error if it alters the application-wide proxy strategy.
- Review `@EnableTransactionManagement`, `@EnableCaching`, auto-configurations, and active global proxy settings.
- Verify **the actual object** with `AopUtils.isJdkDynamicProxy(...)`/`isCglibProxy(...)` after every change.

Spring Framework 7 also introduces per-bean proxy-target options (such as `@Proxyable` in supported versions); do not assume those newer APIs exist in Spring 6.2 of this example.

## 8. Cases That Commonly Cause Confusion

### 8.1. Multiple Implementations of the Same Interface

```java
public interface PaymentService { void pay(); }
public class CardPaymentService implements PaymentService { /* ... */ }
public class BankPaymentService implements PaymentService { /* ... */ }
```

If both are registered as Spring beans, a constructor accepting only `PaymentService` may **fail to disambiguate which bean to inject**. This is a **candidate resolution** issue, not a JDK/CGLIB proxy error. You can use `@Qualifier`, `@Primary`, or inject `List<PaymentService>` if business requirements suit it.

**Illustrative example:**

```java
public CheckoutController(@Qualifier("cardPaymentService") PaymentService service) {
    this.service = service;
}
```

This is a constructor snippet requiring `@Qualifier` and related type imports; not a standalone program.

### 8.2. JDK Proxy Still “Knows” the Target Class

`AopUtils.getTargetClass(proxy)` can return `PaymentServiceImpl.class` even when:

```java
proxy instanceof PaymentServiceImpl // false with a JDK proxy
```

There is no contradiction: **the target class** is the class behind the proxy, while **the proxy's runtime type** governs assignment/casting/injection. Do not use `getTargetClass` as an excuse to cast a proxy to the target implementation.

### 8.3. Bean Names Do Not Fix Assignability Errors

`@Qualifier("paymentService")` helps **select a bean by qualifier/name**, but it does not turn a JDK proxy into a subtype of `PaymentServiceImpl`:

```java
// Still incompatible if Spring is returning a JDK proxy:
public CheckoutController(
        @Qualifier("paymentService") PaymentServiceImpl service) {
    // ...
}
```

If you need to inject the implementation class, ensure **a class-based proxy is actually created** or redesign the API rather than just adding a qualifier.

### 8.4. Classes Implementing No Interface

A target implementing no business interface cannot be represented via its business API by a JDK dynamic proxy; in normal Spring AOP, a class-based proxy is required. `proxyTargetClass=false` only means do not **force** CGLIB where an interface proxy is feasible, rather than being able to create a JDK proxy for any arbitrary class.

### 8.5. Interface Default Methods and Generic Methods

JDK proxies expose interface methods, including some default methods, yet advice matching still depends on the expression, implementation, and call path through the proxy. When using generics/bridge methods or overloads, inspect **the actual method signature** instead of inferring from the name. Choosing interface-based injection does not replace verifying pointcuts.

### 8.6. Do Not “Unwrap the Target” to Avoid Cast Errors

You may come across retrieving the underlying target via `Advised.getTargetSource().getTarget()` and casting to the implementation. This approach **bypasses the proxy**, risking bypassing transactions, caching, security, or `@Aspect` advice. Some target sources are also tied to scopes and may supply a different target on each access.

If a caller needs a business behavior, expose that behavior through an interface/bean supplied by Spring instead of unwrapping the proxy to call the target directly.

### 8.7. Spring Data, Scoped Proxies, and Other Proxies

A Spring Data repository is typically used via **the repository interface**; however, that may be a proxy backing Spring Data queries/implementations rather than necessarily a Spring AOP proxy created from a specific `@Aspect`.

Scoped proxies can use Spring AOP machinery to resolve the target for the current scope. When debugging an injection error, identify **which feature's proxy** it is; do not conclude from a generated class name alone. The general rule remains **which types the proxy is actually assignable to**.

## 9. Checklist for Diagnosing Injection Errors with AOP

### Step 1: Read the Exception and Required Type

Example:

```text
BeanNotOfRequiredTypeException
Required type: example.GreetingService
Actual type: jdk.proxy...$Proxy...
```

This **illustrates the message structure**, not a fixed verbatim exception across every JDK/Spring version. If you see the actual type is a JDK proxy, check concrete dependencies or casts.

### Step 2: Inspect the Proxy Returned by the Context

```java
// Snippet placed in code with an ApplicationContext context.
Object bean = context.getBean("paymentService");
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(bean.getClass().getName());
System.out.println(AopUtils.getTargetClass(bean).getName());
```

Relevant imports are `org.springframework.aop.support.AopUtils` and `org.springframework.context.ApplicationContext`. Do not hard-code generated proxy class names in business code or tests: JDK/Spring may change naming conventions.

### Step 3: Compare the Proxy's Interfaces with the Constructor Parameter

- If the bean is a JDK proxy, is the parameter **an interface exposed by the proxy**?
- If the parameter is a concrete class, is there a mandatory reason?
- If BeanFactory finds multiple candidates, resolve the ambiguity separately with `@Qualifier`/`@Primary`.
- If a class-based proxy is expected, are the class/methods `final`, `private`, or access-restricted?

### Step 4: Check Proxy Configuration

- In plain Spring Framework, what `@EnableAspectJAutoProxy(proxyTargetClass=...)` or XML AOP/auto-proxy settings exist?
- In Boot, what value does `spring.aop.proxy-target-class` have, and is auto-configuration enabled?
- Are transaction/cache/security or other auto-proxy infrastructures participating in proxy configuration?

### Step 5: Verify Advice Behavior

After fixing injection, still **invoke a pointcut-matching method through the bean reference** to confirm advice executes. Type compatibility does not guarantee calls go through the proxy: calling `new ServiceImpl()` or self-invoking `this.pay()` can still skip advice.

## 10. How to Choose in a Spring AOP Project

| Practical requirement | Approach |
| --- | --- |
| Caller only needs behavior already on the interface | **Inject the interface**, compatible with both JDK and CGLIB proxies |
| Has interface, wants flexible implementation swapping | **Inject the interface** and configure bean resolution with qualifiers if needed |
| Needs a method outside the interface | Consider adding the method to an appropriate interface or designing a dedicated bean; use class-based proxies when justified |
| Legacy app mostly injects concrete classes | Can choose CGLIB with thorough tests for `final` limits and context-wide config effects |
| Getting `ClassCastException` from JDK proxy → implementation | **Do not cast**; identify the proxy and change the dependency to a compatible interface |
| Bean has multiple implementations of the same interface | Resolve with `@Qualifier`/`@Primary` or a bean selection strategy, do not flip proxy modes arbitrarily |
| Adding an aspect breaks previously working concrete injection | Check whether the bean had no proxy before; the new advisor caused Spring to create a JDK proxy, exposing the concrete type dependency |
| Need to test AOP accurately | Test proxy types and calls through **beans from the context**, do not test `new Target()` in isolation |

Most important takeaway: **Dependency injection receives the object Spring actually supplies, not necessarily the original target object.** When Spring AOP creates a JDK proxy, the contract for callers is the interface; when it creates a CGLIB proxy, the contract can include the concrete class. Choose dependency types according to the API callers need and verify the active proxy type.

## 11. Self-Check

**Question 1.** `OrderServiceImpl implements OrderService`. Spring creates a JDK proxy for `OrderServiceImpl`. Is the constructor `CheckoutController(OrderServiceImpl service)` compatible with the proxy object?

**Answer:** No. A JDK proxy does not extend the implementation class. Use `CheckoutController(OrderService service)` if that API meets the need.

**Question 2.** The same bean switches to a CGLIB proxy; can a constructor accepting `OrderServiceImpl` work?

**Answer:** Yes, if `OrderServiceImpl` is validly subclass-proxied and Spring can resolve the right bean. However, `final`/`private` methods still are not intercepted via overriding.

**Question 3.** `AopUtils.getTargetClass(bean)` is `OrderServiceImpl.class`. Can `bean` be cast to `OrderServiceImpl`?

**Answer:** Not enough to conclude. You must check the runtime proxy type; if the bean is a JDK proxy, the cast is still invalid.

**Question 4.** A Spring Boot app has `spring.aop.proxy-target-class=false`, the bean has an interface, and a pointcut matches. Which type should be injected to avoid depending on class-based proxies?

**Answer:** Inject via the interface exposed by the proxy.

**Question 5.** The bean is validly injected by concrete type, yet `this.pay()` inside the same target does not trigger `@Before`. Is the CGLIB proxy broken?

**Answer:** No. That is **self-invocation**: internal calls via `this` bypass Spring AOP proxies, whether JDK or CGLIB.

## 12. Official Spring Documentation

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK dynamic proxies and CGLIB, `proxy-target-class`, `final` methods, `this` limitations.
- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html): rule for choosing JDK proxies when interfaces exist and using CGLIB when class-based proxies are needed.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): `@EnableAspectJAutoProxy` and aspect bean requirements.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): `spring.aop.proxy-target-class` configuration and default choices.
- [Spring Framework — AopUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): identifying proxies and target classes.
