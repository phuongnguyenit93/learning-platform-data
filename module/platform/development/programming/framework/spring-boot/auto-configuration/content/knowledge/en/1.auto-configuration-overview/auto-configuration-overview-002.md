# The role of auto-configuration in the relationship between Spring Framework and Spring Boot

## 1. Where auto-configuration fits in the overall picture

**Spring Framework** provides the foundation for a Java application to run: the IoC container (`ApplicationContext`), bean management, Dependency Injection (DI), bean lifecycle, configuration with `@Configuration`/`@Bean`, environment handling, and many modules such as Spring MVC, transactions, and data access. Developers still have to decide and declare the components the application needs.

**Spring Boot** builds on Spring Framework. One of Boot's most important contributions is **auto-configuration**: based on the libraries present, configuration properties, application type, and beans already declared by the user, Boot *proposes* commonly used infrastructure beans/configurations. That reduces repetitive configuration while keeping control in the application's hands.

> Key idea: **Spring Framework executes the IoC/DI mechanism and processes beans; Spring Boot decides whether to contribute certain default bean definitions into that same container.** Auto-configuration does not create a different IoC container and does not replace Spring's foundational architecture.

For example, if an application has appropriate web libraries on the classpath, Boot can configure MVC components, an embedded web server, and related utilities; if an application lacks those conditions, the corresponding configuration is not applied. If the application supplies a bean of a type that auto-configuration is designed to defer to, Boot does not register that default bean.

## 2. Comparing the responsibilities of the two layers

| Aspect | Spring Framework | Spring Boot/auto-configuration |
| --- | --- | --- |
| Creating and managing beans | `BeanFactory`/`ApplicationContext`, DI, scopes, lifecycle | Conditionally registers additional selected **bean definitions** into the Framework's container |
| Manual configuration | Supports `@Configuration`, `@Bean`, `@Import`, component scanning, `@Conditional` | Provides `@AutoConfiguration` classes with built-in conditions for common technologies |
| Discovering application components | `@ComponentScan` finds beans in scanned packages | Loads a **separate auto-configuration list** from metadata inside JARs |
| Environment/configuration | `Environment`, property sources, profiles | Uses these values to enable, disable, or tune default configurations |
| Final decision authority | The application can intentionally declare beans/configurations | Many defaults are designed to **back off** if the application has already defined an appropriate bean |
| Startup | Provides context building/refresh mechanisms | `SpringApplication` orchestrates startup, infers the application type, and applies Boot conveniences |

A plain Spring configuration can run completely without Boot. Conversely, a Boot application is still an application using Spring Framework's core mechanisms; it simply receives an added layer of default selection and a convenient startup workflow.

### Three questions to determine responsibility

1. **Who creates and manages objects?** The Spring container.
2. **Who provides a sensible configuration when the application has not configured one?** Spring Boot auto-configuration, *if* the corresponding conditions are satisfied.
3. **Who has the right to alter configuration according to business requirements?** The application, via its own declared beans/configurations, properties, or appropriate auto-configuration exclusions.

## 3. How does auto-configuration participate at startup?

In a typical Boot application:

```java
@SpringBootApplication
public class MyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
```

`@SpringBootApplication` combines three main ideas:

- `@SpringBootConfiguration`: marks the application's configuration class (a form of `@Configuration`).
- `@EnableAutoConfiguration`: triggers the inspection of automatic configurations.
- `@ComponentScan`: scans application components, normally from the startup class's package downward.

**Component scanning and auto-configuration are two different sources of bean definitions.** An application `@Service` bean typically comes from package scanning; a default bean for an external library can come from an imported auto-configuration class. Do not assume Boot finds all auto-configurations by scanning packages.

Simplified conceptual flow:

```text
SpringApplication.run(...)
  -> prepare Environment and ApplicationContext
  -> process application configuration (@SpringBootApplication)
       -> scan components and process application @Bean methods
       -> @EnableAutoConfiguration selects auto-configuration candidates
  -> evaluate @Conditional, register appropriate bean definitions
  -> Spring Framework instantiates, wires, and manages beans
  -> application is ready according to the startup lifecycle
```

This is a **conceptual diagram**, not the detailed execution order of every processor or every bean. In practice, parsing configuration, registering bean definitions, and instantiating beans involve multiple steps. The key point to grasp is that beans coming from auto-configuration are ultimately managed by the same Spring IoC mechanism.

In Spring Boot 3.x, a JAR's auto-configuration candidates are declared in:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line contains the fully qualified name of a configuration class. These classes are typically marked with `@AutoConfiguration` (a form of `@Configuration`) and `@Conditional...` conditions. `@EnableAutoConfiguration` uses the import mechanism to inspect suitable candidates; being listed as a candidate **does not mean** every bean inside it is guaranteed to be created. Metadata lists *candidates*; conditions decide which parts are applied.

## 4. Conditions that determine default configuration

Those checks are realized using Spring Boot's annotations:

| Common condition | Meaning | Scenario |
| --- | --- | --- |
| `@ConditionalOnClass` | Applies only if one or more classes exist on the classpath | The corresponding integration library is present |
| `@ConditionalOnMissingBean` | Registers only if no matching bean exists at evaluation time | Yields to an application bean |
| `@ConditionalOnBean` | Applies only if a required bean already exists | Adds parts that depend on another piece of infrastructure |
| `@ConditionalOnProperty` | Checks a property value; can use `havingValue`/`matchIfMissing` | Allows enabling/disabling features via configuration |
| `@ConditionalOnWebApplication` | Applies only in the matching web application type | Distinguishes servlet/reactive setups |

A typical decision tree:

```text
Is the corresponding library on the classpath?
  ├─ No -> skip the configuration requiring that library
  └─ Yes
      Are the application type and required properties right?
        ├─ No -> skip
        └─ Yes
            Has the application declared a bean that takes priority?
              ├─ Yes -> default bean with @ConditionalOnMissingBean is not registered
              └─ No -> default bean is registered
```

Notes:

- `@ConditionalOnMissingBean` does not mean **every** bean provided by Boot can be replaced in the exact same way. You must inspect the specific condition of the relevant configuration.
- Bean conditions are evaluated against bean definitions already processed at that moment. Therefore `@ConditionalOnBean`/`@ConditionalOnMissingBean` should generally be placed in auto-configuration, which is processed after user configuration, rather than arbitrarily on ordinary `@Configuration` classes.
- `@ConditionalOnProperty` does not inherently mean "only enabled when the value is `true`": default semantics, `havingValue`, and `matchIfMissing` must be read per annotation.
- The presence of a dependency is an **input signal**, not a mandatory command to create beans. Remaining conditions and user configuration still take effect.

## 5. Distinguishing starters, auto-configuration, and application configuration

These three concepts often go together, but they are not identical:

- **Starter** is a convenient dependency, typically bundling required libraries. Adding `spring-boot-starter-web` brings web-related components onto the classpath; the starter itself is not a bean creator.
- **Auto-configuration** contains conditional configuration logic. When the required dependencies and suitable environment are present, it contributes bean definitions for the Spring container to use.
- **Application configuration** is what the developer explicitly defines: `@Bean`, `@Component`, property settings, etc. This part expresses actual requirements and can cause corresponding defaults to back off.

You can think of it as: **starters bring the tools in**, **auto-configuration checks conditions to install defaults**, and **Spring Framework manages and operates the installed components**. This analogy is only for mental framing; the actual conditions and mechanisms remain annotations, imports, and the container.

## 6. Runnable example: default bean yields to an application-declared bean

Minimal example using **Java 17, Spring Boot 3.3.13, Maven**; no web server needed. We create a `Greeter` supplied by auto-configuration when the application has not declared a bean of this type, then enable an application bean via a property.

File structure:

```text
boot-auto-config-role/
├── pom.xml
└── src/main/
    ├── java/
    │   ├── demo/
    │   │   ├── DemoApplication.java
    │   │   └── Greeter.java
    │   └── autoconfig/
    │       └── GreeterAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

**`pom.xml`**

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
    <artifactId>boot-auto-config-role</artifactId>
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

**`src/main/java/demo/Greeter.java`**

```java
package demo;

public interface Greeter {
    String greet();
}
```

**`src/main/java/demo/DemoApplication.java`**

```java
package demo;

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
    ApplicationRunner showGreeter(Greeter greeter) {
        return args -> System.out.println("GREETING: " + greeter.greet());
    }

    @Bean
    @ConditionalOnProperty(name = "demo.custom-greeter", havingValue = "true")
    Greeter applicationGreeter() {
        return () -> "from application";
    }
}
```

`ApplicationRunner` receives the `Greeter` bean via DI and prints the result after the application starts. `applicationGreeter()` is only registered when the property `demo.custom-greeter=true`.

**`src/main/java/autoconfig/GreeterAutoConfiguration.java`**

```java
package autoconfig;

import demo.Greeter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(Greeter.class)
public class GreeterAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(Greeter.class)
    Greeter defaultGreeter() {
        return () -> "from auto-configuration";
    }
}
```

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

```text
autoconfig.GreeterAutoConfiguration
```

Place `autoconfig` **outside the `demo` package** so the auto-configuration class is loaded via the `.imports` file rather than accidentally falling into the application's component scan. Real projects usually place auto-configuration in a separate library JAR; placing it in the same project here is only to keep the example short and self-contained.

In the directory containing `pom.xml`, with JDK 17+ and Maven available:

```bash
mvn -q -DskipTests package
java -jar target/boot-auto-config-role-0.0.1-SNAPSHOT.jar
```

Besides Spring Boot's startup logs, the program outputs the line:

```text
GREETING: from auto-configuration
```

In this run, the property is not enabled; `applicationGreeter()` does not create a bean. Auto-configuration sees `Greeter` on the classpath and no existing `Greeter` bean, so the `defaultGreeter()` definition is registered.

Next, run:

```bash
java -jar target/boot-auto-config-role-0.0.1-SNAPSHOT.jar --demo.custom-greeter=true
```

The output line is:

```text
GREETING: from application
```

This time `applicationGreeter()` registers the application's bean before the auto-configuration condition for `defaultGreeter()` is evaluated. Because a `Greeter` bean already exists, `@ConditionalOnMissingBean(Greeter.class)` is not satisfied and the default bean **is not registered**. Spring Framework still performs DI for `ApplicationRunner` as usual in both runs.

**What the example proves:** Boot helps provide default choices; Spring IoC executes the selected bean definitions; the application can still intervene with explicit configuration. This lesson does not depend on having a web server.

## 7. When you want to control or investigate auto-configuration

### 7.1. Change configuration via properties

Find the exact property supported by the specific feature before creating a replacement bean yourself. In the program above, `demo.custom-greeter` is a property **defined by the example itself** via `@ConditionalOnProperty`; it is not a default Spring Boot property. Auto-configurations that support properties can let you change timeouts, endpoints, or operating modes without replacing the entire configuration.

### 7.2. Declare a bean explicitly

When the default does not meet requirements, create the application's own bean with the appropriate type and name. Check the `@ConditionalOnMissingBean` condition of the relevant configuration: some conditions check by **type**, some by **name**, and some configurations do not back off in the desired scenario. Adding an arbitrary bean does not guarantee "disabling" every auto-configuration.

### 7.3. Exclude a specific auto-configuration

For auto-configuration classes valid in the Boot version being used, you can exclude them with:

```java
@SpringBootApplication(excludeName = "autoconfig.GreeterAutoConfiguration")
public class DemoApplication {
    // Example illustrating the excludeName attribute; does not replace the runnable class in section 6.
}
```

Or use a property:

```properties
spring.autoconfigure.exclude=autoconfig.GreeterAutoConfiguration
```

**Consequence warning:** if you exclude `GreeterAutoConfiguration` without creating another `Greeter`, the example will fail to start because `showGreeter(Greeter greeter)` lacks a dependency. Excluding means dropping the default source; it does **not** mean automatically having an alternative source. For official Boot auto-configurations, look up the exact class name for the version you are using.

### 7.4. Inspect which conditions matched

For the example JAR:

```bash
java -jar target/boot-auto-config-role-0.0.1-SNAPSHOT.jar --debug
```

Boot will print the **Conditions Evaluation Report** along with startup logs. Look for `GreeterAutoConfiguration` and the *Positive matches* / *Negative matches* sections to see why conditions matched or did not match. You can also run with `--demo.custom-greeter=true` to compare.

When debugging a real project, ask questions in order: is the dependency present, which properties are in effect, what type of context is it, has a bean with the same type/name already been declared, and is the configuration excluded. These are more direct causes than guessing that Boot "failed to scan the class".

## 8. Common misconceptions and mistakes

1. **"Spring Boot replaces Spring Framework."** False: Boot runs on top of Spring Framework and reuses `ApplicationContext`, DI, bean configuration, and the Framework's modules.
2. **"Adding a starter guarantees every bean is present."** False: starters primarily bundle dependencies; auto-configuration still has to pass conditions.
3. **"Auto-configuration is component scanning."** False: the auto-configuration list is loaded via the import/metadata mechanism; component scan is the mechanism for discovering application components.
4. **"With `@ConditionalOnMissingBean`, a custom bean always wins."** Not always true: the condition must be placed properly, and type/name and bean definition processing order matter. This is why auto-configurations are normally processed after application configuration.
5. **"Enabling debug fixes the configuration."** `--debug` mainly provides diagnostic information about conditions; it does not fix missing dependencies or beans on its own.
6. **"You can copy Boot's internal auto-config code directly and edit it."** This often creates coupling to implementation details. Prefer properties, intentional bean overrides, or appropriate `exclude`; only write your own auto-configuration when genuinely developing a library/starter.
7. **"A default configuration not being applied is a Spring IoC bug."** Usually you need to check the classpath/conditions first: IoC can only instantiate and inject bean definitions that were validly registered.

## 9. How to apply this when designing applications

When adding a feature based on Spring Boot, you can follow this sequence:

1. Identify the required functionality and add the right dependencies/starters.
2. Start up with minimal configuration; verify the actual beans and behavior.
3. Use properties for options supported by the module; specify configuration per environment.
4. Declare your own beans only when you need intervention beyond available properties.
5. If there are conflicts or missing beans, read the Conditions Evaluation Report and inspect the relevant auto-configuration's conditions.
6. Exclude the right auto-configuration class if you genuinely do not use that mechanism, while ensuring the application still has the required dependencies.

**Design principle:** let Boot reduce repetitive work, while business, security, performance, and real integration decisions must still be configured, tested, and owned within the application.

## 10. Comprehension self-check

- If a starter is added but the corresponding auto-configuration does not run, name at least three types of conditions to check.
- In the `Greeter` example, why can the `GREETING` output line change without editing `ApplicationRunner`? Distinguish the role of Boot conditions from Framework DI.
- What happens if `GreeterAutoConfiguration` is excluded without an application `Greeter` bean?
- Why should a library's auto-configuration class be declared in `.imports` and placed outside the normal component scan package?

**Suggested answers:** check classpath, properties, application type, existing beans, and exclusions; the two configurations only change which bean is registered while `ApplicationRunner` still depends on the `Greeter` interface; excluding without a replacement causes a missing bean error; import metadata lets Boot intentionally select conditional configurations, avoiding accidental scanning and dependence on the application's package.

## References

- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Framework, *Using the `@Configuration` annotation*: https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html
