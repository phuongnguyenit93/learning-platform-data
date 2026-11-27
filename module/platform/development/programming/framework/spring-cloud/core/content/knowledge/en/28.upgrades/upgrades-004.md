# Distinguishing Registration Mechanisms in spring.factories and AutoConfiguration.imports

## 1. Why Did the Registration Mechanism Change?

Spring Boot needs to know which auto-configurations can apply when an application starts. Before Spring Boot 2.7, libraries typically declared these classes via the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key in `META-INF/spring.factories`. Starting in Spring Boot 2.7, a dedicated file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` was introduced to list auto-configurations.

This is a change to **how auto-configurations are discovered**, not a complete removal of `spring.factories`. Spring Boot 3 specifically removed the `EnableAutoConfiguration` key from the `spring.factories` mechanism, while other extension points continue to use that file. Spring Cloud also uses `spring.factories` for certain bootstrap configurations when an application enables the legacy bootstrap context.

If you upgrade a library and delete `spring.factories` entirely, extension points that still depend on it may stop working. Conversely, if you keep only the old auto-configuration key, the library will not be discovered on Spring Boot 3 or later.

This lesson belongs to the **Upgrades** chapter of the **SPRING_CLOUD_CORE** module. The module focuses on Spring Cloud Commons, Spring Cloud Context, external configuration, Spring Boot compatibility, refresh scope, discovery, service registry, service-to-service communication, and testing/operating common abstractions.

After this lesson, learners can:

- Explain the roles of `META-INF/spring.factories` and `AutoConfiguration.imports`.
- Distinguish factory/SPI registration from auto-configuration candidate registration.
- Describe the transition milestones from Spring Boot 2.6 to 2.7 and 3.x.
- Design dual registration when a library must support both Boot 2.x and 3.x.
- Identify Spring Cloud bootstrap and Spring Boot extension points that still use `spring.factories`.
- Understand the impact of `@AutoConfiguration`, conditions, ordering, and exclusions.
- Test auto-configuration and inspect resources inside the packaged JAR.
- Detect errors caused by shading, resource merging, duplicate registration, or incompatible classes.

## 2. Two Registration Mechanisms Serving Different Needs

### 2.1. META-INF/spring.factories

`spring.factories` is a properties file inside a JAR:

```text
META-INF/spring.factories
```

Each key is the fully qualified name of a factory interface or extension point. The value is a comma-separated list of implementation class names. Spring uses `SpringFactoriesLoader` to read these resources on the classpath and load the corresponding implementations.

Abbreviated example:

```properties
com.acme.spi.PaymentProvider=\
com.acme.payment.CardPaymentProvider,\
com.acme.payment.BankTransferProvider
```

An application or framework can request all implementations of the key `com.acme.spi.PaymentProvider`. The file can contain multiple keys for different extension points:

```properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=\
com.acme.cloud.AcmeBootstrapConfiguration

org.springframework.boot.autoconfigure.AutoConfigurationImportFilter=\
com.acme.autoconfigure.AcmeImportFilter
```

The keys in this example have distinct purposes. The bootstrap key is used by Spring Cloud when creating the bootstrap context; the filter key is a Spring Boot SPI used to filter auto-configuration candidates. They are not the application's default auto-configuration list.

Characteristics of `spring.factories`:

- One file can register multiple extension points.
- Each key maps to one or more implementations.
- The value list is comma-separated, not one class per line.
- The framework must know which key to read and the rules for instantiating implementations.
- Multiple JARs can each provide a `META-INF/spring.factories` resource; when running on the classpath, the loader can read the corresponding resources from multiple JARs.

### 2.2. AutoConfiguration.imports

`AutoConfiguration.imports` is a dedicated list for Spring Boot auto-configurations. Full path:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line is the fully qualified name of an auto-configuration class:

```text
com.acme.autoconfigure.AcmeAutoConfiguration
com.acme.autoconfigure.AcmeWebAutoConfiguration
# Comments starting with a hash can be added
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
```

Spring Boot locates this file in published JARs, reads the listed classes, and processes them as auto-configuration candidates. For nested classes, the class name uses `$` to separate the outer class and inner class.

Characteristics of the imports file:

- Lists only auto-configuration classes, not every kind of SPI.
- Each line is a single fully qualified class name.
- Can contain comments starting with `#`.
- Has no key-value pairs or commas separating classes.
- Auto-configurations must be declared via this file; do not rely on component scanning for discovery.

### 2.3. Direct Comparison

| Criterion | `spring.factories` | `AutoConfiguration.imports` |
| --- | --- | --- |
| Format | Java properties | Line-delimited list |
| Structure | Key → list of implementations | One auto-configuration class per line |
| Scope | Multiple factory/SPI extension points | Boot auto-configuration candidates |
| Loading mechanism | `SpringFactoriesLoader` by key | Boot reads imports during auto-configuration selection |
| Comments | Properties syntax | Lines starting with `#` |
| Used for auto-configuration from Boot 3 | Legacy `EnableAutoConfiguration` key not used | Standard mechanism |
| Used for Spring Cloud Bootstrap | Yes, via `BootstrapConfiguration` key | Does not replace the bootstrap key |

Both files can coexist in the same JAR because they serve different purposes. A class appearing in `spring.factories` does not mean Spring Boot automatically treats it as auto-configuration; that depends on the key the framework is reading.

## 3. Milestones Across Spring Boot Versions

### 3.1. Spring Boot 2.6 and Earlier

In versions prior to 2.7, auto-configurations were registered under the key:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.autoconfigure.AcmeAutoConfiguration,\
com.acme.autoconfigure.AcmeWebAutoConfiguration
```

Spring Boot reads this list to discover candidates. If a library supports only Boot 2.6 or earlier, this is the required mechanism.

### 3.2. Spring Boot 2.7

Spring Boot 2.7 introduced:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

The release notes recommend moving auto-configurations to the imports file. However, Boot 2.7 still reads the legacy key in `spring.factories` for backward compatibility. If the same class is listed in both files, Boot 2.7 deduplicates it.

This creates a helpful transition window: a library can ship both the old and new files to support applications running on pre-2.7 Boot and Boot 2.7.

### 3.3. Spring Boot 3.x

Spring Boot 3 removed support for registering auto-configurations via the key:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration
```

in `spring.factories`. Libraries need the imports file for auto-configurations to be discovered on Boot 3.

An important point in the migration guide: other keys in `spring.factories` are unaffected. For example, `EnvironmentPostProcessor`, `AutoConfigurationImportFilter`, `AutoConfigurationImportListener`, or Spring Cloud `BootstrapConfiguration` may still need this resource per their respective APIs.

### 3.4. Spring Boot 4.x

Spring Boot 4 continues to use `AutoConfiguration.imports` as its auto-configuration discovery mechanism. Current documentation for creating auto-configurations describes this exact resource and declaring one class per line.

SPIs such as `EnvironmentPostProcessor` and `AutoConfigurationImportFilter` still have APIs requiring registration via `META-INF/spring.factories`. Therefore, when upgrading a library to Boot 4, classify each key individually rather than deleting the file by a blanket rule.

### 3.5. Compatibility Matrix

| Spring Boot version | Reads auto-config from legacy `spring.factories` key | Reads `AutoConfiguration.imports` | Packaging guidance |
| --- | --- | --- | --- |
| 2.6 and below | Yes | New mechanism not supported yet | Requires legacy key |
| 2.7 | Yes, for backward compatibility | Yes | Can list in both; Boot 2.7 deduplicates |
| 3.x | No | Yes | Use imports file |
| 4.x | No | Yes | Use imports file; keep `spring.factories` for active SPIs |

The matrix above applies to **auto-configuration registration**. It does not mean Boot 3/4 stops reading all `spring.factories` resources.

## 4. Dual Registration When a Library Supports Multiple Boot Lines

### 4.1. When Do You Need to Keep Both Files?

If a library must support:

- Applications still running Spring Boot 2.6 or lower.
- Applications running Spring Boot 2.7.
- Applications running Spring Boot 3.x or 4.x.

then a common strategy is registering the same auto-configuration class in both locations:

```properties
# META-INF/spring.factories
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.autoconfigure.AcmeAutoConfiguration
```

```text
# META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
com.acme.autoconfigure.AcmeAutoConfiguration
```

Outcome by version:

- Boot 2.6 reads the legacy key and ignores the imports file it does not yet support.
- Boot 2.7 reads both and deduplicates the identical class.
- Boot 3/4 uses the imports file; the legacy auto-configuration key in `spring.factories` is no longer processed.

This is intentional dual registration. You do not need to create two separate auto-configuration classes just to register in both places.

### 4.2. Note on the @AutoConfiguration Annotation

`@AutoConfiguration` was introduced in Spring Boot 2.7. It is a specialized annotation for auto-configuration classes and is meta-annotated with `@Configuration`. It also provides ordering attributes such as `before`, `after`, `beforeNames`, and `afterNames`.

If the artifact must run on Boot 2.6, pay attention to binary compatibility: Boot 2.6 does not have the `@AutoConfiguration` annotation class. A class compiled with this annotation may be incompatible when loaded on a 2.6 runtime, even if the old `spring.factories` file is retained.

For a single binary that must run across Boot 2.6 through 4.x, the conservative option is:

- Compile against the lowest supported baseline API.
- Use `@Configuration(proxyBeanMethods = false)` on the shared registration class.
- Register that class in both resources.
- Use condition/ordering APIs present in the lowest baseline.
- Test the artifact on every Boot line declared as supported.

If supporting only Boot 2.7 or higher, use `@AutoConfiguration` on top-level auto-configurations per current guidance. If you need to leverage newer APIs while still supporting Boot 2.6, consider publishing a separate artifact/variant instead of letting one binary reference a class missing on the older runtime.

### 4.3. Example of a Multi-Version Compatible Class

Example class using `@Configuration` to avoid referencing an annotation available only from Boot 2.7:

```java
package com.acme.autoconfigure;

import com.acme.client.AcmeClient;

import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(AcmeClient.class)
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient() {
        return new AcmeClient();
    }
}
```

This example only illustrates a class registered in both resources. In a real library, add property binding, appropriate conditions, and isolate optional dependency types into nested configuration classes to prevent class-loading errors when optional dependencies are absent from the classpath.

### 4.4. Do Not Let the Two Lists Drift Apart

When maintaining dual registration, both files must declare the same corresponding set of auto-configurations for supported versions.

Failure examples:

- Class A is only in `spring.factories`: Boot 2.6 finds it, but Boot 3/4 does not.
- Class B is only in the imports file: Boot 3/4 finds it, but Boot 2.6 does not.
- A class changed packages, but a resource retains the old name: Boot tries to load a nonexistent class.
- A class was deleted from source, yet remains in a resource: applications may fail during import.

Maintain the auto-configuration list as part of artifact testing rather than updating it manually in multiple places without cross-checks.

## 5. Extension Points That Still Use spring.factories

### 5.1. SpringFactoriesLoader Is Broader Than Auto-Configuration

`spring.factories` is not synonymous with "the auto-configuration list." It is a registry for many factory interfaces. Boot 3 only removed using the `EnableAutoConfiguration` key to discover auto-configurations; other keys can still be read by the framework.

Some examples:

| Extension point | Key in `spring.factories` | Role |
| --- | --- | --- |
| Spring Cloud bootstrap | `org.springframework.cloud.bootstrap.BootstrapConfiguration` | Declares configuration for the bootstrap context |
| Environment post-processing | Fully qualified name of `EnvironmentPostProcessor` for the Boot line in use | Modifies `Environment` before the context is refreshed |
| Auto-configuration import filter | `org.springframework.boot.autoconfigure.AutoConfigurationImportFilter` | Filters candidates prior to deep processing |
| Auto-configuration import listener | `org.springframework.boot.autoconfigure.AutoConfigurationImportListener` | Receives details about imported candidate lists |

Interface and package names can change across major versions. When upgrading, obtain the FQCN from the target Boot line's API and check the corresponding extension point documentation.

### 5.2. Spring Cloud BootstrapConfiguration Example

When an application uses the legacy bootstrap context, Spring Cloud allows adding configuration via the key:

```properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=\
com.acme.cloud.AcmeBootstrapConfiguration
```

The listed class is a Spring configuration class:

```java
package com.acme.cloud;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AcmeBootstrapConfiguration {

    @Bean
    AcmePropertySourceLocator acmePropertySourceLocator() {
        return new AcmePropertySourceLocator();
    }
}
```

Bootstrap configuration is loaded into the bootstrap context to prepare property sources and initializers before the main application context starts. It is not a Boot auto-configuration candidate, so it must not be moved to `AutoConfiguration.imports`.

When using bootstrap configuration, place the class in a dedicated package so application component scanning does not accidentally load it into the main context. Spring Cloud documentation also recommends keeping bootstrap packages outside the scope of `@SpringBootApplication` or `@ComponentScan`.

### 5.3. Bootstrap Context Is Not the Default Choice for Every Application

Spring Cloud Config now supports the Config Data API, for example:

```yaml
spring:
  config:
    import: "optional:configserver:"
```

With this Config Data model, an application does not necessarily need to enable the legacy bootstrap context. Keep `BootstrapConfiguration` only when the application actually uses the bootstrap mechanism and has extension points relying on it.

During migration, determine whether the application uses:

- Config Data import such as `spring.config.import=configserver:`.
- Legacy bootstrap context, usually enabled via the bootstrap starter or corresponding property.
- Both during a transition phase.

Do not convert every `BootstrapConfiguration` into an auto-configuration just because you are migrating auto-configuration registration keys. The two contexts have different timings and purposes.

### 5.4. AutoConfigurationImportFilter Is Also Not an Auto-Configuration

A library may need to filter the auto-configuration list before Boot evaluates full conditions. In that case, the `AutoConfigurationImportFilter` implementation is registered in `spring.factories` under its SPI key.

This filter is not listed in `AutoConfiguration.imports`, because it is not a regular auto-configuration bean. It participates in candidate selection before configuration classes are processed.

## 6. Annotations, Conditions, and Ordering After Switching to Imports

### 6.1. @AutoConfiguration

Spring Boot 2.7 introduced `@AutoConfiguration` to mark top-level auto-configuration classes:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;

@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
public class AcmeAutoConfiguration {
    // Bean definitions
}
```

This annotation is a specialized form of `@Configuration`. Nested configurations or configurations imported by the auto-configuration class can still use `@Configuration`.

When using Boot 2.7+, `@AutoConfiguration` clearly expresses the class's role and supports direct ordering declarations. If the library still supports Boot 2.6, consider binary compatibility as discussed in the dual registration section: the 2.6 runtime lacks this annotation class.

### 6.2. Conditions Still Decide Whether Beans Are Created

The imports file only helps Boot discover candidates. It does not mean every listed class creates beans in every application.

Commonly used conditions:

- `@ConditionalOnClass`: required dependency or class is on the classpath.
- `@ConditionalOnMissingBean`: the application has not provided a replacement bean.
- `@ConditionalOnBean`: a dependent bean already exists.
- `@ConditionalOnProperty`: feature toggle property satisfies the condition.
- `@ConditionalOnResource`: required resource exists.
- `@ConditionalOnWebApplication`: matching application context type.

Example:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(AcmeClient.class)
    static class AcmeClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        AcmeClient acmeClient() {
            return new AcmeClient();
        }
    }
}
```

If the application provides its own `AcmeClient` bean, the auto-configuration should back off. Conditions let a library integrate seamlessly while allowing applications to control implementations.

For optional dependencies, isolate method signatures referencing those classes inside nested configurations annotated with `@ConditionalOnClass`. If an optional class is missing yet appears in the return type of a method on the outer configuration, the JVM may attempt to load that type before the condition is evaluated.

### 6.3. Ordering Does Not Replace Registration

Auto-configurations can declare relative ordering:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class AcmeDatabaseAutoConfiguration {
}
```

Or use `@AutoConfigureBefore`, `@AutoConfigureAfter`, and `@AutoConfigureOrder` depending on the Boot baseline and configuration style.

Ordering only controls the sequence in which bean definitions/configurations are applied. It does not change how classes are discovered. A class annotated with `@AutoConfigureAfter` that is not registered in the imports file will not automatically appear as an auto-configuration candidate.

### 6.4. Excluding Auto-Configuration

All auto-configuration exclusion mechanisms still apply to classes declared in imports:

```java
@SpringBootApplication(exclude = AcmeAutoConfiguration.class)
public class Application {
}
```

Or via property:

```yaml
spring:
  autoconfigure:
    exclude:
      - com.acme.autoconfigure.AcmeAutoConfiguration
```

If you change a package or class name in an upgrade, check places referencing the old name:

- `exclude` and `excludeName` in annotations.
- `spring.autoconfigure.exclude`.
- `before` / `after` ordering in other auto-configurations.
- Tests and operational docs mentioning the class name.

In current Boot versions, when renaming a published auto-configuration class, you can use `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements` to map the old class to the new class for ordering and exclusions:

```text
com.acme.autoconfigure.LegacyAcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
```

The imports file should list only the replacement class after migration is complete. Do not keep both the old and new classes as independent candidates if they represent the same configuration.

## 7. Test-Slice Imports Are a Separate Mechanism

Spring Boot 2.7 also changed how test slices are extended. If a library provides a custom test slice or an annotation meta-annotated with `@ImportAutoConfiguration`, additional auto-configurations can be listed in a separate file:

```text
META-INF/spring/org.springframework.boot.test.autoconfigure.jdbc.JdbcTest.imports
```

Contents:

```text
com.acme.testing.AcmeJdbcTestAutoConfiguration
```

This is not the general `AutoConfiguration.imports` file. The filename corresponds to the fully qualified name of the test slice annotation. It allows adding configuration for a specific slice without pulling test-only configuration into every production application.

If upgrading a custom test slice, read the release notes and testing documentation for the exact Boot line. Do not move all keys from `spring.factories` into one general imports file.

## 8. JAR Packaging and Resource Handling During Shading

### 8.1. Inspecting Resources in the Artifact

The source tree may look right while resources fail to package or get overwritten by plugins. After building, inspect the JAR:

```bash
jar tf acme-spring-boot-autoconfigure.jar
```

At minimum, if the library supports Boot 2.6 through 4.x, check for the required files:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

If the artifact supports only Boot 3/4 and uses no other SPIs via `spring.factories`, that file may not need to contain the old auto-configuration key. However, if it uses Spring Cloud bootstrap or other SPIs, keep the resource with those exact keys.

### 8.2. Multiple JARs on the Classpath vs. Uber-JARs

When running with multiple separate JARs on the classpath, the framework can read resources of the same name across multiple JARs.

When building an uber-JAR with Maven Shade or Gradle Shadow, the plugin must merge resources. If the plugin keeps only the first file or overwrites earlier files with later ones, entries from other dependencies can vanish.

Distinguish the merging rules:

- `AutoConfiguration.imports` is a line-based list, so contents from all JARs should be appended.
- `spring.factories` is a properties file, so it must be merged by key with implementation values concatenated; do not arbitrarily concatenate raw text or let one file overwrite another.
- `META-INF/services/*` files follow their own ServiceLoader rules; do not confuse them with the two files covered here.

### 8.3. Maven Shade

Spring Boot 2.7 release notes explicitly note the need to append the imports file when using Maven Shade without relying on an appropriate parent/plugin configuration:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
</transformer>
```

If the uber-JAR also contains `spring.factories`, use a properties-aware transformer to merge keys/values. The Spring Boot Maven Plugin provides `PropertiesMergingResourceTransformer` for this purpose:

```xml
<transformer implementation="org.springframework.boot.maven.PropertiesMergingResourceTransformer">
    <resource>META-INF/spring.factories</resource>
</transformer>
```

Actual plugin configuration also depends on the Maven Shade version and how transformer dependencies are declared. After packaging, inspect the resource contents inside the final JAR, not just the initial module JAR.

### 8.4. Gradle Shadow

With Gradle Shadow, append the imports file in the task configuration:

```groovy
tasks.withType(com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar).configureEach {
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
}
```

If the artifact also requires `spring.factories`, configure properties merging using the API of your Shadow version. Do not assume a plain text append will properly merge duplicate property keys.

## 9. Testing the Migration and Artifact

### 9.1. ApplicationContextRunner for Testing Conditions

`ApplicationContextRunner` helps test auto-configurations with specific combinations of classpath, properties, and user beans:

```java
class AcmeAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AcmeAutoConfiguration.class)
                    );

    @Test
    void createsDefaultClient() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(AcmeClient.class);
        });
    }
}
```

This test verifies the conditions and bean behavior of the specified class. It does not by itself prove that Boot discovers the imports file in the published JAR.

### 9.2. Testing Bean Back-Off and Optional Dependencies

Include tests for:

- Dependency class present: auto-configuration applies.
- Dependency class excluded via `FilteredClassLoader`: configuration backs off without context errors.
- Property disables feature: no bean created.
- Application provides its own bean: `@ConditionalOnMissingBean` prevents creating the default bean.
- Missing required property: binding/validation fails with an appropriate message.
- Web-only configuration: use `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner` as needed.

Use `ConditionEvaluationReport` when you need to explain why a condition did not match. This helps separate registration failures from condition failures.

### 9.3. Verifying Resource Discovery in the Packaged JAR

Include an artifact-level smoke test:

1. Build the auto-configuration and starter modules.
2. Package the JAR using the actual release process.
3. Consume that JAR as a dependency in a sample application outside the module.
4. Start the application on the target Boot line.
5. Confirm default beans appear and user bean overrides work.
6. Repeat across all Boot versions the library claims to support.
7. If using a shaded JAR, inspect `imports` and `spring.factories` after resource merging.

Do not merely call `AutoConfigurations.of(AcmeAutoConfiguration.class)` in internal tests and conclude that the imports file is valid. That call passes the class directly to the runner and bypasses resource discovery.

### 9.4. CI Matrix by Boot Version

For a library with dual registration, a minimal matrix might be:

| Runtime test | What to confirm |
| --- | --- |
| Boot 2.6.x | Legacy key in `spring.factories` discovers auto-configuration |
| Boot 2.7.x | Both files are read, duplicate classes apply only once |
| Boot 3.x | Imports file discovers classes; legacy `EnableAutoConfiguration` key is no longer a registration path |
| Boot 4.x | Imports file and remaining `spring.factories` SPIs both work |

Use the Spring Cloud release train compatible with each Boot line. If the library supports only specific patches/minors, the CI matrix and release documentation must state that scope explicitly.

## 10. Common Upgrade Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Auto-configuration works on Boot 2.6 but disappears on Boot 3 | Registered only via `EnableAutoConfiguration` in `spring.factories` | Add the class to `AutoConfiguration.imports` |
| Auto-configuration works on Boot 3 but disappears on Boot 2.6 | Only imports file exists; older runtime does not read it | Keep the legacy key in `spring.factories` if still supporting Boot 2.6 |
| A class is configured twice on Boot 2.7 | Lists in the two files have mismatched names or different wrapper classes | Use the exact same FQCN; check duplicates and context conditions |
| Boot 3 stops running `BootstrapConfiguration` | Deleted all of `spring.factories` when moving auto-configurations | Keep the `BootstrapConfiguration` key if still using legacy bootstrap context |
| `EnvironmentPostProcessor` stops running after migration | Removed other SPI keys along with the auto-configuration key | Re-register the SPI in `spring.factories` using the target Boot FQCN |
| Boot 2.6 fails to apply `@AutoConfiguration` class | Annotation added in Boot 2.7; class not recognized on older baseline | Use `@Configuration` for backward-compatible source or publish a separate variant |
| Module JAR works, but uber-JAR has no beans | Shade/Shadow overwrote or failed to merge imports resources | Append the imports file and inspect the packaged artifact |
| Some SPIs vanish after shading | `spring.factories` was overwritten or merged incorrectly by key | Use a properties-aware transformer |
| Auto-configuration is in the file but creates no beans | Condition did not match or user bean caused back-off | Inspect `ConditionEvaluationReport`, classpath, and properties |
| Old `exclude` stops working after package rename | Old class name remains in exclusions or ordering | Update exclusions and consider `AutoConfiguration.replacements` |
| Internal tests pass, but consumer app sees no config | Tests import classes directly without testing JAR resources | Add a smoke test with the packaged artifact |
| Test slice pulls in production configuration by mistake | Shared general imports file instead of a slice-specific file | Register under the test slice annotation name |

## 11. Recommended Migration Process

### 11.1. Inventory Before Editing

First, locate all registration resources in every module:

- `META-INF/spring.factories`.
- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- `META-INF/spring/*.imports` files for test slices or other extension points.
- `AutoConfiguration.replacements` files if packages/classes were previously renamed.

For each key in `spring.factories`, determine which framework reads it, which versions read it, and which classes are registered. Do not guess solely from class names.

### 11.2. Split Entries by Purpose

Create an inventory table:

| Current entry | Type | Target location after migration |
| --- | --- | --- |
| `EnableAutoConfiguration` | Auto-configuration candidate | `AutoConfiguration.imports`; keep legacy key if Boot 2.6 is needed |
| `BootstrapConfiguration` | Spring Cloud legacy bootstrap | Keep in `spring.factories` while still used |
| `EnvironmentPostProcessor` | Boot environment SPI | Keep in `spring.factories` |
| `AutoConfigurationImportFilter` | Boot candidate filter SPI | Keep in `spring.factories` |
| Test slice annotation key | Test-slice registration | Use `META-INF/spring/<annotation FQCN>.imports` per target Boot line |

### 11.3. Execute the Migration

1. Create the imports file in the module containing auto-configurations.
2. Write one class per line using its exact FQCN.
3. If supporting Boot 2.6, maintain the corresponding list under the legacy key in `spring.factories`.
4. If supporting Boot 2.6, avoid compiling shared auto-configuration classes against annotations/APIs introduced in Boot 2.7+.
5. Keep other SPI keys in `spring.factories`.
6. Move test slices into dedicated imports files if the library provides custom slices.
7. Check exclusions, ordering, replacements, and package scanning.
8. Configure resource merging for uber-JARs if applicable.

### 11.4. Verify Across Each Runtime

- Run CI against Boot 2.6 if support is still declared.
- Run Boot 2.7 to verify dual registration and deduplication.
- Run Boot 3.x to ensure auto-configurations do not depend on the legacy key.
- Run Boot 4.x if the library declares compatibility with that line.
- Test a real consumer application using the published JAR, not just tests inside the source module.
- Clearly document compatible Spring Cloud release train versions in the library's support matrix.

## 12. Pre-Release Checklist

1. Has every key in `spring.factories` been classified according to its actual extension point?
2. Are auto-configurations listed in the imports file?
3. If supporting Boot 2.6, is the legacy `EnableAutoConfiguration` key still retained?
4. If supporting Boot 2.6, does the source avoid referencing `@AutoConfiguration` or APIs added in Boot 2.7?
5. Do both dual-registration lists have identical FQCNs?
6. Is there a Boot 2.7 test confirming duplicates are deduplicated?
7. Are Spring Cloud `BootstrapConfiguration` keys retained if the application uses legacy bootstrap?
8. Are SPIs such as `EnvironmentPostProcessor` and `AutoConfigurationImportFilter` still registered properly?
9. Do test-slice registrations have separate annotation-named files?
10. Have conditions, bean back-off, and ordering been tested?
11. Were exclusions and class replacements updated after any package rename?
12. Are resources in the packaged JAR complete and not overwritten?
13. If using Maven Shade/Gradle Shadow, are `imports` and `spring.factories` merged properly?
14. Is there a smoke test consuming the artifact as an external dependency?
15. Does the Boot and Spring Cloud release train matrix clearly state the support scope?

## 13. Official References

- [Spring Boot 2.7 Release Notes — Auto-configuration Registration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes#changes-to-auto-configuration): introduces the imports file, preserves compatibility with `spring.factories`, and deduplicates classes listed in both places.
- [Spring Boot 3.0 Migration Guide — Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide#auto-configuration-files): removes the `EnableAutoConfiguration` key from `spring.factories` and confirms other keys are unaffected.
- [Spring Boot 4.1.2 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): imports format, conditions, ordering, replacements, `ApplicationContextRunner`, `FilteredClassLoader`, and starters.
- [Spring Boot 4.1.2 — EnvironmentPostProcessor API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/EnvironmentPostProcessor.html): confirms this SPI is still registered in `META-INF/spring.factories`.
- [Spring Boot 4.1.1 — AutoConfigurationImportFilter API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportFilter.html): confirms the filter is still registered via `spring.factories`.
- [Spring Cloud — Customizing the Bootstrap Configuration](https://docs.spring.io/spring-cloud/docs/current/reference/htmlsingle/#customizing-the-bootstrap-configuration): the `BootstrapConfiguration` key and how the bootstrap context is created.
- [Spring Boot Maven Plugin — PropertiesMergingResourceTransformer](https://docs.spring.io/spring-boot/maven-plugin/api/java/org/springframework/boot/maven/PropertiesMergingResourceTransformer.html): merges properties files such as `spring.factories` when building shaded JARs.
- [Spring Boot 2.7 Reference — Additional Auto-configuration and Slicing](https://docs.spring.io/spring-boot/docs/2.7.15/reference/html/features.html): separate imports files for test slices.

**Remember:** `AutoConfiguration.imports` is the place to declare auto-configurations for Spring Boot 2.7 and later. `spring.factories` remains the registry for many other SPIs, including Spring Cloud `BootstrapConfiguration` when using legacy bootstrap. For libraries supporting both Boot 2.6 and Boot 3/4, dual-register the exact classes, retain active SPI keys, and test resources inside the published JAR.
