# Declaring an @Aspect Class and Registering It in the Spring Container

## 1. Expected Outcomes

In Spring AOP, annotating a class with `@Aspect` only **describes** that the class can contain pointcuts and advice; for Spring AOP to actually use that class, Spring must **know about the aspect instance as a bean** in an `ApplicationContext` with `@AspectJ` support enabled.

After this lesson, you should be able to do three independent things:

1. Write an `@Aspect` class with valid advice.
2. Register that class as a **Spring bean**, typically via `@Component` and component scanning, or via `@Bean` in `@Configuration`.
3. Enable Spring AOP support and verify that method calls on the **target bean** pass through a proxy to trigger advice.

This lesson is about **how Spring discovers, creates, and manages aspect beans**. Only the pointcut/advice knowledge needed to prove that registration works is used; general Aspect theory is outside the scope of this lesson.

## 2. What Is `@Aspect` to the Spring Container?

Let's distinguish three common roles:

| Component | Annotation / declaration method | What Spring does |
| --- | --- | --- |
| **Aspect class** | `@Aspect` from `org.aspectj.lang.annotation.Aspect` | When the class is a bean in a context with `@AspectJ` support, Spring reads its pointcuts/advice to create advisors |
| **Aspect bean** | `@Component` + scanned, or `@Bean` declaration, XML, bean definition | The container creates/provides the aspect instance, performs dependency injection, and manages its lifecycle accordingly |
| **Target bean** | For example `@Service`, `@Repository`, `@Bean` | If a method matches an advisor and can be proxied, Spring returns an AOP proxy to the caller so advice has a chance to run |

Key points:

- `@Aspect` is **not** a Spring stereotype like `@Component`; merely annotating with `@Aspect` is **not enough** for the component scanner to put the class into the container.
- `@Component` puts the class into the scan scope (if its package is within the scan range); `@Component` by itself **does not enable** AOP and does not make Spring treat the class as an aspect if `@Aspect` is missing.
- `@EnableAspectJAutoProxy` enables the Spring AOP component that detects aspect beans, creates advisors, and auto-proxies matching target beans. It **does not automatically scan** any classes outside of bean definitions.
- With plain Spring Framework, `org.aspectj:aspectjweaver` must be on the classpath for `@AspectJ` expression processing. The library name does not mean the application is running load-time weaving: the mechanism demonstrated here is still **Spring AOP proxies**.

Execution flow:

```text
@Aspect class
    |
    +-- @Component + component scan --------+
    |                                       |
    +-- @Bean / other bean declaration -----+--> aspect bean in ApplicationContext
                                                  |
                             @EnableAspectJAutoProxy / Boot AOP auto-configuration
                                                  |
                                             detect advice
                                                  |
                                        create advisors and inspect target beans
                                                  |
Caller --> target Spring bean proxy --> advice --> target method
```

If either the **aspect registration** step or the **enable AOP support** step is missing, simply having the `@Before` annotation in the source code will not automatically cause business calls to be intercepted.

## 3. Approach 1: `@Aspect` Combined with `@Component`

This is the common approach when a project organizes aspects as classes belonging to packages scanned by Spring:

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {

    @Before("execution(* example.OrderService.submit(..))")
    public void beforeSubmit() {
        System.out.println("[audit] before submit");
    }
}
```

- `@Aspect`: allows Spring to recognize advice declarations once the instance is already a bean.
- `@Component`: allows the component scanner to register `AuditAspect` as a Spring bean.
- `@Before(...)`: the advice method runs before a call to `OrderService.submit(..)` that goes through the AOP proxy and matches the pointcut.

`@Aspect` and `@Component` perform two different jobs. Do not assume `@Aspect` automatically discovers the class, even when the package is scanned.

The example here uses `@Component`; a custom stereotype properly meta-annotated with `@Component` can also perform the registration job.

## 4. Runnable Example with Plain Spring Framework and Java 17+

This example demonstrates the entire chain: **declaring an aspect → component scan → dependency injection → proxy activation → call receiving advice**. The configuration uses Spring Framework 6.2.x and does not require Spring Boot.

### 4.1. Project Structure

```text
spring-aspect-bean-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── AuditSink.java
    ├── AuditAspect.java
    ├── OrderService.java
    └── Main.java
```

### 4.2. `pom.xml`

Use the same Spring Framework version for `spring-context` and `spring-aop`; the example chooses 6.2.19. For real-world applications, let the Spring BOM or Spring Boot manage versions instead of pinning individual modules arbitrarily.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aspect-bean-demo</artifactId>
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

### 4.3. Spring Bean Injected into the Aspect

**`AuditSink.java`**

```java
package example;

import org.springframework.stereotype.Component;

@Component
public class AuditSink {
    public void record(String event) {
        System.out.println("[audit] " + event);
    }
}
```

**`AuditAspect.java`**

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    private final AuditSink sink;

    public AuditAspect(AuditSink sink) {
        this.sink = sink;
    }

    @Before("execution(* example.OrderService.submit(..))")
    public void beforeSubmit() {
        sink.record("before submit");
    }
}
```

**`OrderService.java`**

```java
package example;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public void submit(String orderId) {
        System.out.println("order submitted: " + orderId);
    }
}
```

**`AppConfig.java`**

```java
package example;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "example")
@EnableAspectJAutoProxy
public class AppConfig {
}
```

**`Main.java`**

```java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            AuditAspect aspect = context.getBean(AuditAspect.class);
            OrderService service = context.getBean(OrderService.class);

            System.out.println("aspect bean exists: " + (aspect != null));
            System.out.println("service is proxy: " + AopUtils.isAopProxy(service));
            System.out.println("aspect is proxy: " + AopUtils.isAopProxy(aspect));

            service.submit("A-100");
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

Lines printed by the program above:

```text
aspect bean exists: true
service is proxy: true
aspect is proxy: false
[audit] before submit
order submitted: A-100
```

Exact interpretation:

1. `AnnotationConfigApplicationContext` loads `AppConfig`.
2. `@ComponentScan` finds classes with Spring stereotypes in package `example`. Thanks to `@Component`, `AuditAspect` becomes a bean; `AuditSink` and `OrderService` also become beans.
3. Spring injects `AuditSink` into the constructor of `AuditAspect`. Because an aspect is a bean, it can use constructor injection like other Spring beans.
4. `@EnableAspectJAutoProxy` activates Spring AOP auto-proxy, detects aspects with `@Aspect`, and identifies advice matching `OrderService.submit(..)`.
5. Spring provides a proxy for `OrderService`. When the client calls `service.submit("A-100")`, the advice runs first and then enters the business method.
6. `aspect is proxy: false` is the **correct** result: Spring AOP excludes `@Aspect` beans from being auto-proxied by other aspects; an aspect bean **does not need to be an AOP proxy** for the advice it declares to run.

For applications with a logging framework, framework log lines may appear in addition to the example lines; the lines above are the output from the `System.out.println` statements in the code.

## 5. Approach 2: `@Bean` Declaration in `@Configuration`

It is not always appropriate to annotate an aspect class with `@Component`. When explicit configuration is needed, creating the aspect via a `@Bean` factory method is very useful.

**How to switch the Section 4 example to `@Bean`:** remove only the `@Component` annotation from `AuditAspect` (keeping `@Aspect` and the constructor), then replace the entire `AppConfig.java` with:

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "example")
@EnableAspectJAutoProxy
public class AppConfig {

    @Bean
    public AuditAspect auditAspect(AuditSink sink) {
        return new AuditAspect(sink);
    }
}
```

Keep the rest of Section 4 unchanged; run the same Maven command and receive equivalent output lines.

Explanation:

- `@Bean` causes the **return value from `auditAspect(...)`** to be registered and managed by Spring.
- The `AuditSink sink` parameter is resolved from the container and passed into the aspect constructor.
- There is no need to place `@Component` on `AuditAspect`: Spring detects `@Aspect` on the **class of the registered bean**.
- Avoid unintentionally both scanning `AuditAspect` with `@Component` and creating another `@Bean AuditAspect`; this can create **two aspect beans**, leading to duplicate advice execution and ambiguity when injecting by type. If there are multiple beans of the same type, `getBean(AuditAspect.class)` may throw `NoUniqueBeanDefinitionException`.

**Distinction to keep in mind:** `new AuditAspect(sink)` inside a `@Bean` factory method is valid because the **returned instance is registered by Spring**. Conversely, calling `new AuditAspect(...)` directly in application code without putting that instance into the container **does not register** the aspect with Spring AOP.

### 5.1. Declaring an Aspect Bean with XML

In legacy Spring XML applications, a class with only `@Aspect` can be declared via a bean definition:

```xml
<!-- Illustrative snippet inside a <beans> element with the aop namespace declared. -->
<bean id="auditAspect" class="example.AuditAspect">
    <constructor-arg ref="auditSink"/>
</bean>

<aop:aspectj-autoproxy/>
```

In this approach, `auditSink` must also be declared as a bean. `<aop:aspectj-autoproxy/>` is the XML equivalent of enabling Spring AOP proxies in Java configuration; the XML snippet above is not a standalone XML file. Most new applications use Java configuration or Spring Boot.

## 6. If Using Spring Boot

With Spring Boot, `@SpringBootApplication` combines component scanning from the application class's package; if the `@Aspect` class is within the scan scope and has `@Component`, it is registered like a normal bean.

Example aspect declaration snippet in a Boot application:

```java
package example.app.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class RequestAuditAspect {
    @Before("execution(* example.app.service.OrderService.submit(..))")
    public void beforeOrder() {
        System.out.println("[audit] submitting order");
    }
}
```

**This is an illustrative class to insert into an existing Boot application**, assuming a service `example.app.service.OrderService` with a `submit` method exists. When actually running, `@SpringBootApplication` must be in the parent package `example.app` or `scanBasePackages` must be configured appropriately.

Regarding dependencies:

- **Spring Boot 3.x**: normally uses `org.springframework.boot:spring-boot-starter-aop`.
- **Spring Boot 4.x**: this starter has been renamed to `org.springframework.boot:spring-boot-starter-aspectj`.
- Use the appropriate starter/BOM to bring `spring-aop` and `aspectjweaver` onto the classpath. Do not manually choose two versions that conflict with the Spring Boot BOM.

When AspectJ is on the classpath, Spring Boot has AOP auto-configuration by default and usually **does not require** manually adding `@EnableAspectJAutoProxy`. If the project disables related auto-configuration or customizes `spring.aop.auto=false`, you must review the configuration before expecting advice to run. By default, Boot typically chooses **class-based proxies (CGLIB)**; `spring.aop.proxy-target-class=false` can be used to prefer interface-based proxies when appropriate.

**Do not confuse two conditions:** Spring Boot automatically enabling the AOP mechanism does not mean it automatically registers every class that only has `@Aspect`; that class still needs to enter the container via `@Component`, `@Bean`, or a valid bean registration method.

## 7. Managing Aspect Beans: Scope and Characteristics

### 7.1. An Aspect Is a Bean, but with a Special Role

Spring can inject dependencies into an aspect, apply callbacks/lifecycle hooks corresponding to the bean definition, and manage it as a singleton like a regular bean. However, for Spring AOP:

- The aspect bean is the **source of advisor declarations**, whereas proxies are normally created for matching **target beans**.
- Spring excludes `@Aspect` classes themselves from becoming auto-proxy targets of other aspects. Therefore, calls on an aspect instance should not be expected to trigger advice declared by another aspect.
- By default, Spring uses a model of **one aspect instance per ApplicationContext** (singleton aspect). Special instantiation models such as `perthis` and `pertarget` are advanced topics and are not needed for basic declaration.

### 7.2. Keeping State Safe in an Aspect

A singleton aspect typically serves many concurrent calls from multiple beans/threads. Therefore:

- Prefer aspects that **do not hold per-request mutable state** in fields.
- For per-invocation information, use local variables inside the advice, parameters bound into the advice by Spring/AspectJ, or a dedicated context-appropriate abstraction.
- If you need to record logs/events, inject a bean with a clear responsibility such as `AuditSink`, instead of accumulating request data in unsynchronized mutable fields.

Example of what **not to do** in a singleton aspect:

```java
// Illustrates a flawed design under multithreaded execution; not a standalone program.
private String currentOrderId; // requests can overwrite each other
```

### 7.3. Multiple ApplicationContexts

An aspect registered in one context does not mean it will advise every object in every context of the application. The auto-proxy mechanism and bean scope depend on the context where it is configured. For applications with parent/child contexts or multiple separate contexts, identify which context the **aspect bean** and **target bean** belong to, which proxy creator is operating, and where the reference received by the client comes from.

## 8. Common Errors When Declaring `@Aspect`

| Symptom | Common cause | How to check / fix |
| --- | --- | --- |
| Class has `@Aspect` but advice does not run | Missing `@Component`/`@Bean`, so the class is not in the context | Find bean of type `AuditAspect` with `context.getBeanNamesForType(...)`; register explicitly |
| Has `@Component` but Spring does not find the aspect | Class is outside `@ComponentScan` | Check the root package of `@SpringBootApplication` or `@ComponentScan` |
| Aspect bean exists but target method does not receive advice | Spring AOP not enabled or library missing, pointcut does not match, call bypasses proxy | Check `@EnableAspectJAutoProxy`/Boot auto-config, `aspectjweaver`, `AopUtils.isAopProxy(target)` |
| Advice unexpectedly runs twice | Two identical aspect beans registered via both `@Component` and `@Bean`, or two independent aspects both match | Print the list of beans by type; check for duplicate registration configuration |
| `NoSuchBeanDefinitionException` for the aspect | Bean is not registered or is in a different context | Check bean creation conditions, package scan, profile, actual context |
| `NoUniqueBeanDefinitionException` when injecting the aspect | Multiple aspect beans of the same type exist | Remove duplicate declaration or specify the desired bean with `@Qualifier` |
| `AopUtils.isAopProxy(aspect)` returns `false` | **Normal behavior**: `@Aspect` classes are not auto-proxy targets | Check `AopUtils.isAopProxy(targetService)` and the advice execution result |
| Aspect has `null` or missing dependencies | Aspect object created outside Spring, not receiving DI; or bean wiring error | Let the container create/inject the aspect via `@Component` or `@Bean` |
| Advice does not run when service calls `this.inner()` | Self-invocation does not go through the proxy | Call through a bean/proxy or extract the logic into another bean |

### Checking Directly in the Context

The following Java snippet illustrates how to check inside a method that has `ApplicationContext context`:

```java
// Illustrative snippet; requires the corresponding beans/types to be declared.
String[] names = context.getBeanNamesForType(AuditAspect.class);
System.out.println(java.util.Arrays.toString(names));

OrderService target = context.getBean(OrderService.class);
System.out.println(org.springframework.aop.support.AopUtils.isAopProxy(target));
```

With the Section 4 example, the list usually contains the bean named `auditAspect`; the target has a proxy because the pointcut matches. Checking `context.containsBean("auditAspect")` only tells you whether a bean name is registered, not a substitute for verifying that advice runs.

## 9. Comparison Scenarios

| Scenario | Does `@Aspect` become a source of advice for Spring AOP? | Why |
| --- | --- | --- |
| `@Aspect @Component`, package is scanned, AOP support enabled | **Yes** | Registered as a Spring bean and Spring recognizes the aspect metadata |
| Only `@Aspect`, even if package is scanned, no other bean declaration | **No** | `@Aspect` by itself is not a component marker |
| `@Aspect` class without `@Component`, but returned by `@Bean` | **Yes** | The instance is registered via the factory method |
| `@Component` with a `@Before` method but without `@Aspect` | **No under this `@AspectJ` model** | Spring does not recognize the class as an `@AspectJ` aspect |
| `@Aspect @Component` but AOP auto-proxy is not enabled | **No automatic Spring AOP advice** | Bean exists, but the aspect/proxy processing step is missing |
| Creating `new MyAspect()` outside Spring | **No** | The instance is not part of the aspect beans read by the proxy creator |
| Valid aspect bean, target is an object manually created with `new` outside the container | Aspect **is registered**, but **that target is not advised by a Spring proxy** | Spring AOP only intercepts calls through proxies of managed beans |

**Self-check:** If you change `AuditAspect` in the runnable example to have only `@Aspect` and no `@Bean` declaration, what happens? Spring will not register `AuditAspect` via component scan, so `context.getBean(AuditAspect.class)` cannot find the bean; the program will fail at the bean lookup step and not reach the `submit` call. If you remove the line retrieving the aspect and still call the service, `OrderService` will not receive advice from the unregistered aspect class.

## 10. Official Spring References

- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html): `@Aspect`, registering via `@Bean` or component scan, note about not auto-proxying aspect beans.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): `@EnableAspectJAutoProxy`, AspectJ library on classpath, and proxy creation process.
- [Spring Framework — Aspect Instantiation Models](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html): singleton default, advanced models.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): why advice requires calls through a proxy and self-invocation limitations.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): Spring Boot AOP auto-configuration and proxy selection.
