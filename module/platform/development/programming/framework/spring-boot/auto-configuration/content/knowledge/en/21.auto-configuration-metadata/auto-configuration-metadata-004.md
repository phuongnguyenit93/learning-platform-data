# spring-boot-configuration-processor and spring-configuration-metadata.json

## 1. Goal: Helping IDEs Understand Application Configuration

When developing a Spring Boot starter or auto-configuration, users typically declare configuration in `application.properties` or `application.yaml`. For example:

~~~properties
acme.client.endpoint=https://api.example.test
acme.client.connect-timeout=2s
acme.client.mode=standard
~~~

The application can bind these keys into a class annotated with `@ConfigurationProperties`. However, with only the Java class, the IDE may not fully know:
- Which properties are supported by the library;
- The data type of each property;
- Descriptions and default values;
- Valid values or autocomplete suggestions;
- Which properties are deprecated and which keys replace them.

Spring Boot solves this problem with **configuration metadata**. The annotation processor `spring-boot-configuration-processor` reads classes/methods annotated with `@ConfigurationProperties` at compile time and generates the file:

~~~text
META-INF/spring-configuration-metadata.json
~~~

IDEs and configuration support tools can use that file to provide completion, documentation, and value hints when users edit application configuration.

**Important distinction:** metadata is a description for development tools. It does not automatically bind properties, does not automatically create beans, and does not replace `@ConfigurationProperties` or Spring Binder at runtime.

This article uses **Spring Boot 3.5.16, Java 17+, and Maven/Gradle** as the example baseline.

## 2. Two Similarly Named Processors with Different Jobs

In the Spring Boot ecosystem there are two commonly encountered annotation processors:

| Processor | Generated File | Purpose |
| --- | --- | --- |
| `spring-boot-configuration-processor` | `META-INF/spring-configuration-metadata.json` | Describes configuration properties for IDEs, autocomplete, and documentation |
| `spring-boot-autoconfigure-processor` | `META-INF/spring-autoconfigure-metadata.properties` | Collects certain condition metadata so Spring Boot can filter out inapplicable auto-configurations early, helping startup |

This article focuses on the first processor.

Do not confuse the two files:
- `spring-configuration-metadata.json` describes properties that users can configure.
- `spring-autoconfigure-metadata.properties` is metadata serving auto-configuration evaluation/filtering.

A starter project can use both processors if it both provides `@ConfigurationProperties` and has auto-configuration classes needing condition metadata.

## 3. How It Works

Metadata generation flow:

~~~text
Java/Kotlin source
       |
       v
@ConfigurationProperties
       |
       v
spring-boot-configuration-processor
       |
       v
Annotation processing during compile
       |
       v
META-INF/spring-configuration-metadata.json
       |
       v
Packaged into JAR
       |
       v
IDE reads metadata to support application.properties/YAML
~~~

The processor runs during the compilation phase. It analyzes the source model, property names, types, descriptions, and certain statically inferable default values.

Example class:

~~~java
@ConfigurationProperties("acme.client")
public class AcmeClientProperties {
    private String endpoint;
    private int maxConnections;
}
~~~

can generate metadata for:
- `acme.client.endpoint`;
- `acme.client.max-connections`.

Property names are normalized to lowercase kebab-case, even when Java field names use camelCase.

### Metadata Is Not a Binding Mechanism

There are three separate things:

1. `@ConfigurationProperties` describes the configuration structure that Spring Binder can bind.
2. `@EnableConfigurationProperties`, `@ConfigurationPropertiesScan`, or an appropriate registration mechanism makes the properties object participate in the ApplicationContext.
3. `spring-boot-configuration-processor` generates metadata so development tools understand the configuration.

If you only add an entry to the JSON without code reading/binding the property, the application does not magically start handling that key. Manual metadata only supplements information for the IDE.

Conversely, a property can be bound and work even if metadata is not generated; in that case, the IDE may lack completion or descriptions.

## 4. Configuring the Processor with Maven

Spring Boot 3.5 recommends using `maven-compiler-plugin` version **3.12.0 or higher** and adding the processor to `annotationProcessorPaths`.

Condensed POM example for a Boot 3.5.16 project:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>acme-metadata-demo</artifactId>
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
                            <version>3.5.16</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Points to remember:
- The processor is declared in the compiler plugin, so it only participates in annotation processing at build time.
- The processor version should match the Spring Boot version the project uses.
- If using multiple annotation processors, such as Lombok, they must be declared in `annotationProcessorPaths`. Ensure Lombok runs **before** `spring-boot-configuration-processor` per Spring Boot's guidelines.
- If the project uses AspectJ and annotation processing already runs through another plugin, avoid running the processor twice.

Some older Maven configurations declare `spring-boot-configuration-processor` as a dependency with `optional=true`. With modern Maven Compiler Plugin, explicit annotation processor path configuration helps control which processors run and avoids pulling the processor into consumer runtime dependencies.

Run:

~~~bash
mvn clean compile
~~~

After compiling, check the file:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

If the file is missing, check whether the annotation processor is invoked by Maven compiler plugin, whether the class has `@ConfigurationProperties`, and whether the source compiled successfully.

## 5. Configuring the Processor with Gradle

With Gradle, declare the processor in the `annotationProcessor` configuration:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Run:

~~~bash
./gradlew clean compileJava
~~~

Metadata is typically located at:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

If using `additional-spring-configuration-metadata.json`, configure the task so resources are processed before the annotation processor runs:

~~~groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
~~~

This configuration line ensures additional metadata is available when `compileJava` executes. With Gradle Kotlin DSL, you can use the corresponding syntax:

~~~kotlin
tasks.named<JavaCompile>("compileJava") {
    inputs.files(tasks.named("processResources"))
}
~~~

Do not declare the processor in `implementation` just to run annotation processing. `annotationProcessor` is the configuration meant for this job.

## 6. Java Example: Generating Metadata from @ConfigurationProperties

Create file `src/main/java/com/example/metadata/AcmeClientProperties.java`:

~~~java
package com.example.metadata;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.client")
public class AcmeClientProperties {

    /**
     * Base endpoint of the Acme service.
     */
    private String endpoint = "https://api.example.test";

    /**
     * Maximum time to wait for one request.
     */
    private Duration connectTimeout = Duration.ofSeconds(2);

    /**
     * Request processing mode.
     */
    private Mode mode = Mode.STANDARD;

    /**
     * Retry configuration.
     */
    private Retry retry = new Retry();

    /**
     * Protocol used to reach the service.
     */
    private String protocol = "https";

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Mode getMode() {
        return mode;
    }

    public void setMode(Mode mode) {
        this.mode = mode;
    }

    public Retry getRetry() {
        return retry;
    }

    public void setRetry(Retry retry) {
        this.retry = retry;
    }

    public String getProtocol() {
        return protocol;
    }

    public void setProtocol(String protocol) {
        this.protocol = protocol;
    }

    public enum Mode {
        STANDARD,
        BULK
    }

    public static class Retry {

        /**
         * Maximum number of attempts.
         */
        private int maxAttempts = 3;

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }
    }
}
~~~

The processor can detect properties such as:

| Java field | Generated property |
| --- | --- |
| `endpoint` | `acme.client.endpoint` |
| `connectTimeout` | `acme.client.connect-timeout` |
| `mode` | `acme.client.mode` |
| `retry.maxAttempts` | `acme.client.retry.max-attempts` |
| `protocol` | `acme.client.protocol` |

Descriptions in field Javadoc can be used as `description` when the class's source is being compiled. Write short, clear, plain-text descriptions; do not rely on Markdown or HTML because field Javadoc is put into JSON metadata without passing through a Markdown processor.

**Registering properties for runtime binding:** a class with `@ConfigurationProperties` does not automatically become a bean in every application. For example:

~~~java
package com.example.metadata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(AcmeClientProperties.class)
public class MetadataDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataDemoApplication.class, args);
    }
}
~~~

`@EnableConfigurationProperties` serves runtime binding. The annotation processor can read the properties class at compile time even though a separate bean registration step is needed for the application to use that object.

## 7. How Does the Processor Detect Properties, Descriptions, and Defaults?

The processor collects metadata from classes or methods annotated with `@ConfigurationProperties`.

### 7.1. JavaBeans with Getters/Setters

For typical mutable classes, the processor looks for standard getters/setters. Collection and map types have special handling; in some cases, only a getter is needed to recognize a property.

Property names follow the JavaBean convention:
- `getConnectTimeout()` → `connect-timeout`;
- `isEnabled()` → `enabled`;
- `getRetry().getMaxAttempts()` → `retry.max-attempts`.

### 7.2. Constructor Binding and Records

If a class has a single parameterized constructor, the processor can generate a property for each constructor parameter, unless the constructor is annotated with `@Autowired`. For constructors annotated with `@ConstructorBinding`, properties are generated from that constructor's parameters.

For Java records, component descriptions should be placed using class-level `@param` Javadoc tags, because records do not have explicit instance fields where regular field Javadoc can be placed.

Example:

~~~java
/**
 * Acme client settings.
 *
 * @param endpoint Base endpoint of the service.
 * @param timeout Maximum request duration.
 */
@ConfigurationProperties("acme.client")
public record AcmeClientRecordProperties(
        String endpoint,
        Duration timeout) {
}
~~~

### 7.3. Nested Properties

The processor automatically recognizes inner classes as nested properties. In the `AcmeClientProperties` example, the `Retry` class is a static nested class, so its properties are represented under the `acme.client.retry` namespace.

If the nested type is a regular class located in another file, you can use `@NestedConfigurationProperty` on the field or getter to indicate that the type should be treated as a nested property group:

~~~java
@NestedConfigurationProperty
private Retry retry;
~~~

This annotation supports **metadata generation**; it does not change how Spring Binder binds the object. Collections and maps are already handled specially by the processor, so this annotation is not needed for them.

### 7.4. Lombok

The processor supports common Lombok annotations such as `@Data`, `@Value`, `@Getter`, and `@Setter`. When configuring multiple processors, ensure Lombok runs before the Spring Boot configuration processor so the required accessors can be recognized.

### 7.5. Limitations When Extracting Default Values

The processor uses heuristics to infer default values from the source model. Inference is only reliable when:
- The type is being compiled from the current source;
- The default is statically expressed;
- The value does not depend on runtime logic or constants in another class that the processor cannot analyze.

Some cases the processor cannot infer automatically:
- Collections whose default value is built across multiple statements;
- Default values taken from constants or other methods;
- Types that only exist as compiled classes from dependencies, without source;
- Dynamic values or complex expressions such as `Duration.ofSeconds(2)`.

When a default is not detected, supplement it with manual metadata. Do not assume the JSON already contains all defaults just because a Java field has an initializer.

## 8. Structure of spring-configuration-metadata.json

The file is generated in the JAR at:

~~~text
META-INF/spring-configuration-metadata.json
~~~

The JSON has four main sections:

| Section | Role |
| --- | --- |
| `groups` | Groups properties by prefix or namespace |
| `properties` | Each property that users can declare |
| `hints` | Suggested values, providers, or autocomplete support |
| `ignored` | Properties intentionally excluded from the normal metadata list |

Condensed example:

~~~json
{
  "groups": [
    {
      "name": "acme.client",
      "type": "com.example.metadata.AcmeClientProperties",
      "sourceType": "com.example.metadata.AcmeClientProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.client.endpoint",
      "type": "java.lang.String",
      "description": "Base endpoint of the Acme service.",
      "sourceType": "com.example.metadata.AcmeClientProperties",
      "defaultValue": "https://api.example.test"
    },
    {
      "name": "acme.client.retry.max-attempts",
      "type": "java.lang.Integer",
      "description": "Maximum number of attempts.",
      "sourceType": "com.example.metadata.AcmeClientProperties$Retry",
      "defaultValue": 3
    }
  ],
  "hints": [],
  "ignored": {
    "properties": []
  }
}
~~~

This JSON illustrates the structure. Actual metadata also depends on whether the processor can infer types/defaults/descriptions.

### 8.1. Group

A group is a high-level namespace, not a property with its own value. For example, `acme.client` groups the properties:
- `acme.client.endpoint`;
- `acme.client.connect-timeout`;
- `acme.client.retry.max-attempts`.

A property is not required to belong to a group. Attributes can be declared independently.

Group attributes typically include:
- `name`: group name;
- `type`: representing Java type;
- `description`: description;
- `sourceType`: source type contributing the metadata;
- `sourceMethod`: method contributing the group if any.

### 8.2. Property

Each entry in `properties` describes a key:
- `name`: full name, lowercase and dot-separated;
- `type`: Java type or generic type;
- `description`: description;
- `sourceType`: class contributing the property;
- `defaultValue`: default value if known;
- `deprecation`: deprecation information if any.

Primitive types are represented by their corresponding wrappers, for example `int` becomes `java.lang.Integer`.

### 8.3. Hints

Hints help IDEs provide configuration suggestions. For example, `acme.client.protocol` can accept `http` or `https`:

~~~json
{
  "hints": [
    {
      "name": "acme.client.protocol",
      "values": [
        {
          "value": "https",
          "description": "Use encrypted HTTP transport."
        },
        {
          "value": "http",
          "description": "Use plain HTTP transport."
        }
      ]
    }
  ]
}
~~~

Hints do not validate runtime values automatically. If a property only accepts a fixed set of values, use a Java enum or appropriate validation so code actually enforces the value; metadata only helps IDEs suggest options.

### 8.4. Ignored

The `ignored.properties` section lists keys intentionally excluded from the normal property list. This is how metadata handles properties that should not appear in completion/documentation.

Ignored metadata does not delete Java fields, does not modify beans, and does not disable runtime logic. It only affects the generated metadata content.

## 9. Supplementing Metadata Manually

Not every property comes from a `@ConfigurationProperties` class. Some keys may be read directly using `Environment`, `Binder`, or `@Value`. In addition, the processor may not infer desired defaults or descriptions.

Place the file at:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Example for the Acme project:

~~~json
{
  "properties": [
    {
      "name": "acme.client.connect-timeout",
      "defaultValue": "2s",
      "description": "Maximum time to wait for one request."
    },
    {
      "name": "acme.client.mode",
      "defaultValue": "standard",
      "description": "Request processing mode."
    },
    {
      "name": "acme.client.protocol",
      "type": "java.lang.String",
      "defaultValue": "https",
      "description": "Transport scheme used to reach the service."
    }
  ],
  "hints": [
    {
      "name": "acme.client.protocol",
      "values": [
        {
          "value": "https",
          "description": "Use encrypted HTTP transport."
        },
        {
          "value": "http",
          "description": "Use plain HTTP transport."
        }
      ]
    }
  ],
  "ignored": {
    "properties": [
      {
        "name": "acme.client.internal-cache-size"
      }
    ]
  }
}
~~~

The processor automatically merges these contents into the main metadata file.

Merge rules:
- If a property was already discovered automatically, manual metadata can override `description`, `defaultValue`, and `deprecation` information when declared.
- If a property was not discovered in the current module, manual metadata can add a new property.
- `ignored.properties` removes the corresponding properties from the `properties` section of the generated metadata file.
- The additional metadata file is optional; there is no need to create an empty file if there is no supplemental content.

**Important note:** if you add a new property only in JSON, code must still actually read/bind that property. Metadata does not materialize a Java field or automatically create application behavior.

### 9.1. Defaults for Duration and Collections

In the Java example, `connectTimeout` has a default of `Duration.ofSeconds(2)`. The processor may not infer that expression; manual metadata declares:

~~~json
{
  "name": "acme.client.connect-timeout",
  "defaultValue": "2s"
}
~~~

For collections, for example:

~~~java
private List<String> regions =
        new ArrayList<>(List.of("ap-southeast-1", "ap-northeast-1"));
~~~

the processor does not always infer collection defaults completely. You can supplement:

~~~json
{
  "name": "acme.client.regions",
  "defaultValue": [
    "ap-southeast-1",
    "ap-northeast-1"
  ]
}
~~~

The default format must match the property type and how Spring Boot converts configuration values.

## 10. Value Hints and Providers

A hint can declare `values` or `providers`.

### 10.1. Value Hints

Use when the set of values is relatively stable and can be described statically:

~~~json
{
  "hints": [
    {
      "name": "acme.client.protocol",
      "values": [
        {"value": "http"},
        {"value": "https"}
      ]
    }
  ]
}
~~~

If values are constrained in code, an enum is usually a better choice because the compiler and binder can enforce the type. Hints are only editor assistance.

### 10.2. Value Providers

Providers attach semantic meaning to a property so the IDE can look up context-aware suggestions. Some providers defined by Spring Boot:

| Provider | Purpose |
| --- | --- |
| `any` | Allows entering additional arbitrary values |
| `class-reference` | Suggests classes on the project classpath, optionally restricted to a target type |
| `handle-as` | Asks the editor to treat the property as another type |
| `logger-name` | Suggests logger names and logger groups |
| `spring-bean-reference` | Suggests matching bean names |
| `spring-profile-name` | Suggests Spring profiles present in the project |

Example suggesting bean names:

~~~json
{
  "hints": [
    {
      "name": "acme.client.interceptor",
      "providers": [
        {
          "name": "spring-bean-reference",
          "parameters": {
            "target": "org.springframework.web.client.RestClientCustomizer"
          }
        }
      ]
    }
  ]
}
~~~

Providers do not guarantee every IDE implements them identically. An IDE may support some providers or not yet support a specific provider; therefore treat this as content assistance, not a runtime API.

For maps, hints can apply separately to keys or values using the `.keys` and `.values` suffixes. For example `acme.client.routes.keys` and `acme.client.routes.values`.

## 11. Marking Properties as Deprecated

When renaming a property, you should let users know the old key is obsolete and what the new key is.

For JavaBean properties, use `@DeprecatedConfigurationProperty` on the old getter:

~~~java
import org.springframework.boot.context.properties.DeprecatedConfigurationProperty;

@Deprecated
@DeprecatedConfigurationProperty(
        replacement = "acme.client.endpoint",
        since = "1.4.0")
public String getBaseUrl() {
    return this.endpoint;
}

@Deprecated
public void setBaseUrl(String baseUrl) {
    this.endpoint = baseUrl;
}
~~~

If the old getter/setter still maps to the new property, the application can continue binding the old key during the transition period. The annotation places deprecation and replacement information into metadata.

`@DeprecatedConfigurationProperty`:
- Should be placed on the getter exposing the old property;
- Can specify `replacement` and `since`;
- Generates a warning-level deprecation by default;
- Does not have an attribute to select the level in this annotation, because code is still handling the old property.

When you want to keep a notice for a property that has already been removed from code, you can declare deprecation in manual metadata. Do not remove aliases from code before planning a migration path for users.

## 12. Metadata for Types in Another Module

If `@ConfigurationProperties` uses a nested class located in another module, the current processor may only see the compiled class without source to extract Javadoc/defaults.

Options:
1. Add manual metadata for that property/type.
2. Place metadata source for the type in the module that owns the type.
3. If the type is a regular class you control, consider `@ConfigurationPropertiesSource` per the API of the Boot version in use.
4. If the external type is outside your control, provide corresponding metadata on the classpath following Spring Boot conventions.

A metadata file for a type can be placed in the form:

~~~text
META-INF/spring/configuration/metadata/com.example.SomeType.json
~~~

This is useful in multi-module projects where module A declares properties while the actual nested type is defined in module B.

## 13. Inspecting Metadata After Building

After running:

~~~bash
mvn clean compile
~~~

Check the generated file:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

You can quickly view the contents with:

~~~powershell
Get-Content target/classes/META-INF/spring-configuration-metadata.json
~~~

After packaging the JAR:

~~~bash
mvn package
jar tf target/acme-metadata-demo-1.0.0.jar
~~~

With a standard library JAR, metadata resides at `META-INF/spring-configuration-metadata.json`. With an executable Spring Boot JAR, application contents typically reside in `BOOT-INF/classes/META-INF/spring-configuration-metadata.json`.

You can check separately:

~~~powershell
jar tf target/acme-metadata-demo-1.0.0.jar | Select-String "spring-configuration-metadata.json"
~~~

When publishing a library/starter, verify that the metadata is actually packaged inside the published artifact, not merely present in the module's workspace.

## 14. Testing Runtime Binding and Metadata Generation

Use `ApplicationContextRunner` to confirm properties are still bound into the object. The following test example does not validate the JSON metadata schema; it tests runtime behavior separately.

Create file `src/test/java/com/example/metadata/AcmeClientPropertiesTests.java`:

~~~java
package com.example.metadata;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeClientPropertiesTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PropertiesConfiguration.class);

    @Test
    void bindsConfigurationProperties() {
        runner.withPropertyValues(
                "acme.client.endpoint=https://internal.example.test",
                "acme.client.connect-timeout=3s",
                "acme.client.mode=bulk",
                "acme.client.retry.max-attempts=5",
                "acme.client.protocol=http"
        ).run(context -> {
            assertThat(context)
                    .hasSingleBean(AcmeClientProperties.class);

            AcmeClientProperties properties =
                    context.getBean(AcmeClientProperties.class);

            assertThat(properties.getEndpoint())
                    .isEqualTo("https://internal.example.test");

            assertThat(properties.getConnectTimeout())
                    .isEqualTo(Duration.ofSeconds(3));

            assertThat(properties.getMode())
                    .isEqualTo(AcmeClientProperties.Mode.BULK);

            assertThat(properties.getRetry().getMaxAttempts())
                    .isEqualTo(5);

            assertThat(properties.getProtocol())
                    .isEqualTo("http");
        });
    }

    @Test
    void configurationMetadataWasGenerated() {
        assertThat(new ClassPathResource(
                "META-INF/spring-configuration-metadata.json").exists())
                .isTrue();
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(AcmeClientProperties.class)
    static class PropertiesConfiguration {
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Expected result:** both tests PASS:
- The first test confirms Binder converts property values into the proper Java types, including `Duration`, enum, and nested property.
- The second test confirms the metadata file was copied into the classpath build output.

The two tests prove two different aspects. Runtime binding can work even if metadata is missing; metadata can exist, yet properties still need to be registered and bound properly in the ApplicationContext.

## 15. Common Issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `spring-configuration-metadata.json` missing after compile | Processor not configured or class lacks `@ConfigurationProperties` | Check Maven annotationProcessorPaths or Gradle annotationProcessor |
| IDE does not autocomplete properties | Metadata file missing from JAR/module or IDE has not reloaded project | Check target/classes and published artifact, reload project |
| Property binds but has no description | Missing Javadoc or class only has compiled bytecode | Add source Javadoc or manual metadata |
| Duration/List default does not appear | Processor cannot infer dynamic/collection expressions | Declare `defaultValue` in additional metadata |
| Added JSON metadata but application ignores key | Metadata only describes for IDE | Add actual property reading/binding code |
| Stale metadata after changing properties | Incremental build or artifact not rebuilt | Run a clean build and inspect the new JAR |
| Lombok properties not recognized properly | Lombok ran after Spring processor | Order Lombok before configuration processor |
| Additional metadata not merged in Gradle | `compileJava` ran before `processResources` | Add task dependency per guidelines |
| Duplicate properties or wrong description | Manual metadata override or duplicate declaration | Check property name and metadata sources |
| IDE does not show provider hints | IDE does not support that provider | Check IDE support; do not rely on hints for runtime validation |

## 16. Checklist When Releasing a Starter or Auto-Configuration

Before publishing the artifact:

1. Each properties class has a clear prefix and key names in kebab-case.
2. Properties have short, understandable Javadoc without complex markup.
3. Default values are extracted accurately by the processor or supplemented with manual metadata.
4. Nested properties are described properly; external classes use `@NestedConfigurationProperty` when needed.
5. Deprecated properties have a replacement and deprecation version.
6. Additional metadata only contains properties/hints that truly need supplementation.
7. The processor is declared at compile time, not becoming an unnecessary runtime dependency.
8. If using Lombok, annotation processors are ordered properly.
9. Clean build generates `META-INF/spring-configuration-metadata.json`.
10. The published JAR contains the metadata file.
11. Runtime binding is tested independently of metadata.
12. Consumer smoke test confirms starter users have working completion and binding.

For an auto-configuration library, good metadata helps users discover the public configuration contract without opening source code or guessing properties from bean names.

## 17. Self-Check Questions

**Question 1.** Which file does `spring-boot-configuration-processor` generate and what is it for?

**Answer:** Generates `META-INF/spring-configuration-metadata.json` so IDEs/configuration tools display properties, types, descriptions, defaults, and hints.

**Question 2.** Does JSON metadata make a property bind automatically?

**Answer:** No. Runtime binding still requires `@ConfigurationProperties` and an appropriate registration/binding mechanism. Metadata only assists development tools.

**Question 3.** Where should Maven declare the processor in modern Spring Boot 3.5 configuration?

**Answer:** In `maven-compiler-plugin`, `annotationProcessorPaths`, using plugin version 3.12.0 or higher.

**Question 4.** Which Gradle configuration declares the processor?

**Answer:** `annotationProcessor`.

**Question 5.** Why might the default of `Duration.ofSeconds(2)` not appear?

**Answer:** The processor only infers defaults when expressions can be statically analyzed; method-call expressions may not be recognized. Supplement `defaultValue` in additional metadata.

**Question 6.** Where is `additional-spring-configuration-metadata.json` merged?

**Answer:** The processor merges it into `META-INF/spring-configuration-metadata.json` at compile time. The additional file is optional.

**Question 7.** Does `spring-boot-autoconfigure-processor` replace the configuration processor?

**Answer:** No. It generates `spring-autoconfigure-metadata.properties` for early auto-configuration condition filtering, a different purpose from property metadata.

## 18. Official References

- Spring Boot 3.5 — Generating Your Own Metadata by Using the Annotation Processor: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/annotation-processor.html
- Spring Boot 3.5 — Metadata Format: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/format.html
- Spring Boot 3.5 — Providing Manual Hints: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/manual-hints.html
- Spring Boot 3.5 — Configuration Metadata overview: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/index.html
- Spring Boot 3.5 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
