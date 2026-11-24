# Spring AOP: Registering Target Beans and Avoiding Objects Created with `new` Outside the Container

## 1. Real-World Problem: Same Class, Why Does a Call Run Advice or Not?

Suppose an application has a `ReceiptService` and an aspect that logs before the `issue()` method. The following two ways of using it can lead to different outcomes:

```java
// Spring-managed object: has a chance to receive an AOP proxy when an advisor matches.
ReceiptService managed = applicationContext.getBean(ReceiptService.class);
managed.issue("INV-01");

// Manually created Java object: does not automatically pass through Spring AOP infrastructure.
ReceiptService unmanaged = new ReceiptService();
unmanaged.issue("INV-02");
```

This snippet only illustrates how to obtain objects, not a standalone program. With proxy-based Spring AOP:

- `applicationContext.getBean(...)` returns a **Spring-managed bean**, which can be an **AOP proxy** if the AOP infrastructure is enabled and a matching advisor exists.
- `new ReceiptService()` creates a **standalone Java object**, which is not automatically registered and processed by Spring as a bean merely because its class is annotated with `@Service`.
- Advice runs when the call **goes through the proxy**, not because some annotation is present on the class or because the object was created from the same source code.

A **necessary** condition for Spring AOP to automatically advise a regular service is that the object is managed by Spring and calls to it pass through an appropriate proxy. However, **registering a bean does not automatically guarantee advice**: you still need Spring AOP enabled, a registered aspect/advisor, a matching pointcut, and calls going through the proxy.

### Execution Paths of the Two Objects

```text
                           ApplicationContext
                                |
                     Bean definition for service
                                |
                     Create + configure target bean
                                |
                   Auto-proxy creator (if matched)
                                |
                  Spring bean reference: proxy
                                |
           Controller / Workflow receives service via DI
                                |
               proxy -> advice -> target.issue()


             Code outside Spring calls:
                   new ReceiptService()
                                |
                      object.issue() directly
                                |
                     No Spring AOP proxy
```

This is the **Spring AOP proxy** mechanism inside the Spring IoC container. Do not extrapolate this to AspectJ compile-time/load-time weaving, which operates at the bytecode level and has a different scope.

## 2. Registering Target Beans Properly

### Approach A — Component Scanning with `@Component` / `@Service`

Declare the business class as a Spring component:

```java
package demo.springaop;

import org.springframework.stereotype.Service;

@Service
public class ReceiptService {
    public void issue(String id) {
        System.out.println("[service] issue " + id);
    }
}
```

Enable component scanning for the right package:

```java
package demo.springaop;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy
public class AppConfig {
}
```

These two files are part of the full example in Section 5. `@Service` is a specialization of `@Component`, so the Spring component scanner can find it. `@Repository`, `@Controller`, and `@Component` are also related stereotypes, though you should choose the stereotype that matches the role.

**Scan scope matters greatly:** if a class has `@Service` but its package lies outside the `@ComponentScan` scope, Spring will not create a bean from that class via scanning. In Spring Boot, `@SpringBootApplication` includes component scanning starting from the package containing the application class and its subpackages by default; place the main class in an appropriate parent package, or configure `scanBasePackages`/`scanBasePackageClasses` when project structure requires it.

`@Component` or `@Service` does not turn every `new ReceiptService()` call into a bean. The annotation is metadata for **the container to process when discovering classes**; it does not intercept Java's `new` operator.

### Approach B — Registering a Target with `@Bean`

When annotating the class with `@Service` is inconvenient (external libraries, code requiring factory construction, specific configuration), a `@Bean` method can be used:

```java
@Configuration
class ReceiptConfig {
    @Bean
    ReceiptService receiptService() {
        return new ReceiptService();
    }
}
```

This is an **alternative approach**: remove `@Service` or exclude the class from component scan if also using `@Bean`, to avoid accidentally registering two beans of the same type and making type-based DI ambiguous.

The difference lies in **who retains ownership of managing the instance**:

- Inside `@Bean`, writing `new ReceiptService()` is completely normal: Spring invokes the factory method, takes the returned object, puts it into the bean lifecycle, and applies relevant `BeanPostProcessor`/auto-proxy steps.
- If business code manually writes `new ReceiptService()` and keeps that reference itself, Spring does not know which bean definition that new object belongs to.
- A helper you construct with `new` inside another bean also does not automatically become a **separate bean** merely because the enclosing bean is managed by Spring.

In other words, the advice to “avoid `new` outside the container” applies to **dependencies needing IoC/AOP**, not a ban on every `new` operator. You can still construct regular DTOs, records, value objects, collections, and temporary objects using `new`.

### Approach C — Programmatic Registration and XML

Spring also supports registering bean definitions via container APIs or XML configuration. Illustrative XML example:

```xml
<bean id="receiptService" class="demo.springaop.ReceiptService"/>
```

This fragment is not a complete XML file. From an AOP standpoint, the specific registration method is not the focus: what matters is that the container has a **bean definition**, manages instantiation, and can publish a proxy reference.

### Additional Condition: The Aspect and AOP Infrastructure Must Also Be Registered

Having a target bean is not enough. With Spring's `@AspectJ` declaration style:

```java
@Aspect
@Component
public class ReceiptAspect {
    @Before("execution(* demo.springaop.ReceiptService.issue(..))")
    public void beforeIssue() {
        System.out.println("[aop] before issue");
    }
}
```

This snippet illustrates the aspect; full imports are in Section 5. `@Aspect` **does not automatically cause the class to be registered by the component scanner**; also add `@Component` or create the aspect via `@Bean`. The auto-proxy infrastructure must also be enabled, e.g., `@EnableAspectJAutoProxy` when using plain Spring Framework. Spring Boot with `spring-boot-starter-aop` can be used to get appropriate AOP auto-configuration.

**Distinction:** `@Aspect` describes the aspect, while `@Service`/`@Component`/`@Bean` put instances into the container. Target bean and aspect bean are two different roles in Spring AOP.

## 3. Why Can the Container Return a Proxy?

Typical sequence for a singleton:

1. Spring learns the target's bean definition via component scan, `@Bean`, or an equivalent registration mechanism.
2. The container creates the instance, resolves dependencies, injects configuration, and runs initialization callbacks.
3. Spring AOP's `BeanPostProcessor` infrastructure inspects advisors; when a pointcut matches and a proxy is required, it can wrap the target with a proxy.
4. Another bean requesting the dependency from Spring receives **the reference published by the container**; if wrapped by AOP, this reference is a proxy.
5. Method calls through the proxy pass through interceptors/advice before or after reaching the target, depending on advice type and pointcut.

```text
Spring-managed consumer
        |
        | constructor injection
        v
   service reference
        |
        v
   Spring AOP proxy
        |
        +----> advice
        |
        v
   target method
```

Actual proxy creation timing can be affected by scope, circular dependencies, or custom post-processors. The essence does not change: **the caller must use the proxy reference**, not a separate manually created target.

### Same Class Type Does Not Necessarily Mean Same Object

The following two lines are not equivalent:

```java
ReceiptService fromSpring = context.getBean(ReceiptService.class);
ReceiptService fromNew = new ReceiptService();
```

For a Spring-managed singleton wrapped by AOP, `fromSpring` is typically a proxy reference. `fromNew` is a standalone instance. Checks like `fromSpring == fromNew` will generally yield `false`; nor should you rely on `fromSpring.getClass() == ReceiptService.class` when Spring has created a subclass proxy.

Use Spring's API to diagnose:

```java
boolean proxied = AopUtils.isAopProxy(fromSpring);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(fromSpring);
boolean cglibProxy = AopUtils.isCglibProxy(fromSpring);
```

These three statements only illustrate the API, not a standalone program. In the complete example, the service does not implement an interface, so Spring AOP typically creates a class-based proxy. If the target has an interface, the proxy type depends on configuration such as `proxyTargetClass`; always inspect **the actual bean received**.

## 4. Dependency Injection Is the Standard Way to Deliver Proxies to Callers

Instead of:

```java
public class CheckoutWorkflow {
    private final ReceiptService service = new ReceiptService();

    public void checkout(String id) {
        service.issue(id);
    }
}
```

make the workflow a Spring bean and declare constructor injection:

```java
@Component
public class CheckoutWorkflow {
    private final ReceiptService service;

    public CheckoutWorkflow(ReceiptService service) {
        this.service = service;
    }

    public void checkout(String id) {
        service.issue(id);
    }
}
```

The snippets in this section illustrate the difference, not standalone Java files. When `CheckoutWorkflow` is created by Spring, the container resolves `ReceiptService` and can inject the appropriate proxy. With a single constructor, Spring automatically chooses constructor injection without needing `@Autowired`.

**Note when calling from code outside Spring:** Controllers, scheduled tasks, message listeners, startup runners, tests, or objects created by other frameworks need to receive services from the container via the appropriate integration mechanism. Do not instantiate a service with `new` inside a callback and expect Spring aspects to intercept method calls. When beans must be retrieved at application boundaries, DI is preferred; calling `ApplicationContext.getBean(...)` directly is a reasonable choice at integration points, though business code should not be turned into a service locator.

### Two Different Mistakes Easily Confused

- **Target manually created with `new`:** the object has no Spring proxy in the first place. Even if a method is called from outside the object, Spring AOP has no proxy reference to intercept.
- **Self-invocation on a Spring-managed target:** the bean already has a proxy, but `this.otherMethod()` inside the target still calls directly on the target, bypassing the proxy. This is a call-path issue, not missing bean registration.

Example:

```java
@Service
class InvoiceService {
    public void outer() {
        this.inner(); // Does not go through the Spring AOP proxy.
    }

    public void inner() {
        // Advice for inner() will not automatically run when called from outer().
    }
}
```

This is an illustrative snippet in a system that has an advisor for `inner()`. The appropriate fix is to extract the advised portion into another Spring bean and inject that bean, so calls pass through the reference provided by the container.

## 5. Runnable Maven + Java 17 Example: Managed Bean vs. Manually `new`-ed Object

The example uses **Spring Framework 6.2.x**, Java 17, and Maven. Spring Boot is not needed. There are 5 Java files in package `demo.springaop` and one `pom.xml`. An aspect logs before `ReceiptService.issue()`; main compares calls on a Spring-managed bean and a manually created object.

Structure:

```text
spring-aop-managed-target/
├── pom.xml
└── src/main/java/demo/springaop/
    ├── AppConfig.java
    ├── ReceiptService.java
    ├── ReceiptAspect.java
    ├── CheckoutWorkflow.java
    └── DemoMain.java
```

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-managed-target</artifactId>
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

**File `src/main/java/demo/springaop/AppConfig.java`:**

```java
package demo.springaop;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy
public class AppConfig {
}
```

`@ComponentScan(basePackageClasses = AppConfig.class)` finds Spring components in package `demo.springaop`, where the target, workflow, and aspect live. `@EnableAspectJAutoProxy` allows Spring to automatically create proxies when advice matches.

**File `src/main/java/demo/springaop/ReceiptService.java`:**

```java
package demo.springaop;

import org.springframework.stereotype.Service;

@Service
public class ReceiptService {
    public void issue(String id) {
        System.out.println("[service] issue " + id);
    }
}
```

This service is discovered by Spring via `@Service`. The class and method are not `final`, so they can be wrapped with a class-based proxy in this interface-less example.

**File `src/main/java/demo/springaop/ReceiptAspect.java`:**

```java
package demo.springaop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class ReceiptAspect {
    @Before("execution(* demo.springaop.ReceiptService.issue(..))")
    public void beforeIssue() {
        System.out.println("[aop] before issue");
    }
}
```

The aspect is a Spring bean thanks to `@Component`, and also has `@Before` advice applying to `issue()`.

**File `src/main/java/demo/springaop/CheckoutWorkflow.java`:**

```java
package demo.springaop;

import org.springframework.stereotype.Component;

@Component
public class CheckoutWorkflow {
    private final ReceiptService receiptService;

    public CheckoutWorkflow(ReceiptService receiptService) {
        this.receiptService = receiptService;
    }

    public void checkout(String id) {
        System.out.println("[workflow] checkout " + id);
        receiptService.issue(id);
    }
}
```

The workflow is also created by Spring. The `receiptService` dependency in the constructor is the reference provided by the container; if Spring created an AOP proxy for the service, the workflow uses that proxy.

**File `src/main/java/demo/springaop/DemoMain.java`:**

```java
package demo.springaop;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoMain {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            ReceiptService managed = context.getBean(ReceiptService.class);
            System.out.println("managedProxy=" + AopUtils.isAopProxy(managed));

            context.getBean(CheckoutWorkflow.class).checkout("INV-01");

            ReceiptService unmanaged = new ReceiptService();
            System.out.println("manualProxy=" + AopUtils.isAopProxy(unmanaged));
            unmanaged.issue("INV-02");
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.springaop.DemoMain
```

**Stdout from the program's `System.out` statements** (Maven/Spring may emit other logs depending on the environment):

```text
managedProxy=true
[workflow] checkout INV-01
[aop] before issue
[service] issue INV-01
manualProxy=false
[service] issue INV-02
```

Point-by-point analysis:

1. `managedProxy=true`: Spring recognized `ReceiptService` as a target, `ReceiptAspect` has a matching pointcut, so the container provides a proxy.
2. `CheckoutWorkflow` uses constructor injection. When calling `receiptService.issue("INV-01")`, invocation through the proxy triggers `[aop] before issue` before the business line.
3. `new ReceiptService()` in `DemoMain` creates a standalone object, not a Spring bean; `AopUtils.isAopProxy(unmanaged)` returns `false`.
4. `unmanaged.issue("INV-02")` calls the manually created object directly, so **there is no `[aop]` line** for `INV-02`.
5. Nothing is wrong with the `issue()` method on the unmanaged object: Java still calls the method and prints the result. The difference is that **the AOP proxy infrastructure is not involved**.

If `@Component` is removed from `ReceiptAspect` without registering the aspect with `@Bean`, the aspect is not discovered; the target may still be a Spring bean but without the corresponding advice. If `@Service` is removed from `ReceiptService` without replacing it with `@Bean`, the application will lack a bean to inject into `CheckoutWorkflow` and context startup will fail when resolving the dependency.

### Same Class, Switching Registration Path to `@Bean`

To use a factory method instead of component scan, **remove `@Service` from `ReceiptService`** and add the following method to `AppConfig`:

```java
@Bean
public ReceiptService receiptService() {
    return new ReceiptService();
}
```

The snippet above is a **fragment placed inside a `@Configuration` class**, requiring `import org.springframework.context.annotation.Bean`. Even though it contains the `new` keyword, the returned object is a container-managed bean, so Spring AOP still has the opportunity to wrap it. This is an important exception that distinguishes “using `new` inside a bean factory” from “manually calling `new` on a service and invoking it outside the container”.

## 6. Harder Cases to Recognize

### 6.1 One Class with Two Instances: One Managed, One Unmanaged

For example, a Spring bean's constructor still creates its dependency manually:

```java
@Component
class ProcessingHandler {
    private final ReceiptService badService = new ReceiptService();

    void handle() {
        badService.issue("BAD");
    }
}
```

`ProcessingHandler` being managed by Spring **does not mean** `badService` inside it is managed by the container. This is simply a field referencing a new Java object. The fix is to pass `ReceiptService` into the constructor like in `CheckoutWorkflow`.

### 6.2 `@Autowired` on a Manually Created Object Does Not Work Automatically

```java
class OutsideContainer {
    @Autowired
    ReceiptService service;
}

// Created outside the container:
OutsideContainer object = new OutsideContainer();
```

This example is an illustrative fragment. The `service` field will not be automatically injected by Spring just because it has `@Autowired`. The reason shares the same root cause as AOP: the object did not go through the container's normal bean creation/configuration mechanism.

### 6.3 Having Two Beans of the Same Type

If both `@Service` and `@Bean` are used to create another `ReceiptService`, type-based injection can become ambiguous. Unintentional duplicate registration should be avoided. When multiple implementations or multiple beans of the same type are genuinely needed, name them clearly and use `@Qualifier` or `@Primary` appropriately. For Spring AOP, each bean selected by the container may receive its own proxy; do not equate “one class” with “one single Spring bean”.

### 6.4 Bean Scope and Objects Created Multiple Times

Default `singleton` has one bean instance per Spring container/bean definition according to its scope; it does not mean the entire JVM has only one object of that type. `prototype` allows the container to create a new instance whenever the bean is requested, and Spring still handles initialization/AOP accordingly. However, every `new ReceiptService()` outside the container still remains unmanaged merely because a prototype bean definition of the same class exists.

### 6.5 Two `ApplicationContext`s or Applications with Parent/Child Contexts

A target bean managed in context A is not guaranteed to be proxied by advisors/aspects configured in context B. `@EnableAspectJAutoProxy` is scoped per context; applications with multiple contexts must register configuration in the right place. Therefore, when debugging, check **the actual reference and context**, not just the class name.

### 6.6 Extracting the Raw Target and Calling It Directly

When Spring has created a proxy, you should not try to extract the internal target from the proxy to invoke business methods (for example via internal debug APIs) and wonder why advice does not run. Any call path bypassing the proxy bypasses advice. The same principle applies to self-invocation.

### 6.7 Are There Technical Exceptions for Processing Objects Created Outside the Container?

Spring has low-level integration APIs such as `AutowireCapableBeanFactory` to configure pre-created objects; `initializeBean(...)` can return a post-processed, even wrapped, object. However, **you must use the returned reference and manage its lifecycle carefully**: autowiring an external instance does not turn every existing reference pointing to that instance into an AOP proxy.

Spring also has AspectJ weaving integration for certain domain objects created outside the container, but that is **not** standard Spring AOP proxying and requires separate configuration. In this lesson, the default solution is to register the service as a bean and inject the proper reference from Spring.

## 7. Checklist When “Aspect Does Not Run”

| Symptom | Specific check |
| --- | --- |
| Service has `@Service` but advice does not run | Is the service component-scanned in the right package? Is it actually injected/`getBean`-ed from Spring? |
| Business code uses `new SomeService()` | Unmanaged object exists; replace with constructor injection of the Spring-managed service. |
| `@Bean` contains `new` so worried AOP won't work | The object **returned from the `@Bean` method** is a managed bean; check advisors/pointcuts and the reference the consumer uses. |
| Aspect has `@Aspect` but is not detected | Add `@Component` or a `@Bean` registering the aspect, and enable auto-proxy. |
| Target is a bean but `AopUtils.isAopProxy` is `false` | Check whether any advisor actually matches and whether auto-proxy is active in that context. |
| Proxy exists but one method is not advised | Check pointcut, proxy type, `final`/`private` methods, and call path via `this`. |
| Injection by concrete class fails when AOP is enabled | JDK dynamic proxy only implements interfaces; inject by interface or consider class-based proxy appropriately. |
| Both `@Service` and `@Bean` of the same type | Check duplicate beans, `@Qualifier`, `@Primary`, and the intended registration method. |
| Multiple `ApplicationContext`s exist | Verify target, aspect, and auto-proxy belong to the appropriate context. |
| Self-invocation `this.other()` | Calls target directly, bypassing proxy; extract the method needing interception into another Spring bean. |

To identify the cause in a logical order:

1. Find where the object is created. If it is `new` directly in business code, check whether it is a dependency needing AOP.
2. If it is already a bean, check the bean definition, component scan or `@Bean`, and context configuration.
3. Check that the aspect is also registered as a Spring bean, and auto-proxy is enabled.
4. On the reference injected or returned from the context, use `AopUtils.isAopProxy(...)`.
5. If it is already a proxy, confirm the method is called **through this reference** and the pointcut matches.
6. If advice still does not run, check self-invocation, method accessibility/finality, proxy type, and differences across contexts.

## 8. Review Questions

**1. Does adding `@Service` and writing `new Service()` give automatic AOP?** No. `@Service` only helps Spring discover the class during component scanning; an object created separately with `new` is not automatically managed by Spring.

**2. Is using `new` inside a `@Bean` method wrong?** No. This is a valid way to create an instance for Spring to manage. The container can post-process and proxy the returned object.

**3. If a bean is registered, is advice guaranteed to run?** No. AOP infrastructure must also be enabled, an aspect/advisor must match, the pointcut must match, and the call must go through the proxy.

**4. If a controller is managed by Spring, is every field it creates with `new` managed by Spring?** No. Only dependencies registered and resolved through the container have the corresponding bean lifecycle; directly created objects remain plain Java objects.

**5. How does `this.inner()` inside a proxied bean differ from `new Service().inner()`?** Both can bypass advice, but for different reasons: `this.inner()` is self-invocation bypassing the proxy, whereas an object created with `new` never had a proxy in the first place.

**6. How should code be organized to minimize errors?** Register targets and aspects as Spring beans, let Spring create consumers, use constructor injection for dependencies needing AOP, and establish inter-bean call boundaries for methods requiring interception.

## Official Spring Documentation

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — @AspectJ support and registering aspects](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html)
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
- [Spring Framework — Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring Framework — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework — Integrating AspectJ with Spring Applications](https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html)
