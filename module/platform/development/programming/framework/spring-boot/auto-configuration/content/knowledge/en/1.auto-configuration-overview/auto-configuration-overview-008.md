# Three misconceptions about Spring Boot Auto-configuration

## Goal and context

In Spring Boot, `auto-configuration` registers default configurations and beans for a Spring application based on what the application already has: libraries on the classpath, developer-declared beans, configuration properties, application type, and other conditions. It reduces manual configuration, yet does not promise that every feature is enabled.

Three easy-to-encounter misconceptions:

1. **"Adding a starter always provides the corresponding beans."** False: a starter is primarily a convenient dependency bundle; beans are created only when configuration and conditions match.
2. **"All auto-configurations are enabled."** False: configurations are candidates for consideration; many are skipped because conditions do not match or because the application supplied its own beans.
3. **"Spring Boot replaces Spring Framework."** False: Boot builds on Spring Framework, using the very same IoC container, dependency injection, and Spring's foundational mechanisms.

What must be distinguished is **library present**, **auto-configuration class discovered**, **conditions matched**, and **bean actually registered**. These four states are not equivalent.

## 1. Understanding the chain from dependency to bean

A useful reasoning chain:

~~~text
Add starter/dependency in Maven or Gradle
    ↓
Libraries and classes appear on the classpath
    ↓
Spring Boot discovers registered auto-configuration classes
    ↓
Evaluate conditions on the configuration and/or @Bean method
    ↓
Conditions match → default bean definition can be registered
Conditions do not match → that bean is not registered
    ↓
Spring IoC container manages and injects the actually created beans
~~~

In a typical application, `@SpringBootApplication` includes enabling auto-configuration, scanning components within the appropriate package scope, and marking the root configuration class. Specifically, **component scanning** discovers the application's `@Component`/`@Service`/`@Repository` classes; **auto-configuration** uses configuration classes registered via a separate mechanism. These are two ways of introducing bean definitions into the Spring context that can operate together in one application.

A starter such as `spring-boot-starter-data-jpa` adds a commonly used group of dependencies for JPA. That is not equivalent to Spring Boot guaranteeing it can create `DataSource`, `EntityManagerFactory`, and every related bean in every environment. For instance, an application missing connection settings and an embedded database may fail to start because it cannot configure `DataSource`; another case may already have a user-defined bean causing Boot to back off on part of the configuration. Do not infer bean state solely from a starter name in `pom.xml`.

### Common condition types

| Condition | Question checked | Typical impact |
| --- | --- | --- |
| `@ConditionalOnClass` | Are required classes/libraries on the classpath? | Without the library, skip the related configuration. |
| `@ConditionalOnMissingBean` | Is there no matching bean in the context at evaluation time? | Allows using the application's bean instead of the default. |
| `@ConditionalOnBean` | Does a prerequisite bean already exist? | Adds configuration only when the prerequisite exists. |
| `@ConditionalOnProperty` | Does the property have a matching value? | Allows toggling or selecting a feature via configuration. |
| `@ConditionalOnWebApplication` | Is this a matching web environment? | Avoids registering web beans in non-web applications. |

Conditions can sit on both configuration classes and `@Bean` methods, and multiple conditions can be combined. `@ConditionalOnMissingBean` is not a rule that "whichever bean has the same name makes Boot always win/lose": behavior depends on **bean type**, name/qualifier if specified, search scope, and bean definition registration order. When writing your own auto-configuration, place conditions as recommended by Spring Boot and let auto-configuration run after application-declared bean definitions.

## 2. First misconception: "Adding a starter always creates beans"

**Fact:** starters solve dependency selection; auto-configuration is what decides default bean registration and is usually conditional.

Suppose you want to use an integration component:

- Adding a starter brings the appropriate APIs and implementations onto the classpath.
- If a required class is missing, a configuration guarded by `@ConditionalOnClass` will not apply.
- If a property disables the feature, a configuration guarded by `@ConditionalOnProperty` will not apply.
- If the application has already defined a bean of the same type and the default configuration uses `@ConditionalOnMissingBean`, the default configuration can back off.
- If conditions pass yet the bean needs another missing dependency, context creation can still fail; **matching conditions do not guarantee the entire application starts successfully**.

A familiar example: adding the web starter brings dependencies for Spring MVC and an embedded server under suitable configuration, but does not create business controllers for you; you still have to write controllers or register handlers. Likewise, adding the JPA starter does not create business entities or repositories out of thin air.

**How to verify:** inspect the dependency tree to see which libraries are actually present, then inspect the condition evaluation report and the bean list in `ApplicationContext` to see what was activated. The dependency tree only answers questions about the classpath; it does not prove a bean exists.

## 3. Second misconception: "All auto-configurations are enabled"

**Fact:** Boot discovers many *candidate* auto-configuration classes and then filters them by conditions. A class appearing in the candidate list does not mean it registered any beans.

For example, an application running only batch or command-line workloads normally does not satisfy conditions specific to servlet web applications. Even inside a web application, one configuration group may match while another does not due to a missing dependency or property. An auto-configuration can also match at the class level while a `@Bean` inside it is excluded by a method-level condition.

Do not interpret `Negative matches` in the report as errors: that is usually the normal outcome of selective filtering. Nor should you treat `Positive matches` as a guarantee that every expected bean initialized cleanly. To draw conclusions about beans, check the context and any startup errors.

Ways to control intentionally:

1. **Configure properties** when an auto-configuration supports specific toggle properties; look up the exact property in the documentation for your version.
2. **Provide custom beans** so Boot backs off at points carrying `@ConditionalOnMissingBean`. Do not assume every default bean allows overriding in this way.
3. **Exclude an auto-configuration** with `@SpringBootApplication(exclude = ...)`, `excludeName`, or `spring.autoconfigure.exclude`. Use the exact auto-configuration class name for the current version and understand the scope of exclusion; this is not removing a dependency from the classpath.

Example exclusion configuration by class name when genuinely needed:

~~~properties
# Syntax example; replace with a real fully qualified name from the running version.
spring.autoconfigure.exclude=com.example.autoconfigure.UnwantedAutoConfiguration
~~~

The snippet above only illustrates property structure; `com.example.autoconfigure.UnwantedAutoConfiguration` is not a built-in Spring Boot class. In a real application, find the class to exclude in the condition report or corresponding documentation.

## 4. Practice on Java 17+: default, custom, and absent bean

This example creates **an auto-configuration supplied by the sample application itself**, letting you observe all three outcomes directly without depending on external services. It uses Spring Boot 4.1.2, Maven, and Java 17+. The illustrated APIs also demonstrate modern auto-configuration mechanics: registration via `AutoConfiguration.imports`, property conditions, and backing off when a user bean is present.

Create the file structure:

~~~text
auto-config-myths/
├── pom.xml
└── src/main/
    ├── java/
    │   ├── com/example/demo/DemoApplication.java
    │   ├── com/example/demo/GreetingService.java
    │   └── com/example/autoconfig/GreetingAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>auto-config-myths</artifactId>
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

File `src/main/java/com/example/demo/GreetingService.java`:

~~~java
package com.example.demo;

public interface GreetingService {
    String message();
}
~~~

File `src/main/java/com/example/autoconfig/GreetingAutoConfiguration.java`:

~~~java
package com.example.autoconfig;

import com.example.demo.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService defaultGreetingService() {
        return () -> "AUTO";
    }
}
~~~

With `matchIfMissing = true`, omitting the `demo.greeting.enabled` property still allows the configuration to be considered. When the property is `false`, this entire configuration does not match. If the user has already registered a `GreetingService`, the default bean inside the configuration backs off.

Register the auto-configuration class in the **exact-named** file `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; the file content is a single line:

~~~text
com.example.autoconfig.GreetingAutoConfiguration
~~~

File `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

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
            prefix = "demo.greeting",
            name = "custom",
            havingValue = "true"
    )
    GreetingService customGreetingService() {
        return () -> "CUSTOM";
    }

    @Bean
    ApplicationRunner printGreeting(ObjectProvider<GreetingService> provider) {
        return args -> {
            GreetingService service = provider.getIfAvailable();
            System.out.println("GreetingService: " +
                    (service == null ? "ABSENT" : service.message()));
        };
    }
}
~~~

`ObjectProvider<GreetingService>` lets you safely query the context for a bean even when none exists. This allows running the "absent bean" scenario without triggering a `NoSuchBeanDefinitionException` from mandatory injection.

From the directory containing `pom.xml`, run:

~~~bash
mvn -q -DskipTests package

java -jar target/auto-config-myths-1.0.0.jar
java -jar target/auto-config-myths-1.0.0.jar --demo.greeting.custom=true
java -jar target/auto-config-myths-1.0.0.jar --demo.greeting.enabled=false
~~~

Ignoring startup log lines (which depend on the environment), the `System.out.println` line of each command must be respectively:

~~~text
GreetingService: AUTO
GreetingService: CUSTOM
GreetingService: ABSENT
~~~

Explanation:

| Run | Property condition | Custom bean present? | Result |
| --- | --- | --- | --- |
| Default | `enabled` absent, `matchIfMissing=true` | No | Auto-configuration provides `GreetingService` with value `AUTO`. |
| `--demo.greeting.custom=true` | Allows auto-configuration | Yes, value `CUSTOM` | `@ConditionalOnMissingBean` causes the default bean to back off. |
| `--demo.greeting.enabled=false` | Does not match | No | No `GreetingService`, prints `ABSENT`. |

**Why place the configuration in package `com.example.autoconfig`?** `DemoApplication` is in `com.example.demo`; default component scan does not scan the sibling package `com.example.autoconfig`. `GreetingAutoConfiguration` is loaded thanks to `AutoConfiguration.imports`, properly illustrating the auto-configuration mechanism. If placed inside a package scanned by component scan, the example could obscure the distinction between the two mechanisms.

**Scope of the example:** This is a sample auto-configuration we wrote ourselves, not a claim that Spring Boot includes a built-in `GreetingService` bean. The application does not need web or database starters; the core starter suffices for the example. In real library projects, auto-configuration and starters usually reside in separate modules to share across multiple applications.

## 5. Third misconception: "Spring Boot replaces Spring Framework"

**Fact:** Spring Boot uses Spring Framework to run the application. Boot adds conventions, integrations, and default configurations to reduce repetitive work.

| Responsibility | Spring Framework | Spring Boot |
| --- | --- | --- |
| IoC container, bean lifecycle, dependency injection | Direct foundation | Uses and auto-configures on top of that foundation |
| `@Configuration`, `@Bean`, `@Component`, `@Autowired` | Provides core mechanisms | Used normally as usual |
| Spring MVC, transaction handling, AOP, data integration | Provides or underpins the related ecosystem | Conveniently configures when conditions match |
| Starters and curated dependency version management | Not the focus of Spring Framework | Provides dependency descriptors and dependency management |
| Auto-configuration and application run experience | Provides configuration/condition/bean factory foundation | Selectively coordinates auto-configurations by environment |
| Operational utilities such as Actuator | Not a core Spring Framework feature | Provided via appropriate dependencies, with separate configuration |

`@SpringBootApplication` does not erase knowledge of `@Configuration`, component scan, scopes, proxies, bean lifecycle, bean qualification, or transactions. When facing two beans of the same type, circular dependencies, condition errors, or unscanned components, analyze using **Spring container** rules alongside Boot's auto-configuration layer.

You can completely write manual Spring configuration in a Boot application. For example, declare `@Bean` for specific components, override values via `@ConfigurationProperties`, use Spring Security, Spring Data, or custom infrastructure configuration. Only keep Boot defaults when those defaults meet your needs; otherwise, adjust via supported mechanisms.

## 6. Diagnosing when results differ from expectations

When "the starter was added, yet the bean is still missing" or "why didn't the default bean appear", proceed sequentially:

1. **Identify the exact bean type and expected conditions.** Check the bean by exact type and name; do not infer from the starter name. Distinguish a missing bean from an existing bean injected with the wrong qualifier.
2. **Check actual dependencies.** Run `mvn dependency:tree` or `./gradlew dependencies`, and inspect the classpath and excluded dependencies. Having a starter does not guarantee every needed dependency is present if the project overrode/excluded it.
3. **Read the condition evaluation report.** Run the application with `--debug`; locate the auto-configuration name and positive/negative match reasons. Read reports only from the exact version and runtime environment.
4. **Inspect properties/profiles/environment.** Settings in `application.yml`, `application.properties`, profiles, environment variables, and command-line arguments can change condition outcomes. A misspelled property or one belonging to a different auto-configuration will have no effect.
5. **Look for manually declared beans.** `@Bean`, `@Component`, or another auto-configuration can cause `@ConditionalOnMissingBean` not to match. When using test slices or custom contexts, the bean/auto-configuration set may also differ from the main application.
6. **Distinguish skip reasons from initialization errors.** If a configuration was skipped due to an unmatched condition, there is usually no bean to create; if conditions matched yet a dependency failed during bean creation, read the exception chain and root cause.
7. **Exclude only when you understand the consequences.** `spring.autoconfigure.exclude` removes the specified auto-configuration class; it does not remove libraries from the classpath and does not replace fixing misconfigured properties/beans.

If Spring Boot Actuator is added and access to the appropriate endpoint is allowed, the `conditions` endpoint also helps inspect the condition report. Whether the endpoint exists, is exposed, or is secured depends on configuration and version; do not assume it is always accessible.

In the example above, you can run:

~~~bash
java -jar target/auto-config-myths-1.0.0.jar --debug
~~~

Find `GreetingAutoConfiguration` and `defaultGreetingService` in the condition report. Compare with runs enabling `custom` or disabling `enabled` to see which conditions flipped from match to mismatch. Exact log formatting can vary by Spring Boot version.

## 7. Practical mistakes and how to fix them

**Mistake: "Seeing `spring-boot-starter-...` in Maven means I can `@Autowired` any interface from the library."** An interface on the classpath is not yet a bean. Find the implementation class or bean-creating configuration, and check component scan and the condition report.

**Mistake: "`Negative matches` means auto-configuration is broken."** Unmatched conditions are the normal mechanism to avoid enabling unnecessary integrations. Treat it as an issue only if the application requires that functionality.

**Mistake: "If my bean exists, Boot always turns off every configuration in the same domain."** Boot usually backs off only at points with matching conditions. A custom bean may replace one default while auxiliary beans are still registered; check each class/method condition.

**Mistake: "No need to learn Spring anymore because I use Boot."** Debugging dependency injection, scopes, proxies, lifecycle, MVC, and transactions still requires understanding Spring Framework. Auto-configuration only reduces repetitive setup.

**Mistake: "Just excluding the entire auto-configuration solves it."** Overly broad exclusions can drop beans needed by other features. Prefer tuning published properties, providing your own bean, or fixing actual dependencies before excluding.

## 8. Comprehension self-check

1. Why is adding a starter not enough to conclude a bean was created? — Because a starter primarily adds dependencies; bean registration depends on conditions and application configuration.
2. When is `@ConditionalOnMissingBean` useful? — When an auto-configuration author wants to provide a default value while letting the application supply a suitable bean itself.
3. Does a report with many `Negative matches` necessarily indicate an error? — No. It can be the normal outcome of conditional filtering.
4. Why does `@SpringBootApplication` not replace knowledge of the IoC container? — Because Boot still relies on Spring Framework's container and bean lifecycle.
5. What should be inspected to distinguish "missing library", "property disabled", and "default bean backed off"? — Dependency tree, condition evaluation report, property sources, and beans in the context.

## Official reference documentation

- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — Build Systems / Starters: https://docs.spring.io/spring-boot/reference/using/build-systems.html

**Remember:** Starters bring libraries into the project; auto-configuration conditions decide which default configurations are applied; Spring Framework remains the foundation creating and managing beans underneath Spring Boot.