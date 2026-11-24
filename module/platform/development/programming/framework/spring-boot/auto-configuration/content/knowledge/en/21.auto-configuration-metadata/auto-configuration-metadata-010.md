# Distinguishing Tooling Metadata from Bean Creation Decision Logic

## 1. Goal: Both Are Metadata, Yet Different Responsibilities

When building a Spring Boot starter or auto-configuration library, you may encounter multiple metadata files generated during compilation or packaged inside the JAR. Their file names look quite similar, yet they serve different phases. Confusing them easily leads to false conclusions such as: “Because metadata exists, beans are created automatically”, “The IDE suggests a property so the application definitely handles that property”, or “Deleting the metadata file stops bean creation conditions from running”.

This lesson focuses on Spring Boot **3.3.13**, Spring Framework 6.1, and Java 17+. We will distinguish four components:

1. `META-INF/spring-configuration-metadata.json`: describes properties so IDEs and configuration tools support suggestions, completion, and documentation.
2. `META-INF/spring-autoconfigure-metadata.properties`: auto-configuration condition metadata so Spring Boot can filter out non-matching configurations early, optimizing startup.
3. `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`: list of auto-configuration candidate classes that Spring Boot needs to discover.
4. Runtime APIs such as `@ConfigurationProperties`, `Binder`, `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnMissingBean`, and `@Bean`: the components that actually participate in binding values, evaluating conditions, and registering beans.

**Core takeaway:** metadata supporting tooling and processing optimization does not replace runtime logic. To know whether a bean is created, trace the path of auto-configuration registration, property binding, conditions, and bean definitions.

## 2. Quick Comparison Table

| Component | Who uses it / when | Purpose | Does it directly define beans? |
| --- | --- | --- | --- |
| `spring-configuration-metadata.json` | IDEs, configuration support tools | Suggests property names, types, descriptions, defaults/hints, and deprecation | **No** |
| `spring-autoconfigure-metadata.properties` | Spring Boot when selecting/filtering auto-configurations | Filters out condition-mismatched candidates early to improve startup | **No**; it describes conditions for optimization |
| `AutoConfiguration.imports` | Spring Boot when discovering auto-configurations | Registers the list of auto-configuration candidate classes | **No**; candidates still must pass conditions |
| `@ConfigurationProperties` + Binder | Spring runtime when creating/binding properties beans | Reads Environment and binds values into Java objects | Creates/binds properties beans when registered properly |
| `@Conditional...` + `@Bean` | Spring runtime when processing configurations | Decides whether a configuration/bean method is applied | **Yes**, via bean definitions and BeanFactory |

The first three files all contain “metadata” or “imports”, yet they cannot replace one another. You need to understand both where each file is generated and where it is read.

## 3. Configuration Metadata: Supporting IDEs and Configuration Tools

### 3.1. What Does `spring-configuration-metadata.json` Do?

Spring Boot places configuration metadata in the JAR at:

```text
META-INF/spring-configuration-metadata.json
```

This JSON file describes configurations supported by the library. Compatible IDEs can read it to provide:

- Property name suggestions when writing `application.properties` or `application.yaml`.
- Key name completion and certain commonly used values.
- Expected data types, such as `Boolean`, `String`, `Duration`, or collections.
- Descriptions helping users understand a property's purpose.
- Default values recorded in metadata.
- Hints for meaningful values/options.
- Deprecation information and replacement properties.

Example of partial metadata:

```json
{
  "groups": [
    {
      "name": "acme.greeting",
      "type": "com.acme.greeting.autoconfigure.GreetingProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.greeting.enabled",
      "type": "java.lang.Boolean",
      "description": "Whether the greeting service is enabled.",
      "defaultValue": false
    },
    {
      "name": "acme.greeting.prefix",
      "type": "java.lang.String",
      "description": "Prefix used when creating a greeting.",
      "defaultValue": "Hello"
    }
  ]
}
```

This is a condensed example to illustrate structure. The actual file may contain additional `sourceType`, `hints`, deprecation, and other metadata.

### 3.2. Information Groups in the JSON

| Group | Contents | What can tools use it for? |
| --- | --- | --- |
| `groups` | Namespace or property groups | Displaying organized configuration structure |
| `properties` | Property name, type, description, default, deprecation | Key suggestions, explanations, and value types |
| `hints` | Suggested values or providers supplying suggestions | Completion for enums, modes, or value lists |
| `ignored` | Properties marked to be ignored in metadata | Omitting those properties from corresponding suggestion lists |

A property does not necessarily need its own group. `groups` primarily help tools understand namespaces; `properties` is what describes each key users can enter.

Example `hints`:

```json
{
  "hints": [
    {
      "name": "acme.greeting.mode",
      "values": [
        {
          "value": "formal",
          "description": "Use a formal greeting."
        },
        {
          "value": "casual",
          "description": "Use a casual greeting."
        }
      ]
    }
  ]
}
```

The IDE can display `formal` and `casual` when users configure the property. However, hints **are not runtime validators**. If the application needs to reject values outside the list, there must be proper binding/validation/condition logic; adding hints alone does not make Spring automatically throw an error when a user enters a different value.

### 3.3. Defaults in Metadata Are Not Runtime Value Assignment Commands

Suppose metadata describes:

```json
{
  "name": "acme.greeting.prefix",
  "type": "java.lang.String",
  "defaultValue": "Hello"
}
```

The `defaultValue` in JSON helps tools display documentation/suggestions. Actual values in the application come from how the properties object is initialized, constructors, bound configuration, and runtime logic.

Example:

```java
@ConfigurationProperties("acme.greeting")
public class GreetingProperties {

    private String prefix = "Hello";

    public String getPrefix() {
        return this.prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
```

In this case, `"Hello"` is the default value supplied by the Java object. The metadata processor can infer that value to write into JSON. If someone edits the JSON to `"Hi"` without editing the Java code, the IDE can suggest `"Hi"` while runtime still initializes `prefix` to `"Hello"`. Having the two places out of sync makes documentation misleading.

### 3.4. Metadata Does Not Mean a Property Is Used at Runtime

A key appearing in `spring-configuration-metadata.json` does not prove:

- That a `@ConfigurationProperties` bean actually binds that key.
- That code calls `Environment.getProperty(...)` to read that key.
- That `@ConditionalOnProperty` uses that key.
- That any bean is created or excluded because of that key.
- That runtime will reject any value not listed in hints.

Metadata can contain manually declared properties for cases where keys are handled via `@Value`, `Environment`, or custom logic. Tools can know that key for suggestions, but the application only reacts if runtime code actually reads or binds it.

## 4. Generating Configuration Metadata with the Annotation Processor

### 4.1. `spring-boot-configuration-processor`

Spring Boot provides the `spring-boot-configuration-processor` annotation processor. The processor runs during compilation and collects information from classes or methods annotated with `@ConfigurationProperties` to generate:

```text
META-INF/spring-configuration-metadata.json
```

The processor is not a bean and is not invoked to create beans when the application starts. It runs at **build time** to generate machine-readable documentation.

### 4.2. Maven Configuration

With Maven, the processor can be declared as an optional dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

In projects using Maven Compiler Plugin with explicit annotation processor configuration, declare the processor in `annotationProcessorPaths`. Example for Spring Boot 3.3.13 and compiler plugin 3.13.0:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <annotationProcessorPaths>
            <path>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-configuration-processor</artifactId>
                <version>3.3.13</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
```

Choose one configuration approach suited to the current build and avoid duplicate annotation processing setup. If the project uses Lombok, ensure proper processor ordering so the metadata processor sees the model after Lombok processes it.

### 4.3. Gradle Configuration

With Gradle, declare the processor in its own configuration:

```groovy
dependencies {
    annotationProcessor "org.springframework.boot:spring-boot-configuration-processor"
}
```

Do not put the processor in `implementation` just to get IDE suggestions. `annotationProcessor` is the place for tools that run during compilation; consumers do not need to carry this processor at runtime just to bind properties.

### 4.4. Auto-Generated Metadata and Additional Metadata

The processor reads `@ConfigurationProperties` and the source model to generate most metadata automatically. However, there are cases needing manual supplementation:

- Properties handled via `Environment` or `@Value` without a properties class.
- Default values that cannot be statically inferred from source.
- Additional hints or descriptions needed.
- Deprecation/replacement declarations needed.
- Keys that need to be excluded from auto-generated metadata.

The additional file is named:

```text
META-INF/additional-spring-configuration-metadata.json
```

Example:

```json
{
  "properties": [
    {
      "name": "acme.greeting.mode",
      "type": "java.lang.String",
      "description": "Mode used by the custom greeting strategy."
    }
  ],
  "hints": [
    {
      "name": "acme.greeting.mode",
      "values": [
        {
          "value": "formal",
          "description": "Use a formal greeting."
        },
        {
          "value": "casual",
          "description": "Use a casual greeting."
        }
      ]
    }
  ]
}
```

The processor merges additional metadata with the main metadata. The additional file does not automatically make `acme.greeting.mode` bound or used in conditions. If the application wants this key to take effect, runtime code reading or binding it must be added.

### 4.5. Describing Properties with Javadoc

Spring Boot can use field Javadoc inside `@ConfigurationProperties` to populate `description`. Write short, accurate, plain-text descriptions:

```java
@ConfigurationProperties("acme.greeting")
public class GreetingProperties {

    /**
     * Whether the greeting service is enabled.
     */
    private boolean enabled;

    /**
     * Prefix used when creating a greeting.
     */
    private String prefix = "Hello";

    // getters and setters
}
```

For record classes, there are no regular instance fields to attach field Javadoc to; use class-level `@param` Javadoc tags for record components per Spring Boot's guidelines.

## 5. Auto-Configuration Metadata: Supporting Early Condition Filtering

### 5.1. The `spring-autoconfigure-metadata.properties` File

This is a different file, typically located at:

```text
META-INF/spring-autoconfigure-metadata.properties
```

Spring Boot has a separate annotation processor, `spring-boot-autoconfigure-processor`, to collect certain auto-configuration condition metadata. If the file is generated and present in the JAR, Spring Boot can use it to **eagerly filter** non-matching auto-configurations before full processing, thereby improving startup time.

Points to remember:

- This is not a file for IDEs to suggest properties.
- It describes condition metadata serving the auto-configuration filtering process.
- It does not replace `@ConditionalOnClass`, `@ConditionalOnProperty`, or `@ConditionalOnBean` in source.
- It does not define `@Bean` methods and does not create beans.
- Missing this file does not mean auto-configuration cannot run; Boot still has its standard condition evaluation mechanism.
- This is a candidate-processing optimization, not a place to put new business rules.

### 5.2. Maven Processor Configuration

Spring Boot 3.3 guides adding `spring-boot-autoconfigure-processor` to the annotation processor paths of Maven Compiler Plugin (version 3.12.0 or higher). Example:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <annotationProcessorPaths>
            <path>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-autoconfigure-processor</artifactId>
                <version>3.3.13</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
```

If the same module also needs `spring-boot-configuration-processor`, declare **both processors** in `annotationProcessorPaths`. Keep versions synchronized with the project's Spring Boot BOM/parent. Do not configure one processor path and assume the other processor will still be auto-discovered from the classpath.

### 5.3. Gradle Configuration

With Gradle, the processor uses the `annotationProcessor` configuration:

```groovy
dependencies {
    annotationProcessor "org.springframework.boot:spring-boot-autoconfigure-processor"
}
```

If both metadata types are needed, also declare `spring-boot-configuration-processor` in the same configuration.

### 5.4. Distinguishing the Roles of the Two Processors

| Processor | Generated File | Purpose |
| --- | --- | --- |
| `spring-boot-configuration-processor` | `spring-configuration-metadata.json` | Describes properties so IDEs/tools assist configuration |
| `spring-boot-autoconfigure-processor` | `spring-autoconfigure-metadata.properties` | Records condition metadata so Boot filters auto-configurations early |

Do not substitute one processor for the other. A starter may need both: one so users configure more easily in the IDE, one so Boot optimizes auto-configuration selection.

## 6. `AutoConfiguration.imports` Is Candidate Registration, Not IDE Suggestion Metadata

Another file commonly present in the JAR:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Its contents list auto-configuration class names, one fully qualified class name per line. Spring Boot reads this file to find candidates. After candidates are found, conditions on the class or bean methods still decide whether the configuration applies.

| File | Which question does it answer? |
| --- | --- |
| `AutoConfiguration.imports` | Which auto-configuration classes should Boot inspect? |
| `spring-autoconfigure-metadata.properties` | Which candidates can be excluded early based on condition metadata? |
| `spring-configuration-metadata.json` | Which properties should the IDE suggest/explain? |

For example, the imports file may list `GreetingAutoConfiguration`, yet `@ConditionalOnProperty` still does not match when `acme.greeting.enabled=false`. Conversely, JSON metadata may describe `acme.greeting.enabled`, but if the auto-configuration is not registered or no code reads the property, no bean appears automatically.

## 7. Runtime Logic That Actually Binds Properties and Creates Beans

### 7.1. Binding Properties with `@ConfigurationProperties`

`@ConfigurationProperties` marks a class or method holding typed configuration. However, this annotation needs to be registered through an appropriate mechanism, such as:

- `@EnableConfigurationProperties(GreetingProperties.class)`.
- `@ConfigurationPropertiesScan`.
- `@Component` on the class under a supported model.

Once the properties bean is registered, Spring Boot uses its binding infrastructure to read `Environment` and assign values into the object. Actual values come from property sources and defaults in the Java object/constructor.

### 7.2. Conditions Decide Whether a Bean Is Registered

Example:

```java
@Bean
@ConditionalOnProperty(
    prefix = "acme.greeting",
    name = "enabled",
    havingValue = "true"
)
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService(GreetingProperties properties) {
    return name -> properties.getPrefix() + ", " + name;
}
```

Here:

- `@ConditionalOnProperty` reads the value from Spring `Environment`.
- `havingValue = "true"` requires the property to have value true per the annotation's condition.
- `@ConditionalOnMissingBean` lets users supply their own implementation.
- If conditions match, Spring registers the bean definition for `greetingService`.
- When the bean is requested/instantiated, the method returns the implementation.

`spring-configuration-metadata.json` does not participate in this `enabled` check. Metadata can only help IDEs suggest the key; the condition reads the actual property from Environment.

### 7.3. One Property Can Serve Both Binding and Conditions

In the example, `acme.greeting.enabled` is bound into `GreetingProperties.enabled` and simultaneously checked by `@ConditionalOnProperty`. Both operations read the same configuration source but have different responsibilities:

1. Binder converts the value into a boolean in the `GreetingProperties` object.
2. The condition evaluates Environment to decide whether the `GreetingService` bean is registered.

Do not think the JSON metadata file “converts” the property to boolean or triggers the condition by itself. Both behaviors are performed by the runtime infrastructure.

## 8. Standalone Java 17+ Example: Metadata With and Without Bean Logic

The example below creates a Spring Boot 3.3.13 application with a properties class and an auto-configuration. It runs two contexts:

- `disabled`: the properties bean is still bound, but `GreetingService` is not created.
- `enabled`: the properties bean is bound and the service is created when the property is enabled.

The same runtime code can run even if IDE-facing metadata is not generated. The processor only helps generate tooling-support files during compilation.

### 8.1. Project Structure

```text
metadata-vs-runtime/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   ├── com/example/demo/MetadataVsRuntimeDemo.java
    │   │   └── com/acme/greeting/autoconfigure/
    │   │       ├── GreetingProperties.java
    │   │       ├── GreetingService.java
    │   │       └── GreetingAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

The application package is `com.example.demo`; the auto-configuration resides in `com.acme.greeting.autoconfigure`. The library's package is outside the application's default component scan. Boot finds the auto-configuration via the imports file.

### 8.2. `pom.xml` File

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

    <groupId>com.example</groupId>
    <artifactId>metadata-vs-runtime</artifactId>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-configuration-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Both annotation processors are declared separately in `annotationProcessorPaths`. They run during compile; they must not be added to runtime just so the application binds properties or creates beans.

### 8.3. `GreetingProperties.java` File

Path `src/main/java/com/acme/greeting/autoconfigure/GreetingProperties.java`:

```java
package com.acme.greeting.autoconfigure;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.greeting")
public class GreetingProperties {

    /**
     * Whether the greeting service is enabled.
     */
    private boolean enabled = false;

    /**
     * Prefix used when creating a greeting.
     */
    private String prefix = "Hello";

    public boolean isEnabled() {
        return this.enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getPrefix() {
        return this.prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
```

Field Javadoc helps the configuration processor generate descriptions in metadata. Java field initializers provide the initial runtime value when the property is not configured.

### 8.4. `GreetingService.java` File

Path `src/main/java/com/acme/greeting/autoconfigure/GreetingService.java`:

```java
package com.acme.greeting.autoconfigure;

public interface GreetingService {
    String greet(String name);
}
```

### 8.5. `GreetingAutoConfiguration.java` File

Path `src/main/java/com/acme/greeting/autoconfigure/GreetingAutoConfiguration.java`:

```java
package com.acme.greeting.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true"
    )
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService(
        GreetingProperties properties
    ) {
        return name -> properties.getPrefix() + ", " + name;
    }
}
```

Two things to separate:

- `@EnableConfigurationProperties` registers the properties bean so Spring Boot binds values.
- `@ConditionalOnProperty` and `@ConditionalOnMissingBean` decide whether the service bean is registered.

Even when `enabled=false`, the properties bean still exists because `@EnableConfigurationProperties` is on the auto-configuration class; only the service bean is excluded by the condition.

### 8.6. `AutoConfiguration.imports` Resource

Create the file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Contents:

```text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
```

This file registers the auto-configuration candidate. It differs from the `spring-configuration-metadata.json` file that IDEs read.

### 8.7. `MetadataVsRuntimeDemo.java` File

Path `src/main/java/com/example/demo/MetadataVsRuntimeDemo.java`:

```java
package com.example.demo;

import com.acme.greeting.autoconfigure.GreetingProperties;
import com.acme.greeting.autoconfigure.GreetingService;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;

public class MetadataVsRuntimeDemo {

    public static void main(String[] args) {
        runCase(
            "disabled",
            "--acme.greeting.enabled=false",
            "--acme.greeting.prefix=Hello"
        );

        runCase(
            "enabled",
            "--acme.greeting.enabled=true",
            "--acme.greeting.prefix=Hi"
        );
    }

    private static void runCase(String label, String... args) {
        SpringApplication application =
            new SpringApplication(MetadataVsRuntimeDemo.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context =
                 application.run(args)) {

            GreetingProperties properties =
                context.getBean(GreetingProperties.class);

            boolean serviceExists =
                !context.getBeansOfType(GreetingService.class).isEmpty();

            System.out.printf(
                "%s: propertiesBean=true, enabled=%s, serviceBean=%s%n",
                label,
                properties.isEnabled(),
                serviceExists
            );

            if (serviceExists) {
                GreetingService service =
                    context.getBean(GreetingService.class);
                System.out.println("greeting=" + service.greet("Ada"));
            }
        }
    }
}
```

### 8.8. Building and Running

Requirements: JDK 17+, Maven, and permission to download dependencies. In the `metadata-vs-runtime` directory, run:

```bash
mvn -q clean compile spring-boot:run
```

Lines printed by the program itself:

```text
disabled: propertiesBean=true, enabled=false, serviceBean=false
enabled: propertiesBean=true, enabled=true, serviceBean=true
greeting=Hi, Ada
```

Spring startup logs may appear depending on logging configuration; the three lines above are the output of the `System.out` statements in the program.

**Explanation of the disabled scenario:**

- Auto-configuration is discovered via the imports file.
- `@EnableConfigurationProperties` registers `GreetingProperties`.
- Binder reads the command-line property and assigns `enabled=false`.
- `@ConditionalOnProperty` does not match, so `GreetingService` is not registered.

**Explanation of the enabled scenario:**

- The properties bean is bound with `enabled=true` and `prefix=Hi`.
- The condition matches.
- There is no user-provided `GreetingService` bean, so `@ConditionalOnMissingBean` matches.
- The service bean is registered and returns `Hi, Ada`.

Neither scenario requires reading `spring-configuration-metadata.json` to decide beans. If you disable annotation processors while keeping runtime dependencies, the imports file, properties class, and conditions intact, binding/bean behavior is still determined by runtime code.

### 8.9. Checking the Generated Metadata Files

After compiling, use PowerShell:

```powershell
Get-Content target/classes/META-INF/spring-configuration-metadata.json
Get-Content target/classes/META-INF/spring-autoconfigure-metadata.properties
Get-Content src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

You will see three files with different origins and purposes:

- `spring-configuration-metadata.json`: properties `acme.greeting.enabled` and `acme.greeting.prefix` along with inferred descriptions/defaults.
- `spring-autoconfigure-metadata.properties`: condition metadata collected by the auto-configuration processor.
- `AutoConfiguration.imports`: registration line for `GreetingAutoConfiguration` written by you in resource sources.

Exact key names/contents in the two processor-generated metadata files depend on conditions and the source model. Do not hard-code the entire processor output as a rigid contract; inspect meaningful required entries and use runtime tests to confirm behavior.

## 9. When Metadata Suggests a Property but Runtime Does Not React

Suppose the IDE suggests:

```properties
acme.greeting.mode=formal
```

Yet runtime code only has:

```java
@ConditionalOnProperty(
    prefix = "acme.greeting",
    name = "enabled",
    havingValue = "true"
)
```

and `GreetingProperties` has no `mode` field, nor any code reading `acme.greeting.mode`. In that case:

- The IDE can suggest `mode` if metadata contains this key.
- Binder does not automatically create a `mode` field in the object without a matching property target.
- Conditions do not check `mode`.
- The bean does not change behavior merely because `mode=formal` was entered.

To make the property take effect, add a runtime mechanism. For example, add a field to `GreetingProperties` and use that value in the service; or write logic reading `Environment`; or use an appropriate condition. Then update metadata to accurately describe the new behavior.

**Do not use metadata to fake a feature.** An autocompleted property is not proof that a feature has been implemented.

## 10. Common Mistakes

| Misconception / Error | Reality | Fix |
| --- | --- | --- |
| Having `spring-configuration-metadata.json` creates beans automatically | JSON mainly supports IDEs/tools | Check imports, runtime conditions, and bean definitions |
| Without configuration metadata, properties cannot bind | Binder does not depend on that JSON file | Register `@ConfigurationProperties` and check Environment |
| Hints list valid values so runtime automatically rejects others | Hints serve tooling, not as validators | Use enums, validation, or appropriate checking code |
| `defaultValue` in JSON assigns runtime defaults | Actual defaults come from object/constructor/binding | Keep defaults in code and metadata synchronized |
| `spring-autoconfigure-metadata.properties` is the same as config metadata JSON | The two files have different consumers and purposes | Distinguish processors and runtime usage |
| Having `spring-autoconfigure-metadata.properties` guarantees beans are created | File supports early filtering; conditions still decide | Read conditions and test beans |
| Having `AutoConfiguration.imports` means all beans in the class appear | Candidates can still be excluded by conditions | Check conditions, properties, classpath, and beans |
| Adding processor to `implementation`/runtime dependency | Processor is only needed at build time | Use Maven annotation processor path or Gradle `annotationProcessor` |
| Only writing Javadoc without configuring the processor | JSON may not be generated | Configure `spring-boot-configuration-processor` |
| Manual metadata describes a property without runtime code | IDE may suggest a non-functional key | Only expose properties when runtime truly supports them, or clearly explain purpose |
| Editing generated JSON in target and releasing | File will be overwritten on the next build | Use `additional-spring-configuration-metadata.json` |
| Using one processor in place of the other | Each processor creates a different metadata type | Configure both properly when a module needs both |

## 11. Debugging Workflow When a Bean Is Not Created

Follow this order to avoid editing metadata by mistake:

1. **Confirm auto-configuration is registered:** check `AutoConfiguration.imports` in the JAR or candidate list.
2. **Check classpath:** if there is `@ConditionalOnClass`, confirm the dependency is actually present at runtime.
3. **Check actual properties:** read `Environment` or test configuration; do not look only at IDE autocomplete.
4. **Check property binding:** confirm `@ConfigurationProperties` was registered and values in the object are accurate.
5. **Check conditions:** read `ConditionEvaluationReport`, run with `--debug`, or use `ApplicationContextRunner`.
6. **Check user beans:** `@ConditionalOnMissingBean` may back off because the application already supplied a matching bean.
7. **Check bean registration/creation:** inspect bean definitions and dependency initialization errors.
8. **Only after that, check tooling metadata:** if the IDE does not suggest keys, check the processor and `spring-configuration-metadata.json`.

When the problem is “IDE does not suggest properties”, check metadata. When the problem is “bean is not created”, check runtime conditions and context. The two workflows may relate, but should not replace each other.

## 12. Self-Check Exercises

**Question 1.** What is `spring-configuration-metadata.json` primarily used for?  
**Answer:** Providing information to IDEs/configuration tools such as property names, types, descriptions, defaults, and hints to support completion/documentation.

**Question 2.** If you delete the configuration metadata JSON file from the JAR while keeping `@ConfigurationProperties`, Binder, and auto-configuration intact, do properties still bind?  
**Answer:** Yes. JSON metadata is not a required input for the runtime binder.

**Question 3.** What role does `spring-autoconfigure-metadata.properties` play?  
**Answer:** Contains processor-generated condition metadata so Spring Boot filters out non-matching auto-configurations early, helping startup; it does not replace condition annotations or bean methods.

**Question 4.** Which file lists auto-configuration candidates?  
**Answer:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

**Question 5.** The IDE suggests `acme.greeting.mode=formal`. Does that prove the application reads the mode property?  
**Answer:** No. There must be runtime code binding/reading the property or a condition using it.

**Question 6.** How does `defaultValue` in JSON differ from the default value on a Java field?  
**Answer:** JSON describes it for tools; field initializers/constructors supply the runtime object value before or during binding.

**Question 7.** If you want IDE suggestions for a property that is not auto-detected, what should you do?  
**Answer:** Use `META-INF/additional-spring-configuration-metadata.json` to add metadata; at the same time, ensure runtime has code handling the property if you want it to actually take effect.

**Question 8.** Imports file and condition metadata exist, yet the bean does not appear. What should you inspect next?  
**Answer:** Condition report, actual properties, classpath, user beans, and bean registration results. Metadata does not prove all conditions matched.

## 13. Key Takeaways and References

- `spring-configuration-metadata.json` is for IDEs and configuration support tools; it does not bind properties or create beans by itself.
- `spring-autoconfigure-metadata.properties` is condition metadata for early auto-configuration filtering; it helps performance rather than replacing condition logic.
- `AutoConfiguration.imports` registers auto-configuration candidates; conditions still decide whether a configuration applies.
- `@ConfigurationProperties` must be registered properly; Binder reads Environment and binds values into objects.
- `@Conditional...`, `@Bean`, and BeanFactory decide which bean definitions are registered.
- Hints and defaults in metadata serve tooling; keep them synchronized with runtime code.
- When debugging, separate IDE metadata issues from binding/condition/bean creation issues.

Official Spring Boot 3.3.13 documentation:

1. [Configuration Metadata — purpose and how metadata is generated](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html).
2. [Metadata Format — groups, properties, hints, ignored, and deprecation](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html).
3. [Generating Your Own Metadata by Using the Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html).
4. [Creating Your Own Auto-configuration — conditions, imports, autoconfigure processor, and testing](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
5. [`@ConfigurationProperties` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html).
6. [`@EnableConfigurationProperties` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/EnableConfigurationProperties.html).
7. [`@ConditionalOnProperty` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).
8. [`@AutoConfiguration` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html).
