# @SpringBootApplication Combines Application Configuration, Component Scanning, and Auto-Configuration

## 1. Lesson Objectives

In a Spring Boot application, the startup class is usually very short:

```java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

A single annotation here performs the role of **three configuration groups**:

1. Marks the root class as **application configuration** so Spring can read bean definitions provided by the application.
2. Enables **component scanning** to find components in the appropriate packages.
3. Enables **auto-configuration** so Spring Boot evaluates default configurations based on libraries, the environment, and existing beans.

Understanding these three roles accurately explains why a `@Service` is injected, why a `@Bean` method is processed, and why a `JdbcTemplate` or `DataSource` can appear even when the application has not written a configuration class for it.

Key point to remember: `@SpringBootApplication` **does not create every bean immediately by itself**. It provides the entry point for Spring to parse configuration and register bean definitions; `ApplicationContext` and `BeanFactory` manage object creation, dependency resolution, and the bean lifecycle.

## 2. The Three Annotations That Compose @SpringBootApplication

In terms of primary functionality, you can read:

```java
@SpringBootApplication
```

as the combination of:

```java
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
```

This is a way of **explaining the three core roles**, not a promise that replacing the single annotation directly with those three lines will always preserve every attribute alias and default filter. `@SpringBootApplication` has its own integration details, such as filters related to component scanning and forwarded attributes.

| Component | Responsibility | Typical Input | Result |
| --- | --- | --- | --- |
| `@SpringBootConfiguration` | Root configuration of the application | Startup class along with `@Bean`/`@Import` methods | Bean definitions from explicit configuration |
| `@ComponentScan` | Application component discovery | Root package and subpackages | Bean definitions for `@Component`, `@Service`, `@Controller`, `@Repository`, `@Configuration`, etc. |
| `@EnableAutoConfiguration` | Activates auto-configuration selection | Classpath, properties, web/non-web application type, existing bean definitions | Default configurations/beans **when conditions match** |

All three paths feed their results into **the same Spring IoC container**. Bean definitions from different sources are still processed by Spring Framework using a consistent bean management mechanism.

### 2.1. @SpringBootConfiguration: the root class is Spring configuration

`@SpringBootConfiguration` is a Boot-specific annotation meta-annotated with `@Configuration`. Therefore, a class annotated with `@SpringBootApplication` can declare `@Bean`, `@Import`, and standard Spring configuration elements:

```java
@SpringBootApplication
public class DemoApplication {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

This snippet illustrates `@Bean` semantics and requires importing `java.time.Clock`, `org.springframework.context.annotation.Bean`, and the Boot annotations to use in a real program. Spring parses the `applicationClock()` method into a bean definition; for a default singleton, the bean is created when the container needs to instantiate it.

Important points:

- `@Bean` is configuration **explicitly declared by the application**; it is not auto-configuration merely because it is placed in the Boot class.
- The root class usually contains only `main()` and small configuration pieces; configuration groups can be separated into other `@Configuration` classes for maintainability.
- Spring Boot uses `@SpringBootConfiguration` as the root configuration marker. Some Boot testing mechanisms can search upward through packages to locate this root class.
- `@SpringBootApplication` supports the `proxyBeanMethods` attribute. Its default value is `true`; when you need to avoid proxying inter-`@Bean` method calls, you can use `proxyBeanMethods=false`. You should not manually invoke a `@Bean` method as a regular Java method to replace dependency injection.

### 2.2. @ComponentScan: discovering application components

`@ComponentScan` finds eligible classes within the scanned package scope and registers bean definitions, for example:

```java
@Service
public class PriceService {
    public int applyDiscount(int price) {
        return price - 10;
    }
}
```

Stereotypes such as `@Service`, `@Repository`, and `@Controller` are specializations or meta-annotations of `@Component`. A `@Configuration` class within the scan scope can also be discovered and contribute beans from its `@Bean` methods.

**Default scope:** Spring starts scanning from the package containing the class annotated with `@SpringBootApplication` and its subpackages. Therefore, the location of the main class is an important code-organization decision.

Example of a suitable package structure:

```text
com.example.store
├── StoreApplication.java          (@SpringBootApplication)
├── config
│   └── PaymentConfiguration.java  (@Configuration)
├── service
│   └── OrderService.java          (@Service)
├── repository
│   └── OrderRepository.java       (@Repository)
└── web
    └── OrderController.java       (@RestController)
```

If `StoreApplication` is located in `com.example.store`, the classes above belong to subpackages and can be scanned. If `StoreApplication` is placed deeper in `com.example.store.launcher`, then `com.example.store.service` becomes a **sibling package**, outside the default scan scope.

Be sure to distinguish:

- **A class being on the classpath** does not mean **component scan will register that class**; the class must reside within the scan scope or be brought into the container through another mechanism.
- **Being scanned** does not guarantee a bean is created successfully; missing dependencies, `@Profile` conditions, conflicting configurations, or initialization errors can still prevent startup.
- `@Bean` methods in a configuration class are only processed when that configuration class is actually brought into the configuration system via scanning, `@Import`, or another valid registration mechanism.

### 2.3. @EnableAutoConfiguration: activating conditional default configuration

`@EnableAutoConfiguration` is the mechanism that causes Boot to select auto-configuration classes conditionally. In Spring Boot 3.x, JARs that provide auto-configuration typically declare candidates in:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

This file contains the **fully qualified class names** of auto-configuration classes. This is a candidate registration mechanism distinct from scanning the application's `@Component` classes.

Conceptual example:

```java
@AutoConfiguration
@ConditionalOnClass(RemoteClient.class)
class RemoteClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RemoteClient.class)
    RemoteClient remoteClient() {
        return new RemoteClient();
    }
}
```

`RemoteClient` in the example is a hypothetical class, so this snippet only illustrates conditions and is not standalone Java code. It expresses: when the required class is present and no corresponding bean exists yet, the configuration can provide a default bean. If a condition is not satisfied, that bean definition may **not be registered**.

Common conditions include:

- `@ConditionalOnClass`: a class/library is present on the classpath.
- `@ConditionalOnMissingBean`: no matching bean exists at the time the condition is evaluated.
- `@ConditionalOnBean`: a required bean is present.
- `@ConditionalOnProperty`: a configuration property satisfies the requirement.
- `@ConditionalOnWebApplication`: the context is of an appropriate web application type.

There is no rule that "adding a dependency guarantees Boot will create the bean". Auto-configuration also depends on other conditions, properties, application type, exclusions, and beans declared by the application itself.

## 3. Three Mechanisms Converging in One ApplicationContext

Consider the different bean sources:

```text
                      @SpringBootApplication
                                |
             +------------------+--------------------+
             |                  |                    |
             v                  v                    v
  @SpringBootConfiguration  @ComponentScan  @EnableAutoConfiguration
  Explicit application      Component       Conditional
  configuration             discovery       auto-configuration selection
             |                  |                    |
             +------------------+--------------------+
                                |
                                v
                       BeanDefinitionRegistry
                   (register bean definitions)
                                |
                                v
                    ApplicationContext / BeanFactory
                     (DI, instantiation, lifecycle)
                                |
                                v
                         Bean instances
```

The diagram only illustrates how responsibilities combine. In practice, Spring performs multiple steps for `@Configuration` processing, import selectors, `BeanDefinitionRegistryPostProcessor`, condition evaluation, and bean initialization.

**Conceptual timeline:**

1. `SpringApplication.run(...)` prepares the `Environment`, determines the appropriate context type, and adds the application class as a configuration source.
2. During `refresh()`, Spring processes configuration classes, component scans, and imports, then registers valid bean definitions.
3. Auto-configurations are selected during the configuration processing phase based on active conditions; matching default beans are registered.
4. Spring resolves dependencies, runs processors, and initializes non-lazy singletons at the appropriate stage.
5. After the context refreshes successfully, Boot invokes registered `ApplicationRunner`/`CommandLineRunner` beans and reaches the ready state.

Therefore, `@ComponentScan` and `@EnableAutoConfiguration` typically supply **different sets of bean definitions**, yet beans produced by the two mechanisms can depend on one another. For example, an application `@Service` receives a `JdbcTemplate` auto-configured by Boot without needing two separate containers.

## 4. Runnable Example: Three Bean Sources in the Same Application

The example uses **Java 17 or higher, Spring Boot 3.3.13, and Maven**. The application does not start a web server; we add `spring-boot-starter-jdbc` along with the H2 embedded database so Boot can auto-configure `DataSource` and `JdbcTemplate`.

We will have:

- `@SpringBootApplication`: provides the startup class and an `ApplicationRunner` bean.
- `@Service`: discovered via component scanning.
- `@Configuration` + `@Bean`: provides a `GreetingTemplate` defined by the application.
- `JdbcTemplate`: auto-configured by Spring Boot because the dependencies and conditions match.

### 4.1. File Structure

```text
spring-boot-annotation-demo/
├── pom.xml
└── src/main/java/example/bootlesson/
    ├── BootLessonApplication.java
    ├── config/
    │   └── GreetingConfiguration.java
    ├── model/
    │   └── GreetingTemplate.java
    └── service/
        └── GreetingService.java
```

Notice that `BootLessonApplication` is in `example.bootlesson`, which is the **parent package** of the remaining classes. As a result, default component scanning finds `GreetingConfiguration` and `GreetingService` without manually specifying packages.

### 4.2. pom.xml

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
    <artifactId>spring-boot-annotation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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

`spring-boot-starter-jdbc` brings the required JDBC components, `JdbcTemplate`, DataSource, and connection pool onto the classpath; H2 lets Boot detect an embedded database without requiring an external database URL. A starter only brings in dependencies; **auto-configurations evaluate conditions to register beans**.

### 4.3. Application-Defined Model

**`src/main/java/example/bootlesson/model/GreetingTemplate.java`**

```java
package example.bootlesson.model;

public record GreetingTemplate(String prefix) {
    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
```

This is a plain Java 17 record; **it has no `@Component`**. It is not yet a Spring bean unless registered through configuration.

### 4.4. Bean from Application Configuration

**`src/main/java/example/bootlesson/config/GreetingConfiguration.java`**

```java
package example.bootlesson.config;

import example.bootlesson.model.GreetingTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GreetingConfiguration {

    @Bean
    GreetingTemplate greetingTemplate() {
        return new GreetingTemplate("Xin chào");
    }
}
```

`GreetingConfiguration` is a scanned configuration component. Spring processes `@Bean greetingTemplate()` and registers a bean definition; `GreetingTemplate` becomes a bean when the container creates it.

`proxyBeanMethods=false` is appropriate here because the `@Bean` methods do not call one another. If another bean is genuinely needed inside the configuration, it can be injected via `@Bean` method parameters or constructor injection rather than calling the method directly, avoiding confusion with a plain Java call.

### 4.5. Service Discovered via Component Scanning

**`src/main/java/example/bootlesson/service/GreetingService.java`**

```java
package example.bootlesson.service;

import example.bootlesson.model.GreetingTemplate;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final GreetingTemplate template;

    public GreetingService(GreetingTemplate template) {
        this.template = template;
    }

    public String hello(String name) {
        return template.greet(name);
    }
}
```

`@Service` makes the class a component scan candidate. Spring creates `GreetingService` and injects the `GreetingTemplate` supplied by application configuration. This is a clear example of **constructor injection**, rather than calling `new GreetingService(...)` manually.

### 4.6. Root Class and Bean Created by Auto-Configuration

**`src/main/java/example/bootlesson/BootLessonApplication.java`**

```java
package example.bootlesson;

import example.bootlesson.service.GreetingService;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class BootLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootLessonApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(GreetingService service, JdbcTemplate jdbc) {
        return args -> {
            System.out.println("APP_CONFIG: " + service.hello("Spring Boot"));
            String value =
                jdbc.queryForObject("SELECT 'JdbcTemplate active'", String.class);
            System.out.println("AUTO_CONFIG: " + value);
        };
    }
}
```

Here, three mechanisms work together:

1. The root `@SpringBootApplication` class has a `@Bean demonstrate(...)` method, meaning the `ApplicationRunner` bean originates from **application configuration**.
2. `GreetingService` and `GreetingConfiguration` in subpackages are discovered by component scan; `GreetingConfiguration` in turn declares `GreetingTemplate` via `@Bean`.
3. Spring Boot uses the classpath and JDBC auto-configuration conditions to provide `DataSource` and `JdbcTemplate`. `ApplicationRunner` receives `JdbcTemplate` via DI like any other bean.

**Running the program:**

```bash
mvn -q -DskipTests package
java -jar target/spring-boot-annotation-demo-0.0.1-SNAPSHOT.jar --spring.main.web-application-type=none
```

Besides the banner and startup logs, the program prints these exact two lines produced by `ApplicationRunner`:

```text
APP_CONFIG: Xin chào, Spring Boot!
AUTO_CONFIG: JdbcTemplate active
```

**Why does it produce this output?**

- `APP_CONFIG`: `GreetingService` receives `GreetingTemplate("Xin chào")`; `hello("Spring Boot")` produces the corresponding greeting.
- `AUTO_CONFIG`: H2 executes a SQL query selecting a constant string, so `JdbcTemplate#queryForObject(...)` returns `JdbcTemplate active`.
- `ApplicationRunner` is invoked by Boot after the context refreshes successfully. Because `spring-boot-starter-web` is absent, the application runs in non-web mode and does not need to open an HTTP port.

When observing this example, the point to prove is not that every starter behaves identically, but that **beans from application configuration, component scan, and auto-configuration are all managed and injected by Spring IoC through one unified mechanism**.

## 5. What Do scanBasePackages and scanBasePackageClasses Change?

When the main class cannot be placed in the parent package, `@SpringBootApplication` can explicitly specify component scanning packages:

```java
@SpringBootApplication(scanBasePackages = {
    "example.bootlesson.service",
    "example.bootlesson.config"
})
public class BootLessonApplication {
}
```

Or select packages by type to avoid typo-prone strings:

```java
@SpringBootApplication(scanBasePackageClasses = {
    GreetingService.class,
    GreetingConfiguration.class
})
public class BootLessonApplication {
}
```

These two snippets illustrate annotation attributes and assume the appropriate classes/imports exist; they do not replace the full `BootLessonApplication.java` file in the earlier runnable example.

`scanBasePackages` is an alias forwarded to `@ComponentScan(basePackages = ...)`, while `scanBasePackageClasses` forwards to `@ComponentScan(basePackageClasses = ...)`.

**Crucial limitation:** these two attributes affect **component scan**. They do **not** simultaneously alter every other scanning scope:

- They do not change the default JPA entity scanning scope controlled by `@EntityScan`.
- They do not directly change the Spring Data repository scanning scope controlled by `@Enable...Repositories` annotations.
- They do not turn the list of JAR auto-configurations into component scan targets.
- They should not be used as a blanket replacement for consistent application package organization.

Spring Boot also has the concept of an **auto-configuration package**, typically tied to the package of the class enabling `@EnableAutoConfiguration`. Some auto-configurations use this root package information to set up relevant features. Therefore, changing `scanBasePackages` may fix scanning for `@Service`, but it may not properly handle entities/repositories if they are placed outside the root package.

**Easiest package layout to maintain:** place the `@SpringBootApplication` class in the application's root package, and place `config`, `service`, `repository`, `web`, and `domain` areas in subpackages. If you intentionally split modules/packages specially, configure each mechanism according to its own responsibility.

## 6. When Do You Need @Import or Explicit Configuration?

Not every configuration must be scanned. `@Import` lets you bring a specific configuration class into the Spring system without widening the scan scope too broadly:

```java
@Configuration(proxyBeanMethods = false)
@Import(ExternalPaymentConfiguration.class)
class PaymentFeatureConfiguration {
}
```

This is an illustrative snippet: `ExternalPaymentConfiguration` is a hypothetical name and requires a real class/import. When `PaymentFeatureConfiguration` is processed by Spring, `@Import` brings the referenced configuration into the bean definition registration process.

Comparison:

| Scenario | Usually Appropriate Mechanism |
| --- | --- |
| Discovering services/controllers/repositories owned by the application within the package tree | Component scanning |
| Creating beans when a factory method is needed or for third-party libraries without stereotypes | `@Configuration` + `@Bean` |
| Bringing a specific configuration class from outside the package tree into context | `@Import` |
| Providing conditional defaults for a library/starter | Auto-configuration, with `@AutoConfiguration` and `.imports` metadata |
| Adjusting how an official auto-config behaves | Properties / intentional bean override / documented exclusion |

You should not add a `@ComponentScan` across all of `org.springframework` or an overly broad root package to "find" auto-configuration beans. Doing so can register unintended components, cause conflicts, or make startup unpredictable.

## 7. How Does Auto-Configuration Back Off for the Application?

Suppose an auto-configuration has this logic:

```java
@AutoConfiguration
class SampleAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Formatter.class)
    Formatter defaultFormatter() {
        return new Formatter("default");
    }
}
```

`Formatter` here is an illustrative type; the snippet is not standalone. When the application has already registered a matching `Formatter` bean before the condition is checked, `defaultFormatter()` may **not be registered**. This is **back-off** behavior, a common design choice that allows applications to replace defaults.

Distinguish three situations:

| Mechanism | Effect | Does It Delete Another Bean? |
| --- | --- | --- |
| `@ConditionalOnMissingBean` | Decides whether to register a default bean | No default definition needs to be created when the condition does not match |
| `@Primary` | Prioritizes one bean when multiple autowire candidates match by type | No |
| Bean definition overriding | A definition with a duplicate name replaces another definition if permitted | Can replace a bean definition with the same name |

Spring Boot generally disables bean definition overriding by default. Do not confuse back-off with Boot silently overwriting application beans.

**Note on ordering:** conditions that depend on existing bean definitions are evaluated during configuration processing. Therefore, `@ConditionalOnMissingBean` is better suited for auto-configuration than for ordinary application configuration; placing this annotation arbitrarily on an application bean does not guarantee the intended outcome if registration order differs.

## 8. Controlling Auto-Configuration Directly on @SpringBootApplication

You can exclude a **specific** auto-configuration using the annotation:

```java
@SpringBootApplication(
    exclude = org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration.class
)
public class BootLessonApplication {
}
```

Or by class name:

```java
@SpringBootApplication(
    excludeName = "org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration"
)
public class BootLessonApplication {
}
```

These two examples only illustrate the configuration syntax; **do not apply them as a replacement to the runnable program in section 4**, because excluding `JdbcTemplateAutoConfiguration` can leave `ApplicationRunner` without a `JdbcTemplate` bean.

An equivalent approach in terms of configuration intent is the property:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration
```

Limitations:

- `exclude`/`excludeName` are meant for **auto-configuration**, not as a general way to remove a `@Service` created by component scanning.
- Excluding an auto-configuration class does not automatically provide a replacement bean; dependency injection still requires the corresponding beans.
- When changing/excluding a configuration, check other auto-configurations that depend on it. For example, a missing `DataSource` can lead to a missing `JdbcTemplate`.
- Specific classes may change across Spring Boot versions; always check the exact version used by your application.

For typical customization needs, prefer official properties or explicit beans before excluding an entire major auto-configuration.

## 9. Self-Verifying Behavior at Startup

### 9.1. Enabling the Conditions Evaluation Report

Run the example with an additional option:

```bash
java -jar target/spring-boot-annotation-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none --debug
```

Look for entries related to `DataSourceAutoConfiguration` and `JdbcTemplateAutoConfiguration` in the **Conditions Evaluation Report**.

- **Positive matches**: the corresponding conditions were satisfied.
- **Negative matches**: the conditions were not satisfied; the report usually states why.
- **Exclusions**: auto-configurations excluded by configuration.

The report helps explain **why an auto-configuration was or was not applied**. It does not replace the stack trace if a bean was registered but failed during instantiation.

### 9.2. A bean is in the registry but not yet instantiated?

The distinction between a **bean definition** and an **instance** is important. Spring may have registered the bean definition but deferred creating the singleton due to `@Lazy` or because it is a prototype/special scope.

Conversely, when `@ConditionalOnMissingBean` prevents a default bean from being registered, the default bean definition may not exist at all from the start. These two situations require two different debugging approaches:

- Definition missing: check component scan, `@Import`, conditions, and exclusions.
- Definition present but bean unavailable: check lazy initialization, dependencies, factory methods, `BeanPostProcessor`, and exceptions.

You can use `ConfigurableApplicationContext#getBeanFactory()` in diagnostic tools to inspect metadata such as `containsBeanDefinition(name)` or `getBeanDefinition(name)`. Prefer constructor injection in business code rather than calling `getBean()` to manage services manually.

### 9.3. Looking from the Dependency Angle

In the section 4 example:

- If you remove `spring-boot-starter-jdbc` while still importing `JdbcTemplate`, the Java code **will not compile** because the JDBC API is no longer on the compile classpath.
- If you keep the JDBC starter without H2 and without providing a suitable database, the application can fail because it cannot configure a `DataSource`.
- If `GreetingService` is moved outside the component scanning scope without being registered another way, `ApplicationRunner` can fail due to a missing `GreetingService` bean.
- If all dependencies and packages are kept intact, Spring Boot can configure the JDBC infrastructure; `GreetingTemplate` remains application-defined.

These changes affect **different root causes**. No "magic" annotation can compensate for missing dependencies, packages, or properties.

## 10. Common Mistakes

### Mistake 1: Confusing component scanning with auto-configuration

**Symptom:** "I did not put the JDBC config package into `@ComponentScan`, so why is `JdbcTemplate` still present?"

**Explanation:** auto-configuration classes are loaded via Boot's candidate list and conditions, not by the application scanning the JDBC package. `JdbcTemplate` still ends up as a Spring bean.

### Mistake 2: Placing the main class too deep

**Symptom:** a valid `@Service` exists, yet the application reports a missing bean.

**Explanation:** default component scanning only scans from the root package downward into subpackages. Move the main class up to an appropriate parent package, explicitly configure `scanBasePackageClasses`, or use `@Import` where appropriate.

### Mistake 3: Thinking every @Bean is auto-configured by Boot

**Explanation:** `@Bean` methods written by the application team are explicit configuration. Auto-configurations are configurations conditionally registered by Boot/libraries via their own mechanism. Being managed by the same Spring container does not make their origins the same.

### Mistake 4: Having a starter but not seeing the expected bean

**Explanation:** starters typically bundle dependencies. An auto-configuration may fail to match `@ConditionalOnClass`, properties, existing beans, web context type, or may have been excluded. Use the Conditions Evaluation Report to find the specific reason.

### Mistake 5: Using scanBasePackages to fix both JPA entities and repositories

**Explanation:** `@SpringBootApplication`'s scan attributes only control component scanning. For JPA/Spring Data, check `@EntityScan`, `@EnableJpaRepositories`, and the appropriate auto-configuration package scope instead of assuming component scanning covers everything.

### Mistake 6: Using @Primary to prevent a default bean from existing

**Explanation:** `@Primary` only affects bean selection during injection. To replace a default, check whether the relevant configuration backs off by type/name when the application bean has already been declared.

### Mistake 7: Scanning packages too broadly to fix a missing bean

**Explanation:** scanning unrelated libraries or root packages can pull in unintended controllers, repositories, or beans. Identify the exact source of the needed bean and widen the scope appropriately.

### Mistake 8: Copying @SpringBootApplication onto multiple arbitrary configuration classes

**Explanation:** an application usually has one clear root class. Additional configuration groups should use `@Configuration`/`@Import`. Having multiple `@SpringBootConfiguration` classes within the scope auto-detected by tests can create root configuration ambiguity.

## 11. Designing Easy-to-Understand and Maintainable Applications

Practical workflow:

1. Place the `@SpringBootApplication` class in a root package covering most of the application code.
2. Place services/controllers/repositories in subpackages and use appropriate stereotypes.
3. Place beans created via factory methods in clearly scoped `@Configuration` classes.
4. Add dependencies/starters matching the feature; check auto-configuration before writing duplicate infrastructure configuration yourself.
5. Use properties to tune default configuration when supported by the module.
6. When a bean does not appear or is ambiguous, distinguish **scan**, **configuration**, **condition**, and **bean instantiation** before making fixes.
7. When replacing a default is needed, check `@ConditionalOnMissingBean` and the configuration contract; when excluding is needed, exclude the exact specific auto-configuration class.

Quick diagnostic table:

| Symptom | First Check | How to Verify |
| --- | --- | --- |
| `@Service` is not injected | Packages of main class and service | `@ComponentScan`, package location, `@Profile` |
| `@Bean` does not appear | Whether `@Configuration` class is processed | Component scan or `@Import` |
| Boot infrastructure bean missing | Auto-configuration conditions | `--debug`, Conditions Evaluation Report |
| Multiple beans of the same type | Candidates and selection rules | `@Qualifier`, `@Primary`, bean name |
| Definition exists but startup fails | Dependencies/constructor/init callbacks | Root cause of `BeanCreationException` |
| Changed scanBasePackages but entities still missing | JPA/Spring Data mechanisms differ from component scan | `@EntityScan`/repository configuration |

## 12. Knowledge Self-Check

**Question 1.** What roles does `@SpringBootApplication` carry?

**Answer:** Application configuration (`@SpringBootConfiguration`), component scanning (`@ComponentScan`), and enabling auto-configuration (`@EnableAutoConfiguration`).

**Question 2.** Why might a `@Service` in a sibling package to the main class not be found?

**Answer:** Because by default `@ComponentScan` starts from the package containing the class annotated with `@SpringBootApplication` and its subpackages, and does not automatically cover every package in the project.

**Question 3.** If an application has already declared a bean of the exact type that an auto-configuration with `@ConditionalOnMissingBean` intends to provide, what usually happens?

**Answer:** If the auto-configuration's condition is evaluated when the application bean has already been registered and matches the criteria, the default bean backs off, meaning it is not registered.

**Question 4.** Does adding `scanBasePackages` automatically adjust JPA entity scanning?

**Answer:** No. That attribute adjusts component scan, whereas entity/repository scanning has its own scope and configuration.

**Question 5.** In the Java 17 example, which beans come from each source?

**Answer:** `ApplicationRunner` and `GreetingTemplate` come from the application's `@Bean` methods; `GreetingService` comes from component scanning; `DataSource` and `JdbcTemplate` come from Boot auto-configuration matching conditions with the JDBC starter and H2.

**Question 6.** When an auto-configuration has a negative match, is it definitely caused by `@ComponentScan`?

**Answer:** No. Auto-configuration conditions can fail due to classpath, beans, properties, application type, or exclusions. You need to inspect the condition report and the specific reason.

## References

- Spring Boot — Using the `@SpringBootApplication` Annotation: https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Framework — Classpath Scanning and Managed Components: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
- Spring Framework — Java-based Container Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
