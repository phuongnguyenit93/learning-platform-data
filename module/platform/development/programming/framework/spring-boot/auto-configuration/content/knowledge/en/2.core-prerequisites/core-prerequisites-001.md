# ApplicationContext, BeanFactory, and Bean Definitions During Startup

## 1. Why understand these three concepts?

When a Spring Boot application starts, Spring does not immediately instantiate an object just because it finds a `@Component` class or a `@Bean` method. First, Spring **reads configuration and registers bean definitions**; then the **container** uses those definitions to create objects, resolve dependencies, apply lifecycle callbacks and processors, and manage beans for the lifetime of the application.

The three concepts are related:

- **`BeanDefinition`**: a descriptor/metadata stating how a bean must be created and configured.
- **`BeanFactory`**: the core contract of the Spring IoC container, capable of providing beans by name or type, resolving dependencies, and managing bean lifecycles. An important implementation is `DefaultListableBeanFactory`.
- **`ApplicationContext`**: the application-level container surface, extending bean lookup capabilities and adding the environment (`Environment`), resources, internationalization messages, application events, and lifecycle orchestration. In common implementations, the context uses an internal `BeanFactory`.

Spring Boot **does not replace** these components. `SpringApplication.run(...)` prepares and refreshes (`refresh`) a Spring Framework `ApplicationContext`. Auto-configuration contributes additional **conditional bean definitions** to that container.

Mental diagram:

```text
Configuration sources
  @Component / @Service / @Repository / @Controller
  @Configuration + @Bean / @Import
  BeanDefinitionRegistry / ImportBeanDefinitionRegistrar
  Spring Boot auto-configuration
                |
                v
       BeanDefinitionRegistry
         (list of definitions)
                |
                v
        Internal BeanFactory
   (resolve DI, create beans, scope,
      lifecycle, post-processing)
                |
                v
        ApplicationContext
   (application API, Environment,
        events, resources, ...)
                |
                v
     Bean instance in use
```

This is a **diagram of responsibilities**, not a step-by-step trace of Spring's internals. Nor should `BeanDefinitionRegistry` be equated with a physical object completely separate from `BeanFactory`: `DefaultListableBeanFactory` is an example that implements several of these contracts simultaneously.

## 2. How do a Bean, a BeanDefinition, and a regular Java object differ?

A **bean** is an object managed by the Spring container. An object created with `new` in application code is just an ordinary Java object, unless it is registered or managed through container mechanisms.

A **`BeanDefinition`** is the blueprint telling the container how to create and process a bean. It typically holds information such as:

| Information | Practical meaning |
| --- | --- |
| Bean name | Identifier key in the container, e.g. `paymentService` |
| Bean class or factory method | Instantiate directly from a class or invoke a `@Bean`/factory method |
| Scope | `singleton`, `prototype`, or an additional provided scope |
| Lazy initialization | Whether to defer instantiation until needed |
| Dependencies / constructor arguments | Data and references used when creating the bean |
| Conditions and related configuration sources | Decide whether the bean definition is registered; some conditions are evaluated **before** the definition exists |
| Lifecycle metadata | Init/destroy methods and lifecycle processing info when declared |

Example:

```java
@Configuration
class FeatureConfig {
    @Bean
    ReportFormatter reportFormatter() {
        return new ReportFormatter();
    }
}
```

When Spring processes `FeatureConfig`, it may register a bean definition named `reportFormatter` bound to the factory method `reportFormatter()`. This **does not mean** a `ReportFormatter` has already been created. For a non-lazy singleton, Spring normally creates the bean during the completion phase of `refresh()`; for a bean marked `@Lazy`, creation can be deferred until first use.

`BeanDefinition` is not a copy of the object; nor is it a record of all runtime values. For example, an object created from a factory method may become an AOP proxy after `BeanPostProcessor`s run, and the final type of the object in use may not match the declared class type exactly.

### Bean name, bean type, and scope

- A bean can be retrieved by name (`getBean("reportFormatter")`) or by type (`getBean(ReportFormatter.class)`). Lookup by type can be ambiguous if multiple beans share the same type and there is no appropriate disambiguation mechanism.
- `singleton` is Spring's default: **one instance per bean definition within a single container**, not "a single instance across the entire JVM". Multiple `ApplicationContext`s can hold different singletons.
- `prototype` typically creates a new object each time the container is asked for the bean. Spring does not automatically manage the full destruction lifecycle of a prototype handed to a client the way it does for a singleton.
- A bean definition can already be registered while its corresponding singleton has **not yet been created**. This is crucial when observing startup and auto-configuration conditions.

## 3. What does BeanFactory do?

`BeanFactory` is the foundational API of the IoC container. Common calls include:

```java
Object beanByName = beanFactory.getBean("reportFormatter");
ReportFormatter beanByType = beanFactory.getBean(ReportFormatter.class);
boolean exists = beanFactory.containsBean("reportFormatter");
```

This snippet illustrates API usage and assumes an existing `beanFactory` variable along with a matching bean definition; it is **not a standalone Java program**.

With `DefaultListableBeanFactory`, Spring can register bean definitions, find autowiring candidates, check scopes, and manage singletons. In a typical application, developers do not instantiate `DefaultListableBeanFactory` and invoke each operation manually; `ApplicationContext` and its processors handle that process.

When creating a bean, the container may need to:

1. Read the bean definition and determine the appropriate constructor or factory method.
2. Resolve dependencies, which may require creating other beans first.
3. Instantiate the object and inject the required values/references.
4. Apply the appropriate callbacks or `BeanPostProcessor`s; the final bean may be wrapped in a proxy.
5. Retain the instance for subsequent lookups according to its scope, especially for singletons.
6. Execute appropriate destruction callbacks when the container closes, depending on scope and management.

Therefore, calling `getBean()` sometimes merely reads an existing singleton instance, but it can also **trigger bean creation** and an entire dependency chain. Avoid treating `getBean()` as a pure map lookup in every situation.

### Extension interfaces to distinguish

- `ListableBeanFactory`: can list and look up beans by type, rather than only looking up a single name.
- `ConfigurableListableBeanFactory`: provides additional configuration/inspection APIs for the bean factory, including `BeanDefinition` lookup.
- `BeanDefinitionRegistry`: registers, queries, and removes bean definitions; typically used by configuration-processing infrastructure.
- `BeanFactoryPostProcessor`: intervenes in **metadata/BeanFactory after definitions have been loaded**, before most regular beans are instantiated.
- `BeanDefinitionRegistryPostProcessor`: a subtype of `BeanFactoryPostProcessor` that gets an additional opportunity to register bean definitions. `ConfigurationClassPostProcessor` is a key example in Java configuration processing.
- `BeanPostProcessor`: acts on **bean instances** before/after initialization; involved in injection, callbacks, and many proxy mechanisms.

Remember the conceptual order: **registries and factory processors work on definitions; bean post-processors work on instances.** However, the framework has multiple processing phases and some infrastructure beans are initialized early, so a general diagram does not replace reading the specific lifecycle.

## 4. What does ApplicationContext add?

`ApplicationContext` inherits Spring's bean-access interfaces while providing many application capabilities:

| Capability | Example | Why it is useful |
| --- | --- | --- |
| Bean lookup, DI | `getBean(...)`, autowiring | Use registered objects |
| Environment and profiles | `getEnvironment()`, `@Profile` | Read effective configuration and separate environments |
| Resource loading | `getResource(...)` | Access resources according to Spring conventions |
| Application events | `publishEvent(...)` | Broadcast events within the application |
| Message resolution | `getMessage(...)` | Support i18n |
| Parent-child contexts | `getParent()` | Container hierarchy in architectures that need it |
| Lifecycle | `refresh()`, `close()` on `ConfigurableApplicationContext` | Orchestrate startup/shutdown |

Not every `ApplicationContext` has the same web server initialization mechanism. Common implementations include:

- `AnnotationConfigApplicationContext` for annotation-based application environments without a web server.
- `AnnotationConfigServletWebServerApplicationContext` in Spring Boot servlet web applications with an embedded server.
- `AnnotationConfigReactiveWebServerApplicationContext` in Spring Boot reactive web applications with an embedded server.

Boot typically infers the application type from the classpath, and it can also be adjusted with properties such as `spring.main.web-application-type`. **The context type depends on how the application is launched and which stack is used**; not every Boot project automatically creates a web server.

### When to use `ApplicationContext` directly?

Most business code should receive dependencies via constructor:

```java
@Service
class ReportService {
    private final ReportFormatter formatter;

    ReportService(ReportFormatter formatter) {
        this.formatter = formatter;
    }
}
```

This is an illustrative snippet and requires an appropriate `ReportFormatter` definition/import in a real application. Constructor injection makes dependencies explicit and easy to test. Calling `applicationContext.getBean(...)` throughout business code easily hides dependencies, makes the application harder to test, and drifts toward the *service locator* anti-pattern. Direct context APIs are better suited for writing integrations, infrastructure, observability tools, or logic that genuinely requires dynamic lookup.

## 5. SpringApplication.run and the refresh() cycle

Consider how a basic Boot application is processed:

```java
@SpringBootApplication
public class ExampleApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExampleApplication.class, args);
    }
}
```

`@SpringBootApplication` combines `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`. Boot participates in preparing the launch, while Spring Framework manages the actual lifecycle of the context and beans.

Conceptual timeline:

```text
main()
  |
  v
SpringApplication.run(...)
  |
  +--> determine application type and prepare Environment
  +--> create the appropriate ApplicationContext type
  +--> register primary sources and initializers
  |
  v
ApplicationContext.refresh()  [Spring Framework]
  |
  +--> prepare BeanFactory
  +--> run BeanDefinitionRegistryPostProcessor /
  |    BeanFactoryPostProcessor
  |      |
  |      +--> process @Configuration, @ComponentScan, @Import, @Bean
  |      +--> @EnableAutoConfiguration finds candidates and evaluates conditions
  |      +--> register valid BeanDefinitions
  |
  +--> register BeanPostProcessors
  +--> prepare other context infrastructure
  +--> instantiate most non-lazy singletons
  |      +--> resolve dependencies
  |      +--> instantiate / populate / initialize / post-process
  +--> finish refresh and publish corresponding lifecycle events
  |
  v
SpringApplication invokes ApplicationRunner / CommandLineRunner
  |
  v
Application ready to serve; context continues managing beans
```

The branches in `refresh()` above are **simplified to clarify responsibilities**. They do not guarantee an absolute order for every listener, processor, condition, dependency, or bean. Different `ApplicationContext` implementations may vary in some infrastructure phases.

Milestones to distinguish:

1. **Definition registration**: Spring knows *how* to create the bean, but has not necessarily created it yet.
2. **Condition processing**: Boot and Spring decide which configurations qualify to be registered; in Spring Boot 3.x, auto-configurations are brought in via the candidate imports list mechanism.
3. **Bean instantiation**: the factory executes the constructor/`@Bean` method, resolves dependencies, and runs callbacks and post-processors.
4. **Startup completion**: Boot runners are invoked after the context refreshes successfully; failures creating required beans can cause `SpringApplication.run` to fail.

Under standard defaults, most non-lazy singletons are created during `refresh()`; however, `@Lazy`, prototype scope, certain factories, or special handlers can defer instance creation until later.

## 6. How do @Configuration, @Bean, and @Component enter the registry?

Distinguish the two common paths.

### Component scanning

```java
@Component
class ExchangeRateService {
    // ...
}
```

When this package falls within `@ComponentScan` scope, Spring can register a bean definition for the `ExchangeRateService` class. The container then selects a constructor, resolves dependencies, and creates the instance when needed. Stereotypes such as `@Service`, `@Repository`, and `@Controller` are all tied to this component scanning mechanism.

### @Bean methods

```java
@Configuration
class PaymentConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new PaymentGateway();
    }
}
```

After processing `@Configuration`, Spring registers a bean definition for `paymentGateway`, whose metadata points to the factory method. When the bean is needed, Spring invokes that method. The snippets here are illustrative and assume `PaymentGateway` is already defined.

The two paths produce **bean definitions from different sources**, yet both are managed by the Spring IoC container. If the same bean name appears from multiple sources, conflict/overriding rules also come into play; never assume the last bean always wins simply because "its file appeared later".

### Why is @Configuration special?

A full `@Configuration` class with the default `proxyBeanMethods=true` can be enhanced by Spring so that calls between `@Bean` methods go through the container to preserve bean semantics. With `proxyBeanMethods=false`, direct Java calls between `@Bean` methods are not intercepted by this mechanism. **Constructor injection or declaring parameters on the `@Bean` method** is the explicit way to receive the container-managed bean without relying on calling configuration methods directly.

These mechanisms handle configuration processing before/during bean definition registration; an `@Bean` annotation does not automatically create an instance the moment the JVM loads the class.

## 7. Where does auto-configuration add bean definitions?

In Spring Boot 3.x, the list of a library's auto-configuration classes is declared in:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

`@EnableAutoConfiguration` activates the selection of these candidates. `@AutoConfiguration` classes are Spring configurations applied **conditionally**, for example:

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

This is an **illustrative snippet**: `ExternalClient` is a hypothetical type and the code is not a standalone application. Its meaning is:

- If `ExternalClient` is absent from the classpath, the class condition does not match and this configuration is not applied.
- If the class is present but the application already provides a matching `ExternalClient` bean, the `@ConditionalOnMissingBean` configuration backs off in favor of the application bean.
- If all required conditions pass, Spring registers the `externalClient` bean definition; creating the instance afterward is up to the BeanFactory.

An **unmatched condition typically prevents the bean definition from appearing**, which differs from a case where the bean definition exists but the bean has not been created yet due to `@Lazy`. Both situations can make it look like "the instance isn't there yet", but debugging them is completely different.

Other common conditions include `@ConditionalOnProperty`, `@ConditionalOnBean`, `@ConditionalOnWebApplication`, and resource conditions. Bean conditions depend on the state of bean definitions at evaluation time; that is why auto-configuration is organized to be processed after application configuration and has ordering rules. Do not use `@ConditionalOnMissingBean` arbitrarily in business configuration and expect the result to always behave like official auto-configuration.

### Does auto-configuration mean beans override beans?

No. A default bean configured to **back off** simply will not be registered if a matching application bean already exists. **Bean definition overriding**, by contrast, is a mechanism where a definition with the same name replaces another definition; Spring Boot generally disables bean definition overriding by default. In addition, `@Primary` prioritizes a candidate during autowiring by type, but **does not remove** the remaining bean definitions. Distinguish these three situations before fixing an issue:

| Mechanism | What happens | Symptom |
| --- | --- | --- |
| Condition back off | Default bean is not registered | Default definition not found; application bean already exists |
| Bean definition overriding | One definition replaces another with the same name | May report a name conflict if overriding is disallowed |
| `@Primary`/`@Qualifier` | Choose among multiple beans of the same type | Multiple beans still exist; one candidate is selected for the dependency |

## 8. Runnable example: BeanDefinition exists, but bean instance does not yet exist

This example uses **Java 17+**, **Spring Boot 3.3.13**, Maven, and `spring-boot-starter` to run an application without a web server. The goal is to observe three facts in the same context:

1. After `SpringApplication.run()`, the bean definition created by `@Bean` is already present.
2. `@Lazy` keeps the singleton from being instantiated immediately.
3. `getBean()` asks the BeanFactory to create the instance; a subsequent lookup returns the same singleton.

Structure:

```text
context-fundamentals/
├── pom.xml
└── src/main/java/demo/
    └── ContextFundamentalsApplication.java
```

**`pom.xml`:**

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
    <artifactId>context-fundamentals</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
```

**`src/main/java/demo/ContextFundamentalsApplication.java`:**

```java
package demo;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;

@SpringBootApplication
public class ContextFundamentalsApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(ContextFundamentalsApplication.class, args)) {

            String name = "trainingGreetingService";
            BeanDefinition definition =
                context.getBeanFactory().getBeanDefinition(name);

            System.out.println("DEFINITION_FOUND: "
                + context.containsBeanDefinition(name));
            System.out.println("FACTORY_METHOD: "
                + definition.getFactoryMethodName());
            System.out.println("CREATED_BEFORE_GET: "
                + context.getBeanFactory().containsSingleton(name));

            GreetingService first = context.getBean(GreetingService.class);
            GreetingService second = context.getBean(name, GreetingService.class);

            System.out.println("CREATED_AFTER_GET: "
                + context.getBeanFactory().containsSingleton(name));
            System.out.println("SAME_SINGLETON: " + (first == second));
            System.out.println("MESSAGE: " + first.greet("Boot"));
        }
    }

    @Bean
    @Lazy
    GreetingService trainingGreetingService() {
        System.out.println("CREATE_GREETING");
        return new GreetingService("Hello");
    }

    public static final class GreetingService {
        private final String prefix;

        public GreetingService(String prefix) {
            this.prefix = prefix;
        }

        public String greet(String name) {
            return prefix + ", " + name + "!";
        }
    }
}
```

From the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn -q -DskipTests package
java -jar target/context-fundamentals-0.0.1-SNAPSHOT.jar --spring.main.web-application-type=none
```

Ignoring the banner and startup logs, the lines printed by the example in order are:

```text
DEFINITION_FOUND: true
FACTORY_METHOD: trainingGreetingService
CREATED_BEFORE_GET: false
CREATE_GREETING
CREATED_AFTER_GET: true
SAME_SINGLETON: true
MESSAGE: Hello, Boot!
```

Explanation of each milestone:

- `DEFINITION_FOUND: true`: `@Bean` was processed by Spring's parser and registered as a definition named `trainingGreetingService`.
- `FACTORY_METHOD: trainingGreetingService`: the bean definition holds the name of the method that creates the object. The object does not necessarily exist yet.
- `CREATED_BEFORE_GET: false`: because of `@Lazy`, the example's singleton bean is not yet in the singleton cache after `refresh()` (and no consumer requested it early).
- `getBean(GreetingService.class)` is the actual request that causes the container to call the `@Bean` method, producing `CREATE_GREETING`.
- `CREATED_AFTER_GET: true`: the instance is now registered in the factory's singleton cache.
- `SAME_SINGLETON: true`: lookups by type and by name both return the same instance for this singleton definition.
- `MESSAGE`: behavior of the object after Spring creates it.

`containsBeanDefinition(name)` and `containsSingleton(name)` answer **two different questions**: *is there a bean blueprint?* and *is a singleton instance already registered?* Do not infer the existence of an instance solely from finding a definition.

Note that `@Lazy` on a bean **does not strictly guarantee** it will never be created during startup in every application: if another non-lazy singleton needs that bean to initialize, the container still has to create the dependency. The example above deliberately has no such consumer before the `getBean()` calls in `main`.

## 9. Bean lifecycle and the role of processors

When Spring decides to instantiate a regular bean, the high-level steps include:

```text
BeanDefinition (metadata)
   |
   v
Resolve constructor / factory method and dependencies
   |
   v
Instantiate (create object)
   |
   v
Populate properties / dependency injection
   |
   v
Aware callbacks (if applicable)
   |
   v
BeanPostProcessor before initialization
   |
   v
Initialization callbacks (@PostConstruct,
InitializingBean, custom init method if any)
   |
   v
BeanPostProcessor after initialization
   |  [may return a proxy]
   v
Bean ready for use
   |
   v
Destruction callbacks on context close (if applicable)
```

This is a general diagram: `InstantiationAwareBeanPostProcessor`, `FactoryBean`, AOP, and other extensions can introduce additional processing branches. Not every bean runs every callback.

For example, a `@Transactional` bean may be exposed via a proxy after related post-processing; application code receives a bean conforming to the expected contract, but the runtime class may differ from the declared class. Therefore, when debugging, separate the **bean definition**, the **original instance**, and the **actual instance/proxy retrieved**.

Two common points of confusion:

- `BeanFactoryPostProcessor` intervenes in container metadata **before regular singleton instantiation**. `BeanPostProcessor` intervenes on created instances.
- Do not call `getBean()` arbitrarily inside a factory post-processor: requesting early bean instantiation can cause the bean to bypass some `BeanPostProcessor`s or alter the expected order.

A bean with `@PreDestroy` or a custom destroy method is managed by the container according to its lifecycle; prototype beans handed to a client generally need to be cleaned up by the client itself. Closing the `ApplicationContext` is an important operation in standalone applications or test examples.

## 10. Startup scenarios to know

### 10.1. Definition exists, yet injection still fails

A definition may already be registered while instance creation fails: missing dependencies, circular dependencies, errors in the constructor/factory method, invalid property binding, or an initialization callback throwing an exception. In such cases, `containsBeanDefinition` can be true while `getBean()` or `SpringApplication.run()` still fails.

Common exceptions:

- `NoSuchBeanDefinitionException`: no matching candidate at resolution time.
- `NoUniqueBeanDefinitionException`: multiple candidates exist with insufficient information to choose.
- `BeanCreationException`: unable to create or initialize the bean; inspect the underlying root cause.
- `BeanCurrentlyInCreationException`: typically related to a cycle or requesting a bean while it is currently being created.

Actual exceptions depend on context; an error may be wrapped inside `UnsatisfiedDependencyException` or `BeanCreationException`.

### 10.2. Default bean does not appear

Check two questions separately:

1. **Was the auto-configuration selected and did its conditions match?** Check the classpath, properties, web context type, exclusions, and existing user-defined beans.
2. **Was the bean definition registered, yet not created or failed to create?** Check lazy initialization, dependencies, and initialization exceptions.

You can enable diagnostic output with:

```bash
java -jar target/context-fundamentals-0.0.1-SNAPSHOT.jar --debug --spring.main.web-application-type=none
```

Boot prints the Conditions Evaluation Report in the diagnostic output. *Positive matches* and *Negative matches* help explain the auto-configuration decisions. The report explains configuration conditions; it does not replace reading the stack trace when bean creation fails.

### 10.3. Two beans of the same type

For example, if an application registers two different `PaymentGateway` beans, a constructor taking only a `PaymentGateway` parameter may become ambiguous. You can use `@Qualifier`, `@Primary`, or redesign the API. `@Primary` does not remove a bean; it affects candidate selection. When examining auto-configuration, read carefully whether the condition checks by **type** or by **name** to know whether a custom bean prevents the default from being registered.

### 10.4. Two independent contexts

Two independent `ApplicationContext`s can both contain a bean named `trainingGreetingService`, with each holding its own separate singleton. `singleton` does not mean JVM-global. In hierarchical parent-child contexts, bean visibility and shadowing rules can differ; determine which context owns the definition and the actual bean.

### 10.5. Lazy is not a cure-all for startup problems

Setting `@Lazy` or `spring.main.lazy-initialization=true` can defer creation of some beans and shorten startup, but configuration errors may only surface on the first request that uses the bean. Beans needed early may still be created anyway. When optimizing, measure actual startup time and consider the service's fail-fast requirements.

## 11. How to observe in a real application

When investigating a bean, gather facts in order:

1. **Identify the running context:** servlet, reactive, or non-web; whether there is a parent context.
2. **Find the definition source:** `@Component`, `@Bean` method, auto-configuration import, or programmatic registration.
3. **Read conditions and exclusions:** especially for auto-configuration, consult the Conditions Evaluation Report.
4. **Check creation timing:** eager singleton, lazy singleton, prototype, or custom scope.
5. **Inspect dependencies and post-processing:** missing dependencies, ambiguous types, circular dependencies, or proxies.
6. **Check the runtime instance and lifecycle:** whether the bean was created/initialized successfully and whether the context is closing.

In diagnostic code, `ConfigurableApplicationContext#getBeanFactory()` provides a `ConfigurableListableBeanFactory`, from which definitions can be read via `getBeanDefinition(name)`. Limit the use of these APIs in regular business logic, as they couple code directly to Spring infrastructure.

### Things to avoid when intervening in startup

- Mutating bean definitions inside a bean constructor/`@PostConstruct` to "add configuration": this is usually too late for processing that must occur before instantiation.
- Calling `getBean()` inside a `BeanFactoryPostProcessor` to try to run business logic early: this can trigger instantiation before the full post-processor chain is in place.
- Using `@Primary` hoping auto-configuration will stop creating a bean: those are two separate mechanisms.
- Reading a proxy bean's class name and concluding the bean definition was lost: proxying is a normal possible step in instance processing.
- Assuming all singletons are created at the exact same moment or that every `@Bean` is lazy.
- Guessing the cause of `NoSuchBeanDefinitionException` from a dependency name without reading the Conditions Evaluation Report and root cause.

## 12. Self-check

**Question 1.** After `refresh()`, `containsBeanDefinition("x")` returns `true` while `containsSingleton("x")` returns `false`. Is this a contradiction?

**Answer:** No. A bean definition can exist before a bean instance is created, such as with a lazy bean. Also be sure to consider the scope and bean name being checked.

**Question 2.** When you want to add a bean definition before regular singletons are created, which extension type is more appropriate: `BeanDefinitionRegistryPostProcessor` or `BeanPostProcessor`?

**Answer:** `BeanDefinitionRegistryPostProcessor`, because it is designed for the definition-registration phase. `BeanPostProcessor` handles instances.

**Question 3.** Why can Spring Boot provide auto-configuration while still using Spring Framework's DI?

**Answer:** Boot selects and conditionally registers bean definitions; the Spring container uses the valid definitions to create beans, resolve dependencies, and manage lifecycles.

**Question 4.** Are `@Primary`, bean overriding, and `@ConditionalOnMissingBean` the same thing?

**Answer:** No. `@Primary` prioritizes a candidate during injection; overriding replaces a bean definition with the same name (if allowed); `@ConditionalOnMissingBean` decides **not to register** the default bean when a matching bean already exists.

**Question 5.** If `SpringApplication.run()` throws a bean creation error, should you only look for the bug in `main()`?

**Answer:** No. Read the exception cause chain to see when the bean was instantiated, which dependency was missing, which configuration condition failed to match, and which callback failed.

## References

- Spring Framework — The IoC Container: https://docs.spring.io/spring-framework/reference/core/beans.html
- Spring Framework — Bean Overview and BeanDefinition: https://docs.spring.io/spring-framework/reference/core/beans/definition.html
- Spring Framework — Customizing the Nature of a Bean: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
