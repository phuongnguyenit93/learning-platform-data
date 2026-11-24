# DeferredImportSelector and Why Spring Boot Defers Auto-Configuration Processing

## 1. Lesson Objectives

Spring Boot can register default beans automatically via **auto-configuration** classes, yet it often must give priority to choices declared by the application itself. The `DeferredImportSelector` mechanism is a key piece that makes this possible: it allows selecting and processing imported configurations to occur **after ordinary `@Configuration` classes are processed** during Spring's configuration parsing.

After this lesson, you will be able to:

- Distinguish `@Import` of a configuration class, `ImportSelector`, and `DeferredImportSelector`.
- Explain the path from `@SpringBootApplication`/`@EnableAutoConfiguration` to `AutoConfigurationImportSelector` and the candidate auto-configuration list.
- Understand why deferral is needed: **bean definitions supplied by the application must have a chance to be registered before auto-configuration evaluates bean-based conditions**, especially `@ConditionalOnMissingBean`.
- Distinguish **import selection**, **condition evaluation**, **bean definition registration**, and **bean instantiation**; "deferred" does not mean running asynchronously, running after the application is ready, or instantiating beans lazily.
- Write an auto-configuration with Java 17+ and verify "back off" behavior with concrete execution commands.

Context: this lesson covers **activating auto-configuration** in Spring Boot, focusing on the purpose of the deferred import mechanism. Classpath, property, or bean conditions are mentioned only as needed to clarify why import selection must follow the right order.

## 2. From @Import to DeferredImportSelector

Spring Framework supports the `@Import` annotation to bring additional configurations into configuration class processing. Three cases should be distinguished:

| Form | What Does Spring Do? | When Is It Useful? |
| --- | --- | --- |
| `@Import(AdditionalConfig.class)` | Imports a directly specified configuration class. | You already know the exact class to include. |
| `@Import(CustomImportSelector.class)`, where selector implements `ImportSelector` | Calls the selector to choose a list of class names to import. | The import list depends on annotation metadata or selection logic. |
| `@Import(CustomDeferredSelector.class)`, where selector implements `DeferredImportSelector` | Records the selector and processes import selection in the **deferred phase** after ordinary configurations have been parsed. | Imports depend on conditions or must be evaluated after application-declared configurations. |

Illustrative example of a regular `ImportSelector`:

~~~java
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class BasicImportSelector implements ImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] {"com.example.config.ExtraConfiguration"};
    }
}
~~~

This is only an **API illustration class**, not a self-running program: `ExtraConfiguration` must actually exist and a configuration class must import the selector via `@Import(BasicImportSelector.class)`. The key point is that `selectImports(...)` returns **configuration class names**; it does not directly return bean objects, invoke bean constructors, or start the context itself.

`DeferredImportSelector` is a variant of `ImportSelector`:

~~~java
import org.springframework.context.annotation.DeferredImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class DelayedImportSelector implements DeferredImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] {"com.example.config.ExtraConfiguration"};
    }
}
~~~

With the illustrative classes above, the timing difference is: Spring does not process the import list of `DelayedImportSelector` immediately upon encountering the annotation as it would for a regular selector; it **collects the selector to process later during configuration class parsing**. The API also supports `Ordered`/`@Order` to control order among deferred selectors, and `getImportGroup()` to group results before emitting the final import list.

The phrase "deferred processing after `@Configuration` classes" must be understood in proper scope: it is **a phase within configuration metadata and bean definition processing of the current refresh**, not waiting until `ApplicationReadyEvent` or after `ApplicationRunner`.

## 3. Where Does AutoConfigurationImportSelector Fit?

In Spring Boot, `@SpringBootApplication` includes enabling auto-configuration through `@EnableAutoConfiguration`. Conceptual path:

~~~text
@SpringBootApplication
  └── @EnableAutoConfiguration
        └── @Import(AutoConfigurationImportSelector.class)
              └── implements DeferredImportSelector
                    └── select/group/order auto-configurations
                          └── import eligible @AutoConfiguration classes
                                └── evaluate @Conditional on class / @Bean
                                      └── register matching bean definitions
~~~

`AutoConfigurationImportSelector` is a Spring Boot infrastructure class implementing `DeferredImportSelector` along with callbacks such as `EnvironmentAware` and `BeanFactoryAware`. It reads exclusion options and discovers candidate auto-configuration classes. With Spring Boot 3.x, candidates are published by libraries via the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each valid line in this resource specifies the fully qualified name of an auto-configuration class, for example:

~~~text
com.example.autoconfig.GreeterAutoConfiguration
~~~

This is a **metadata file name inside a JAR/classpath**, not a bean, not an application.properties file, and not a `@ComponentScan`. A dependency can contain this resource so Boot finds configurations provided by that dependency. In modern Spring Boot, register auto-configuration classes through the version-appropriate `AutoConfiguration.imports` mechanism rather than letting component scanning pick them up accidentally.

### Separate Stages—Avoid Merging Them Into One

1. **Candidate discovery:** Boot collects auto-configuration names registered by libraries on the classpath. A class listed in `AutoConfiguration.imports` is only a **candidate**.
2. **Exclusions and pre-filtering:** Boot evaluates excluded classes, and filters/metadata can drop ineligible candidates, such as when a required class is absent. A class dropped here will not be imported as a selected configuration.
3. **Grouping and ordering:** Boot can group results from selectors and order auto-configurations by before/after relationships to decide **configuration processing order**.
4. **Parsing imported classes:** Spring proceeds to process auto-configuration metadata, including class-level `@Conditional` checks, nested configurations, and `@Bean` methods.
5. **Registering bean definitions, then creating beans:** Only valid bean definitions enter the context. Bean instance creation belongs to a separate stage and also depends on scope, lazy initialization, dependencies, and bean lifecycle.

Do not say "being in the imports file means every bean will appear": it may be excluded, filtered, fail a condition, or fail during bean creation. Also do not say "the selector creates beans": the selector chooses **which classes participate in configuration**.

## 4. Why Must Auto-Configuration Be Deferred?

The most important motivation is **prioritizing application configuration over framework defaults**.

Imagine a library providing a notification service. An application might want to define its own `NotificationSender`. Auto-configuration should create the default sender only when no matching bean exists. Typically there is a method:

~~~java
@Bean
@ConditionalOnMissingBean(NotificationSender.class)
NotificationSender defaultNotificationSender() {
    return new DefaultNotificationSender();
}
~~~

This is an illustrative snippet; `NotificationSender` and `DefaultNotificationSender` are hypothetical types that must be declared to compile. Desired rule:

- If the application already declared `@Bean NotificationSender customSender()`, Boot **backs off** and does not register the corresponding default sender.
- If the application has not declared one, Boot can register the default bean, provided other conditions also match.

`@ConditionalOnMissingBean` does not travel forward in time to see every bean that will exist in the future. According to Spring Boot documentation, bean conditions rely on **bean definitions already processed up to the point of evaluation**. If auto-configuration were processed too early, it might not yet see a user-defined bean, thus registering an unintended default configuration.

`DeferredImportSelector` solves the ordering problem at the import layer: auto-configuration import selection is processed **after** ordinary configurations. Thus, auto-configuration has a reliable basis to observe application bean definitions when applying "missing bean" conditions. Boot documentation therefore recommends placing `@ConditionalOnBean` and `@ConditionalOnMissingBean` primarily on auto-configurations.

Logical comparison diagram:

~~~text
Early processing without guaranteed order (illustrating the risk)
    1. Evaluate default: NotificationSender not seen yet
    2. Register defaultSender
    3. Later process @Bean customSender
       → potential conflict or unexpected behavior

Processing via Boot's deferred mechanism
    1. Process application configuration: see customSender
    2. Reach auto-configuration import phase
    3. Evaluate @ConditionalOnMissingBean(NotificationSender.class)
    4. Condition does not match → skip defaultSender
       → application retains customization control
~~~

This explains the **architectural rationale**, not a claim that any wrong registration order always leads to two beans with the same name. Specific outcomes still depend on conditions, bean types, bean names, and how the user registers them.

### Why Not Prioritize Simply by Renaming Beans?

Bean names solve only part of the issue. `@ConditionalOnMissingBean` can match by type, name, annotation, and other search attributes. A bean named `customSender` can still share the same **type** as the default `defaultSender`. That is why processing order of **bean definitions** is the core issue; renaming a bean cannot replace conditional back-off.

### Why Is Deferral Also Useful for Other Condition Types?

Some auto-configurations need to know which libraries exist, related configurations, servlet/reactive environment, properties, and other beans. Selecting imports in the deferred phase creates a consistent checkpoint to filter, order, and coordinate multiple auto-configurations. Still, **not every condition needs deferral for the same reason**: for instance, `@ConditionalOnClass` can inspect the classpath without depending on application beans. The crucial benefit for bean conditions is ordering relative to bean definitions created by the application.

## 5. What Does DeferredImportSelector.Group Help With?

Spring Framework allows a `DeferredImportSelector` to declare `getImportGroup()`. The group receives results from multiple deferred selectors and can coordinate ordering, filtering, deduplicating, or re-selecting emitted imports. `AutoConfigurationImportSelector` uses a Boot-specific group to process auto-configuration selections.

Callback overview:

~~~text
ConfigurationClassParser
    ├── parse ordinary @Configuration classes
    ├── record DeferredImportSelector
    └── process deferred selectors
          ├── place selector into its corresponding group
          ├── group.process(metadata, selector)
          └── group.selectImports()
                → list of Entry(metadata, importClassName)
                → continue parsing imported configurations
~~~

**A Group is not a thread group**. `process` and `selectImports` participate in metadata processing during context construction, not a parallel execution mechanism. If you write a custom `DeferredImportSelector.Group`, you must ensure emitted imports have valid ordering and metadata, while avoiding side effects dependent on arbitrary order.

`AutoConfigurationImportSelector.AutoConfigurationGroup` is a Boot implementation detail: you do not need to call or instantiate it yourself in an application. What application developers should do is use public annotations and metadata (`@AutoConfiguration`, the imports file, conditions, and ordering rules).

## 6. Auto-Configuration Ordering: How Does @AutoConfiguration(before/after) Differ?

Even after the deferred phase, auto-configurations may still need ordering relative to one another. For example, configuration A provides a prerequisite bean so B can apply a `@ConditionalOnBean` condition. Spring Boot supports:

~~~java
@AutoConfiguration(after = SomeOtherAutoConfiguration.class)
public class MyAutoConfiguration {
    // Appropriate bean definitions and conditions
}
~~~

This is an illustrative snippet, **not a complete class**: you must import the annotation from the right package and define `SomeOtherAutoConfiguration`. You can use `before`, `after`, `beforeName`, `afterName`; dedicated annotations `@AutoConfigureBefore`/`@AutoConfigureAfter` and `@AutoConfigureOrder` also exist.

Three kinds of ordering must be distinguished:

| Ordering Type | Practical Meaning |
| --- | --- |
| Regular selector order vs. deferred selector | Determines when **import selection and parsing** occur relative to application configuration. |
| Order among auto-configurations | Affects the **processing and bean definition registration order** of auto-configurations, useful for conditions depending on existing definitions. |
| Bean instantiation order | Managed by the dependency graph, `@DependsOn`, eager/lazy settings, and lifecycle; **not** directly decided by `@AutoConfiguration(after=...)`. |

Class-level conditions and method-level conditions can also be processed in different phases. Spring Framework has `ConfigurationCondition.ConfigurationPhase.PARSE_CONFIGURATION` and `REGISTER_BEAN`; do not assume all conditions run on a single timeline. In practice, use the **Condition Evaluation Report** to inspect condition outcomes.

### Misconceptions About Ordering

- **"Deferred means all Boot beans are created last."** No. This defers import/configuration processing, not a promise that every instance is constructed last.
- **"after = X means X's bean is instantiated via `new` before my bean."** No. Auto-configuration ordering affects definition order; instantiation still depends on bean dependencies.
- **"A @ConditionalOnMissingBean guarantees skipping whenever any future bean exists."** No. It relies on bean definitions already processed at the time the condition is evaluated.
- **"Once @AutoConfiguration is used, there is no need to declare an imports file."** For auto-configurations packaged under Boot 3.x conventions, `AutoConfiguration.imports` metadata is still required for Boot to discover them.

## 7. Hands-On Java 17+ / Spring Boot 3.5.0: Application Beats the Default Bean

The following example builds **the project's own auto-configuration**, registered via `AutoConfiguration.imports`. The application has a custom bean controlled by the `demo.user=true` property. When the custom bean is present, the default backs off. When auto-configuration is disabled by another property condition, the project has no default bean. Thus, three situations can be observed without needing a database or web server.

This is a complete example with Maven and JDK 17+, requiring no source code from other lessons.

### 7.1. Directory Structure

~~~text
deferred-import-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/
        │       ├── api/Greeter.java
        │       ├── app/DemoApplication.java
        │       └── autoconfig/GreeterAutoConfiguration.java
        └── resources/
            ├── application.properties
            └── META-INF/spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

`DemoApplication` is intentionally placed in `com.example.app` and `GreeterAutoConfiguration` in `com.example.autoconfig` (two sibling packages). Default component scanning from `@SpringBootApplication` in `com.example.app` does not automatically scan the auto-configuration class. It is brought in via **imports metadata** as the mechanism to demonstrate.

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>deferred-import-demo</artifactId>
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

### 7.3. Greeter.java

File `src/main/java/com/example/api/Greeter.java`:

~~~java
package com.example.api;

public interface Greeter {
    String sayHello();
}
~~~

This is just a simple Java contract. **Simply having an interface on the classpath creates no bean**.

### 7.4. GreeterAutoConfiguration.java

File `src/main/java/com/example/autoconfig/GreeterAutoConfiguration.java`:

~~~java
package com.example.autoconfig;

import com.example.api.Greeter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo",
        name = "auto",
        havingValue = "true",
        matchIfMissing = true
)
public class GreeterAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Greeter.class)
    Greeter defaultGreeter() {
        return () -> "AUTO";
    }
}
~~~

Two condition layers:

- Class-level condition: `demo.auto` allows the configuration by default, yet `--demo.auto=false` eliminates this configuration.
- `@Bean`-level condition: registers `defaultGreeter` only when no matching `Greeter` bean is visible at condition evaluation time.

`@AutoConfiguration` is essentially a Spring configuration class as well. It does not automatically mean "the bean is always created". Nor does the annotation replace registering library metadata.

### 7.5. AutoConfiguration.imports

The file must have the exact path:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

And content:

~~~text
com.example.autoconfig.GreeterAutoConfiguration
~~~

If the file is not packaged into the JAR at the right place, Spring Boot will not discover the sample auto-configuration through this mechanism. Do not use `@ComponentScan` to mask a metadata mistake: doing so hides what you are learning.

### 7.6. DemoApplication.java

File `src/main/java/com/example/app/DemoApplication.java`:

~~~java
package com.example.app;

import com.example.api.Greeter;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "user",
            havingValue = "true"
    )
    Greeter userGreeter() {
        return () -> "USER";
    }

    @Bean
    ApplicationRunner printResult(ObjectProvider<Greeter> greeters) {
        return args -> {
            Greeter greeter = greeters.getIfAvailable();
            System.out.println("GREETER="
                    + (greeter == null ? "NONE" : greeter.sayHello()));
        };
    }
}
~~~

The root class is **application** configuration. The application's `userGreeter` bean is processed before Boot's auto-configuration. When the property enables this bean, `@ConditionalOnMissingBean(Greeter.class)` on `defaultGreeter` will not match.

`ObjectProvider<Greeter>` retrieves the bean if present, or `null` if absent; using this allows the case with no `Greeter` to still run and print `NONE`. If multiple beans of the same type existed, `getIfAvailable()` could fail due to non-uniqueness, yet with this exact sample configuration every case has at most one `Greeter`.

### 7.7. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.main.banner-mode=off
logging.level.root=ERROR
~~~

Do not hardcode defaults for `demo.user` or `demo.auto` in the file: these two properties are controlled via application arguments below. You can keep the logging configuration as is or change it to inspect the condition report.

### 7.8. Packaging and Running

In the `deferred-import-demo` directory:

~~~bash
mvn -q -DskipTests package
java -jar target/deferred-import-demo-1.0.0.jar
~~~

Line printed by the application:

~~~text
GREETER=AUTO
~~~

Because the application has not registered a custom `Greeter` and `demo.auto` is absent (permitted via `matchIfMissing=true`), auto-configuration registers the default bean.

Run with the application-declared bean:

~~~bash
java -jar target/deferred-import-demo-1.0.0.jar --demo.user=true
~~~

Line printed by the application:

~~~text
GREETER=USER
~~~

`userGreeter` was registered; auto-configuration checked for a missing `Greeter`, failed to match, and **backed off**. This outcome aligns with processing auto-configuration imports in the deferred phase.

Disable the sample auto-configuration without enabling the custom bean:

~~~bash
java -jar target/deferred-import-demo-1.0.0.jar --demo.auto=false
~~~

Line printed by the application:

~~~text
GREETER=NONE
~~~

The class-level condition on `GreeterAutoConfiguration` does not match; the application does not have `userGreeter`. Therefore there is no `Greeter` bean.

Enable the application bean even when auto-configuration is disabled:

~~~bash
java -jar target/deferred-import-demo-1.0.0.jar --demo.auto=false --demo.user=true
~~~

Line printed by the application:

~~~text
GREETER=USER
~~~

This proves that **application configuration and auto-configuration are two distinct sources of bean definitions**. Excluding an auto-configuration does not mean the application's `@Bean` methods are excluded too.

Summary table:

| Argument | Application Bean | Default Bean | Printed Output |
| --- | --- | --- | --- |
| None | No | Yes | `GREETER=AUTO` |
| `--demo.user=true` | Yes | Skipped by `@ConditionalOnMissingBean` | `GREETER=USER` |
| `--demo.auto=false` | No | No, class condition does not match | `GREETER=NONE` |
| `--demo.auto=false --demo.user=true` | Yes | No | `GREETER=USER` |

**Scope of inference:** the `GREETER=...` lines are stdout printed by the program itself, excluding Spring Boot/JVM/Maven logs (which may vary by environment). The example accurately demonstrates metadata and condition mechanics in Spring Boot 3.5.0; it is not meant to prove internal callbacks solely by log line order, as import selection callbacks are not logged in the example.

## 8. How to Verify That Deferred Import Is in Effect

### Observing Why Conditions Matched or Did Not Match

Run with debug mode and enable logging at an appropriate level:

~~~bash
java -jar target/deferred-import-demo-1.0.0.jar --demo.user=true --debug --logging.level.root=INFO
~~~

Look for `GreeterAutoConfiguration` and `defaultGreeter` in the **Condition Evaluation Report** if the report is logged. Exact wording and line labels depend on Boot version and logging. Look for the reason the default bean was not registered due to an existing `Greeter` provided by the application. Rerun without `--demo.user=true` to compare.

Remember: the report shows **condition evaluation results**; it is not a full stack trace of `ConfigurationClassParser` callbacks. If you want to observe the exact moment `AutoConfigurationImportSelector` is invoked, debug the source in your IDE with breakpoints in the Boot/Spring Framework infrastructure classes of the exact version, such as `AutoConfigurationImportSelector` and the parser's deferred import handler. Do not add production code just to print an implementation detail.

### Verifying Import Metadata Is Inside the JAR

After packaging on a system with the `jar` command:

~~~bash
jar tf target/deferred-import-demo-1.0.0.jar
~~~

Look for the resource entry inside `BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Because `jar tf` output lists many files, there is no single fixed stdout; simply confirm the metadata path exists inside the JAR.

If the metadata is missing, check the file name, `src/main/resources` location, and build process. If the file exists yet the bean is still missing, check properties, annotation conditions, exclusions, and the report instead of assuming the deferred selector is broken.

### Distinguishing "Imported" from "Bean Instantiated"

An auto-configuration may be selected and parsed, yet a bean inside it is still not registered due to `@ConditionalOnMissingBean`. Or the bean definition may be registered yet instantiation is deferred because of `@Lazy`. Or instance creation may fail due to a missing dependency. Never rely on a single signal (starter on classpath, class in imports file, positive match at class level) to draw conclusions about the entire bean graph.

## 9. Why Shouldn't You Apply DeferredImportSelector to Every Configuration Yourself?

`DeferredImportSelector` fits when a library needs to select a conditional set of configurations in a late phase, especially cases like auto-configuration. In application code, simpler needs can be met with `@Configuration`, `@Bean`, `@Import`, or component scanning.

Creating custom deferred selectors often increases complexity: selector ordering, metadata, condition application, grouping, and API clarity. If you merely want to let users replace a default bean in a custom starter, the cleanest public and maintainable approach is usually:

1. Write an `@AutoConfiguration` class with appropriate conditions.
2. Register it properly via `AutoConfiguration.imports`.
3. Place `@ConditionalOnMissingBean` on the bean that should back off and return a sufficiently specific type.
4. If multiple auto-configurations depend on each other, specify ordering via `before`/`after` appropriately.
5. Write tests or runnable examples covering both presence and absence of a user bean.

**Never write a custom selector just to manually instantiate bean instances**; a selector returns class names and does not replace the Spring IoC container.

## 10. Common Errors and Misconceptions

### Confusing "Deferred" with Async / Lazy

Deferred here refers to **the schedule for processing import metadata within a configuration pass**. It does not use a thread pool, has no `CompletableFuture`, does not make beans `@Lazy`, and does not postpone execution until after the first request arrives.

### Confusing Auto-Configuration Ordering with Bean Dependency Ordering

`@AutoConfiguration(after = X.class)` helps control the order in which auto-configurations are applied. It does not force X's bean to finish instantiating before the current configuration's bean. Use dependency injection/`@DependsOn` if there is a specific initialization requirement and you understand why.

### Placing @ConditionalOnMissingBean on an Arbitrary Application @Configuration

The condition only knows about definitions already processed at the time it is evaluated. Using bean conditions on application configurations with unclear ordering can yield unexpected results. Boot documentation recommends these conditions on auto-configurations because of the mechanism that loads them after user configurations.

### Placing Auto-Configuration Inside a Component Scan Package

If the same auto-configuration class is both picked up by component scanning and brought in via imports metadata, experiments about deferred ordering become hard to reason about. According to Boot documentation, auto-configuration should reside outside component scan and be discovered via the imports file; do not arbitrarily enable extra component scanning inside an auto-configuration.

### Forgetting AutoConfiguration.imports

`@AutoConfiguration` on a class does not automatically put that class into the classpath candidate list. Check the exact path, line-by-line contents, and packaging.

### Mistaking a Non-Matching @ConditionalOnMissingBean for an Error

If the application has a matching bean of the same type, that is the intended "back off" behavior. Read the condition report and observe the actual beans in the context.

### Using Ordering to "Fix" Every Condition Failure

A condition failure can stem from a missing class, wrong property, different profile, existing bean, or excluded auto-configuration. `before`/`after` only relates to auto-configuration order; before adjusting order, know why the condition failed.

### Thinking Every Default Configuration Allows Overriding

Not every auto-configuration puts `@ConditionalOnMissingBean` on every bean. Inspect the actual condition logic of the class in the Boot and library versions you use. "Application takes precedence" is a broad design principle, yet the exact effect depends on the conditions on each bean.

## 11. Self-Assessment Questions

1. **What does `ImportSelector` return?** A list of class names to import, not bean instances.
2. **How does `DeferredImportSelector` differ from a regular selector?** It is processed in the deferred phase after ordinary configuration classes are processed.
3. **Why does Boot use this mechanism?** To coordinate auto-configurations after application configuration, especially for conditions based on existing bean definitions, and to group/filter/order candidates.
4. **Does `AutoConfigurationImportSelector` invoke `@Bean` methods itself?** No; it selects configurations. The Spring container processes bean definitions and creates instances in the appropriate phases.
5. **Does adding a class to `AutoConfiguration.imports` guarantee its beans are created?** No; exclusions, filters, conditions, and instantiation still apply.
6. **Why can `@ConditionalOnMissingBean` be order-dependent?** Because it checks bean definitions that have already been processed at the time of evaluation.
7. **Does `@AutoConfiguration(after = X.class)` control bean instance creation order?** No; it controls configuration application order.
8. **When running the demo with `--demo.user=true`, why does it print USER?** The application-declared bean was registered, causing the default bean's missing-`Greeter` condition to fail.
9. **With `--demo.auto=false --demo.user=true`, does a bean exist?** Yes, the bean provided by the application exists; the condition disabling auto-configuration does not affect that bean.
10. **Does "defer" here wait for ApplicationReadyEvent?** No, it happens during configuration processing of the context refresh.

## Official References

- Spring Framework — `DeferredImportSelector` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html
- Spring Framework — `ImportSelector` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/ImportSelector.html
- Spring Boot — `AutoConfigurationImportSelector` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html

**Takeaway:** `DeferredImportSelector` lets Spring Boot process auto-configuration imports **after application configuration**, so conditions like `@ConditionalOnMissingBean` can observe choices declared by the application and only fill in missing defaults. This is an ordering of **configuration parsing and bean definition registration**, not an asynchronous or post-startup bean instantiation mechanism.