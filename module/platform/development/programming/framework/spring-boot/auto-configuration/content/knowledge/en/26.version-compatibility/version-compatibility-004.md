# Avoid Assuming `spring.factories` Was Removed for Every Extension Mechanism

## 1. Key takeaway to remember first

Spring Boot changed **how auto-configuration is registered**: from the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key in `META-INF/spring.factories` to the `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` file.

That change **does not mean the `spring.factories` file was deleted from the entire Spring ecosystem**.

In Spring Boot 3.3:

- The `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key in `spring.factories` is no longer used to register auto-configuration.
- `spring.factories` is still used for several other extension points, such as `EnvironmentPostProcessor` and `ApplicationListener`.
- Spring Framework still provides `SpringFactoriesLoader` to read implementations declared in `META-INF/spring.factories`.
- Other mechanisms such as `@Import`, component scanning, `ServiceLoader`, or `AutoConfiguration.imports` have their own registration rules.

Therefore, when upgrading a library to Spring Boot 3, examine **each key and extension point** in `spring.factories`. Move the auto-configuration key to imports; keep other keys if the corresponding extension points still require them.

This lesson focuses on the scope of changes across Spring Boot 2.6 and earlier, Boot 2.7, and Boot 3.x. Code examples use Java 17+ and Spring Boot 3.3.13.

## 2. Change history by version

| Version | Auto-configuration registration | Status of EnableAutoConfiguration key in spring.factories |
|---|---|---|
| Spring Boot 2.6 and older | `META-INF/spring.factories` | Supported registration mechanism |
| Spring Boot 2.7 | `AutoConfiguration.imports` introduced | Still read for backward compatibility, but deprecated |
| Spring Boot 3.0 and later | `AutoConfiguration.imports` | Support for this key removed |
| Spring Boot 3.3 | `AutoConfiguration.imports` | Does not register auto-configuration via the legacy key; other spring.factories keys can still be used |

### 2.1. Before Spring Boot 2.7

A library published auto-configuration using the file:

`src/main/resources/META-INF/spring.factories`

Example:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.catalog.autoconfigure.CatalogAutoConfiguration,\
com.acme.catalog.autoconfigure.CatalogWebAutoConfiguration
```

Spring Boot reads the list of classes under the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key to locate auto-configuration candidates.

This is the registration mechanism described in the Spring Boot 2.5 documentation.

### 2.2. Spring Boot 2.7: transition period

Spring Boot 2.7 introduced the file:

`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Each line contains the fully qualified name of one auto-configuration class:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
com.acme.catalog.autoconfigure.CatalogWebAutoConfiguration
```

Boot 2.7 still reads legacy auto-configuration entries in `spring.factories` for backward compatibility. If the same class appears in both files, Boot 2.7 deduplicates the entry.

This is a suitable period for a library to support both older and newer Boot applications simultaneously: publish candidates in both locations, then test against the target versions.

However, the Boot 2.7 documentation marks loading auto-configuration from `spring.factories` as deprecated. This backward compatibility should not be interpreted as advice to keep using the legacy key for new projects.

### 2.3. Spring Boot 3.0: removing exactly one registration mechanism

The Boot 3 Migration Guide states clearly: support for registering auto-configuration in `spring.factories` via the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key was removed in favor of the imports file.

The crucial point lies in the next clause of the guide: **other `spring.factories` entries under different keys are unaffected by this change**.

Thus, if a library contains both entries:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.catalog.autoconfigure.CatalogAutoConfiguration

org.springframework.boot.env.EnvironmentPostProcessor=\
com.acme.catalog.CatalogEnvironmentPostProcessor
```

then when upgrading to Boot 3:

- Move `CatalogAutoConfiguration` to `AutoConfiguration.imports`.
- Keep the `EnvironmentPostProcessor` entry if the library still provides this processor.

Do not delete the entire `spring.factories` file merely because the auto-configuration key moved elsewhere.

## 3. Three mechanisms to distinguish

| Mechanism | File or registration method | Who processes it? | What is it used for? |
|---|---|---|---|
| Auto-configuration candidates | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Spring Boot auto-configuration import mechanism | Listing auto-configuration classes |
| Factory/SPI registry | `META-INF/spring.factories` | Spring Framework `SpringFactoriesLoader` or Spring Boot extension points | Finding implementations by key (interface/factory type name) |
| Other Spring/Java mechanisms | `@Import`, component scan, `ServiceLoader`, direct registration... | The corresponding mechanism | Loading configurations, components, or implementations per their own contracts |

There is no single file that registers every kind of extension.

### 3.1. AutoConfiguration.imports is a dedicated candidate list

The imports file is not a properties file. Each line is a class name:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
com.acme.catalog.autoconfigure.CatalogMetricsAutoConfiguration
```

Spring Boot finds this file inside JARs on the classpath when processing `@EnableAutoConfiguration`, usually triggered through `@SpringBootApplication`.

After finding candidates, Boot proceeds to evaluate conditions such as `@ConditionalOnClass`, `@ConditionalOnProperty`, and `@ConditionalOnMissingBean`. Being listed in imports does not mean every bean in the class is guaranteed to be created; conditions still determine whether the configuration applies.

Library authors maintain the imports list. Do not use this file to register `EnvironmentPostProcessor`, `ApplicationListener`, or a custom SPI.

### 3.2. spring.factories is a key-based registry

`spring.factories` uses the Java Properties format. Keys are typically the fully qualified name of an interface or abstract class; values are comma-separated lists of implementation names.

Example:

```properties
com.acme.catalog.CatalogPlugin=\
com.acme.catalog.plugin.FastCatalogPlugin,\
com.acme.catalog.plugin.CachedCatalogPlugin
```

This is a declaration for an SPI named `CatalogPlugin`. Some code must invoke a factory loader for that SPI type for the implementations to be loaded.

The `spring.factories` file **does not automatically activate arbitrary keys**. An extension point must have code that reads the corresponding key, typically via `SpringFactoriesLoader` or a dedicated Spring Boot loader mechanism.

### 3.3. SpringFactoriesLoader still reads spring.factories

Spring Framework provides:

`org.springframework.core.io.support.SpringFactoriesLoader`

This loader searches `META-INF/spring.factories` files on the classpath, reads entries keyed by factory type, and instantiates the declared implementations.

For example, with Spring Framework 6.1, you can use the API:

```java
SpringFactoriesLoader loader =
        SpringFactoriesLoader.forDefaultResourceLocation();

List<CatalogPlugin> plugins =
        loader.load(CatalogPlugin.class);
```

Factories files from multiple JARs can contribute implementations for the same factory type. The loader aggregates the list by key and sorts results using `AnnotationAwareOrderComparator`; duplicate implementations are deduplicated according to the loader's rules.

This is a general Spring Framework mechanism. Boot 3 removing an auto-configuration key does not make the `SpringFactoriesLoader` API disappear.

## 4. Extension points that still use spring.factories in Spring Boot 3.3

Some examples from official documentation and APIs:

| Extension point | Key in spring.factories | Role |
|---|---|---|
| `EnvironmentPostProcessor` | `org.springframework.boot.env.EnvironmentPostProcessor` | Customize `Environment` before the ApplicationContext is refreshed |
| `ApplicationListener` | `org.springframework.context.ApplicationListener` | Automatically register listeners for application events, including events occurring before the context is created |
| `FailureAnalyzer` | `org.springframework.boot.diagnostics.FailureAnalyzer` | Analyze startup failures and provide diagnostic messages/remediation actions |
| `ApplicationContextInitializer` | `org.springframework.context.ApplicationContextInitializer` | Initialize or customize the ApplicationContext before refresh |
| Library-defined SPI | SPI interface/abstract class name | Load implementations when code invokes `SpringFactoriesLoader` with that type |

The list above consists of examples, not an exhaustive list of every extension point. When working with a specific type, check the API/documentation of the exact version to confirm the required loader and key.

### 4.1. EnvironmentPostProcessor

`EnvironmentPostProcessor` allows modifying the Environment before the ApplicationContext is refreshed. The Spring Boot 3.3.13 API explicitly states that implementations must be registered in `META-INF/spring.factories` using the fully qualified interface name as the key.

Example:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.acme.catalog.CatalogEnvironmentPostProcessor
```

This entry remains valid in Boot 3.3. Do not move that entry to `AutoConfiguration.imports`, because imports is for auto-configuration candidates.

### 4.2. ApplicationListener

If you want a listener registered automatically for `SpringApplication` events, including events occurring before the context exists, Spring Boot documentation still instructs using `META-INF/spring.factories`:

```properties
org.springframework.context.ApplicationListener=\
com.acme.catalog.CatalogStartupListener
```

Bean-based listeners can handle events after the context is created. For very early events, registering via `SpringApplication.addListeners(...)` or `spring.factories` is more appropriate.

### 4.3. FailureAnalyzer

A library can provide a `FailureAnalyzer` to turn cryptic exceptions into error messages with descriptions and remediation steps:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.acme.catalog.CatalogConfigurationFailureAnalyzer
```

This is also a separate factory key. Moving auto-configuration to imports does not change the `FailureAnalyzer` registration rule in Boot 3.3.

## 5. Custom SPI example with SpringFactoriesLoader

Suppose a library lets applications extend it with catalog plugins. API:

```java
package com.acme.catalog;

public interface CatalogPlugin {

    String name();
}
```

An implementation:

```java
package com.acme.catalog.plugin;

import com.acme.catalog.CatalogPlugin;

public class FastCatalogPlugin implements CatalogPlugin {

    @Override
    public String name() {
        return "fast";
    }
}
```

Registration in `META-INF/spring.factories`:

```properties
com.acme.catalog.CatalogPlugin=\
com.acme.catalog.plugin.FastCatalogPlugin
```

Consuming code:

```java
package com.acme.catalog;

import java.util.List;

import org.springframework.core.io.support.SpringFactoriesLoader;

public class CatalogPluginRegistry {

    public List<CatalogPlugin> loadPlugins() {
        return SpringFactoriesLoader
                .forDefaultResourceLocation()
                .load(CatalogPlugin.class);
    }
}
```

When `loadPlugins()` is called, Spring Framework searches `spring.factories` on the classpath and reads the `com.acme.catalog.CatalogPlugin` key.

If you only write a key in the file without any code calling the loader or handling that SPI, plugins do not appear automatically in the application. The registry and implementation contract must be designed by the library.

In real projects, consider constructor injection, ordering, initialization error handling, and the possibility of multiple libraries contributing plugins. Avoid using factory loading if a normal bean or `@Import` solves the requirement more simply.

## 6. Complete example: a Boot 3.3 JAR using both files

This example demonstrates that both mechanisms can coexist in one library:

- `CatalogEnvironmentPostProcessor` is registered via `spring.factories`.
- `CatalogAutoConfiguration` is registered via `AutoConfiguration.imports`.

On startup, the application prints a value added by the EnvironmentPostProcessor and the state of the bean created by auto-configuration.

### 6.1. Project structure

```text
catalog-compat-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   ├── com/acme/catalog/
    │   │   ├── CatalogEnvironmentPostProcessor.java
    │   │   └── CatalogFeature.java
    │   ├── com/acme/catalog/autoconfigure/
    │   │   └── CatalogAutoConfiguration.java
    │   └── com/acme/demo/
    │       └── CatalogDemoApplication.java
    └── resources/
        ├── application.properties
        └── META-INF/
            ├── spring.factories
            └── spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 6.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>catalog-compat-demo</artifactId>
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
```

### 6.3. CatalogFeature.java

```java
package com.acme.catalog;

public record CatalogFeature(String status) {
}
```

### 6.4. CatalogEnvironmentPostProcessor.java

```java
package com.acme.catalog;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class CatalogEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        Map<String, Object> values = Map.of(
                "acme.catalog.bootstrap-marker",
                "loaded");

        environment.getPropertySources().addLast(
                new MapPropertySource("catalogBootstrapMarker", values));
    }
}
```

This class adds a property to the Environment before the context is refreshed. It is not an auto-configuration class and is not listed in `AutoConfiguration.imports`.

### 6.5. CatalogAutoConfiguration.java

```java
package com.acme.catalog.autoconfigure;

import com.acme.catalog.CatalogFeature;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    CatalogFeature catalogFeature() {
        return new CatalogFeature("enabled");
    }
}
```

Auto-configuration is enabled when `acme.catalog.enabled=true`. The `CatalogFeature` bean is the result of the auto-configuration mechanism.

### 6.6. CatalogDemoApplication.java

```java
package com.acme.demo;

import com.acme.catalog.CatalogFeature;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class CatalogDemoApplication implements CommandLineRunner {

    private final Environment environment;
    private final CatalogFeature feature;

    public CatalogDemoApplication(
            Environment environment,
            CatalogFeature feature) {
        this.environment = environment;
        this.feature = feature;
    }

    public static void main(String[] args) {
        SpringApplication.run(CatalogDemoApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println(
                "environmentPostProcessor="
                        + environment.getProperty(
                                "acme.catalog.bootstrap-marker"));

        System.out.println(
                "autoConfiguration=" + feature.status());
    }
}
```

The `com.acme.demo` package is the application's package. `CatalogAutoConfiguration` sits outside normal component scanning and is discovered via the imports file. This properly demonstrates the role of the auto-configuration candidate list.

### 6.7. spring.factories

Create the file:

`src/main/resources/META-INF/spring.factories`

Contents:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.acme.catalog.CatalogEnvironmentPostProcessor
```

This file registers `EnvironmentPostProcessor`. Do not put `CatalogAutoConfiguration` under the `EnableAutoConfiguration` key when targeting Boot 3.x.

### 6.8. AutoConfiguration.imports

Create the file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Contents:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

This file lists only auto-configuration classes. Do not add `CatalogEnvironmentPostProcessor` here.

### 6.9. application.properties

```properties
acme.catalog.enabled=true
```

### 6.10. Running the application

From the directory containing `pom.xml`, JDK 17+ and Maven are required:

```bash
mvn -q spring-boot:run
```

The two lines printed by the application:

```text
environmentPostProcessor=loaded
autoConfiguration=enabled
```

Spring Boot startup logs may also appear. The two lines above are the output of the `System.out.println` statements in `CommandLineRunner`.

The result proves:

1. Spring Boot still reads `spring.factories` to load EnvironmentPostProcessor.
2. Spring Boot reads `AutoConfiguration.imports` to find CatalogAutoConfiguration.
3. Both mechanisms work together in one JAR, each serving a different extension point.

## 7. Compatibility strategies when a library supports multiple Boot versions

A library may need to support multiple application generations. Choose registration files based on the lowest and highest versions the library commits to supporting.

| Library target | Auto-configuration registration | Other spring.factories contents |
|---|---|---|
| Boot 2.6 or older only | Use EnableAutoConfiguration key in spring.factories | Keep necessary keys |
| Boot 2.7 only | Use AutoConfiguration.imports; legacy key still read but deprecated | Keep necessary keys |
| Boot 2.7 and Boot 3.x | Same class may be listed in both imports and spring.factories to support both generations; Boot 2.7 deduplicates | Keep necessary keys |
| Boot 3.x only | Use only AutoConfiguration.imports for auto-configuration | Keep spring.factories for extension points that still use it |

### 7.1. Dual registration pattern for Boot 2.6, 2.7, and 3.x

If an artifact genuinely supports both Boot 2.6 and Boot 3.x, the legacy auto-configuration key can be retained alongside the imports file.

`META-INF/spring.factories`:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.catalog.autoconfigure.CatalogAutoConfiguration

org.springframework.boot.env.EnvironmentPostProcessor=\
com.acme.catalog.CatalogEnvironmentPostProcessor
```

`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

Result by version:

- Boot 2.6 reads the auto-configuration entry in `spring.factories`; the new imports file is not used to replace the legacy mechanism.
- Boot 2.7 reads both, still supports the legacy key for backward compatibility, and deduplicates repeated candidates.
- Boot 3.x obtains auto-configurations from imports; the `EnableAutoConfiguration` key in `spring.factories` is no longer supported. The EnvironmentPostProcessor entry is still processed.

### 7.2. Dual registration does not automatically guarantee bytecode compatibility

Two registration files only solve **class discoverability**. They do not guarantee that code is compatible in APIs, dependencies, or the Java baseline across versions.

For example, `@AutoConfiguration` was introduced in Spring Boot 2.7. If a library declares Boot 2.6 support yet its compiled code depends on an annotation available only from Boot 2.7 onward, adding both registration files will not magically make that annotation exist in Boot 2.6.

When supporting multiple versions:

- Clearly identify the lowest Spring Boot version.
- Choose APIs present in that baseline or split artifacts/versions if needed.
- Check both the Java bytecode target and the accompanying Spring Framework version.
- Run consumer integration tests on every committed version line.
- Do not check only that the JAR contains both files.

### 7.3. Do not delete other keys when migrating auto-configuration

Suppose the legacy file has three keys:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.catalog.autoconfigure.CatalogAutoConfiguration

org.springframework.boot.env.EnvironmentPostProcessor=\
com.acme.catalog.CatalogEnvironmentPostProcessor

org.springframework.context.ApplicationListener=\
com.acme.catalog.CatalogStartupListener
```

When migrating to Boot 3:

1. Move `CatalogAutoConfiguration` to imports.
2. Keep `EnvironmentPostProcessor` if still used.
3. Keep `ApplicationListener` if still used.
4. Check that each implementation still conforms to the APIs of the target Spring Boot/Spring Framework versions.

## 8. JAR packaging and handling colliding resource names

A common pitfall appears when packaging libraries or applications using the Maven Shade Plugin, Gradle Shadow Plugin, or fat JAR tools.

Multiple dependencies can contain files with the same name:

- `META-INF/spring.factories`
- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

If the packaging tool keeps only the last resource instead of merging properly, some extension implementations or auto-configuration candidates may disappear.

Distinguish how each should be merged:

- `spring.factories` is a properties file: keys and implementation lists from multiple JARs must be merged according to properties semantics.
- `AutoConfiguration.imports` is a line list: when creating a shaded JAR, lines from multiple dependencies must be appended/merged.

The Spring Boot 2.7 Release Notes include examples configuring `AppendingTransformer` for the imports file when using Maven Shade Plugin, and configuring `append(...)` for Gradle Shadow Plugin. Do not assume all packaging plugins handle these resources properly by default.

### 8.1. Checking resources in the JAR

After building:

```bash
mvn clean package
```

List the resources:

```bash
jar tf target/catalog-compat-demo-1.0.0.jar
```

Look for at minimum:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

If using Spring Boot's executable JAR, dependencies may be packaged under `BOOT-INF/lib`. When inspecting a specific dependency JAR, you can extract that nested JAR and inspect the resources inside.

### 8.2. Checking contents after merging

Do not stop at confirming the files exist. Open the contents and check:

- Does `spring.factories` contain all keys required by the library?
- Do keys have the exact fully qualified interface names?
- Do implementation names have the right packages/classes?
- Does `AutoConfiguration.imports` contain all candidates, one class per line?
- Are there any leftover class names that were repackaged or deleted?
- Do other dependency JARs still contribute their resources after shading?

With a standard library JAR that does not shade dependencies, each dependency keeps its own resources on the classpath; the loader aggregates the resources. Merging issues usually arise when combining multiple JARs into a single JAR.

## 9. Common misconceptions

| Misconception | Reality | How to handle |
|---|---|---|
| Boot 3 deleted `spring.factories` | Only the EnableAutoConfiguration key was removed for auto-configuration registration | Inspect each key in the file |
| All extension points must move to imports | Imports is for auto-configuration candidates | Identify the extension point's loader |
| EnvironmentPostProcessor must move to imports | Boot 3.3 still requires registration in spring.factories | Keep the EnvironmentPostProcessor key |
| ApplicationListener can no longer be registered via spring.factories | Spring Boot docs still support the ApplicationListener key for auto-registered listeners | Keep the key if early listeners are needed |
| Writing any custom key in spring.factories runs the class automatically | A loader must invoke the matching factory type/key | Look for code calling SpringFactoriesLoader |
| Putting auto-config in both files always double-registers beans | Boot 2.7 deduplicates duplicate candidates; Boot 3 uses imports for auto-config | Use dual registration intentionally when version support requires it |
| Listing in imports guarantees all beans are created | Auto-configuration is still subject to conditions | Check the Condition Evaluation Report |
| Deleting spring.factories is mandatory when upgrading to Boot 3 | May drop EnvironmentPostProcessor, listeners, or other SPIs | Remove only the legacy auto-config key when Boot 2.x is no longer needed |
| spring.factories is Java ServiceLoader | The two mechanisms have different formats and loaders | Use the right SpringFactoriesLoader or ServiceLoader |
| A resource file existing in source means it is in the JAR | Build/shading may drop or overwrite resources | Inspect the artifact after packaging |

## 10. Safe migration workflow

When upgrading a library from Boot 2.x to Boot 3.x:

1. Find all `META-INF/spring.factories` files in modules and dependencies you own.
2. List every key, rather than only looking at the filename.
3. For the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key, move the classes to `AutoConfiguration.imports`.
4. Keep keys like `EnvironmentPostProcessor`, `ApplicationListener`, or `FailureAnalyzer` if those extension points are still used in the target version.
5. If supporting Boot 2.7 and Boot 3, decide whether dual registration is needed.
6. If supporting Boot 2.6 and earlier alongside Boot 3, keep dual registration and check API/bytecode compatibility.
7. Check resource merging if using shade/shadow/fat JARs.
8. Build the JAR and inspect the final resource contents.
9. Run consumer applications on every supported Spring Boot version.
10. Enable `--debug` when needed to inspect auto-configuration candidates and the condition report.

Text search can be used in the source:

```bash
rg -n "EnableAutoConfiguration|EnvironmentPostProcessor|ApplicationListener|FailureAnalyzer" .
```

Then classify keys by purpose. Do not replace every Spring-related line with a single imports file.

## 11. Self-check questions

**Question 1.** Which key in `spring.factories` did Spring Boot 3 remove?

**Answer:** `org.springframework.boot.autoconfigure.EnableAutoConfiguration`, which is the key used to register auto-configuration candidates.

**Question 2.** Which file replaced that key?

**Answer:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, with each line listing the fully qualified name of one auto-configuration class.

**Question 3.** Does Spring Boot 2.7 still read the legacy auto-configuration key?

**Answer:** Yes. Boot 2.7 maintains backward compatibility support while marking the legacy mechanism deprecated; if the same class is listed in both places, duplicate candidates are deduplicated.

**Question 4.** In Boot 3.3, where is EnvironmentPostProcessor registered?

**Answer:** In `META-INF/spring.factories`, under the key `org.springframework.boot.env.EnvironmentPostProcessor`.

**Question 5.** Which file does `SpringFactoriesLoader` use?

**Answer:** `META-INF/spring.factories`; the key is the factory type name and the value is the list of implementations.

**Question 6.** If a custom SPI key is declared in `spring.factories`, does the implementation run automatically?

**Answer:** No. Code must call `SpringFactoriesLoader` for that exact factory type or have a dedicated loader handling that key.

**Question 7.** When a library supports both Boot 2.6 and Boot 3, is adding AutoConfiguration.imports enough?

**Answer:** Not yet. Boot 2.6 needs the legacy `EnableAutoConfiguration` key; both locations can be dual-registered. You must also verify source/API/bytecode compatibility, because two registration files do not make newer APIs exist in older versions.

**Question 8.** When building a shaded JAR, why must both spring.factories and imports be merged?

**Answer:** Multiple dependencies can contribute implementations/candidates. If resources are overwritten, some extension points or auto-configurations can vanish.

## 12. Takeaways

- The Boot 3 change only removed the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key in `spring.factories` for registering auto-configurations.
- Boot 2.7 introduced `AutoConfiguration.imports`, still reads the legacy key for backward compatibility, and deduplicates candidates.
- Boot 3.x uses `AutoConfiguration.imports` for auto-configuration candidates.
- `spring.factories` is still used for other extension points, such as `EnvironmentPostProcessor`, `ApplicationListener`, `FailureAnalyzer`, and library-defined SPIs.
- `SpringFactoriesLoader` is Spring Framework's general factory loading mechanism; a key only has effect when a loader processes it.
- `AutoConfiguration.imports`, `spring.factories`, `@Import`, component scanning, and Java `ServiceLoader` are distinct mechanisms.
- During migration, classify every key before deleting or moving files.
- Verify resources in the final JAR and run consumer tests on supported versions.

### Official documentation

- [Spring Boot 2.7 Release Notes — Auto-configuration Registration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes)
- [Spring Boot 3.0 Migration Guide — Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3.13 API — EnvironmentPostProcessor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html)
- [Spring Boot 3.3 — Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Framework 6.1 API — SpringFactoriesLoader](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/core/io/support/SpringFactoriesLoader.html)
