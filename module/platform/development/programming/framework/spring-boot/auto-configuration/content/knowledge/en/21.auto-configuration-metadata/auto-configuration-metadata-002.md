# spring-boot-autoconfigure-processor and spring-autoconfigure-metadata.properties

> **Goal:** Understand how Spring Boot uses an annotation processor at compile time to generate `META-INF/spring-autoconfigure-metadata.properties`, enabling early filtering of auto-configurations that cannot apply. This lesson focuses on the `spring-boot-autoconfigure-processor` artifact, Maven/Gradle configuration, generated metadata contents, how Boot uses it, and how to inspect the file in the published JAR.

Content follows Spring Boot 3.3.x, using Java 17+. This metadata serves **optimizing auto-configuration processing**. It differs from `@ConfigurationProperties` metadata used for IDE configuration key suggestions; the two types have different processors, purposes, and file names.

## 1. Why Does Spring Boot Need Metadata for Auto-Configuration?

A Spring Boot application can receive hundreds of auto-configurations from starters on the classpath. Many configurations will never apply because an optional library is missing, the application type does not match, or required conditions are not met.

If Boot had to load and analyze every auto-configuration class before knowing that class cannot be used, startup would have to perform extra work. Spring Boot provides `spring-boot-autoconfigure-processor` to pre-read certain annotations during the **compile phase**, then write information usable for early filtering into:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

When the application starts, Boot can read this metadata and filter out unsuitable auto-configurations early. The remaining classes continue through the standard configuration and condition processing pipeline.

You can picture two phases:

~~~text
BUILD / COMPILE
AutoConfiguration source
        |
        v
spring-boot-autoconfigure-processor
        |
        v
META-INF/spring-autoconfigure-metadata.properties
        |
        v
Package metadata into autoconfigure JAR

RUNTIME / APPLICATION STARTUP
AutoConfiguration.imports
        |
        v
Auto-configuration candidate set
        |
        v
Read metadata to filter out unsuitable candidates early
        |
        v
Analyze remaining candidates
        |
        v
Fully evaluate @Conditional annotations
        |
        v
Register bean definitions and create beans
~~~

This is a startup optimization mechanism. Metadata does not create beans, does not replace the imports file, and does not replace runtime condition evaluation.

## 2. Two Components That Must Be Distinguished

### 2.1. Annotation Processor

The artifact to configure is:

~~~text
org.springframework.boot:spring-boot-autoconfigure-processor
~~~

The processor runs while the Java compiler processes the source code of the module containing auto-configurations. It reads metadata from the annotations it supports, extracts appropriate values, and writes the properties file to the compile output.

This processor is typically only needed in the **autoconfigure module** of a library. If a project is split into:

~~~text
acme/
├── acme-autoconfigure/
│   ├── AutoConfiguration classes
│   └── META-INF/spring/...
└── acme-starter/
    └── dependency declarations
~~~

then configure the annotation processor in `acme-autoconfigure`, where the auto-configuration sources are actually compiled. The starter only aggregates dependencies for consuming applications; there is no need to add the processor to the starter module if that module does not contain auto-configuration classes.

### 2.2. Generated Metadata File

Exact path:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

This is a **generated** file, not a file developers need to write line by line themselves. With Maven, the output is typically located at:

~~~text
target/classes/META-INF/spring-autoconfigure-metadata.properties
~~~

With the Gradle Java plugin, the file is typically located in the classes output of the main source set:

~~~text
build/classes/java/main/META-INF/spring-autoconfigure-metadata.properties
~~~

When packaging the JAR, the resource must appear at the exact `META-INF/` path inside the JAR. Do not place this file under `META-INF/spring/`; that directory is used for other resources such as `AutoConfiguration.imports`.

## 3. What Information Does the Processor Record?

The processor only collects **a selective subset** of auto-configuration metadata. Commonly recorded information includes:

- Classpath conditions via `@ConditionalOnClass`.
- Bean conditions via `@ConditionalOnBean`.
- Single-candidate conditions via `@ConditionalOnSingleCandidate`.
- Application type via `@ConditionalOnWebApplication`.
- Configuration ordering via `@AutoConfigureBefore`, `@AutoConfigureAfter`, `@AutoConfigureOrder`.
- Corresponding ordering declared directly via the `before`, `beforeName`, `after`, `afterName` attributes of `@AutoConfiguration`.

**Do not assume every `@Conditional` annotation has an entry in this file.** For example, `@ConditionalOnMissingBean` and `@ConditionalOnProperty` are still evaluated by the standard condition mechanism when the configuration is processed; do not expect the processor to generate a corresponding metadata line for every such annotation.

| Annotation/Group | Role of processor metadata | When is it still evaluated? |
| --- | --- | --- |
| `@ConditionalOnClass` | Records class names to check to support early filtering | Condition still matters during configuration processing |
| `@ConditionalOnBean` | Can record required bean types to support candidate filtering | When Boot evaluates configuration conditions |
| `@ConditionalOnSingleCandidate` | Records type information to check | In the corresponding condition pipeline |
| `@ConditionalOnWebApplication` | Records required application type | When Boot determines the application context type |
| `@AutoConfigureBefore` / `@AutoConfigureAfter` | Records ordering relationships | When Boot sorts auto-configurations |
| `@AutoConfigureOrder` | Records priority order | When Boot sorts auto-configurations |
| `@ConditionalOnMissingBean` | Do not rely on this metadata file to replace the condition | When bean definitions have been processed up to evaluation time |
| `@ConditionalOnProperty` | Not every property condition is included in this metadata | When Boot evaluates properties from Environment |
| `@ConditionalOnResource` / `@ConditionalOnExpression` | Do not assume the processor stores all these expressions completely | When the corresponding condition runs at runtime |

Key point to remember: the metadata file is **not a complete copy of annotations on the class**. It contains information Boot can use for optimization or ordering steps before fully evaluating configurations.

## 4. Shape of the Properties File

Example of an auto-configuration:

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import com.acme.audit.AuditService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(
        afterName = "com.acme.core.autoconfigure.CoreAutoConfiguration")
@ConditionalOnClass(AuditClient.class)
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditService.class)
    public AuditService auditService() {
        return new AuditService("auto");
    }
}
~~~

Assuming the processor recognizes the class and supported metadata, the generated file may look like this illustrative example:

~~~properties
com.acme.audit.autoconfigure.AuditAutoConfiguration=
com.acme.audit.autoconfigure.AuditAutoConfiguration.ConditionalOnClass=com.acme.audit.AuditClient
com.acme.audit.autoconfigure.AuditAutoConfiguration.AutoConfigureAfter=com.acme.core.autoconfigure.CoreAutoConfiguration
~~~

This is a **structural illustrative example**, not a fixed output for all sources. The processor writes the class name as a key and adds keys according to the metadata types it supports. Multi-element values can be represented as comma-separated lists.

In the example above:

- `ConditionalOnClass` is recorded because it is a condition type supported by the processor.
- `AutoConfigureAfter` reflects the `afterName` attribute on `@AutoConfiguration`.
- `ConditionalOnProperty` is not included in the metadata example; it is still read from the annotation and evaluated when Boot processes conditions.
- `ConditionalOnMissingBean` is also not replaced by this metadata; Boot still needs to inspect actual bean definitions.

Do not manually edit or copy the illustrative properties file into source resources. Let the compiler processor generate the file based on the module's actual source.

## 5. Configuring with Maven

With Maven, use `maven-compiler-plugin` version 3.12.0 or higher and declare the processor in `annotationProcessorPaths`. The following example uses Java 17 and Spring Boot 3.3.13:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <spring-boot.version>${spring-boot.version}</spring-boot.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
        <version>${spring-boot.version}</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-autoconfigure-processor</artifactId>
                        <version>${spring-boot.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Points to note:

1. `spring-boot-autoconfigure-processor` goes in `annotationProcessorPaths`, because it is a dependency for compile-time annotation processing.
2. The processor version should match the Spring Boot version used by the module.
3. Use a sufficiently recent compiler plugin per Spring Boot 3.3 guidelines.
4. If the project already uses Lombok or other annotation processors, add the required processors to the same `annotationProcessorPaths`. When configuring a custom processor path, do not accidentally drop processors already in use.
5. Place the configuration in the module that has `@AutoConfiguration` sources, not only in the starter module that aggregates dependencies.

If the project uses the Spring Boot parent/BOM, you can inherit the managed version instead of repeating the version in multiple places; the important thing is that the processor and Boot artifacts are compatible from the same release line.

Run a clean compile:

~~~bash
mvn clean compile
~~~

After compiling, verify:

~~~text
target/classes/META-INF/spring-autoconfigure-metadata.properties
~~~

After packaging, the metadata must be inside the published JAR.

## 6. Configuring with Gradle

With the Gradle Java plugin, declare the processor in the `annotationProcessor` configuration:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.springframework.boot:spring-boot-autoconfigure:3.3.13'

    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor:3.3.13'

    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

`annotationProcessor` is the dedicated configuration for processors invoked during the compile task. Do not declare the processor as a runtime dependency expecting it to run automatically.

Run a clean compile:

~~~bash
./gradlew clean compileJava
~~~

Check the classes output:

~~~text
build/classes/java/main/META-INF/spring-autoconfigure-metadata.properties
~~~

The exact path may vary if the project customizes source sets or output directories. The most reliable way to confirm is to inspect the JAR artifact after building.

## 7. Distinguishing the Two Processor Types and Two Metadata Files

This is the easiest point to confuse when developing a starter. Spring Boot has two different processors with different goals:

| Aspect | Auto-configuration metadata | Configuration properties metadata |
| --- | --- | --- |
| Processor | `spring-boot-autoconfigure-processor` | `spring-boot-configuration-processor` |
| Generated file | `META-INF/spring-autoconfigure-metadata.properties` | `META-INF/spring-configuration-metadata.json` |
| Primary data | Supported conditions and ordering information for auto-configurations | Property names, data types, descriptions, default values, and hints |
| Purpose | Helps Boot filter early and sort auto-configurations | Supports IDE autocomplete, documentation, and configuration suggestions |
| Execution time | Java compile | Java compile |
| Related annotations | `@AutoConfiguration` and supported conditions/orders | `@ConfigurationProperties` and configuration metadata elements |

Example of a library with:

~~~java
@ConfigurationProperties(prefix = "acme.audit")
public class AuditProperties {

    /**
     * Whether audit integration is enabled.
     */
    private boolean enabled = true;

    /**
     * Timeout for the audit request.
     */
    private Duration timeout = Duration.ofSeconds(3);

    // Getters and setters
}
~~~

`spring-boot-configuration-processor` helps generate metadata so IDEs can suggest `acme.audit.enabled` and `acme.audit.timeout`. That processor **does not replace** `spring-boot-autoconfigure-processor`.

A module may need both processors if it provides both auto-configurations and exposes `@ConfigurationProperties` keys:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor:3.3.13'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor:3.3.13'
}
~~~

The two generated files serve two different needs; do not confuse their names or check only one file and conclude both metadata types have been generated.

## 8. How Is Metadata Used at Runtime?

When the application runs, `@EnableAutoConfiguration` finds the list of auto-configuration candidates via the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

After obtaining the candidate list, Boot can read `spring-autoconfigure-metadata.properties` so filters can quickly check certain conditions without having to fully analyze each class from the start.

For example, an auto-configuration requires `com.acme.audit.AuditClient` on the classpath. If that class is absent, the metadata provides the class name for the filter to exclude the candidate early. Excluded candidates do not need to go through deeper processing steps for that configuration.

The remaining candidates are still processed by Spring normally:

- Class-level conditions are evaluated against the actual environment and classpath.
- Bean conditions inspect bean definitions already processed up to that point.
- Property conditions read values from `Environment`.
- `@Bean` methods with their own conditions are evaluated when the configuration is processed.
- Only after bean definitions are registered does Spring instantiate objects according to the dependency graph.

**Metadata does not decide in place of runtime conditions.** It only helps Boot skip candidates early when the metadata allows it to determine with certainty that they do not apply. Conditions that depend on the actual state of the context must still be evaluated during startup.

If the metadata file is absent, Boot can still process auto-configurations by reading class metadata and evaluating conditions through the normal process. The main consequence is losing the early filtering optimization; it does not mean the application must fail simply because this file is missing.

## 9. The Two Resources Cannot Replace Each Other

An autoconfigure module typically has both of these resources:

~~~text
src/main/resources/
└── META-INF/
    └── spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

and the metadata file generated in the compile output:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

Roles:

- `AutoConfiguration.imports` **registers candidates** so Boot knows which classes to consider.
- `spring-autoconfigure-metadata.properties` **assists with filtering/ordering candidates** using information collected before runtime.

If only metadata exists without the imports resource, the metadata file does not automatically turn a class into a candidate. If the imports resource exists without metadata, Boot can still find and process candidates, only losing the corresponding metadata optimization.

Do not write the list of auto-configuration classes into `spring-autoconfigure-metadata.properties`; the discovery list belongs in the imports file.

## 10. Verifying Metadata Was Generated and Packaged

### 10.1. Checking After Compile

With Maven:

~~~bash
mvn clean compile
~~~

Check the file:

~~~powershell
Test-Path "target/classes/META-INF/spring-autoconfigure-metadata.properties"
Get-Content "target/classes/META-INF/spring-autoconfigure-metadata.properties"
~~~

With Gradle:

~~~bash
./gradlew clean compileJava
~~~

Check the file:

~~~powershell
Test-Path "build/classes/java/main/META-INF/spring-autoconfigure-metadata.properties"
Get-Content "build/classes/java/main/META-INF/spring-autoconfigure-metadata.properties"
~~~

If the project uses custom source sets/outputs, adjust the path according to the main source set output.

### 10.2. Checking the Published JAR

With Maven:

~~~bash
mvn clean package
~~~

List the JAR contents:

~~~powershell
jar tf target/acme-audit-autoconfigure-1.0.0.jar |
    Select-String "spring-autoconfigure-metadata.properties"
~~~

To read the contents inside the JAR:

~~~powershell
jar xf target/acme-audit-autoconfigure-1.0.0.jar META-INF/spring-autoconfigure-metadata.properties
Get-Content "META-INF/spring-autoconfigure-metadata.properties"
~~~

In the output, there must be:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

At the same time, separately verify the imports resource:

~~~powershell
jar tf target/acme-audit-autoconfigure-1.0.0.jar |
    Select-String "AutoConfiguration.imports"
~~~

These two checks confirm both independent resources have been packaged. Having metadata in the JAR does not prove all conditions are correct; test runtime conditions separately.

## 11. Complete Example for Testing Auto-Configuration

The following example simulates an audit library. It uses `@ConditionalOnClass` to apply only when the marker class is present, `@ConditionalOnProperty` to toggle integration on/off, and `@ConditionalOnMissingBean` to let the application replace the default.

### 11.1. Marker Class and Service

**`src/main/java/com/acme/audit/AuditClient.java`**

~~~java
package com.acme.audit;

public final class AuditClient {
}
~~~

**`src/main/java/com/acme/audit/AuditService.java`**

~~~java
package com.acme.audit;

public record AuditService(String source) {
}
~~~

### 11.2. Auto-Configuration

**`src/main/java/com/acme/audit/autoconfigure/AuditAutoConfiguration.java`**

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import com.acme.audit.AuditService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(
        afterName = "com.acme.core.autoconfigure.CoreAutoConfiguration")
@ConditionalOnClass(AuditClient.class)
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditService.class)
    public AuditService auditService() {
        return new AuditService("auto");
    }
}
~~~

In this class, the processor can generate metadata for `@ConditionalOnClass` and ordering relationships. `@ConditionalOnProperty` and `@ConditionalOnMissingBean` are still evaluated by runtime conditions.

### 11.3. Imports Resource

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
com.acme.audit.autoconfigure.AuditAutoConfiguration
~~~

This is the discovery resource required when the JAR is used by a consuming application via `@EnableAutoConfiguration`. Metadata properties do not replace this resource.

### 11.4. Testing with ApplicationContextRunner

**`src/test/java/com/acme/audit/autoconfigure/AuditAutoConfigurationTests.java`**

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import com.acme.audit.AuditService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(AuditAutoConfiguration.class));

    @Test
    void defaultServiceIsCreatedWhenConditionsMatch() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AuditService.class);
            assertThat(context.getBean(AuditService.class).source())
                    .isEqualTo("auto");
        });
    }

    @Test
    void disabledPropertySkipsAutoConfiguration() {
        runner.withPropertyValues("acme.audit.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(AuditService.class);
                });
    }

    @Test
    void userBeanMakesDefaultBackOff() {
        runner.withUserConfiguration(UserAuditConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context.getBean(AuditService.class).source())
                            .isEqualTo("user");
                    assertThat(context).doesNotHaveBean("auditService");
                });
    }

    @Test
    void missingOptionalClientSkipsAutoConfiguration() {
        runner.withClassLoader(new FilteredClassLoader(AuditClient.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(AuditService.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditConfiguration {

        @Bean
        AuditService customAuditService() {
            return new AuditService("user");
        }
    }
}
~~~

Test dependency:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}
~~~

Run:

~~~bash
mvn -Dtest=AuditAutoConfigurationTests test
~~~

Or:

~~~bash
./gradlew test --tests com.acme.audit.autoconfigure.AuditAutoConfigurationTests
~~~

**Expected result:** 4 tests PASS when the module is configured with Spring Boot 3.3.x, JUnit Jupiter, and AssertJ. The tests use `AutoConfigurations.of(...)` to load the class directly, so they verify condition/runtime behavior rather than proving the imports resource was discovered. Verifying compile-time metadata must still be performed via output/JAR as in section 10.

## 12. Common Errors and Troubleshooting

### Missing spring-autoconfigure-metadata.properties

Common causes:

- The processor was declared in the starter module while the auto-configuration classes are in another module.
- The processor was only declared in runtime/implementation dependencies instead of the processor path.
- Maven compiler plugin is too old or the annotation processor configuration is not applied.
- Gradle declared the wrong configuration, such as `implementation` instead of `annotationProcessor`.
- The build is using stale output; clean compile has not been run.
- A custom build plugin disabled annotation processing.
- Sources contain no annotations for which the processor can record metadata.

How to check: confirm the right module, configure the processor path, run `clean compile`, then check the main source set output.

### File Exists but Does Not Have Expected Keys

Do not assume every annotation must appear. Check:

1. Does the annotation belong to the group supported by the processor?
2. Which class/method is the annotation placed on and does the processor collect that element?
3. Is the condition value in the extracted attributes?
4. Are you looking at the right file for the module/JAR containing that source?

For example, not seeing `@ConditionalOnProperty` in the metadata file does not prove the annotation is ignored at runtime. It only shows there is no corresponding prefilter entry in this metadata.

### Application Still Runs Without the Metadata File

This is normal behavior. Metadata is used to optimize early filtering. If the file is missing, Boot can still read class metadata and fully evaluate conditions; startup may just have to do more work.

### File Exists in target/classes but Not in the JAR

Check resource packaging, which module artifact is actually published, and whether build configuration excludes `META-INF`. Do not only verify the file in the IDE; consuming applications read the resource from the JAR on the runtime classpath.

### Confusing with the Imports File

`AutoConfiguration.imports` lists candidate classes. `spring-autoconfigure-metadata.properties` stores certain condition/ordering information to support filtering and sorting. The two files have different purposes and must be verified separately.

### Confusing with Configuration Properties Metadata

`spring-configuration-metadata.json` serves IDEs and documentation for properties. It is not an auto-configuration filtering file. If you want both property autocomplete and auto-configuration prefiltering, configure both appropriate processors.

## 13. Step-by-Step Verification Practice

A short workflow to confirm a module is configured properly:

1. Create an `@AutoConfiguration` class with `@ConditionalOnClass` and an ordering attribute.
2. Put the processor in Maven `annotationProcessorPaths` or Gradle `annotationProcessor` in the autoconfigure module.
3. Run a clean compile.
4. Open `META-INF/spring-autoconfigure-metadata.properties` in the classes output.
5. Look for the class's FQCN and the condition/order keys supported by the processor.
6. Package the JAR and check that the metadata file is inside the artifact.
7. Verify `AutoConfiguration.imports` is also in the JAR.
8. Use `ApplicationContextRunner` to test real conditions when the class is present/absent, property is enabled/disabled, and user bean overrides.
9. Run an application consuming the starter to confirm the full discovery and runtime flow.

You do not need to write the metadata file manually to test. Inspect the artifact generated by the compiler, because that is the exact file consuming applications will read.

## 14. Self-Check Questions

1. At what stage does `spring-boot-autoconfigure-processor` run?  
   **Answer:** While compiling the Java sources of the module containing auto-configuration, via annotation processing.

2. What is the exact name of the generated file?  
   **Answer:** `META-INF/spring-autoconfigure-metadata.properties`.

3. Does this file replace `AutoConfiguration.imports`?  
   **Answer:** No. The imports file lists candidates; metadata assists with filtering/sorting certain candidates.

4. Does `@ConditionalOnProperty` not appearing in metadata mean runtime ignores that annotation?  
   **Answer:** No. Conditions are still evaluated during the normal runtime process.

5. Why should the processor be configured in the autoconfigure module?  
   **Answer:** Because that module contains the auto-configuration sources to process and is where generated metadata is packaged with the JAR.

6. What is the difference between `spring-boot-autoconfigure-processor` and `spring-boot-configuration-processor`?  
   **Answer:** The first processor generates condition/order metadata to optimize auto-configuration; the second processor generates property metadata for IDEs and documentation.

7. If the metadata file is missing, does the application necessarily fail to start?  
   **Answer:** No. The file is a startup optimization; Boot can still process conditions normally without this metadata.

8. Why is it necessary to inspect the JAR after building?  
   **Answer:** Because having the file in classes output does not guarantee the resource was packaged and published with the artifact.

## Official Documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): autoconfigure module section, role of metadata, Maven compiler plugin, and Gradle annotation processor.
- [Spring Boot 3.3 — AutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): ordering attributes `before`, `beforeName`, `after`, `afterName`.
- [Spring Boot — Configuration Metadata: Generating Your Own Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html): separate processor for `@ConfigurationProperties` and the `spring-configuration-metadata.json` file.
- [Spring Boot source — AutoConfigureAnnotationProcessor](https://github.com/spring-projects/spring-boot/tree/v3.3.13/spring-boot-project/spring-boot-tools/spring-boot-autoconfigure-processor): source code of the processor in the Spring Boot 3.3 line.

**Takeaway:** `spring-boot-autoconfigure-processor` generates compile-time metadata so Boot can filter out certain auto-configurations early and optimize startup. `spring-autoconfigure-metadata.properties` does not register classes, does not replace runtime conditions, and does not replace `spring-configuration-metadata.json`. Configure the processor in the right module, inspect the file after compile, and confirm the resource is inside the published JAR.
