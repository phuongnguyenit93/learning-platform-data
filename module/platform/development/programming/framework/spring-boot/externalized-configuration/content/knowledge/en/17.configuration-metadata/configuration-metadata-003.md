# Declaring the Annotation Processor in Gradle and Maven for Spring Boot Configuration Metadata

## 1. Problem: Helping the IDE Understand Custom Configuration Properties

Spring Boot has many familiar properties such as `server.port`, `spring.application.name`, or `spring.datasource.url`. For framework properties, the IDE can usually suggest key names, show descriptions, and warn about certain improper usages.

However, projects often define their own configuration groups as well:

~~~yaml
app:
  notification:
    enabled: true
    sender-name: catalog-service
    max-retries: 4
    retry-delay: 5s
~~~

And Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        boolean enabled,
        String senderName,
        int maxRetries,
        Duration retryDelay
) {}
~~~

The application can bind values into `NotificationProperties` without needing a separate metadata file. However, an IDE unaware of a project's custom properties might fail to suggest `app.notification.sender-name` or display descriptions when a developer edits `application.yml`.

To assist development tooling, Spring Boot provides **`spring-boot-configuration-processor`**: a Java annotation processor that extracts information from `@ConfigurationProperties` types at **compile time** and generates configuration metadata in JSON format.

When the build is configured properly, the workflow can be visualized as:

~~~text
Class/record @ConfigurationProperties
               │
               ▼
       Java compilation
               │
               ▼
spring-boot-configuration-processor
               │
               ▼
META-INF/spring-configuration-metadata.json
               │
               ▼
IDE / dev tools read metadata
               │
               ▼
Suggest property names, types, descriptions, defaults...
~~~

**Goal of this lesson:** know how to declare the processor in **Gradle** and **Maven**, distinguish compile-time dependencies from runtime application dependencies, understand where the JSON file is generated, handle cases combined with **Lombok** or multi-module projects, and verify results with an actual build.

## 2. What Is an Annotation Processor?

In Java, annotations such as `@ConfigurationProperties`, `@Component`, or `@Deprecated` can appear in source code. However, **an annotation does not automatically mean some tool will generate a file**.

An **annotation processor** is a component invoked by the Java compiler during annotation processing. It can read information about annotations, classes, methods, fields, constructors, or type elements to generate additional source code or resources.

The Spring Boot configuration processor uses this mechanism to create **metadata describing configuration properties**. It does not need to boot an application context, connect to a database, or start a web server to discover processable `@ConfigurationProperties` types.

Distinguish three responsibilities:

| Component | Role |
| --- | --- |
| `@ConfigurationProperties` | Declares the prefix and target Java type to bind configuration |
| Spring Boot Binder | At runtime, reads property sources and binds values into Java objects |
| `spring-boot-configuration-processor` | At compile time, generates JSON metadata for IDEs/tooling |

A `@ConfigurationProperties` class **can still bind successfully without the processor**. Conversely, adding the processor while forgetting to register the `@ConfigurationProperties` bean means metadata can be generated, yet the application still lacks a configuration bean to inject.

This is the key difference: **metadata serves tooling experience and documentation; it does not replace runtime binding**.

## 3. Artifact Name and Generated File

Artifact used for Spring Boot projects:

~~~text
org.springframework.boot:spring-boot-configuration-processor
~~~

Standard output filename:

~~~text
META-INF/spring-configuration-metadata.json
~~~

When compiling with Maven, a common location is:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

With Gradle and the `main` Java source set, the common location is:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

The exact path depends on the toolchain, source set, plugins, and build structure. What matters is that **the file resides in the compilation output**, from which it can usually be packaged into a JAR.

An illustrative JSON metadata example:

~~~json
{
  "groups": [
    {
      "name": "app.notification",
      "type": "com.example.demo.config.NotificationProperties",
      "sourceType": "com.example.demo.config.NotificationProperties"
    }
  ],
  "properties": [
    {
      "name": "app.notification.enabled",
      "type": "java.lang.Boolean",
      "sourceType": "com.example.demo.config.NotificationProperties"
    },
    {
      "name": "app.notification.sender-name",
      "type": "java.lang.String",
      "sourceType": "com.example.demo.config.NotificationProperties"
    },
    {
      "name": "app.notification.retry-delay",
      "type": "java.time.Duration",
      "sourceType": "com.example.demo.config.NotificationProperties"
    }
  ]
}
~~~

This is a **JSON shape example**, not a guarantee that every field, type name, or element order in the generated file will match identically across all versions.

A metadata file can contain data groups:

- `groups`: configuration groups and source types.
- `properties`: property names, types, sources, descriptions, and defaults if the processor has enough information.
- `hints`: value suggestions/value providers for certain properties.

IDE tools can read the JSON to support code completion. Spring Boot API documentation and actual generated metadata are the authoritative sources for understanding what fields may appear.

## 4. Preparing a Sample Configuration Class

To illustrate both build tools on the same example, assume we have:

~~~text
src/
  main/
    java/com/example/demo/
      DemoApplication.java
      config/ClientProperties.java
    resources/
      application.yml
~~~

`ClientProperties.java`:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * HTTP client settings for calling the catalog service.
 */
@ConfigurationProperties(prefix = "app.catalog-client")
public record ClientProperties(
        String baseUrl,
        Duration connectTimeout,
        int maxRetries
) {}
~~~

`application.yml`:

~~~yaml
app:
  catalog-client:
    base-url: https://catalog.example.org
    connect-timeout: 3s
    max-retries: 4
~~~

`DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Here `@ConfigurationPropertiesScan` registers configuration beans in the scanned package. This is a **runtime mechanism** separate from the configuration processor recognizing annotations and generating metadata.

The canonical names of the three properties are:

~~~properties
app.catalog-client.base-url
app.catalog-client.connect-timeout
app.catalog-client.max-retries
~~~

Once configured, the processor can include information about these properties in metadata so the IDE recognizes them.

## 5. Gradle Groovy DSL: Declaring with `annotationProcessor`

In projects using `build.gradle` (Groovy DSL), the common declaration is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

If the project properly uses Spring Boot's dependency management or BOM, you may omit specifying a separate version on the `annotationProcessor` line because the artifact version is managed alongside other Spring Boot dependencies.

**Significance of `annotationProcessor` in Gradle:**

- Places the processor on the **annotation processor path** of the compile task.
- Allows the compiler to invoke the processor to generate metadata.
- Does not automatically put the processor on the **runtime classpath** like an `implementation` dependency.
- Separates a **build-only** tool from libraries the application needs when running.

An example closer to a real project:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-plugin-version>'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

In the full example, `<spring-boot-version>` and `<dependency-management-plugin-version>` are **instructional placeholders**: replace them with plugin versions suitable for your project before running. For an already generated Spring Boot project, you usually only need to add **one `annotationProcessor` line** in the `dependencies` block rather than rewriting the entire build file.

Some projects manage versions via a Gradle version catalog or platform BOM instead of the dependency-management plugin. In those cases, use the project's existing version management mechanism and avoid duplicate or unnecessary version changes.

## 6. Gradle Kotlin DSL: Declaring in `build.gradle.kts`

If the project uses Kotlin DSL, the syntax differs from Groovy DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")

    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )
}
~~~

A fuller block example:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "<spring-boot-version>"
    id("io.spring.dependency-management") version "<dependency-management-plugin-version>"
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Notes:

- `build.gradle` is Groovy DSL: `annotationProcessor 'group:artifact'`.
- `build.gradle.kts` is Kotlin DSL: `annotationProcessor("group:artifact")`.
- The declaration typically goes in the module **containing the `@ConfigurationProperties` source code**, not necessarily the module containing `main()` in a multi-module project.
- A Java project using a Kotlin DSL build file **does not mean the Java source code has been converted to Kotlin**. Here Kotlin is only the language of the build script.

### Gradle Compile Commands

Linux/macOS:

~~~bash
./gradlew clean classes
~~~

Windows:

~~~powershell
.\gradlew.bat clean classes
~~~

Gradle will compile the classes of the `main` source set. If Java annotation processing is enabled and the processor finds suitable configuration classes, metadata will be present in the compile output.

After building, look for:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

If the project has a different compile or output layout, check the `compileJava` task and the output location reported by Gradle instead of assuming every project must share the exact same path.

## 7. Why Should You Not Just Use `implementation` for the Processor in Gradle?

Two configurations look similar but serve different purposes:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

and:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

In modern Gradle, processors must be on the **annotation processor path** to run properly during `compileJava`. Putting the artifact in `implementation` is not the dedicated way to declare it and may fail to trigger annotation processing as expected.

Furthermore, `implementation` describes a library that application code depends on at compile time and that may be present on the runtime classpath. That does not match the purpose of the configuration processor: the application **does not need it to bind configuration at runtime**.

Comparison table:

| Gradle configuration | Main purpose | Suitable for configuration processor? |
| --- | --- | --- |
| `implementation` | Libraries used by application code | Not the recommended choice |
| `compileOnly` | Present at compile time, absent at runtime | Not sufficient to ensure the processor runs |
| `annotationProcessor` | Processors invoked by the compiler during Java compilation | **Yes** |
| `runtimeOnly` | Libraries needed at runtime but not at compile time | No |
| `testAnnotationProcessor` | Processors for Java test sources | Only when test source set annotations need processing |

Do not add both `implementation` and `annotationProcessor` for the same processor without a specific technical reason. Usually, `annotationProcessor` alone is all you need.

## 8. Maven: The Common `optional` Dependency Declaration

In projects using Maven and the Spring Boot parent or BOM for dependency management, a concise common approach is:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-configuration-processor</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

Maven's `optional=true` means this dependency is not automatically pulled in as a **transitive dependency** when another project depends on the current module. This is a reasonable choice for a build-time tool.

However, understand accurately:

- `optional=true` **is not** a "disable at runtime" directive in every packaging mechanism.
- `optional=true` **does not automatically enable** annotation processing if the build environment has disabled processors.
- For projects using an explicit processor path, you may need to put the processor on a separate path via the Maven Compiler Plugin.
- When configuring `annotationProcessorPaths`, processors omitted from that list may not be discovered by the Maven Compiler Plugin as they were with earlier classpath discovery mechanisms.

Therefore, **declaring an optional dependency** and **configuring the compiler processor path** are two approaches that can complement or substitute for one another depending on the build; avoid adding redundant configurations merely by copying from different tutorials.

## 9. Maven: `pom.xml` Example Using the Spring Boot Parent

A minimal POM for a Java/Spring Boot project can start with:

~~~xml
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

    <groupId>com.example</groupId>
    <artifactId>config-metadata-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Version note:** `3.3.13` here is an **example from the Spring Boot 3.3 line**, not a recommendation to use that exact version for a new project. In real work, keep the Boot version decided by the project and use compatible components, especially when the system already has a parent, BOM, or custom dependency management configuration.

Maven compile command:

~~~bash
mvn clean compile
~~~

In a build that supports normal annotation processor discovery, the compiler can load the processor from appropriate dependencies and generate metadata. However, on some newer Java toolchains or compiler configurations that restrict annotation processing, **a simple optional dependency does not guarantee processor execution**. When a reliable and explicit configuration is needed, use a processor path as shown in the next section.

## 10. Maven Compiler Plugin: Specifying the Annotation Processor Path

A more explicit way is to declare the processor in `maven-compiler-plugin`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-configuration-processor</artifactId>
                        <version>${spring.boot.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

In this snippet, `spring.boot.version` is a **self-declared property** or one provided by the project's build; it is not necessarily present automatically just because the application uses Spring Boot. Before using it, ensure the property has a value, for example:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring.boot.version>3.3.13</spring.boot.version>
</properties>
~~~

If the parent locks a different version, you must update `spring.boot.version` to match; avoid accidentally running the processor on a different version line than the Spring Boot version being compiled.

Meaning:

- `annotationProcessorPaths`: tells the compiler explicitly which artifacts are for annotation processing.
- `parameters=true`: retains parameter name info when compiling Java, helpful for constructor binding; **not an equivalent condition to generating metadata**.
- `spring-boot-configuration-processor` on the processor path: serves metadata generation.

With newer Maven Compiler Plugin versions, processor configuration may vary, such as dedicated dependency type mechanisms in newer plugin generations. This lesson presents the common `annotationProcessorPaths` syntax of Maven Compiler Plugin 3.x. Verify compatible configuration against the Maven plugin your project uses.

### When to Choose Optional Dependency vs. Explicit Processor Path?

- Traditional Spring Boot Maven projects where parent/BOM manages versions and annotation processing already works: declaring `optional` is usually the simplest step.
- Builds wanting to specify the exact processors invoked by the compiler: use `annotationProcessorPaths`.
- Builds that also use Lombok/MapStruct or other processors: use an explicit processor path, listing all necessary processors in the configuration.
- Builds using a JDK/toolchain where processor discovery is restricted: configure an explicit processor path and run compile to verify.

Do not delete existing annotation processor paths in the POM when adding the Spring Boot processor. If the plugin already has processor paths, **append the artifact to the list** rather than replacing the list with a single processor.

## 11. Gradle and Maven: Quick Comparison

| Aspect | Gradle | Maven |
| --- | --- | --- |
| Common build files | `build.gradle` / `build.gradle.kts` | `pom.xml` |
| Basic processor declaration | `annotationProcessor(...)` | Optional dependency or `annotationProcessorPaths` |
| Compile command | `./gradlew clean classes` | `mvn clean compile` |
| Common output | `build/classes/java/main/META-INF/...` | `target/classes/META-INF/...` |
| Where versions are managed | Plugin/BOM/platform/version catalog | Parent/BOM/dependency management/property |
| Build-time/runtime separation | `annotationProcessor` | Processor path or dependency and packaging policy |
| Processor for another module | Declared in the module containing the classes | Declared in the Maven module with those sources |
| Needs to start Spring Boot? | No | No |

Do not assume metadata is only generated if you run `bootRun` or `spring-boot:run`. Neither is the simplest way to verify annotation processing. Start with the **compile** task.

## 12. Inspecting the JSON File After Building

With Gradle:

~~~bash
./gradlew clean classes
~~~

With Maven:

~~~bash
mvn clean compile
~~~

Then check the corresponding output location.

Linux/macOS, Gradle example:

~~~bash
find build -name spring-configuration-metadata.json -print
~~~

Linux/macOS, Maven example:

~~~bash
find target -name spring-configuration-metadata.json -print
~~~

On PowerShell:

~~~powershell
Get-ChildItem -Path .\build -Recurse -Filter spring-configuration-metadata.json
Get-ChildItem -Path .\target -Recurse -Filter spring-configuration-metadata.json
~~~

Only run the command on the directory matching your build tool; a project does not necessarily have both `build` and `target`.

If the file is found, open it and verify the expected keys:

~~~json
{
  "name": "app.catalog-client.base-url",
  "type": "java.lang.String"
}
~~~

Actual metadata may include additional `sourceType`, `description`, or other properties. Do not directly edit generated files in `build/` or `target/` because the next compile can overwrite them.

### Inspecting Inside the JAR

After packaging:

~~~bash
./gradlew bootJar
~~~

or:

~~~bash
mvn package
~~~

You can use the JDK's `jar` tool to list files inside the archive:

~~~bash
jar tf path/to/application.jar
~~~

With a Spring Boot executable JAR, application classpath resources are typically placed under `BOOT-INF/classes/`, so you may see:

~~~text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
~~~

However, metadata may also reside inside the JAR of a **library module** that the application depends on. In that case, the artifact containing the `@ConfigurationProperties` source is the natural place to check metadata. Do not assume you must find a single metadata file at the root of the executable JAR.

## 13. How Do IDEs Use Metadata?

When an IDE or Spring extension supports reading metadata, developers can get assistance while typing:

~~~yaml
app:
  catalog-client:
    base-url: https://catalog.example.org
~~~

Examples of behaviors:

- Suggesting `app.catalog-client.base-url`.
- Suggesting `connect-timeout` when editing the `app.catalog-client` group.
- Displaying the type `java.time.Duration`.
- Displaying the property description if appropriate metadata exists.
- Warning on unknown properties or improper usage according to the tool's capabilities.
- Supporting enum suggestions or hints if metadata contains sufficient information.

However, having the JSON file **does not guarantee every IDE produces an identical list of suggestions**. Results also depend on IDE/plugin version, index cache, project import, module dependencies, and how the tool interprets metadata.

A workflow when autocomplete does not show up:

1. Rebuild the module containing `@ConfigurationProperties`.
2. Confirm the JSON metadata actually exists and contains the key.
3. Refresh/reimport the project in the IDE.
4. Check plugins supporting Spring/Spring Boot configuration.
5. Check whether the IDE recognizes the dependency between the module where YAML is edited and the module containing metadata.
6. Only then investigate the source class or processor further.

The key is to **check the build output first**, avoiding concluding that the processor failed to run just because an IDE temporarily has not updated suggestions.

## 14. Adding Javadoc for Useful Descriptions in Metadata

The processor can use information from source code, including certain Javadocs, to provide descriptions for configuration properties.

JavaBean example:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.catalog-client")
public class ClientProperties {

    /**
     * Base URL of the Catalog API.
     */
    private String baseUrl;

    /**
     * Maximum time to establish a connection.
     */
    private Duration connectTimeout = Duration.ofSeconds(3);

    /**
     * Maximum number of retries on transient errors.
     */
    private int maxRetries = 2;

    public String getBaseUrl() { return baseUrl; }
    public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }

    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

Metadata can contain descriptions corresponding to each property if the processor extracts them. For Java records, Javadoc for record components or parameter descriptions must follow the format supported by the processor/version.

Some notes:

- Descriptions should explain **operational meaning and units**, rather than just repeating the Java field name.
- If a property is `Duration`, specify whether it is connection time, response read time, or shutdown wait time.
- If a property is `boolean`, explain what `true`/`false` states do.
- If there is a default, clearly describe the default source and applicability.
- Do not put secrets or sensitive internal info into metadata descriptions.

For example, the description "Maximum number of retries on transient errors" is more helpful than "maxRetries property".

## 15. Does Metadata Automatically Infer Defaults?

The processor can determine certain default values from field initializers or configuration info it understands, but **not every runtime default can be inferred at compile time**.

Simple example:

~~~java
private int maxRetries = 3;
~~~

The processor can place default `3` into metadata.

However, some cases are difficult or impossible to infer statically:

~~~java
private Duration timeout = calculateTimeout();
~~~

~~~java
public ClientProperties(Environment environment) {
    this.timeout = environment.getProperty(
            "app.client.timeout", Duration.class, Duration.ofSeconds(5));
}
~~~

Or defaults that depend on profiles, environment variables, configuration outside the JAR, other beans, or runtime logic.

Therefore:

- `defaultValue` in metadata is **descriptive information to assist tooling**.
- The actual value is still decided by the Binder based on property sources and runtime defaults.
- An IDE showing a default does not mean that is guaranteed to be the production value.

If metadata omits a default you know exists in code, do not rush to edit the generated JSON; first verify whether that default falls under cases the processor can detect statically.

## 16. The Annotation Processor Is Not Bean Validation

Suppose the record is:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @Min(1) @Max(32) int threadCount
) {}
~~~

There are three distinct roles:

1. `spring-boot-configuration-processor` generates metadata for tooling during compilation.
2. Spring Boot Binder creates `WorkerProperties` from configuration when the application runs.
3. Bean Validation checks `@Min(1)` and `@Max(32)` when validation is enabled and an appropriate provider is present.

To make validation run, the commonly used dependency is:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

Or Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

This is a **different** dependency from `spring-boot-configuration-processor`.

Having the processor does not mean `@Min` constraints will automatically run. Having a Bean Validation provider does not mean the metadata file will be generated. Do not use one dependency in place of the other.

## 17. The Annotation Processor Does Not Automatically Register `@ConfigurationProperties` Beans

Example:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl) {}
~~~

Adding the Gradle dependency:

~~~groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
~~~

can help generate metadata about `app.client.base-url`, but **does not automatically create the `ClientProperties` bean**.

For Spring to use the class as a configuration bean, an appropriate registration mechanism is needed. For example:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {}
~~~

Or:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {}
~~~

There are also cases where JavaBean `@ConfigurationProperties` is bound when the bean is created via `@Bean`, whereas immutable constructor binding has its own rules. The annotation processor does not resolve binding style selection or bean registration for you.

If the application reports an error that the configuration bean cannot be found, do not immediately conclude "missing configuration processor". Check scanning, packages, registration, and constructor binding first.

## 18. Maven and Lombok: Two Processors May Need to Run Together

Many projects use **Lombok** to generate getters, setters, and constructors:

~~~java
import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Getter
@Setter
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private String baseUrl;
    private int maxRetries;
}
~~~

At the same time, the Spring Boot configuration processor needs to inspect the configuration model to generate metadata. Because Lombok can modify the class structure during annotation processing, **the interaction order between processors** can affect property detection.

Maven Compiler Plugin example with declared processor paths:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.projectlombok</groupId>
                        <artifactId>lombok</artifactId>
                        <version>${lombok.version}</version>
                    </path>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-configuration-processor</artifactId>
                        <version>${spring.boot.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

The `lombok.version` and `spring.boot.version` properties must have compatible values in the POM/effective build; this is a **configuration template**, not a standalone runnable POM when properties are missing.

When Lombok is used, it is generally necessary to ensure Lombok is processed before the configuration processor extracts information. Listing Lombok first in the configuration is a common way to organize it, but **do not treat XML text order as absolute proof** that every Java compiler/plugin enforces the exact desired order. Run the actual build and verify that metadata contains all properties whose accessors are generated by Lombok.

One way to avoid depending on complex getter/setter generation mechanisms is to use **Java records** for data-only configuration groups:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        int maxRetries
) {}
~~~

Records are often easier to read and provide clearer component info to the processor than relying on a series of code-generation annotations.

## 19. Gradle and Lombok: Dependencies Should Be Declared Separately

With Gradle Groovy DSL:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

With Gradle Kotlin DSL:

~~~kotlin
dependencies {
    compileOnly("org.projectlombok:lombok")
    annotationProcessor("org.projectlombok:lombok")

    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

Here:

- `compileOnly` allows Java source to use Lombok annotations during compilation.
- `annotationProcessor 'lombok'` enables Lombok to process annotations.
- `annotationProcessor 'spring-boot-configuration-processor'` enables Spring Boot to generate metadata.

If Gradle does not yet manage the Lombok version via a BOM or other configuration, you must supply an appropriate version. Do not blindly copy these three lines into a project that already uses a Lombok plugin or convention plugin, as it may already configure processor paths.

When metadata is missing properties from a Lombok-annotated class:

1. Verify Lombok works and the code compiles properly.
2. Verify the Spring processor is present on the compile annotation processor path.
3. Run a clean compile to eliminate stale results.
4. Read the actual JSON and compare expected keys.
5. If needed, adjust how Lombok/processors are declared per recommendations for your build tool version.
6. Consider converting simple configuration classes to records or explicit getters/setters.

## 20. Do Not Use `-parameters` to Replace the Processor

Some projects must preserve constructor parameter names to support constructor binding for `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        String baseUrl,
        int maxConnections
) {}
~~~

For ordinary Java classes, the compiler flag:

~~~text
-parameters
~~~

helps store constructor parameter names in bytecode so the Binder can determine property names.

Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

However:

- `-parameters` helps **retain parameter names for reflection/binding** when needed.
- `spring-boot-configuration-processor` helps **generate JSON metadata for IDEs**.
- The two mechanisms do not replace each other.

A project may bind constructors properly yet lack metadata because the processor is missing. A project can also generate metadata yet fail binding due to missing parameter names or incorrect registration/constructors.

## 21. Maven Projects Not Using the Spring Boot Parent

Some projects do not inherit `spring-boot-starter-parent` and instead use a BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring.boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

In that case, you need to provide `spring.boot.version` in the `properties` section or from an appropriate build config, and ensure Maven plugins have suitable versions/customizations because a BOM **manages dependencies** but does not completely replace the parent in managing plugins.

With a standard dependency declaration:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

dependency management can supply the artifact version.

However, with `maven-compiler-plugin` and `annotationProcessorPaths`, version inference from `dependencyManagement` depends on the Maven Compiler Plugin version and corresponding resolution mechanisms. For examples to work clearly on plugin 3.x, declaring an explicit version in the processor path via a defined property is straightforward:

~~~xml
<path>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <version>${spring.boot.version}</version>
</path>
~~~

Do not hardcode a processor version out of sync with the BOM just because an older tutorial used a different version.

## 22. Multi-Module Gradle Projects: Declaring in the Right Module

Suppose the project is:

~~~text
settings.gradle
build.gradle
config-model/
  build.gradle
  src/main/java/.../ClientProperties.java
application/
  build.gradle
  src/main/java/.../DemoApplication.java
~~~

If `ClientProperties` resides in the `config-model` module, the processor must be configured for the compile task of **that module**.

Example `config-model/build.gradle`:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.springframework.boot:spring-boot'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

This is an illustrative configuration. A real module needs an appropriate version management mechanism; without a BOM/platform, the `spring-boot` and processor dependencies need explicit versions.

Application module:

~~~groovy
dependencies {
    implementation project(':config-model')
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

If you only place `annotationProcessor` in the `application` module while `@ConfigurationProperties` classes to be processed reside in `config-model`, metadata might not appear in the source module's artifact.

Rule:

> The processor must participate in **the compilation where source code carrying `@ConfigurationProperties` is compiled**.

The same applies to multi-module Maven: add the dependency/processor path in the module containing the configuration classes, or configure inheritance appropriately in the parent POM of the relevant modules.

## 23. Metadata in Libraries Reused Across Multiple Applications

A custom starter library or shared module can expose:

~~~java
@ConfigurationProperties(prefix = "acme.payment")
public record PaymentProperties(
        String endpoint,
        int maxRetries
) {}
~~~

If the library generates metadata inside its own JAR, IDEs of dependent applications can read this metadata, depending on IDE capabilities and how dependencies are imported.

This is a major benefit: **metadata is not only useful in the final application**; it also makes libraries with customizable configuration easier to use.

Distinguish:

- Metadata describes `acme.payment.endpoint` and `acme.payment.max-retries`.
- Auto-configuration or an appropriate bean registration mechanism is what actually creates/conditions beans at runtime.
- Packaging metadata inside a library does not automatically make the library a complete Spring Boot starter.
- A property having metadata does not mean it always works in every application; runtime may depend on beans/auto-configuration or specific conditions.

For public libraries, descriptions and hints in metadata should be treated as part of the configuration API experience.

## 24. `additional-spring-configuration-metadata.json` to Supplement Information

There is information the processor cannot fully infer automatically, such as a property whose valid values belong to a list defined outside source code or needing extra descriptions/hints.

Spring Boot supports an additional file:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Example:

~~~json
{
  "properties": [
    {
      "name": "app.catalog-client.base-url",
      "type": "java.lang.String",
      "description": "Base URL used to call the Catalog service."
    }
  ],
  "hints": [
    {
      "name": "app.catalog-client.mode",
      "values": [
        {
          "value": "sandbox",
          "description": "Use the testing environment."
        },
        {
          "value": "production",
          "description": "Use the live environment."
        }
      ]
    }
  ]
}
~~~

Roles:

- `spring-configuration-metadata.json` is usually an **auto-generated file** in the build output.
- `additional-spring-configuration-metadata.json` is a **source file** managed by the project, used to add or adjust metadata info according to Spring Boot's supported format.
- When the build is configured appropriately, additional metadata can be merged with generated metadata for IDEs to use.

Do not edit generated files in `build/classes` or `target/classes` directly. To add descriptions, use Javadoc and/or additional metadata in the right place.

### Gradle Note on Task Ordering

In certain Gradle setups, Java compile tasks and resource processing tasks have an ordering that affects when the processor sees the additional metadata file. If you need to **merge** additional metadata into the auto-generated JSON at compile time, ensure the task preparing the additional metadata file has completed before the processor runs.

Do not arbitrarily alter the project-wide task graph without signs of an error. First inspect the output JSON and check documentation corresponding to your Gradle/Spring Boot version.

## 25. Metadata Differs from `spring.factories` and Auto-Configuration Imports

Filenames in the `META-INF` directory can confuse beginners:

~~~text
META-INF/spring-configuration-metadata.json
META-INF/additional-spring-configuration-metadata.json
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

They do not serve the same function.

- **Configuration metadata JSON:** helps IDEs/tooling understand properties.
- **Additional configuration metadata JSON:** supplements metadata information.
- **`spring.factories`:** a historical factory/extension registration mechanism in the Spring ecosystem, serving a purpose different from metadata.
- **`AutoConfiguration.imports`:** resource used to list auto-configurations in relevant Spring Boot versions.

Do not try to manually put `@ConfigurationProperties` classes into `spring-configuration-metadata.json` expecting Spring Boot to create beans automatically. This file is not a bean registration list.

If you build a starter, understand clearly that **publishing metadata for IDEs** and **runtime auto-configuration** are two independent yet complementary tasks.

## 26. When Does the Processor Fail to Generate Sufficient Metadata?

Typical scenarios:

1. The class lacks `@ConfigurationProperties`, or the annotation is placed somewhere unsupported by the processor.
2. Source code handles properties dynamically such that the processor cannot determine a static schema.
3. The class uses JavaBean binding but lacks proper accessor information.
4. The class uses Lombok, yet annotation processing or processor ordering is not working properly.
5. The annotation processor was only added to another module, not the module containing the source.
6. The build only ran tasks that did not compile the changed module.
7. Build cache or stale output has not been updated.
8. The compiler plugin disabled annotation processing via options like `-proc:none`.
9. Versions of the processor, Boot, and toolchain are incompatible.
10. The IDE has not reloaded the module or indexed the generated metadata file.

With constructor binding, records, nested classes, maps/lists, and complex generic types, the processor's descriptive capabilities also depend on how those Java constructs are detected and version support limits.

Not every property has to exist in metadata for the Binder to run. If a property is missing, determine whether it is a statically analyzable member before treating it as a build error.

## 27. Distinguishing the Compiler Processor from Runtime Property Sources

How build tools obtain metadata:

~~~text
Java source @ConfigurationProperties
             │
             ▼
Annotation processor
             │
             ▼
spring-configuration-metadata.json
~~~

How the running application receives values:

~~~text
application.yml + env + CLI + ...
               │
               ▼
Environment / Config Data
               │
               ▼
ConfigurationProperties Binder
               │
               ▼
ClientProperties instance
~~~

Both paths may involve the same `ClientProperties` class, yet their purposes are completely different.

Example configuration:

~~~yaml
app:
  catalog-client:
    connect-timeout: 5s
~~~

Metadata may state that `connect-timeout` has type `Duration` and description "time to establish connection", while at runtime the app may receive `connect-timeout=2s` from a higher-precedence environment variable.

Metadata **does not store runtime effective values** and does not determine active profiles. It primarily provides static schema/documentation for tooling.

## 28. Ordered Diagnosis to Avoid Blind Build Tweaks

When the IDE does not suggest a custom property, proceed step by step.

### Step 1 — Check the Source Class

Ensure the annotation is correct:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl) {}
~~~

Do not confuse with:

~~~java
@Value("${app.client.base-url}")
private String baseUrl;
~~~

The configuration processor primarily handles `@ConfigurationProperties` models, and does not automatically generate full metadata for `@Value` variables scattered throughout code.

### Step 2 — Check Gradle/Maven Processor Declaration

Gradle:

~~~groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Or an explicit processor path if the build uses that mechanism.

### Step 3 — Clean Compile

~~~bash
./gradlew clean classes
~~~

or:

~~~bash
mvn clean compile
~~~

### Step 4 — Inspect the JSON File

Locate:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Open the file and check whether the `app.client.base-url` property appears.

### Step 5 — Distinguish Processor Not Running vs. Processor Running with Missing Fields

- **No JSON**: recheck processor path, compile task, Java toolchain, disabled annotation processing, or source set.
- **JSON exists but property missing**: recheck class structure, accessors, record components, Lombok, nested types, or inference limits.
- **JSON has all properties but IDE does not suggest**: refresh IDE, metadata support plugins, indexing, and module dependencies.
- **IDE suggests it but runtime does not bind**: check bean registration, prefix, property source precedence, and Java types. This is no longer a metadata issue.

### Step 6 — Do Not Modify Sources Outside the Needed Scope

In a large project, do not overhaul the entire plugin/BOM system just because one property is not suggested by the IDE. Prefer small changes, verify the build, and confirm output.

## 29. Common Errors and Fixes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Gradle build succeeds but no JSON | Missing `annotationProcessor` | Add processor to the right module |
| `implementation` present but processor does not run | Processor not on annotation processor path | Use `annotationProcessor` |
| Maven has optional dependency but no JSON | Annotation processing disabled/restricted, or compiler has not loaded processor | Configure explicit processor path and verify compile |
| Maven compiler has processor paths but missing metadata | Spring processor not added to paths list | Append the artifact instead of replacing the entire list |
| After enabling Lombok, metadata lacks fields | Processor cannot observe accessors/constructors after Lombok | Check both processors' config and clean compile |
| Metadata only exists in library module | Processor runs where classes are compiled | Check corresponding artifact/module |
| JSON file exists but IDE does not suggest | IDE has not indexed/reimported module | Reload/refresh and check IDE plugin |
| Metadata has key but runtime reports missing bean | Configuration properties not scanned/enabled | Use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` |
| Property has type but no description | Processor could not obtain Javadoc/hints | Add Javadoc or additional metadata |
| `defaultValue` missing in JSON | Default depends on runtime or processor cannot infer | Do not edit generated file directly; review how defaults are described |
| Using `@Value` without generating metadata | Not a `@ConfigurationProperties` model for processor to describe | Group configs into `@ConfigurationProperties` types when suitable |
| Added `-parameters` yet still no JSON | `-parameters` does not trigger configuration processor | Declare processor separately |
| JAR includes processor as runtime dependency | Dependency scope/configuration inappropriate | Place on separate processor path |
| Processor version mismatches Spring Boot | Version hardcoded or BOM/parent mismanaged | Align version with project's Boot version |
| Edited JSON in `build/` then lost it | File is build output | Edit source/Javadoc/additional metadata and rebuild |

## 30. A Small Experiment with Gradle

Suppose the application only has:

~~~java
package com.example.demo;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.retry")
public record RetryProperties(
        int maxAttempts,
        Duration backoff
) {}
~~~

`build.gradle` needs the dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Run:

~~~bash
./gradlew clean classes
~~~

Check output:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

Under `properties`, expect names like:

~~~text
demo.retry.max-attempts
demo.retry.backoff
~~~

You can inspect via the IDE, terminal, or a small program reading JSON. There is no need to start the application just to observe these keys.

Try renaming a record component, for example `maxAttempts` to `attemptLimit`, and recompile. If the processor runs and the IDE has refreshed, the new metadata may describe:

~~~text
demo.retry.attempt-limit
~~~

This demonstrates that metadata originates from the **Java schema at compile time**, not from the set of keys that happen to appear in runtime YAML.

## 31. A Small Experiment with Maven

With the same `RetryProperties` record above, add in `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

If the build uses an explicit processor path, ensure the Spring processor is listed in `annotationProcessorPaths`.

Run:

~~~bash
mvn clean compile
~~~

Check:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

When metadata contains both `demo.retry.max-attempts` and `demo.retry.backoff`, the metadata compilation step is working for that class.

If the file does not appear, do not conclude that runtime binding is broken. Recheck the **effective POM**, Java compiler plugin, annotation processing status, and whether the class is actually compiled in the current module.

Some newer Java toolchains require explicit processor configuration rather than relying on classpath scanning, making an explicit processor path worth considering when older setups do not work.

## 32. Practice Exercises

### Exercise 1 — Choose Gradle Configuration

A `build.gradle` project currently only has:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter'
~~~

Add a dependency to generate configuration metadata.

**Answer:**

~~~groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
~~~

Choose `annotationProcessor` because the artifact needs to be invoked by the compiler at build time, not as a runtime library for the application.

### Exercise 2 — Kotlin DSL

Write the equivalent declaration in `build.gradle.kts`.

**Answer:**

~~~kotlin
annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
~~~

### Exercise 3 — Maven Dependency

A Spring Boot project uses a parent/BOM that already manages versions. Write the basic dependency configuration.

**Answer:**

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

If the build uses explicit processor paths or does not auto-discover processors, configure it accordingly on the compiler plugin.

### Exercise 4 — Distinguish Processor and Binder

An application has `@ConfigurationPropertiesScan` and properly binds `app.client.base-url`, yet the IDE does not autocomplete. What is the purpose of adding the processor?

**Answer:** to supplement metadata for development tools. The processor is not a required component for the runtime Binder to bind properties, and does not replace bean registration.

### Exercise 5 — Inspect Generated File

After running `mvn clean compile`, where do you find the JSON file?

**Answer:** typically `target/classes/META-INF/spring-configuration-metadata.json`. With Gradle Java compile, typically `build/classes/java/main/META-INF/spring-configuration-metadata.json`. In other build environments, search for the file by name in compilation output.

### Exercise 6 — What Does Optional Dependency Mean?

Does `<optional>true</optional>` in a POM mean the processor is guaranteed to be excluded from all runtime artifacts and guaranteed to be invoked by the compiler?

**Answer:** no. `optional` primarily controls transitivity of Maven dependencies. How the compiler discovers processors and how artifacts are packaged still depend on plugins/builds. To explicitly isolate the processor path, use appropriate compiler configuration.

### Exercise 7 — Lombok and Processor

A `@ConfigurationProperties` class uses Lombok to generate getters/setters, and Gradle only declares `compileOnly lombok`. What is missing?

**Suggested Answer:** Lombok is needed on `annotationProcessor` for it to execute; the Spring Boot configuration processor is also needed if metadata is desired. If metadata still misses fields, inspect the interaction and ordering of processors in the actual build.

### Exercise 8 — Multi-Module

`ClientProperties` is in module `config-model`, and `main()` is in module `application`. Does declaring the Spring processor only in module `application` guarantee generating metadata inside the `config-model` JAR?

**Answer:** no. The processor must participate in compiling the module containing the annotated source, namely `config-model`. Placing the processor only in the final application does not retroactively generate metadata for sources already compiled in another library.

### Exercise 9 — Metadata File Differs from Runtime Config

`spring-configuration-metadata.json` has entry `app.worker.thread-count`, but an environment variable sets `APP_WORKER_THREADCOUNT=10`. What does runtime choose?

**Answer:** metadata only describes property names and types. Runtime values are determined by Binder/PropertySource precedence. If the environment variable is the effective source and converts validly, `thread-count` can be 10; metadata does not lock the value.

### Exercise 10 — Need Additional Descriptions/Hints

The processor generates the name `app.client.mode`, but the IDE does not suggest the choices `sandbox` and `production`. How can this be added?

**Answer:** use the metadata hints mechanism in `additional-spring-configuration-metadata.json` or an appropriate type model such as an enum, then recompile and inspect metadata/IDE. Do not edit generated JSON directly in build output.

## 33. Project Application Checklist

Before marking metadata configuration complete, verify:

1. Clear `@ConfigurationProperties` classes/records with valid canonical prefixes.
2. Identify **the module that actually compiles** the configuration classes.
3. For Gradle Java, add `spring-boot-configuration-processor` to `annotationProcessor`.
4. For Maven, declare the processor via an optional dependency or processor path appropriate for the compiler plugin/toolchain.
5. Align the processor version with the Spring Boot version used by the project.
6. If using Lombok/MapStruct, check all required processors and their interactions.
7. Run clean compile.
8. Locate `META-INF/spring-configuration-metadata.json` in the module's output.
9. Verify at least one custom property name appears in the JSON.
10. If descriptions or hints are missing, add Javadoc or appropriate additional metadata.
11. Reimport/refresh the IDE when the JSON file exists but autocomplete has not updated.
12. Verify runtime beans are registered separately; do not equate metadata with binder/validation/auto-configuration.
13. Do not place sensitive data in metadata descriptions or unnecessary literal defaults.
14. For library modules, verify metadata is packaged inside that module's own artifact.
15. Use the same workflow on CI to catch builds failing to generate expected metadata.

The checklist above represents technical steps for managing build tooling; it does not imply every configuration class must generate the same number of properties or every IDE must render the same UI.

## 34. Takeaways

- `spring-boot-configuration-processor` is a **compile-time annotation processor**, not the runtime Spring Boot Binder.
- Standard artifact: `org.springframework.boot:spring-boot-configuration-processor`.
- Generated file: **`META-INF/spring-configuration-metadata.json`**.
- **Gradle Groovy DSL:** `annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'`.
- **Gradle Kotlin DSL:** `annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")`.
- **Maven:** typically declared as a dependency with `<optional>true</optional>`; can be specified via `maven-compiler-plugin`/`annotationProcessorPaths` to control the compiler processor path.
- Maven's `optional` does not guarantee the processor runs or is definitely excluded from every runtime artifact.
- **Place the processor in the module containing `@ConfigurationProperties` classes**, especially in multi-module projects.
- If **Lombok** is present, configure both the Lombok processor and Spring Boot processor, then verify actual metadata.
- `-parameters` serves to retain constructor parameter names; it does not substitute for the annotation processor.
- Metadata aids IDE completion, descriptions, and hints; **it does not automatically register beans**, enable Bean Validation, or decide runtime property values.
- For additional descriptions/hints, use `additional-spring-configuration-metadata.json` and **do not edit generated files in `build/` or `target/`**.
- The most reliable verification is to **compile and read the JSON**, then test the IDE experience.

## References

- [Spring Boot Reference — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Spring Boot Reference — Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Gradle User Manual — Annotation Processing](https://docs.gradle.org/current/userguide/java_plugin.html#sec:java_compile_avoidance)
- [Apache Maven Compiler Plugin — Annotation Processor Paths](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
