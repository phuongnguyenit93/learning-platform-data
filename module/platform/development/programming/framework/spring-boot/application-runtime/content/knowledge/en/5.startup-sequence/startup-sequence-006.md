# Loading Bean Definition Sources Before Refresh — Spring Boot 3.3

## 1. Lesson Objectives

In the Spring Boot startup sequence, `SpringApplication` needs to load **initial configuration sources** into `ApplicationContext` before calling `refresh()`. These sources tell Spring which configuration classes to analyze in order to continue discovering `@Component` classes and processing `@Bean`, `@Import`, and auto-configuration.

After this lesson, you should be able to:

- Distinguish **configuration source**, **BeanDefinition**, and **bean instance**.
- Explain the position of the `SpringApplication.load(context, sources)` step in the startup process.
- Understand why `@SpringBootApplication` is loaded before refresh, whereas a `@Service` may only be discovered during refresh.
- Know how to pass additional sources, register definitions in the pre-refresh phase, and observe results safely.
- Run a Java 21 / Spring Boot 3.3 example; recognize errors caused by missing sources, wrong package scanning, configuration conditions, or bean creation failures.

**Key takeaway:** loading sources before refresh **does not mean all beans already exist**. The loading step puts root definitions into the registry; parsing annotations, discovering components, and creating instances are still performed by Spring during the refresh phase.

## 2. Distinguishing Sources, Definitions, and Objects

| Concept | Description | Example |
| --- | --- | --- |
| **Source** | Input used to load configuration | `App.class`, `ExtraConfiguration.class` |
| **BeanDefinition** | Metadata describing how Spring creates/manages a bean: name, type, scope, factory method, lazy, dependencies... | Definition named `greetingService` |
| **Bean instance** | Actual Java object already instantiated and managed by the container | Instance of `GreetingService` |
| **BeanDefinitionRegistry** | Component allowing registration and lookup of bean definitions | Registry of the appropriate `ApplicationContext` |
| **ApplicationContext** | Spring container managing definitions, instances, environment, and lifecycle | Context of a non-web or web application |

There are three distinct steps:

1. **Declaring the source:** `new SpringApplication(App.class)` specifies the root configuration class.
2. **Registering the BeanDefinition:** while preparing the context and processing configuration, Spring learns how to create beans.
3. **Instantiating the bean:** during refresh (for ordinary non-lazy singletons), Spring invokes factories/constructors, injects dependencies, and runs necessary callbacks.

A BeanDefinition can already exist even when the bean has not been created yet. For a `@Lazy` bean, the instance may only be initialized when requested later. Conversely, the mere existence of a `@Component`-annotated class in source code does not prove Spring has found it: it must also be within scan scope or registered via another mechanism.

Example:

```java
@SpringBootApplication
class DemoApplication { }

@Service
class GreetingService { }
```

`DemoApplication.class` is the source; `GreetingService.class` is a component to be discovered via `@ComponentScan`. Spring Boot can load the definition of `DemoApplication` before refresh, while the definition for `GreetingService` is registered when configuration processing runs during refresh.

## 3. Order of Related Steps in SpringApplication

The following diagram is the **conceptual** sequence for a successful startup on Spring Boot 3.3:

```text
main(args)
  |
  +-- new SpringApplication(DemoApplication.class)
  |     +-- Record primary source(s)
  |
  +-- application.run(args)
        |
        +-- ApplicationStartingEvent
        +-- Prepare Environment, profiles, external configuration
        +-- ApplicationEnvironmentPreparedEvent
        +-- Create ApplicationContext
        |
        +-- prepareContext(...)
        |     +-- Attach Environment to context
        |     +-- Run ApplicationContextInitializer
        |     +-- ApplicationContextInitializedEvent
        |     +-- Register initial infrastructure beans
        |     +-- load(context, sources)          <-- LOAD PRIMARY SOURCES
        |     +-- ApplicationPreparedEvent
        |
        +-- refreshContext(context)
        |     +-- BeanDefinitionRegistryPostProcessor
        |     |     +-- ConfigurationClassPostProcessor
        |     |           +-- Process @Configuration, @ComponentScan
        |     |           +-- Process @Import, @Bean, auto-configuration
        |     +-- BeanFactoryPostProcessor
        |     +-- Register BeanPostProcessor
        |     +-- Instantiate ordinary non-lazy singletons
        |     +-- Complete refresh
        |
        +-- ApplicationStartedEvent
        +-- Run ApplicationRunner / CommandLineRunner
        +-- ApplicationReadyEvent
```

The sequence above omits some internal callbacks, yet reflects the boundaries you need to know:

- `ApplicationContextInitializer.initialize(context)` runs when the context **has been created but not refreshed, and before primary sources are loaded**. At this point you cannot assume definitions from the primary source already exist.
- `SpringApplication.load(context, sources)` loads the **primary sources** into the registry, typically via the annotated-class mechanism. This step belongs to `prepareContext(...)`.
- `ApplicationPreparedEvent` is published **after loading sources and before refresh**. This is the appropriate observation point if you want to confirm primary sources have been registered.
- `refreshContext(context)` triggers processing of configuration classes, component scanning, bean factory post-processors, ordinary singleton instantiation, and the remaining lifecycle steps.
- `ApplicationStartedEvent` arrives after the context refreshes; `ApplicationReadyEvent` arrives after runners have been invoked.

**Do not confuse `ApplicationContextInitializedEvent` with `ApplicationPreparedEvent`.** The first event happens after initializers but before loading primary sources. The second event happens once sources have been loaded and the context is about to refresh.

## 4. Which Sources Does Spring Boot Load?

### 4.1. The Startup Class Is the Primary Source

An application typically writes:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`DemoApplication.class` is the **primary source**. The `@SpringBootApplication` annotation combines `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`.

Loading the source does not mean Spring has immediately executed every annotation. During refresh, `ConfigurationClassPostProcessor` processes Java configuration and registers derived definitions, including component scan results and `@Bean` methods.

### 4.2. Passing Multiple Primary Sources

Additional configuration classes can be passed directly:

```java
SpringApplication application = new SpringApplication(
        DemoApplication.class,
        ExtraConfiguration.class);
application.run(args);
```

This is an **illustrative snippet**, assuming the two classes above exist. Spring Boot accepts both as sources. If `ExtraConfiguration` has `@Configuration`, the configuration class's definition can already be present at the prepared milestone; `@Bean` methods inside it are still processed during refresh.

Besides classes, Spring Boot's loading mechanism supports certain appropriate source forms such as package names and configuration resources. However, in Boot 3.3 projects using Java configuration, explicit configuration classes together with `@Import`/`@ComponentScan` are usually easier to control.

### 4.3. Definitions Derived From Sources

- **`@ComponentScan`:** finds classes annotated with `@Component`, `@Service`, `@Repository`, `@Controller` within the configured scope, then registers their BeanDefinitions.
- **`@Import`:** brings additional configuration classes or other imported components into the analysis process.
- **`@Bean`:** marks a factory method creating a bean; the bean definition is registered during configuration processing.
- **`@EnableAutoConfiguration`:** activates conditional auto-configurations based on classpath, properties, profiles, and existing beans.
- **`@Conditional` and `@Profile`:** may cause certain definitions not to be registered even though the configuration source was loaded.

Therefore, never deduce that an `ApplicationPreparedEvent` listener will see all services, repositories, or auto-configured beans. Many of them are only processed later during refresh.

## 5. Hands-on Project: Java 21 + Spring Boot 3.3

The following application runs in **non-web** mode to focus on bootstrap. It inspects three milestones: an initializer before source load, a prepared listener after source load, and a runner after refresh.

### 5.1. File Structure

```text
bean-source-demo/
├── pom.xml
└── src/main/java/com/example/startup/
    ├── BeanSourceApplication.java
    └── GreetingService.java
```

### 5.2. Maven pom.xml

File `pom.xml`:

```xml
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

    <groupId>com.example</groupId>
    <artifactId>bean-source-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
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

Spring Boot 3.3 requires at least Java 17; here the configuration uses JDK 21. `spring-boot-starter` contains the core components and does not require adding a web starter for a CLI example.

### 5.3. Service Scanned During Refresh

File `src/main/java/com/example/startup/GreetingService.java`:

```java
package com.example.startup;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String message() {
        return "Hello from service";
    }
}
```

Spring finds this class via `@SpringBootApplication`'s default component scan when refresh processes configuration. Simply having the `@Service` annotation in a Java file does not cause the bean to be created immediately when the program starts.

### 5.4. Main Class With Three Observation Points

File `src/main/java/com/example/startup/BeanSourceApplication.java`:

```java
package com.example.startup;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BeanSourceApplication {

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(BeanSourceApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        // Context exists, primary source not yet loaded.
        application.addInitializers(context -> {
            boolean present = context.containsBeanDefinition("beanSourceApplication");
            System.out.println("1. initializer: source definition = " + present);
        });

        // After loading primary source, before refresh.
        application.addListeners(
                (ApplicationListener<ApplicationPreparedEvent>) event -> {
                    var context = event.getApplicationContext();

                    boolean source = context.containsBeanDefinition("beanSourceApplication");
                    boolean service = context.containsBeanDefinition("greetingService");

                    System.out.println("2. prepared: source definition = " + source);
                    System.out.println("3. prepared: service definition = " + service);
                });

        application.run(args);
    }

    @Bean
    ApplicationRunner inspectAfterRefresh(
            ApplicationContext context,
            GreetingService service) {

        return args -> {
            System.out.println("4. runner: service available = "
                    + context.containsBean("greetingService"));
            System.out.println("5. runner: " + service.message());
        };
    }
}
```

**Explaining each observation point:**

1. `new SpringApplication(BeanSourceApplication.class)` records the source but has not created the context yet.
2. The initializer runs before `load(context, sources)`, so `containsBeanDefinition("beanSourceApplication")` returns `false`.
3. When `ApplicationPreparedEvent` fires, Boot has already registered the definition for the main class, under the default name `beanSourceApplication`. Hence the result is `true`.
4. Component scanning is processed during refresh. At the prepared event, `greetingService` has not yet been discovered from the `@Service` annotation, so `containsBeanDefinition("greetingService")` is `false`.
5. After refresh, Spring has processed the service and the `@Bean inspectAfterRefresh` method; the runner is injected with `GreetingService` and executes after `ApplicationStartedEvent`.

`containsBeanDefinition(...)` checks **definition metadata**. `containsBean(...)` indicates that the bean name is present in the container, which does not mean every `@Lazy` bean has already been instantiated. Do not call `getBean(GreetingService.class)` inside an initializer or prepared listener to force the bean to appear early; the context has not finished refreshing yet.

### 5.5. Compiling, Running, and Inspecting Stdout

In the `bean-source-demo` directory, using JDK 21 and Maven:

```bash
java -version
mvn -version
mvn spring-boot:run
```

The five lines explicitly printed by the example code have this order and content:

```text
1. initializer: source definition = false
2. prepared: source definition = true
3. prepared: service definition = false
4. runner: service available = true
5. runner: Hello from service
```

The real console also includes the Spring Boot banner and logging, so other lines may interleave. The output above shows **only the `System.out.println` lines**, not the entirety of stdout.

Package and run the JAR:

```bash
mvn package
java -jar target/bean-source-demo-0.0.1-SNAPSHOT.jar
```

Because `WebApplicationType.NONE` was selected, the application does not open an HTTP port. Once the runner finishes and no other non-daemon threads keep the JVM alive, the process exits.

### 5.6. Experiment: Source Class Outside Component Scan

Create a configuration in package `com.example.extra`, outside the default scan scope of `com.example.startup`.

File `src/main/java/com/example/extra/FeatureConfiguration.java`:

```java
package com.example.extra;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    public String featureMessage() {
        return "Feature from extra source";
    }
}
```

Replace the application creation line in `BeanSourceApplication.main()` with:

```java
// Requires importing com.example.extra.FeatureConfiguration.
SpringApplication application = new SpringApplication(
        BeanSourceApplication.class,
        FeatureConfiguration.class);
```

This is a **replacement snippet inside the main class**, not a standalone program. Because `FeatureConfiguration.class` is passed directly as a source, the class's definition is present after `load(context, sources)` even though it lies outside the scanned package.

Inside the prepared listener, you can add:

```java
System.out.println("prepared: feature config = "
        + context.containsBeanDefinition("featureConfiguration"));
System.out.println("prepared: featureMessage = "
        + context.containsBeanDefinition("featureMessage"));
```

Expect `true` for the source class and `false` for the bean from the `@Bean` method at the prepared milestone. When refresh processes configuration, the definition for `featureMessage` is added and the bean can be created per the lifecycle.

## 6. Additional Mechanisms: Before Refresh and During Refresh

### 6.1. Common Approach: `@Configuration` and `@Bean`

In most projects, use `@Configuration`, `@Bean`, `@Import`, and `@ComponentScan` so Spring manages dependencies and lifecycle clearly. Example of a bean from the standard Java library:

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ClockConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

This is an **additional class that must reside in the Spring project** and an appropriate or imported package; it is not a standalone Java program. Spring registers the definition for `clock` when processing configuration during refresh.

### 6.2. Programmatic BeanDefinition in an Initializer

For infrastructure that needs to prepare a definition very early, you can use `ApplicationContextInitializer` with `BeanDefinitionRegistry`.

Example **snippet added in `main`** after creating `application` and before `application.run(args)`:

```java
// Imports placed at top of file:
// import java.time.Clock;
// import org.springframework.beans.factory.support.BeanDefinitionBuilder;
// import org.springframework.beans.factory.support.BeanDefinitionRegistry;

application.addInitializers(context -> {
    if (!(context instanceof BeanDefinitionRegistry registry)) {
        throw new IllegalStateException("No BeanDefinitionRegistry");
    }

    registry.registerBeanDefinition(
            "bootClock",
            BeanDefinitionBuilder.genericBeanDefinition(
                    Clock.class, Clock::systemUTC).getBeanDefinition());
});
```

This snippet **does not compile standalone**; it requires the listed imports, Spring dependencies, and the `application` variable from `main`. In standard Spring Boot contexts, the registry is available. With custom contexts, check the interface first as shown in the example. The `bootClock` definition is placed in the registry before refresh; during refresh Spring can use the `Clock::systemUTC` supplier to create the instance.

**Prefer `@Bean Clock clock()` unless a low-level hook is needed.** Dynamic registration makes code harder to inspect and risks bean name collisions.

### 6.3. Distinguishing the Post-Processors

| Mechanism | Timing | Effect |
| --- | --- | --- |
| `ApplicationContextInitializer` | Before loading primary sources, before refresh | Customizes context, can register initial metadata |
| `SpringApplication.load(...)` | After initializers, before refresh | Loads primary sources into registry |
| `BeanDefinitionRegistryPostProcessor` | During refresh | Adds or modifies bean definitions before bean creation |
| `ConfigurationClassPostProcessor` | During refresh; is a registry post-processor | Parses configuration, scan, import, `@Bean` |
| `BeanFactoryPostProcessor` | During refresh, before ordinary singleton instantiation | Modifies BeanFactory metadata/configuration |
| `BeanPostProcessor` | When creating bean instances | Intercepts initialization, supports mechanisms like proxies |

Do not call `context.refresh()` yourself inside an initializer or prepared event: `SpringApplication` owns the bootstrap sequence. Also do not use `BeanPostProcessor` as a tool to load primary sources, because it operates at the bean-instance stage.

## 7. Common Troubleshooting

| Symptom | Common cause | Where to investigate |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Bean not registered, package not scanned, `@Profile`/`@Conditional` condition not met | Check primary sources, packages, `@Import`, config, and conditions |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type to inject | Use `@Qualifier`, `@Primary`, or redesign interfaces |
| `BeanDefinitionOverrideException` | Multiple definitions sharing a name when overriding is disallowed | Find duplicate registration, rename, or remove duplicate source |
| `BeanCreationException` | Definition exists, but constructor, injection, or factory method fails | Read `Caused by` in the stack trace |
| `ClassNotFoundException` / `NoClassDefFoundError` | Missing dependency or incompatible library version | Check Maven dependency tree/BOM, check Java version |
| `@Service` not yet seen at prepared event | Component scan has not been processed because refresh has not happened | Observe after refresh instead of forcing early bean creation |
| `@Bean` method does not run immediately | Bean is lazy or only its definition exists, instance not yet requested | Distinguish definition registration from instance creation |
| Auto-configuration missing a bean | `@ConditionalOnClass`, `@ConditionalOnMissingBean`, or properties do not match | Inspect condition evaluation report, try `--debug` |
| Initializer calls `getBean` and fails | Context not yet refreshed, dependency graph incomplete | Move work requiring beans to a runner/bean lifecycle |

For systematic debugging:

1. Check the class passed to `SpringApplication.run(...)` or the `SpringApplication` constructor.
2. Check the package of the main class relative to `@Component`/`@Service` classes.
3. Check `@Configuration`, `@Import`, `@Bean`, profiles, and conditional annotations.
4. Identify the timing you are observing: initializer, prepared event, during refresh, or runner.
5. Read the root cause (`Caused by`) of the error; do not add random annotations or dependencies.
6. For auto-configuration, use `--debug` to see matching and non-matching conditions.
7. If encountering legacy libraries, verify compatibility with Spring Framework 6 / Boot 3 and the Jakarta namespace where applicable.

### About Bean Overriding

Spring Boot by default prevents overriding bean definitions with duplicate names. The property `spring.main.allow-bean-definition-overriding` can change this, but should not be enabled just to mask duplicate configurations. Fix the registration source properly.

### About Lazy Initialization

`@Lazy` affects the timing of **instance creation**, and does not mean the definition has not been registered. `containsBeanDefinition("someBean")` can return `true` while the constructor has never run.

### About Sources Outside Packages

If a class lies outside the scan scope, simply renaming a package or adding a dependency is not enough. Specify a valid registration path: import the configuration, pass an additional primary source, or intentionally reconfigure the scan scope.

## 8. Review Exercises

1. Explain source, BeanDefinition, and instance using the `GreetingService` example.
2. Why does the initializer see `beanSourceApplication = false`, while the prepared listener sees `true`?
3. Why does `greetingService` not yet appear in the prepared event? Which Spring component will find it?
4. Remove `@Service` from `GreetingService`, re-run, and identify the error; fix it using `@Bean` configuration.
5. Move the service outside the `com.example.startup` package and explain why it is not scanned.
6. Add `FeatureConfiguration` as a primary source and compare when the class definition and `@Bean featureMessage` appear.
7. Distinguish `ApplicationContextInitializer` from `BeanDefinitionRegistryPostProcessor` and `BeanPostProcessor`.
8. Why can calling `context.getBean(...)` or manually calling `refresh()` from an initializer cause errors?
9. Explain a scenario where a BeanDefinition exists but the instance has not yet been created.
10. Redraw the sequence `source -> load -> prepared -> refresh -> started -> runners -> ready` and mark where `@ComponentScan` is processed.

**Pass criteria:** you can run the Maven example yourself producing the five output lines in the exact order, understand why the booleans are `false`, `true`, `false`, `true` respectively, and clearly distinguish **loading initial sources before refresh** from **parsing configuration and creating beans during refresh**.

## 9. Official References

- Spring Boot 3.3 — SpringApplication: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — SpringApplication API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework — Java-based Container Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
- Spring Framework — BeanFactory Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework — Classpath Scanning: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
