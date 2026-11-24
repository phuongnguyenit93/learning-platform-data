# Registering Classes with `@Component` and Specialized Stereotypes in Spring Core Container

## 1. From Java Objects to Spring-Managed Beans

In plain Java, creating an object typically starts with `new`:

```java
GreetingService service = new GreetingService(repository);
```

The programmer must decide when to instantiate, which dependencies to pass, where to keep the instance, and manage its lifecycle manually. The Spring IoC Container shifts the responsibility of creating and wiring many objects to the container through **bean definitions**. One way to register a bean is to declare a `@Bean` method; another is to **mark a class with a stereotype annotation** and have Spring scan the classpath to discover that class.

For example:

```java
import org.springframework.stereotype.Component;

@Component
class TextFormatter {
    String format(String text) {
        return "[" + text + "]";
    }
}
```

When Spring scans the package containing `TextFormatter`, this class can become a bean with the default name `textFormatter`. Another bean can then receive `TextFormatter` via constructor injection. **An annotation on a class does not by itself make the object appear in the container**: there must be a registration mechanism, such as `@ComponentScan` or component scanning configured by Spring Boot.

Naming the roles accurately is very important:

- **Class**: defines the type and behavior in Java source code.
- **Bean definition**: metadata that the container uses to manage a bean (class/factory, scope, name, qualifiers, etc.).
- **Spring bean**: an object created, configured, and managed by the Spring container according to a bean definition.
- **Stereotype annotation**: a marker on a class that identifies its architectural role and, when scanned, registers a bean.

The goal of this lesson is to properly use `@Component` and the specialized stereotypes `@Service`, `@Repository`, `@Controller`, and `@Configuration`; and to understand registration via scanning, bean names, constructor injection, custom stereotypes, and common pitfalls.

## 2. `@Component` and Specialized Stereotypes

From the **bean registration** perspective, `@Component` is the general-purpose stereotype; the specialized stereotypes classify a class's role, yet all of them are recognized by the default component scanner via the `@Component` meta-annotation. Choose an annotation based on **actual responsibility**, because the annotation does not automatically activate layer mechanisms.

| Annotation | Recommended Role | Conditions Not to Assume |
| --- | --- | --- |
| `@Component` | General helper, adapter, formatter, or technical component | Not every Java object needs to be a bean |
| `@Service` | Business use cases and business orchestration | Does not automatically open transactions, caching, retries, or AOP |
| `@Repository` | Repository/DAO, data access | Exception translation requires an appropriate post-processor and translator; `JdbcTemplate` has its own error-translation path |
| `@Controller` | Presentation/web controller | Has no HTTP endpoint without a web stack, handler mapping, and routes |
| `@Configuration` | Java configuration, typically containing `@Bean` methods | Has its own configuration semantics, including the `proxyBeanMethods` option |

A utility bean may need dependency injection or Spring's lifecycle:

```java
import org.springframework.stereotype.Component;

@Component
class SlugGenerator {
    String slug(String text) {
        return text.trim().toLowerCase(java.util.Locale.ROOT)
                .replace(' ', '-');
    }
}
```

`SlugGenerator` is discovered by the scanner when it resides in the right base package. If only a pure function is needed, a plain Java utility outside the container can still be appropriate.

`@Service` expresses business logic and supports constructor injection like any other component:

```java
@Service
class CheckoutService {
    private final PaymentRepository payments;

    CheckoutService(PaymentRepository payments) {
        this.payments = payments;
    }

    String summary() { return payments.status(); }
}
```

This is an illustrative snippet, assuming an interface/class `PaymentRepository` and a corresponding bean exist; with a single constructor, Spring does not require `@Autowired` on the constructor. `@Service` does not automatically establish transactions.

Similarly, `@Repository` can mark a bean to be processed by persistence exception translation infrastructure, but it does not automatically translate every exception. `@Controller` can be scanned into an `ApplicationContext` without an HTTP server; request handling only occurs when the appropriate Spring MVC/WebFlux stack is running. `@RestController` combines `@Controller` and `@ResponseBody` in Spring Web.

`@Configuration(proxyBeanMethods = false)` is suitable when `@Bean` factory methods operate independently. If you want to call another `@Bean` method directly while still preserving the container's singleton semantics, you should consider full configuration. The runnable example in section 5 demonstrates all five stereotypes, injection, bean names, and a custom stereotype within the same context.

## 3. Component Scanning and Registration Mechanism

Component scanning works according to the following flow:

```text
Classpath/packages requested for scanning
               |
               v
Spring reads metadata of candidate classes
               |
               v
Applies default stereotypes and include/exclude filters
               |
               v
Creates and registers bean definitions for valid candidates
               |
               v
When the container needs/initializes a bean:
resolve dependencies -> create instance -> inject -> lifecycle
```

Important: **class scanning and instance creation are two separate phases**. The scanner registers bean definitions; when an instance is created also depends on scope, lazy flags, dependencies, and the context initialization process.

By default, component scan detects classes annotated with `@Component`, `@Service`, `@Repository`, `@Controller`, `@Configuration`, or custom annotations meta-annotated with `@Component`. You can customize candidate filtering with `includeFilters` and `excludeFilters` if needed.

### 3.1. Enabling Scanning with `@ComponentScan`

```java
@Configuration
@ComponentScan(basePackages = "com.example.orders")
class OrderConfiguration {
}
```

This is an illustrative snippet. When registering `OrderConfiguration` with `AnnotationConfigApplicationContext`, Spring scans the `com.example.orders` package and its subpackages for component candidates.

A safer variant when renaming packages:

```java
@Configuration
@ComponentScan(basePackageClasses = OrderApplication.class)
class OrderConfiguration {
}
```

Here `OrderApplication.class` serves only as a **type-safe marker** to identify the package; the marker class itself does not need to carry a stereotype. `OrderApplication` must exist in the package you want to scan.

If `@ComponentScan` does not declare a package, Spring defaults to using the package of the **configuration class declaring the annotation**, along with its subpackages. Placing the configuration class in a narrow or misplaced package will cause components in packages outside that scope to be missed.

### 3.2. Spring Boot and Default Package Scanning

In a typical Spring Boot project:

```java
@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

This is an **illustrative Boot application snippet**, not the plain Spring Context project in section 5. `@SpringBootApplication` provides functionality equivalent to combining `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`. By default, component scanning starts from the package where the application class is located. Therefore, place the application class in the **root package** containing the subpackages to be scanned, for example:

```text
com.example.orders/
├── OrderApplication.java
├── api/OrderController.java
├── service/OrderService.java
└── persistence/OrderRepository.java
```

A class in a sibling package or a parent package **outside** the scan area may not be discovered, even if annotated with `@Service`.

### 3.3. Being a Candidate Does Not Mean Every Class Is Instantiated

- An **interface** annotated with a stereotype has no concrete constructor to instantiate itself; place the stereotype on the **implementation** you want to register. Specialized annotation/repository mechanisms, such as Spring Data repositories, have their own proxy creation process.
- An **abstract** class generally does not become a regular directly instantiable bean solely by having `@Component`. If you need to register a bean, provide a concrete implementation or an appropriate factory.
- A **nested non-static class** carries an implicit outer-instance dependency; do not expect the scanner to register it as an independent component. For nested classes that are scanned, use `static` if truly needed.
- A **conditional bean** (for example, an inactive profile) may be skipped; the mere presence of a class on the classpath is not enough to assert that the bean exists in the container.
- A class with a stereotype that is missing a constructor dependency can still be registered as a bean definition and then fail during instantiation.

## 4. Bean Naming and Usage Scope

### 4.1. Default Component Names

Spring typically uses `AnnotationBeanNameGenerator` for beans discovered via scanning. If no explicit name is given, the default name is derived by uncapitalizing the first character of the **short class name** according to JavaBeans rules:

| Declaration | Typical Bean Name |
| --- | --- |
| `@Component class TextFormatter` | `textFormatter` |
| `@Service class CheckoutService` | `checkoutService` |
| `@Repository class OrderRepositoryImpl` | `orderRepositoryImpl` |
| `@Controller class OrderController` | `orderController` |

There are exceptions for class names starting with multiple uppercase characters (such as `URLService`), so do not assume the default rule is simply always lowercasing the first character.

You can specify a name explicitly:

```java
@Service("checkoutWorkflow")
class CheckoutService {
    // ...
}
```

In that case, the expected bean name is `checkoutWorkflow`, not `checkoutService`. Bean names must be unique within a container; two components using the same name can cause a conflicting registration error. Do not resolve conflicts by silently enabling bean definition overriding without first understanding why two beans share the same name.

### 4.2. Bean Name, Bean Type, and Qualifier

The bean name serves identification within the container; the type serves type-based autowiring. If a constructor requires an interface and two matching implementation beans exist, `@Service`/`@Repository` will not automatically pick the right implementation. You can use `@Qualifier`, `@Primary`, or redesign the dependency.

```java
// Illustrative snippet: both implementations are registered.
@Service("localSender")
class LocalSender implements Sender { }

@Service("remoteSender")
class RemoteSender implements Sender { }

// In the constructor of another bean:
NotificationService(@Qualifier("remoteSender") Sender sender) {
    this.sender = sender;
}
```

This is not a standalone Java snippet: `Sender`, `NotificationService`, and imports must be defined. `@Qualifier("remoteSender")` directs Spring to the candidate with a matching qualifier or bean name; this phrase **is unrelated to whether the two classes share the same stereotype**.

### 4.3. Scope and Lifecycle

Component scanning does not fix the scope to prototype. By default, a Spring bean registered with `@Component`, `@Service`, `@Repository`, or `@Controller` has **container-scoped singleton** scope. This means Spring typically provides the same instance for container lookups:

```java
@Service
@Scope("prototype")
class ReportTask {
    // Each time the container resolves a prototype bean, a new instance is created.
}
```

This is an illustrative snippet; `org.springframework.context.annotation.Scope` must be imported. Use a scope appropriate to the lifecycle rather than choosing prototype just because a method needs to run multiple times. With singleton, Spring can create the instance eagerly during context refresh; `@Lazy` alters the eager/lazy policy where appropriate, though another dependency requiring that bean can still trigger initialization.

A Spring-managed bean can receive dependency injection, post-processors, initialization/destruction callbacks, and proxies as configured. **An object created with `new` does not automatically become the same bean registered by the scanner**, even if its class has `@Component`.

## 5. Runnable Java 17+ Project: Registering Five Types of Stereotypes

The example below uses **Spring Framework 6.2.18**, requiring no Spring Boot or servlet container. All Java files reside in the same package. To keep the example easy to copy, non-`public` classes are placed in the same file as the main class; the Java compiler still generates separate `.class` files, and the component scanner discovers eligible concrete top-level classes.

### 5.1. File Structure

```text
component-stereotypes-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/components/
    └── ComponentStereotypesDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'component-stereotypes-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.components.ComponentStereotypesDemo'
}
```

`spring-context` pulls in the required Spring Beans/Core modules. This example does not use servlets, HTTP, or a database; `@Controller` and `@Repository` here simply demonstrate roles and scanning behavior.

### 5.2. Complete Java Code

`src/main/java/demo/components/ComponentStereotypesDemo.java`:

```java
package demo.components;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Controller;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;

public class ComponentStereotypesDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DemoConfig.class)) {
            System.out.println("component = " +
                    context.containsBean("textDecorator"));
            System.out.println("service = " +
                    context.containsBean("greetingService"));
            System.out.println("repository = " +
                    context.containsBean("inMemoryGreetingRepository"));
            System.out.println("controller = " +
                    context.containsBean("greetingController"));
            System.out.println("configuration = " +
                    context.containsBean("demoConfig"));
            System.out.println("custom = " +
                    context.containsBean("featureInfo"));

            GreetingController controller =
                    context.getBean(GreetingController.class);
            System.out.println("greeting = " + controller.render());

            GreetingService first = context.getBean(GreetingService.class);
            GreetingService second = context.getBean(GreetingService.class);
            System.out.println("sameService = " + (first == second));
        }
    }
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = ComponentStereotypesDemo.class)
class DemoConfig {
}

interface GreetingRepository {
    String load();
}

@Repository
class InMemoryGreetingRepository implements GreetingRepository {

    @Override
    public String load() {
        return "Hello from repository";
    }
}

@Service
class GreetingService {

    private final GreetingRepository repository;

    GreetingService(GreetingRepository repository) {
        this.repository = repository;
    }

    String greeting() {
        return repository.load() + " via service";
    }
}

@Component
class TextDecorator {

    String decorate(String input) {
        return "[" + input + "]";
    }
}

@Controller
class GreetingController {

    private final GreetingService service;
    private final TextDecorator decorator;

    GreetingController(GreetingService service, TextDecorator decorator) {
        this.service = service;
        this.decorator = decorator;
    }

    String render() {
        return decorator.decorate(service.greeting());
    }
}

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
@interface Feature {
    @AliasFor(annotation = Component.class, attribute = "value")
    String value() default "";
}

@Feature("featureInfo")
class FeatureInfo {
}
```

In a single Java file, only `ComponentStereotypesDemo` is top-level `public`; the remaining classes and annotation have package-private visibility, which is valid because they are in the same package and compiled into separate `.class` files. Constructors of scanner-instantiated classes here can be package-private; Spring can access them appropriately in standard classpath applications. When using the Java Platform Module System with `module-info.java`, `opens` configuration for reflection must be considered separately; this example does not use a module descriptor.

### 5.3. Run Command and Output

Use JDK 17 or higher and a compatible Gradle version; in the project directory:

```bash
gradle run --quiet
```

If a Gradle Wrapper is present, use `./gradlew run --quiet` on Linux/macOS or `.\gradlew.bat run --quiet` on Windows PowerShell. Lines printed by the program:

```text
component = true
service = true
repository = true
controller = true
configuration = true
custom = true
greeting = [Hello from repository via service]
sameService = true
```

`System.out.println` only prints the lines above; Spring or Gradle logs, if additional logging is configured in the environment, are not the business output of the program.

### 5.4. Step-by-Step Execution Trace

1. `new AnnotationConfigApplicationContext(DemoConfig.class)` registers the configuration class and refreshes the context.
2. `@ComponentScan(basePackageClasses = ComponentStereotypesDemo.class)` instructs Spring to scan the `demo.components` package.
3. Spring discovers `InMemoryGreetingRepository`, `GreetingService`, `TextDecorator`, `GreetingController`, and `FeatureInfo` via their stereotypes, while `DemoConfig` is registered as a configuration bean.
4. The container selects `InMemoryGreetingRepository` to satisfy the `GreetingRepository` interface because only one implementation is registered here.
5. The container injects `GreetingRepository` into `GreetingService`, and then `GreetingService` and `TextDecorator` into `GreetingController` via constructors. `@Autowired` is not needed because each class has only one constructor.
6. `@Feature("featureInfo")` is scanned because `@Feature` carries the `@Component` meta-annotation. `@AliasFor` maps the `value` of `@Feature` to the logical component name, so the bean is named `featureInfo`.
7. `controller.render()` returns a formatted string. This is a normal Java call to the `@Controller` bean; **there is no HTTP request**.
8. `first == second` returns `true` because `GreetingService` has the default singleton scope within the same context.

Each output line is a narrow check of the declared behavior. If you remove `@ComponentScan` while still registering `DemoConfig`, the scanner is no longer configured to search for stereotypes in the package, and beans like `GreetingService` are not created automatically.

## 6. Custom Stereotypes: Extending `@Component` Properly

Large projects often need custom stereotypes expressing architectural intent, such as `@DomainService`, `@UseCase`, or `@InboundAdapter`. Spring supports this by **meta-annotating a custom annotation with `@Component`**:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface DomainService {
    @AliasFor(annotation = Component.class, attribute = "value")
    String value() default "";
}
```

This snippet illustrates the **contents of `DomainService.java`**, requiring imports as in section 5. The `@DomainService` annotation can be used on a class:

```java
@DomainService("orderUseCase")
public class OrderUseCase {
}
```

The second snippet illustrates **`OrderUseCase.java`** in a scanned package. The bean is named `orderUseCase` via the alias. The rules are:

- `@Target(ElementType.TYPE)` allows attaching the annotation to classes.
- `@Retention(RetentionPolicy.RUNTIME)` ensures the annotation metadata can be read at runtime.
- `@Component` on the custom annotation tells the scanner that this is a stereotype.
- `@AliasFor(annotation = Component.class, attribute = "value")` declares an **explicit alias** for the bean name. Since Spring 6.1, the older convention-based approach where a custom stereotype simply declared `String value()` has been deprecated; using `@AliasFor` makes semantics clearer and more durable.
- If you do not need to specify a bean name from the custom annotation, you can define a simple marker stereotype without a `value` attribute; the scanner still derives the default name from the class.

**Avoid overusing custom stereotypes** if they do not carry clear meaning. Labels that merely duplicate `@Service` under another name without any additional convention can make code harder to understand.

## 7. How Does `@Component` Differ from `@Bean`?

Both can register beans, but the **definition source** differs:

| Criterion | Stereotype + Component Scanning | `@Bean` in Configuration |
| --- | --- | --- |
| Where declared | On a class | On a method of a configuration class or suitable configuration class |
| Typical target | Application classes controlled by the team | Library classes, objects needing factory logic, customizable objects |
| Registration mechanism | Scanner searches for metadata in packages | Configuration processor reads factory method |
| Default bean name | From class name, e.g. `paymentService` | From method name, e.g. `paymentClient` |
| Injection | Yes, managed by Spring container | Yes, managed by Spring container |
| Default scope | Singleton | Singleton |
| Can be combined? | Yes | Yes |

Example with a third-party class whose source cannot be modified:

```java
@Configuration(proxyBeanMethods = false)
class ExternalConfig {
    @Bean
    ExternalClient externalClient() {
        return new ExternalClient("endpoint");
    }
}
```

This is an illustrative snippet, missing the `ExternalClient` definition and imports. `@Bean` is easier to use than trying to add `@Component` to a library class you do not control.

Do not both scan a class with `@Component` **and declare a `@Bean` producing the same instance/class** without clear intent; you may create two beans of the same type and make single-candidate injection ambiguous. A project can combine both registration approaches, provided each bean has an intentional role, scope, and name.

## 8. Scan Scope, Exclusions, and Startup Performance

Component scanning inspects classes on the runtime classpath within the base package and its subpackages. A class annotated with `@Service` in a sibling package or outside the root will not be found by that scan pass. With Spring Boot, `@SpringBootApplication` typically scans from the package of the application class down into its sub-branches.

Use `@ComponentScan(basePackages = "...")` or `basePackageClasses = Marker.class` to define the root, keeping the scope **sufficient but not overly broad**. `includeFilters` adds matching criteria; `excludeFilters` removes candidates from a scan pass; `useDefaultFilters=false` disables the default stereotype detection rules. A bean can also be created via `@Bean`, `@Import`, or other configuration even if it is not scanned. When widening the scan area, verify the classpath, candidates, conditional configurations, and naming conflicts before shipping to production.

## 9. Common Errors

Errors when using stereotypes typically fall into different phases: **registration**, **bean instantiation**, or **infrastructure integration**:

| Symptom | What to Check First |
| --- | --- |
| `@Service` bean is missing even though class exists | Runtime classpath, package root, include/exclude filters, `useDefaultFilters`, profiles/conditions |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type; requires explicit selection via `@Qualifier`, `@Primary`, or collection injection |
| Two components in different packages conflict | Identical default bean names, explicit names, or naming generator |
| `@Repository` does not translate exceptions | Presence of `PersistenceExceptionTranslationPostProcessor`, appropriate translator, and whether calls go through a proxy |
| Controller exists in context but HTTP returns 404 | MVC/web infrastructure, `DispatcherServlet`, mapping, and HTTP path/method |
| `@Service` method does not roll back | `@Transactional`, transaction manager, proxy/call path, and self-invocation |
| Object created with `new` lacks `@Autowired` dependencies | Object did not go through Spring bean registration and lifecycle |
| Bean definition exists but application fails to start | Constructor/dependencies, circular dependencies, factory error, or conditional configuration |

**Debug in order:** (1) verify the package and classpath; (2) check whether the configuration class is registered; (3) inspect annotations/filters/conditions; (4) inspect bean names and types using `containsBean`/`getBeanNamesForType`; (5) find the instantiation root cause; (6) check the relevant web/transaction/persistence infrastructure. Do not widen scanning to the entire classpath just to mask dependency or naming errors.

## 10. Practice Exercises

### Exercise 1 — Renaming a Component

Change:

```java
@Component
class TextDecorator { /* ... */ }
```

to:

```java
@Component("messageDecorator")
class TextDecorator { /* ... */ }
```

In the verification snippet in section 5, replace `containsBean("textDecorator")` with `containsBean("messageDecorator")`. **Type-based** dependency injection can still work if there is only one `TextDecorator` bean; however, the default bean name `textDecorator` is no longer the registered name.

### Exercise 2 — Changing Stereotype by Role

If you change `GreetingService` from `@Service` to `@Component`, will the program in section 5 still run? **Yes**, as long as the component is still scanned and there is no additional configuration relying on the `@Service` annotation. However, the code no longer clearly expresses the business layer, and custom tooling/aspects/filters targeting `@Service` may change behavior.

If you change `InMemoryGreetingRepository` from `@Repository` to `@Component`, the bean can still be scanned, but the repository metadata used for exception translation and architectural convention is lost. This is why you should not mechanically replace every stereotype with `@Component`.

### Exercise 3 — Moving to an Unscanned Package

Move `TextDecorator` to package `demo.util` while keeping `@ComponentScan(basePackageClasses = ComponentStereotypesDemo.class)` in package `demo.components`. What do you predict will happen? Spring will not scan `demo.util`; when creating `GreetingController`, the `TextDecorator` dependency will be missing unless another bean registration configuration exists. The fix is to properly expand the scan scope or move the utility back into a scanned package.

### Exercise 4 — Adding a Second Repository

Declare an additional `@Repository class RemoteGreetingRepository implements GreetingRepository`. If both beans are eligible and there is no primary or qualifier clarifying the choice, the constructor `GreetingService(GreetingRepository repository)` can fail with `NoUniqueBeanDefinitionException` (typically appearing in the context creation error chain). The fix is to apply `@Qualifier` according to role or intentionally choose a primary bean.

### Exercise 5 — Custom Stereotype

Create the `@DomainService` annotation following the example in section 6 and mark a concrete class in a scanned package with `@DomainService("invoiceUseCase")`. Verify the bean name with `containsBean("invoiceUseCase")` and explain why `@AliasFor` matters in Spring Framework 6.1+.

### Exercise 6 — Lifecycle

Call `context.getBean(GreetingService.class)` twice on the same context, then compare with `==`. Why is it `true`? Because `GreetingService` is a singleton by default. If a bean is declared `@Scope("prototype")` and is not held inside another singleton, each resolution of the prototype can create a different instance. Do not assume that merely changing the scope of a dependency will cause all clients already holding a reference to automatically refresh it.

## 11. Checklist Before Adding a Stereotype

- Does the class **need** to be managed by Spring? If yes, does its responsibility belong to `@Component`, `@Service`, `@Repository`, or `@Controller`?
- Is the package within the right `@ComponentScan` scope or Spring Boot's default scan scope?
- Are there multiple implementations of an injected interface? If so, is the selection policy clear?
- Is the bean name meaningful, and is there any risk of colliding with another bean name?
- Is a `@Bean` factory method needed because the class cannot be modified or requires configuration logic?
- Does it depend on web, transaction, exception translation, AOP, or scope mechanisms that a stereotype **alone does not activate**?
- If using a custom stereotype, has it been meta-annotated with `@Component` and given a bean name alias with `@AliasFor` when needed?

## 12. Key Takeaways

`@Component` and the specialized stereotypes help Spring **discover classes and register bean definitions via component scanning**. `@Service` expresses business logic, `@Repository` expresses data access, `@Controller` expresses the web layer, and `@Configuration` is a component with configuration semantics. Custom stereotypes can be created via the `@Component` meta-annotation; when specifying a bean name through a custom attribute, use an explicit `@AliasFor`. Regardless of which stereotype is used, a bean is only present when **scanned or registered through an appropriate mechanism**; role annotations do not automatically enable a web server, transactions, or exception translation.

### Official Documentation

- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html).
- [Spring Framework — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html).
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html).
- [Spring Framework — DAO Support and `@Repository`](https://docs.spring.io/spring-framework/reference/data-access/dao.html).
- [Spring Framework — Exception Translation](https://docs.spring.io/spring-framework/reference/data-access/orm/general.html).
