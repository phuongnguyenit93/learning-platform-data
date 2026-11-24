# Filtering Auto-Configuration Candidates Before Full Configuration Processing in Spring Boot

## 1. The Problem: Many Candidates, Yet the Application Needs Only a Subset

A Spring Boot application can bring many starters and libraries onto the classpath. Each JAR can publish candidate auto-configuration classes via the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The candidate list can be much larger than the configurations that actually apply. For example, an auto-configuration integrating JDBC should not be fully processed if the required JDBC APIs are completely absent at runtime. Parsing every candidate class as a full configuration only to discover later that classpath conditions fail adds startup work.

Spring Boot therefore has an **early candidate filtering** (*early auto-configuration filtering*) mechanism. The idea is to use **class names and pre-prepared condition metadata** to eliminate candidates that are definitely unsuitable before having to read and fully process their configuration class structure.

An immediate distinction: **candidate filtering** is an optimization step during auto-configuration selection. It does not mean skipping all condition evaluations, and must not be understood as “if the class is present, the bean is created”.

### After This Lesson, You Can Answer

- Is a class name in **AutoConfiguration.imports** already a bean?
- How does Spring Boot decide to drop a candidate at an early stage?
- What roles do **AutoConfigurationImportFilter**, **AutoConfigurationMetadata**, and **spring-boot-autoconfigure-processor** play?
- Why is **@ConditionalOnClass** at the class level suitable for early filtering, while **@ConditionalOnMissingBean** needs to know the context's bean state?
- How do you prove a candidate is skipped when an optional dependency disappears and appears when the dependency is present?
- If a candidate creates no bean, should you check the imports file, exclude, classpath, or condition report first?

The exercise uses **Java 21, Gradle, and Spring Boot 3.3.x**, with a library and consuming application example in separate packages.

## 2. Big Picture from Discovery to Bean Registration

Overview flow:

~~~text
JARs on classpath
      |
      v
Read AutoConfiguration.imports
→ Candidate class name list
      |
      v
Deduplicate / remove configured excludes
      |
      v
Early filters (AutoConfigurationImportFilter)
+ condition metadata when available
      |
      +----------------------+
      |                      |
  Filtered out        Remaining candidates
  Not imported                |
                              v
                 Select/order auto-configurations
                              |
                              v
                 Process annotations, @Configuration,
                 conditions at appropriate phases
                              |
                       +------+------+
                       |             |
                     Match       No match
                       |             |
                       v             v
                  Bean definition   Skip corresponding
                  may be registered bean/configuration
                       |
                       v
                  Context creates beans per lifecycle
~~~

The diagram intentionally simplifies several Spring processing stages. In Spring Boot 3.3, **AutoConfigurationImportSelector** participates in selecting auto-configurations via the **DeferredImportSelector** mechanism. When selecting candidates, the selector can apply import filters before configuration classes are fully processed.

Concepts to distinguish:

| Term | Role | What It Does **Not** Prove |
| --- | --- | --- |
| **Candidate discovery** | Collect class names from **AutoConfiguration.imports** | Does not yet mean the class creates a bean. |
| **Exclusion** | Remove classes the application asked to exclude | Does not mean the class/bytecode vanished from the JAR. |
| **Early filtering** | Eliminate candidate classes definitely unsuitable based on available information | Does not replace all bean/property/runtime conditions. |
| **Condition evaluation** | Decide whether a configuration or bean method fits | Does not mean every class had to be loaded upfront. |
| **Bean registration/creation** | Register definitions and instantiate per the Spring container | Bean creation order is not dictated solely by imports line order. |

These are **multiple layers of selection**, not a single if expression.

## 3. AutoConfigurationImportSelector Selects and Filters Candidates

In Spring Boot 3.3, **AutoConfigurationImportSelector** is the component coordinating auto-configuration class selection. When auto-configuration is enabled via **@EnableAutoConfiguration** (usually inside **@SpringBootApplication**), the selector finds the candidate list and performs the necessary processing.

The main steps can be understood as:

1. Check whether auto-configuration is enabled.
2. Read candidate class names from **AutoConfiguration.imports** resources on the classpath.
3. Deduplicate names and apply the set of **excluded** auto-configurations.
4. Apply **AutoConfigurationImportFilter** implementations to eliminate candidates failing early-checked conditions.
5. Finalize the imported class set and let Spring continue processing configurations, conditions, and bean definitions.

Method names and implementation details may vary across Spring Boot versions, but the meaning of filtering before importing configuration classes is the focus of this lesson.

### 3.1. How Does Exclude Differ from a Filter?

An application can explicitly exclude an auto-configuration:

~~~java
@SpringBootApplication(
    excludeName = "com.example.greeting.autoconfigure.OptionalGreetingAutoConfiguration"
)
public class DemoApplication {
}
~~~

This is a **snippet illustrating annotation syntax in a class**, not a complete Java program. Exclusion configuration can also use the **spring.autoconfigure.exclude** property when appropriate. Exclude expresses an **explicit application decision** not to use that configuration.

By contrast, an import filter can drop a candidate because **a condition is not satisfied**, such as an optional integration class being completely absent. When the dependency appears, the filter can keep the candidate in the list and other conditions continue deciding.

Exclude is not a fix for accidentally missing dependencies. For libraries you author yourself, define proper conditions instead of forcing every consuming application to maintain an exclude list.

## 4. How Does AutoConfigurationImportFilter Work?

Spring Boot 3.3 provides the **org.springframework.boot.autoconfigure.AutoConfigurationImportFilter** interface. An import filter receives the array of candidate class names and metadata, and returns a boolean array by position:

~~~java
boolean[] match(
    String[] autoConfigurationClasses,
    AutoConfigurationMetadata autoConfigurationMetadata
);
~~~

This is an **API method signature**, not a standalone Java program. Each **true** position means the candidate at that index **is retained at that filter step**; **false** means **do not import** that candidate past the filter. The result array must have the **exact same length** as the input candidate array.

Mental example (not actual Spring Boot output):

~~~text
Input candidates:
[CoreAutoConfiguration, OptionalGreetingAutoConfiguration]

Filter checks presence of OptionalFeature:

OptionalFeature present:
[true, true]

OptionalFeature absent:
[true, false]
~~~

Receiving **true** does not mean all bean, property, and application conditions are satisfied. It only means that specific filter **did not eliminate the candidate at this stage**.

### 4.1. Where Can Filters Be Registered?

In Spring Boot 3.3, **AutoConfigurationImportFilter** extensions are discovered using the **spring.factories** mechanism. This is an easily confused distinction:

- **AutoConfiguration.imports**: registers **candidate auto-configuration classes**.
- **META-INF/spring.factories**: can register **AutoConfigurationImportFilter implementations** and several other Spring Boot SPIs.
- **META-INF/spring-autoconfigure-metadata.properties**: contains **condition metadata generated by the annotation processor** to aid early filtering.

The three files have different responsibilities. Do not put auto-configuration classes into spring.factories expecting Boot 3.x to discover them via the new imports mechanism, and do not put filter names into AutoConfiguration.imports as if they were @AutoConfiguration classes.

A typical library **does not need to write a custom AutoConfigurationImportFilter**. The recommended approach for most cases is declaring **@ConditionalOnClass**, appropriate conditions, and enabling the annotation processor. A custom filter SPI is only suited when there are prerequisite checks that standard conditions do not handle well.

### 4.2. Why Can Early Filtering Be Faster?

The filter's inputs are primarily **class names as strings** and pre-collected metadata about conditions. Consequently, some candidates can be eliminated **before having to read the bytecode of that auto-configuration class** for full configuration processing.

This reduces class and condition parsing work at startup, especially in applications containing many optional integrations. However, actual impact depends on the number of candidates, conditions, classpath, and runtime. Do not claim every application sees a fixed speedup or that Spring Boot reads no bytecode at all during startup.

## 5. Metadata Enables Pre-Filtering Without Full Class Processing

Spring Boot provides the **spring-boot-autoconfigure-processor** annotation processor. When a library module is compiled, the processor can collect condition information on auto-configurations and generate the resource:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

An example of the metadata's **meaning** is recording that **OptionalGreetingAutoConfiguration** requires class **com.example.optionalapi.OptionalFeature** to be present. An early filter can use that information to eliminate the configuration when the optional class is absent from the classpath.

This is metadata **for auto-configuration**. Do not confuse it with:

~~~text
META-INF/spring-configuration-metadata.json
~~~

The second JSON file supports configuration documentation/hints from **@ConfigurationProperties** in IDEs; it does not serve the same function as condition metadata used for early filtering.

### 5.1. What Does a Filter Need from Metadata?

**AutoConfigurationMetadata** provides lookup capabilities for processor-generated data by class name and metadata key. Filters can read this data without parsing the entire class as a Spring configuration yet.

Not every bean condition or dynamic runtime property can be decided conclusively from static metadata alone. A candidate not eliminated early may still **fail to match** when Spring evaluates conditions in the context.

### 5.2. What If Metadata Is Missing?

Missing **spring-autoconfigure-metadata.properties** typically affects **early-filtering optimization**, without by itself turning a conditional configuration into an unconditional one. Spring still has mechanisms to evaluate annotations/conditions in later phases.

This differs from missing **AutoConfiguration.imports**: if the imports resource is absent, the library's auto-configuration class may **not be discovered as a candidate** in consuming applications.

| Missing File | Notable Consequence |
| --- | --- |
| **AutoConfiguration.imports** | Missing registration path for the library's candidate classes. |
| **spring-autoconfigure-metadata.properties** | Loses early-filtering opportunity via metadata; condition logic must still be applied when processing configurations. |
| **spring-configuration-metadata.json** | Primarily loses IDE property hints/documentation, if such metadata was intended to be provided. |

Do not interpret a passing context test as sufficient proof that all three resources are packaged properly.

## 6. Project Example: One Always-Considered Candidate, One Optional-Class Candidate

We create three modules:

~~~text
early-filter-lab/
├── settings.gradle
├── build.gradle
├── optional-api/
│   ├── build.gradle
│   └── src/main/java/com/example/optionalapi/
│       └── OptionalFeature.java
├── greeter-autoconfigure/
│   ├── build.gradle
│   ├── src/main/java/com/example/greeter/
│   │   ├── BaseMarker.java
│   │   ├── GreetingService.java
│   │   └── autoconfigure/
│   │       ├── BaseAutoConfiguration.java
│   │       └── OptionalGreetingAutoConfiguration.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/example/greeter/autoconfigure/
│       └── AutoConfigurationConditionsTest.java
└── demo-app/
    ├── build.gradle
    └── src/main/java/com/example/demo/
        └── DemoApplication.java
~~~

**optional-api** contains only one class acting as a classpath condition. **greeter-autoconfigure** declares two candidates. **demo-app** consumes the library and observes beans before/after adding optional-api to runtime.

### 6.1. Gradle Build Using Java 21 and Spring Boot 3.3.13

File **settings.gradle**:

~~~groovy
rootProject.name = 'early-filter-lab'
include 'optional-api', 'greeter-autoconfigure', 'demo-app'
~~~

Root **build.gradle**:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}

subprojects {
    apply plugin: 'java'
    apply plugin: 'io.spring.dependency-management'

    group = 'com.example'
    version = '1.0.0'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    repositories {
        mavenCentral()
    }

    dependencyManagement {
        imports {
            mavenBom 'org.springframework.boot:spring-boot-dependencies:3.3.13'
        }
    }

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }
}
~~~

Version **3.3.13** is pinned **to describe and verify the exact API in this lesson**, not as a claim of the latest Spring Boot release. Gradle requires a compatible JDK 21/Gradle environment and network access to Maven Central on first dependency download.

File **optional-api/build.gradle**:

~~~groovy
plugins {
    id 'java-library'
}
~~~

File **greeter-autoconfigure/build.gradle**:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'
    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation project(':optional-api')
}
~~~

**Explanation:** The processor is in the **annotationProcessor** configuration, so it participates in compilation without becoming a runtime dependency of the application. **optional-api** is only **testImplementation** in the autoconfigure module; production code in this module does not require optional-api, because it uses a string class name in the condition annotation.

File **demo-app/build.gradle**:

~~~groovy
plugins {
    id 'org.springframework.boot'
}

dependencies {
    implementation project(':greeter-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

This is the application configuration **without optional-api at runtime yet**. In the second run, we will add this dependency intentionally.

### 6.2. Defining the Optional Class

File **optional-api/src/main/java/com/example/optionalapi/OptionalFeature.java**:

~~~java
package com.example.optionalapi;

public final class OptionalFeature {

    private OptionalFeature() {
    }
}
~~~

This is a marker class, creating no bean or business behavior itself. The presence of this class on **runtimeClasspath** is the fact evaluated by the **@ConditionalOnClass** condition.

### 6.3. Defining the Library's Bean Types

File **greeter-autoconfigure/src/main/java/com/example/greeter/BaseMarker.java**:

~~~java
package com.example.greeter;

public record BaseMarker(String name) {
}
~~~

File **greeter-autoconfigure/src/main/java/com/example/greeter/GreetingService.java**:

~~~java
package com.example.greeter;

public final class GreetingService {

    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

These classes reside in the library JAR, so they **can always exist on the classpath** when an application declares greeter-autoconfigure.

### 6.4. Candidate Without an Optional Classpath Condition

File **greeter-autoconfigure/src/main/java/com/example/greeter/autoconfigure/BaseAutoConfiguration.java**:

~~~java
package com.example.greeter.autoconfigure;

import com.example.greeter.BaseMarker;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class BaseAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(BaseMarker.class)
    public BaseMarker baseMarker() {
        return new BaseMarker("core");
    }
}
~~~

This configuration does not require optional-api. If the application has not provided BaseMarker, the default **baseMarker** bean is created in both experiments.

### 6.5. Candidate Guarded by a Classpath Condition

File **greeter-autoconfigure/src/main/java/com/example/greeter/autoconfigure/OptionalGreetingAutoConfiguration.java**:

~~~java
package com.example.greeter.autoconfigure;

import com.example.greeter.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "com.example.optionalapi.OptionalFeature")
public class OptionalGreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

**Reading the conditions:**

- **@ConditionalOnClass** at the **class level**: consider Greeting configuration only when class **OptionalFeature** can be found.
- **@ConditionalOnMissingBean** at the **@Bean method level**: even when the classpath is valid, create the default GreetingService only if the application has not provided a matching bean.
- **name = "..."** lets you specify the optional class by string FQCN without needing to import that type to compile the library.

Placing the classpath condition at the auto-configuration class level is a favorable choice so the annotation processor can generate metadata for early filtering. Placing the condition only on **a `@Bean` method** does not carry the same semantics of “eliminating the entire auto-configuration class from the candidate list”.

**Advanced note:** If a method signature, field, or nested config of the auto-configuration directly references the optional type, the JVM/Spring may need to resolve the type at another point. In practice, use a separate nested configuration with an appropriate **@ConditionalOnClass** to isolate methods depending on optional libraries. This example does not need that because GreetingService does not reference OptionalFeature.

### 6.6. Publishing Both Candidates in the Imports File

File **greeter-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**:

~~~text
com.example.greeter.autoconfigure.BaseAutoConfiguration
com.example.greeter.autoconfigure.OptionalGreetingAutoConfiguration
~~~

Both class names are **initial candidates**. Having a line in imports **does not** mean the class will pass conditions or create beans.

At library compile time, the processor attempts to generate metadata for OptionalGreetingAutoConfiguration's condition. A real application can use that metadata to eliminate the candidate early if OptionalFeature is absent.

## 7. Testing Conditions in a Small Context

File **greeter-autoconfigure/src/test/java/com/example/greeter/autoconfigure/AutoConfigurationConditionsTest.java**:

~~~java
package com.example.greeter.autoconfigure;

import com.example.greeter.BaseMarker;
import com.example.greeter.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationConditionsTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    BaseAutoConfiguration.class,
                    OptionalGreetingAutoConfiguration.class));

    @Test
    void createsBothBeansWhenOptionalClassIsAvailable() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(BaseMarker.class);
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context.getBean(GreetingService.class).greet("An"))
                .isEqualTo("Xin chào, An!");
        });
    }

    @Test
    void skipsGreetingWhenOptionalClassIsHidden() {
        runner.withClassLoader(
            new FilteredClassLoader("com.example.optionalapi")
        ).run(context -> {
            assertThat(context).hasSingleBean(BaseMarker.class);
            assertThat(context).doesNotHaveBean(GreetingService.class);
        });
    }

    @Test
    void usesApplicationGreetingServiceWhenProvided() {
        runner.withUserConfiguration(CustomGreetingConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context.getBean(GreetingService.class).greet("An"))
                    .isEqualTo("Xin chào, An!");
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomGreetingConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return new GreetingService();
        }
    }
}
~~~

**Meaning of the three tests:**

1. Because **optional-api** is in **testImplementation**, the test context normally sees OptionalFeature. Both default beans are present.
2. **FilteredClassLoader** hides the optional-api package; the BaseMarker bean remains present, while the default GreetingService is not created because the classpath condition fails.
3. When a user-declared GreetingService bean exists, **@ConditionalOnMissingBean** makes the auto-configuration yield. In the demo, the custom bean has the same behavior to keep code short; proof of back-off is **hasSingleBean**, not a different return string.

Run:

~~~bash
gradle :greeter-autoconfigure:test
~~~

If the project has a Gradle Wrapper, use **./gradlew :greeter-autoconfigure:test** or **.\gradlew.bat :greeter-autoconfigure:test** on Windows.

**Evidentiary limit of the tests:** We specified **AutoConfigurations.of(...)** directly. These tests are great for verifying **@ConditionalOnClass and @ConditionalOnMissingBean logic**, yet **they do not by themselves prove an import filter eliminated the class using metadata during the AutoConfigurationImportSelector step**, nor do they prove the JAR contains imports. To verify the real discovery and filtering path, the next step is required.

## 8. Running a Consuming Application Without Manual Configuration Import

File **demo-app/src/main/java/com/example/demo/DemoApplication.java**:

~~~java
package com.example.demo;

import com.example.greeter.BaseMarker;
import com.example.greeter.GreetingService;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(ApplicationContext context) {
        return args -> {
            boolean hasBase =
                !context.getBeansOfType(BaseMarker.class).isEmpty();
            boolean hasGreeting =
                !context.getBeansOfType(GreetingService.class).isEmpty();

            System.out.println("BaseMarker present: " + hasBase);
            System.out.println("GreetingService present: " + hasGreeting);
        };
    }
}
~~~

Notice the application package **com.example.demo** differs from the library package **com.example.greeter.autoconfigure**. **@SpringBootApplication** scans the application's package and subpackages by default; it **does not scan the external auto-configuration package**. Candidates are discovered via the library's imports file.

### 8.1. Run A: optional-api Absent

Keep **demo-app/build.gradle** without a dependency on optional-api, then run:

~~~bash
gradle :demo-app:bootRun
~~~

Expected two lines printed by ApplicationRunner:

~~~text
BaseMarker present: true
GreetingService present: false
~~~

There may be many other Spring Boot and Gradle logs before/after these two lines. **There is no GreetingService** because class **OptionalFeature** is absent. The candidate is found from imports, yet the class-level condition does not match; with properly generated metadata, Spring Boot can eliminate the candidate early.

To observe further condition details, run:

~~~bash
gradle :demo-app:bootRun --args='--debug'
~~~

Look for the entry related to **OptionalGreetingAutoConfiguration** in the condition report, if displayed in that version and scenario's report stream. Do not assume every candidate eliminated at the import filter step appears in the exact same form as a fully processed configuration.

### 8.2. Run B: Adding the Optional Dependency

In **demo-app/build.gradle**, add one exact line inside the dependencies block:

~~~groovy
runtimeOnly project(':optional-api')
~~~

**This is a single line to add to build.gradle at this stage**, not the entire file to overwrite. When running the application, OptionalFeature is present on **runtimeClasspath**. Repeat:

~~~bash
gradle :demo-app:bootRun
~~~

Expected two lines:

~~~text
BaseMarker present: true
GreetingService present: true
~~~

This change illustrates the relationship:

~~~text
OptionalFeature absent
→ @ConditionalOnClass fails
→ OptionalGreetingAutoConfiguration eliminated/skipped
→ No default GreetingService

OptionalFeature present
→ Not eliminated by classpath condition
→ Next checks @ConditionalOnMissingBean condition
→ Default GreetingService present if no replacement bean exists
~~~

This is an evidence-based way to learn. Do not use “fewer logs” as absolute performance proof; startup time is affected by caches, JVM warm-up, hardware, initial dependency downloads, and many other factors.

### 8.3. Adding Exclude for Comparison

While **optional-api** is present, you can try excluding the candidate with an argument:

~~~bash
gradle :demo-app:bootRun --args='--spring.autoconfigure.exclude=com.example.greeter.autoconfigure.OptionalGreetingAutoConfiguration'
~~~

The application again is expected to print **GreetingService present: false** even though OptionalFeature is present. This is the result of an **explicit exclude** requested by the application. It differs from the cause “class absent from runtime classpath”. After the experiment, re-run without exclude to return to normal configuration.

## 9. Inspecting Generated Metadata and Packaged Resources

Run the compile and package task on the library module:

~~~bash
gradle :greeter-autoconfigure:jar
~~~

With the example's group and version, the expected JAR file is at:

~~~text
greeter-autoconfigure/build/libs/greeter-autoconfigure-1.0.0.jar
~~~

List entries:

~~~bash
jar tf greeter-autoconfigure/build/libs/greeter-autoconfigure-1.0.0.jar
~~~

Look for:

~~~text
com/example/greeter/autoconfigure/BaseAutoConfiguration.class
com/example/greeter/autoconfigure/OptionalGreetingAutoConfiguration.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
~~~

**Note:** The metadata resource is generated by the annotation processor during compilation. If **spring-autoconfigure-metadata.properties** is missing, check whether **annotationProcessor** is configured properly, Gradle compilation ran, and the JAR includes the compiler's generated resources output. Do not hand-craft a guessed metadata file just to make tests pass.

If the system has **unzip**, you can read the metadata entry:

~~~bash
unzip -p greeter-autoconfigure/build/libs/greeter-autoconfigure-1.0.0.jar META-INF/spring-autoconfigure-metadata.properties
~~~

Exact output depends on the processor and version, but look for information related to **OptionalGreetingAutoConfiguration** and the **OptionalFeature** classpath condition. Metadata is tool-generated data; do not treat observed line order, per-line formatting, or arbitrary key names as an immutable API for business applications.

Also read the imports resource in the JAR to make sure both FQCNs are present. A test that directly imports classes can pass even when the JAR lacks the imports file.

### Two Easily Confused Metadata Types

| Resource | Generated By | Role |
| --- | --- | --- |
| **AutoConfiguration.imports** | Declared by library author | Points out candidate auto-configuration classes. |
| **spring-autoconfigure-metadata.properties** | **spring-boot-autoconfigure-processor** | Provides condition metadata for early filtering. |
| **spring-configuration-metadata.json** | **spring-boot-configuration-processor** | Supports discovery/hints for configuration properties. |

This lesson creates no @ConfigurationProperties, so there is no need to add the configuration processor solely to illustrate import filtering.

## 10. Distinguishing Early-Checked Conditions from Late-Checked Conditions

Early filtering is most effective when a condition **can be determined using available information** before Spring has to construct all bean definitions.

| Condition or Factor | Usable for Early Decision? | Correct Understanding |
| --- | --- | --- |
| **@ConditionalOnClass** on auto-configuration class | Often usable with classpath metadata for early filtering | Class absent → can eliminate immediately; class present → still must check other conditions. |
| **@ConditionalOnMissingClass** | Can use classpath info for cases supported by processor/filter | Must verify condition logic of the version in use. |
| **@ConditionalOnBean** | Requires knowing registered bean definitions | Cannot safely infer solely from the list of classes in JARs. |
| **@ConditionalOnMissingBean** | Requires knowing context state and proper processing order | Not a “does JAR have class” check. |
| **@ConditionalOnProperty** | Depends on Environment and property semantics | Not identical to a classpath metadata lookup; evaluation timing depends on mechanism. |
| **@ConditionalOnWebApplication** | Depends on web application context / application type | Not as simple as the library class being listed in imports. |
| **Exclude** | Can eliminate during candidate selection | Explicit configuration choice by application, not a bean condition. |

In particular, **@ConditionalOnMissingBean** is used so default configuration **backs off** when the user has already created a bean. That condition cannot be handled accurately by counting classpath dependencies, because two applications with the exact same classpath can have different bean definitions.

### 10.1. Why Not Put Every Condition into an Import Filter?

If a filter tries to create contexts or read unregistered beans prematurely, it can make wrong decisions. Early filtering must be **conservative**: eliminate a candidate only when there is solid basis at the current stage that it does not apply.

**Good design** usually places classpath conditions on the auto-configuration class, uses bean/property conditions where appropriate, and lets Spring Boot execute each condition's proper mechanism.

## 11. When Do You Need to Write a Custom AutoConfigurationImportFilter?

Most starter authors only need to:

1. Register the **@AutoConfiguration** class in **AutoConfiguration.imports**.
2. Use standard conditions like **@ConditionalOnClass**, **@ConditionalOnMissingBean**, and **@ConditionalOnProperty**.
3. Enable **spring-boot-autoconfigure-processor** to generate early-filtering metadata.
4. Test branches with/without optional dependencies, custom beans, and consuming applications.

**AutoConfigurationImportFilter** is a low-level SPI. You should only consider implementing it yourself when a condition **can be safely checked early**, is systemic in nature, and no standard annotation/condition fits well.

If you actually write a filter, note the API contract:

- Receives an array of class names, which may contain null elements as sequential filters process it.
- Must not mutate the candidate class array directly.
- Returns a boolean array of **the exact same length**, mapped index-for-index.
- Must not eagerly load classes in bulk or instantiate beans during filtering, as that defeats the optimization.
- Register the filter in **META-INF/spring.factories** under the **AutoConfigurationImportFilter** key, while auto-configuration classes still go through **AutoConfiguration.imports**.
- Write tests verifying proper candidate elimination, retention, and resilience when metadata is missing or candidates are null.

Do not turn the filter SPI into a per-request/per-user business customization mechanism. It runs during context bootstrap, not when handling individual HTTP requests.

## 12. Diagnosing When a Candidate Does Not Create a Bean

### Case A — Library Is on the Classpath Yet the Class Is Not Treated as a Candidate

Check whether the JAR has the **AutoConfiguration.imports** resource and the FQCN is right. **@AutoConfiguration** on the Java class alone is insufficient for an external library to be discovered. Confirm the application's runtimeClasspath actually includes that JAR, and no custom packaging overwrote the resource.

### Case B — Imports Exists Yet Eliminated Because Optional Class Is Missing

Run Gradle on the right module to inspect dependencies:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
~~~

If optional-api is absent, **@ConditionalOnClass(name=...)** does not match. You can verify the actual class using a **ClassLoader** at runtime or inspect the dependency graph; do not rely solely on another module's source having that class.

### Case C — Optional Class Is Present Yet the Bean Is Still Missing

Early filtering does not guarantee every bean is created. Check:

- Did any **@ConditionalOnMissingBean** back off because the application already declared a bean?
- Was **@ConditionalOnProperty** disabled by a property/profile?
- Is the ApplicationContext type appropriate?
- Was the configuration excluded?
- Was there an error in the @Bean method or its bean dependencies during context initialization?

Use the Condition Evaluation Report with **--debug** to find why a condition failed to match. If the candidate was eliminated very early, report details may differ from a configuration class processed after import.

### Case D — No Metadata Found Even Though Code Has @ConditionalOnClass

Check that the processor was added via **annotationProcessor** in the autoconfigure module actually being compiled. Check compilation outputs and the published JAR; distinguish **spring-autoconfigure-metadata.properties** from **@ConfigurationProperties** metadata.

Missing metadata is not a valid reason to skip conditions yourself. Functional bugs and optimization issues must be diagnosed separately.

### Case E — Startup Time Does Not Improve Noticeably

Early filtering avoids part of the work, yet total startup still depends on classpath, reflection, bean creation, I/O, databases, logging, and JVM warm-up. There is no fixed time threshold applicable to every project.

If optimizing performance, use repeated benchmarks under controlled conditions, measuring **startup time** and the count of processed auto-configurations/beans. Do not measure a single cold run right after Gradle just downloaded dependencies.

## 13. Extended Experiments to Verify Understanding

**Experiment 1 — Without metadata:** Create an experimental build without running **spring-boot-autoconfigure-processor**, while keeping imports and condition classes. Compare behavior with/without OptionalFeature. Functional conditions must still execute accurately; the expected difference lies in the ability to use metadata for early filtering, not in the bean outcome.

**Experiment 2 — Moving condition placement:** Move the classpath condition from the class level down to the **@Bean** method level. Explain why this no longer carries the same semantics of “eliminating the entire candidate early”; measure and observe via the actual report.

**Experiment 3 — With a custom bean:** Provide GreetingService from the application before auto-configuration creates a bean. Verify only one bean remains and distinguish back-off from missing OptionalFeature.

**Experiment 4 — Explicit exclude:** Keep OptionalFeature on the classpath while excluding OptionalGreetingAutoConfiguration. Explain why the bean outcome matches the missing-class case yet **has a different cause**.

**Experiment 5 — Checking the JAR:** Temporarily delete imports in a test branch. Re-run the direct AutoConfigurations.of test and run demo-app. State why the condition test can still pass while the consuming application fails to auto-discover the configuration.

Change only **one factor** per experiment to trace causes from evidence, then restore sources before moving to the next lesson.

## 14. Misconceptions to Avoid

**“Every line in AutoConfiguration.imports is instantiated into a bean.”** Incorrect. Each line only publishes a candidate class, and that class can be excluded, early-filtered, fail conditions, or declare no beans.

**“Early filtering and @ConditionalOnMissingBean are the same mechanism.”** Incorrect. Early filtering relies on sufficiently certain information at class selection time; MissingBean inspects bean definitions in the Spring context.

**“Having @ConditionalOnClass guarantees having a bean.”** Incorrect. It is a potentially necessary condition, not sufficient. Other conditions and bean creation logic still apply.

**“spring-autoconfigure-metadata.properties is where candidates are registered.”** Incorrect. The candidate list lives in **AutoConfiguration.imports**. Condition metadata serves fast filtering.

**“Missing metadata makes @ConditionalOnClass stop working.”** Incorrect. Condition evaluation is not replaced by metadata; losing metadata mainly reduces pre-import optimization.

**“To filter candidates, just write a narrower @ComponentScan.”** Incorrect. Component scan is a separate component discovery path. Library auto-configuration is published via imports and processed by the import selector/conditions.

**“To turn off a bean, you must write a custom AutoConfigurationImportFilter.”** Usually unnecessary. Use **@ConditionalOnProperty**, **@ConditionalOnMissingBean**, or excludes per your integration contract.

**“A test with AutoConfigurations.of is proof of early filtering.”** Insufficient. It tests conditions when adding classes directly to the context; proving the discovery/import filtering path requires running a consumer that boots via the imports mechanism.

## 15. Lesson Completion Checklist

- [ ] Can explain the difference between **candidate**, **import**, **condition match**, and **created bean**.
- [ ] Can state the responsibilities of **AutoConfigurationImportSelector** and **AutoConfigurationImportFilter**.
- [ ] Can distinguish the three resources **AutoConfiguration.imports**, **spring-autoconfigure-metadata.properties**, and **spring-configuration-metadata.json**.
- [ ] Place **@ConditionalOnClass** at the class level to express a classpath-dependent integration.
- [ ] Use **@ConditionalOnMissingBean** properly to yield to user beans.
- [ ] Can build a JAR containing classes, imports, and processor metadata.
- [ ] Ran context tests when OptionalFeature is present and hidden.
- [ ] Ran demo-app with optional-api absent and present, observing the difference.
- [ ] Proved explicit exclude differs from a missing optional class.
- [ ] Do not interpret direct condition tests as absolute proof of startup optimization.
- [ ] Know how to use **--debug**, the dependency graph, and JAR inspection to diagnose root causes.

## Conclusion

**Filtering candidates before full configuration processing** helps Spring Boot avoid parsing auto-configurations that cannot apply to the current runtime. The initial list comes from **AutoConfiguration.imports**; **AutoConfigurationImportFilter** implementations can use information such as the classpath and **metadata generated by spring-boot-autoconfigure-processor** to eliminate candidate classes early.

Remaining candidates must still pass appropriate conditions and Spring's bean registration/creation mechanisms. When designing a library, publish classes accurately in imports, declare conditions at the right level, enable the processor for optimization, and verify with both isolated tests and real consuming applications. That is how you understand **why a configuration was skipped, eliminated early, or actually produced a bean**, rather than guessing from dependencies alone.

## Reference Documentation

- [AutoConfigurationImportFilter — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportFilter.html)
- [AutoConfigurationImportSelector — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html)
- [Spring Boot reference — Developing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
