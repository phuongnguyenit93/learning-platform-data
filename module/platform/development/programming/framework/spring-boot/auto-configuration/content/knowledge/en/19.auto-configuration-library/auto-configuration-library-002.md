# Creating an @AutoConfiguration Class and Registering It in the Imports File

> **Goal:** Package auto-configuration inside a library so Spring Boot applications discover and apply it simply by adding the dependency. The two core pieces are **a configuration class annotated with `@AutoConfiguration`** and **its fully qualified class name listed in the `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` resource** inside the published JAR.

This lesson belongs to the **Auto-Configuration Library** group, using Spring Boot 3.3.x and Java 17+. It covers the discovery mechanism, module/package layout, bean creation conditions, auto-configuration ordering, testing the imports resource, and verifying the JAR.

## 1. What Problem Does Auto-Configuration Solve?

A Java/Spring library may provide services, clients, serializers, or infrastructure components. If every application had to manually write the wiring beans for the library, integration code would be repetitive and prone to misconfiguration.

Spring Boot Auto Configuration lets a library propose a default configuration. When the library is on the classpath and the appropriate conditions are satisfied, Boot applies that configuration automatically. The application can still provide its own bean to replace the default.

For example, the `acme-greeting` library wants to provide `GreetingService`:

1. The application adds the library dependency.
2. Boot discovers `GreetingAutoConfiguration` from the imports resource.
3. Auto-configuration registers the default `GreetingService` when conditions allow.
4. If the application declares its own `GreetingService`, the default bean backs off.
5. If a property disables the feature, the configuration is not applied.

Consuming applications do not need to know the configuration class name or manually `@Import` it. Discovery is the responsibility of the auto-configuration mechanism.

**Distinction:** `@Configuration` is a standard Spring configuration annotation. `@AutoConfiguration` is a specialized Spring Boot annotation designed for auto-configuration classes discovered through `ImportCandidates`. Annotating a class with `@AutoConfiguration` without registering it in the imports file is not enough for Boot to discover it via `@EnableAutoConfiguration`.

## 2. Two Required Components

### 2.1. Configuration Class with @AutoConfiguration

Example:

~~~java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new GreetingService("Hello");
    }
}
~~~

`@AutoConfiguration` belongs to the `org.springframework.boot.autoconfigure` package. This annotation already carries the `@Configuration(proxyBeanMethods = false)` meta-annotation; there is no need to add `@Configuration` on the same class.

Each condition in the example has a specific purpose:

- `@ConditionalOnProperty` at the class level allows the entire auto-configuration to apply when `acme.greeting.enabled=true`. With `matchIfMissing=true`, the feature is enabled by default if the application does not declare the property.
- `@ConditionalOnMissingBean(GreetingService.class)` on the method creates the default bean only if the context does not already contain a compatible `GreetingService` bean.
- The method return type is the concrete `GreetingService` so bean conditions have sufficient type information during evaluation.

Auto-configuration should provide **replaceable defaults**. If the library has optional integrations, add appropriate conditions such as `@ConditionalOnClass` so they apply only when the dependency is present. Do not create beans unconditionally and force applications to delete or override them.

### 2.2. Auto-Configuration Registration Resource

Create the exact path inside the module containing the configuration class:

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

Content:

~~~text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
~~~

Each line is the **fully qualified class name** of an auto-configuration. Do not write short names, bean names, standalone package names, or Java file paths.

If the library has multiple independent configurations, list each class on its own line:

~~~text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
com.acme.greeting.autoconfigure.GreetingMetricsAutoConfiguration
com.acme.greeting.autoconfigure.GreetingWebAutoConfiguration
~~~

You can add comment lines starting with `#` in the imports file:

~~~text
# Core integration
com.acme.greeting.autoconfigure.GreetingAutoConfiguration

# Optional web integration
com.acme.greeting.autoconfigure.GreetingWebAutoConfiguration
~~~

The path and filename are strictly case-sensitive. `AutoConfiguration.imports` must reside under `META-INF/spring/`; placing it inside a Java package or directly under `META-INF/` prevents Boot from finding it via this convention.

**Do not confuse with `spring.factories`:** Since Spring Boot 2.7, auto-configuration candidates are registered through the dedicated imports resource. With Spring Boot 3.3, use `AutoConfiguration.imports` for auto-configurations. `spring.factories` can still serve other extension points, but do not use the legacy `EnableAutoConfiguration` key to register new auto-configurations.

## 3. Recommended Module and Package Structure

A minimal autoconfigure module:

~~~text
acme-greeting-autoconfigure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/acme/greeting/
    │   │       ├── GreetingService.java
    │   │       └── autoconfigure/
    │   │           └── GreetingAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/
    │           └── spring/
    │               └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/
            └── com/acme/greeting/autoconfigure/
                └── GreetingAutoConfigurationTests.java
~~~

Place library APIs and auto-configurations in intentional packages. A consuming application might have the root package `com.example.app`; the library has its own `com.acme.greeting` package so it does not accidentally become a target of the application's regular component scan.

**Auto-configurations must be loaded via the imports file.** Spring Boot recommends placing these classes in their own package and ensuring they are **not** targets of component scanning. Do not add `@ComponentScan` to an auto-configuration to scan the entire library package. If helper configurations or specific components are needed, use explicit `@Import`.

Practical rules:

- Name classes ending with `AutoConfiguration`, such as `GreetingAutoConfiguration`.
- Prefer top-level classes over nested classes.
- Keep auto-configurations outside root packages typically scanned by user applications.
- Do not annotate auto-configurations with `@Component` or plain `@Configuration` expecting component scan to discover them.
- Class names in the imports file must match the exact compiled package and class name.

### If the Class Is a Nested Class

In the rare case where an auto-configuration is not a top-level class, the name in the imports file uses `$` to separate the enclosing and nested classes, for example:

~~~text
com.acme.Outer$NestedAutoConfiguration
~~~

Although this syntax is supported, top-level classes are generally easier to find, order, and maintain.

## 4. How Does Boot Find the Imports File?

In a consuming application, `@SpringBootApplication` includes `@EnableAutoConfiguration`. `@EnableAutoConfiguration` uses Boot's import selector mechanism to locate auto-configuration candidates from `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` resources on the classpath.

When an application has multiple library JARs, Boot locates matching resources across the classpath and aggregates all candidates. Thus each autoconfigure JAR can provide a resource with the same path listing its own classes.

High-level flow:

~~~text
Application starts
       |
       v
@SpringBootApplication
       |
       v
@EnableAutoConfiguration
       |
       v
AutoConfigurationImportSelector
       |
       v
Read AutoConfiguration.imports on classpath
       |
       v
Filter candidates by exclusions and conditions
       |
       v
Apply matching auto-configurations
       |
       v
Register eligible default beans
~~~

This is a high-level flow; Boot also performs metadata, ordering, and condition processing before beans are created.

### No Need to Manually Import Classes in the Application

The consuming application only needs the library dependency and optional property configuration:

~~~yaml
acme:
  greeting:
    enabled: true
~~~

With the `matchIfMissing=true` default shown in the example, the property can be omitted entirely and the feature stays enabled by default. To disable it:

~~~properties
acme.greeting.enabled=false
~~~

When `@SpringBootApplication` enables auto-configuration, Boot finds the class from the imports file. Users do not need to add:

~~~java
@Import(GreetingAutoConfiguration.class)
~~~

Direct `@Import` can load a configuration in special cases, but if the goal is publishing a self-configuring library that works upon adding a dependency, it must be registered properly in the imports file.

## 5. Conditions in Auto-Configuration

`@AutoConfiguration` only marks a class as an auto-configuration; it does not decide which beans should be created. Conditions determine the scope of application.

### 5.1. Classpath Conditions

`@ConditionalOnClass` applies a configuration only when a class is present on the runtime classpath. For example, a library providing an integration for an optional client:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.client.VendorClient")
    static class VendorClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        VendorGreetingClient vendorGreetingClient() {
            return new VendorGreetingClient();
        }
    }
}
~~~

This snippet is a structural example; `VendorGreetingClient` and the vendor library must be provided in the appropriate module. The key point is that the nested configuration class is guarded by the classpath condition. When a dependency is optional, do not put a `@Bean` method on an always-loaded class whose return type is directly an absent class; the JVM may need to load that type before the method-level condition is evaluated. Isolate optional dependencies into a nested configuration with a class-level condition.

In composed meta-annotations containing `@ConditionalOnClass` or `@ConditionalOnMissingClass`, Boot documentation requires using the `name` attribute rather than referencing the class via `value` in that scenario.

### 5.2. Bean Conditions

`@ConditionalOnMissingBean` is the standard pattern for letting applications replace defaults:

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new GreetingService("Hello");
}
~~~

If the application already has a `GreetingService` bean, the default method does not register that bean. Other default beans in the same auto-configuration can still be created if their own conditions match.

`@ConditionalOnBean` applies a supporting bean only when a dependency bean already exists. Bean conditions only see bean definitions already processed at the time the condition runs; therefore, order auto-configurations when depending on another provider.

### 5.3. Property Conditions

`@ConditionalOnProperty` allows toggling based on deployment configuration:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {
    // @Bean methods
}
~~~

Explicitly specify `havingValue` for boolean flags. By default if omitted, any property present and not equal to the string `false` can match; that is not equivalent to requiring `true` exactly. `matchIfMissing` determines whether omitting the key counts as a match.

### 5.4. Other Conditions

Depending on the goal, Boot also provides `@ConditionalOnResource`, `@ConditionalOnWebApplication`, `@ConditionalOnNotWebApplication`, and `@ConditionalOnExpression`. Pick the condition matching what needs checking: classpath, bean, property, resource, or application type. Avoid SpEL expressions that directly reference beans whenever possible, as those beans may be initialized too early during context refresh.

## 6. Ordering Auto-Configurations

If an auto-configuration needs to run after another provider configuration, declare the ordering relationship:

~~~java
@AutoConfiguration(after = JacksonAutoConfiguration.class)
public class GreetingJsonAutoConfiguration {
    // Bean depending on Jackson configuration
}
~~~

Ordering attributes of `@AutoConfiguration`:

- `before`: runs before the specified auto-configuration classes.
- `beforeName`: runs before classes specified by fully qualified string name.
- `after`: runs after the specified auto-configuration classes.
- `afterName`: runs after classes specified by fully qualified string name.

Use `afterName` when referencing a configuration name without requiring a compile-time dependency on that class in the module. When auto-configurations do not need direct knowledge of each other yet still need relative ordering, `@AutoConfigureOrder` can be used.

**Auto-configuration ordering affects only bean definition registration order.** It does not dictate the order in which bean objects are instantiated later; bean creation order is governed by dependency injection and `@DependsOn` relationships if any. Do not use `@AutoConfigureOrder` as a substitute for dependency injection or to control constructor invocation order.

Do not rely on line order in `AutoConfiguration.imports` to establish provider/consumer relationships. Declare `before`/`after` explicitly.

## 7. Complete Example: Greeting Library

This section combines the class, imports resource, and tests into a coherent example.

### 7.1. Service API

**File:** `src/main/java/com/acme/greeting/GreetingService.java`

~~~java
package com.acme.greeting;

public record GreetingService(String prefix) {

    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
~~~

This is the library API class. It does not depend on Spring; auto-configuration is solely responsible for registering a default instance.

### 7.2. Auto-Configuration Class

**File:** `src/main/java/com/acme/greeting/autoconfigure/GreetingAutoConfiguration.java`

~~~java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new GreetingService("Hello");
    }
}
~~~

`@ConditionalOnProperty` is the overall condition on the configuration. `@ConditionalOnMissingBean` on the method lets the application supply another implementation. The return type is explicitly declared as `GreetingService` so conditions see the type clearly.

### 7.3. Imports Resource

**File:** `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

~~~text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
~~~

This step enables Boot to discover the class automatically when the JAR is on the classpath. The resource belongs to the autoconfigure module, not the application's YAML configuration file.

### 7.4. Consuming Application Configuration

When using the default:

~~~yaml
acme:
  greeting:
    enabled: true
~~~

The application can inject the service:

~~~java
package com.example.app;

import com.acme.greeting.GreetingService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showGreeting(GreetingService greetingService) {
        return args -> System.out.println(
                greetingService.greet("Lan"));
    }
}
~~~

When configuration is valid and the default service is registered, stdout is:

~~~text
Hello, Lan!
~~~

If the application declares its own `GreetingService`, `@ConditionalOnMissingBean` causes the default to back off. If `acme.greeting.enabled=false`, the configuration does not create the service bean; the application then cannot inject `GreetingService` unless another bean provides it.

**Application package vs. library package:** `com.example.app` is not a parent package of `com.acme.greeting`, so `@SpringBootApplication`'s default component scan does not scan the library's auto-configuration class. Boot still discovers it through the imports file.

## 8. Testing Both Conditions and Imports File Discovery

A common mistake is testing auto-configuration directly with `AutoConfigurations.of(...)` and concluding that the imports file is correct. That approach **does not test the resource**: the test specifies the class directly. You need at least one test running through `@EnableAutoConfiguration` to prove Boot can read the imports file.

The following test example uses Java 17+, Spring Boot 3.3.x, JUnit Jupiter, and AssertJ. Place the file in the same module as the `src/main/resources` resource above.

**File:** `src/test/java/com/acme/greeting/autoconfigure/GreetingAutoConfigurationTests.java`

~~~java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner directRunner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(GreetingAutoConfiguration.class));

    @Test
    void enableAutoConfigurationDiscoversImportsFile() {
        new ApplicationContextRunner()
                .withUserConfiguration(ImportDiscoveryApplication.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("Hello, Lan!");
                });
    }

    @Test
    void missingEnabledPropertyUsesDefaultAndRegistersService() {
        directRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(GreetingService.class);
        });
    }

    @Test
    void falsePropertyDisablesAutoConfiguration() {
        directRunner.withPropertyValues("acme.greeting.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(GreetingService.class);
                });
    }

    @Test
    void userBeanMakesDefaultBackOff() {
        directRunner.withUserConfiguration(UserGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context).hasBean("customGreetingService");
                    assertThat(context).doesNotHaveBean("greetingService");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("Welcome, Lan!");
                });
    }

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class ImportDiscoveryApplication {
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGreetingConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return new GreetingService("Welcome");
        }
    }
}
~~~

Explanation of the two test paths:

- `enableAutoConfigurationDiscoversImportsFile` uses a configuration annotated with `@EnableAutoConfiguration`. Boot must read `AutoConfiguration.imports` from the classpath itself to locate `GreetingAutoConfiguration`. This is the critical test for registration.
- The remaining three tests use `AutoConfigurations.of(GreetingAutoConfiguration.class)` to load the class directly, focusing on default property behavior and back-off. They do not replace the discovery test above.

Run in a Maven module with Spring Boot 3.3.x:

~~~bash
mvn -Dtest=GreetingAutoConfigurationTests test
~~~

Or with the Gradle wrapper:

~~~bash
./gradlew test --tests com.acme.greeting.autoconfigure.GreetingAutoConfigurationTests
~~~

**Expected result:** 4 tests PASS, with no fixed stdout because the tests use assertions. The discovery test confirms the service is found via the imports file; the remaining tests confirm the default works, a false property disables the configuration, and a user bean replaces the default.

## 9. Packaging and Inspecting the JAR

Resources in `src/main/resources` are copied into output resources by Maven/Gradle and packaged inside the JAR. A common mistake is having the file in the IDE but placed in the wrong module or misnamed so it does not appear in the published artifact.

With Maven:

~~~bash
mvn clean package
~~~

Inspect the JAR:

~~~bash
jar tf target/acme-greeting-autoconfigure-1.0.0.jar
~~~

The listing must contain exactly:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

On Windows PowerShell, you can filter:

~~~powershell
jar tf target/acme-greeting-autoconfigure-1.0.0.jar |
    Select-String "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports"
~~~

If the resource is missing:

1. Check the filename and letter casing.
2. Check that the file is under `src/main/resources/META-INF/spring/`, not `src/test/resources`.
3. Check that the module containing the auto-configuration is actually built and published.
4. Check whether the build configuration excludes that resource.
5. Check that the resource content lists the exact class name matching the compiled package and class.

Merely confirming the file exists in the JAR still does not prove the class is applied; run a discovery test with `@EnableAutoConfiguration` or a real consuming application.

## 10. Custom Starter Structure

For simple libraries, API code, auto-configurations, and the imports resource can be combined in a single module. When a library has many dependencies or multiple optional integrations, split it into two modules:

~~~text
acme/
├── acme-spring-boot-autoconfigure/
│   ├── API and AutoConfiguration classes
│   ├── META-INF/spring/AutoConfiguration.imports
│   └── configuration metadata
└── acme-spring-boot-starter/
    └── dependency declarations
~~~

Roles:

- **Autoconfigure module:** contains configuration classes, supporting APIs, `@ConfigurationProperties`, the imports resource, and conditions.
- **Starter module:** usually a very small JAR that aggregates the autoconfigure dependency along with required dependencies so users only need to add one starter.

Splitting into two modules is not mandatory. If the library has few components, minimal optional dependencies, and simple configuration, combining them can make sense.

If the autoconfigure module references an optional vendor library, consider declaring that dependency as optional in build metadata so users can consume the autoconfigure module without pulling in every integration. A starter tailored for a specific use case can add the corresponding vendor dependency.

Module names should use the library's own namespace, such as `acme-spring-boot-autoconfigure` and `acme-spring-boot-starter`. Avoid starting your own library module names with `spring-boot`.

## 11. Configuration Metadata and Class Replacements

### 11.1. Condition Metadata

Spring Boot can use the `spring-boot-autoconfigure-processor` annotation processor to collect auto-configuration condition metadata, helping filter candidates early and improving startup in some cases. In Maven, declare the annotation processor in the compiler plugin configuration; in Gradle, use the `annotationProcessor` configuration.

If the library provides `@ConfigurationProperties`, `spring-boot-configuration-processor` can generate `META-INF/spring-configuration-metadata.json` so IDEs suggest property names, types, and descriptions. This is user-facing configuration metadata, **distinct** from `AutoConfiguration.imports` used for class discovery.

| Resource | Purpose |
| --- | --- |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Lists auto-configuration classes for Boot discovery |
| `META-INF/spring-autoconfigure-metadata.properties` | Condition metadata used to optimize auto-configuration filtering |
| `META-INF/spring-configuration-metadata.json` | Property descriptions supporting IDEs and documentation |

The processors do not replace the imports file. An auto-configuration class must still be registered in the imports resource.

### 11.2. Renaming or Replacing an Auto-Configuration Class

An auto-configuration class may be referenced by other classes via `before`/`after` or exclusion lists. When changing packages or replacing a class, you may need the resource:

**`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements`**

Example content:

~~~text
com.acme.greeting.autoconfigure.LegacyGreetingAutoConfiguration=com.acme.greeting.autoconfigure.GreetingAutoConfiguration
~~~

This file maps the old class to its replacement. At the same time, update `AutoConfiguration.imports` to list only the new class; do not continue registering both the old class and the replacement if they represent the same configuration.

This is a maintenance scenario for already-published libraries, not a required resource for a new starter.

## 12. Common Mistakes

1. **Creating an `@AutoConfiguration` class but forgetting the imports file:** Boot does not auto-discover a class merely because it resides in a JAR.
2. **Wrong resource path:** the file must live under `META-INF/spring/` with the exact name `org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
3. **Writing incomplete class names:** you must use the FQCN, including package and class name.
4. **Putting the imports file in test resources:** the resource is absent from the main artifact consumed by applications.
5. **Component-scanning auto-configurations:** this can cause configurations to be loaded as regular configurations, outside the intended auto-configuration mechanism and condition ordering. Keep them in a dedicated package and register them only through the imports file.
6. **Using `spring.factories` from outdated guides:** in Boot 3.3, register auto-configurations using the imports file.
7. **Placing missing-bean conditions on methods returning `Object`:** type metadata may be insufficient for Boot to evaluate accurately; return a concrete type.
8. **Not using `@ConditionalOnMissingBean` for replaceable defaults:** applications may end up with multiple beans for the same role and fail candidate selection.
9. **Confusing imports file line order with processing order:** use `before`/`after` or `@AutoConfigureOrder` when ordering is needed.
10. **Using auto-configuration ordering to control bean initialization order:** dependency injection and `@DependsOn` govern object instantiation order.
11. **Using component scan inside auto-configuration:** if helpers are needed, prefer explicit `@Import` rather than scanning an entire package.
12. **Testing only with `AutoConfigurations.of`:** this loads the class directly and does not prove the imports file is packaged or read.
13. **Checking only that the JAR contains the file:** you still need a discovery test to catch wrong FQCNs, unloadable classes, or unmatched conditions.
14. **Registering the same class via multiple mechanisms:** avoid listing a class in imports while also scanning/importing it as a regular configuration without a clear reason.

## 13. Library Release Checklist

- [ ] Auto-configuration class uses `@AutoConfiguration` and resides in a dedicated package.
- [ ] Default beans have appropriate conditions, typically `@ConditionalOnMissingBean`.
- [ ] Property conditions specify `havingValue` and `matchIfMissing` explicitly for boolean flags.
- [ ] Imports resource is at the exact path under `src/main/resources`.
- [ ] Every entry is an accurate FQCN; comments use `#` if needed.
- [ ] Auto-configuration classes are not component-scanned.
- [ ] Optional dependencies are isolated with appropriate conditions.
- [ ] `ApplicationContextRunner` tests cover defaults, properties, and user overrides.
- [ ] Discovery test verifies loading via `@EnableAutoConfiguration`.
- [ ] Built JAR contains the imports resource.
- [ ] Property and module names use the library's own namespace.
- [ ] Starter module pulls in the required dependencies for intended use cases.

## 14. Knowledge Self-Check

1. A class has `@AutoConfiguration` but is missing from `AutoConfiguration.imports`. Will `@SpringBootApplication` auto-discover it?  
   **Answer:** Not via auto-configuration discovery; the class must be registered in the imports resource.

2. Should the class entry in the imports file be `GreetingAutoConfiguration` or the FQCN?  
   **Answer:** The FQCN, such as `com.acme.greeting.autoconfigure.GreetingAutoConfiguration`.

3. Is putting the imports resource in `src/test/resources` sufficient for applications consuming the library?  
   **Answer:** No; it must be in main resources and packaged inside the published JAR.

4. Why should auto-configurations not be component-scanned?  
   **Answer:** Boot requires auto-configurations to be loaded via the imports file to preserve proper filtering, ordering, and condition evaluation. Component scanning can cause them to be processed as regular configurations.

5. What does `@ConditionalOnMissingBean` on a default method provide?  
   **Answer:** It lets a bean declared by the application replace the default; other default beans in the same class can still be applied.

6. Does a test using `AutoConfigurations.of(GreetingAutoConfiguration.class)` verify the imports file?  
   **Answer:** No; it loads the class directly. Use an `@EnableAutoConfiguration` test to verify discovery.

7. What does `@AutoConfiguration(after = OtherAutoConfiguration.class)` control?  
   **Answer:** The application/bean-definition registration order of auto-configurations, not object instantiation order.

8. If a published auto-configuration is renamed, which resource may need updating to map the old class to the new one?  
   **Answer:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements`, while updating the imports file to list only the replacement class.

## Official Documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `@AutoConfiguration`, imports file, component-scan rule, ordering, conditions, and testing.
- [Spring Boot 3.3 API — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): meta-annotation, `before`/`after` attributes, and auto-configuration semantics.
- [Spring Boot 3.3 API — EnableAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html): mechanism for enabling auto-configuration in applications.
- [Spring Boot 3.3 API — ImportAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/ImportAutoConfiguration.html): selective loading of auto-configurations; useful in certain scenarios, especially in tests.
- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata.html): property metadata supporting IDEs and documentation.

**Key takeaway:** An auto-configuring library requires both **an `@AutoConfiguration` class** and **the `AutoConfiguration.imports` resource packaged in the JAR**. The class provides beans and conditions; the imports file lets Boot find the class; `@EnableAutoConfiguration` triggers discovery; tests must verify both real discovery and default/back-off behavior.
