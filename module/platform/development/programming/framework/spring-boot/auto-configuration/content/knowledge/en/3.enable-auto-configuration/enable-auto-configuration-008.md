# From SpringApplication.run to Configuration Class Processing and Bean Definition Registration

## 1. Objectives and Big Picture

When running a Spring Boot application:

```java
@SpringBootApplication
public class MyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
```

Spring does not immediately invoke constructors for all `@Component` classes. First, Boot prepares the environment and `ApplicationContext`, and then Spring Framework **parses configuration sources**, registers **`BeanDefinition`s**, resolves dependencies, and creates the required beans. This initialization pipeline explains how Spring Boot combines application-authored configuration, component scanning, and auto-configuration.

The lesson follows this path:

```text
main()
  -> SpringApplication.run(...)
  -> prepare Environment, ApplicationContext, and sources
  -> refresh() context
       -> read @Configuration / @ComponentScan / @Import / @Bean
       -> evaluate auto-configuration and @Conditional
       -> register BeanDefinitions into the registry
       -> register BeanPostProcessors
       -> create non-lazy singletons and process lifecycle
  -> context refreshed successfully
  -> invoke ApplicationRunner / CommandLineRunner
  -> report application ready
```

This is a **conceptual diagram**, not a trace of every internal call. Certain infrastructure beans are created early to participate in parsing configurations; not every bean waits for the same step. Subsequent sections clarify where decisions about **bean definitions** occur versus where **bean instances** are actually created.

Expected outcomes after this lesson:

- Distinguish the responsibilities of `SpringApplication`, `ApplicationContext`, `BeanFactory`, and `BeanDefinitionRegistry`.
- Describe how Spring processes `@SpringBootApplication`, `@Configuration`, `@ComponentScan`, `@Import`, and `@Bean`.
- Understand how auto-configurations are selected from metadata, evaluated against conditions, and contribute bean definitions.
- Read logs/stack traces at the right phase: missing bean definition, condition mismatch, bean creation error, or runner failure.
- Observe firsthand a bean that **has a definition yet no instance** using a Java 17 + Spring Boot example.

## 2. Which Object Does What?

| Component | Responsibility | Key Point to Remember |
| --- | --- | --- |
| `SpringApplication` (Boot) | Coordinates startup, prepares environment/context, loads configuration sources, invokes runners, and emits lifecycle events | Does not replace Spring Framework's IoC container |
| `Environment` | Aggregates property sources, profiles, and configuration values | Can affect `@Profile`, `@ConditionalOnProperty`, and binding |
| `ApplicationContext` | Application-level container: provides beans, events, resources, lifecycle, environment | `refresh()` is the key milestone turning configuration into an active context |
| `BeanDefinitionRegistry` | Stores/registers/looks up bean definitions | A definition does not equate to an instantiated bean |
| `BeanFactory` | Creates/retrieves beans, DI, scopes, initialization, and destruction | `getBean()` sometimes triggers bean creation |
| `BeanDefinition` | Metadata describing how to create a bean, e.g., class, factory method, scope, lazy flag | Configuration of the bean, not the bean itself |
| `BeanFactoryPostProcessor` | Modifies metadata before most ordinary beans are instantiated | Should not call `getBean()` arbitrarily inside this processor |
| `BeanPostProcessor` | Intervenes on instances before/after initialization; can create proxies | Operates in a different phase from definition processing |

An implementation such as `DefaultListableBeanFactory` can implement multiple interfaces simultaneously, including both factory and registry. Separating responsibilities conceptually does not mean each role must be a separate physical object.

**Two independent states of a bean:**

```text
Has BeanDefinition?        Yes
Created singleton instance? Maybe not yet
```

A `@Lazy` singleton illustrates this clearly: metadata is already registered during configuration processing, yet the instance may appear only when requested. Conversely, an auto-configuration whose condition fails may **not register a definition** at all; that is not a lazy initialization issue.

## 3. From main() into SpringApplication.run(...)

`SpringApplication.run(MyApplication.class, args)` is a convenience call that creates a `SpringApplication` and launches it. `MyApplication.class` is the **primary source**: Boot uses it as the initial configuration source. Additional sources can be added through appropriate `SpringApplication` APIs or configuration mechanisms.

### 3.1. Preparing the Environment

Boot orchestrates preparing the `Environment` from multiple sources such as command-line arguments, system properties, environment variables, and application configuration files. Property precedence rules decide the effective values. This environment affects profile selection and configuration conditions, so two startups with the exact same classes can produce different sets of bean definitions.

Example:

```bash
java -jar app.jar --spring.profiles.active=dev
```

This command illustrates Spring Boot property syntax; `app.jar` is an example name, not the artifact built in the hands-on section. When the `dev` profile is active, configurations with `@Profile("dev")` can be evaluated, while configurations meant only for `prod` are skipped.

`Environment` does not automatically turn every property into a bean. A property can drive a condition, be bound into `@ConfigurationProperties`, or be read via API; the result depends on the specific mechanism.

### 3.2. Selecting the ApplicationContext Type

Boot infers the application type from the classpath and configuration (such as `spring.main.web-application-type`), then creates the matching context. For example:

- **Non-web** applications may use `AnnotationConfigApplicationContext`.
- **Servlet web** applications typically use `AnnotationConfigServletWebServerApplicationContext`.
- **Reactive web** applications typically use `AnnotationConfigReactiveWebServerApplicationContext`.

These names describe common implementations in Spring Boot 3.x, not a guarantee of a single class under every custom setup. Context selection affects the infrastructure created and which `@ConditionalOnWebApplication` conditions can match.

### 3.3. Preparing and Loading Configuration Sources

Boot prepares the context, attaches the environment, applies relevant initializers, and loads primary sources. That does not mean all application beans are created right at this step. The root class is typically added to the registry as a definition so configuration processors can inspect it deeply during `refresh()`.

Observe the distinction:

```text
Knowing the root configuration class
  != having parsed all imports and @Beans
  != having created every instance
```

`SpringApplication.run()` ultimately returns a `ConfigurableApplicationContext` **if startup succeeds**; if a fatal error occurs during `refresh()`, Boot handles startup failure and throws the appropriate exception.

## 4. Why Is ApplicationContext.refresh() the Decisive Step?

In `AbstractApplicationContext`, `refresh()` coordinates multiple steps to turn initial definitions into a usable container. You can picture the major sequence as:

```text
refresh()
  prepareRefresh()
  obtainFreshBeanFactory()
  prepareBeanFactory(beanFactory)
  postProcessBeanFactory(beanFactory)
  invokeBeanFactoryPostProcessors(beanFactory)
  registerBeanPostProcessors(beanFactory)
  initMessageSource()
  initApplicationEventMulticaster()
  onRefresh()
  registerListeners()
  finishBeanFactoryInitialization(beanFactory)
  finishRefresh()
```

These are Framework-level phase names (with implementation details simplified). Several steps invoke extension points that can register additional bean definitions; specific context types (especially web) perform additional work as well.

Two phases are particularly important for this lesson:

- **`invokeBeanFactoryPostProcessors(...)`**: factory/registry post-processors participate in finalizing metadata. Among them, `ConfigurationClassPostProcessor` parses `@Configuration`, `@ComponentScan`, `@Import`, and `@Bean`, registering additional definitions.
- **`finishBeanFactoryInitialization(...)`**: after required processors are configured, Spring typically instantiates remaining **non-lazy** singletons (`preInstantiateSingletons`). `@Lazy`, prototype, or differently scoped beans may be created at other times.

Do not read this diagram as "no instances exist before `finishBeanFactoryInitialization`". Some processors and infrastructure must be instantiated early so Spring can continue; the point is that most non-lazy business singletons are finalized in the later phase.

For web contexts, creating/preparing the embedded server sits in the corresponding lifecycle phases; do not infer that the server starts the instant `@SpringBootApplication` is seen.

## 5. How Does ConfigurationClassPostProcessor Read Configuration?

`ConfigurationClassPostProcessor` is a Spring Framework `BeanDefinitionRegistryPostProcessor` registered by the annotation-processing mechanism. It works with known configuration classes, discovers configuration metadata, and translates them into bean definitions in the registry.

### 5.1. The Root @SpringBootApplication Class

`@SpringBootApplication` is a composite annotation carrying three primary roles:

```java
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
```

`@SpringBootConfiguration` is a specialized form of `@Configuration`. `@ComponentScan` finds stereotypes within the matching package scope. `@EnableAutoConfiguration` triggers auto-configuration selection. Listing them like this conveys meaning, not an exact replacement for every metadata/filter/alias on the composite annotation.

Root class example:

```java
package example.shop;

@SpringBootApplication
public class ShopApplication {
}
```

When placed in `example.shop`, default component scanning targets `example.shop` and subpackages such as `example.shop.service` or `example.shop.config`. That **does not** mean Boot scans the entire classpath or discovers auto-configuration JARs using `@ComponentScan`.

### 5.2. Reading @ComponentScan

Suppose there is a class:

```java
package example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public int finalPrice(int price) {
        return price - 10;
    }
}
```

If this package falls within the scan scope, Spring discovers the eligible class and registers a bean definition for `PriceService`. The `PriceService` object is not necessarily instantiated at the moment the metadata is discovered.

If `ShopApplication` sits in `example.shop.launcher` while `PriceService` sits in `example.shop.service`, they are sibling packages and the default scan from `launcher` **does not cover** `service`. Placing main in the root package or intentionally configuring scan scope resolves the issue.

### 5.3. Reading @Configuration and @Bean

Example:

```java
@Configuration(proxyBeanMethods = false)
class PricingConfiguration {
    @Bean
    PricingPolicy pricingPolicy() {
        return new PricingPolicy();
    }
}
```

This is an illustrative snippet: `PricingPolicy` must be defined and imported appropriately. Spring turns `pricingPolicy()` into a bean definition carrying factory method metadata. When the bean is needed, BeanFactory invokes the factory method through the appropriate mechanism and applies DI/lifecycle.

In some cases `@Bean` can be placed on classes without full `@Configuration`; semantics of inter-`@Bean` method calls differ between **full configuration** (`proxyBeanMethods=true`) and lite mode or `proxyBeanMethods=false`. The clearest way for one bean to depend on another is declaring the dependency via **`@Bean` parameters** or constructor injection.

### 5.4. Reading @Import and Extension Mechanisms

`@Import` brings configuration classes or controlled registration mechanisms into parsing:

```java
@Configuration
@Import(ExternalModuleConfiguration.class)
class ModuleConfiguration {
}
```

The snippet above is illustrative; `ExternalModuleConfiguration` is a hypothetical type, not a standalone runnable file. `@Import` can involve `ImportSelector`, `DeferredImportSelector`, or `ImportBeanDefinitionRegistrar`, not just importing an existing class.

`BeanDefinitionRegistryPostProcessor` can also register additional definitions directly when used at the right time. This is an infrastructure/framework extension, not a daily tool meant to replace simple `@Bean` methods.

## 6. At Which Step Does Auto-Configuration Enter the Pipeline?

`@EnableAutoConfiguration` (carried by `@SpringBootApplication`) uses Spring's import mechanism. In Spring Boot 3.x, `AutoConfigurationImportSelector` participates in selecting auto-configuration candidates; JARs declare the list in:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line in the metadata file holds the fully qualified name of an auto-configuration class. This candidate list is **distinct** from the package scope scanned by `@ComponentScan`. The selection mechanism also supports exclusions, conditions, and appropriate relative ordering among auto-configurations.

A typical auto-configuration class:

```java
@AutoConfiguration
@ConditionalOnClass(ExternalClient.class)
class ExternalClientAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(ExternalClient.class)
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
```

`ExternalClient` is a hypothetical type and the snippet above is **illustrative only**, not a standalone compilable program. Class conditions and bean conditions ensure a default definition appears only when module requirements are met.

### When Are Conditions Checked?

Some conditions can exclude a configuration class during configuration parsing; others are evaluated when preparing to register bean definitions. Hence there is no single checkpoint where "every `@Conditional` runs after every `@Bean`". Spring/Boot has phase logic and configuration ordering, especially for `@ConditionalOnBean` and `@ConditionalOnMissingBean`.

Common condition types:

| Condition | Checks | Observable Outcome |
| --- | --- | --- |
| `@ConditionalOnClass` | Class/library on classpath | Missing dependency skips the configuration needing it |
| `@ConditionalOnProperty` | Property has required value | Enables/disables configuration by environment |
| `@ConditionalOnBean` | Matching bean already registered | Configuration depends on available infrastructure |
| `@ConditionalOnMissingBean` | No matching bean at evaluation time | Default **backs off** for application configuration |
| `@ConditionalOnWebApplication` | Web application type | Web configuration runs only when appropriate |

The processing sequence is designed so auto-configuration can react to application beans already registered. However, **never** assume every Boot bean has `@ConditionalOnMissingBean` or every user bean automatically wins in every case; inspect the actual condition by type/name and accompanying conditions.

### Distinguishing Three Commonly Confused Outcomes

1. **Definition not registered:** Condition did not match; the default bean may not appear in the registry.
2. **Definition registered yet instance not created:** The object may be marked `@Lazy`, belong to another scope, or not be needed yet.
3. **Definition exists yet instance creation fails:** Constructor error, missing dependency, circular bean, property configuration, or initialization callback causes startup failure.

These three situations have different diagnostic steps; looking only at a "no bean" message is insufficient.

## 7. How Is a BeanDefinition Stored and Used to Create a Bean?

A `BeanDefinition` can carry information such as:

- Bean name and definition source.
- Class to instantiate or factory bean/factory method.
- Scope such as singleton/prototype and lazy status.
- Constructor arguments, property values, autowire metadata.
- Init/destroy methods and other lifecycle attributes.

For example, a method:

```java
@Bean
@Lazy
ReportFormatter reportFormatter() {
    return new ReportFormatter("REPORT");
}
```

is illustrative code, assuming a `ReportFormatter` class exists. Spring can register a bean definition named `reportFormatter` while processing configuration. Because of `@Lazy`, the singleton does not need to be instantiated immediately if no dependency requires it early.

When a bean is requested or pre-instantiation time arrives, `BeanFactory` can:

1. Choose the constructor/factory method from the definition.
2. Resolve dependencies and create required beans.
3. Instantiate the object, inject values, run callbacks and `BeanPostProcessor`s.
4. Return the final bean, potentially a proxy, to the consumer.
5. Cache the singleton instance for reuse when the scope is singleton.

**A `BeanDefinition` is not a runtime object**. For instance, `containsBeanDefinition("reportFormatter") == true` is not enough to conclude `containsSingleton("reportFormatter") == true`.

Do not use the phrase "single instance across the JVM": Spring's default singleton means one instance per bean definition within one container. Two independent `ApplicationContext`s can hold two different singletons for the same bean name.

## 8. Runnable Example: From Configuration to Definition and Instance

To observe the entire process, we use **Java 17+, Spring Boot 3.3.13, and Maven** with a non-web project. There are three bean sources:

- A bean declared via `@Configuration` + `@Bean`.
- A `@Service` bean discovered by component scan.
- `ObjectMapper` provided by Spring Boot auto-configuration when Jackson and required conditions are present.

At the same time, a `@Lazy` bean demonstrates that **the definition exists before the instance**.

### 8.1. Project Structure

```text
bean-startup-demo/
├── pom.xml
└── src/main/java/demo/
    ├── TraceApplication.java
    ├── config/
    │   └── GreetingConfiguration.java
    ├── model/
    │   └── GreetingFormatter.java
    └── service/
        └── GreetingService.java
```

`TraceApplication` sits in package `demo`, which is the parent package of `config`, `model`, and `service`. Thus default `@ComponentScan` discovers the configuration and service in the subpackages.

### 8.2. pom.xml

```xml
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
    <groupId>example</groupId>
    <artifactId>bean-startup-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
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
```

`spring-boot-starter-json` puts Jackson on the classpath. In the example's default configuration, conditional Boot auto-configuration can provide an `ObjectMapper` bean. No web server needs to be declared to demonstrate Jackson.

### 8.3. Bean Model and Application Configuration

**`src/main/java/demo/model/GreetingFormatter.java`:**

```java
package demo.model;

public record GreetingFormatter(String prefix) {
    public String greet(String name) {
        return prefix + " " + name;
    }
}
```

This is a regular Java class; with no stereotype, merely existing on the classpath is **not enough** for Spring to automatically register a bean.

**`src/main/java/demo/config/GreetingConfiguration.java`:**

```java
package demo.config;

import demo.model.GreetingFormatter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GreetingConfiguration {

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter("Chào");
    }
}
```

`GreetingConfiguration` is found by component scanning; Spring parses `@Bean greetingFormatter()` into a bean definition. `proxyBeanMethods=false` fits because the `@Bean` methods here do not call one another. The way the service receives the bean is **constructor injection**.

### 8.4. Scanned Service

**`src/main/java/demo/service/GreetingService.java`:**

```java
package demo.service;

import demo.model.GreetingFormatter;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final GreetingFormatter formatter;

    public GreetingService(GreetingFormatter formatter) {
        this.formatter = formatter;
    }

    public String say(String name) {
        return formatter.greet(name);
    }
}
```

`@Service` is discovered via component scan. Spring creates the `GreetingService` bean and resolves its `GreetingFormatter` dependency already defined by the `@Bean` method.

### 8.5. Startup Class and Inspecting the Registry

**`src/main/java/demo/TraceApplication.java`:**

```java
package demo;

import java.util.Map;
import com.fasterxml.jackson.databind.ObjectMapper;
import demo.service.GreetingService;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;

@SpringBootApplication
public class TraceApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(TraceApplication.class, args)) {

            String beanName = "delayedMarker";
            System.out.println("DEFINITION: "
                + context.containsBeanDefinition(beanName));
            System.out.println("BEFORE_GET: "
                + context.getBeanFactory().containsSingleton(beanName));

            context.getBean(DelayedMarker.class);

            System.out.println("AFTER_GET: "
                + context.getBeanFactory().containsSingleton(beanName));
        }
    }

    @Bean
    ApplicationRunner showBeans(GreetingService service, ObjectMapper mapper) {
        return args -> {
            System.out.println("SERVICE: " + service.say("Spring"));
            System.out.println("JACKSON: "
                + mapper.writeValueAsString(Map.of("ready", true)));
        };
    }

    @Bean
    @Lazy
    DelayedMarker delayedMarker() {
        System.out.println("CREATE_DELAYED");
        return new DelayedMarker();
    }

    public static class DelayedMarker {
    }
}
```

`context.getBean(DelayedMarker.class)` appears **after** `SpringApplication.run`, so before that point no consumer requested `delayedMarker` in the example. Because of `@Lazy`, the definition exists yet the instance is not yet in the singleton cache.

`showBeans()` is an application `@Bean`. `ApplicationRunner` is executed by Boot after the context refreshes successfully; it receives `GreetingService` from component scanning and `ObjectMapper` provided by auto-configuration. Notice that `ApplicationRunner` is invoked **before** `SpringApplication.run` returns, so the `SERVICE`/`JACKSON` lines appear before the `DEFINITION` inspection.

### 8.6. Build, Run, and Compare Output

In the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn -q -DskipTests package
java -jar target/bean-startup-demo-0.0.1-SNAPSHOT.jar --spring.main.web-application-type=none
```

Omitting the banner, startup logs, and shutdown logs, the lines **printed by the example itself** in order are:

```text
SERVICE: Chào Spring
JACKSON: {"ready":true}
DEFINITION: true
BEFORE_GET: false
CREATE_DELAYED
AFTER_GET: true
```

Explanation:

1. `SERVICE` comes from the scanned `GreetingService`, depending on `GreetingFormatter` declared by `@Bean`.
2. `JACKSON` demonstrates that `ObjectMapper` is available via Spring Boot auto-configuration under the project's classpath conditions.
3. `DEFINITION: true`: Spring registered the bean definition named `delayedMarker`.
4. `BEFORE_GET: false`: the `delayedMarker` singleton instance has not been created yet because of `@Lazy` and no dependency requested it.
5. `CREATE_DELAYED`: the `@Bean delayedMarker()` method actually executes upon calling `getBean()`.
6. `AFTER_GET: true`: the singleton instance is now managed by the factory.

In another application, if a non-lazy singleton bean depends on a lazy bean, the lazy instance can still be created early to satisfy the dependency. Therefore **lazy is a policy to defer when possible**, not a promise never to instantiate during startup.

If you want to check the example's environment, you can run:

```bash
java -version
mvn -version
```

These commands show the installed tool versions; they do not change the bean lifecycle mechanism.

## 9. Comparing Frequently Confused Milestones

| Milestone | What You Can Assert | What You Cannot Assert Yet |
| --- | --- | --- |
| `.class` file is on the classpath | JVM/classloader can load the class if valid | The class is already a Spring bean |
| Component scan finds the class | The class can become a bean definition candidate | The bean instance was created successfully |
| `@Bean` is parsed | A definition with a factory method can be registered | The factory method has already run |
| Auto-configuration listed in `.imports` | There is a configuration candidate to consider | All conditions pass or all its beans exist |
| `containsBeanDefinition(name)` returns `true` | The registry knows a definition with that name | A singleton instance is already in the cache |
| `containsSingleton(name)` returns `true` | BeanFactory has registered a singleton instance under that name | Every consumer has already called the bean |
| Context refresh completes | Most non-lazy singletons and infrastructure are ready | All lazy/prototype beans have been created |
| `SpringApplication.run()` returns normally | Startup steps performed by Boot succeeded | Future business operations will not fail |

`containsBeanDefinition(name)` checks the context's local registry according to its API; note that hierarchical contexts or aliases can create differences when looking up beans by name. For the final object, an AOP proxy can also make the runtime class differ from the declared class.

### Distinguishing Bean Overriding from Condition Back-Off

- **Condition back-off:** a configuration with `@ConditionalOnMissingBean` decides **not** to add the default bean when a matching bean already exists.
- **Bean definition overriding:** a definition registered later uses the same name to replace an earlier definition, if permitted. Boot disables overriding by default.
- **`@Primary`/`@Qualifier`:** chooses among beans of the same type during injection; does not remove other beans.

These three mechanisms relate to bean selection yet occur at different layers. In particular, `@Primary` **does not** cause an arbitrary auto-configuration to back off.

## 10. Diagnosing Errors by Phase

### 10.1. Cannot Find @Service

For example, `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException` involving an application service. Check:

- Are `@Component`/`@Service` declared properly?
- Is the main class in a parent package of the service?
- Is there a `@Profile` or condition preventing the bean definition from being registered?
- Is the configuration class imported or scanned?
- Are there multiple contexts, with the bean sitting in a different context?

If the scan scope does not include the service, adding auto-configuration properties usually **will not fix** the root cause.

### 10.2. Infrastructure Bean Does Not Appear

If `DataSource`, `ObjectMapper`, or a similar infrastructure bean is missing, check dependencies, properties, conditions, exclusions, and beans already declared by the application. Enable condition diagnostics:

```bash
java -jar target/bean-startup-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none --debug
```

Boot prints the **Conditions Evaluation Report** in startup output. *Positive matches*, *Negative matches*, and *Exclusions* explain why candidate auto-configurations were or were not applied. You may need to read the root cause if the definition exists yet bean instantiation failed.

Do not see an auto-configuration in the candidate list and assume all its beans must be present.

### 10.3. Bean Definition Exists Yet Still Fails

Common causes:

- The `@Bean` factory method throws an exception.
- The constructor cannot resolve a dependency or dependencies form a cycle.
- Property binding or init callbacks fail.
- A bean was instantiated too early by an extension and did not pass through all processors.
- Multiple beans share the same type, making injection ambiguous (`NoUniqueBeanDefinitionException`).

When seeing `BeanCreationException`, read the **deepest meaningful `Caused by` chain**, the class/method creating the bean, and the failing bean name. A bean creation exception can be wrapped in `UnsatisfiedDependencyException` when another bean depends on it.

### 10.4. When Do Conditions Run?

Do not memorize the wrong rule "all conditions are evaluated only after all beans are created". For auto-configuration, class/property/bean conditions are evaluated during parsing and registration, before most singletons are instantiated. Bean conditions depend on definitions known at evaluation time, so processing order is especially important.

Here, distinguish:

```text
Condition false     -> no default bean definition
@Lazy               -> definition exists, instance may not exist yet
BeanCreationError   -> definition exists, instance creation failed
```

These are three independent problems and should be identified before editing code.

## 11. Extension Points: When Do You Truly Need to Intervene?

For ordinary application needs, prefer `@Configuration`, `@Bean`, `@Component`, properties, and constructor injection. The extensions below serve libraries or specialized infrastructure:

| Extension | Active Phase | Used For |
| --- | --- | --- |
| `BeanDefinitionRegistryPostProcessor` | Registering/manipulating definitions while the container builds the registry | Generating definitions from a specialized metadata structure |
| `BeanFactoryPostProcessor` | Adjusting metadata/factory before most bean initialization | Changing properties or definition attributes |
| `BeanPostProcessor` | Before/after instance initialization | Decorating beans, creating proxies, processing callbacks |
| `ApplicationContextInitializer` | After context is created yet before refresh | Adjusting context/environment before startup |
| `ApplicationRunner` / `CommandLineRunner` | After successful context refresh | Running tasks at the application startup phase |

Note: instantiating a bean too early inside a `BeanFactoryPostProcessor` can leave some `BeanPostProcessor`s unregistered yet, causing unexpected behavior. Do not call `getBean()` in this phase merely to run a business task early.

When developing **auto-configuration for a library**, use `@AutoConfiguration`, appropriate conditions, and `.imports` declarations per Spring Boot guidance. When only developing an application, writing a custom auto-configuration for every bean is usually unnecessary.

## 12. Practical Design and Testing Rules

1. Place the `@SpringBootApplication` class in an appropriate root package, and components in subpackages.
2. Use `@Bean` for objects needing factory methods or from libraries lacking stereotypes.
3. Add starters for needed dependencies; use the Conditions Evaluation Report to see which auto-configurations match.
4. Use constructor injection to make dependencies explicit; avoid calling `ApplicationContext.getBean()` arbitrarily in business logic.
5. When using `@Lazy`, understand that errors may be delayed until first use; consider fail-fast for critical infrastructure beans.
6. When a default must be replaced, inspect the specific `@ConditionalOnMissingBean` condition rather than assuming `@Primary` will replace it.
7. When debugging, identify the exact phase: **definition registration**, **dependency resolution**, **instance creation**, or **runner/startup**.

In Spring Boot tests, startup failures often happen while the test context refreshes. An effective approach is to read the failing bean name, root cause, and related configuration; then determine whether it is a **missing definition** or an **initialization failure**. Do not fix it by widening package scan excessively or turning off auto-configurations wholesale without knowing the cause.

## 13. Self-Check

**Question 1.** Are `SpringApplication.run()` and `ApplicationContext.refresh()` the same method?

**Answer:** No. Boot's `SpringApplication` orchestrates startup; inside it, Spring Framework's context is refreshed. Boot also manages the environment, lifecycle events, and invoking runners.

**Question 2.** If the parser finds a `@Bean`, does that mean the factory method has already run?

**Answer:** Not necessarily. Spring usually registers the bean definition first; the factory method runs only when the container creates the bean.

**Question 3.** Will a `@Service` outside the default scan package appear just because the class is on the classpath?

**Answer:** No. It must be discovered by component scan, imported via appropriate configuration, or registered by another mechanism.

**Question 4.** Why does `.imports` containing an auto-configuration not guarantee that beans provided by that configuration will always exist?

**Answer:** That is only the candidate list. Classpath, properties, context type, existing beans, and exclusions still decide which configurations remain eligible.

**Question 5.** In the example, why is `DEFINITION: true` yet `BEFORE_GET: false`?

**Answer:** `@Bean delayedMarker` was processed into a bean definition, yet `@Lazy` defers singleton creation until the first `getBean()` call (since there is no early consumer).

**Question 6.** When an infrastructure bean is missing, where should you start?

**Answer:** Check dependencies, auto-configuration conditions, profiles/properties, exclusions, and existing beans; use the Conditions Evaluation Report and read the root cause instead of just widening `@ComponentScan`.

## References

- Spring Boot — SpringApplication: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Framework — The IoC Container: https://docs.spring.io/spring-framework/reference/core/beans.html
- Spring Framework — Java-based Container Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
- Spring Framework — Classpath Scanning: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
