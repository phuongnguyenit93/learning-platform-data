# Creating Conditional Auto-Configuration That Backs Off When a User Bean Exists

> **Spring Boot Fundamentals · Integrated Practice**  
> Auto-configuration enables Spring Boot and starters to integrate with applications without requiring users to declare every bean manually. A library can supply a default implementation when the classpath and configuration match, while **backing off when the application already defines its own bean**. This lesson builds a small auto-configuration, registers it using Spring Boot's mechanism, combines common conditions, and tests both the default path and the override path.

## 1. What Problem Does Auto-Configuration Solve?

Suppose an application needs a greeting service:

```java
public interface GreetingService {
    String greet(String name);
}
```

If every application had to create the bean manually:

```java
@Configuration
public class GreetingConfiguration {

    @Bean
    GreetingService greetingService() {
        return new DefaultGreetingService("Hello");
    }
}
```

then the library providing `GreetingService` would not actually reduce configuration. Every application would need to know which implementation class to instantiate and how to configure it.

A library can provide auto-configuration to:

- Create `DefaultGreetingService` when required APIs are on the classpath.
- Enable the feature only when properties turn it on.
- Register `GreetingProperties` for configuration binding.
- Create a default bean when no other `GreetingService` exists.
- Step aside for the application if the user declares a custom bean.

Consumer applications then simply add the starter dependency and launch Spring Boot:

```java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

When the dependency containing the auto-configuration is on the classpath and its conditions match, Spring Boot discovers that configuration automatically.

### 1.1. Auto-Configuration Is Not Component Scanning

| Mechanism | How it works | Typical purpose |
| --- | --- | --- |
| Component scanning | Scans packages from application config for `@Component`, `@Service`, `@Repository` | Discover application-declared beans |
| Auto-configuration | Reads auto-configuration list in artifacts, then applies conditions | Supply default configuration from frameworks/starters |
| `@Import` | Imports specified configuration classes or selectors | Wire a specific configuration |
| `@Bean` | Registers objects returned by methods | Explicit bean declarations |

Auto-configuration does not need to live under the `@SpringBootApplication` class's package for component scan to find it. It is discovered through auto-configuration registration metadata.

### 1.2. Why Are Conditions Needed?

A well-behaved auto-configuration should not create beans regardless of whether the application needs them. It must answer:

- Is the required library on the classpath?
- Did the user enable the feature via properties?
- Do dependent beans already exist?
- Did the user provide a replacement bean?
- Is the application running in a matching web environment?
- Is there a clear single candidate bean to inject?

`@ConditionalOn...` annotations express those conditions.

### 1.3. Back-Off Is a Core Starter Behavior

Suppose auto-configuration provides `DefaultGreetingService`. If the application declares:

```java
@Bean
GreetingService greetingService() {
    return new CustomGreetingService();
}
```

the auto-configuration should **not create an additional default bean for the same role**. The application then uses its own implementation.

This is back-off: default configuration steps aside when the user has supplied a matching bean.

Back-off does not mean Spring deletes an already-created bean, swaps implementations at runtime, or merges two objects. It is a decision about whether to register a bean definition while constructing the ApplicationContext.

## 2. Common Conditional Annotations

Spring Boot provides several conditions so auto-configuration activates only when the environment matches.

| Annotation | What it checks | Example usage |
| --- | --- | --- |
| `@ConditionalOnClass` | One or more classes are on the classpath | Configure integration only when library is present |
| `@ConditionalOnMissingClass` | One or more classes are absent from classpath | Pick fallback when optional class is absent |
| `@ConditionalOnBean` | Matching bean is already registered | Create adapter depending on an existing service |
| `@ConditionalOnMissingBean` | No matching bean exists yet | Create default bean and back off on user override |
| `@ConditionalOnSingleCandidate` | Exactly one candidate or one explicitly chosen candidate | Create bean needing an unambiguous collaborator |
| `@ConditionalOnProperty` | Property matches required name/value | Toggle feature on/off |
| `@ConditionalOnResource` | Specific resource can be found | Enable integration only when config file exists |
| `@ConditionalOnWebApplication` | App runs in matching web application type | Configure Servlet/Reactive integration |
| `@ConditionalOnNotWebApplication` | App is not a web application | Configure batch/CLI |
| `@ConditionalOnJava` | Java runtime satisfies version condition | Select configuration per Java version |
| `@ConditionalOnExpression` | SpEL expression evaluates to true | Special conditions, used sparingly |

Conditions can be placed at class or method level. Placing on a class affects all bean methods inside it; placing on a method affects only that bean method.

### 2.1. `@ConditionalOnClass`

Enable configuration only when required dependencies are on the classpath:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.metrics.MeterRegistry")
public class MetricsAutoConfiguration {
    // Configure integration for the metrics library.
}
```

The `name` attribute lets you specify the class name as a String. This is helpful when the class might not be present on the runtime classpath.

Another form uses a class literal:

```java
@ConditionalOnClass(MeterRegistry.class)
```

This is convenient when the dependency is on the auto-configuration module's compile classpath. However, if the optional class is absent at runtime, be careful with method signatures or field references directly referencing that class. Extract configuration depending on optional types into conditional nested configurations.

### 2.2. `@ConditionalOnMissingClass`

Use when activating a fallback if a library is absent:

```java
@AutoConfiguration
@ConditionalOnMissingClass(
        "com.vendor.fastjson.FastJsonMapper")
public class DefaultJsonAutoConfiguration {
    // Configure JSON fallback.
}
```

This condition inspects the classpath, not beans. A class can exist on the classpath without a corresponding bean in the ApplicationContext.

### 2.3. `@ConditionalOnProperty`

Enable configuration only when a property has a matching value:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {
}
```

Attributes:

- `prefix`: key prefix.
- `name`: property name or list of names.
- `havingValue`: value to match.
- `matchIfMissing`: whether the condition counts as matching when the property is absent.

In the example above, the feature is enabled by default if the property is missing, and disabled when:

```properties
acme.greeting.enabled=false
```

If `havingValue` is omitted, default evaluation usually treats any existing property value other than `false` as matching. When clear semantics are needed, declare `havingValue` explicitly.

### 2.4. `@ConditionalOnBean`

Create configuration only when a dependent bean is already registered:

```java
@Bean
@ConditionalOnBean(PaymentClient.class)
PaymentHealthIndicator paymentHealthIndicator(
        PaymentClient client) {
    return new PaymentHealthIndicator(client);
}
```

This expresses "only provide the health indicator when the application already has a PaymentClient bean."

The condition can only evaluate bean definitions registered at the time the condition is checked. For auto-configurations, processing order is critical if one configuration depends on a bean created by another.

### 2.5. `@ConditionalOnMissingBean`

This is the key condition of this lesson:

```java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new DefaultGreetingService("Hello");
}
```

If the context does not yet contain a bean matching type `GreetingService` when the condition is evaluated, the method creates the default bean. If a matching bean already exists, the method is skipped.

Base the condition on the **contract/interface** users are expected to override rather than only the concrete default implementation. That lets applications supply a different implementation while still satisfying the contract.

### 2.6. `@ConditionalOnSingleCandidate`

An auto-configuration may need a collaborator without creating a bean when multiple ambiguous candidates exist:

```java
@Bean
@ConditionalOnSingleCandidate(DataSource.class)
DatabaseInspector databaseInspector(DataSource dataSource) {
    return new DatabaseInspector(dataSource);
}
```

The condition matches when only one matching candidate exists or one candidate is marked primary for unambiguous selection. This avoids configuring an integration in contexts with multiple datasources and no default choice.

### 2.7. `@ConditionalOnResource`

For example, enable configuration only if a schema file exists:

```java
@AutoConfiguration
@ConditionalOnResource(
        resources = "classpath:/acme/schema.sql")
public class SchemaAutoConfiguration {
}
```

Resources are checked via Spring's resource lookup mechanism. If a resource is generated at build time, ensure it is actually packaged into the artifact.

### 2.8. `@ConditionalOnWebApplication`

For example, configuration applying only to Servlet web applications:

```java
@AutoConfiguration
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
public class GreetingWebAutoConfiguration {
}
```

You can pick reactive type when an integration targets WebFlux. Do not add a web condition merely because a starter has REST endpoints if the bean is also useful in batch/CLI apps.

## 3. Designing Auto-Configuration Around Contracts

Before writing annotations, clarify:

1. Which beans does the auto-configuration provide?
2. Which contracts are extension points for applications?
3. Which dependencies are required vs. optional?
4. Which properties control the feature?
5. Which user beans cause the default to back off?
6. Which conditions disable the entire configuration?
7. Who is responsible for initializing and closing resources?

Example:

```text
Acme Greeting Auto-configuration
    |
    +-- Condition: GreetingService API available
    |
    +-- Condition: acme.greeting.enabled != false
    |
    +-- Enable GreetingProperties
    |
    +-- If no GreetingService bean:
    |       create DefaultGreetingService
    |
    +-- If user provides GreetingService:
            back off
```

Designing contracts first avoids tying conditions to internal classes that applications cannot replace.

## 4. Building the Greeting Auto-Configuration Example

We will build an auto-configuration providing a greeting service with a configurable prefix.

### 4.1. Module Structure

An auto-configuration module can be structured as:

```text
acme-greeting-autoconfigure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/greeting/
    │   │   ├── GreetingService.java
    │   │   ├── DefaultGreetingService.java
    │   │   ├── GreetingProperties.java
    │   │   └── autoconfigure/
    │   │       └── GreetingAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/acme/greeting/autoconfigure/
            └── GreetingAutoConfigurationTest.java
```

In large projects, the API and implementation can be split into separate modules. This practice keeps one module to focus on the auto-configuration mechanics.

### 4.2. Extension Point Interface

```java
package com.acme.greeting;

public interface GreetingService {

    String greet(String name);
}
```

This interface is the contract applications consume and can implement themselves.

### 4.3. Default Implementation

```java
package com.acme.greeting;

public final class DefaultGreetingService
        implements GreetingService {

    private final String prefix;

    public DefaultGreetingService(String prefix) {
        this.prefix = prefix;
    }

    @Override
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }

        return prefix + ", " + name.trim();
    }
}
```

This class is a plain Java object. It needs no `@Component`, `@Service`, or Spring imports. Auto-configuration will decide when to instantiate it.

### 4.4. Configuration Properties

```java
package com.acme.greeting;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.greeting")
public class GreetingProperties {

    /**
     * Prefix used by the default greeting implementation.
     */
    private String prefix = "Hello";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
```

The properties object holds configuration values. The default value `Hello` allows applications to use the starter without declaring properties.

You can add Bean Validation such as `@NotBlank` if the project has a validation provider. Decide clearly whether empty-property errors should be caught at bind time or inside the constructor/service.

### 4.5. Auto-Configuration Class

```java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.DefaultGreetingService;
import com.acme.greeting.GreetingProperties;
import com.acme.greeting.GreetingService;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
@EnableConfigurationProperties(GreetingProperties.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(
            GreetingProperties properties) {

        return new DefaultGreetingService(
                properties.getPrefix());
    }
}
```

Key pieces to note:

- `@AutoConfiguration` marks the class as a Boot auto-configuration.
- `@ConditionalOnClass` requires the greeting API to be on the classpath.
- `@ConditionalOnProperty` controls the feature.
- `@EnableConfigurationProperties` registers the properties bean.
- `@Bean` creates the default service.
- `@ConditionalOnMissingBean(GreetingService.class)` enables user overrides.

### 4.6. Registering Auto-Configuration via the Imports File

Create the exact file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Content:

```text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
```

Each line is the fully qualified class name of an auto-configuration class for Spring Boot to discover.

This is the standard auto-configuration registration mechanism in Spring Boot 3. Do not add `@ComponentScan` for this package.

### 4.7. Does Auto-Configuration Need `@Component`?

No. `@AutoConfiguration` already marks the configuration class for Boot's auto-configuration mechanism. Adding `@Component` is usually unnecessary and can cause the class to be discovered unintentionally via component scan if its package falls inside a scan scope.

Keep the auto-configuration package separate from application packages so it never depends on how consumers organize component scanning.

## 5. Backing Off When the Application Supplies Its Own Bean

Now the application wants a custom greeting:

```java
package com.example.demo;

import com.acme.greeting.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomGreetingConfiguration {

    @Bean
    GreetingService greetingService() {
        return name -> "Welcome, " + name + "!";
    }
}
```

Because the auto-configuration has:

```java
@ConditionalOnMissingBean(GreetingService.class)
```

when the user's bean is already registered before the auto-configuration condition is evaluated, the default bean is not created.

Expected result:

```text
ApplicationContext
    |
    +-- CustomGreetingConfiguration
    |       └── GreetingService (user implementation)
    |
    +-- GreetingAutoConfiguration
            └── GreetingService default: BACK OFF
```

### 5.1. Why Should the Condition Check the Interface?

Suppose the default implementation is `DefaultGreetingService` and the user implementation is `FriendlyGreetingService`. If the condition says:

```java
@ConditionalOnMissingBean(DefaultGreetingService.class)
```

then a user bean of type `FriendlyGreetingService` will not trigger back-off because it is not a `DefaultGreetingService`. Auto-configuration would also create the default service, making `GreetingService` injection ambiguous.

The condition should check the contract:

```java
@ConditionalOnMissingBean(GreetingService.class)
```

### 5.2. Declare `@Bean` Return Types Clearly

Good example:

```java
@Bean
GreetingService greetingService() {
    return new DefaultGreetingService("Hello");
}
```

If the return type is declared as an overly specific class or `Object`, type prediction during bean definition processing may lack sufficient information to recognize the target contract.

When a bean is consumed via an interface, declaring the interface return type and writing conditions against the interface keeps the contract clear.

### 5.3. User Beans Can Live in Different Packages

User configuration does not have to share a package with the auto-configuration. It only needs to be registered into the same `ApplicationContext` before the auto-configuration bean condition is evaluated.

That is why Boot processes auto-configurations through a dedicated mechanism ordered after ordinary user configurations.

### 5.4. Do Not Create Two Beans for the Same Contract and Hope `@Primary` Solves It

`@Primary` picks one bean for type-based injection, but it does not fulfill the goal of backing off. If auto-configuration still creates a default despite a custom user bean, the context may contain two instances, altering behavior unexpectedly and complicating inspection.

Use `@ConditionalOnMissingBean` to prevent creating the default in the first place.

## 6. Back-Off by Bean Name vs. Bean Type

`@ConditionalOnMissingBean` supports multiple forms.

### 6.1. By Type

```java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new DefaultGreetingService("Hello");
}
```

This is most common when users can provide any implementation of the contract.

### 6.2. By Name

```java
@Bean
@ConditionalOnMissingBean(name = "customGreetingService")
GreetingService greetingService() {
    return new DefaultGreetingService("Hello");
}
```

This fits when the extension contract is defined by bean name, though it is generally less flexible than a type-based contract.

### 6.3. Combining Type and Annotations

Conditions can be configured to check beans with specific annotations or types. Only do this when it is an intentional contract.

Avoid complicated conditions based on secret bean names. Starter users need to know clearly how they can override defaults.

### 6.4. Search Strategy

`@ConditionalOnMissingBean` can search the current context or include ancestor contexts per its search strategy. For applications with parent/child `ApplicationContext`s, decide whether default beans should back off when a bean exists in the parent.

In ordinary Boot applications with a single main context, default search behavior is usually sufficient. Only customize it when the architecture genuinely uses context hierarchies and has matching tests.

## 7. Class-Level vs. Method-Level Conditions

### 7.1. Class-Level Condition

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true")
public class GreetingAutoConfiguration {

    @Bean
    GreetingService greetingService() {
        return new DefaultGreetingService("Hello");
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}
```

When the property does not match, the entire auto-configuration class is skipped. Neither bean method creates a bean.

### 7.2. Method-Level Condition

```java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.greeting",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(
            GreetingProperties properties) {
        return new DefaultGreetingService(
                properties.getPrefix());
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}
```

Here the property only controls the `GreetingService` bean, while `GreetingFormatter` is still created.

### 7.3. Scoping Conditions Based on Dependencies

If the entire feature is meaningless when disabled, placing the condition at the class level avoids registering related beans. If only one optional bean is disabled while other beans remain useful, place the condition on the method.

Do not repeat identical conditions at both class and method levels unless it adds meaning.

## 8. Condition Evaluation and Auto-Configuration Ordering

A common mistake is assuming Spring waits until all beans in the context are instantiated before evaluating `@ConditionalOnMissingBean`. In reality, conditions are evaluated during configuration parsing and bean definition registration.

### 8.1. Why Does Ordering Matter?

Suppose auto-configuration A checks for a bean supplied by auto-configuration B. If A is processed before B, `@ConditionalOnBean` in A may not see that bean yet.

Spring Boot lets you declare auto-configuration ordering:

- `@AutoConfigureBefore`.
- `@AutoConfigureAfter`.
- `@AutoConfigureOrder`.
- `before`/`after`/`beforeName`/`afterName` attributes on `@AutoConfiguration` in supporting versions.

Example:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class DatabaseAuditAutoConfiguration {
}
```

This configuration requests that audit auto-configuration be evaluated after `DataSource` auto-configuration.

### 8.2. Ordering Is Not Singleton Initialization Order

`@AutoConfigureAfter` controls the order in which auto-configurations are processed, not a guarantee that beans in one class are instantiated immediately after beans in another.

Singleton beans are normally instantiated according to the dependency graph and context lifecycle. If bean A needs bean B, express that dependency via method parameter or constructor instead of relying on configuration ordering.

### 8.3. User Configuration Is Usually Processed Before Auto-Configuration

Spring Boot designs auto-configuration to run after application-declared configuration. That way `@ConditionalOnMissingBean` can see user beans and back off.

In custom setups with complex configuration imports, parent/child contexts, or special ordering, inspect the condition report and test thoroughly. Never rely on class locations in the source tree.

### 8.4. Do Not Use `@Order` as a Substitute for Dependencies

If `SecondConfiguration` needs a bean from `FirstConfiguration`, inject that bean or use appropriate auto-configuration ordering between the two auto-configurations. `@Order` on many Spring components has specific semantics and is not a general-purpose tool for controlling all bean creation.

## 9. Classpath Conditions and Optional Dependencies

Starters often have integrations that only activate when an external library is present.

For example, metrics auto-configuration activates only when the vendor metrics API is on the classpath.

### 9.1. Isolating Optional Integrations into Nested Configurations

```java
@AutoConfiguration
public class AcmeMetricsAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "com.vendor.metrics.MeterRegistry")
    static class MetricsConfiguration {

        @Bean
        @ConditionalOnMissingBean
        MetricsReporter metricsReporter(
                com.vendor.metrics.MeterRegistry registry) {
            return new VendorMetricsReporter(registry);
        }
    }
}
```

The idea is that only when the optional class is present does the nested configuration apply. This isolation prevents loading method signatures referencing optional types too early.

In the module's compile setup, the vendor dependency may be needed on the compile classpath to compile code, without necessarily being packaged as a mandatory dependency for every consumer. How optional/runtime scopes are declared depends on Maven/Gradle module design.

### 9.2. Using Class Names in Conditions for Optional Dependencies

```java
@ConditionalOnClass(
        name = "com.vendor.metrics.MeterRegistry")
```

A string class name does not require the JVM to resolve a class literal when reading the annotation. This helps ensure the condition can be evaluated even when the optional class is absent.

### 9.3. Do Not Reference Optional Classes in the Outer Configuration

If the outer auto-configuration has method parameters, fields, or return types directly referencing an optional class, the classloader can fail when that class is missing.

Keep all references to optional APIs inside nested configurations guarded by class conditions. This is especially important when a starter supports multiple classpath combinations.

### 9.4. `@ConditionalOnClass` Does Not Replace Dependency Management

The condition only decides whether to apply configuration. It does not download dependencies, pick versions, or fix conflicts.

If a class exists in too old a version, code can still hit `NoSuchMethodError` or `NoClassDefFoundError`. You may need version conditions or compatibility checks per library contracts.

## 10. Combining Multiple Conditions

Real-world auto-configurations often combine multiple conditions at once.

```java
@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
@EnableConfigurationProperties(GreetingProperties.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(
            GreetingProperties properties) {
        return new DefaultGreetingService(
                properties.getPrefix());
    }
}
```

Conditions on the same class combine with AND logic: all must match for the class-level configuration to apply. Bean methods also carry their own conditions.

### 10.1. Example Combining Property and Bean Conditions

```java
@Bean
@ConditionalOnBean(PaymentClient.class)
@ConditionalOnMissingBean(PaymentHealthIndicator.class)
PaymentHealthIndicator paymentHealthIndicator(
        PaymentClient client) {
    return new PaymentHealthIndicator(client);
}
```

Meaning:

- A `PaymentClient` bean exists.
- No `PaymentHealthIndicator` bean exists yet.
- When both hold, create the default health indicator.

### 10.2. Avoid Redundant Conditions

If a bean method takes a required `PaymentClient` parameter, Spring already needs that bean when invoking the method. `@ConditionalOnBean` still adds value by preventing bean definition registration when the dependency is absent, making context behavior and condition reports clearer.

However, do not add every conceivable condition. Every condition should represent a meaningful requirement for starter users.

### 10.3. Property Conditions and Property Binding Are Two Distinct Steps

`@ConditionalOnProperty` reads the Environment to decide whether configuration applies. `@EnableConfigurationProperties` registers an object to bind multiple properties into a typed bean.

A condition does not create the properties bean by itself. Nor does a properties bean automatically toggle auto-configuration unless used inside an appropriate condition.

## 11. Creating a Starter Module So Users Only Add One Dependency

In a library ecosystem, modules are commonly split into:

- `acme-greeting-spring-boot-autoconfigure`: contains auto-configuration, properties, and default implementations.
- `acme-greeting-spring-boot-starter`: dependency aggregator pulling in auto-config and required integrations.

Structure:

```text
acme-greeting/
├── acme-greeting-core/
├── acme-greeting-spring-boot-autoconfigure/
└── acme-greeting-spring-boot-starter/
```

### 11.1. Core Module

Contains plain Java contracts and implementations:

```text
acme-greeting-core
├── GreetingService.java
└── DefaultGreetingService.java
```

Core does not necessarily depend on Spring Boot.

### 11.2. Auto-Configure Module

Contains:

- `GreetingAutoConfiguration`.
- `GreetingProperties`.
- `AutoConfiguration.imports`.
- Configuration processor metadata if IDE completion is desired.
- Tests for conditions/back-off.

This module depends on Spring Boot autoconfigure and the core API.

### 11.3. Starter Module

Starters are typically very thin:

```xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-greeting-spring-boot-autoconfigure</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
```

The starter can add integration dependencies suited to its purpose. A starter does not necessarily need to contain source code.

### 11.4. Why Separate Auto-Config and Starter?

Benefits:

- Users add the starter without listing every dependency themselves.
- Auto-config can be consumed separately when tight dependency control is needed.
- The core library can be reused outside Spring Boot.
- Multiple starters can target different integrations while sharing core.

For small libraries, modules can be combined to reduce complexity. Split modules when it creates meaningful build/reuse boundaries.

## 12. Required Dependencies in the Auto-Configuration Module

Minimal Maven example:

```xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-greeting-core</artifactId>
        <version>1.0.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-configuration-processor</artifactId>
        <optional>true</optional>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

The Spring Boot parent/BOM manages compatible versions. If not using the parent, import the Boot dependency BOM or specify versions per project dependency management.

### 12.1. Configuration Processor

`spring-boot-configuration-processor` generates metadata for `@ConfigurationProperties` so IDEs provide autocomplete for properties. It is normally an optional/annotation-processor dependency per your build tool.

It is not a runtime requirement for binding to work. Runtime binding comes from Spring Boot infrastructure.

### 12.2. Test Dependencies

`spring-boot-starter-test` provides test utilities for Spring Boot. The auto-configuration module can use `ApplicationContextRunner` to quickly test each condition without booting an entire demo application.

### 12.3. Do Not Make Optional Integrations Mandatory Transitive Dependencies

If a metrics library is only needed when users turn on metrics integration, consider declaring it optional or splitting out an integration module. A good starter does not force every consumer to pull in unused client libraries.

## 13. Registering Auto-Configuration in Spring Boot 3

Create the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

One entry per line:

```text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
com.acme.greeting.autoconfigure.GreetingMetricsAutoConfiguration
```

Spring Boot reads this metadata to locate auto-configuration classes.

### 13.1. Do Not Use Component Scan for Discovery

If auto-configuration is only discovered because its package sits under the application's scan root, the starter will behave inconsistently whenever consumers place their application class in another package.

Registering via imports metadata lets the starter be discovered independently of consumer packages.

### 13.2. An Auto-Configuration Can Import Sub-Configurations

You can use nested configurations or `@Import` to split configuration. However, classes needing optional dependencies must still be guarded so they are not loaded when dependencies are absent.

### 13.3. Do Not Register the Same Class Twice via Multiple Mechanisms

If an auto-configuration is both listed in the imports file and component-scanned/explicitly imported another way, it can cause configuration duplication or confusing behavior.

Keep one clear discovery mechanism for auto-configuration classes.

### 13.4. Differences from Older Spring Boot 2

Older Spring Boot 2 projects typically registered auto-configurations under the `EnableAutoConfiguration` key in `META-INF/spring.factories`. Spring Boot 3 uses `AutoConfiguration.imports` for the auto-configuration list.

When upgrading an older starter, migrate metadata registration according to the target version. Do not blindly delete `spring.factories` if it still holds other Spring factories besides auto-configuration.

## 14. Writing Tests with `ApplicationContextRunner`

`ApplicationContextRunner` is well-suited for testing auto-configuration. It builds a lightweight context, applies specified configurations, supplies properties, and checks bean outcomes.

### 14.1. Testing the Default Bean

```java
package com.acme.greeting.autoconfigure;

import static org.assertj.core.api.Assertions.assertThat;

import com.acme.greeting.GreetingService;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    GreetingAutoConfiguration.class));

    @Test
    void createsDefaultGreetingService() {
        contextRunner
                .withPropertyValues(
                        "acme.greeting.enabled=true",
                        "acme.greeting.prefix=Hi")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);

                    GreetingService service =
                            context.getBean(GreetingService.class);

                    assertThat(service.greet("Lan"))
                            .isEqualTo("Hi, Lan");
                });
    }
}
```

This test verifies:

- Auto-configuration is applied.
- Property condition matches.
- Properties are bound.
- Default bean is created.
- Default implementation uses the configured prefix.

### 14.2. Testing Back-Off When User Provides a Bean

```java
@Test
void backsOffWhenUserProvidesGreetingService() {
    contextRunner
            .withUserConfiguration(
                    UserGreetingConfiguration.class)
            .run(context -> {
                assertThat(context)
                        .hasSingleBean(GreetingService.class);

                GreetingService service =
                        context.getBean(GreetingService.class);

                assertThat(service.greet("Lan"))
                        .isEqualTo("Welcome, Lan!");
            });
}

@Configuration(proxyBeanMethods = false)
static class UserGreetingConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return name -> "Welcome, " + name + "!";
    }
}
```

The most important test of this lesson: a user bean already exists, so auto-configuration must back off and the context has only one `GreetingService`.

### 14.3. Testing Property Disabling the Feature

```java
@Test
void doesNotCreateGreetingServiceWhenDisabled() {
    contextRunner
            .withPropertyValues(
                    "acme.greeting.enabled=false")
            .run(context -> {
                assertThat(context)
                        .doesNotHaveBean(GreetingService.class);
            });
}
```

This tests the class-level property condition. When the property does not match, the configuration is not applied.

### 14.4. Testing Default Behavior When Property Is Missing

Because the condition uses `matchIfMissing = true`, also test omitting `acme.greeting.enabled`:

```java
@Test
void enablesGreetingByDefault() {
    contextRunner.run(context -> {
        assertThat(context)
                .hasSingleBean(GreetingService.class);
    });
}
```

This verifies the feature's default semantics. If `matchIfMissing` is later changed to false, the test will catch the contract change.

### 14.5. Testing User Bean Still Works When Property Is Absent

If the feature is enabled by default and the user provides a custom bean, the default bean must back off. Test both when the property is omitted and when it is explicitly enabled.

This ensures back-off does not depend on a specific property value beyond the defined class-level condition.

### 14.6. Context Runner Tests Do Not Test the Imports File

In the example, `AutoConfigurations.of(GreetingAutoConfiguration.class)` names the auto-configuration class directly. It tests conditions and bean behavior, but does not prove the metadata file was packaged and read properly.

Add a consumer smoke test or artifact test to verify `AutoConfiguration.imports` is inside the JAR and Spring Boot discovers it automatically.

## 15. Verifying Discovery Through a Real Application Context

Create a demo application depending on the starter:

```java
@SpringBootApplication
public class GreetingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                GreetingDemoApplication.class, args);
    }
}
```

Controller:

```java
@RestController
public class GreetingController {

    private final GreetingService greetings;

    public GreetingController(GreetingService greetings) {
        this.greetings = greetings;
    }

    @GetMapping("/greet")
    public String greet(@RequestParam String name) {
        return greetings.greet(name);
    }
}
```

Application config:

```yaml
acme:
  greeting:
    enabled: true
    prefix: Greetings
```

When running, call:

```text
GET /greet?name=An
```

Expected result:

```text
Greetings, An
```

This test verifies auto-configuration is discovered via imports metadata on the consumer classpath, rather than only via direct class reference in tests.

### 15.1. Verifying Consumer Override

Add user configuration to the demo:

```java
@Configuration(proxyBeanMethods = false)
public class DemoGreetingConfiguration {

    @Bean
    GreetingService greetingService() {
        return name -> "Welcome, " + name + "!";
    }
}
```

The endpoint should return the user implementation's behavior. If the context reports two beans of the same type, verify whether `@ConditionalOnMissingBean` targets the right interface and whether auto-configuration is processed in the proper order.

## 16. Inspecting the Condition Report

When a bean fails to appear or a default bean fails to back off, the condition report shows which conditions matched or failed to match.

You can run the application with debug:

```bash
java -jar greeting-demo.jar --debug
```

Or set:

```properties
debug=true
```

Spring Boot prints the Condition Evaluation Report, including positive matches and negative matches for auto-configuration.

### 16.1. What to Look For

If the default bean is not created, check:

- Was the auto-configuration class recognized?
- Did `@ConditionalOnClass` match?
- Did `@ConditionalOnProperty` match?
- Did `@ConditionalOnMissingBean` see a user bean?
- Are there other conditions on nested configurations or methods?
- Was the configuration class excluded from auto-configuration?

### 16.2. Auto-Configuration Not Imported

If the class does not appear in the condition report:

1. Verify the exact imports file path.
2. Verify the FQCN content.
3. Verify the JAR artifact contains the resource.
4. Verify the starter/autoconfigure dependency is on the runtime classpath.
5. Verify class name and package after refactoring.
6. Check exclude configurations.

Do not rush to add `@ComponentScan` to mask unpackaged metadata.

### 16.3. Condition Report Is a Diagnostic Tool

The condition report shows auto-configuration decisions for that startup environment. It does not prove every method in a bean executes properly or that external services connect successfully.

Combine the report with context tests and behavioral assertions.

## 17. Advanced Conditions and Use Cases

### 17.1. `@ConditionalOnMissingBean` with Multiple Beans

Suppose an application has two `GreetingService` beans:

```java
@Bean
@Primary
GreetingService primaryGreetingService() {
    return name -> "Primary " + name;
}

@Bean
GreetingService secondaryGreetingService() {
    return name -> "Secondary " + name;
}
```

`@ConditionalOnMissingBean(GreetingService.class)` sees matching beans already exist and backs off. `@Primary` only determines the candidate for type-based injection; it does not make the condition act as if no bean exists.

### 17.2. `@ConditionalOnSingleCandidate` with Multiple DataSources

If only one `DataSource` exists or one is marked primary, the condition matches. If multiple `DataSource`s exist without an unambiguous candidate, the bean depending on a single `DataSource` is not created.

This helps auto-configurations pick a default datasource. If an integration supports multiple datasources, design beans with qualifiers or explicit configuration rather than forcing an implicit choice.

### 17.3. `@ConditionalOnBean` for a Specific Bean Type

For example, create an adapter only when the user declared a client:

```java
@Bean
@ConditionalOnBean(Clock.class)
TimeAwareGreetingService timeAwareGreetingService(
        Clock clock) {
    return new TimeAwareGreetingService(clock);
}
```

If `Clock` is absent, the bean is not created. In practice, if a suitable default `Clock` exists, an auto-configuration may create `Clock` first and later configurations consume it. Express ordering and back-off explicitly.

### 17.4. `@ConditionalOnExpression`

You can use SpEL when a condition requires an expression. However, specialized property conditions are usually clearer, more readable, and produce cleaner condition reports. Avoid putting complex logic in SpEL because it is harder to test and sensitive to type conversion.

### 17.5. `@ConditionalOnJava`

You can enable configuration based on the Java runtime:

```java
@AutoConfiguration
@ConditionalOnJava(
        range = ConditionalOnJava.Range.EQUAL_OR_NEWER,
        value = JavaVersion.TWENTY_ONE)
public class Java21AutoConfiguration {
}
```

Only use this when an integration genuinely requires a specific runtime version. Do not use the condition to hide incompatible dependencies; it is better to state baselines and version requirements clearly in artifact metadata/documentation.

## 18. Ordering Between Multiple Auto-Configurations

Suppose a starter has two configurations:

- `CoreAutoConfiguration` creates the core service.
- `WebAutoConfiguration` creates web support needing the core service.

You can declare:

```java
@AutoConfiguration
public class CoreAutoConfiguration {
    // Core beans.
}
```

```java
@AutoConfiguration(after = CoreAutoConfiguration.class)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
public class WebAutoConfiguration {
    // Web beans.
}
```

If you need to reference a configuration from an optional dependency, use name-based ordering so class literals do not force early resolution of optional classes.

### 18.1. Ordering Cannot Fix Missing Dependencies

If Web configuration needs a core bean, yet Core configuration did not match because a property is off, changing ordering alone will not make the bean appear. Verify whether the condition logic itself is appropriate.

### 18.2. Do Not Rely on Alphabetical Order

Class names or line order in the imports file are not an API contract for ordering beans. Use ordering annotations and explicit dependency graphs.

### 18.3. Avoiding Condition Cycles

If A only creates when bean B exists and B only creates when bean A exists, neither may ever be created. That is a dependency cycle at the configuration condition level.

Find an independent root initialization point or group tightly coupled beans into one configuration with clear logic.

## 19. Auto-Configuration Properties and IDE Metadata

Auto-configurations commonly expose `@ConfigurationProperties` so consumers can configure features.

Example:

```yaml
acme:
  greeting:
    enabled: true
    prefix: Welcome
```

Properties class:

```java
@ConfigurationProperties(prefix = "acme.greeting")
public class GreetingProperties {

    private String prefix = "Hello";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
```

### 19.1. Registering the Properties Bean

You can use:

```java
@EnableConfigurationProperties(GreetingProperties.class)
```

on the auto-configuration class. This ensures the properties type is registered when the configuration applies.

If the properties class is component-scanned or registered another way, a second registration mechanism may not be needed, though starters should maintain one consistent path.

### 19.2. Metadata Processor

`spring-boot-configuration-processor` generates metadata for `@ConfigurationProperties` so IDEs suggest property names, types, descriptions, and default values.

Metadata enhances developer experience. It is not the runtime source of truth and does not replace validation/binding.

### 19.3. Writing Useful Descriptions

Javadoc on property fields or additional metadata can explain:

- What the property does.
- Default value.
- Valid values.
- When to enable/disable it.
- Whether it can be overridden with a bean.

A user-friendly starter documents both its properties and its extension points.

## 20. Back-Off Does Not Override Every Bean in the Starter

If auto-configuration creates multiple beans:

```java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() { ... }

@Bean
GreetingFormatter greetingFormatter() { ... }

@Bean
GreetingMetrics greetingMetrics() { ... }
```

A user supplying `GreetingService` only makes that bean method back off. `GreetingFormatter` and `GreetingMetrics` may still be created.

If those beans depend directly on the default implementation, design them to depend on the `GreetingService` contract instead of `DefaultGreetingService`.

### 20.1. Depending on Interfaces

Good:

```java
@Bean
GreetingFacade greetingFacade(GreetingService service) {
    return new GreetingFacade(service);
}
```

Less flexible:

```java
@Bean
GreetingFacade greetingFacade(
        DefaultGreetingService service) {
    return new GreetingFacade(service);
}
```

When a user overrides the service with another implementation, the second bean cannot be injected.

### 20.2. Conditionalizing a Group by User Bean

If a group of default beans only makes sense when no overall extension interface exists, place conditions on the configuration class or individual beans depending on the goal. Check behavior when users override one bean while still expecting supporting beans.

Do not put `@ConditionalOnMissingBean` on the entire configuration class if that would accidentally drop infrastructure beans still needed when the user provides a custom implementation.

## 21. Common Mistakes When Writing Auto-Configuration

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Forgetting `AutoConfiguration.imports` | Boot does not discover auto-config | Verify resource path and artifact contents |
| Using component scan for discovery | Behavior depends on consumer packages | Register via imports metadata |
| Missing `@ConditionalOnMissingBean` | Creates default alongside user bean | Back off on the contract interface |
| Conditioning on concrete class | Custom implementations fail to trigger back-off | Condition on the API type |
| Using `@ConditionalOnBean` in wrong order | Condition misses required bean | Check auto-config ordering |
| Unclear defaults on `@ConditionalOnProperty` | Feature toggles unexpectedly | Specify `havingValue` and `matchIfMissing` |
| Optional class in outer method signature | Class loading fails when dependency is absent | Isolate in nested configuration with class condition |
| Pinning dependency versions arbitrarily | Conflicts with Boot BOM | Use Boot dependency management |
| Using `@Order` to control all beans | Misapplied ordering semantics | Use dependency injection and auto-config ordering |
| Bean depends on concrete default impl | User override breaks wiring | Depend on the interface |
| Using `@Primary` instead of back-off | Context retains unnecessary extra bean | Prevent creating default in the first place |
| Condition cycle: A needs B, B needs A | Neither configuration applies | Identify a root condition |
| Testing only by calling classes directly | Does not verify Spring conditions | Use `ApplicationContextRunner` |
| Testing context runner without testing imports | Packaged metadata may be missing | Add a consumer smoke test |
| Putting auto-config inside component scan package | May be registered twice | Separate packages and use imports |
| Adding too many conditions | Starter becomes unpredictable | Keep conditions minimal and meaningful |

## 22. Debugging When the Default Bean Fails to Back Off

If the context throws:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2
```

check in order:

1. Was the user bean actually registered in the same `ApplicationContext`?
2. Is the user bean assignable to the interface checked by the condition?
3. Does `@ConditionalOnMissingBean` check the right type/name?
4. Was the auto-configuration processed after user configuration?
5. Does another auto-configuration also create a bean for the same contract?
6. Does the bean method have an overly narrow return type or insufficient metadata?
7. Was the user configuration excluded by a condition or profile?
8. Is there a parent/child context with an unexpected search strategy?

### 22.1. Inspecting Bean Definitions

In tests, you can check:

```java
String[] names = context.getBeanNamesForType(
        GreetingService.class);

assertThat(names).hasSize(1);
```

If two beans exist, print their names and implementation classes to locate their registration sources. Never just slap `@Primary` on one and ignore why the default bean failed to back off.

### 22.2. Inspecting the Condition Report

Run with `--debug` and locate the corresponding auto-configuration. If `@ConditionalOnMissingBean` reports not matching, check which existing bean or target type the message cites.

If the condition did match even though the user bean should have been present, ordering or type prediction may not be working as intended.

### 22.3. Testing with Context Runner

A small test using `withUserConfiguration` usually yields answers much faster than debugging a whole application. When the runner test passes yet the consumer app fails, suspect discovery, package scanning, classpath, or context hierarchy.

## 23. Testing Classpath and Property Variations

An auto-configuration may run across many environmental combinations. Test representative scenarios.

| Scenario | Classpath | Property | User bean | Expected outcome |
| --- | --- | --- | --- | --- |
| Default | Greeting API present | `enabled` missing | No | Default created |
| Explicit enabled | Present | `enabled=true` | No | Default created |
| Disabled | Present | `enabled=false` | No | Service not created |
| User override | Present | `enabled=true` | Yes | Only user bean used |
| Optional library missing | Optional API absent | Feature needing API | No | Integration not created |
| Multiple candidates | Multiple collaborator beans | Feature enabled | Multiple beans | Created only if condition/candidate fits |
| Resource missing | Resource absent | Feature needing resource | No | Configuration not created |
| Invalid property value | API present | `enabled=invalid` | No | Condition does not match per defined semantics |

### 23.1. Testing Missing Classes

Spring Boot Test provides `FilteredClassLoader` to simulate a classpath missing a type/package:

```java
contextRunner
    .withClassLoader(
            new FilteredClassLoader(
                    OptionalMetricsApi.class))
    .run(context -> {
        assertThat(context)
                .doesNotHaveBean(MetricsReporter.class);
    });
```

This example assumes optional auto-configuration was designed not to reference optional types outside guarded nested configurations. If a class is still resolved early by an outer configuration, the test catches the issue.

### 23.2. Testing Missing Resources

Use appropriate classloader/resource setups or isolate resource-conditional logic into a dedicated configuration. Ensure tests truly test the condition rather than leaving dummy files on the test classpath that make conditions always match.

### 23.3. Testing Invalid Properties

If a condition requires `havingValue="true"`, values like `yes` or `invalid` must not implicitly count as true. Test explicitly to document the semantics the starter promises.

## 24. Practice Lab: Creating Auto-Configuration and Proving Back-Off

### Goal

Build `acme-greeting-spring-boot-autoconfigure` with a default service, properties, classpath/property conditions, and user override support.

### Step 1 — Create the Module

Create a Maven/Gradle module depending on Spring Boot Autoconfigure and the core module. Align versions via a compatible Boot BOM/plugin.

### Step 2 — Create the API

Create `GreetingService` with method `greet(String name)`. Keep the interface pure Java.

### Step 3 — Create the Default Implementation

Create `DefaultGreetingService` accepting a prefix via constructor. Do not annotate it with `@Component`.

### Step 4 — Create Properties

Create `GreetingProperties` with prefix `acme.greeting` and field `prefix` defaulting to `Hello`. Add descriptions/metadata if desired.

### Step 5 — Create the Auto-Configuration

Use:

- `@AutoConfiguration`.
- `@ConditionalOnClass`.
- `@ConditionalOnProperty` with intentional `matchIfMissing`.
- `@EnableConfigurationProperties`.
- `@Bean`.
- `@ConditionalOnMissingBean(GreetingService.class)`.

### Step 6 — Register Imports

Create `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` and add the auto-configuration's FQCN.

### Step 7 — Test Default

Use `ApplicationContextRunner` and `AutoConfigurations.of(...)`. Verify the default bean is created and the prefix is bound.

### Step 8 — Test User Override

Create a test configuration declaring a custom `GreetingService`. Assert only one bean exists for the interface and behavior comes from the user implementation.

### Step 9 — Test Disabled Property

Set `acme.greeting.enabled=false`. Assert the default service is not created.

### Step 10 — Test Missing Property

Omit the enabled property. Assert the outcome matches your chosen `matchIfMissing`.

### Step 11 — Test Optional Dependency

Create an integration depending on an optional class, guarded by a nested configuration and `@ConditionalOnClass(name=...)`. Use `FilteredClassLoader` to verify the context still boots when the optional class is absent.

### Step 12 — Test Consumer Discovery

Create a demo application adding only the starter dependency without explicit auto-configuration imports. Start the context and call the service. Check that the JAR includes the imports resource.

### Step 13 — Try Multiple Implementations

Register two user `GreetingService` beans. Confirm auto-config backs off, yet injection becomes ambiguous without primary/qualifier. Note that back-off only suppresses the default bean; it does not resolve multiple user-defined beans.

### Step 14 — Read the Condition Report

Run the demo with `--debug`. Locate positive/negative matches and explain each condition.

### Step 15 — Inspect the Artifact

Build the JAR and inspect it:

```bash
jar tf target/acme-greeting-spring-boot-autoconfigure-1.0.0.jar
```

Confirm `AutoConfiguration.imports` is inside the archive and its class name points to the right auto-configuration.

### Self-Check Questions

1. How does auto-configuration differ from component scanning?
2. Why should a starter provide a default bean that backs off?
3. Does `@ConditionalOnClass` check the classpath or the bean registry?
4. How do `@ConditionalOnBean` and `@ConditionalOnMissingBean` differ?
5. Why should conditions target the interface contract instead of the concrete default class?
6. How does `matchIfMissing=true` change property condition behavior?
7. How do class-level and method-level conditions differ?
8. Why is `@ConditionalOnMissingBean` sensitive to ordering?
9. Does `@AutoConfigureAfter` control singleton initialization order?
10. Why should optional classes be isolated in nested configurations?
11. Which resource registers auto-configuration in Spring Boot 3?
12. Which metadata did older Spring Boot 2 commonly use for auto-configuration?
13. Why does `@Primary` not replace back-off?
14. What can `ApplicationContextRunner` verify?
15. Why does a context runner test not prove the imports file was packaged?
16. How do you simulate a missing optional class with `FilteredClassLoader`?
17. Why should a `@Bean` method's return type reflect the contract?
18. Should a user bean in a parent context cause auto-configuration to back off?
19. When do you use `@ConditionalOnSingleCandidate`?
20. How do you debug a default bean appearing alongside a user bean?

## 25. Quick Reference Table

| Component | Role |
| --- | --- |
| `@AutoConfiguration` | Marks a Boot auto-configuration class |
| `AutoConfiguration.imports` | Registers auto-configurations for Boot discovery |
| `@ConditionalOnClass` | Applies only when class is on classpath |
| `@ConditionalOnMissingClass` | Applies only when class is absent |
| `@ConditionalOnProperty` | Toggles by Environment property |
| `@ConditionalOnBean` | Requires an already-registered bean |
| `@ConditionalOnMissingBean` | Creates default when no matching bean exists |
| `@ConditionalOnSingleCandidate` | Requires a single resolvable candidate |
| `@ConditionalOnResource` | Requires a resource to exist |
| `@ConditionalOnWebApplication` | Restricts to web applications |
| `@EnableConfigurationProperties` | Registers properties bean |
| `@Bean` | Creates bean from configuration method |
| Back-off | Auto-config skips default when matching user bean exists |
| Interface contract | Stable override point for applications |
| `@AutoConfigureBefore/After` | Controls processing order of auto-configurations |
| `@AutoConfigureOrder` | Declares auto-configuration order |
| Nested configuration | Isolates references to optional classes |
| `ApplicationContextRunner` | Fast testing of conditions and bean registration |
| `FilteredClassLoader` | Simulates classpath missing a class |
| Condition Evaluation Report | Explains positive/negative condition matches |
| Starter module | Aggregates dependencies for consumer convenience |
| Auto-configure module | Holds Spring Boot configuration logic |
| Core module | Holds API/logic independent of Spring |

**Core takeaway:** Auto-configuration should provide **sensible defaults, activate only when conditions fit, and respect application-declared beans**. Register configuration via `AutoConfiguration.imports`, apply appropriate classpath/property/bean conditions, put `@ConditionalOnMissingBean` on the contracts users need to replace, and verify both default and override paths with `ApplicationContextRunner`. Designed this way, a starter integrates seamlessly with Spring Boot while leaving control over behavior in the application's hands.
