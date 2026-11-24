# @Configuration, @Bean, and @Import in Java-Based Configuration

## 1. The problem: who creates and wires objects in an application?

In plain Java, business code can call `new` directly and pass objects around. In a Spring application, the standard approach is to declare which objects are managed by the **Spring container** and let the container create, wire, and track their lifecycles. A managed object is called a **bean**; the place that holds and provides beans is typically accessed through `ApplicationContext`.

**Java-based configuration** is the way to describe registering those beans using Java classes and methods. Three foundational annotations serve distinct roles:

- `@Configuration`: marks **a class as a source of Spring configuration declarations**.
- `@Bean`: marks **a method that creates or provides an object for the container to register as a bean**.
- `@Import`: **brings additional configuration classes or other components into the processed configuration set**, even if they lie outside the component scan scope.

Visualizing the three layers of responsibility:

~~~text
Java configuration fed into ApplicationContext
    |
    +-- @Configuration: this is a configuration source class
    |       |
    |       +-- @Bean: registers how to create BeanDefinition for object A
    |       +-- @Bean: registers how to create BeanDefinition for object B
    |                       ^
    |                       | Spring resolves dependencies via injection
    |
    +-- @Import(OtherConfiguration.class)
            |
            +-- @Bean: adds definition for object C

BeanDefinition registered
    -> Spring creates instances by demand/scope/lifecycle
    -> beans can be looked up/injected from ApplicationContext
~~~

Do not conflate a **configuration class**, a **bean definition** (`BeanDefinition`), and a **bean instance**. Spring may know how to create a bean very early, yet a lazy singleton or prototype bean might not be created right away. Nor is every Java object a bean: objects created via `new` outside the container's lifecycle are not automatically managed.

### Where the three annotations fit in Spring Boot

`@SpringBootApplication` includes `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`. `@SpringBootConfiguration` is a form of Spring configuration; `@EnableAutoConfiguration` uses a configuration-import mechanism to select appropriate auto-configurations. Understanding `@Configuration`, `@Bean`, and `@Import` is therefore a prerequisite before examining why an auto-configuration may or may not create a bean.

However, **a regular `@Configuration` does not automatically become an auto-configuration**. In Spring Boot 3.x, library auto-configurations must be declared via `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, typically accompanied by `@Conditional...` conditions. `@Import(MyConfig.class)` is an **explicit** import; the auto-configuration selection mechanism based on a candidate list and conditions is a broader step.

## 2. `@Configuration`: declaring a source of bean definitions

A class annotated with `@Configuration` tells Spring that this class can declare beans and import further configuration. Simple example:

~~~java
package example.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {
    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

When `TimeConfiguration` is fed into `ApplicationContext`, the `applicationClock()` method is parsed to register a bean of type `Clock`, named `applicationClock` by default. Simply defining the `TimeConfiguration` class in the project **is not enough**: it must be processed via component scan, `@Import`, direct registration with the context, or another configuration-import mechanism.

### Getting a `@Configuration` class into the application

Common paths:

1. **Component scan:** place the class in a package scanned by `@ComponentScan`; `@Configuration` carries `@Component` semantics.
2. **Explicit import:** use `@Import(TimeConfiguration.class)` on an already-processed configuration.
3. **Direct registration:** use `AnnotationConfigApplicationContext.register(TimeConfiguration.class)` in a plain Spring Framework application.
4. **Spring Boot auto-configuration:** qualifying classes are loaded via the auto-configuration candidate mechanism; this is a separate, conditional and selective process.

For example, if `DemoApplication` is placed in package `example.app` and `TimeConfiguration` in `example.config`, default component scanning from `example.app` will not automatically scan a sibling package. `@Import` is an intentional, explicit import in source code.

### Is `@Configuration` a bean or just a declaration?

The configuration class itself is normally also registered and instantiated by the container to serve its factory methods, but that does not turn **every method** on it into a bean. Only methods matching the relevant processing mechanism (such as `@Bean`) contribute bean definitions. `@Configuration` does not mean every class in the same package gets created.

## 3. `@Bean`: declaring how to create and manage a bean

The `@Bean` annotation is placed on a factory method. Spring processes that declaration into a `BeanDefinition` and invokes the method when the object needs to be created.

~~~java
@Configuration
public class ClientConfiguration {
    @Bean
    ApiClient apiClient() {
        return new ApiClient("https://example.org");
    }
}
~~~

*This is an illustrative snippet; `ApiClient` is a hypothetical type with no definition in the example.* In a complete program, the container can supply the `ApiClient` bean elsewhere via constructor injection.

### Name, type, and dependencies

- **Name:** defaults to the method name, e.g. `apiClient`; you can specify `@Bean("primaryClient")` or names/aliases per annotation syntax.
- **Type:** based on the declared return type and actual object; when conditions need to identify the type, declare a return type carrying useful type information rather than an overly generic type like `Object`.
- **Parameters:** Spring resolves `@Bean` method parameters through dependency injection. When you need `Clock`, declare `myService(Clock clock)` rather than calling `clock()` directly.
- **Scope:** defaults to singleton scope within a container; can be changed with `@Scope`. `@Lazy` affects instantiation timing.
- **Lifecycle:** the object can participate in initialization/destruction via Spring callbacks; for instance `@Bean(initMethod = "start", destroyMethod = "close")` if the object's type has those methods.

Bean method parameters are **dependencies** resolved via autowiring rules, not necessarily values obtained from another method in the same class:

~~~java
@Configuration(proxyBeanMethods = false)
class ReportConfiguration {
    @Bean
    ReportRepository reportRepository() {
        return new ReportRepository();
    }

    @Bean
    ReportService reportService(ReportRepository repository) {
        return new ReportService(repository);
    }
}
~~~

*Illustrative snippet: assumes two classes `ReportRepository` and `ReportService` already exist with matching constructors.* Spring retrieves the `ReportRepository` bean to pass into `reportService`. This style makes dependency relationships explicit and remains valid even when `@Configuration` proxying is disabled.

### When there are multiple beans of the same type

If the container holds two `PaymentGateway` beans, a single-value injection by type `PaymentGateway` can be ambiguous. Where appropriate, use `@Qualifier` to pick a specific name/qualifier, `@Primary` to set a default preference, or inject a list/map of beans. **`@Bean("someName")` does not mean this bean will always be chosen when injecting by type**.

Do not confuse **duplicate bean names** with **multiple beans of the same type**: those are two different situations. Spring Boot disables accidental overriding of same-named definitions by default, whereas multiple beans of the same type can be completely valid as long as injection is properly disambiguated.

## 4. Two modes of `@Configuration`: `proxyBeanMethods`

This is the most commonly misunderstood aspect when learning Java-based configuration.

### Default mode: `@Configuration(proxyBeanMethods = true)`

By default, Spring enhances the configuration class with a runtime-generated subclass to intercept calls to `@Bean` methods in a way that honors bean lifecycle semantics. For a singleton bean, direct calls between bean methods on the **Spring-managed configuration instance** can return the exact singleton object from the container instead of creating a new object each time.

~~~java
@Configuration // proxyBeanMethods defaults to true
class FullConfiguration {
    @Bean
    Store store() {
        return new Store();
    }

    @Bean
    Checkout checkout() {
        return new Checkout(store());
    }
}
~~~

*Illustrative snippet: `Store` and `Checkout` are hypothetical types, and `Checkout` accepts `Store` via its constructor.* When Spring invokes `checkout()`, the `store()` call inside the enhanced class respects bean management. This mechanism is called **inter-bean method reference**.

Requirements: the class and methods must be compatible with subclassing/proxying; you cannot declare the class `final` or the `@Bean` method `final`/`private` when relying on this kind of interception. This is a configuration proxy, distinct from an AOP proxy for `@Transactional`.

### Non-intercepting mode: `proxyBeanMethods = false`

~~~java
@Configuration(proxyBeanMethods = false)
class LiteConfiguration {
    @Bean
    Store store() {
        return new Store();
    }

    @Bean
    Checkout checkout() {
        return new Checkout(store()); // Direct Java call.
    }
}
~~~

If the hypothetical classes are ordinary classes, `store()` on the second line is a plain Java call and creates **a new Store**, not a guaranteed lookup of the registered `store` bean. The container still registers a singleton bean named `store` from its own factory method; however, the `Store` object created by the direct call inside `checkout()` can be a separate object that is not managed as that singleton bean. This can cause two unintended instances.

The safe pattern with `proxyBeanMethods = false`:

~~~java
@Configuration(proxyBeanMethods = false)
class LiteConfiguration {
    @Bean
    Store store() {
        return new Store();
    }

    @Bean
    Checkout checkout(Store store) {
        return new Checkout(store);
    }
}
~~~

Spring passes the managed `Store` bean into the `checkout` method. This is also the preferred style when writing auto-configurations or independent factory configurations, because it makes dependencies explicit and avoids needing inter-method interception.

| Aspect | `proxyBeanMethods=true` | `proxyBeanMethods=false` |
| --- | --- | --- |
| Calling `anotherBeanMethod()` inside the configuration class | Intercepted by Spring to respect scope and context beans | Regular Java method call |
| `final` class/method | Restricted by subclassing/interception requirements | No subclassing needed to intercept bean methods |
| Recommended way to declare dependencies | Method parameters are still clear and testable | Method parameters are the safe, recommended approach |
| Purpose | When inter-bean direct call semantics are needed | Independent factory methods, reducing proxy overhead |

**Distinction:** `@Bean` inside a regular `@Component` class is also processed in *lite* mode; do not expect direct calls to bean methods there to be intercepted by Spring the way `@Configuration(proxyBeanMethods=true)` does.

## 5. `@Import`: composing Java configuration parts

`@Import` can be placed on a configuration class or on a custom annotation. It brings the specified classes into configuration processing. The most basic case:

~~~java
@Configuration(proxyBeanMethods = false)
@Import({DataConfiguration.class, ServiceConfiguration.class})
class ApplicationConfiguration {
}
~~~

Spring processes `DataConfiguration` and `ServiceConfiguration` along with their bean declarations, even though those classes may lie outside component scan scope.

`@Import` does not duplicate beans merely because you declare the same class in two places. What matters is **which classes are registered** and **which bean definitions are created**; do not try to import multiple times as a strategy for creating multiple instances.

### What can be imported?

- **`@Configuration` classes:** the primary case, bringing in `@Bean` methods and further imports.
- **Regular component classes:** classes Spring can register as configuration/bean components as appropriate, without necessarily being marked `@Configuration`.
- **`ImportSelector`:** logic that chooses a list of class names to import based on annotation metadata.
- **`ImportBeanDefinitionRegistrar`:** logic that registers `BeanDefinition`s programmatically when `@Bean` syntax or plain class importing is insufficient.

The last two SPIs are advanced extension points. At the foundational level, understanding `@Import(SomeConfiguration.class)` is enough; there is no need to write an `ImportSelector` for every feature.

### `@Import` vs. commonly confused forms of "import"

| Mechanism | What it brings in | Key difference |
| --- | --- | --- |
| Java `import java.time.Clock;` | Type name into compilation scope | Does **not** register a bean |
| `@ComponentScan` | Components found by package/filter | Scans by scope rules |
| `@Import(X.class)` | Specified configuration class, component, or import SPI | Explicit by class |
| `@ImportResource("classpath:...")` | Bean definitions from configuration resources such as XML | Intended for resource-based configuration |
| Spring Boot `spring.config.import` | External property/configuration files (`.properties`, `.yml`, ...) | Belongs to the **configuration data** loading path, not importing Java `@Configuration` |
| Spring Boot `AutoConfiguration.imports` | List of **candidate** auto-configuration classes in a JAR | Boot selects and evaluates conditions before contributing beans |

### Conditional imports

`@Conditional` can be placed on a configuration class or on `@Bean` methods inside an imported class. Importing only makes that class **considered**, not guaranteed to pass all conditions. For example, in Spring Boot, auto-configuration commonly combines `@ConditionalOnClass`, `@ConditionalOnProperty`, and `@ConditionalOnMissingBean` to decide which beans actually get registered.

For libraries, do not replace the `AutoConfiguration.imports` mechanism with manual `@Import` calls from the application and call that "auto-configuration". If users have to import the class explicitly, that is explicitly imported configuration. You can use `@Import` **inside** an auto-configuration to split sub-configurations by feature.

## 6. Complete example: configuration outside component scan, imported via `@Import`

This example uses **Java 17+**, **Spring Boot 3.3.13**, and **Maven 3.9+**. It demonstrates all three annotations in a runnable application while clarifying:

1. Configuration in an unscanned package participates only because of `@Import`.
2. `@Bean` registers `Clock` and `GreetingService`.
3. Spring uses the `@Bean` parameter to inject the right `Clock` object.
4. `proxyBeanMethods=false` is safe because factory methods do not call one another directly.

### File structure

~~~text
java-config-demo/
├── pom.xml
└── src/main/java/
    └── lesson/
        ├── app/
        │   └── DemoApplication.java
        ├── config/
        │   ├── CoreConfiguration.java
        │   └── FeatureConfiguration.java
        └── domain/
            └── GreetingService.java
~~~

#### `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>lesson</groupId>
    <artifactId>java-config-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter` is sufficient for a console example using `ApplicationContext`. No web server is needed.

#### `src/main/java/lesson/domain/GreetingService.java`

~~~java
package lesson.domain;

import java.time.Clock;
import java.time.LocalDate;

public final class GreetingService {
    private final Clock clock;

    public GreetingService(Clock clock) {
        this.clock = clock;
    }

    public String greet(String name) {
        return "Hello " + name + " on " + LocalDate.now(clock);
    }
}
~~~

`GreetingService` is a plain Java class without `@Component`. It only becomes a bean when registered by a configuration.

#### `src/main/java/lesson/config/CoreConfiguration.java`

~~~java
package lesson.config;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CoreConfiguration {
    @Bean
    public Clock appClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
~~~

`Clock.fixed` keeps the execution date deterministic, so the result can be predicted accurately on any machine at any time. The bean named `appClock` has type `Clock`.

#### `src/main/java/lesson/config/FeatureConfiguration.java`

~~~java
package lesson.config;

import java.time.Clock;
import lesson.domain.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@Import(CoreConfiguration.class)
public class FeatureConfiguration {
    @Bean("greetingService")
    public GreetingService greetingService(Clock appClock) {
        return new GreetingService(appClock);
    }
}
~~~

`@Import(CoreConfiguration.class)` adds the configuration providing `Clock`. The `Clock appClock` parameter is injected by Spring by type. There is no manual `new CoreConfiguration()` or `appClock()` call, so it does not depend on method-call interception.

#### `src/main/java/lesson/app/DemoApplication.java`

~~~java
package lesson.app;

import java.util.Arrays;
import lesson.config.FeatureConfiguration;
import lesson.domain.GreetingService;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Import;

@SpringBootApplication(scanBasePackages = "lesson.app")
@Import(FeatureConfiguration.class)
public class DemoApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {
            GreetingService greeting = context.getBean(
                "greetingService", GreetingService.class
            );
            String[] names = context.getBeanNamesForType(
                GreetingService.class
            );
            Arrays.sort(names);

            System.out.println("names=" + Arrays.toString(names));
            System.out.println(greeting.greet("Lan"));
            System.out.println("clock=" + context.containsBean("appClock"));
        }
    }
}
~~~

Scanning only `lesson.app` is intentional: `lesson.config` is a sibling package and is **not** automatically scanned. Thanks to `@Import(FeatureConfiguration.class)`, the application imports `FeatureConfiguration`; that class in turn imports `CoreConfiguration`. Each configuration then contributes its respective `@Bean`s.

### Running the application

Place the five files at the exact paths above, navigate to the directory containing `pom.xml`, and run:

~~~bash
java -version
mvn -version
mvn -q spring-boot:run
~~~

The lines printed by the program's `System.out.println` statements, in exact order, are:

~~~text
names=[greetingService]
Hello Lan on 2026-01-01
clock=true
~~~

Spring Boot logs, if any, appear additionally depending on the environment. This example does not depend on the system clock because `Clock` is a fixed clock.

### Tracing bean creation

~~~text
DemoApplication
  @SpringBootApplication(scanBasePackages="lesson.app")
  @Import(FeatureConfiguration.class)
          |
          v
FeatureConfiguration (@Configuration)
  @Import(CoreConfiguration.class)
  @Bean greetingService(Clock appClock)
          |                     ^
          v                     |
CoreConfiguration (@Configuration)
  @Bean appClock(): Clock ------+
          |
          v
Spring registers BeanDefinitions for appClock and greetingService
          |
          v
Create Clock -> pass into greetingService(...) factory method
          |
          v
ApplicationContext holds beans "appClock" and "greetingService"
~~~

The order above describes **logical dependencies**, not an assertion that Spring always executes every step in strict line-by-line order across all scopes. Definitions can be registered before instances are created.

## 7. Three experiments to clarify each annotation's role

### Experiment 1: remove `@Import` from `DemoApplication`

Remove just the `@Import(FeatureConfiguration.class)` line while keeping `scanBasePackages = "lesson.app"`. Because the two configuration classes sit in `lesson.config`, they no longer have a loading path via component scanning in this program.

When execution reaches `context.getBean("greetingService", GreetingService.class)`, it throws `NoSuchBeanDefinitionException`. Since the application does not catch that exception, none of the three success output lines above appear. Conclusion: merely having a Java file containing `@Configuration`/`@Bean` does not guarantee the container receives the bean definition.

### Experiment 2: keep the outer import, remove the inner import

Keep `@Import(FeatureConfiguration.class)`, but remove `@Import(CoreConfiguration.class)` from `FeatureConfiguration`. The `greetingService` bean still has its factory method definition, yet there is no longer a `Clock` bean provided by `CoreConfiguration`. When Spring creates the `GreetingService` singleton, resolving the `Clock` parameter fails; the application fails to complete normal startup, typically with an `UnsatisfiedDependencyException` chain leading to `NoSuchBeanDefinitionException`. Exact message details may vary by version/environment.

Conclusion: a `@Bean` with parameters expresses a dependency requirement that the container must satisfy. Having a bean definition for the service does not guarantee all dependencies needed to instantiate it exist.

### Experiment 3: add an optional `Clock` in the app

In a processed configuration class, suppose you declare another `Clock` bean. When `greetingService(Clock appClock)` needs injection by type, it can become ambiguous if multiple `Clock` beans exist with no disambiguation. Fix it using `@Qualifier("appClock")` on the parameter or design an appropriate `@Primary` bean; do not rely on method declaration order for arbitrary selection.

Example changing the signature and adding an import (this is only a replacement snippet for the complete code):

~~~java
import org.springframework.beans.factory.annotation.Qualifier;

@Bean("greetingService")
public GreetingService greetingService(@Qualifier("appClock") Clock clock) {
    return new GreetingService(clock);
}
~~~

Note: this is a **replacement snippet** inside `FeatureConfiguration` after adding the corresponding import, not a standalone Java class. To verify the multi-bean case, you must actually declare a second `Clock` bean in a loaded configuration.

## 8. How do `@Configuration`, `@Bean`, and `@Import` participate in auto-configuration?

The pieces you just learned connect directly to Spring Boot's mechanism:

~~~text
@SpringBootApplication
   |
   +-- @SpringBootConfiguration -> root configuration source of the application
   |
   +-- @ComponentScan -> finds application components/configs
   |
   +-- @EnableAutoConfiguration
          |
          +-- selector mechanism (DeferredImportSelector)
               |
               +-- reads AutoConfiguration.imports list
               +-- filters exclusions and conditions
               +-- imports qualifying auto-configurations
                    |
                    +-- @AutoConfiguration (a specialized @Configuration)
                         |
                         +-- @Import(...) if splitting sub-configurations
                         +-- @Bean ... @Conditional... -> bean definitions
~~~

The key point is that **importing configuration** and **satisfying conditions** are two distinguishable steps:

- `@Import(FooConfiguration.class)` written by the application author expresses an explicit choice: include `FooConfiguration` in the set to be processed.
- `@EnableAutoConfiguration` in Boot relies on a configuration import selector, reads candidates from `AutoConfiguration.imports`, and then evaluates appropriate exclusions/conditions.
- An `@AutoConfiguration` class uses the familiar `@Configuration`/`@Bean` mechanisms to declare beans; it adds `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, and so on so default beans back off or activate only when the environment qualifies.
- `@Import` on an auto-configuration class can import auxiliary `@Configuration` classes. Conditions placed on imported classes/beans are still evaluated according to their own rules.

Illustrative example of a library auto-configuration:

~~~java
@AutoConfiguration
@ConditionalOnClass(RemoteClient.class)
public class RemoteClientAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(RemoteClient.class)
    RemoteClient remoteClient() {
        return new RemoteClient();
    }
}
~~~

This is an **illustrative snippet**, assuming a `RemoteClient` type and appropriate dependencies exist. To become an auto-configuration discovered automatically in Boot 3.x, the fully qualified class name must also be declared in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. If the application already declares a matching `RemoteClient` bean, the default method typically backs off due to `@ConditionalOnMissingBean`. Do not sprinkle `@ConditionalOnMissingBean` indiscriminately across regular configuration classes: condition results depend on which bean definitions have already been processed at evaluation time; Spring Boot documentation recommends placing `OnBean`/`OnMissingBean` conditions in auto-configuration to align with loading order.

### When to use which approach?

| Need | Choice |
| --- | --- |
| Registering application-owned services/infrastructure | `@Configuration` and `@Bean` |
| Splitting large configuration into clear parts | `@Import(PartConfiguration.class)` |
| Having Spring discover components in a package | `@ComponentScan` or default scanning from `@SpringBootApplication` |
| Providing default configuration for a reusable library across Boot apps | `@AutoConfiguration` + `AutoConfiguration.imports` file + appropriate conditions |
| Loading external property files | `spring.config.import`, not `@Import` |

## 9. Common mistakes and how to trace the cause

| Symptom / misconception | Possible cause and how to check |
| --- | --- |
| Created a `@Configuration` class yet no bean exists | The class was not scanned/imported/registered. Check the main class package and component scan scope. |
| `@Bean` exists yet bean is missing when injected | Configuration was not processed, condition failed, or bean could not be created due to missing dependencies. |
| Calling `new SomeConfiguration().bean()` | This is an out-of-container call; it does not represent how Spring manages beans/lifecycles. |
| Disabling `proxyBeanMethods` yet calling `otherBean()` directly | May create a new plain Java object rather than the managed bean; use factory method parameters instead. |
| Creating two beans of the same type and injection fails | Use `@Qualifier`/`@Primary` or refine the dependency signature to reflect actual intent. |
| Seeing `@Import` and thinking it scans the whole package | `@Import` imports the exact specified class/SPI; `@ComponentScan` scans qualifying classes in packages. |
| Thinking Java `import` creates beans | Java `import` only brings type names into scope for source compilation. |
| Thinking `spring.config.import` loads Java config | That property loads configuration data, not a replacement for `@Import`. |
| Putting `@AutoConfiguration` inside a scanned package expecting auto-config behavior | Auto-configurations should be loaded via `AutoConfiguration.imports`, outside component scan. |
| Guessing bean order from method/import declaration order | Definition registration rules and **instantiation** order depend on dependency relationships, scope, and lifecycle. |

### Evidence-based diagnostic process

1. Locate the bean under investigation and confirm its expected **name and type**.
2. Locate the `@Bean` method or component providing that bean.
3. Verify whether the owning class is actually loaded via scan, `@Import`, or auto-configuration.
4. If the bean has factory parameters, verify that the container provides those dependencies.
5. If auto-configuration is involved, inspect conditions and match/mismatch reasons via `--debug` or Spring Boot's condition report.
6. Confirm actual state using `ApplicationContext#getBeanNamesForType`, `containsBean`, and when needed `BeanDefinition` query APIs.

Do not infer from "the Java file exists" that a bean was created; nor treat a missing-bean exception at one injection point as sufficient proof that the bug lies in the mentioned `@Bean`.

## 10. Practice and self-check questions

1. Why might `TimeConfiguration` in `example.config` fail to take effect when the main class is in `example.app`? Name two ways to register it intentionally.
2. Distinguish three outcomes: a class is brought into configuration, a `BeanDefinition` is registered, a singleton instance is instantiated.
3. Explain the difference between `@Import(FeatureConfiguration.class)` and `@ComponentScan("lesson.config")` in the example.
4. Explain why calling `store()` inside `checkout()` differs between `proxyBeanMethods=true` and `false`. Rewrite the method using bean parameters.
5. Remove each `@Import` annotation per the two experiments in section 7. Predict the error and confirm via logs; distinguish **no BeanDefinition** from **definition exists but missing dependency at instantiation**.
6. Why is adding `@AutoConfiguration` to a library class still not enough for Spring Boot 3.x to discover it automatically? State the exact registration file name.
7. When two `Clock` beans exist, what does using `@Qualifier` mean compared to using `@Primary`? When should each be applied?

**Self-assessment:** you should be able to pinpoint where configuration is discovered, where bean definitions appear, how Spring resolves factory method parameters, and what separates explicitly imported configuration from conditional auto-configuration.

## 11. Takeaways for subsequent topics

**`@Configuration` declares a configuration source; `@Bean` declares a bean; `@Import` connects configuration sources.** All three participate in building the `ApplicationContext`; Spring Boot auto-configuration uses this very foundation to selectively import default configurations according to classpath, properties, conditions, and application-supplied beans.

For new configurations, the most testable style is to split by responsibility, import explicitly when needed, declare dependencies via `@Bean` parameters, choose `proxyBeanMethods=false` when inter-bean method calls are unnecessary, and verify actual beans in the context rather than guessing from annotations.

**Official documentation:**
- [Spring Framework — Using `@Configuration`](https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html)
- [Spring Framework — `@Bean` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Bean.html)
- [Spring Framework — `@Import` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Import.html)
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
