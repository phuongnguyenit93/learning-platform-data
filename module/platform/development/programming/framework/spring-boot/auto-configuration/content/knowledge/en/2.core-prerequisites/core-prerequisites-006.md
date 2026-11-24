# Environment, PropertySource, and When Properties Become Available for Conditions in Spring Boot

## 1. The problem to understand

Auto-configuration does not make decisions in a vacuum. Conditions such as `@ConditionalOnProperty` look up property values from `Environment` at **the time the condition is evaluated**. To predict which beans will be registered, three separate questions must be answered:

1. **Where does the property come from?** `application.properties`/`application.yaml` files, profiles, OS environment variables, JVM system properties, `--key=value` arguments, custom sources, and so on can all supply values.
2. **Which source takes precedence when keys collide?** `Environment` traverses `PropertySource`s in priority order and returns the first matching value; it does not merge two values for the same key into one.
3. **Was the source added before the condition was evaluated?** A value visible inside an `ApplicationRunner` after the application starts is not guaranteed to have been present when an earlier condition ran.

For example: a feature should only create a bean when `feature.mail.enabled=true`. If this key is in a config file yet overridden via command-line to `false`, the bean is normally not registered. If a piece of code only puts the key into `Environment` after the condition has already been evaluated, adding that key does not cause Spring to re-evaluate and re-register the bean.

The goal of this lesson is to understand the exact concepts, precedence order, lifecycle milestones, and how to verify them with a Java 17+ application.

## 2. What is Environment?

`org.springframework.core.env.Environment` is Spring Framework's abstraction representing **properties** and **profiles** active for the application.

Typical APIs:

| API | Meaning |
| --- | --- |
| `environment.getProperty("demo.message")` | Reads a string value or `null` if not found. |
| `environment.getProperty("demo.port", Integer.class)` | Looks up and converts type; may fail if the data cannot be converted. |
| `environment.getProperty("demo.message", "fallback")` | Uses a fallback value when the property is not found. |
| `environment.containsProperty("demo.message")` | Checks whether the property resolves to a value. |
| `environment.getActiveProfiles()` | Returns the currently active profiles. |
| `configurableEnvironment.getPropertySources()` | Inspects or manages the chain of property sources when using `ConfigurableEnvironment`. |

`Environment` is a **lookup surface**; it does not necessarily hold every value in a single `Map`. An application can have multiple sources all carrying the key `demo.message`. The order of the sources determines the observed value.

`ConfigurableEnvironment` extends read access by allowing configuration of profiles and `MutablePropertySources`. This type is especially useful in early application initialization phases, such as when writing an `EnvironmentPostProcessor`.

Distinguish from similarly named concepts:

- **Environment**: interface for querying properties and profiles.
- **PropertySource**: a concrete key-value source, such as environment variables, system properties, a loaded file, or a custom map.
- **PropertySources**: an **ordered** collection of property sources used to resolve keys.
- Spring Boot **ConfigData**: mechanism for processing external configuration such as `application.properties`, YAML, profile-specific files, and `spring.config.import` during environment preparation.
- **`@ConfigurationProperties`**: binds already-available properties onto a structured configuration object; this binding does not correspond to when values first enter `Environment`.
- **`@ConditionalOnProperty`**: decides whether to include a configuration or bean definition in the context based on the property looked up when evaluating the condition.

## 3. How does PropertySource work?

A `PropertySource<T>` has a name and knows how to retrieve a value by key from a backing source object `T`. For example, `MapPropertySource` reads values from a `Map`. `SystemEnvironmentPropertySource` supports lookup rules suited to OS environment variables.

You can picture `Environment` as a search chain:

~~~text
getProperty("demo.message")
    |
    v
Highest-priority PropertySource  ---> has value? ---> return it
    |
    | absent
    v
Next PropertySource              ---> has value? ---> return it
    |
    | absent
    v
...
    |
    +-- no source has a value ---> null / defaultValue
~~~

Key takeaway: when the same key appears in multiple sources, **the highest-precedence source that resolves the key wins**. Adding a source with `addFirst(...)` places it at the front of the list; `addLast(...)` places it at the end. `addBefore(...)` and `addAfter(...)` allow positioning relative to a known source. Distinguish **lookup precedence order** from **when a source was loaded**: a source added later can still be placed at the end, giving it low priority.

Illustrative Spring Framework example, without running a Boot application:

~~~java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

public class PropertySourceOrderDemo {
    public static void main(String[] args) {
        StandardEnvironment env = new StandardEnvironment();

        env.getPropertySources().addLast(
                new MapPropertySource("low", Map.of("demo.answer", "LOW"))
        );
        env.getPropertySources().addFirst(
                new MapPropertySource("high", Map.of("demo.answer", "HIGH"))
        );

        System.out.println(env.getProperty("demo.answer"));

        env.getPropertySources().remove("high");
        System.out.println(env.getProperty("demo.answer"));
    }
}
~~~

With `spring-core` and Spring Framework dependencies on the classpath, the class above prints:

~~~text
HIGH
LOW
~~~

Note: this snippet illustrates **APIs and precedence**. It is not a standalone Java file compiling with only the JDK, because `StandardEnvironment` and `MapPropertySource` belong to Spring libraries. The complete Maven example in section 7 runs as an actual Spring Boot application.

### Data sources and precedence order in Spring Boot

Spring Boot has its own rules, published in the **Externalized Configuration** documentation. In a typical Boot application, keep these practical points in mind:

- Command-line arguments such as `--demo.message=CLI` usually **take precedence over** JVM `-Ddemo.message=JVM`, environment variables, and config files, unless the application disables command-line properties.
- JVM system properties typically **take precedence over** OS environment variables; both usually take precedence over config data from `application.properties`.
- Config data from files typically **takes precedence over** `@PropertySource` on `@Configuration` classes; `SpringApplication.setDefaultProperties` provides a low-precedence fallback.
- Other sources such as `SPRING_APPLICATION_JSON`, servlet/JNDI, test annotations, devtools, and custom sources have their own places in the order. Do not treat the shortened list above as the absolute complete order for every Boot version and application type.

In the *ascending-precedence* list published by Boot documentation, **sources appearing later can override sources appearing earlier**. When iterating `MutablePropertySources` in code, **sources appearing earlier in the list are searched first**. Both descriptions are consistent; they simply view the list from opposite ends.

Example with the same key `demo.message`:

| Source | Value |
| --- | --- |
| `application.properties` | `FILE` |
| Environment variable `DEMO_MESSAGE` | `ENV` |
| JVM argument `-Ddemo.message=JVM` | `JVM` |
| Application argument `--demo.message=CLI` | `CLI` |

When all of these sources are present under default Boot settings, the resolved value is typically `CLI`. Remove `--demo.message` and `JVM` wins; also remove `-D` and the environment variable can win; remove the environment variable too and you get `FILE`. This is an example of **overriding**, not four beans or four configurations created simultaneously.

### Profiles, files, and imports

Spring Boot supports `application-{profile}.properties`, `application-{profile}.yaml`, and `spring.config.import`. Which files are loaded also depends on active profiles, file locations, config data ordering, and location groups. For instance, `application-dev.properties` only applies when the `dev` profile is active or an appropriate import mechanism loads it.

When diagnosing a final value, do not look only at `src/main/resources/application.properties`. Check active profiles, files outside the JAR, imported files, and launch arguments. Values can differ between IDEs, tests, local run commands, and containers.

## 4. When properties become available in the startup lifecycle

"Present in a file" does not mean "already in `Environment` from the very beginning". The diagram below shows **high-level milestones**; exact callback details can vary across Boot versions:

~~~text
SpringApplication.run(...)
    |
    v
Create / prepare Environment
- read app arguments, system properties, environment variables
- process config data: application.*, profiles, spring.config.import
- run EnvironmentPostProcessors in configured order
    |
    v
Create ApplicationContext and prepare context
    |
    v
Refresh context: parse @Configuration,
register bean definitions, process auto-configuration,
and evaluate @ConditionalOnProperty / other @Conditional
    |
    v
Instantiate required singleton beans,
bind @ConfigurationProperties, inject dependencies
    |
    v
ApplicationRunner / CommandLineRunner
    |
    v
Application ready to serve
~~~

Important timings:

**Before context refresh:** configuration sources prepared by Boot via ConfigData and `EnvironmentPostProcessor`s can already be present for lookup while configuration classes and auto-configurations are processed. If you need to supply a source for very early decisions, typically use ConfigData or `Environment` preparation mechanisms.

**During refresh / configuration parsing:** `@ConditionalOnProperty` is typically evaluated to decide whether to register a configuration or `@Bean`. It uses `Environment` values **at evaluation time**, with the current precedence order. A condition on a class and a condition on a method may be evaluated at different steps while parsing/registering bean definitions.

**After beans are registered and instantiated:** `@Value` or `@ConfigurationProperties` can read/bind properties during bean creation. That is not proof they existed at an earlier stage. If you mutate `Environment` inside `ApplicationRunner`, `Environment.getProperty(...)` can read the new value, yet Spring Boot **does not automatically re-evaluate all previously checked conditions** or add/remove beans based on the new value.

Example: `@ConditionalOnProperty(name = "demo.enabled", havingValue = "true")` excluded a bean because the value was `false`. Adding `demo.enabled=true` later inside `ApplicationRunner` does not make the bean appear in that same context. To alter bean structure based on startup conditions, you normally must configure the value properly **before** refresh and start a new context.

### Why must `@PropertySource` be used with timing in mind?

`@PropertySource("classpath:extra.properties")` is processed by Spring Framework when the `@Configuration` class is parsed during **context refresh**. Spring Boot notes that this timing is **too late** for certain properties already used before refresh begins, such as `logging.*` and `spring.main.*`.

Do not overgeneralize this into "`@PropertySource` is always useless for every condition": which condition runs when, in what order configuration classes are parsed, and whether the source was added yet determine whether it arrives in time. Even so, if an auto-configuration needs a reliable value **from the environment preparation phase**, supply it via ConfigData or an `EnvironmentPostProcessor` rather than relying on incidental `@Configuration` class processing order.

`@PropertySource` supports Java `.properties` files by default. Do not assume `@PropertySource("classpath:extra.yaml")` automatically supports YAML like Boot's ConfigData mechanism; loading YAML via this annotation requires an appropriate `PropertySourceFactory` or using Boot's standard mechanism.

### EnvironmentPostProcessor and execution order

`EnvironmentPostProcessor` is Spring Boot's extension point for modifying `ConfigurableEnvironment` **before refresh**. An implementation is registered in `META-INF/spring.factories`; `Ordered` or `@Order` can be used to control ordering. Boot also uses `ConfigDataEnvironmentPostProcessor` to process config data. A custom processor must consider its order relative to that processor if it depends on properties from config files.

In the example in the next section, the custom processor chooses `Ordered.LOWEST_PRECEDENCE` and appends a `MapPropertySource` via `addLast`. This serves as a fallback source: properties from command-line or config files loaded by Boot will override it. In this simple program, the processor creates the defaults before conditions are evaluated, so conditions can use them.

## 5. How does @ConditionalOnProperty read Environment?

Example:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "demo",
        name = "feature-enabled",
        havingValue = "true",
        matchIfMissing = false
)
FeatureService featureService() {
    return () -> "ENABLED";
}
~~~

This is an **illustrative snippet inside a `@Configuration` / `@SpringBootApplication` class**, not a standalone program. The condition checks the key `demo.feature-enabled` in `Environment`.

Cases:

| Resolved value of `demo.feature-enabled` | Result with `havingValue="true", matchIfMissing=false` |
| --- | --- |
| `true` | Condition matches. |
| `false` | Does not match. |
| Key absent | Does not match. |
| Another string such as `other` | Does not match. |

If `havingValue` is omitted, `@ConditionalOnProperty`'s default rule is broader: the property must be present and its value **must not equal `false`** per the annotation's logic. If `matchIfMissing=true` is set, the condition can match even when the key is missing. Therefore, do not confuse "key exists" with "boolean value is true", and specify `havingValue` explicitly when you want a specific constraint.

`@ConditionalOnProperty` checks properties on `Environment`; it does not directly read a specific file. Source precedence and when sources were loaded determine the result. Whether the bean ends up registered also depends on other conditions in effect (classpath, existing beans, web environment, etc.).

For structures like `demo.targets[0]` or collections, do not assume `@ConditionalOnProperty` will thoroughly validate nested element presence. Boot documentation recommends writing a custom condition for complex collection checks.

## 6. Complete example: fallback source, file, command-line, and condition

The Maven project below uses **Java 17 and Spring Boot 3.5.0**, sufficient to observe three behaviors:
- An `EnvironmentPostProcessor` adds fallback properties into `Environment` before conditional beans are evaluated.
- `application.properties` can override a property in the fallback source.
- Command-line arguments can override both the file and the fallback source, thereby changing bean registration.

Structure:

~~~text
environment-condition-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/demo/
    │   ├── DemoApplication.java
    │   ├── FeatureService.java
    │   └── EarlyDefaultsPostProcessor.java
    └── resources/
        ├── application.properties
        └── META-INF/spring.factories
~~~

### pom.xml

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
    <artifactId>environment-condition-demo</artifactId>
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

### FeatureService.java

File `src/main/java/com/example/demo/FeatureService.java`:

~~~java
package com.example.demo;

public interface FeatureService {
    String message();
}
~~~

### EarlyDefaultsPostProcessor.java

File `src/main/java/com/example/demo/EarlyDefaultsPostProcessor.java`:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class EarlyDefaultsPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        MapPropertySource defaults = new MapPropertySource(
                "demoFallback",
                Map.of(
                        "demo.feature-enabled", "true",
                        "demo.message", "FALLBACK_MESSAGE"
                )
        );

        environment.getPropertySources().addLast(defaults);
    }
}
~~~

This class **is not a Spring bean** and does not need `@Component`; Spring Boot invokes it as an extension during the `Environment` preparation phase. The source name `demoFallback` can be observed when iterating `getPropertySources()`. `addLast` lets higher-precedence sources override fallback values.

### META-INF/spring.factories

Exact contents of `src/main/resources/META-INF/spring.factories`:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.demo.EarlyDefaultsPostProcessor
~~~

The path and key are critical: if registered incorrectly, the processor does not run and `demo.feature-enabled` will be missing. This example uses the API and registration path of **Spring Boot 3.5.x**. Do not arbitrarily change it to package names or registration mechanisms from other Boot versions.

### application.properties

Contents of `src/main/resources/application.properties`:

~~~properties
spring.main.banner-mode=off
logging.level.root=ERROR
demo.message=FILE_MESSAGE
~~~

We **do not** declare `demo.feature-enabled` in the file. When no higher-precedence source supplies it, the processor provides `true` for this key. Meanwhile, `demo.message=FILE_MESSAGE` in config data takes precedence over `FALLBACK_MESSAGE` in `demoFallback`.

### DemoApplication.java

File `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "feature-enabled",
            havingValue = "true"
    )
    FeatureService featureService(Environment environment) {
        return () -> environment.getProperty(
                "demo.message", "MISSING_MESSAGE");
    }

    @Bean
    ApplicationRunner showResult(
            Environment environment,
            ObjectProvider<FeatureService> serviceProvider) {

        return args -> {
            FeatureService service = serviceProvider.getIfAvailable();

            System.out.println("enabled="
                    + environment.getProperty("demo.feature-enabled"));
            System.out.println("message="
                    + environment.getProperty("demo.message"));
            System.out.println("service="
                    + (service == null ? "ABSENT" : service.message()));
        };
    }
}
~~~

`@ConditionalOnProperty` decides whether to register `FeatureService` from the property available when configuration is processed. `ApplicationRunner` runs after the context has initialized and merely observes the final state. `ObjectProvider` avoids a mandatory injection failure when the bean is absent.

### Run and compare

JDK 17+ and Maven are required. From the `environment-condition-demo` directory:

~~~bash
mvn -q -DskipTests package
java -jar target/environment-condition-demo-1.0.0.jar
~~~

Ignore environment log lines (if any). The three lines printed by the program:

~~~text
enabled=true
message=FILE_MESSAGE
service=FILE_MESSAGE
~~~

Explanation: `demo.feature-enabled` comes from `demoFallback`; `demo.message` comes from the file. The condition matches and `FeatureService` is registered.

Override via command-line:

~~~bash
java -jar target/environment-condition-demo-1.0.0.jar --demo.feature-enabled=false --demo.message=CLI_MESSAGE
~~~

Three lines from the program:

~~~text
enabled=false
message=CLI_MESSAGE
service=ABSENT
~~~

Explanation: the command-line source is searched before the file and fallback map. `@ConditionalOnProperty(havingValue="true")` does not match, so `FeatureService` is not registered; the runner still runs thanks to `ObjectProvider`.

Override using only a JVM system property:

~~~bash
java -Ddemo.feature-enabled=false -jar target/environment-condition-demo-1.0.0.jar
~~~

Three lines from the program:

~~~text
enabled=false
message=FILE_MESSAGE
service=ABSENT
~~~

Explanation: `-Ddemo.feature-enabled=false` takes precedence over the fallback map value. `demo.message` still comes from the file because the example supplies no higher-precedence source for that key.

You can also try:

~~~bash
java -jar target/environment-condition-demo-1.0.0.jar --demo.feature-enabled=true --demo.message=CLI_MESSAGE
~~~

Three-line result:

~~~text
enabled=true
message=CLI_MESSAGE
service=CLI_MESSAGE
~~~

These four scenarios demonstrate that the condition reads **the resolved value from Environment**, rather than being hard-wired to a file or to the `EnvironmentPostProcessor`'s values.

### What if the processor registration is removed?

If you remove the registration line from `spring.factories` and run with the current file config, `demo.feature-enabled` is not provided by any source in the example. The condition `havingValue="true"` with default `matchIfMissing=false` does not match, so `FeatureService` is absent. This illustrates two independent requirements: a correct implementation still must be **registered and executed at the right phase**, and the property must **resolve to the right value**.

## 7. Observing the winning source and execution timing

When debugging, merely calling `environment.getProperty(key)` is often not enough because it shows the **final value** without telling you which source supplied it. You can add this diagnostic snippet inside the example's `showResult` method:

~~~java
// Illustrative snippet placed inside showResult(...).
// The environment variable here has type Environment.
if (environment instanceof
        org.springframework.core.env.ConfigurableEnvironment configurable) {
    for (org.springframework.core.env.PropertySource<?> source
            : configurable.getPropertySources()) {
        Object value = source.getProperty("demo.feature-enabled");
        if (value != null) {
            System.out.println("source=" + source.getName()
                    + "; value=" + value);
            break;
        }
    }
}
~~~

This snippet **is not a standalone class**. It iterates `MutablePropertySources` in order and stops at the first source returning a non-`null` value for the example key. Some sources—especially those involving environment variables and property naming—have flexible name resolution rules; when checking which key wins, query the same key form used in the condition and be mindful of canonicalized names.

In projects with Actuator, the `/actuator/env` endpoint (when provided and exposed in a controlled way) helps inspect values and property sources; the `/actuator/conditions` endpoint (when enabled/exposed) shows why conditions matched or did not match. These endpoints are not necessarily public or enabled by default. Avoid logging secrets and do not expose sensitive configuration details carelessly.

Another tool is running:

~~~bash
java -jar target/environment-condition-demo-1.0.0.jar --debug
~~~

Spring Boot outputs the **Condition Evaluation Report** in diagnostic logs if logging allows it to appear. Note that the example sets `logging.level.root=ERROR`; to view the report at an appropriate level, remove the log-suppression setting or override the log level on launch, such as:

~~~bash
java -jar target/environment-condition-demo-1.0.0.jar --debug --logging.level.root=INFO
~~~

Look for `DemoApplication#featureService` and the `@ConditionalOnProperty` match/mismatch reason. Do not confuse a configuration's `Positive matches` with every related bean having been instantiated successfully.

## 8. Common timing-related errors and how to handle them

### "In the runner I see true, yet the bean is missing"

The value may have been added or modified **after** configuration was processed. Printing the value at the end of startup does not replay its history. Check which callback adds the property, `EnvironmentPostProcessor` ordering, event listeners, profiles, and when the condition is evaluated. If a property must determine context structure, provide it earlier via config data or an appropriate initialization hook.

### "I added @PropertySource, yet logging.* did not change"

`@PropertySource` is processed during refresh; logging configuration may have already read its values earlier. Use `application.properties`, command-line arguments, system/environment properties, or a suitable early configuration mechanism.

### "I see the same key in two files, so I thought there were two values"

`Environment.getProperty` returns a single value resolved by precedence. Find the highest-precedence source and check active profiles/imported files; if the key is a multi-element structure, binding has its own rules—do not infer "merging" solely because two files exist.

### "I added a PropertySource inside @Bean and waited for @ConditionalOnProperty to change"

By the time an `@Bean` method runs, conditional bean definitions may already have been decided. Modifying `Environment` inside a bean is usually too late to affect earlier bean registration decisions. Move property-adding logic to the `Environment` preparation phase.

### "My environment variable uses underscores, yet the condition does not pick it up"

Spring Boot defines environment variable naming rules for externalized configuration, such as `DEMO_FEATURE_ENABLED` mapping to the canonical property key. Use consistent property naming, check relaxed binding rules and the specific source instead of guessing from character substitution. Keys with multiple hyphens, dots, or collection indices require extra care.

### "I changed a property at runtime, yet the bean was not added or removed"

Conditions like `@ConditionalOnProperty` are normally **context initialization conditions**, not a reactive system updating on every property change. To update behavior at runtime, design a service that reads values dynamically, use a dedicated refresh mechanism, or recreate the context as required. Do not rely on auto-configuration to mutate the bean graph inside a running context.

### "I only debugged application.properties"

Values from command-line arguments, JVM system properties, OS env, external config, or profiles can override the file packaged inside the JAR. Inspect `Environment` and the `PropertySource` order directly.

## 9. Concise diagnostic workflow

When a conditional bean is missing:

1. **Confirm key, value, and annotation.** Read `prefix`, `name`, `havingValue`, `matchIfMissing`, and any other active conditions; avoid guessing from the bean name.
2. **Confirm property sources.** Find the first source supplying the key, check order and returned value; compare CLI, `-D`, env, config data, profiles, and imports.
3. **Confirm timing.** Was the source added before refresh, or during/after refresh? In which configuration is `@PropertySource` processed? Was `EnvironmentPostProcessor` registered and run in the right order?
4. **Read the condition report.** Distinguish "condition did not match so bean was not registered" from "condition matched yet bean instantiation failed".
5. **Run a minimal test.** Use two different launch commands from section 6 to verify whether changing a high-precedence source alters the bean creation decision.
6. **Fix at the right phase.** Values needed for conditions must be ready during condition evaluation; values only used inside bean logic can be read/bound later in the bean's lifecycle.

## 10. Self-check questions

**1. Is Environment a configuration file?** No. It is an abstraction for querying multiple `PropertySource`s and profile information.

**2. Why might a key appear in application.properties while getProperty returns a different value?** Because a higher-precedence source (such as command-line arguments) also supplies that key.

**3. How do addFirst and addLast differ?** `addFirst` puts the source at the front to be searched first; `addLast` puts the source at a lower priority in the current list.

**4. Will a new property added in ApplicationRunner re-run @ConditionalOnProperty for an already-evaluated bean?** No. Bean registration conditions are not automatically re-evaluated just because `Environment` changes after startup.

**5. Why should @PropertySource not be used to control logging.*?** Because the annotation is processed during refresh, whereas logging may already have been configured earlier.

**6. If demo.feature-enabled is absent, does havingValue="true" match?** By default `matchIfMissing=false`, so it does not match.

**7. If a property is false in a file yet true from the command-line, what does the condition see?** Under default precedence, the condition reads `true` from the command-line source at evaluation time, so it can match.

## Official documentation

- Spring Framework — Environment Abstraction: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Creating Your Own Auto-configuration (conditions): https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — EnvironmentPostProcessor API (select your exact version): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html

**Practical takeaway:** To explain a conditional bean, check **the resolved Environment value, the winning PropertySource by precedence, and when the property became available when the condition was evaluated**. Reading a value at the end of startup only confirms the current state; it is no substitute for understanding the startup lifecycle.