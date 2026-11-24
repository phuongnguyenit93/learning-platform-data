# Distinguishing Component Scanning from Annotation Processing on Existing Beans in Spring Core Container

## 1. Learning Objectives

Spring Framework uses annotations at different times. Two processes that are most frequently confused are:

1. **Component scanning:** finding eligible classes on the classpath and **registering bean definitions** into the IoC Container.
2. **Annotation processing on already-registered beans:** when beans are created and managed, infrastructure components read annotations to **inject dependencies, run lifecycle callbacks, or apply additional behavior**.

These two tasks are related yet **not the same**. A class annotated with `@Component` that has not been scanned or registered by another mechanism does not become a bean on its own. Conversely, a bean declared via `@Bean` or XML can still have `@Autowired`, `@PostConstruct`, and many other annotations processed if the corresponding infrastructure is present.

After this lesson, you will be able to:

- Distinguish **bean definition discovery/registration** from **bean instance processing**.
- Explain why `@ComponentScan` and `@Autowired` solve two different problems.
- Identify the roles of `ConfigurationClassPostProcessor`, `AutowiredAnnotationBeanPostProcessor`, `CommonAnnotationBeanPostProcessor`, and other `BeanPostProcessor`s.
- Run a Java 17+ example demonstrating a bean registered via `@Bean` with an `@Autowired` field and `@PostConstruct`/`@PreDestroy` callbacks even without `@ComponentScan`.
- Pinpoint why an annotation has no effect: **missing bean**, **missing post-processor registration**, **missing integration infrastructure**, or **calls bypassing a proxy**.
- Read logs and inspect bean definitions accurately instead of assuming Spring automatically processes any annotation it sees.

**Context:** this content belongs to the **Component Scanning** group of Spring Core Container, while connecting to lifecycle and IoC Container extension points. Examples mentioning transactions, caching, and web mappings are only used to define mechanism boundaries.

## 2. Two Independent Questions: "Where Does the Bean Come From?" and "What Does Spring Do with It?"

A Java class is not automatically a Spring bean just because the classpath contains it:

```java
import org.springframework.stereotype.Component;

@Component
public class GreetingService {
    public String greet() {
        return "hello";
    }
}
```

This class compiles when Spring Context is on the classpath, yet to retrieve `GreetingService` from `ApplicationContext`, there must first be a corresponding **bean definition** or another registration mechanism.

**First question — Bean registration:** How is the bean definition placed into the registry? For example: `@ComponentScan`, `@Bean` in a configuration, `@Import`, XML, programmatic registration, or auto-configuration mechanisms.

**Second question — Bean processing:** When the container instantiates from the bean definition, does it inject `@Autowired` fields/methods, invoke `@PostConstruct`, run init callbacks, create AOP proxies, or register related metadata? This requires appropriate post-processors and infrastructure.

Mental model diagram:

```text
                         CLASS / METADATA
                                |
                     Bean registration paths
                    /           |           \
          @ComponentScan      @Bean        XML / @Import / ...
                    \           |           /
                     \          v          /
                         BeanDefinition
                                |
                Spring BeanFactory / ApplicationContext
                                |
                   create and configure bean instance
                                |
                appropriate BeanPostProcessors
                   /           |            \
            @Autowired   @PostConstruct    AOP proxy ...
                                |
                        bean ready for use
```

Do not interpret this diagram to mean Spring always executes processors in one simple fixed sequence for all annotations. Some components operate **on bean definitions before instances exist**, some intervene before/after initialization, and others belong to different runtime infrastructure. Subsequent sections analyze each group.

## 3. What Does Component Scanning Actually Do?

### 3.1. Finding Candidate Classes Within Configured Scope

In plain Spring configuration:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan(basePackages = "com.example.catalog")
public class CatalogConfig {
}
```

`@ComponentScan` instructs Spring to scan package `com.example.catalog` and its subpackages, apply candidate-matching filters (by default including `@Component` and stereotypes such as `@Service`, `@Repository`, `@Controller`), and register bean definitions.

**It does not mean** Spring automatically scans every package, nor does it mean the scanner immediately creates all instances as soon as it reads class files.

Example:

```text
com.example.catalog
  ├── CatalogConfig       @Configuration + @ComponentScan
  ├── CatalogService      @Service
  ├── CatalogRepository   @Repository
  └── Helper              plain class, no marker

com.example.external
  └── ExternalService     @Service
```

With the configuration above and no other registration, the scanner can discover `CatalogService` and `CatalogRepository` in the target package; `Helper` lacks a default marker, and `ExternalService` lies outside the scan scope. `CatalogConfig` enters the context via how you load or scan it.

### 3.2. Being Scanned Does Not Mean Guaranteed Instantiation

After a class is selected, Spring must still satisfy bean definition rules, bean names, scopes, constructors, dependencies, conditional metadata, and initialization infrastructure. A candidate can be excluded by filters/conditions, or bean creation can fail due to a missing dependency.

```text
Class found on classpath
        !=
Class matches component-scan filter
        !=
Bean definition registration succeeds
        !=
Bean instance creation succeeds
        !=
Has every expected runtime behavior
```

These are distinct layers to inspect separately.

### 3.3. What the Component Scanner Does Not Do on Its Own

- Does not automatically inject `@Autowired` into an object you instantiate yourself with `new` outside the container.
- Does not have to be present for `@Bean` to work.
- Does not turn every class with any arbitrary annotation into a bean; the default scanner only recognizes annotations matching its filters.
- Does not automatically open HTTP ports, start transactions, or register caching.
- Cannot prevent a bean from appearing if that same bean is registered via `@Bean` or another configuration.

**Key takeaway:** component scanning primarily serves **discovering and registering bean definitions**.

## 4. What Is Annotation Processing on Existing Beans?

Suppose a bean is registered directly via Java configuration:

```java
@Configuration
class AppConfig {
    @Bean
    ReportService reportService() {
        return new ReportService();
    }

    @Bean
    ReportRepository reportRepository() {
        return new ReportRepository();
    }
}
```

This is a structural example; a real application needs declarations/imports for `@Configuration`, `@Bean`, and both classes. There is no `@ComponentScan` in this configuration, yet the container still has `reportService` and `reportRepository` beans registered by the `@Bean` factory methods.

If `ReportService` has:

```java
import org.springframework.beans.factory.annotation.Autowired;

class ReportService {
    @Autowired
    private ReportRepository repository;

    public String run() {
        return repository.read();
    }
}
```

then when Spring creates the bean from `@Bean` and `AutowiredAnnotationBeanPostProcessor` is active, the field can be injected before use.

**The actual mechanism is not component scan discovering `@Autowired` fields to register `ReportService`.** `ReportService` was already registered by `@Bean`; the post-processor subsequently processes injection metadata on the instance being created.

Similarly, `@PostConstruct` requires lifecycle annotation processing infrastructure to act on managed beans. A manually created object:

```java
ReportService ordinaryObject = new ReportService();
```

does not automatically get `@Autowired` injected or `@PostConstruct` called by Spring merely because the source code carries annotations. **In Java**, annotations are metadata; a framework or tool must actually read and act on that metadata.

## 5. Two Groups of Extension Points to Distinguish

Spring has extension points operating on **definitions** and **instances** in different phases.

| Group | Target | Primary Timing | Examples and Role |
| --- | --- | --- | --- |
| `BeanDefinitionRegistryPostProcessor` | Registry of bean definitions | Before instantiating regular business beans | Can register additional definitions; `ConfigurationClassPostProcessor` processes configuration classes, `@Bean`, `@ComponentScan`. |
| `BeanFactoryPostProcessor` | Bean definition metadata | Before creating regular beans | Modifies/configures metadata, e.g. placeholder/property settings. |
| `BeanPostProcessor` | Managed bean instances | During bean creation/initialization | Processes annotation injection/lifecycle, applies proxies, or runs custom initialization logic. |
| Infrastructure outside bean creation | Bean metadata and/or runtime requests/calls | During context setup or application execution | MVC handler mappings, scheduled task registration, AOP advisors/interceptors. |

`BeanDefinitionRegistryPostProcessor` extends `BeanFactoryPostProcessor`, adding a phase that operates on the **registry**. `ConfigurationClassPostProcessor` parses annotation configuration, so class scanning and `@Bean` registration can occur during the same metadata processing phase before application beans are instantiated.

`BeanPostProcessor` has two core callbacks:

```java
Object postProcessBeforeInitialization(Object bean, String beanName);
Object postProcessAfterInitialization(Object bean, String beanName);
```

This is the conceptual signature of `org.springframework.beans.factory.config.BeanPostProcessor` (the actual API provides default implementations). A processor can return the original instance or a replaced/wrapped instance. Spring AOP typically creates proxies through post-processing infrastructure, yet **not every `BeanPostProcessor` creates a proxy**.

**Key point:** a bean already present in the definition registry will go through the bean creation lifecycle. Package scanning is not a prerequisite for these `BeanPostProcessor`s to run.

## 6. Who Processes Common Annotations?

| Annotation / metadata | Typical Phase or Infrastructure | Key Conditions to Remember |
| --- | --- | --- |
| `@Component`, `@Service`, `@Repository`, `@Controller` | Component scan / bean definition registration | Appropriate package/filters scanned, or bean registered through another path. |
| `@Configuration` and `@Bean` | `ConfigurationClassPostProcessor` | Configuration class must enter the context via a valid registration path. |
| `@Autowired`, `@Value`, Jakarta `@Inject` | `AutowiredAnnotationBeanPostProcessor` and dependency/value resolution | Bean is Spring-managed; processor must be registered. |
| Jakarta `@Resource`, `@PostConstruct`, `@PreDestroy` | `CommonAnnotationBeanPostProcessor` / lifecycle support | Processor and Jakarta Annotation API must be properly present. |
| `@Transactional` | Transaction annotation source, AOP/interceptor, transaction manager | Does not automatically enable transactions just because a bean has the annotation. |
| `@Async` | Async infrastructure, typically `AsyncAnnotationBeanPostProcessor` | Requires enabling async support, executor, and appropriate invocation. |
| `@Cacheable` | Caching/AOP infrastructure | Requires enabling caching and configuring a suitable cache manager. |
| `@Scheduled` | `ScheduledAnnotationBeanPostProcessor` / scheduling infrastructure | Requires enabling scheduling and an appropriate execution context. |
| `@RequestMapping`, `@GetMapping` on controllers | Spring MVC handler mapping/adapter | Requires a web application context and appropriate MVC infrastructure. |

One annotation may be read by multiple components or used across multiple phases; this table shows the **primary lead** for analysis, without claiming every annotation has only one processor or behaves identically in all applications.

### 6.1. @Autowired Is Not a "Class-Scanning Mechanism"

When Spring has a bean definition for class `A` and is creating `A`, `AutowiredAnnotationBeanPostProcessor` can analyze constructors, fields, or methods marked `@Autowired` to assist constructor selection and dependency injection. Depending on registration path and timing, injection details differ.

For example, a class registered via `@Bean` whose constructor is **called directly inside the factory method**: the container does not re-select a constructor for that `new A()` object. However, `@Autowired` fields/methods on the returned instance can still be post-processed. Conversely, a bean instantiated directly from its bean class can have `@Autowired` constructors selected by the processor.

### 6.2. @PostConstruct Runs After Injection, Before the Bean Is Ready

With the processor properly configured, `@PostConstruct` callbacks typically run once basic dependencies have been injected into the instance, during the bean initialization phase, before the bean finishes startup.

`@PreDestroy` runs during Spring-managed bean destruction, typically on context close for singletons. The container **does not manage full destruction callbacks for prototypes after handing out an instance**; therefore do not assume prototypes always receive `@PreDestroy` after finishing work.

## 7. Runnable Example: NO Component Scan Yet Annotations Still Work

This is the most important hands-on exercise. We deliberately **omit `@ComponentScan`**, yet still:

- Register `Formatter` and `ManualService` via two `@Bean` factory methods.
- Use `@Autowired` to inject the `Formatter` field into the `ManualService` bean.
- Use `@PostConstruct` to print injection status before main logic runs.
- Use `@PreDestroy` to print the destruction event when closing `ApplicationContext`.
- Put `@Service` on `ManualService` to prove the class has a stereotype yet **is registered thanks to `@Bean`**.
- Put `@Component("unscannedComponent")` on another class without registering it, proving **annotations alone do not turn a class into a bean**.

### 7.1. Creating the Project

Structure:

```text
annotation-processing-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── AnnotationProcessingDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'annotation-processing-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'jakarta.annotation:jakarta.annotation-api:2.1.1'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.AnnotationProcessingDemo'
}
```

Spring Framework 6.2.x requires Java 17+. Add the Jakarta Annotation API directly in dependencies so the project cleanly compiles `jakarta.annotation.PostConstruct` and `jakarta.annotation.PreDestroy` imports. Do not use legacy Java EE `javax.annotation` with Spring 6.

**`src/main/java/demo/AnnotationProcessingDemo.java`**

```java
package demo;

import java.util.Locale;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

public class AnnotationProcessingDemo {

    public static class Formatter {
        public String format(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    @Service
    public static class ManualService {
        // Deliberately using field injection to observe annotation processing.
        // In production design, constructor injection is usually preferred.
        @Autowired
        private Formatter formatter;

        @PostConstruct
        void afterInjection() {
            System.out.println("post-construct=" + (formatter != null));
        }

        public String work(String input) {
            return formatter.format(input);
        }

        @PreDestroy
        void beforeDestroy() {
            System.out.println("pre-destroy");
        }
    }

    @Component("unscannedComponent")
    public static class UnscannedComponent {
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Formatter formatter() {
            return new Formatter();
        }

        @Bean
        ManualService manualService() {
            return new ManualService();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("context-ready");
            System.out.println("manual-service="
                    + context.containsBean("manualService"));
            System.out.println("unscanned-component="
                    + context.containsBean("unscannedComponent"));

            ManualService service = context.getBean(ManualService.class);
            System.out.println("work=" + service.work("hello"));
        }
    }
}
```

**Run** in the project root directory:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS, or `gradlew.bat run --quiet` on Windows. Standalone `javac AnnotationProcessingDemo.java` is insufficient without declaring the Spring/Jakarta classpath; Gradle compiles and runs with dependencies.

**Lines printed by the program (stdout):**

```text
post-construct=true
context-ready
manual-service=true
unscanned-component=false
work=HELLO
pre-destroy
```

Build tools may print other logs depending on the environment; the lines above are the output from the program's `System.out.println` calls.

### 7.2. Why Is the Output Like That?

1. `new AnnotationConfigApplicationContext(Config.class)` registers configuration class `Config` and refreshes the context. `Config` has `@Configuration` and **no `@ComponentScan`**.
2. `ConfigurationClassPostProcessor` processes `@Bean` methods, creating bean definitions for `formatter` and `manualService`.
3. The container creates the `ManualService` bean from factory method `manualService()`. Inside the factory method, the object is constructed via `new ManualService()`; this `new` call occurs **inside a Spring-controlled bean creation mechanism**.
4. The returned bean instance is processed by relevant post-processors. `AutowiredAnnotationBeanPostProcessor` finds the `formatter` field and injects the `Formatter` bean from the context.
5. `CommonAnnotationBeanPostProcessor` picks up the `@PostConstruct` callback; at that point `formatter != null`, so it prints `post-construct=true` **before** `context-ready`.
6. `@Service` on `ManualService` is not why the bean appears in this example. `@Bean` is the actual registration path, yet that does not stop processors from processing the instance.
7. `UnscannedComponent` has `@Component` but is not directly registered and no component scan is active, so `containsBean("unscannedComponent")` returns `false`.
8. `try-with-resources` closes `AnnotationConfigApplicationContext`. The `@PreDestroy` callback of singleton `ManualService` runs and prints `pre-destroy`.

This exercise proves two separate facts:

- **Bean definitions can exist without component scan:** `manualService=true`.
- **Annotations on existing beans are still processed:** `post-construct=true` and `work=HELLO`, even without `@ComponentScan`.

It also proves the converse: **`@Component` sitting on a class alone does not create a bean** if the class is neither scanned nor registered.

### 7.3. What Happens If You Call new Outside the Container?

Consider this standalone snippet:

```java
AnnotationProcessingDemo.ManualService manual =
        new AnnotationProcessingDemo.ManualService();
manual.work("hello");
```

This is not how Spring beans are created: the `formatter` field remains `null`, so `work` throws a `NullPointerException` at `formatter.format(...)`. There is no automatic `@PostConstruct` or `@PreDestroy`. Do not run this variant expecting a passing test.

**Subtle point:** `@Bean` can return an object created with `new` and **still** be processed by Spring because the factory method runs inside the container lifecycle. Merely "seeing the `new` keyword" is not enough to conclude whether Spring manages a bean; you must check how that object enters the container.

## 8. Comparing with Component Scan via a Counterpart Example

Building on the previous program, to automatically discover stereotype-annotated classes, you can create a context with scan configuration:

```java
@Configuration
@ComponentScan(basePackageClasses = AnnotationProcessingDemo.class)
class ScanConfig {
}
```

This is a **separate configuration illustration**, not a drop-in replacement in the demo without reviewing packages. Scanning the whole `demo` package containing `Config` with its `@Bean` methods may cause Spring to pick up `Config` as well; manually declared beans could appear alongside scanned beans of the same type and cause duplicate names, multiple candidates, or definition conflicts. When experimenting, separate scanned fixture packages from manual configuration packages or exclude/import intentionally.

An independent scan test might use:

```java
@Configuration
@ComponentScan(basePackages = "com.example.scandemo")
class ScanOnlyConfig {
}
```

Assume `com.example.scandemo` contains `@Service OrderService` and `@Component AuditSink` with valid dependencies. The scanner discovers them and registers definitions. Afterward, **the same post-processor system** still handles `@Autowired` injection and lifecycle callbacks on the created instances.

### Two Paths Leading to One Bean Creation Mechanism

```text
Path A:
@Component on class
     |
@ComponentScan right package
     |
BeanDefinition
     |
Container creates bean
     |
BeanPostProcessor: @Autowired, @PostConstruct, ...

Path B:
@Configuration + @Bean
     |
ConfigurationClassPostProcessor
     |
BeanDefinition
     |
Container creates bean
     |
BeanPostProcessor: @Autowired, @PostConstruct, ...
```

They differ in the **bean definition registration path**; the instance processing phase uses shared container infrastructure. Specific object instantiation mechanics can differ (container-selected constructor vs. factory method instantiating the object), so do not claim every annotation applies identically across all registration paths.

## 9. How Do BeanFactory and ApplicationContext Differ Here?

**`BeanFactory`** is the foundational interface for retrieving/managing beans; certain low-level implementations do not automatically register all annotation post-processors. **`ApplicationContext`** is the higher-level interface that normally detects and registers appropriate `BeanFactoryPostProcessor`s and `BeanPostProcessor`s during refresh.

`AnnotationConfigApplicationContext` is especially convenient for Java annotation configuration: it registers common annotation config processors upon initialization, which is why section 7's example works without manually declaring `@Bean` for `AutowiredAnnotationBeanPostProcessor`.

Distinguishing environments:

| Environment | Bean registration | Annotation processing |
| --- | --- | --- |
| `new AnnotationConfigApplicationContext(AppConfig.class)` | Reads configuration classes and `@Bean`; scans only if requested | Core annotation processors are pre-registered. |
| `new ClassPathXmlApplicationContext("beans.xml")` | Reads XML bean definitions | Typically declares `<context:annotation-config/>` or `<context:component-scan/>` to enable corresponding annotation processing in XML config. |
| Standalone `new DefaultListableBeanFactory()` | Definitions can be registered via API | Does not automatically equate to `AnnotationConfigApplicationContext`'s full annotation infrastructure; requires explicit setup. |
| Spring Boot application context | Auto-configuration, Java configuration, default component scanning by package setup | Boot usually wires needed infrastructure automatically, though each feature has its own activation conditions. |

This table describes typical behavior; custom configuration, modules/classpath, or extension points can alter it.

### 9.1. <context:annotation-config/> and <context:component-scan/> in XML

XML example of annotation processing for **already-declared** beans:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:annotation-config/>

    <bean id="formatter" class="com.example.Formatter"/>
    <bean id="reportService" class="com.example.ReportService"/>
</beans>
```

If `ReportService` has `@Autowired Formatter` and the right processor is present, the XML bean still gets injected. `<context:annotation-config/>` **does not perform component scanning**; it only registers post-processors for annotations on beans registered in the same context.

Conversely, XML:

```xml
<context:component-scan base-package="com.example"/>
```

enables scanning in the package and also **implicitly enables common annotation-config processors** by default. Therefore, in many XML configurations using `<context:component-scan/>`, adding a separate `<context:annotation-config/>` just for `@Autowired` is unnecessary.

**Important context scope:** post-processors normally take effect within the **specific context** where they are registered; in multi-context applications (root/child web contexts), do not assume processors in a child context automatically process beans in the parent.

## 10. How Does BeanDefinitionRegistryPostProcessor Differ from BeanPostProcessor?

### 10.1. Configuring Metadata Before Instance Creation

`ConfigurationClassPostProcessor` is a crucial infrastructure example capable of processing `@Configuration`, `@ComponentScan`, `@Bean`, and `@Import`, and registering related definitions/conditions. It runs **before most application bean creation**.

This explains why `@Bean` declarations in configuration classes are still read by Spring even without component scanning. The `ApplicationContext` already knows about the configuration class because you passed it to the constructor or registered it another way.

A custom `BeanFactoryPostProcessor` is typically used to inspect or modify `BeanDefinition`s prior to instantiation, not to modify already-instantiated objects:

```java
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetadataConfig {
    @Bean
    static BeanFactoryPostProcessor inspectDefinitions() {
        return beanFactory -> {
            if (beanFactory.containsBeanDefinition("exampleBean")) {
                var definition =
                        beanFactory.getBeanDefinition("exampleBean");
                System.out.println("scope=" + definition.getScope());
            }
        };
    }
}
```

This is an illustrative example, printing output only if an `exampleBean` definition exists. `getScope()` may return an empty string when the bean uses the default scope rather than literally printing `singleton`. For a `BeanFactoryPostProcessor` declared via `@Bean`, a `static` method avoids instantiating the configuration instance early.

### 10.2. Processing Instances When the Container Creates Beans

A custom `BeanPostProcessor` can observe beans registered from both component scanning and `@Bean`:

```java
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class TraceConfig {
    @Bean
    static BeanPostProcessor traceProcessor() {
        return new BeanPostProcessor() {
            @Override
            public Object postProcessAfterInitialization(
                    Object bean, String name) {
                if (name.equals("exampleBean")) {
                    System.out.println("initialized=" + name);
                }
                return bean;
            }
        };
    }
}
```

This snippet only triggers when a bean named `exampleBean` exists in the same context and the processor is registered early enough. `postProcessAfterInitialization` does not decide which classes the scanner picks; it receives the **Spring-created instance** and returns an object for the container to continue using.

**Early-initialization note:** A custom `BeanPostProcessor` is itself a special bean instantiated early. If it pulls in many application beans during its own initialization, those beans may miss full processing by other post-processors, especially auto-proxying. When declaring `@Bean` methods returning `BeanPostProcessor`/`BeanFactoryPostProcessor`, consider `static` and minimize dependencies per framework guidelines.

## 11. @Autowired, @PostConstruct, and the Bean Lifecycle

Simplified diagram for a typical singleton:

```text
BeanDefinition exists
        |
Container determines how to instantiate object
        |
Instantiate (constructor / factory method)
        |
Appropriate property/field/method injection
        |
BeanPostProcessor before initialization
        |
@PostConstruct and init callbacks per configuration/order
        |
BeanPostProcessor after initialization (may create proxy)
        |
Bean ready for use
        |
Context closes / scope ends with destruction support
        |
@PreDestroy, DisposableBean, corresponding destroy callbacks
```

This diagram is a learning model: `@PostConstruct` may be handled by a `BeanPostProcessor` in a phase preceding other init callbacks, and AOP/creation infrastructure has variations. Do not treat this diagram as an exact ordering contract for every extension point across all versions.

### 11.1. Dependency Injection in @Bean-Created Objects

Objects returned by `@Bean` factory methods still go through the container's normal property population and initialization steps. That explains examples having:

```java
@Bean
SomeService service() {
    return new SomeService();
}
```

while `SomeService` has an `@Autowired` field. If the field-injection processor is present, the field is processed after the factory method creates the object.

### 11.2. Constructor Injection Remains the Preferred Choice

The earlier example used field injection to showcase *instance annotation processing*. In production design, constructor injection makes required dependencies explicit and objects easier to test:

```java
@Service
public class CheckoutService {
    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public String checkout() {
        return gateway.pay();
    }
}
```

This is a structural example with `PaymentGateway` as a hypothetical business interface. For scanned classes with a single constructor, Spring can resolve dependencies when instantiating the bean. If created inside `@Bean` via `new CheckoutService(gateway)`, the factory method is responsible for supplying arguments; Spring does not replace the constructor call already executed.

### 11.3. Prototype Bean Note

Spring normally invokes initialization callbacks such as `@PostConstruct` for a prototype when creating it, yet after handing the prototype instance to the caller, the container does not manage full destruction the way it does for singletons. If a prototype holds resources, the caller must plan cleanup appropriately.

## 12. Not Every Annotation Is Handled by a BeanPostProcessor

This deeper distinction helps prevent rote misconceptions:

### 12.1. @Transactional Requires AOP and Transaction Management

A class annotated with `@Service` or created via `@Bean` can participate in transactions if transaction infrastructure is properly enabled, the annotation is recognized, and calls pass through the appropriate interceptor/proxy:

```java
@Service
public class MoneyTransferService {
    @org.springframework.transaction.annotation.Transactional
    public void transfer(long from, long to, long amount) {
        // Real business logic and persistence implemented here.
    }
}
```

This snippet illustrates a class; it is not a full program. `@Transactional` does not work merely because the scanner recognized `@Service` or because `@Bean` registered the class. You need a transaction manager, transaction attribute source/advisor/interceptor, and proper proxy/AspectJ conditions. In standard proxy mode, **self-invocation** (one method inside the same bean calling another method on `this`) bypasses the transaction proxy.

### 12.2. @RequestMapping Belongs to Web Infrastructure

A controller can be a valid Spring bean without having an HTTP endpoint:

```java
@Controller
class HelloController {
    @GetMapping("/hello")
    @ResponseBody
    String hello() {
        return "hello";
    }
}
```

This is a Web MVC snippet requiring annotation imports, a web application context, and corresponding servlet/handler mapping. Component scanning only puts the controller into the registry; Spring MVC's `RequestMappingHandlerMapping` must inspect the controller bean, discover mappings, and wire them to the dispatcher. A plain `AnnotationConfigApplicationContext` does not turn `@GetMapping` into an HTTP endpoint.

### 12.3. @Scheduled Requires Scheduling Infrastructure

`@Scheduled` on an existing bean will not run on a schedule without appropriate scheduling support. Typical configurations use `@EnableScheduling` (or equivalent infrastructure) to register the necessary processor. Registering the bean via scanning or `@Bean` is one thing; the scheduling processor is what detects schedules and executes them.

### 12.4. @Repository and Exception Translation

`@Repository` is a specialization of `@Component`, yet persistence exception translation behavior is not guaranteed by the marker alone. When `PersistenceExceptionTranslationPostProcessor` and matching `PersistenceExceptionTranslator`s are present, Spring can create appropriate interceptors/proxies and translate exceptions into the `DataAccessException` family. Some technologies like `JdbcTemplate` also have their own exception translation mechanism. Distinguish the marker, the post-processor, and the data-access technology.

**General rule:** to know whether an annotation takes effect, always determine **who reads that annotation**, **when it reads it**, and **what infrastructure conditions are required**.

## 13. Comparison Table for Debugging

| Question | Component scanning | Annotation processing on beans |
| --- | --- | --- |
| What problem does it answer? | Which classes get bean definitions automatically registered? | How are registered bean instances/metadata configured and operated? |
| Core inputs | Classpath, base packages, metadata, include/exclude filters | Container-managed bean definitions/instances, annotations on classes/fields/methods |
| Typical mechanisms | `@ComponentScan`, `ClassPathBeanDefinitionScanner` | `AutowiredAnnotationBeanPostProcessor`, `CommonAnnotationBeanPostProcessor`, and other built-in processors |
| Typical phase | Before bean creation, during definition registration | During bean creation or runtime infrastructure processing |
| Output | `BeanDefinition` plus name/scope metadata | Dependencies injected, callbacks invoked, proxies/behaviors attached |
| Do they require each other? | No; scanning creates definitions without replacing BPPs | No; BPPs process beans from `@Bean`, XML, and other registration paths |
| Applies to objects created by `new` outside container? | No | Not automatically |
| Are all annotations processed in one place? | No | No; involves BFPPs, BPPs, and web/AOP/runtime infrastructure |

### Scenario Matrix

| Scenario | Bean exists? | Can `@Autowired` / `@PostConstruct` run? |
| --- | --- | --- |
| `@Component` in an unscanned package, not otherwise registered | No | No |
| `@Component` properly scanned and registered, annotation processors active | Yes | Yes |
| Class without `@Component`, registered via `@Bean`, processors active | Yes | Yes |
| Class with `@Component`, registered via `@Bean`, scan disabled | Yes | Yes |
| Class registered via XML, corresponding processors declared | Yes | Yes |
| Object instantiated via `new` in business code without handing to container | Not a Spring bean | Not automatically |
| Bean in context, but corresponding annotation processor missing | Yes | Some annotations may go unprocessed |
| Controller bean has `@GetMapping` without Spring MVC infrastructure | Yes | No HTTP endpoint from controller bean alone |

The word "Can" in the last column emphasizes that **the right post-processors must be present** along with valid dependencies/callbacks; it does not guarantee every bean always processes cleanly.

## 14. Common Misconceptions

### 14.1. "@Autowired only works on scanned classes"

False. `@Autowired` is processed on Spring-managed beans if the processor is registered; beans can come from `@Bean` or XML. The runnable example proved this case.

### 14.2. "Class has @Component but getBean cannot find it, so @Component is broken"

Not necessarily. Check scan packages, include/exclude filters, profiles/conditions, whether the configuration was loaded, bean names, and registration errors. If the class lies outside the scan region and is not registered elsewhere, its absence is expected.

### 14.3. "Enabling @ComponentScan makes all annotations work"

False. Component scanning registers beans and in many contexts also enables core processors, yet annotations like `@Transactional`, `@Cacheable`, `@Async`, `@Scheduled`, or `@RequestMapping` require dedicated infrastructure.

### 14.4. "Adding @PostConstruct to an object created with new will invoke the callback"

False. If code creates an object manually outside the container, annotations do not execute automatically. Let the container manage the instance or invoke application-controlled initialization logic manually; do not expect Spring callbacks.

### 14.5. "@Bean ignores all annotations on the returned class"

False. Objects returned by `@Bean` are processed as Spring-managed beans, including standard post-processors. However, constructor invocation already happened inside the factory method, so do not assume Spring chooses an `@Autowired` constructor instead of that method's `new` call.

### 14.6. "BeanFactoryPostProcessor and BeanPostProcessor are the same"

False. `BeanFactoryPostProcessor` processes **metadata/definitions** before regular bean creation; `BeanPostProcessor` processes **instances** during the initialization cycle. Triggering bean creation too early inside a BFPP can bypass some BPPs.

### 14.7. "Once @Service is scanned, @Transactional definitely works"

False. Transactions require a transaction manager and appropriate AOP/interceptors. Having a bean does not mean transaction boundaries exist. Self-invocation can also bypass proxies in standard mode.

### 14.8. "A BeanPostProcessor processes every object in the JVM"

False. Processors are registered per **specific container** and apply to beans managed by that container. Manually created objects or beans in another context are not automatically processed by it.

### 14.9. "If @ComponentScan excludes a class, @Bean cannot instantiate that class"

False. Exclude filters only block one discovery path. `@Bean` or another configuration can still register that class.

### 14.10. "@PostConstruct and @PreDestroy always run on the same schedule across all scopes"

Incorrect. Initialization callbacks for prototypes can run when beans are created, but the container does not manage full destruction the way it does for singletons. Contexts that are not closed properly can also prevent destruction callbacks from running as expected.

## 15. Layered Diagnostic Methodology

When an annotation appears "not to work", do not fix it by adding `@ComponentScan` to every configuration. Separate three questions in order.

### 15.1. Layer 1: Does the Bean Definition Exist?

In an `AnnotationConfigApplicationContext` or a context with matching APIs:

```java
System.out.println(context.containsBeanDefinition("manualService"));
System.out.println(context.containsBean("manualService"));
```

This snippet relies on the `context` variable from section 7. `containsBeanDefinition` checks **definitions directly in the current factory**, whereas `containsBean` can reflect available beans and in some setups search parent factories. When investigating hierarchical contexts, understand this distinction.

If the bean does not exist, inspect registration paths: `@ComponentScan`, `@Bean`, `@Import`, XML, profiles, or filters. **Do not debug field injection when the class is not even a bean yet.**

### 15.2. Layer 2: Was the Instance Processed?

If the bean exists yet an `@Autowired` field is `null`, check:

- Was the object actually obtained from the container, or did the caller `new` a separate instance?
- Does the context have `AutowiredAnnotationBeanPostProcessor` registered?
- Is field/method injection valid, does the dependency bean exist, and is there a unique candidate?
- Was the bean instantiated early before post-processors were ready?
- In `@Bean` cases, what was constructed by the factory method versus what is handled by post-processors?

For `@PostConstruct` callbacks, verify that the Jakarta Annotation API and `CommonAnnotationBeanPostProcessor` are present and that callback signature/lifecycle rules are satisfied.

### 15.3. Layer 3: Is Dedicated Infrastructure Enabled?

If `@Transactional` is not working, check the transaction manager, transaction advisor, proxies, and call paths. If `@GetMapping` has no route, check the web application context and handler mappings. If `@Scheduled` does not run, check scheduling infrastructure. These are not component scan errors if the bean is already registered and visible in the context.

### 15.4. Inspecting Bean Definitions to Trace Registration Path

```java
var factory = context.getBeanFactory();
var definition = factory.getBeanDefinition("manualService");

System.out.println(definition.getFactoryMethodName());
System.out.println(definition.getResourceDescription());
```

Place this snippet within the scope of `context` from section 7. For beans defined via `@Bean`, `getFactoryMethodName()` normally returns `manualService`. `getResourceDescription()` can describe the class/configuration source; exact output varies by registration method, so do not assert fixed stdout text across all environments.

For component-scanned beans, the bean definition usually references the candidate's class source/resource rather than a `@Bean` factory method. Combine this information with the registered post-processor list to see why an annotation is or is not processed.

## 16. Tests to Confirm the Difference

### 16.1. Testing Registration

Build the context with only `Config` from section 7:

- `containsBean("manualService")` must be `true`.
- `containsBean("unscannedComponent")` must be `false`.

This tests the **registration path**. It is not enough to prove injection or lifecycle callbacks ran.

### 16.2. Testing Injection and Lifecycle

Use the bean from the context:

```java
var service = context.getBean(AnnotationProcessingDemo.ManualService.class);
String result = service.work("hello");
if (!"HELLO".equals(result)) {
    throw new AssertionError("Annotation injection failed: " + result);
}
```

This snippet builds on `context` from the full program; it proves the `Formatter` dependency was ready when `work` ran. JUnit assertions can be used in projects with test dependencies. To test `@PostConstruct` and `@PreDestroy` automatically, record callbacks in a recorder/test fixture and assert before/after closing the context, avoiding tests tightly coupled to stdout.

### 16.3. Testing with Two Separate Contexts

You can create two fixtures:

- **Fixture A:** `@Bean` only, no `@ComponentScan`; assert beans are registered and annotations processed.
- **Fixture B:** configure `@ComponentScan` on one package containing stereotypes; assert the scanner registers the matching classes and post-processors process them.

To test the effect of missing processors, use a low-level `BeanFactory` with explicit registrations. However, do not assume an `AnnotationConfigApplicationContext` without component scan also disables `AutowiredAnnotationBeanPostProcessor`: the two are independent.

### 16.4. Testing Proxy Behavior

When testing `@Transactional` or `@Async`, `containsBean` returning `true` and injection working do not prove interceptors/async are active. Test observable transaction/async behavior and ensure calls go through the Spring-managed proxy or appropriate mode.

## 17. Scenario Exercises

**Scenario 1.** Class `EmailSender` has `@Component` yet lies outside all scanned base packages. Another `@Bean` method in configuration returns `new EmailSender()`. Does the class become a bean?

**Answer:** Yes, if the configuration containing `@Bean` is processed and bean creation succeeds. It comes from the factory method; `@Component` is not the direct cause.

**Scenario 2.** `EmailSender` above has an `@Autowired Client client` field. Does having or lacking component scan determine injection?

**Answer:** Not directly. If `EmailSender` is a Spring-managed bean and `AutowiredAnnotationBeanPostProcessor` is active, field injection can still happen. The `Client` dependency must have a matching bean.

**Scenario 3.** A `@Service` class is scanned into a bean, yet its `@Scheduled` method never runs. Where should you check first?

**Answer:** Scheduling infrastructure: `@EnableScheduling`/the corresponding processor, scheduler configuration, and valid method signature; component scanning has already done its job if the bean exists.

**Scenario 4.** A developer adds `@PostConstruct` to an object manually created with `new` inside a service method. Will the callback run automatically?

**Answer:** No. This is an instance outside the container's bean lifecycle. Putting annotations on a class does not make Spring automatically process that object.

**Scenario 5.** A `@Controller` is instantiated as a bean by Spring, yet `GET /hello` returns 404. Is the bug necessarily in component scanning?

**Answer:** No. Check the web stack, handler mappings, mapping annotations, HTTP method/path, and which context holds the controller. Having the bean only proves registration/creation, not routing.

**Scenario 6.** `@Autowired` does not work on an object returned by a `@Bean` factory method. What factors should be checked?

**Answer:** Whether the processor is registered, whether the received object is the container-managed instance, whether injection metadata is valid, whether dependencies can be resolved, or whether the bean was instantiated early before BPPs were fully active.

**Scenario 7.** `@Bean SomeService service() { return new SomeService(); }` creates a bean, while `SomeService` has constructor `@Autowired SomeService(A a)` and no no-arg constructor. Does Spring automatically rewrite the `new SomeService()` statement?

**Answer:** No. Java statements inside a factory method must compile; Spring does not replace constructor calls inside methods. You can declare `@Bean SomeService service(A a) { return new SomeService(a); }` so the container resolves `A` and passes it to the factory method.

**Scenario 8.** A `BeanFactoryPostProcessor` calls `getBean()` to fetch a service too early, and subsequently the service misses AOP auto-proxying. Why?

**Answer:** Because the bean was instantiated before full registration of `BeanPostProcessor`s/auto-proxy creators, leaving it ineligible for processing. BFPPs should primarily manipulate metadata rather than requesting business bean instances early.

## 18. Knowledge and Practice Checklist

When seeing an annotation in Spring, answer in order:

1. **Are we talking about a class or a bean instance?** Presence on the classpath does not mean a bean definition is registered.
2. **Through which path was the bean registered?** `@ComponentScan`, `@Bean`, XML, `@Import`, or another mechanism?
3. **Which processor is responsible?** Configuration parser/registry processor, autowiring/lifecycle BPP, AOP advisor, MVC handler mapping, or scheduler?
4. **When does the processor act?** Before bean creation, during injection/initialization, or during runtime requests/method calls?
5. **What condition might be missing?** Package scan, post-processor, dependency bean, transaction manager, web infrastructure, scope, proxy path, or lifecycle callback?
6. **Is there observable evidence?** Bean definition exists, field injected, callback ran, proxy executed, request mapping worked, or transaction actually rolled back?
7. **Is there another registration path?** Excluding from component scan does not exclude from `@Bean`/`@Import`.

## 19. Official References

- [Spring Framework 6.2 — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config.html): fundamentals of annotation injection, `AutowiredAnnotationBeanPostProcessor`, `CommonAnnotationBeanPostProcessor`, and `<context:annotation-config/>`.
- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): candidate class discovery, stereotypes, bean definition registration, and `@ComponentScan`.
- [Spring Framework 6.2 — Container Extension Points](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): distinguishing `BeanFactoryPostProcessor` and `BeanPostProcessor`, execution timing, and early initialization notes.
- [Spring Framework 6.2 — Using @PostConstruct and @PreDestroy](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html): lifecycle callback conditions and `CommonAnnotationBeanPostProcessor`.
- [Spring Framework — Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): bean definitions and metadata.
- [Spring Framework 6.2 — ConfigurationClassPostProcessor API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/ConfigurationClassPostProcessor.html): registering and processing configuration class metadata.

**Key takeaway:** **Component scanning** answers "Which classes does Spring automatically discover and register as beans?". **Annotation processing** answers "Once a bean exists, what metadata does Spring infrastructure read and what does it do with that bean?". A bean from `@Bean` still receives injection/lifecycle processing, whereas a class with `@Component` outside all registration paths is still not a Spring bean.
