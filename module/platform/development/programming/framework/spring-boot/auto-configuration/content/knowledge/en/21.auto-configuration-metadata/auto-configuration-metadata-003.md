# Metadata Supporting Early Candidate Filtering and Optimizing Configuration Processing Cost

## 1. What Problem Does Metadata Solve?

A Spring Boot application can pull in dozens or hundreds of auto-configurations from Spring Boot, Spring projects, and third-party starters. Spring needs to read the candidate list, determine which configurations match the current classpath and environment, and only then parse the selected configurations to register bean definitions.

If every candidate had to be read and fully analyzed before knowing whether it fits, startup would waste extra work. For example, an application does not use a search library, yet the search integration auto-configuration is still in a starter's candidate list. If it can be determined early that the search library class does not exist, Spring Boot can filter out that configuration before reading the auto-configuration class's bytecode.

Spring Boot supports this mechanism using **auto-configuration metadata**:

- An annotation processor collects certain static conditions from the auto-configuration source code during compilation.
- The processor writes metadata to `META-INF/spring-autoconfigure-metadata.properties` inside the artifact.
- At startup, `AutoConfigurationImportFilter` implementations can use the metadata to filter out non-matching candidates before the configuration's bytecode is read.
- The remaining candidates continue through the standard configuration parsing and condition evaluation process.

The goal is to reduce the amount of configuration that must be processed during startup. Metadata is a **path optimization**, not a replacement for `@Conditional` and not a place to register beans.

This lesson uses **Spring Boot 3.3.13 and Java 17+**, focusing on metadata generation, how Spring uses metadata, how to inspect the JAR, and how to test a conditional auto-configuration.

## 2. Distinguishing Three Easily Confused Metadata Types

Spring Boot has several files with the word “metadata”, but they have different purposes:

| File | Role | Who uses it? |
|---|---|---|
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Lists the names of auto-configuration candidates in the JAR | `AutoConfigurationImportSelector` finds candidates |
| `META-INF/spring-autoconfigure-metadata.properties` | Stores certain condition/order metadata to filter candidates early | Auto-configuration import filters and sorter |
| `META-INF/spring-configuration-metadata.json` | Describes `@ConfigurationProperties` properties, data types, default values, descriptions, and hints | IDEs, tooling, and developers writing application config |

The three files cannot replace one another:

- Missing `AutoConfiguration.imports`: Spring Boot has no list to auto-discover auto-configurations via the imports mechanism.
- Missing `spring-autoconfigure-metadata.properties`: configurations can still be evaluated by standard conditions, but the opportunity for early filtering based on generated metadata is lost.
- Missing `spring-configuration-metadata.json`: the application still binds properties if the code is correct, but the IDE may lack completion and documentation hints.

**Important point:** `spring-boot-autoconfigure-processor` generates auto-configuration metadata; `spring-boot-configuration-processor` generates configuration property metadata. Their names look similar, but their artifacts and responsibilities are different.

## 3. When Does the Candidate Filtering Process Take Place?

Conceptually, Spring Boot's process can be represented as follows:

~~~text
@EnableAutoConfiguration
        |
        v
Read AutoConfiguration.imports files on the runtime classpath
        |
        v
Collect candidate class names and apply exclusions
        |
        v
Read spring-autoconfigure-metadata.properties
        |
        v
AutoConfigurationImportFilter checks metadata
        |
        +---- Static condition cannot match
        |          |
        |          v
        |     Filter out candidate early
        |
        +---- Candidate still eligible
                   |
                   v
        Sort order and parse configuration
                   |
                   v
        Evaluate remaining conditions
                   |
                   v
        Register bean definitions
                   |
                   v
        Instantiate beans per dependencies and lifecycle
~~~

`AutoConfigurationImportFilter` is designed to quickly filter out auto-configurations before their bytecode is read. The `match(...)` method receives a list of class names and `AutoConfigurationMetadata`, and returns a boolean array corresponding to the candidates; `false` elements will not be imported.

You can think of metadata as an **early-checkable condition summary**. Spring does not need to analyze an entire class just to know a static condition such as a required class missing from the classpath.

The actual process has more internal steps than the diagram. Metadata does not decide every condition by itself and does not create beans directly. After filtering, the remaining configurations still go through the standard configuration processing pipeline.

## 4. Metadata Is Generated at Compile Time

### 4.1. Spring Boot's Annotation Processor

The artifact needed in the module containing auto-configurations is:

`org.springframework.boot:spring-boot-autoconfigure-processor`

This is a Java annotation processor. When the compiler processes auto-configuration classes, the processor collects the annotations/attributes it supports and generates the file:

`META-INF/spring-autoconfigure-metadata.properties`

The processor should be declared in the **autoconfigure module**, where `@AutoConfiguration` classes are compiled. There is no need to put the processor on the runtime classpath of consuming applications.

The processor can only collect metadata from annotations and information it understands. Do not assume every `@Conditional`, every property condition, or every `@Bean` method can be completely decided at the early-filtering step.

### 4.2. Maven Configuration

With Spring Boot 3.3, the official documentation recommends using Maven Compiler Plugin version 3.12.0 or higher and declaring the processor in `annotationProcessorPaths`.

Example `build` section in `pom.xml` of an auto-configuration module, assuming the project uses Spring Boot 3.3.13 and Java 17:

~~~xml
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
                        <version>3.3.13</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

The module also needs a compile-time dependency for the annotations/APIs it uses, typically `spring-boot-autoconfigure`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-autoconfigure</artifactId>
</dependency>
~~~

When using the Spring Boot parent/BOM, runtime dependency versions are usually centrally managed. In `annotationProcessorPaths`, declare the processor version matching the project's Boot version to avoid generating metadata with a different version.

If the project uses Lombok or other annotation processors, add them to the same `annotationProcessorPaths` list and check processor ordering per each tool's guidelines. Do not accidentally drop existing processors when changing the compiler configuration.

### 4.3. Gradle Configuration

With Gradle, place the processor in the `annotationProcessor` configuration:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")

    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

The example assumes the Spring Boot BOM or dependency management plugin manages versions. If the project does not use a BOM, declare version 3.3.13 consistently for Spring Boot artifacts.

Do not declare the processor in `implementation` just so the compiler finds it. `annotationProcessor` reflects the proper compile-time role and avoids pulling the processor into unnecessary runtime dependencies.

### 4.4. The Processor Is Not a Consumer Runtime Dependency

Consumers need the runtime classes provided by the starter, such as auto-configuration APIs, service APIs, and the actual integration library. Consumers do not need to run the starter's annotation processor on every startup.

The flow is:

1. The auto-configuration module compiles and generates metadata.
2. The metadata is packaged into the module's JAR.
3. The starter/consumer places that JAR on the runtime classpath.
4. Spring Boot reads the metadata when processing auto-configuration candidates.

If the processor does not run, `@Conditional` annotations can still be evaluated through the standard mechanism. The issue is that the application lacks the generated metadata to support early-filtering optimization.

## 5. Example Auto-Configuration with an Optional Dependency

Suppose the Acme Search library only works when an external SDK has the class:

`com.vendor.search.SearchClient`

The starter wants to provide a default `SearchFacade` if the SDK is present and the application has not provided its own facade.

### 5.1. Starter API

File `src/main/java/com/acme/search/SearchFacade.java`:

~~~java
package com.acme.search;

public interface SearchFacade {

    String provider();
}
~~~

### 5.2. Auto-Configuration

File `src/main/java/com/acme/search/autoconfigure/SearchAutoConfiguration.java`:

~~~java
package com.acme.search.autoconfigure;

import com.acme.search.SearchFacade;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.search.SearchClient")
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchFacade.class)
    DefaultSearchFacade searchFacade() {
        return new DefaultSearchFacade();
    }

    static class DefaultSearchFacade implements SearchFacade {

        @Override
        public String provider() {
            return "starter-default";
        }
    }
}
~~~

The class-level `@ConditionalOnClass` condition describes that the auto-configuration only applies when the SDK is on the classpath. Using `name` lets the configuration reference the optional class by name, without forcing the auto-configuration's method signatures to directly use a type that may be absent.

`@ConditionalOnMissingBean` on the bean method expresses the back-off contract: if the application already provides a `SearchFacade`, the default bean is not registered. This condition still needs to be evaluated against the state of bean definitions in the context; it should not be treated as a static condition that can always be resolved solely from compile-time metadata.

### 5.3. Registering the Candidate

Create the file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Contents:

~~~text
com.acme.search.autoconfigure.SearchAutoConfiguration
~~~

This file places the auto-configuration name into the candidate list. Processor metadata does not replace the imports file.

## 6. Inspecting Metadata in the Built Artifact

After building the auto-configuration module:

~~~bash
mvn clean package
~~~

Check that the JAR has the necessary files:

~~~bash
jar tf target/search-autoconfigure-1.0.0.jar
~~~

In the list, look for:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
~~~

The first file must contain the `SearchAutoConfiguration` class name. The second file is generated by the processor from the condition/order metadata it recognizes. Exact contents depend on the annotations in the module and the processor version.

In PowerShell you can filter the list:

~~~powershell
jar tf target/search-autoconfigure-1.0.0.jar |
    Select-String "AutoConfiguration.imports|spring-autoconfigure-metadata.properties"
~~~

If you want to read the packaged metadata contents, extract the exact entry from the JAR:

~~~powershell
jar xf target/search-autoconfigure-1.0.0.jar META-INF/spring-autoconfigure-metadata.properties
Get-Content META-INF/spring-autoconfigure-metadata.properties
~~~

This is a generated output file. Do not edit this file manually to control runtime behavior. Edit the annotations/processor configuration in source and rebuild the artifact instead.

### 6.1. If the Metadata File Does Not Appear

Check in order:

1. Is `spring-boot-autoconfigure-processor` in `annotationProcessorPaths` or Gradle `annotationProcessor`?
2. Does the processor have the same version as the Spring Boot version in use?
3. Did the compiler accidentally run with `-proc:none` or a configuration disabling annotation processing?
4. Does the auto-configuration class have annotations/conditions supported by the processor?
5. Are you inspecting the JAR from the right module and the right build?
6. Was the resource packaged incorrectly or excluded by a build plugin?

A project might not generate a useful metadata file if there are no conditions recognized by the processor. The absence of the file does not by itself prove that auto-configuration imports are broken.

## 7. Testing Behavior When the Optional Class Is Present or Absent

Metadata is an internal optimization. Application tests still need to confirm proper behavior when the class is present, when the class is absent, and when the user overrides the default bean.

### 7.1. Creating a Marker Class in Tests

In the test project, create a mock SDK class:

File `src/test/java/com/vendor/search/SearchClient.java`:

~~~java
package com.vendor.search;

public final class SearchClient {
}
~~~

This class is only a test marker to simulate the SDK being on the test classpath. In a real application, the class will come from an external SDK dependency.

### 7.2. Integration Test Going Through Auto-Configuration Imports

File `src/test/java/com/acme/search/autoconfigure/SearchAutoConfigurationTests.java`:

~~~java
package com.acme.search.autoconfigure;

import com.acme.search.SearchFacade;
import com.vendor.search.SearchClient;

import org.junit.jupiter.api.Test;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class SearchAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestApplication.class);

    @Test
    void createsDefaultWhenOptionalSdkIsPresent() {
        this.runner.run(context -> {
            assertThat(context).hasSingleBean(SearchFacade.class);
            assertThat(context.getBean(SearchFacade.class).provider())
                    .isEqualTo("starter-default");
        });
    }

    @Test
    void skipsAutoConfigurationWhenOptionalSdkIsMissing() {
        this.runner
                .withClassLoader(new FilteredClassLoader(SearchClient.class))
                .run(context ->
                        assertThat(context).doesNotHaveBean(SearchFacade.class));
    }

    @Test
    void userFacadeMakesDefaultBackOff() {
        this.runner
                .withUserConfiguration(UserSearchConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(SearchFacade.class);
                    assertThat(context.getBean(SearchFacade.class).provider())
                            .isEqualTo("user");
                });
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }

    @Configuration(proxyBeanMethods = false)
    static class UserSearchConfiguration {

        @Bean
        SearchFacade customSearchFacade() {
            return () -> "user";
        }
    }
}
~~~

The test application uses `@EnableAutoConfiguration`, not `AutoConfigurations.of(SearchAutoConfiguration.class)`. That causes Spring Boot to go through candidate discovery from the `AutoConfiguration.imports` file in the JAR/test resources.

`FilteredClassLoader` simulates the scenario where the SDK is not on the runtime classpath. In that case, the class condition does not match and the default `SearchFacade` is not registered. The user bean test confirms auto-configuration yields to the application configuration.

### 7.3. Running the Tests

With Maven:

~~~bash
mvn test
~~~

Expected result: three tests PASS.

| Test | SDK class | User bean | Result |
|---|---|---|---|
| `createsDefaultWhenOptionalSdkIsPresent` | Present | Absent | Default `SearchFacade` present |
| `skipsAutoConfigurationWhenOptionalSdkIsMissing` | Absent | Absent | No `SearchFacade` |
| `userFacadeMakesDefaultBackOff` | Present | Present | Only application's facade is used |

The tests confirm auto-configuration discovery and condition behavior. They do not measure startup time and do not by themselves prove the processor generated metadata. To confirm the metadata part, inspect the artifact as in the previous section.

## 8. Where Does Metadata Help Optimize Cost?

Suppose the runtime classpath has 100 auto-configuration candidates, of which 30 depend on libraries that are not present. If the corresponding static conditions have been recorded in metadata, Spring can filter out some candidates right at the filter stage, before reading each configuration's bytecode.

Benefits come from reducing work that must be done:

- Fewer auto-configuration classes must be read/parsed.
- Fewer irrelevant configurations go deep into configuration processing.
- Less metadata/class loading and condition processing for candidates already guaranteed not to match.
- Startup cost can decrease, especially for applications with many starters and many optional auto-configurations.

Do not cite a generic percentage improvement figure. The savings depend on the number of candidates, the number of early-filterable conditions, classloaders, dependency graph size, runtime environment, and other startup costs.

Metadata also does not directly reduce request execution time, database query speed, or the instantiation cost of a selected bean. It focuses on the auto-configuration selection and processing phase when the context starts.

## 9. Limitations: Metadata Does Not Evaluate Every Condition

Metadata is a partial record of information usable early. Many conditions still need the current context, Environment, or bean definitions:

- `@ConditionalOnMissingBean` needs to know whether a matching bean has already been registered.
- `@ConditionalOnBean` depends on BeanFactory state and the order of definitions processed so far.
- `@ConditionalOnProperty` needs the effective value in Environment.
- `@ConditionalOnResource` needs to check resources via the resource loader.
- `@ConditionalOnExpression` needs to evaluate SpEL; in particular, do not reference beans in expressions because it can cause premature bean initialization.

Some condition types can be recorded by the processor into metadata for early filtering; other conditions are evaluated during standard configuration processing. Do not assume every `@Conditional` annotation is put into metadata or that a candidate kept by metadata will definitely create a bean.

### 9.1. Distinguishing Early Filtering from Final Condition Results

There are three different situations:

| Situation | Meaning |
|---|---|
| Candidate excluded by metadata filter | Spring does not import that auto-configuration during this processing pass |
| Candidate passes filter but standard condition does not match | The configuration/bean is still excluded at the condition evaluation stage |
| Bean definition is registered but instance creation fails | The error lies in dependencies, constructors, factory methods, binding, or lifecycle |

The Condition Evaluation Report is useful for explaining condition match/no-match. However, looking at the report alone is not enough to conclude that metadata produced a specific time savings.

### 9.2. Metadata Does Not Replace Proper Condition Design

Write auto-configurations with conditions that express the right contract:

- Use `@ConditionalOnClass` to isolate integrations with optional dependencies.
- Use `@ConditionalOnMissingBean` for default beans that the application is allowed to replace.
- Use `@ConditionalOnProperty` when a feature depends on a configuration property.
- Split nested configurations when needed to protect method signatures from optional classes absent from the classpath.
- Provide a specific return type for `@Bean` methods so bean conditions have sufficient type metadata.

The processor only helps Boot check early what can be checked; it cannot fix an auto-configuration with wrong conditions or missing declared dependencies.

## 10. Separating Auto-Configuration Metadata from Configuration Property Metadata

A common naming mistake is confusing the two annotation processors:

### `spring-boot-autoconfigure-processor`

- Collects certain condition/order metadata of auto-configurations.
- Generates `META-INF/spring-autoconfigure-metadata.properties`.
- Supports the early candidate filtering mechanism during auto-configuration import.
- Declared in Maven `annotationProcessorPaths` or Gradle `annotationProcessor`.

### `spring-boot-configuration-processor`

- Reads classes/fields/methods annotated with `@ConfigurationProperties`.
- Generates `META-INF/spring-configuration-metadata.json`.
- Provides property descriptions, data types, default values, and hints for IDEs.
- Helps developers write `application.yml`/`application.properties` more conveniently.

A starter may need **both**: one processor to optimize auto-configuration filtering, one processor to provide property hints for IDEs. They generate two different files and serve two different stages.

## 11. Measuring and Evaluating Effectiveness Reliably

To find out whether metadata is worthwhile in a specific project:

1. Build the artifact with `spring-boot-autoconfigure-processor` enabled.
2. Check that the JAR has `META-INF/spring-autoconfigure-metadata.properties`.
3. Confirm important auto-configuration conditions were recorded by the processor.
4. Run the same application with the same dependency graph, same JDK, same configuration, and same environment.
5. Measure multiple fresh-process startups, discard warm-up runs if any, and compare the median instead of picking a single fastest run.
6. If deep analysis is needed, use Java Flight Recorder or startup profiling tools to inspect class loading, configuration parsing, and other costs.
7. Verify that the final conditions and beans do not change across builds.

Do not compare one run on a warm machine against one run on a cold machine, or simultaneously change dependencies/properties and attribute the entire difference to metadata.

For small applications with only a few auto-configurations, the difference may be very small. For large starter ecosystems with many optional integrations and many non-matching candidates, early filtering can significantly reduce configuration parsing work.

## 12. Common Mistakes

- **Confusing `AutoConfiguration.imports` with `spring-autoconfigure-metadata.properties`:** one file lists candidates; the other supports filtering those candidates.
- **Misusing `spring-boot-configuration-processor`:** this processor generates property metadata for IDEs, not a replacement for the auto-configuration processor.
- **Declaring the processor in runtime `implementation`:** use the dedicated annotation processor configuration to keep the proper compile-time scope.
- **Building source only without checking the JAR:** the generated file might not be inside the final artifact due to compiler/resource/packaging configuration.
- **Writing metadata properties by hand:** format and keys are generated details; fix annotations/processor setup and rebuild.
- **Thinking all conditions are filtered early:** only a subset of metadata is recorded by the processor; conditions needing Environment/BeanFactory still must run at the appropriate stage.
- **Thinking metadata decides the final bean:** metadata only helps filter candidates; bean conditions and bean registration still have their own pipeline.
- **Using an `AutoConfigurations.of(...)` test and concluding imports metadata was tested:** that testing style is useful for condition logic, but does not replace an integration test going through `@EnableAutoConfiguration` and the imports resource.
- **Not aligning the processor version with Boot:** metadata generated by a different version can be hard to diagnose; keep the same version.
- **Disabling annotation processing:** compiler options like `-proc:none` prevent the processor from running.
- **Omitting the processor when a module has many optional auto-configurations:** functionality can still be correct, but the opportunity for early filtering is lost.
- **Unintentionally pulling optional dependencies into runtime:** classpath conditions always see classes if the dependency is actually packaged; check dependency scopes and starter composition.
- **Measuring startup with a single run:** noise from JIT, filesystem cache, process scheduling, and environment can exceed the metadata difference.

## 13. Process for Verifying a Starter in a Real Project

1. Identify which module contains `@AutoConfiguration`.
2. Check that the module declares `spring-boot-autoconfigure-processor` in the proper compile-time configuration.
3. Check that `AutoConfiguration.imports` lists the right candidate classes.
4. Run a clean build of the artifact.
5. Use `jar tf` to confirm both the imports resource and `spring-autoconfigure-metadata.properties`.
6. Use `ApplicationContextRunner` or integration tests to verify classpath present/missing and user bean back-off.
7. Use `FilteredClassLoader` to simulate absent optional dependencies.
8. Use the condition report when needed to explain final outcomes.
9. If interested in performance, measure startup multiple times with a controlled environment and dependency graph.
10. Clearly separate which conclusions are evidence of correctness, which are evidence of metadata generation, and which are performance measurements.

The final three pieces of evidence must remain distinct: **behavior tests** prove conditions work; **JAR inspection** proves metadata is packaged; **startup measurement** shows actual improvement.

## 14. Self-Check Questions

1. How do `AutoConfiguration.imports` and `spring-autoconfigure-metadata.properties` differ? **Imports lists candidates; metadata assists with filtering out unsuitable candidates early.**
2. Which artifact generates `spring-autoconfigure-metadata.properties`? **`spring-boot-autoconfigure-processor`.**
3. Where should the processor be declared? **In the module containing auto-configuration, via Maven `annotationProcessorPaths` or Gradle `annotationProcessor`.**
4. Does metadata replace `@ConditionalOnClass`? **No.** The annotation expresses the condition; metadata is a compile-time record to support early filtering.
5. If the metadata file is absent, will auto-configuration definitely stop working? **No.** Standard conditions can still be evaluated; the early-filtering opportunity is lost.
6. Is `@ConditionalOnMissingBean` always decided solely from compile-time metadata? **No.** It depends on bean definitions in the context.
7. Which file does `spring-boot-configuration-processor` generate? **`META-INF/spring-configuration-metadata.json`**, used for property hints/tooling.
8. What data does `AutoConfigurationImportFilter` receive? **A list of auto-configuration class names and `AutoConfigurationMetadata`; it returns match results to determine which candidates are imported.**
9. What does `FilteredClassLoader` test in this lesson? **Simulates an optional SDK missing from the classpath and confirms auto-configuration does not create the bean.**
10. Do passing tests prove how much faster startup is? **No.** Tests prove correctness; controlled startup measurements are needed to evaluate performance.
11. Should you edit `spring-autoconfigure-metadata.properties` directly inside the JAR? **No.** The file is generated output; edit source/processor config and rebuild.
12. Why separate class-level `@ConditionalOnClass` from method signatures depending on optional libraries? **So the optional class is not loaded by the JVM before the condition has a chance to guard the configuration.**

## 15. Official References (Spring Boot 3.3.13)

- [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): annotation processor, metadata file, Maven/Gradle configuration, and auto-configuration lifecycle.
- [AutoConfigurationImportFilter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportFilter.html): filter that can exclude auto-configurations before bytecode is read.
- [AutoConfigurationImportSelector API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html): selecting and filtering auto-configuration candidates.
- [AutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): declaring an auto-configuration class.
- [Condition Annotations API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/package-summary.html): conditions used to decide whether a configuration applies.
- [Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html): property metadata used for IDEs and tooling.
