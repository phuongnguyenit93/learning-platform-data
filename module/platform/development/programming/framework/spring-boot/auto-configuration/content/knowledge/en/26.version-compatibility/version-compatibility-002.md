# Registering via `spring.factories` in Legacy Code and Migrating to `AutoConfiguration.imports`

**Topic:** Spring Boot Auto Configuration  
**Knowledge Area:** Version Compatibility  
**Objective:** Understand how Spring Boot discovers auto-configuration in older versions, migrate registration to `AutoConfiguration.imports`, maintain compatibility between Boot 2.x and 3.x, and verify that the registration file is actually packaged and loaded in the application.

## 1. Auto-configuration needs to be registered

A `@Configuration` or `@AutoConfiguration` class inside a dependency JAR does not automatically become an auto-configuration. Spring Boot needs a list of candidate classes to include in the import process.

An application enables this mechanism via `@EnableAutoConfiguration`, usually included in `@SpringBootApplication`:

```java
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

When processing `@EnableAutoConfiguration`, Spring Boot locates the classes published by libraries, then evaluates conditions such as `@ConditionalOnClass`, `@ConditionalOnProperty`, and `@ConditionalOnMissingBean`.

Before Spring Boot 2.7, the standard registration method used the `META-INF/spring.factories` file with the key `org.springframework.boot.autoconfigure.EnableAutoConfiguration`.

Starting from Boot 2.7, the new registration mechanism uses:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Boot 2.7 supports both sources to provide a transition period. Boot 3 removed auto-configuration registration via the legacy key in `spring.factories`. This change affects the **class discovery** process; bean logic and conditions inside the auto-configuration still apply as before.

## 2. Legacy registration using `spring.factories`

Suppose a library has the class:

```java
package com.acme.lib.autoconfigure;

import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.acme.client.AcmeClient")
public class AcmeClientAutoConfiguration {

    @Bean
    AcmeService acmeService() {
        return new AcmeService();
    }
}
```

Before Boot 2.7, create the file:

```text
src/main/resources/META-INF/spring.factories
```

Contents:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration
```

When there are multiple classes, the value is a comma-separated list:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration,\
com.acme.lib.autoconfigure.AcmeWebAutoConfiguration,\
com.acme.lib.autoconfigure.AcmeMetricsAutoConfiguration
```

This is a Java `Properties` file:

- The key is the fully qualified name of `EnableAutoConfiguration`.
- The value is the fully qualified names of the auto-configuration classes.
- Commas separate multiple classes.
- A trailing `\` at the end of a line continues the same property onto the next line.

A `spring.factories` file can contain multiple keys to register other Spring Boot extension points, such as `ApplicationListener`, `ApplicationContextInitializer`, `EnvironmentPostProcessor`, or `FailureAnalyzer`. During migration, handle the `EnableAutoConfiguration` key specifically; do not delete the entire file if other keys are still in use.

## 3. The new `AutoConfiguration.imports` format

Create the file at the exact path:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Write one fully qualified class name per line:

```text
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration
com.acme.lib.autoconfigure.AcmeWebAutoConfiguration
com.acme.lib.autoconfigure.AcmeMetricsAutoConfiguration
```

Unlike `spring.factories`:

- There is no `EnableAutoConfiguration=` key.
- Commas are not used to separate classes.
- Each class sits on its own line.
- Comments can be written using `#`.
- Class names must include the full package.

Example:

```text
# Core integration
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration

# Optional web integration
com.acme.lib.autoconfigure.AcmeWebAutoConfiguration
```

In the rare case where a class is nested inside another class, use `$` to separate the class names:

```text
com.acme.lib.autoconfigure.AcmeConfiguration$NestedAutoConfiguration
```

Prefer top-level auto-configuration classes with clear names that are easy to inspect.

Spring Boot searches for this file inside JARs on the classpath. Therefore, the file must be packaged inside the artifact that consumers actually receive. Having the `.class` file in the JAR without the registration resource is not enough for Spring Boot to discover that class automatically.

## 4. Compatibility matrix by version

| Version | `spring.factories` with `EnableAutoConfiguration` key | `AutoConfiguration.imports` | Behavior |
| --- | --- | --- | --- |
| Boot 2.6 and older | Supported | Not supported yet | Must use the legacy mechanism |
| Boot 2.7 | Supported for backward compatibility | Supported | Classes listed in both sources are deduplicated |
| Boot 3.x | Key no longer used to register auto-configuration | Supported | Imports file is required |

### 4.1. Boot 2.7 as a transition period

Boot 2.7 introduces the imports file while still reading legacy entries in `spring.factories`. A class can be listed in both files; Boot 2.7 deduplicates repeated entries.

This allows a library to publish both files to support:

- Older Boot versions that only know `spring.factories`.
- Boot 2.7, which understands both sources.
- Boot 3, which uses the new imports file.

If a library only supports Boot 2.7 and later, it can use imports as the primary registration source. If it still supports Boot 2.6 or earlier, it needs to keep the legacy entry as long as those versions remain supported.

### 4.2. Boot 3 removes the legacy key, not all of `spring.factories`

The following entry no longer registers auto-configuration on Boot 3:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration
```

If a library only keeps this entry, the class can still compile and be packaged, yet Boot 3 will not load it via auto-configuration discovery. The typical symptom is that default beans disappear even though the dependency is on the classpath.

Do not interpret this change as the removal of all `spring.factories` functionality. Boot 3 only removes auto-configuration registration via the `EnableAutoConfiguration` key; other keys can still be used by Spring Boot for their respective extension points.

## 5. Choosing a migration approach by lowest supported version

### Case A: Supporting only Boot 2.7+ and Boot 3.x

Use `@AutoConfiguration` and the imports file:

```java
package com.acme.lib.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeService acmeService() {
        return new AcmeService();
    }
}
```

If versions prior to 2.7 are no longer supported, there is no need to keep the legacy `EnableAutoConfiguration` entry just to register this class.

### Case B: Supporting both Boot 2.6 and Boot 2.7/3.x

Keep both files:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Example `spring.factories`:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration
```

Example imports:

```text
com.acme.lib.autoconfigure.AcmeClientAutoConfiguration
```

Note that `@AutoConfiguration` only exists from Boot 2.7 onward. If Boot 2.6 is the lowest runtime, a class annotated with `@AutoConfiguration` could reference an annotation missing from Boot 2.6, leading to class-loading errors such as `NoClassDefFoundError`.

A common annotation choice is to keep `@Configuration(proxyBeanMethods = false)` and ordering annotations available in older versions such as `@AutoConfigureBefore`/`@AutoConfigureAfter`. Boot 3 can still load that class from the imports file:

```java
package com.acme.lib.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfigureAfter;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@AutoConfigureAfter(name = "com.acme.other.autoconfigure.OtherAutoConfiguration")
@ConditionalOnClass(name = "com.acme.client.AcmeClient")
public class AcmeClientAutoConfiguration {

    @Bean
    AcmeService acmeService() {
        return new AcmeService();
    }
}
```

The two registration files only solve discovery. They do not automatically guarantee that all bytecode, the Java baseline, Spring Framework APIs, and the dependency graph are compatible across every version. If differences between Boot 2 and Boot 3 are too large, consider separate artifacts/variants and test each baseline.

### 5.1. Quick selection rules

- Boot 3.x only: use imports.
- Boot 2.7 and Boot 3.x: imports is the new mechanism; both files can be kept if older versions must also be supported.
- Boot 2.6 and lower: `spring.factories` is required.
- Boot 2.6 and lower alongside Boot 3.x: both files are required and annotation/dependency compatibility must be verified.
- Do not delete other `spring.factories` keys simply because auto-configuration was migrated.

## 6. `@AutoConfiguration` and `@Configuration`

Boot 2.7 introduces:

```java
org.springframework.boot.autoconfigure.AutoConfiguration
```

`@AutoConfiguration` is a specialized annotation for auto-configuration classes. It is meta-annotated with `@Configuration(proxyBeanMethods = false)`, so auto-configuration does not enable method proxying by default.

Use it on the top-level class:

```java
@AutoConfiguration
public class AcmeClientAutoConfiguration {
}
```

Nested configurations still use:

```java
@Configuration(proxyBeanMethods = false)
static class OptionalClientConfiguration {
}
```

Keep in mind:

- `@AutoConfiguration` does not self-register the class; the imports file must still list that class.
- This annotation does not replace conditions like `@ConditionalOnClass` or `@ConditionalOnMissingBean`.
- Use `@AutoConfiguration` when the baseline is Boot 2.7 or higher.
- If supporting Boot prior to 2.7, review the annotation and dependency baseline; use `@Configuration` if a single shared compatible class is needed.

## 7. Migrating ordering annotations

Legacy code typically uses:

```java
@Configuration(proxyBeanMethods = false)
@AutoConfigureBefore(DataSourceAutoConfiguration.class)
@AutoConfigureAfter(HibernateJpaAutoConfiguration.class)
public class AcmePersistenceAutoConfiguration {
}
```

With `@AutoConfiguration`, ordering can be expressed directly:

```java
@AutoConfiguration(
        before = DataSourceAutoConfiguration.class,
        after = HibernateJpaAutoConfiguration.class
)
public class AcmePersistenceAutoConfiguration {
}
```

Class names can be used when you do not want a direct dependency on another class:

```java
@AutoConfiguration(
        beforeName = "com.acme.other.autoconfigure.OtherAutoConfiguration",
        afterName = "com.acme.cache.autoconfigure.CacheAutoConfiguration"
)
public class AcmeClientAutoConfiguration {
}
```

The `@AutoConfigureBefore` and `@AutoConfigureAfter` annotations can still be used. `@AutoConfigureOrder` is useful when general ordering is needed without two auto-configurations directly referencing each other.

Ordering governs the order in which auto-configurations are applied and bean definitions are registered. It does not determine the final object instantiation order; instantiation still follows the dependency graph and `@DependsOn`.

Do not rely on line order in the imports file as an ordering contract. Express before/after relationships using the dedicated annotations.

## 8. Which module must contain the imports file?

For a library with a dedicated starter, a typical layout is:

```text
acme/
├── acme-core/
├── acme-spring-boot-autoconfigure/
│   ├── src/main/java/com/acme/lib/autoconfigure/
│   │   ├── AcmeClientAutoConfiguration.java
│   │   └── AcmeWebAutoConfiguration.java
│   └── src/main/resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
├── acme-spring-boot-starter/
└── consumer-app/
```

The imports file must reside in the JAR containing the auto-configuration classes. If the starter is only a dependency aggregator artifact, the resource normally resides in the `autoconfigure` module pulled in by the starter, and does not need to be copied into the starter JAR.

An application can receive auto-configurations from multiple JARs. Spring Boot finds the imports files on the classpath and aggregates the candidates.

Do not place auto-configurations in a package scanned by the application's component scan. Auto-configurations should be discovered via the registration file; supporting configurations should be loaded with `@Import`. Avoid using `@ComponentScan` inside auto-configuration to scan arbitrary components.

## 9. Merging resources when building shaded/uber JARs

When using a regular library JAR, the imports resource is copied from `src/main/resources` into the JAR. However, when creating a shaded/uber JAR, multiple dependencies can contain the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

If the packaging tool keeps only the last file instead of merging contents, some auto-configurations will disappear from the final artifact.

With the Maven Shade Plugin, `AppendingTransformer` can be used:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
</transformer>
```

With the Gradle Shadow Plugin:

```groovy
tasks.withType(com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar).configureEach {
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
}
```

This configuration is only needed when the build actually merges dependency resources. If `spring.factories` is still kept, ensure the plugin merges properties files properly so keys/values from different dependencies do not overwrite each other. After shading, inspect the contents of the final file rather than checking only individual module JARs.

## 10. Working example: Boot 3.3.13 registering via imports

The example uses Java 17, Maven, and Spring Boot 3.3.13. An integration test starts a minimal application with `@EnableAutoConfiguration`, then verifies the bean is found via the imports file.

### 10.1. Structure

```text
acme-autoconfigure-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── GreetingService.java
    │   │   └── autoconfigure/GreetingAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/
        └── AutoConfigurationImportTest.java
```

### 10.2. `pom.xml`

```xml
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

    <groupId>demo</groupId>
    <artifactId>acme-autoconfigure-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 10.3. `GreetingService.java`

```java
package demo;

public record GreetingService(String message) {
}
```

### 10.4. `GreetingAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.GreetingService;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new GreetingService("hello from auto-configuration");
    }
}
```

`@ConditionalOnMissingBean` allows the application to supply its own `GreetingService`, causing the default bean to back off.

### 10.5. `AutoConfiguration.imports` file

Contents:

```text
demo.autoconfigure.GreetingAutoConfiguration
```

Exact path:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 10.6. Integration test

File `AutoConfigurationImportTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = AutoConfigurationImportTest.TestApplication.class)
class AutoConfigurationImportTest {

    @Autowired
    ApplicationContext context;

    @Test
    void discoversAutoConfigurationFromImportsFile() {
        assertThat(context.getBeansOfType(GreetingService.class))
                .hasSize(1);

        assertThat(context.getBean(GreetingService.class).message())
                .isEqualTo("hello from auto-configuration");
    }

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class TestApplication {
    }
}
```

The test uses real `@EnableAutoConfiguration`, so Spring Boot must locate the class from the imports file on the classpath. The test does not call the auto-configuration constructor directly and does not use `@Import` to bypass discovery.

Run:

```bash
mvn test
```

Expected output:

```text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
```

If the test cannot find `GreetingService`, check the resource path, package/class name, and resource output. If the bean appears twice, check whether the class is simultaneously registered by component scan or another import mechanism.

## 11. Verifying the resource in the final JAR

Build the artifact:

```bash
mvn clean package
```

List the JAR contents:

```bash
jar tf target/acme-autoconfigure-demo-1.0.0.jar
```

Find the resource on Linux/macOS:

```bash
jar tf target/acme-autoconfigure-demo-1.0.0.jar |
    grep -F 'META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports'
```

On Windows PowerShell:

```powershell
jar tf target/acme-autoconfigure-demo-1.0.0.jar |
    Select-String 'META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports'
```

Read the resource contents without extracting the entire JAR:

```bash
unzip -p target/acme-autoconfigure-demo-1.0.0.jar \
    META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

The output must contain:

```text
demo.autoconfigure.GreetingAutoConfiguration
```

If the JAR lacks the resource, check:

- Whether the file is in `src/main/resources`.
- Whether the filename matches every character and letter case.
- Whether Maven resource filtering/custom packaging excludes `META-INF/spring/**`.
- Whether you are inspecting the right artifact/version.
- If using Shade/Shadow, whether the append/merge configuration took effect.

The presence of the `.class` file in the JAR does not prove auto-configuration is registered. The class and registration metadata are two independent pieces.

## 12. Testing compatibility across each Boot line

For libraries supporting multiple versions, create a separate consumer test for each baseline:

| Consumer | Required registration | Result to verify |
| --- | --- | --- |
| Boot 2.6.x | `spring.factories` | Auto-configuration is discovered via the legacy key |
| Boot 2.7.x | Both files if supporting older versions | Class is loaded exactly once |
| Boot 3.x | `AutoConfiguration.imports` | Auto-configuration is loaded even though the legacy key no longer takes effect |

Each consumer test must use the exact dependency versions of that Boot line. Do not merely swap a version property in one test if the dependency graph, Java baseline, or Spring Framework APIs already differ.

You should verify:

1. The consumer starts via `@SpringBootApplication` or `@EnableAutoConfiguration`.
2. The default bean appears when conditions match.
3. An application-supplied bean causes `@ConditionalOnMissingBean` to back off.
4. Absent optional classes do not cause class loading failures.
5. The published JAR contains the right registration file.
6. Shaded JARs preserve all imports entries from every dependency.
7. Boot 2.7 does not double-register a class when both files list it.

### 12.1. Logic tests vs. discovery tests

`ApplicationContextRunner.withConfiguration(AutoConfigurations.of(MyAutoConfiguration.class))` is useful for testing conditions, beans, and properties. However, the runner accepts the class directly, so it does not prove the imports file was placed correctly or packaged.

To test discovery, start a context with `@EnableAutoConfiguration` without manually importing the class, as in the integration test above. Then inspect the final JAR to confirm publication.

## 13. Common mistakes

**Mistake 1 — Renaming the file while keeping the legacy format.**  
`AutoConfiguration.imports` is not a Properties file. No `EnableAutoConfiguration=` key, no commas; one class per line.

**Mistake 2 — Editing only `spring.factories` and forgetting imports.**  
Boot 3 no longer loads auto-configurations via the legacy key. The class is in the JAR, yet it is not discovered.

**Mistake 3 — Deleting all of `spring.factories`.**  
Other keys may still be used by Boot. Remove the legacy auto-configuration entry only when compatibility with versions prior to 2.7 is no longer needed.

**Mistake 4 — Using `@AutoConfiguration` while still supporting Boot prior to 2.7.**  
This annotation does not exist in Boot 2.6. When an older runtime tries to read the class, `NoClassDefFoundError` can occur. Use a common annotation or publish version-appropriate artifacts.

**Mistake 5 — Placing imports in a module consumers do not receive.**  
The resource must be in a JAR on the classpath. A module that builds successfully but is not pulled in by the starter will not contribute auto-configurations.

**Mistake 6 — Putting auto-configuration inside component scan.**  
Auto-configuration should be discovered via the registration file. Keep a dedicated package and use `@Import` for supporting configurations.

**Mistake 7 — Forgetting to merge resources when shading.**  
Multiple dependencies can contain an imports file. If the plugin keeps only one copy, other entries are lost from the uber JAR.

**Mistake 8 — Relying on line order in imports.**  
Use `@AutoConfiguration(before/after)` or dedicated ordering annotations to express relationships.

**Mistake 9 — Using a test that imports the class directly to conclude discovery works.**  
That test bypasses registration files. An integration test via `@EnableAutoConfiguration` is needed.

**Mistake 10 — Checking only the submodule JAR.**  
The final artifact after Shade/Shadow can lose the resource. Inspect the exact JAR that consumers download.

## 14. Migration checklist

1. Find all `META-INF/spring.factories` files across modules.
2. Locate the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` entry.
3. List all classes in the value, accounting for commas and line-continuation `\` characters.
4. Create `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
5. Convert each class name onto its own line.
6. If the baseline is Boot 2.7+, consider using `@AutoConfiguration` on top-level classes.
7. If still supporting prior to Boot 2.7, keep the legacy entry and verify annotation/dependency baselines.
8. Preserve other `spring.factories` keys.
9. Configure resource merging if using Maven Shade or Gradle Shadow.
10. Write an integration test via `@EnableAutoConfiguration`.
11. Build the JAR, run `jar tf`, and inspect the imports contents.
12. Run consumer tests on the lowest and highest Boot versions declared as supported.

## 15. Self-check questions

**Question 1.** Before Boot 2.7, where was auto-configuration registered?  
**Answer:** `META-INF/spring.factories`, under the key `org.springframework.boot.autoconfigure.EnableAutoConfiguration`.

**Question 2.** Where does the new registration file live?  
**Answer:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

**Question 3.** What is the format of the imports file?  
**Answer:** One fully qualified class name per line; comments can begin with `#`.

**Question 4.** How does Boot 2.7 handle a class listed in both files?  
**Answer:** It supports both sources and deduplicates repeated entries.

**Question 5.** Why does the legacy `EnableAutoConfiguration` entry no longer work in Boot 3?  
**Answer:** Boot 3 removed auto-configuration registration via that key; the imports file must be used.

**Question 6.** Does Boot 3 stop reading all keys in `spring.factories`?  
**Answer:** No. Only auto-configuration registration via the `EnableAutoConfiguration` key was removed; other keys are unaffected by this change.

**Question 7.** Which version introduced `@AutoConfiguration`?  
**Answer:** Spring Boot 2.7.0. If supporting older Boot versions, check the use of this annotation in bytecode.

**Question 8.** Why does `AutoConfigurations.of(MyAutoConfiguration.class)` not prove the imports file is correct?  
**Answer:** The test passes the class directly to the runner, bypassing discovery via `@EnableAutoConfiguration` and the imports resource.

**Question 9.** Why must resources be appended when using Shadow or Shade?  
**Answer:** Multiple dependencies can provide the same imports file; without merging, the final artifact can lose some class registrations.

**Question 10.** Does `@AutoConfiguration(before = X.class)` guarantee the current bean is instantiated before X's beans?  
**Answer:** No. It controls auto-configuration application and bean definition registration order; bean instantiation still follows the dependency graph and lifecycle.

## 16. Key principles to remember

- Before Boot 2.7: register via `spring.factories` with the `EnableAutoConfiguration` key.
- Boot 2.7: supports both files and deduplicates duplicate entries.
- Boot 3: uses `AutoConfiguration.imports`; the legacy auto-configuration key in `spring.factories` no longer has effect.
- Other `spring.factories` keys can still be used.
- The imports file contains one fully qualified class name per line.
- `@AutoConfiguration` exists from Boot 2.7 onward; nested configurations continue using `@Configuration`.
- Keep both registration files if supporting Boot prior to 2.7, while verifying annotations and dependency baselines.
- Use ordering annotations instead of relying on line order in the resource.
- Merge resources when creating shaded/uber JARs and verify the final artifact.
- Use integration tests via `@EnableAutoConfiguration` to confirm real discovery.

### Official references

- [Spring Boot 2.7 Release Notes — Auto-configuration Registration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes)
- [Spring Boot 3.0 Migration Guide — Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — `@AutoConfiguration`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 2.7 Reference — Locating Auto-configuration Candidates](https://docs.spring.io/spring-boot/docs/2.7.x/reference/htmlsingle/)
