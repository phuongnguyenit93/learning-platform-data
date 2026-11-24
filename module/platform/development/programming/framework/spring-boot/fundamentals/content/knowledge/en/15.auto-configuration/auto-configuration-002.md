# `@EnableAutoConfiguration` and the configuration import mechanism

One of the convenient features of Spring Boot is that you can add the appropriate dependencies to a project and start using many capabilities without manually declaring every infrastructure bean. For example, when an application has the Spring MVC library, Spring Boot can configure the required web components; when a data access library and matching datasource are present, the framework can provide beans for working with the database.

This capability comes from **auto-configuration**. The `@EnableAutoConfiguration` annotation enables that mechanism. Behind the annotation, Spring uses a configuration import mechanism to locate and bring suitable auto-configuration classes into the application context's processing pipeline.

To understand this flow, three ideas are essential:

- `@Import` is the Spring Framework mechanism for bringing configurations or registrars into the application context.
- `@EnableAutoConfiguration` uses an import selector to select applicable auto-configurations.
- Selected auto-configurations still have to pass conditions such as classpath, properties, and existing beans before bean definitions are registered.

## 1. What problem does auto-configuration solve?

In a traditional Spring application, developers often had to manually declare many infrastructure components:

- `DataSource` and transaction manager for data access.
- MVC infrastructure, message converters, and web server for HTTP applications.
- Beans supporting JSON, validation, caching, or security.
- Connection configurations and library integrations.

Spring Boot provides default configurations based on common conventions. When conditions are met, the framework can automatically register the necessary beans. You can still customize them via properties or declare replacement beans yourself.

For example, in an application with Spring Web on the classpath:

```text
Add web dependency
        |
        v
Spring Boot detects web-related classes
        |
        v
Matching web auto-configurations are selected
        |
        v
Evaluate conditions and configure environment
        |
        v
Register matching infrastructure beans
        |
        v
Application can handle HTTP requests
```

Auto-configuration is not magic that creates everything regardless of configuration. It is a set of conditional configuration classes, imported and processed according to Spring's rules.

## 2. What is `@EnableAutoConfiguration`?

`@EnableAutoConfiguration` resides in the package:

```java
org.springframework.boot.autoconfigure.EnableAutoConfiguration
```

This annotation instructs Spring Boot to inspect and apply suitable auto-configurations based on the classpath, `Environment`, bean definitions, and related conditions.

A minimal bootstrap class can be written as:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.ComponentScan;

@ComponentScan
@EnableAutoConfiguration
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

In typical applications, you rarely write the two annotations above separately because `@SpringBootApplication` already combines them.

### 2.1. `@SpringBootApplication` includes `@EnableAutoConfiguration`

Common declaration:

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

Conceptually, `@SpringBootApplication` combines:

```text
@SpringBootApplication
    |
    +-- @SpringBootConfiguration
    |
    +-- @EnableAutoConfiguration
    |
    +-- @ComponentScan
```

The three parts have distinct responsibilities:

| Annotation | Role |
| --- | --- |
| `@SpringBootConfiguration` | Marks the application's primary configuration class, based on `@Configuration` |
| `@EnableAutoConfiguration` | Enables the auto-configuration selection and import mechanism |
| `@ComponentScan` | Discovers application components within the scanned package scope |

Therefore, `@SpringBootApplication` both supports component scanning and enables auto-configuration. These two mechanisms work together, but they are not the same thing.

## 3. Spring Framework's configuration import mechanism

Before diving into `@EnableAutoConfiguration`, let us understand `@Import`.

`@Import` is a Spring Framework annotation:

```java
org.springframework.context.annotation.Import
```

It allows a configuration class to bring additional configurations or bean-registration components into the context.

For example:

```java
@Configuration
@Import(FeatureConfiguration.class)
public class ApplicationConfiguration {
}
```

Spring will process `FeatureConfiguration` as an imported configuration, even if it is not discovered via component scan.

### 3.1. Importing a configuration class

```java
@Configuration
public class FeatureConfiguration {

    @Bean
    public FeatureService featureService() {
        return new FeatureService();
    }
}
```

Another class imports it:

```java
@Configuration
@Import(FeatureConfiguration.class)
public class MainConfiguration {
}
```

The `featureService` bean can be registered from the imported configuration. This is a way to split configuration into small, reusable modules.

### 3.2. Importing with `ImportSelector`

Spring also allows dynamic importing via `ImportSelector`. This interface has the method:

```java
String[] selectImports(AnnotationMetadata importingClassMetadata);
```

The selector receives metadata of the configuration class importing it and returns the fully qualified names of the classes to import.

For example:

```java
public class FeatureImportSelector implements ImportSelector {

    @Override
    public String[] selectImports(
            AnnotationMetadata importingClassMetadata) {
        return new String[] {
            "com.example.demo.feature.FeatureConfiguration"
        };
    }
}
```

Usage:

```java
@Configuration
@Import(FeatureImportSelector.class)
public class ApplicationConfiguration {
}
```

A selector lets you decide which configuration classes to import at the time Spring processes metadata, rather than hardcoding every configuration in the `@Import` annotation.

### 3.3. Importing with `ImportBeanDefinitionRegistrar`

Another mechanism is `ImportBeanDefinitionRegistrar`. It allows registering bean definitions directly into the registry during import processing.

Conceptual differences:

| Mechanism | Job |
| --- | --- |
| `@Import(SomeConfiguration.class)` | Imports a specific configuration class |
| `ImportSelector` | Selects a list of classes to import |
| `DeferredImportSelector` | Selects classes to import in a deferred phase after normal configurations are processed |
| `ImportBeanDefinitionRegistrar` | Directly registers bean definitions into the registry |

`@EnableAutoConfiguration` relies on an import selector to choose auto-configurations; an important part of this design is deferred import processing.

## 4. How does `@EnableAutoConfiguration` use `@Import`?

In Spring Boot, `@EnableAutoConfiguration` is connected to `AutoConfigurationImportSelector` via `@Import`.

You can picture the annotation structure as follows:

```java
@AutoConfigurationPackage
@Import(AutoConfigurationImportSelector.class)
public @interface EnableAutoConfiguration {
    // Exclusion attributes...
}
```

This is a simplified diagram to illustrate the main relationship. The actual source code also includes metadata, aliases, and related annotations.

`AutoConfigurationImportSelector` is a `DeferredImportSelector`. It finds auto-configuration candidates, filters out excluded or unsuitable configurations, and returns the list of configurations to import.

General flow:

```text
@SpringBootApplication
        |
        v
@EnableAutoConfiguration
        |
        v
@Import(AutoConfigurationImportSelector.class)
        |
        v
AutoConfigurationImportSelector
        |
        v
Find list of auto-configuration candidates
        |
        v
Apply exclusions and condition filters
        |
        v
Sort according to auto-configuration rules
        |
        v
Import matching configuration classes
        |
        v
Spring processes @Bean methods and registers BeanDefinitions
        |
        v
Bean instances are created according to lifecycle
```

Key point: `@EnableAutoConfiguration` does not directly create `DataSource`, `DispatcherServlet`, or `ObjectMapper`. It turns on the mechanism that finds and imports configurations; the imported configuration classes are what declare those beans.

## 5. Why use `DeferredImportSelector`?

A regular `ImportSelector` selects classes to import while configuration is being processed. A `DeferredImportSelector` defers import processing until after regular configuration classes have been parsed.

This is very useful for auto-configuration because Spring Boot also needs to consider user-declared configurations.

For example, a library provides a default bean:

```java
@Configuration(proxyBeanMethods = false)
public class DefaultClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

The application defines its own:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {

    @Bean
    public Clock businessClock() {
        return Clock.systemDefaultZone();
    }
}
```

When auto-configuration is processed after application configuration, the `@ConditionalOnMissingBean(Clock.class)` condition can see the `Clock` bean provided by the application and cause the default configuration to "back off".

If auto-configuration were processed too early, it might not yet see bean definitions that the user is about to register. Deferred importing helps Spring Boot organize this process in line with prioritizing user configuration.

**Do not interpret deferred as waiting until every bean instance has finished being created.** It is deferring import processing within the configuration parsing/registration phase, before all singleton beans are instantiated.

## 6. Where do auto-configuration candidates come from?

Spring Boot needs a mechanism to know which libraries provide auto-configuration classes. The registration mechanism has evolved across Spring Boot generations.

### 6.1. Metadata mechanism in modern Spring Boot versions

In modern Spring Boot lines (from the 2.7 generation onward and used in Spring Boot 3.x), auto-configurations are declared in the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line is the fully qualified name of an auto-configuration class:

```text
com.example.library.autoconfigure.SearchAutoConfiguration
com.example.library.autoconfigure.MetricsAutoConfiguration
```

When the library is packaged as a JAR, the metadata file resides inside the JAR and Spring Boot can read the listed classes to build the candidate list.

This allows a starter or integration library to publish its auto-configurations without requiring user applications to manually import each class.

### 6.2. Legacy mechanism via `spring.factories`

In older Spring Boot versions, auto-configurations were usually registered in:

```text
META-INF/spring.factories
```

Example of legacy metadata:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.library.autoconfigure.SearchAutoConfiguration,\
com.example.library.autoconfigure.MetricsAutoConfiguration
```

Starting with Spring Boot 2.7, the `AutoConfiguration.imports` file mechanism was introduced for registering auto-configurations. Spring Boot 3 moved to the new mechanism for auto-configuration registration; projects upgrading from older versions need to migrate metadata according to the corresponding version's guide. `spring.factories` is still used for some other factory/extension points, so you should not delete that file just because auto-configuration moved to the imports file.

### 6.3. Comparing the two registration methods

| Aspect | Legacy `spring.factories` | `AutoConfiguration.imports` |
| --- | --- | --- |
| Location | `META-INF/spring.factories` | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Data format | Property key mapped to a list of classes | One class name per line |
| Historical role | Registered auto-configurations in older Boot lines | Dedicated mechanism for auto-configuration in modern lines |
| When developing a new library | Use only if an older Boot line requires it | Use according to modern Boot guidelines |

Follow the exact Spring Boot version your library supports. A starter that needs to be compatible across multiple generations may need metadata or module structure following a specific migration strategy; do not blindly copy configuration from legacy projects.

## 7. What does an auto-configuration class look like?

An auto-configuration class is a configuration class containing default beans and conditions to decide when they are registered.

In modern Spring Boot versions, you can use `@AutoConfiguration`:

```java
package com.example.library.autoconfigure;

import com.example.library.SearchClient;
import com.example.library.DefaultSearchClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(SearchClient.class)
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchClient.class)
    public SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
```

The example assumes `SearchClient` and `DefaultSearchClient` belong to an integration library and are present when the appropriate dependency is added.

The two conditions have different meanings:

- `@ConditionalOnClass(SearchClient.class)`: considers the configuration only when `SearchClient` is on the classpath.
- `@ConditionalOnMissingBean(SearchClient.class)`: registers the default bean only if no matching bean by type exists yet.

`@AutoConfiguration` is the way to mark a configuration intended for the auto-configuration mechanism. It is based on Spring's configuration class and is typically declared with `proxyBeanMethods = false`, suitable for independent bean configurations.

### 7.1. `@AutoConfiguration` and `@Configuration`

You may still see older auto-configurations declared with `@Configuration`. In modern Boot lines, `@AutoConfiguration` clearly expresses the auto-configuration role and supports before/after ordering metadata.

For example:

```java
@AutoConfiguration(
    after = DataSourceAutoConfiguration.class
)
public class ReportingAutoConfiguration {
}
```

Or using a separate annotation:

```java
@AutoConfigureAfter(DataSourceAutoConfiguration.class)
```

These ordering mechanisms control processing order between auto-configuration classes during import. They are not `@Order` for sorting all bean instances in the application context.

## 8. Conditions that decide whether auto-configuration is applied

Being in the candidate list **does not mean the configuration is guaranteed to be applied**. After being discovered, the configuration class still has to satisfy conditions.

Some common conditions:

| Annotation | Data inspected | Example |
| --- | --- | --- |
| `@ConditionalOnClass` | Classpath | Spring MVC or client library is present |
| `@ConditionalOnMissingClass` | Classpath | Another implementation is absent |
| `@ConditionalOnBean` | Bean definitions | `DataSource` or required dependency already exists |
| `@ConditionalOnMissingBean` | Bean definitions | Application has not provided a replacement bean |
| `@ConditionalOnProperty` | Environment property | `feature.enabled=true` |
| `@ConditionalOnWebApplication` | Application context type | Servlet or reactive application |
| `@ConditionalOnResource` | Resource | Configuration file or template exists |

For example:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.messaging.MessageClient")
@ConditionalOnProperty(
    prefix = "messaging",
    name = "enabled",
    havingValue = "true"
)
public class MessagingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    MessagePublisher messagePublisher() {
        return new DefaultMessagePublisher();
    }
}
```

For the configuration above to apply, the optional class must be on the classpath and the property must be enabled. The bean method also has its own condition so it does not replace an application-provided bean.

### 8.1. Candidate, match, and bean instance are three distinct stages

```text
AutoConfiguration.imports
        |
        v
Candidate class discovered
        |
        v
Conditions evaluated
        |
        +-- Does not match --> Skip configuration
        |
        +-- Matches
              |
              v
       Process configuration class
              |
              v
       Register bean definitions
              |
              v
       Instantiate beans when needed
```

A class can be listed yet excluded by a condition. A condition can match while a bean method inside fails its own condition. And even after a bean definition is registered, instance creation can still fail due to dependencies or runtime configuration.

## 9. `@AutoConfigurationPackage` and the application's root package

`@EnableAutoConfiguration` is also associated with `@AutoConfigurationPackage`. This annotation uses a registrar to record the application's root package as information for other Spring Boot discovery mechanisms.

For example:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
}
```

The `com.example.shop` package can be registered as the auto-configuration package. Mechanisms such as Spring Boot's default entity scanning can rely on this package to determine their search scope.

Distinction:

- `@ComponentScan` finds components such as `@Service`, `@Controller`, `@Component`.
- `@AutoConfigurationPackage` records the root package for other auto-configuration mechanisms to use.
- `@EnableAutoConfiguration` enables auto-configuration importing.

The three mechanisms cooperate without replacing one another.

### 9.1. Why does the main class location matter?

Typically, you should place the `@SpringBootApplication` class in a common root package:

```text
com.example.shop
├── ShopApplication.java
├── controller/
├── service/
├── repository/
└── domain/
```

As a result, default component scanning and the root package for related mechanisms can cover the application's subpackages.

If the main class is placed too deep or entity packages lie outside the default region, you may need explicit configuration such as `scanBasePackages`, `@EntityScan`, or `@EnableJpaRepositories`. Expanding component scan does not automatically alter every entity/repository scanning scope.

## 10. Excluding unnecessary auto-configurations

Not every auto-configuration present on the classpath is suitable for an application. Spring Boot allows excluding specific configurations.

### 10.1. Using `exclude` on `@SpringBootApplication`

For example:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class DemoApplication {
}
```

When doing so, `DataSourceAutoConfiguration` is excluded from the auto-configuration process. This example can be useful for applications that do not need automatic datasource configuration, though if another bean still requires `DataSource`, the application may fail to start.

### 10.2. Using `excludeName`

When the class to exclude is not available at compile time, you can use its fully qualified name:

```java
@SpringBootApplication(
    excludeName = {
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
    }
)
public class DemoApplication {
}
```

`excludeName` accepts class names as strings. This avoids having to import the excluded class directly.

### 10.3. Using a property

You can configure:

```properties
spring.autoconfigure.exclude=\
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

For multiple classes, provide a list of names in the appropriate property format:

```properties
spring.autoconfigure.exclude=\
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,\
org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration
```

Exact class names depend on the Spring Boot version; consult the project's dependencies and APIs.

### 10.4. When should you exclude?

Exclude only when you know which configuration is being applied and why you do not need it. For example:

- The application does not use a database, yet a dependency accidentally pulls in a related configuration.
- You want to manually configure part of the infrastructure differently.
- An auto-configuration is incompatible with the deployment environment.

Do not exclude configurations en masse just to get the application to start. If an auto-configuration is applied unintentionally, inspect the condition report and identify which dependency/property/bean caused it to match.

## 11. Ordering between auto-configurations

An auto-configuration may depend on beans provided by another auto-configuration. Spring Boot supports metadata to order them.

For example:

```java
@AutoConfiguration
@AutoConfigureAfter(DataSourceAutoConfiguration.class)
public class AuditAutoConfiguration {
    // Configuration may require DataSource
}
```

Or:

```java
@AutoConfiguration
@AutoConfigureBefore(ValidationAutoConfiguration.class)
public class CustomValidationAutoConfiguration {
}
```

In releases supporting `@AutoConfiguration`, you can use the `before`, `after`, `beforeName`, and `afterName` attributes directly on the annotation.

### 11.1. Ordering does not replace conditions

`@AutoConfigureAfter` only orders relative processing order. It does not by itself guarantee that the dependency the configuration needs exists.

If `AuditAutoConfiguration` needs a `DataSource`, it should still have a condition:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
@ConditionalOnBean(DataSource.class)
public class AuditAutoConfiguration {
}
```

The condition determines whether the configuration is eligible to apply; ordering determines the processing order among imported configurations. The two serve different purposes.

### 11.2. Do not confuse auto-configuration ordering with `@Order`

| Mechanism | What is ordered | Purpose |
| --- | --- | --- |
| `@AutoConfigureBefore` / `@AutoConfigureAfter` | Auto-configuration classes | Orders framework configurations |
| `@Order` / `Ordered` | Beans or extension points supporting order | Sorts elements/handlers |
| Constructor injection | Dependency relationships between beans | Ensures dependencies are resolved to create a bean |
| `@DependsOn` | Initialization relationship by bean name | Requires another bean to initialize first |

If auto-configuration A needs bean B, use appropriate conditions and configuration ordering. Do not put `@Order` on two configuration classes as a substitute for dependencies.

## 12. Creating your own auto-configuration for a library

Suppose you are developing a library that provides a search client. Users only need to add the library dependency to their project; if they have not provided their own `SearchClient`, the library supplies a default implementation.

### 12.1. Declaring the interface and implementation

```java
package com.example.search;

public interface SearchClient {
    String search(String query);
}
```

```java
package com.example.search;

public class DefaultSearchClient implements SearchClient {

    @Override
    public String search(String query) {
        return "Search result for: " + query;
    }
}
```

### 12.2. Creating the auto-configuration class

```java
package com.example.search.autoconfigure;

import com.example.search.DefaultSearchClient;
import com.example.search.SearchClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "search",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchClient.class)
    public SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
```

Explanation:

- `@AutoConfiguration` marks the configuration as intended for auto-configuration.
- `@ConditionalOnProperty` enables the integration only when the matching property is set; this example defaults to enabled if the property does not exist.
- `@ConditionalOnMissingBean` backs off if the application already provides a `SearchClient`.
- `@Bean` provides the default implementation.

If the actual implementation requires an optional library, add `@ConditionalOnClass` and structure the configuration so that optional classes are loaded only when the dependency is present.

### 12.3. Registering the class in the imports file

Create the file:

```text
src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Content:

```text
com.example.search.autoconfigure.SearchAutoConfiguration
```

When packaging the library, this file must reside inside the JAR at the exact path `META-INF/spring/...`. Spring Boot reads metadata from the classpath to find auto-configuration classes.

### 12.4. Application using the library

The application only needs to add the library dependency. If enabled by default:

```properties
search.enabled=true
```

Or omit the property if the configuration uses `matchIfMissing = true`. When there is no other `SearchClient` bean, the auto-configuration can register `DefaultSearchClient`.

Users can still provide their own implementation:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationSearchConfiguration {

    @Bean
    public SearchClient searchClient() {
        return new CompanySearchClient();
    }
}
```

When auto-configuration is processed in the proper order, `@ConditionalOnMissingBean(SearchClient.class)` prevents the default bean from being registered.

### 12.5. Why should the auto-configuration package be organized carefully?

Auto-configuration is found via the metadata file and does not need to rely on the application's component scan. Therefore, place it in a separate package such as `com.example.search.autoconfigure`, outside the root package scanned by user applications.

If an auto-configuration class is left inside the application's component scan area, it may be discovered as a regular configuration outside the intended import path. This can easily cause conditions or processing order to behave differently than designed. Separating packages and using the imports file keeps the class's role clear.

## 13. At which steps is the import mechanism processed?

The internal pipeline has many processors, but you can picture it in stages:

1. Spring begins processing the application's root configuration class.
2. It reads `@Import` and detects `AutoConfigurationImportSelector`.
3. It processes normal configurations and collects deferred imports.
4. `AutoConfigurationImportSelector` loads the list of auto-configuration candidates from metadata.
5. It applies the exclusion list, import filters, and relevant conditions.
6. It sorts auto-configuration classes according to ordering metadata.
7. Selected classes enter configuration processing.
8. Bean methods and corresponding registrars register bean definitions.
9. The container creates bean instances according to the dependency graph, scope, and lifecycle.

This is a learning model, not an exhaustive list of every internal call in every Spring Boot version. Detailed steps can change across versions.

### 13.1. Importing does not mean creating objects immediately

When an auto-configuration class is imported, it mainly means Spring brings the configuration into parsing. `@Bean` methods can produce bean definitions. Actual object creation still depends on scope, lazy initialization, and when dependencies are requested.

For example:

```java
@Bean
@Lazy
public ExpensiveReportClient reportClient() {
    return new ExpensiveReportClient();
}
```

The bean definition can be registered when the configuration is processed, while the object may be created lazily only when needed. Therefore, distinguish:

```text
Candidate discovered
    ≠ configuration imported
    ≠ bean definition registered
    ≠ bean instance created
```

Each `≠` represents a different stage; one step can be skipped or fail without implying all previous steps did not happen.

## 14. Diagnosing auto-configuration

When a default bean appears unexpectedly or fails to appear despite adding a starter, inspect the condition report.

### 14.1. Enabling `--debug`

Start the application with:

```bash
./gradlew bootRun --args='--debug'
```

Or Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

If running on Windows, use `gradlew.bat` or `mvnw.cmd` accordingly. Argument syntax may need adjustment depending on the shell and plugin version; in an IDE you can also put `--debug` in Program arguments.

Spring Boot can print the **Conditions Evaluation Report** with:

- Positive matches: configurations whose conditions matched.
- Negative matches: skipped configurations and reasons.
- Exclusions: excluded configurations.
- Unconditional classes: configurations not dependent on specific conditions.

### 14.2. Asking questions at the right layer

| Question | Where to check |
| --- | --- |
| Is the auto-configuration class in the candidate list? | Imports metadata and dependency JAR |
| Is the class excluded? | `exclude`, `excludeName`, `spring.autoconfigure.exclude` |
| Which condition did not match? | Condition Evaluation Report |
| Was the bean definition registered? | Bean definition registry / application context |
| Why did bean instance creation fail? | Exception, `Caused by`, dependencies, and lifecycle |
| Did the user provide a replacement bean? | `@ConditionalOnMissingBean`, bean definitions, and application configuration |

You should not enable bean definition overriding to work around every auto-configuration issue. If a configuration was skipped due to a missing class or property, overriding does not solve the underlying cause.

### 14.3. Checking metadata in a library

If developing your own starter, check that the built JAR contains the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

and that the file contains the exact fully qualified class names. If the file is not packaged or the class name is wrong, Spring Boot cannot find the candidate from that metadata.

For projects using older Spring Boot versions, verify `spring.factories` metadata according to that version's conventions. Do not mix registration rules across Boot lines without a clear compatibility strategy.

## 15. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "`@EnableAutoConfiguration` creates every bean itself." | It enables the discovery and import mechanism; beans are registered from configurations/registrars when conditions match |
| "Auto-configuration is the same as component scan." | Component scan finds components in packages; auto-configuration imports configurations from metadata |
| "A class in the imports file is guaranteed to apply." | The class still has to pass exclusions and conditions |
| "Importing a class means objects are created immediately." | Importing configuration, registering definitions, and instantiating objects are separate steps |
| "`@Order` sorts all auto-configurations and all beans." | Auto-configuration has its own ordering; `@Order` is used on extension points that support ordering |
| "`@ConditionalOnMissingBean` always sees beans registered later." | Conditions only evaluate the state of definitions at the moment they run |
| "`spring.factories` is no longer used anywhere." | Auto-configuration metadata moved to the imports file in newer lines; `spring.factories` still has other roles depending on version |
| "`scanBasePackages` changes all entity/repository search regions." | It adjusts component scan; entities and repositories have separate configuration mechanisms |
| "Excluding an auto-configuration deletes all beans with the same function." | It excludes the specified configuration; beans can still be registered from other configurations |

## 16. Practice exercises

### Exercise 1 — Observing `@SpringBootApplication`

Create a Spring Boot application with a main class:

```java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Open the source or use your IDE to inspect the meta-annotations on `@SpringBootApplication`. Identify which annotation enables auto-configuration and which enables component scan.

### Exercise 2 — Manually importing a configuration

Create `FeatureConfiguration` with a `@Bean`. Use `@Import(FeatureConfiguration.class)` from another configuration class. Retrieve the bean from the application context and explain why component scan does not need to discover that class.

### Exercise 3 — Trying a simple auto-configuration

Create `SearchAutoConfiguration` with `@AutoConfiguration` and `@ConditionalOnMissingBean(SearchClient.class)`. Register the class in `AutoConfiguration.imports`. Run the application without a `SearchClient` bean, then declare a `SearchClient` bean yourself in the application.

Observe when the default bean is registered and when it "backs off".

### Exercise 4 — Excluding auto-configuration

Choose an auto-configuration present in the project and exclude it using `exclude` or the `spring.autoconfigure.exclude` property. Enable `--debug` and compare the Condition Evaluation Report before and after exclusion.

### Exercise 5 — Checking a classpath condition

Create an auto-configuration that depends on an optional class. Try running with the dependency present and absent. Explain why `@ConditionalOnClass` must be placed appropriately so the optional class is not loaded prematurely.

### Exercise 6 — Distinguishing import and component scan

Create a configuration class outside the application's root package. Without expanding component scan, import the class via `@Import`. Observe that the bean is still registered. Explain why importing does not depend on the package scan scope.

### Exercise 7 — Reading JAR metadata

Package a small auto-configuration library. Open the JAR and find `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Confirm that the class name in the file matches the actual package/class.

## 17. Key takeaways

`@EnableAutoConfiguration` enables Spring Boot's auto-configuration mechanism. This annotation uses `@Import` to bring `AutoConfigurationImportSelector` into processing; the selector finds auto-configuration candidates from metadata, applies exclusions and conditions, and returns matching configurations for Spring to process further.

In modern Spring Boot versions, the `AutoConfiguration.imports` file is where libraries publish auto-configuration classes. Selected classes must still satisfy conditions such as classpath, property, or existing beans. Once imported, configurations can register bean definitions; the container instantiates objects according to dependencies, scope, and lifecycle.

When developing applications or starters, clearly distinguish **component scan**, **configuration import**, **auto-configuration candidate**, **condition match**, **bean definition**, and **bean instance**. Understanding each step accurately helps you explain why a starter auto-configures itself, why a default bean can yield to the application, and how to diagnose when auto-configuration does not behave as expected.
