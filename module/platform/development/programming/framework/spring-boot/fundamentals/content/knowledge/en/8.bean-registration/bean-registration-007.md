# Component Scan, `@Import`, and Auto-Configuration Are Different Registration Paths

In Spring Boot, a bean can appear in `ApplicationContext` without you ever calling `new` in business code. However, **not every bean is created by the same mechanism**. Some beans are discovered by scanning packages, some are brought in through an explicitly imported configuration, and some are automatically configured by Spring Boot based on dependencies and application state.

Distinguishing **component scanning**, **`@Import`**, and **auto-configuration** helps answer common questions: Why did adding `@Service` leave Spring unable to find the bean? Why did adding a library to the classpath suddenly add a `DataSource` or HTTP client bean? Why does excluding an auto-configuration leave controllers still scanned? Why can users declare their own bean to replace a default provided by Spring Boot?

This lesson belongs to the **Bean Registration** chapter and focuses on how **bean definitions enter the container**. Once registered, Spring resolves dependencies, creates instances, and manages lifecycles according to scope and configuration.

## 1. Bean Registration Does Not Mean Immediate Object Instantiation

A **bean definition** is metadata telling the container how a bean can be created: name, type, factory/constructor, scope, lazy mode, conditions, and related information. From the bean definition, Spring instantiates the object when appropriate.

```text
Declaration Source               Container Result                  At Use Time
-------------------              ----------------                  -----------
@Component / @Service ──┐
@Configuration / @Bean ─┼──> Bean definition ──> Bean instance/proxy ──> Caller
@Import ────────────────┤       (metadata)            (by scope)
Auto-configuration ─────┘
```

This diagram illustrates **multiple paths bringing definitions into the same container**. A bean can enter through nested mechanisms: for example, component scan finds a `@Configuration` class, whose `@Bean` methods then declare additional beans. Do not treat these paths as three isolated systems.

Do not confuse **having a definition** with **already having an instance**. Default singletons are typically instantiated when the context refreshes; lazy beans may be deferred; prototypes create a new instance on request; request/session beans have their own lifecycles.

## 2. How Do the Three Main Paths Differ?

| Mechanism | Who decides where to look? | Primary input | Typical use |
|---|---|---|---|
| **Component scan** | You or the application config specify **packages to scan**. | Classes in packages with `@Component` and related stereotypes, plus scan filters. | Finding application controllers, services, repositories, and configurations. |
| **`@Import`** | A configuration class specifies **classes/configurations to include**. | Directly listed classes, or dynamically chosen selectors/registrars. | Composing configuration modules, enabling an integration, using configs outside scan scope. |
| **Spring Boot auto-configuration** | Boot discovers **auto-configuration lists provided by JARs**, then evaluates conditions. | Auto-configuration metadata, classpath, existing beans, properties, application type... | Providing sensible defaults for web, data, messaging, observability, and integrated libraries. |

**All three ultimately register bean definitions** when eligible; the difference lies in **how they are discovered and chosen for application**.

- Component scan: "Look for components in these packages."
- `@Import`: "Include this configuration/class in configuration processing."
- Auto-configuration: "Evaluate configurations listed by Boot from dependencies, applying them only when conditions match."

`@Bean` is how you declare a bean inside a configuration class; it is **not a mechanism for discovering the configuration class itself**. A `@Bean` takes effect only if its containing configuration class is loaded into the context via scan, `@Import`, auto-configuration, or an equivalent registration path.

## 3. Starting from a Minimal Spring Boot Application

Suppose the source code has root package `com.example.shop`:

```text
src/main/java/
└── com/example/shop/
    ├── ShopApplication.java
    ├── api/
    ├── service/
    └── config/
```

Main class:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

`@SpringBootApplication` combines three key parts:

1. **`@SpringBootConfiguration`**: marks the Spring Boot configuration (based on Spring configuration).
2. **`@EnableAutoConfiguration`**: asks Spring Boot to consider eligible auto-configurations.
3. **`@ComponentScan`**: searches for components in the root package and its subpackages by default.

Having just one annotation on the main class can mislead beginners into thinking Spring has **one** bean discovery mechanism. In reality, multiple configuration-processing steps collaborate during startup.

An application can use component scan while disabling a specific auto-configuration. A library can use `@Import` without ever being component-scanned inside the application's packages. That is why you must inspect the **registration source** when diagnosing issues.

## 4. First Path: Component Scanning

### 4.1. Which Components Does Spring Look For?

Example application service:

```java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public long total(long unitPrice, int quantity) {
        return unitPrice * quantity;
    }
}
```

If the scan configuration covers `com.example.shop.service`, this class is discovered as a component candidate and its bean definition is registered.

Common annotations:

| Annotation | Typical role | Relation to component scan |
|---|---|---|
| `@Component` | General component | Direct scan candidate. |
| `@Service` | Business logic layer | Stereotype meta-annotated with `@Component`. |
| `@Repository` | Persistence/data access layer | Component stereotype, may integrate exception translation. |
| `@Controller` | Web controller | Component stereotype. |
| `@RestController` | Controller returning response body | Combines controller and response body semantics. |
| `@Configuration` | Bean configuration class | Can be found by scan, then its `@Bean` methods are processed. |

**It is not only annotations literally named "Component" that get scanned.** Stereotypes and custom annotations with suitable meta-annotations can also be recognized. Still, having an annotation on a class **is not enough** if the class lies outside the scan scope or is excluded by filters/conditions.

### 4.2. Default Scan Scope

In the example with `ShopApplication` in `com.example.shop`, subpackages such as `com.example.shop.service` and `com.example.shop.api` are normally scanned.

By contrast:

```text
com.example.shop.ShopApplication         # Root package
com.example.shop.service.PriceService    # Inside default scope
com.example.shared.ExternalService       # Outside default scope
```

`ExternalService` is not scanned merely because both classes sit on the classpath.

You can configure the scan scope intentionally:

```java
@SpringBootApplication(scanBasePackages = {
        "com.example.shop",
        "com.example.shared"
})
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

However, widening scanning into library packages too broadly can register unwanted components. Usually, keeping the main class in an appropriate root package and using the library's configuration mechanism is simpler.

**Note:** `scanBasePackages` on `@SpringBootApplication` affects **component scan**, and does not automatically alter packages used by mechanisms such as JPA entity/repository scanning. Those mechanisms have their own annotations and rules, such as `@EntityScan` or `@EnableJpaRepositories` when customization is needed.

### 4.3. Component Scan and `@Bean` Working Together

```java
package com.example.shop.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

If `TimeConfiguration` sits in a scanned package, Spring discovers the **configuration class**, then processes `appClock()` to register a **`Clock` bean**. `java.time.Clock` itself has no `@Component` and is not scanned.

```text
component scan
      │
      ▼
TimeConfiguration discovered
      │
      ▼
Process @Bean appClock()
      │
      ▼
Clock bean definition
      │
      ▼
Clock instance when needed
```

This shows why saying "the bean was registered via component scan" is sometimes shorthand; **the `Clock` bean was declared via `@Bean`, while the class containing its definition was found by scanning**.

### 4.4. Filters Select or Exclude Components

`@ComponentScan` supports `includeFilters` and `excludeFilters`. For example, you can exclude a class from scanning:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.stereotype.Service;

@ComponentScan(
    basePackages = "com.example.shop",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = ExperimentalService.class
    )
)
class ScanConfiguration { }
```

This snippet assumes an `ExperimentalService` class exists. A filter affects only **that specific scan**; if another configuration explicitly imports or registers that same class, do not expect a scan filter to block every registration path.

## 5. Second Path: `@Import`

`@Import` is a **Spring Framework** annotation for bringing other classes/configurations into configuration processing. Unlike scanning, it does not ask Spring to traverse every class in a package and filter by stereotype.

Suppose you want to use a component located **outside the application's scan packages**:

```java
package com.acme.billing;

public interface InvoiceFormatter {
    String format(long amount);
}
```

```java
package com.acme.billing;

public class SimpleInvoiceFormatter implements InvoiceFormatter {
    @Override
    public String format(long amount) {
        return "Amount: " + amount;
    }
}
```

The library provides a configuration:

```java
package com.acme.billing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class BillingConfiguration {

    @Bean
    public InvoiceFormatter invoiceFormatter() {
        return new SimpleInvoiceFormatter();
    }
}
```

The application explicitly imports it:

```java
package com.example.shop;

import com.acme.billing.BillingConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(BillingConfiguration.class)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Even though `BillingConfiguration` resides in `com.acme.billing`, outside `com.example.shop`, Spring processes it via `@Import`. The `InvoiceFormatter` bean is declared from the `@Bean` method and can be injected into services or controllers.

**Here `@Import` brings in a configuration class; it is not the same as a Java package import.** The `import com.acme.billing.BillingConfiguration;` statement above is purely Java syntax to reference the type. The `@Import(BillingConfiguration.class)` annotation is what instructs Spring to register/process the configuration.

### 5.1. Can Component Classes Be Imported Directly?

Yes. `@Import` can accept ordinary component classes beyond `@Configuration`. For example:

```java
@Configuration(proxyBeanMethods = false)
@Import(ExternalCalculator.class)
public class CalculatorFeatureConfiguration { }
```

Assuming `ExternalCalculator` can be instantiated by the container and its dependencies are satisfied, Spring can register it as a bean through the import process even if the class lies outside scanned packages.

Direct import is **intentional and transparent**, though when a module needs multiple beans, a dedicated configuration with `@Bean` methods or an `@Enable...` annotation usually makes integration easier for users to understand.

### 5.2. Importing a Group of Configurations

```java
@Configuration(proxyBeanMethods = false)
@Import({
    BillingConfiguration.class,
    ReportConfiguration.class
})
public class BusinessFeatureConfiguration { }
```

This works well when grouping related configurations behind **one clear activation point**, without expanding component scanning across an entire library package.

Example of a custom annotation:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Import;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(BillingConfiguration.class)
public @interface EnableBilling { }
```

Then:

```java
@SpringBootApplication
@EnableBilling
public class ShopApplication { /* main() */ }
```

When `@EnableBilling` is processed as a composed annotation, `BillingConfiguration` is imported. This is how many feature-enabling annotations in the Spring ecosystem work: behind a concise name often lies `@Import` with supporting classes.

### 5.3. `ImportSelector` and `ImportBeanDefinitionRegistrar`

`@Import` can also accept:

- **`ImportSelector`**: chooses configuration class names to import based on metadata and context.
- **`DeferredImportSelector`**: a selector variant that defers import selection within configuration processing.
- **`ImportBeanDefinitionRegistrar`**: registers bean definitions programmatically through the registry.

These extension points suit frameworks, starters, and infrastructure libraries rather than beginner applications. They explain why beans can be added even when source code has no direct `@Import(SomeConfiguration.class)`.

**Spring Boot auto-configuration also uses a configuration selection and import mechanism**, yet discovering lists from JAR metadata and checking Boot conditions belong to the Boot layer; that is an important difference from an application's explicit `@Import`.

## 6. Third Path: Spring Boot Auto-Configuration

Spring Boot aims to give applications sensible defaults for chosen libraries. For instance, when a compatible web technology is on the classpath, Boot can provide web-server-related configuration; when persistence libraries and datasource configuration are present, Boot can configure data access components.

This happens via **auto-configuration classes**—configuration classes discovered by Boot through metadata and applied conditionally.

A typical main class enables this mechanism via `@SpringBootApplication`, since that annotation includes `@EnableAutoConfiguration`.

### 6.1. Where Are Auto-Configurations Found?

In Spring Boot **2.7 and later**, JARs can provide a list of auto-configurations in:

```text
META-INF/spring/
└── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line in the file contains the **fully qualified class name** of an auto-configuration class. For example:

```text
com.acme.clock.autoconfigure.ClockAutoConfiguration
```

In Boot **2.6 and earlier**, auto-configurations were listed under `EnableAutoConfiguration` in `META-INF/spring.factories`. Boot 2.7 was a transition release supporting the `AutoConfiguration.imports` format; for Boot 3.x and newer lines, do not register auto-configurations under the legacy key in `spring.factories` as though it were the current primary mechanism.

This is **dedicated metadata for auto-configuration**, distinct from component scanning application packages. Auto-configuration classes normally reside in accompanying library or starter JARs; Spring Boot reads the list and evaluates conditions before/during adding bean definitions to the context.

### 6.2. What Conditions Does Boot Check?

Common annotations:

| Condition | General meaning |
|---|---|
| `@ConditionalOnClass` | Apply configuration only when the specified class is on the classpath. |
| `@ConditionalOnMissingClass` | Apply only when the specified class is absent from the classpath. |
| `@ConditionalOnBean` | Apply only when a matching bean already exists at evaluation time. |
| `@ConditionalOnMissingBean` | Register default only if no matching bean exists at evaluation time. |
| `@ConditionalOnProperty` | Evaluate property presence, value, and optional behavior when unset. |
| `@ConditionalOnWebApplication` | Apply only in an appropriate web application context. |
| `@ConditionalOnResource` | Check presence of a specified resource. |

Not every condition checks only the classpath. **Each auto-configuration may require multiple conditions to pass together**, and conditions can be placed at the class level or on `@Bean` methods.

A library class being present on the classpath **does not guarantee all auto-configured beans will be created**. Boot may skip a configuration because another class is missing, a property disables the feature, a user-provided bean already exists, or the context is not the right type.

### 6.3. Auto-Configuration "Backs Off" for User Configuration

A key characteristic of Spring Boot is that auto-configurations typically supply **conditional defaults**, such as registering a bean only when the application has not provided a matching implementation. `@ConditionalOnMissingBean` is a common mechanism for this behavior.

Conceptual illustration:

```text
Did the application provide its own Clock bean?
          │
       ┌──┴───┐
       │      │
      Yes     No
       │      │
       ▼      ▼
  Use user   Auto-config creates
    bean       default Clock
```

This differs from saying "Spring Boot always overrides configuration". Normally Boot tries to **back off** when the user has already configured a matching bean type. However, always check each auto-configuration's actual annotations; **not every auto-configuration uses `@ConditionalOnMissingBean`**.

## 7. Example: Building a Small Auto-Configuration for a Library

To see the difference clearly, suppose you write a library providing a default `java.time.Clock` bean for other applications. This example follows the pattern for **Spring Boot 3.x/4.x**, registering auto-configuration via `AutoConfiguration.imports`.

The library's package lies **outside the consuming application's component scan scope**:

```text
clock-integration/
├── src/main/java/com/acme/clock/autoconfigure/
│   └── ClockAutoConfiguration.java
└── src/main/resources/META-INF/spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports

shop-app/
└── src/main/java/com/example/shop/
    └── ShopApplication.java
```

In the library module, `ClockAutoConfiguration.java`:

```java
package com.acme.clock.autoconfigure;

import java.time.Clock;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "demo.clock",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class ClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock defaultClock() {
        return Clock.systemUTC();
    }
}
```

Metadata file contents:

```text
com.acme.clock.autoconfigure.ClockAutoConfiguration
```

The file must be packaged at the exact path `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` **inside the library JAR**. An auto-configuration declared in this file is discovered by Boot's auto-configuration mechanism, **without requiring `@Component` or `@Import` in the consuming application**.

The `shop-app` application only needs the library JAR with its metadata and matching dependencies on the runtime classpath; `ShopApplication` remains as in Section 3.

If `demo.clock.enabled` is unset, `matchIfMissing=true` treats the configuration as enabled. If no `Clock` bean exists yet, Boot registers the bean from `defaultClock()`. If the property is `false`, the configuration condition fails and the default bean is not registered.

The application can explicitly declare a different `Clock`:

```java
package com.example.shop.config;

import java.time.Clock;
import java.time.ZoneId;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppTimeConfiguration {

    @Bean
    public Clock businessClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }
}
```

When Spring Boot evaluates the auto-configuration and sees the user-provided `Clock` bean, `@ConditionalOnMissingBean(Clock.class)` causes the default **not to be registered**. This behavior is commonly called **back-off**.

**Important note on ordering:** Bean-based conditions like `@ConditionalOnMissingBean` depend on bean definitions already processed at evaluation time. Auto-configurations are designed to run after user configuration in the proper lifecycle; do not casually place this annotation on ordinary component configurations expecting it to see every bean registered later.

### Avoiding a Common Mistake When Writing Auto-Configurations

**Do not place auto-configuration classes inside packages component-scanned by the application**, and do not add `@Component` or unnecessary direct imports to configurations already registered via `AutoConfiguration.imports`. Bringing the same configuration into the context through two different paths makes condition evaluation and ordering hard to reason about, and can even cause registration conflicts depending on the case.

A library starter typically brings required dependencies onto the classpath. **Auto-configuration metadata** usually lives in the library's auto-config module. The two artifacts can be separate or combined in one JAR depending on design; there is no rule requiring every starter to contain all configuration classes directly.

## 8. Component Scan, `@Import`, and Auto-Configuration in the Same Application

Imagine an application containing:

- Your team's `ProductController` and `ProductService`, under `com.example.shop`, annotated with stereotypes.
- A business library's `BillingConfiguration`, enabled via `@Import(BillingConfiguration.class)`.
- `ClockAutoConfiguration` inside an integration JAR, listed in `AutoConfiguration.imports`.

When Spring Boot builds the context:

```text
ShopApplication (@SpringBootApplication)
               │
               ├─ Component scan package com.example.shop
               │       ├─ ProductController definition
               │       └─ ProductService definition
               │
               ├─ @Import(BillingConfiguration.class)
               │       └─ @Bean InvoiceFormatter definition
               │
               └─ Enable auto-configuration
                       ├─ Read auto-config list from classpath
                       ├─ Evaluate conditions
                       └─ @Bean default Clock (if conditions pass)
                                         │
                                         ▼
                               ApplicationContext
                                         │
                                         ▼
                        Resolve dependencies, create beans
```

The branches illustrate **configuration sources**, not a rigid execution order across all steps. Spring processes configuration classes across multiple phases, selectors, and conditions; bean definitions coming from scan, import, or auto-configuration are all handled uniformly by the container.

A service can inject beans from any branch as long as matching definitions exist in the context:

```java
@Service
public class ReceiptService {
    private final InvoiceFormatter formatter;
    private final Clock clock;

    public ReceiptService(InvoiceFormatter formatter, Clock clock) {
        this.formatter = formatter;
        this.clock = clock;
    }

    public String createReceipt(long amount) {
        return formatter.format(amount) + " @ " + clock.instant();
    }
}
```

This snippet assumes `InvoiceFormatter` and `Clock` are imported and have matching beans. **Code consuming a bean does not need to know whether the bean came from scan, import, or auto-configuration**; the container supplies dependencies by type/qualifier and matching resolution rules.

## 9. `@Import` Is Not Auto-Configuration

`@Import` and auto-configuration are related, yet **not synonymous**.

With explicit import:

```java
@Import(BillingConfiguration.class)
```

the author specifies the **exact** class to process. Spring does not need to locate it via package scanning rules. Conditional annotations inside the imported configuration can still decide which beans are registered.

With Spring Boot auto-configuration:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
com.acme.clock.autoconfigure.ClockAutoConfiguration
```

the application does not need to know the name `ClockAutoConfiguration` directly. Boot discovers it from classpath metadata, adds it to candidate auto-configurations, evaluates conditions, and orders it appropriately.

In other words, **auto-configuration leverages Spring's configuration import infrastructure**, while adding Spring Boot's **automatic discovery, auto-configuration ordering, and conditional conventions** on top. Do not think of it as merely `@Import` written somewhere else.

### When Is `@ImportAutoConfiguration` Used?

Spring Boot provides `@ImportAutoConfiguration` to selectively import certain auto-configurations in special contexts, such as test slice configurations or controlled-scope scenarios. It differs from standard `@Import` in being designed specifically for auto-configuration classes.

For normal Spring Boot applications, do not add `@ImportAutoConfiguration` for every starter. The default auto-configuration mechanism already handles discovering eligible configurations.

## 10. Excluding an Auto-Configuration Does Not Disable Component Scan

You can exclude a Spring Boot auto-configuration explicitly:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

This example assumes a Boot generation where `DataSourceAutoConfiguration` has the name and package shown above. When working with a different Boot version, verify the exact class name in that version's documentation.

Another option is setting `spring.autoconfigure.exclude` with a list of auto-configuration class names. Excluding only **prevents the auto-configuration mechanism from applying the specified configuration**; it does not delete beans registered by application component scanning or user-defined `@Bean` methods.

For example:

- You exclude Boot's datasource auto-configuration.
- Your own `@Configuration` still defines `@Bean DataSource`.
- The container can still register the user-declared datasource.

There is no contradiction: the two definitions have **different registration sources**.

Conversely, if you exclude a package from component scan, beans entering via `@Import` or auto-configuration can still appear unless blocked by another condition.

## 11. `@ComponentScan` and Auto-Configuration Do Not Always Scan the Same Scope

A common misconception is: "If a dependency is in `build.gradle` and has a `@Service` class inside its JAR, Spring Boot automatically scans every package in that JAR."

That is false by default. **Component scan is package-scoped**, starting from your application or declared configuration; a JAR is simply part of the classpath. If a service inside a JAR sits outside scanned packages and is not configured separately, it will not become a bean.

Meanwhile, **auto-configuration** relies on metadata lists and Boot mechanisms, not scanning every stereotype inside every JAR.

A well-structured library can ship:

```text
library.jar
├── com/acme/api/...                       # Public API
├── com/acme/internal/...                  # Implementation
├── com/acme/autoconfigure/MyAutoConfiguration.class
└── META-INF/spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

When the dependency is present, Boot can evaluate `MyAutoConfiguration` even when `com.acme` lies outside the application's default scan scope.

**Practical takeaway:** Setting `scanBasePackages = "com"` so "Spring finds every library" is far too broad. It can register internal components from arbitrary JARs unintentionally. Check whether the library offers a starter, auto-configuration, or supported `@Enable...` annotation instead.

## 12. Role of Dependencies: Having a Class Does Not Guarantee Having a Bean

A Gradle declaration:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
}
```

typically brings in modules for JDBC and related integrations, yet you should not assume every environment automatically has a working connected datasource.

Distinguish three levels:

1. **Artifact is on the classpath**: outcome of Gradle/Maven dependency resolution.
2. **Auto-configuration is a candidate**: Boot finds the configuration name in metadata.
3. **Bean is actually registered and instantiable**: configuration conditions pass and dependencies resolve.

Sometimes Boot registers a bean definition, yet bean creation fails due to missing connection settings or another runtime condition. Seeing an auto-configuration selected does not guarantee all external connections are ready.

The same applies to web, messaging, security, and persistence. A starter is **classpath input**; Spring Boot still has to decide how to use that classpath alongside existing beans and properties.

## 13. Diagnosing: Where Did a Bean Come From?

When a bean is missing or appears unexpectedly, determine its **registration source** first.

### 13.1. Read Error Messages and Root Classes

Common symptoms:

| Symptom | What to check first |
|---|---|
| `NoSuchBeanDefinitionException` | Was the class scanned? Was `@Import` triggered? Was auto-configuration discovered and did its conditions pass? |
| `NoUniqueBeanDefinitionException` | Are multiple same-type beans coming from scan, config, and auto-config? Are qualifiers or `@Primary` needed? |
| `BeanCreationException` | Bean was registered, but its constructor, factory method, config, or dependency failed? |
| Auto-configuration not taking effect | Is `AutoConfiguration.imports` metadata present? Does the classpath match? Do class/bean/property/web conditions pass? |
| Library bean not scanned | Is its package in scan scope? Does the library provide `@Import` or a starter/auto-config? |
| A default bean disappeared after adding `@Bean` | Did `@ConditionalOnMissingBean` cause auto-config to back off? |
| `@Service` annotation has no effect | Is the class in a scanned package? Was the bean blocked by conditions, profiles, or filters? |

### 13.2. Use the Conditions Evaluation Report

In development, launch the application with:

```bash
java -jar app.jar --debug
```

or set:

```properties
debug=true
```

Spring Boot can print the **conditions evaluation report**, categorizing applied and skipped configurations along with reasons. Exact formatting and logger names vary by version.

This report is especially useful when investigating auto-configuration: a missing class, mismatched property, already-existing bean, or incompatible web context type. It **does not replace** reading the root error in the stack trace.

### 13.3. Inspect Bean Definitions from `ApplicationContext`

In a test or scratch app, you can ask the container whether a bean is registered:

```java
package com.example.shop;

import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.ConfigurableApplicationContext;

@Configuration(proxyBeanMethods = false)
public class BeanInspectorConfiguration {

    @Bean
    ApplicationRunner inspectBeans(ConfigurableApplicationContext context) {
        return args -> {
            ConfigurableListableBeanFactory factory =
                    context.getBeanFactory();

            for (String name : context.getBeanDefinitionNames()) {
                if (!factory.containsBeanDefinition(name)) {
                    continue;
                }
                var definition = factory.getBeanDefinition(name);
                if (name.contains("clock") || name.contains("Clock")) {
                    System.out.printf(
                            "%s -> %s%n",
                            name,
                            definition.getResourceDescription()
                    );
                }
            }
        };
    }
}
```

This example intentionally filters printing to names containing `clock/Clock`; `resourceDescription` **is not always populated** or sufficient to identify a source uniquely because bean definitions can be registered in multiple ways. It is simply a clue. To dig deeper, inspect `factoryBeanName`, `factoryMethodName`, `beanClassName`, the conditions report, and related configuration metadata.

In environments with Spring Boot Actuator, `/actuator/beans` and `/actuator/conditions` management endpoints also help inspect beans and conditions if dependencies, exposure settings, and access permissions allow. **Do not expose management endpoints publicly to the internet just for debugging.**

### 13.4. Inspect the Dependency Graph

If an artifact is absent from the runtime classpath, auto-configurations inside that artifact cannot be discovered.

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Maven:

```bash
./mvnw dependency:tree
```

Compare direct dependencies, transitive dependencies, versions, and exclusions. Remember that artifact and starter names can vary across Spring Boot releases.

## 14. Startup Sequence: Does Scan Always Run First and Import After?

Do not describe startup as a rigid schedule like "scan all beans first, then import everything, then run all auto-configurations". Spring processes configuration classes, import selectors, conditional registrations, and bean factory post-processors across multiple phases, and a scanned configuration can itself declare `@Import` or `@Bean`.

What to understand at a foundational level:

```text
SpringApplication.run(...)
       │
       ▼
Prepare Environment and ApplicationContext
       │
       ▼
Read root configuration + process scan / import / auto-configuration
       │
       ▼
Assemble and process bean definitions
       │
       ▼
Resolve dependencies, create eligible singletons, run lifecycle callbacks
       │
       ▼
Application ready to serve per its runtime model
```

**Ordering among auto-configurations** can affect conditions that check bean definitions. Spring Boot supports ordering metadata such as `@AutoConfiguration(before = ...)`, `after = ...`, or `@AutoConfigureBefore`/`@AutoConfigureAfter` depending on the version line. This controls **configuration processing order**, without guaranteeing creation order of all beans or execution order of business methods.

For application developers, typical choices are:

- Register application-specific beans via component scan/`@Bean`.
- Enable integrations intentionally via `@Import` or library annotations.
- Let Boot supply defaults through auto-configuration when conditions fit.
- Override via user beans when auto-configuration supports back-off, rather than tweaking processing order unnecessarily.

## 15. Distinguishing Errors Across Three Scenarios

### Scenario A: `@Service` Outside Scan Scope

`ExternalService` in `com.example.shared` has `@Service`, while `ShopApplication` sits in `com.example.shop` without custom scan settings.

**Fix:** move the service into an appropriate application package, adjust root package / `scanBasePackages` intentionally, or register it via `@Configuration`/`@Import` depending on module boundaries.

### Scenario B: Library Configuration Not Imported

`BillingConfiguration` sits in `com.acme.billing` on the classpath and defines `@Bean InvoiceFormatter`, yet is neither scanned nor listed in `AutoConfiguration.imports`.

**Fix:** add:

```java
@Import(BillingConfiguration.class)
```

or use `@EnableBilling` if the library provides it. Writing only `import com.acme.billing.BillingConfiguration;` at the top of a Java file **does not create a bean definition**.

### Scenario C: Auto-Configuration Discovered, Yet No Bean Created

`ClockAutoConfiguration` is listed in `AutoConfiguration.imports`, while the application already defines its own `Clock` bean. With `@ConditionalOnMissingBean(Clock.class)`, Boot skips registering `defaultClock()`.

**Fix:** this may be the **intended** outcome. Verify which bean is actually injected. If two distinct `Clock` beans are needed, design explicit names/qualifiers and adjust conditions accordingly. Do not randomly strip conditions just to create an extra bean and hit ambiguity errors.

## 16. When to Choose Which Registration Path?

| Context | Appropriate approach | Reason |
|---|---|---|
| Application service/controller in root package | `@Service`/`@RestController` via component scan | Simple, conventional, and easy to locate in code. |
| JDK/library object needing constructor/builder setup | `@Bean` in a context-loaded `@Configuration` | Clear control over the factory method without editing library source. |
| Configuration bundle requiring explicit user opt-in | `@Import` or `@Enable...` wrapping `@Import` | Avoids scanning the whole library; enabled features remain visible. |
| Writing a Spring Boot library needing dependency-driven defaults | `@AutoConfiguration` + `AutoConfiguration.imports` + conditions | Fits reusable integrations across multiple applications. |
| Application wants to replace a Boot default | Declare your own bean after checking back-off conditions | Preserves convention-based configuration where supported. |
| Need to turn off a specific auto-configuration | `exclude` or `spring.autoconfigure.exclude` | Targets the auto-configuration source without disabling component scan. |

**Practical rule:** application code is typically registered via stereotypes/`@Bean`; libraries preferring explicit opt-in can use `@Import`; Spring Boot integrations aiming to work automatically when a dependency is present typically use auto-configuration. These are guidelines, not rigid laws: multiple valid designs exist depending on requirements.

## 17. Practice Exercises

### Exercise 1 — Checking Component Scan Scope

1. Create `ShopApplication` in `com.example.shop`.
2. Register a `@Service` in `com.example.shop.service` and inject it into a runner/controller.
3. Create another `@Service` in an independent package outside the scan scope.
4. Observe the difference, then expand scanning intentionally to verify your prediction.

### Exercise 2 — Importing Configuration Outside the Package

1. Create `BillingConfiguration` with `@Bean InvoiceFormatter` in `com.acme.billing`.
2. Without importing the configuration, try injecting `InvoiceFormatter`: observe the missing-bean error.
3. Add `@Import(BillingConfiguration.class)` to the main class.
4. Restart and verify the bean resolves.

Explain why **a Java `import` statement alone** is not sufficient.

### Exercise 3 — Auto-Configuration with Back-Off

1. Create the integration module with `ClockAutoConfiguration` and `AutoConfiguration.imports` as in Section 7.
2. Add that module to your application's runtime classpath.
3. Observe the `Clock` bean being registered when no other bean exists.
4. Add `@Bean Clock businessClock()` and observe the default auto-configuration backing off.
5. Try setting `demo.clock.enabled=false` and observe the condition's effect.

When evaluating results, check the conditions report too; bean count alone cannot explain every case.

### Exercise 4 — Diagnose Before Fixing

In an application with a controller, a user-declared `Clock` bean, and a database starter, answer:

- Did the controller come from component scan or auto-configuration?
- Was `Clock` registered by the application's `@Bean` or by Boot?
- Which database auto-configurations were evaluated, and which conditions failed?
- If you exclude datasource auto-configuration, is the controller still registered? Why?

### Exercise 5 — Trace Registration Paths

Pick three real beans in your project. For each bean, identify **the configuration or component class**, **how its definition enters the container**, **any registration conditions**, and **dependencies to resolve**. Do not infer bean creation order from diagrams alone.

## 18. Takeaways

- **Component scanning** locates component classes within configured packages and filters; this is typically where application beans start.
- **`@Import`** brings specified classes/configurations directly into processing, cleanly connecting modules without broad scanning.
- **Spring Boot auto-configuration** reads configurations listed in JAR metadata and applies conditions to supply sensible defaults.
- **`@Bean` declares a bean; it is not a discovery rule for the configuration class itself.** The containing class must be loaded via one of the registration paths.
- **Having an artifact on the classpath does not guarantee having a bean.** It must pass discovery, conditional registration, and bean instantiation.
- **Registration paths work together.** A bean is injected by type/qualifier regardless of whether it came from scan, import, or auto-configuration.

When a bean is missing, trace the chain **"where does the definition come from → was the configuration loaded → did conditions pass → did dependencies resolve → did instantiation succeed"**. That is how you distinguish a bean registration error from a bean instantiation error in Spring Boot.
