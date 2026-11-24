# Distinguishing `@Aspect` from Component-Registration Annotations in Spring AOP

## 1. Distinction to Make

In Spring AOP, a class with `@Aspect` is **not necessarily managed by the Spring container**. Conversely, a class with `@Component` is a candidate for Spring component scan to register as a bean, but **does not automatically become an aspect**. The two annotations answer **two different questions**:

- **`@Aspect`** answers: *Does this class declare advice/pointcuts for Spring AOP to recognize?*
- **`@Component`** (or an equivalent stereotype) answers: *Should the Spring component scanner detect and register this class as a bean?*

For advice from an `@Aspect` class to be used by Spring AOP, Spring must see that class **as a bean in the `ApplicationContext`**, and the application must also enable `@AspectJ` auto-proxy support. Both the aspect bean and the target bean must be configured so the AOP mechanism can apply.

This lesson focuses solely on annotations, bean registration, and aspect detection mechanisms **in Spring Framework/Spring Boot**. General Aspect concepts are outside the scope here.

## 2. Two Groups of Annotations with Different Responsibilities

| Criterion | `@Aspect` | `@Component` / component-registration annotation |
| --- | --- | --- |
| Library origin | `org.aspectj.lang.annotation.Aspect` (AspectJ) | `org.springframework.stereotype.Component` (Spring) |
| Primary role | Marks a class containing aspect declarations for Spring AOP to parse | Marks a class as a Spring bean candidate during component scan |
| Makes Spring scan find the class? | **No** | **Yes**, when the class is within the scan scope and meets conditions |
| Defines advice by itself? | Tells Spring to inspect `@Before`, `@Around`, ... methods inside the class | **No** |
| Enough for target calls to run advice? | No, requires an aspect bean, AOP mechanism, and matching target proxy | No, requires a matching advisor/pointcut and call through proxy |
| Can it be used alone? | Yes, when the aspect is already declared as a bean via `@Bean` or other means | Yes; an ordinary component does not need to be an aspect |
| Can they be used together? | **Yes** | **Yes** |

Two imports to remember:

```java
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;
```

**Important note:** The Spring Framework documentation explicitly states that `@Aspect` is **not sufficient for autodetection via classpath scanning**. You must add `@Component` or a valid custom stereotype according to component scanner rules, **or** register the aspect instance via `@Bean`, XML, or a bean definition. This is a Spring rule, not a syntactic difference between the two annotations.

## 3. Three Common Scenarios

### Case A: Only `@Aspect`

```java
package example.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.service.OrderService.submit(..))")
    public void beforeSubmit() {
        System.out.println("[audit] before submit");
    }
}
```

If the application configuration only uses `@ComponentScan` and **has no other bean definition for this class**, the scanner does not register `AuditAspect`. As a result:

- `AuditAspect` is a Java class with `@Aspect` metadata.
- **There is no `AuditAspect` bean** in the context provided by component scan.
- Advice inside it **is not used by Spring AOP** merely because the class is on the classpath.
- `@EnableAspectJAutoProxy` also **does not automatically turn classes outside the container into beans**.

That means writing only `@Aspect` is **not wrong**: it works if you **register the class as a bean by another means**, such as `@Bean`. The mistake is assuming that the annotation registers the bean by itself.

### Case B: `@Aspect` + `@Component`

```java
package example.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("execution(* example.service.OrderService.submit(..))")
    public void beforeSubmit() {
        System.out.println("[audit] before submit");
    }
}
```

This is the common pattern:

1. `@Component` allows the component scanner to discover the class and Spring to register `AuditAspect` as a bean (if the package is scanned).
2. `@Aspect` allows Spring AOP to parse that bean to find advice, pointcuts, and advisors.
3. If AOP is enabled, a target bean such as `OrderService` matching the pointcut can receive a proxy; calling the method through the proxy causes the advice to run.

### Case C: Only `@Component`, No `@Aspect`

```java
package example.aop;

import org.springframework.stereotype.Component;

@Component
public class AuditHelper {
    public void log(String event) {
        System.out.println("[helper] " + event);
    }
}
```

`AuditHelper` is a normal Spring bean that can be injected and called normally. It is **not recognized as an `@AspectJ` aspect** merely because the class is a component. Having a method named `beforeSubmit` also does not make Spring AOP treat it as advice.

> Practical rule: **`@Aspect` describes the class's AOP role; `@Component` allows the scanner to register the class as a bean.** Spring uses both pieces of information at different steps.

## 4. `@Component`, `@Service`, `@Repository`, and Custom Stereotypes

Spring annotations such as `@Service`, `@Repository`, and `@Controller` are stereotypes meta-annotated with `@Component`; they are used to mark the bean's role in each application layer. If you write:

```java
@Aspect
@Service
public class AuditAspect {
    // ...
}
```

Then in terms of **component scan eligibility**, a stereotype recognized by Spring such as `@Service` can still cause the class to be registered as a bean. However, **`@Component` is the clearer expression** for a technical aspect that is not a business service. Do not use `@Service` merely to fix Spring not finding an aspect.

Conversely, target beans are normally defined with annotations expressing their true role:

```java
@Service
public class OrderService {
    public void submit() {
        System.out.println("order submitted");
    }
}
```

The presence of `@Service` does not turn `OrderService` into an aspect. It is a **target bean** that can be intercepted by advice after Spring AOP creates an appropriate proxy.

### Custom Stereotype

You can also define a custom stereotype meta-annotated with `@Component`:

```java
package example.aop;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Component
public @interface InfrastructureComponent {
}
```

And use it:

```java
// Illustrates a class using a custom stereotype; advice methods are omitted.
@Aspect
@InfrastructureComponent
public class AuditAspect {
}
```

When the scanner recognizes `InfrastructureComponent` via meta-annotation, the class is a bean candidate. `@Aspect` still retains its separate responsibility. Custom stereotypes should only be created when the project has semantics genuinely worth reusing, and are unnecessary for small examples.

## 5. Runnable Java 17+ Example: Comparing the Cases Directly

A plain Spring Framework example using Maven, Spring 6.2.19, and AspectJ Weaver 1.9.25.1. The goal is to observe precisely **which aspect class becomes a bean, whether the service is a proxy, and whether advice runs**.

### 5.1. Project Structure

```text
spring-aspect-component-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── OrderService.java
    ├── AuditAspect.java
    ├── InvisibleAspect.java
    ├── AuditHelper.java
    └── Main.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aspect-component-demo</artifactId>
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

**`OrderService.java`**

```java
package example;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public void submit() {
        System.out.println("service: submit");
    }
}
```

**`AuditAspect.java`: has both annotations**

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
        System.out.println("registered aspect: before");
    }
}
```

**`InvisibleAspect.java`: has only `@Aspect`**

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class InvisibleAspect {
    @Before("execution(* example.OrderService.submit(..))")
    public void beforeSubmit() {
        System.out.println("invisible aspect: before");
    }
}
```

**`AuditHelper.java`: has only `@Component`**

```java
package example;

import org.springframework.stereotype.Component;

@Component
public class AuditHelper {
    public String label() {
        return "helper bean";
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
            System.out.println("AuditAspect beans: "
                + context.getBeanNamesForType(AuditAspect.class).length);
            System.out.println("InvisibleAspect beans: "
                + context.getBeanNamesForType(InvisibleAspect.class).length);
            System.out.println("AuditHelper beans: "
                + context.getBeanNamesForType(AuditHelper.class).length);

            OrderService service = context.getBean(OrderService.class);
            System.out.println("service is AOP proxy: " + AopUtils.isAopProxy(service));
            service.submit();
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

The `System.out.println` lines of the example, in order:

```text
AuditAspect beans: 1
InvisibleAspect beans: 0
AuditHelper beans: 1
service is AOP proxy: true
registered aspect: before
service: submit
```

**Output explanation:**

1. `AuditAspect` has both `@Aspect` and `@Component`. The scanner registers one bean, and then Spring AOP uses the aspect metadata to create advice. When `submit()` is called through the service proxy, `registered aspect: before` appears.
2. `InvisibleAspect` sits right inside package `example` but has no `@Component` or `@Bean` declaration. Therefore `InvisibleAspect beans: 0`; its advice is not registered and `invisible aspect: before` does not appear.
3. `AuditHelper` has `@Component` so there is one bean, but it lacks `@Aspect` and creates no advice.
4. `@EnableAspectJAutoProxy` enables finding aspect beans and creating proxies. `service is AOP proxy: true` proves the target is being intercepted by Spring.

The results are based on **the exact files/configuration** in the example. Adding a bean definition for `InvisibleAspect` or changing scan/configuration will change the output.

## 6. Without `@Component`, an Aspect Can Still Be Registered via `@Bean`

In many projects, you do not want the aspect class to depend on `@Component`, or you need to create the aspect via a factory to inject configuration parameters. `@Bean` is also a way for the Spring container to manage an aspect.

To try a **variant** from the Section 5 example, keep `InvisibleAspect.java` (which has only `@Aspect`). Replace `AppConfig.java` with:

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
    public InvisibleAspect invisibleAspect() {
        return new InvisibleAspect();
    }
}
```

Keep the remaining classes unchanged. Rerunning the Section 5 program will output:

```text
AuditAspect beans: 1
InvisibleAspect beans: 1
AuditHelper beans: 1
service is AOP proxy: true
invisible aspect: before
registered aspect: before
service: submit
```

**Note on advice ordering:** When multiple aspects have the same kind of advice and `@Order` is not configured, **the order of the two advice lines is not guaranteed**. The two lines may swap positions, while the important point is that both appear before `service: submit`. Do not write tests that depend on that arbitrary order.

Reason for the change: `@Bean` registers the `InvisibleAspect` instance as a Spring bean; `@Aspect` on the class is still recognized by Spring AOP. `new InvisibleAspect()` **inside a `@Bean` factory method** differs from arbitrarily creating `new InvisibleAspect()` outside the container: only the instance returned from `@Bean` is a registered bean.

If you only want one aspect, remove or disable `AuditAspect` when switching to `@Bean`. **Do not** duplicatively declare the same aspect via both `@Component` and `@Bean` unintentionally; two instances can produce duplicate advice and cause ambiguity during injection.

## 7. Enabling Spring AOP Is a Separate Step

Registering the aspect bean and enabling the AOP system are two distinct steps.

In plain Spring Framework, you typically use:

```java
@Configuration
@ComponentScan("example")
@EnableAspectJAutoProxy
public class AppConfig {
}
```

- `@ComponentScan` finds classes eligible for bean registration.
- `@EnableAspectJAutoProxy` enables `@AspectJ`-style Spring AOP processing and automatically creates proxies for matching beans.
- AspectJ Weaver must be on the classpath for Spring to parse pointcut expressions.
- `@EnableAspectJAutoProxy` **does not automatically register** classes that only have `@Aspect` outside bean definitions.

With **Spring Boot** applications, when the AOP/AspectJ dependency and corresponding auto-configuration are active, Boot can enable AspectJ auto-proxy support by default without you needing to add `@EnableAspectJAutoProxy`. However, you still need to **register the aspect as a bean**.

Common starter names:

```xml
<!-- Spring Boot 3.x, inside <dependencies>; version comes from the Boot BOM. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

```xml
<!-- Spring Boot 4.x, inside <dependencies>; version comes from the Boot BOM. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aspectj</artifactId>
</dependency>
```

These are two **Boot-version-specific dependency snippets**, not a complete POM, and should not be added simultaneously just to “be safe”. The Boot BOM/parent is responsible for keeping Spring/AspectJ dependencies compatible.

### Package Scanning in Spring Boot

Suppose the main class is placed at `com.acme.app.Application`, while the aspect is placed at `com.acme.infrastructure.AuditAspect`. Default component scan starts from the package containing the main class and its subpackages; `com.acme.infrastructure` **does not belong** to the scope of `com.acme.app`. Even if the class has both `@Aspect @Component`, it still will not become a bean if the right package is not scanned.

Two common solutions are placing the aspect in `com.acme.app.aop` (within the scan scope), or configuring scanning explicitly via `@SpringBootApplication(scanBasePackages = {"com.acme.app", "com.acme.infrastructure"})` when there are package organization reasons. In large applications, `@Import` or `@Bean` can also be used to register the aspect explicitly.

## 8. Other Annotations Do Not Replace `@Aspect`

Further distinguish several annotations you may encounter:

| Annotation | Registers a bean? | Defines the aspect role? | Notes |
| --- | --- | --- | --- |
| `@Aspect` | Does not auto-register via scan | **Yes** | Requires an aspect bean |
| `@Component` | Yes, if scanned | No | Using alongside `@Aspect` is common |
| `@Service` | Yes, if scanned | No | Used for business services; also a component |
| `@Repository` | Yes, if scanned | No | Used for persistence layer, has related exception translation |
| `@Configuration` | Recognized by Spring as a configuration class when validly registered/scanned | No | Used to declare `@Bean`/context configuration |
| `@Bean` | **Yes**, for the return value from a `@Bean` method | No | Can create a bean from a class that already has `@Aspect` |
| `@ComponentScan` | Instructs package scanning to find candidates | No | Does not mean every class on the classpath is registered |
| `@EnableAspectJAutoProxy` | Enables Spring AOP auto-proxy mechanism | Does not turn a class into an aspect bean by itself | Needs aspect bean, matching pointcut, target proxy |

`@Aspect` is **not** a meta-annotated `@Component` annotation: they differ right from their source library and responsibility. Even if a custom annotation is meta-annotated with `@Component`, it only replaces **component registration**, not the `@Aspect` marker.

## 9. An Aspect Bean Is Not the Same as a Target Proxy

Another misconception: after adding `@Component`, many people check whether the **aspect bean** is an AOP proxy. Spring AOP has a specific rule:

- Classes with `@Aspect` are **not auto-proxied by Spring as targets of other aspects**.
- `AopUtils.isAopProxy(context.getBean(AuditAspect.class))` returning `false` is **normal**.
- You must inspect the **target bean** (e.g., `OrderService`) to verify the proxy and observe advice calls.

Diagnostic example in a method that has `ApplicationContext context`:

```java
// Illustrative snippet using the classes declared in the Section 5 example.
Object aspect = context.getBean(AuditAspect.class);
Object service = context.getBean(OrderService.class);

System.out.println(AopUtils.isAopProxy(aspect));  // false: expected
System.out.println(AopUtils.isAopProxy(service)); // true: if pointcut matches
```

Do not conclude `@Aspect` “does not work” just because **the aspect bean itself is not a proxy**.

In addition, if a target is created via `new OrderService()` in normal code, that instance is not automatically proxied even if another Spring-managed `OrderService` already has a proxy. This is a limitation of **proxy-based Spring AOP**, unrelated to whether the aspect has `@Component`.

## 10. Diagnosing When an Aspect Is Not Recognized by Spring

When advice does not run, check each layer in order to avoid fixing the wrong thing:

1. **Is there an aspect bean yet?** Use `context.getBeanNamesForType(AuditAspect.class)`; if the array is empty, check `@Component`/`@Bean`, `@ComponentScan`, package, profile, bean creation conditions, and the right `ApplicationContext`.
2. **Is `@Aspect` marked properly on the class?** Import `org.aspectj.lang.annotation.Aspect`; a component containing a method named `before` is not automatically treated by Spring as advice.
3. **Is AOP support enabled?** Check `@EnableAspectJAutoProxy` in plain Spring Framework, or Spring Boot's auto-configuration/AspectJ dependency.
4. **Is the target a proxied bean?** Retrieve the target through Spring and use `AopUtils.isAopProxy(target)`; do not check the aspect instead of the target.
5. **Does the call actually go through the proxy?** Internal calls `this.method()` inside the target bypass advice applied specifically to the internally called method.
6. **Does the pointcut match properly?** Check method, package, signature, annotation, and method proxyability conditions (e.g., `final` methods cannot be overridden by a CGLIB subclass).
7. **Are there duplicate aspect beans?** If the same aspect class is registered via both `@Component` and `@Bean`, or multiple scan configurations overlap, inspect the bean list and count advice executions.

A concise check with the example context:

```java
String[] names = context.getBeanNamesForType(AuditAspect.class);
System.out.println(java.util.Arrays.toString(names));

OrderService target = context.getBean(OrderService.class);
System.out.println(AopUtils.isAopProxy(target));
```

If `names` is empty, do not just tweak the pointcut expression yet. If the aspect bean and target proxy exist but advice does not appear, then examine the pointcut/call path/processing order.

### Quick Scenario Table

| Declaration | Does component scan find the aspect bean? | Can advice run via Spring AOP? |
| --- | --- | --- |
| Only `@Aspect`, no `@Bean` | **No** | No, because no aspect bean is registered |
| `@Aspect @Component`, inside scanned package | **Yes** | Yes, if AOP is enabled and pointcut/target match |
| `@Aspect @Component`, outside scanned package | **No** unless registered another way | No, unless bean is registered by another means |
| `@Aspect` + `@Bean` returning aspect instance | Component scan not needed | Yes, if AOP is enabled and target matches |
| Only `@Component`, no `@Aspect` | Yes | Does not create `@AspectJ` advice from that class |
| Aspect bean exists but AOP not enabled | Yes | No corresponding Spring `@AspectJ` auto-proxy |
| Aspect bean exists, target created with `new` outside container | Yes | Does not intercept that target with a Spring proxy |

## 11. Self-Check

**Question 1.** Does `@Aspect` make Spring component scan automatically pick up a class?

**Answer:** No. Without `@Component`/an equivalent stereotype or another bean definition, Spring will not automatically register a class as a bean just because of `@Aspect`.

**Question 2.** Why might `@Aspect @Component` still fail to run advice?

**Answer:** The class might lie outside the scan scope, lack AOP support, lack AspectJ on the classpath, have a non-matching pointcut, target might not be proxied, or the call might not go through the proxy. The two annotations only solve the first two steps of aspect metadata and bean registration (when scanning actually occurs).

**Question 3.** Can `@Component` be omitted from an aspect and Spring AOP still be used?

**Answer:** Yes. Keep `@Aspect` and register the aspect with `@Bean` (or a valid bean definition); enable Spring AOP.

**Question 4.** Is `@Service` instead of `@Component` on an aspect class allowed?

**Answer:** To the component scanner, `@Service` is also a Spring stereotype and can register the bean. However, you should choose `@Component` for infrastructure aspects to express responsibility accurately.

**Question 5.** The aspect bean is registered, yet `AopUtils.isAopProxy(aspect)` is `false`. Is that an error?

**Answer:** No. Spring AOP excludes aspect classes from auto-proxying as targets of other aspects. Check the proxy of the **target service** and advice execution.

## 12. Official Documentation

- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html): clearly explains that `@Aspect` is not sufficient for classpath autodetection; requires `@Component` or equivalent bean definition, and notes that aspects are not auto-proxied targets.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): how to enable `@EnableAspectJAutoProxy` and classpath requirements.
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): `@Component`, `@Service`, `@Repository` stereotypes and custom stereotypes.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): Spring Boot auto-configuration for AOP and proxies.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy mechanisms and call limitations.
