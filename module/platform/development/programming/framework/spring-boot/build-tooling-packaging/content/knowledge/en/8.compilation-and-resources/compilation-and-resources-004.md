# Generating Configuration Metadata with spring-boot-configuration-processor

## 1. Learning Objectives

When a Spring Boot project defines custom configuration keys such as `demo.client.timeout` or `demo.client.retry.max-attempts`, IDEs assist developers far better when they know each key's **name, data type, description, suggested values, and deprecation status**. Spring Boot provides **`spring-boot-configuration-processor`** to generate this information from Java source code during compilation.

After this lesson, you will be able to:

- Explain how the annotation processor differs from **runtime value binding**.
- Configure `spring-boot-configuration-processor` for Maven and Gradle in a way suited to modern Java.
- Write `@ConfigurationProperties` classes readable by the processor, including JavaBeans and Java `record` types.
- Locate and inspect the generated **`META-INF/spring-configuration-metadata.json`** file.
- Use Javadoc to populate descriptions, and understand nested properties, data types, and default values.
- Add **`META-INF/additional-spring-configuration-metadata.json`** for details the processor cannot infer automatically.
- Verify metadata via build commands and artifact contents, and diagnose missing IDE configuration autocomplete.

**Scope:** Spring Boot 3.5.x, Java 17+; the primary artifact names and paths below are also used in recent Spring Boot lines, though compiler/plugin configurations should be verified against your actual release line. Complete examples in this lesson use **Spring Boot 3.5.16** for concrete Maven coordinates, without implying every project must use this exact version.

## 2. What Is Configuration Metadata and What Is It For?

**Configuration metadata** is a machine-readable document, usually JSON, describing configuration keys exposed by a library or application. Spring Boot and supported IDEs understand this format to provide key completion, type information, description tooltips, value hints, and warnings when deprecated properties are used.

Example custom application configuration:

~~~properties
demo.client.name=inventory
demo.client.timeout=5s
demo.client.retry.max-attempts=4
~~~

An IDE supporting Spring Boot metadata can suggest `demo.client.*` keys inside `application.properties` or `application.yml`, because the project ships a metadata file publishing those keys and types. Whether an IDE displays suggestions also depends on extensions/plugins, project import, and IDE caches; having metadata does not guarantee identical UX across every editor.

### 2.1. Three Components to Keep Distinct

| Component | When does it run? | What does it do? |
| --- | --- | --- |
| `@ConfigurationProperties` and Spring Boot Binder | Primarily when the Spring `ApplicationContext` starts/runs | Reads `Environment` and binds values into configuration objects |
| `spring-boot-configuration-processor` | **During Java compilation** | Analyzes source declarations/annotations and generates JSON metadata |
| IDEs or metadata-consuming tools | While editing, inspecting, or discovering configuration | Uses JSON for autocomplete and displaying descriptions/hints |

**The processor does not create Spring beans, bind values, load `application.properties` into the app, or perform validation.** The application still needs to register `@ConfigurationProperties` via `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or an appropriate bean mechanism. To validate data at runtime, use Bean Validation/validators and dedicated binding configuration.

Do not treat metadata as a runtime config file required for Spring Boot to function: the application can bind properties and run even if metadata is never generated, though IDEs and documentation consumers will lack assistance.

## 3. Compile-Time Processing Flow

~~~text
Java source:
  @ConfigurationProperties(prefix = "demo.client")
  class DemoClientProperties { ... }
                 |
                 | javac / Maven Compiler / Gradle JavaCompile
                 v
Spring Boot configuration annotation processor
  - detects annotated classes / factory methods
  - reads getters/setters or constructor components
  - infers key names, types, and Javadoc descriptions
  - attempts to infer simple default values
                 |
                 | optionally merges manually declared metadata
                 v
META-INF/spring-configuration-metadata.json
                 |
                 | placed in output classes and artifact JAR
                 v
IDEs / tools read metadata for completion and docs
~~~

The processor belongs to **Java annotation processing**. In Maven, the compiler plugin invokes it during `compile`; in Gradle, `compileJava` runs it when declared on the `annotationProcessor` path. **Do not confuse this processor with the Spring AOT processor or GraalVM native-image config**: those are different mechanisms with different outputs.

Sections that can appear in metadata include:

- **`groups`**: configuration groups, typically derived from prefixes.
- **`properties`**: full keys, data types, descriptions, source types, defaults, and deprecations when inferred.
- **`hints`**: suggested value lists or provider aids for IDEs.
- **`ignored`**: items excluded from metadata via manual declarations.

The official path tools look up on the classpath is **`META-INF/spring-configuration-metadata.json`**.

## 4. Configuring the Processor with Maven

### 4.1. Why Use annotationProcessorPaths?

Historically, some projects declared `spring-boot-configuration-processor` as a normal dependency with `<optional>true</optional>`. That approach relies on compiler/JDK classpath processor discovery and is not the clearest setup on modern Java. **Starting with JDK 23, `javac` does not automatically scan the classpath to run annotation processors unless the build enables it explicitly.** Therefore, configure the processor on the **annotation processor path** or via explicit compiler plugin processor settings, rather than hoping a regular dependency triggers it.

Per Spring Boot 3.5 documentation, with Maven use **Maven Compiler Plugin 3.12.0 or later** and declare the processor:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.0</version>
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
~~~

This snippet belongs inside **`pom.xml`** and is not a standalone POM file. If a parent POM or BOM already manages processor/plugin versions under your build setup, you can omit managed versions and verify the effective POM; pinning both versions in the example ensures artifact resolution works cleanly in the standalone demo.

**Note when using a custom Maven parent:** the `spring-boot-dependencies` BOM manages dependency versions, but importing the BOM **does not automatically import Maven plugin management from `spring-boot-starter-parent`**. Check your custom parent's configuration for Maven Compiler Plugin and `spring-boot-maven-plugin` to avoid missing or conflicting settings.

### 4.2. Do Not Make the Processor a Runtime Dependency

The processor is strictly for **build time**. When placed in `annotationProcessorPaths`, you do not need to also declare the processor as a `compile` or `runtime` dependency just to generate metadata. The presence of the JSON file in the JAR is a build output and does not require the processor on the runtime classpath.

If a legacy Maven project still uses an optional dependency, check the active Java version and compiler plugin; on newer JDKs, **adding only an optional dependency without enabling annotation processing can cause the JSON file not to appear**.

## 5. Configuring the Processor with Gradle

### 5.1. Gradle Groovy DSL

In a Gradle project using Spring Boot and Java, declare the processor on the **`annotationProcessor`** configuration of the module containing `@ConfigurationProperties`:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor:3.5.16'
}
~~~

If the project already has dependency management supplying versions to this configuration, `:3.5.16` may be omitted after verifying actual dependency resolution. The example pins the version explicitly because it targets the exact processor for Spring Boot 3.5.16.

### 5.2. Gradle Kotlin DSL

For `build.gradle.kts`:

~~~kotlin
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor:3.5.16")
}
~~~

`annotationProcessor` **differs from** `implementation` and `runtimeOnly`. Putting the processor in `implementation` alone does not ensure Gradle invokes it during compilation. In a multi-module build, declare the processor on **the module that compiles the configuration properties classes**, not just the main application runner module.

### 5.3. When Using additional-spring-configuration-metadata.json

If you provide an additional metadata file in `src/main/resources/META-INF/`, Spring Boot documentation recommends making `compileJava` take `processResources` outputs as inputs so the processor sees the manual metadata while compiling sources.

Gradle Groovy DSL:

~~~groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
~~~

Gradle Kotlin DSL:

~~~kotlin
tasks.named("compileJava") {
    inputs.files(tasks.named("processResources"))
}
~~~

The key point is **task ordering and data dependency**: the additional file must be available to the processor at compile time. If you do not use additional metadata, this task wiring is unnecessary. In projects with convention plugins or custom task graphs, verify it introduces no circular task dependencies.

Verification command:

~~~bash
./gradlew clean compileJava
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean compileJava
~~~

The output typically lands at `build/classes/java/main/META-INF/spring-configuration-metadata.json`; after packaging, verify the path inside the actual artifact. If your project uses Kotlin or another annotation-processing setup, check toolchain/plugin specifics instead of copying a Java-only snippet verbatim.

## 6. Complete Maven Example: Generating Metadata from a JavaBean

### 6.1. Structure

Create a Spring Initializr project: **Java**, **Maven**, **Spring Boot 3.5.16**, **Java 17**, packaging **JAR**. The example below uses `spring-boot-starter` and requires neither Spring Web nor a database.

~~~text
metadata-demo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/
└── src/
    └── main/
        ├── java/com/example/metadatademo/
        │   ├── MetadataDemoApplication.java
        │   └── DemoClientProperties.java
        └── resources/
            ├── application.properties
            └── META-INF/
                └── additional-spring-configuration-metadata.json
~~~

The additional file shown here will be added in section 9. If no manual supplements are needed yet, **do not create that file** at the start; the processor still generates metadata from Java sources.

### 6.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>metadata-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

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
                <version>3.14.0</version>
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
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The example uses the Boot starter parent for standard dependency management and executable packaging. If practicing in a repository that already has a corporate parent, do not add a second parent; take only the compiler processor configuration compatible with your existing POM while managing versions/plugins through the parent or module.

### 6.3. DemoClientProperties.java

Create `src/main/java/com/example/metadatademo/DemoClientProperties.java`:

~~~java
package com.example.metadatademo;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Configuration for connecting to the customer service.
 */
@ConfigurationProperties(prefix = "demo.client")
public class DemoClientProperties {

    /** Display name of the client. */
    private String name = "local-client";

    /** Timeout duration when waiting for a service response. */
    private Duration timeout = Duration.ofSeconds(2);

    /** Retry policy when calling the service. */
    private Retry retry = new Retry();

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public Retry getRetry() {
        return retry;
    }

    public void setRetry(Retry retry) {
        this.retry = retry;
    }

    public static class Retry {

        /** Maximum number of attempts. */
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

Key points:

- `@ConfigurationProperties(prefix = "demo.client")` defines the prefix for both the binder and the processor.
- **Getters/setters** form the JavaBean model read by the processor; the Java property `maxAttempts` becomes the canonical configuration key `max-attempts`.
- `Duration` is a type Spring Boot can convert from strings like `5s`; recording the type in metadata helps IDEs validate and assist values.
- `Retry` is a **static nested class**, treated by the processor as a subgroup; hence the expected key is `demo.client.retry.max-attempts`, not `demo.client.max-attempts`.
- Javadoc directly on fields supplies `description` text when the processor compiles this class's source. Write **plain text** and avoid Javadoc tags or HTML formatting that JSON metadata tools do not render.

The processor can infer simple default values like `name = "local-client"` or `maxAttempts = 3`. However, an expression such as `Duration.ofSeconds(2)` **should not be expected to turn into a JSON `defaultValue` automatically**: initializers involving method calls may need manual metadata. Having or omitting `defaultValue` in JSON does not change the object's actual runtime default.

### 6.4. MetadataDemoApplication.java

Create `src/main/java/com/example/metadatademo/MetadataDemoApplication.java`:

~~~java
package com.example.metadatademo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class MetadataDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showClientConfiguration(DemoClientProperties props) {
        return args -> System.out.println(
                "client=" + props.getName()
                + ", timeout=" + props.getTimeout()
                + ", attempts=" + props.getRetry().getMaxAttempts()
        );
    }
}
~~~

`@ConfigurationPropertiesScan` registers the properties class for **runtime binding**. It is separate from the annotation processor, even though both read `@ConfigurationProperties`. The `ApplicationRunner` bean merely prints bound values for verification and is not required to generate metadata.

### 6.5. application.properties

Create `src/main/resources/application.properties`:

~~~properties
demo.client.name=inventory
demo.client.timeout=5s
demo.client.retry.max-attempts=4
~~~

When the application runs successfully, the binder reads these keys and populates `DemoClientProperties`. Java's `Duration.ofSeconds(5).toString()` returns `PT5S`, so the runner prints the **exact** line:

~~~text
client=inventory, timeout=PT5S, attempts=4
~~~

Spring Boot also prints startup logs depending on the environment, so predict only **the line emitted by the runner**, not the entire stdout. Because the app omits `spring-boot-starter-web`, it needs no HTTP server or port 8080.

### 6.6. Building, Generating JSON, and Running

Linux/macOS at the project root:

~~~bash
./mvnw clean compile
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd clean compile
.\mvnw.cmd spring-boot:run
~~~

If the project lacks a Maven Wrapper, use a preinstalled Maven via `mvn clean compile` and `mvn spring-boot:run`, provided Maven and JDK versions are compatible. During `compile`, the Maven Compiler Plugin invokes the Spring Boot annotation processor configured in `pom.xml`.

After compiling, locate the file:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

On Linux/macOS:

~~~bash
cat target/classes/META-INF/spring-configuration-metadata.json
~~~

On PowerShell:

~~~powershell
Get-Content .\target\classes\META-INF\spring-configuration-metadata.json
~~~

`cat`/`Get-Content` simply prints the file. If the file is missing, consult the troubleshooting section at the end rather than assuming runtime binding is broken.

## 7. What Does Generated Metadata Look Like?

Below is an **illustrative simplified model**, not a fixed byte-for-byte compiler output: actual output may include additional fields such as `sourceType`, `defaultValue`, `description`, and different ordering depending on the processor version.

~~~json
{
  "groups": [
    {
      "name": "demo.client",
      "type": "com.example.metadatademo.DemoClientProperties"
    },
    {
      "name": "demo.client.retry",
      "type": "com.example.metadatademo.DemoClientProperties$Retry"
    }
  ],
  "properties": [
    {
      "name": "demo.client.name",
      "type": "java.lang.String",
      "description": "Display name of the client."
    },
    {
      "name": "demo.client.timeout",
      "type": "java.time.Duration",
      "description": "Timeout duration when waiting for a service response."
    },
    {
      "name": "demo.client.retry.max-attempts",
      "type": "java.lang.Integer",
      "description": "Maximum number of attempts."
    }
  ]
}
~~~

**Do not copy this mocked JSON file to replace the generated one**. Let the processor generate the real output and inspect the actual file with the commands from section 6.6; manual additions have their own file as shown in section 9.

Field meanings:

| Field | Purpose |
| --- | --- |
| `groups[].name` | Prefix/group containing related properties |
| `properties[].name` | Full canonical configuration key (typically kebab-case) |
| `properties[].type` | Java type helping IDEs validate and suggest values |
| `properties[].description` | Explanatory text, typically sourced from Javadoc |
| `properties[].defaultValue` | Default value **if inferred by the processor or declared manually** |
| `properties[].deprecation` | Deprecation details when declared/detected |
| `hints[]` | Value suggestions or providers assisting IDE input |

The metadata file does not control precedence between `application.yml`, environment variables, and command-line arguments. Property source resolution and relaxed binding belong to Spring Boot runtime.

## 8. Java Records, Nested Properties, and Inference Limits

### 8.1. Immutable Configuration via Java Record

Since Java 17, you can use a `record` as an immutable configuration model. Below is an **alternative illustrative source class**; do not declare the same `demo.client` prefix as the earlier JavaBean example in the same application unless intentionally sharing a namespace.

Create `MailProperties.java` in package `com.example.metadatademo` inside a Spring Boot project:

~~~java
package com.example.metadatademo;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Mail system configuration.
 *
 * @param sender sender email address.
 * @param retryCount number of retry attempts.
 */
@ConfigurationProperties(prefix = "demo.mail")
public record MailProperties(String sender, int retryCount) {
}
~~~

With `@ConfigurationPropertiesScan` (or `@EnableConfigurationProperties(MailProperties.class)`), runtime binds via the record's constructor. The processor inspects record components to generate keys such as `demo.mail.sender` and `demo.mail.retry-count`. **To document record components**, place `@param` tags in class-level Javadoc as shown, rather than on instance fields (records do not declare mutable JavaBean fields).

In Spring Boot 3.x, a record with a single canonical constructor generally does not require `@ConstructorBinding`. If a class has multiple or specialized constructors, consult the constructor-selection and processor rules for your specific Boot version.

### 8.2. Nested Classes and @NestedConfigurationProperty

The processor automatically recognizes **inner/nested classes** like `Retry` in our example and emits a sub-prefix. If a property uses a separate standalone class defined elsewhere, annotate the field/component with `@NestedConfigurationProperty` to **signal to the processor** that it represents nested metadata.

Illustrative field inside a `@ConfigurationProperties` class:

~~~java
import org.springframework.boot.context.properties.NestedConfigurationProperty;

@NestedConfigurationProperty
private RemoteOptions remote;
~~~

This is a **field snippet**, not a standalone Java class; it assumes `RemoteOptions` already exists. The annotation drives **metadata discovery**—it does not create beans and is not a runtime binder switch. For collections and maps, the processor follows specific rules; it typically describes a map/list as a single property rather than enumerating unbounded dynamic keys as individual JSON entries.

### 8.3. @Bean Methods Annotated with @ConfigurationProperties

The processor also recognizes `@ConfigurationProperties` on `@Bean` methods, commonly used when binding third-party library classes via a factory method:

~~~java
@Bean
@ConfigurationProperties(prefix = "vendor.connection")
VendorConnectionSettings vendorConnectionSettings() {
    return new VendorConnectionSettings();
}
~~~

This is a **snippet inside a `@Configuration` class**, requiring a compatible return type/method and a bindable bean. If `VendorConnectionSettings` comes from a compiled dependency whose sources are unavailable to the processor in this module, some descriptions or defaults may not be inferred. Manual metadata can fill those gaps. User-defined custom annotations **meta-annotated** with `@ConfigurationProperties` are not automatically recognized by the processor per Spring Boot 3.5 documentation.

### 8.4. Why Might defaultValue Be Missing?

The processor uses static heuristics to read initializers from source code. Do not expect it to evaluate arbitrary Java expressions, read constants from other classes, or infer defaults for every `List`/`Map`. For example:

~~~java
private Duration timeout = Duration.ofSeconds(2);
~~~

Runtime genuinely defaults to `PT2S`, yet the processor may omit `defaultValue`. This is a compile-time inference limitation, not a bug in the Spring binder. When accurate defaults are needed for IDE display, use `additional-spring-configuration-metadata.json`.

## 9. Adding Manual Metadata and Hints

### 9.1. Why Add a Manual Metadata File?

Three common cases arise:

1. A property is read directly via `@Value` or `Environment.getProperty(...)` without a `@ConfigurationProperties` class for the processor to analyze.
2. The processor detects a property but lacks a `description`, cannot infer `defaultValue`, or lacks deprecation info.
3. You want IDEs to suggest **specific values** when a user types the property.

Create the file at the exact path:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

When the processor runs, the contents of the additional file are **merged into the generated metadata**. The additional file does not replace the generated `spring-configuration-metadata.json`. When a property name matches an already-discovered entry, declared fields such as `description`, `defaultValue`, and `deprecation` can override processor-inferred details; undiscovered properties are added as new entries.

### 9.2. Complete Additional JSON Example

~~~json
{
  "properties": [
    {
      "name": "demo.client.timeout",
      "description": "Client connection timeout limit.",
      "defaultValue": "PT2S"
    },
    {
      "name": "demo.feature-toggle",
      "type": "java.lang.Boolean",
      "description": "Enables an optional feature read by the app via Environment.",
      "defaultValue": false
    }
  ],
  "hints": [
    {
      "name": "demo.client.name",
      "values": [
        {
          "value": "inventory",
          "description": "Client calling the inventory service."
        },
        {
          "value": "orders",
          "description": "Client calling the orders service."
        }
      ]
    }
  ]
}
~~~

Explanation:

- `demo.client.timeout` was already discovered from the JavaBean; manual metadata adds **`defaultValue` `"PT2S"`**, which the processor may not infer from `Duration.ofSeconds(2)`.
- `demo.feature-toggle` is an **illustrative** key that the application could read via `Environment` or `@Value`. The JSON only documents the key; **it does not cause the application to read or use it**.
- `hints` provide **suggestions** (`inventory` and `orders`) to IDEs without preventing users from entering other names. Enforcing valid values requires actual binding/validation logic.

**Never store secrets, passwords, or tokens in metadata**: the JSON file is packaged inside the artifact and can be read by consumers of the library. Include only non-sensitive descriptions, hints, and defaults.

### 9.3. Deprecated Properties and Metadata

When renaming a property, you may want to flag the old key as deprecated and point to its replacement, for example:

~~~json
{
  "properties": [
    {
      "name": "demo.client.old-name",
      "type": "java.lang.String",
      "description": "Legacy client name.",
      "deprecation": {
        "level": "warning",
        "reason": "Use the new key name to unify configuration.",
        "replacement": "demo.client.name"
      }
    }
  ]
}
~~~

This JSON is an **illustrative standalone manual declaration**; you can place the `properties` item inside your active additional JSON file. It **only produces warnings/documentation in metadata** and does not make Spring Boot automatically alias `demo.client.old-name` to `demo.client.name`. If runtime backward compatibility is required, your code/binder must actually support the old key. Recording `deprecation` in metadata does not replace migration logic.

Spring Boot also provides `@DeprecatedConfigurationProperty` on appropriate accessors so the processor emits deprecation metadata, though that annotation likewise creates no runtime alias and does not guarantee backward compatibility on its own.

## 10. Inspecting Metadata After Compile and Package

### 10.1. Maven

Linux/macOS:

~~~bash
./mvnw clean compile
./mvnw clean package
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd clean compile
.\mvnw.cmd clean package
~~~

The file generated at compile time is typically:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

When the Spring Boot Maven Plugin builds an executable JAR, application metadata sits under the archive's classes directory (typically `BOOT-INF/classes/META-INF/spring-configuration-metadata.json`). List entries:

~~~bash
jar tf target/metadata-demo-0.0.1-SNAPSHOT.jar
~~~

Search for `spring-configuration-metadata.json` in the output. The JAR filename in the example comes from the `artifactId`/`version` in section 6's POM; if your real project uses a different name, inspect the actual artifact in `target/`.

When building a **plain library JAR**, metadata sits at `META-INF/spring-configuration-metadata.json` at the root of the JAR (without `BOOT-INF/classes`). This is one reason to know **the actual artifact type** before checking paths.

### 10.2. Gradle

Linux/macOS:

~~~bash
./gradlew clean compileJava
./gradlew bootJar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean compileJava
.\gradlew.bat bootJar
~~~

`bootJar` requires the Spring Boot Gradle plugin. The intermediate file is typically at:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

Its path inside the executable JAR also follows the Spring Boot plugin layout. For a Gradle library module using `jar` instead of `bootJar`, inspect the plain JAR layout. In multi-module builds, inspect the output of **the module containing the `@ConfigurationProperties` source**, not just the root build directory.

### 10.3. Inspecting JSON Meaningfully

Do not merely check that the file exists. Open the JSON and verify:

- `groups` includes the `demo.client` prefix (when detected by the processor).
- `properties` includes `demo.client.name`, `demo.client.timeout`, and `demo.client.retry.max-attempts`.
- `description` fields match the source Javadoc, and manual `defaultValue` overrides take effect after adding additional metadata.
- `hints` were merged rather than skipped due to task ordering or caching.
- The final JSON file is packaged inside the artifact actually consumed by IDEs/dependents.

After reimporting/rebuilding the project in your IDE, open `application.properties` and test completion after typing `demo.client.`. If suggestions do not appear even though the JSON is valid, check your IDE's Spring tooling/plugins and reload the project/classpath before editing Java code.

## 11. Lombok and Multiple Annotation Processors

When a project uses **Lombok** to generate getters, setters, and constructors, whether the metadata processor sees the model can depend on **annotation processor execution order**. Spring Boot documentation specifies configuring Lombok to run before `spring-boot-configuration-processor`.

- **Maven:** check Maven Compiler Plugin's `annotationProcessorPaths` and `annotationProcessors` (or the equivalent mechanism for your plugin version) to ensure the right order.
- **Gradle:** declare processors via `annotationProcessor` and order/configure them per Spring Boot and Lombok documentation for your versions.

Gradle Groovy DSL example including both artifacts:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.42'
    annotationProcessor 'org.projectlombok:lombok:1.18.42'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor:3.5.16'
}
~~~

`1.18.42` is an **illustrative value**; check which Lombok release supports your project's JDK and compiler. Proper declaration order per the docs is necessary, though real builds are also affected by plugins and toolchains. If annotation processing runs twice (for example due to an AspectJ plugin sharing a compiler invocation), duplicate/overwritten outputs may occur; configure a single primary processing pipeline and ensure processors are not invoked redundantly.

Different build scripts and IDE integrations may use separate processor paths and Java compiler settings. Do not rely solely on "compiles in the IDE" if CI uses a different Gradle/Maven command and the JSON file disappears from the JAR.

## 12. Troubleshooting: Missing JSON or Missing IDE Autocomplete

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `spring-configuration-metadata.json` missing after `compile` | Processor not on annotation processor path, processing disabled, or compile task did not run | Check Maven Compiler Plugin/Gradle `annotationProcessor`; run clean compile and inspect logs |
| Java 23+ build succeeds without generating metadata | Relied on implicit classpath processor discovery, which changed | Declare the processor explicitly via `annotationProcessorPaths`/`annotationProcessor` |
| Maven cannot resolve `spring-boot-configuration-processor` | Wrong version, unmanaged by BOM/parent, or repository/proxy error | Check coordinates/version, repository access, and effective POM |
| JSON exists, but `demo.client.*` is missing | Class lacks `@ConfigurationProperties` or is not in the compiled sources | Verify annotation, module source paths, and compile outputs |
| JSON has name/type, but lacks description | Source lacks suitable Javadoc or type comes from a compiled dependency | Add plain Javadoc on source fields/params or add manual metadata |
| Missing `defaultValue` for `Duration` or collections | Processor does not evaluate complex initializers or external constants | Declare the default in the additional metadata file |
| Missing `retry.max-attempts` | Nested type not recognized or lacks matching getters/setters/mapping | Check nested class structure, accessors, and `@NestedConfigurationProperty` for external types |
| Additional hints do not appear | Wrong file path, invalid JSON, or build task does not feed resources before compile | Check `src/main/resources/META-INF`, `processResources` task ordering, clean rebuild |
| Lombok class has fields, but metadata misses properties | Lombok did not run before configuration processor or processor path is incomplete | Order processors properly, verify JDK/Lombok versions and build logs |
| Runtime still fails to bind even with complete metadata | `@ConfigurationProperties` bean not registered, wrong prefix, or config source issue | Add `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` and inspect property sources |
| IDE does not suggest keys even though JSON is valid | IDE has not imported/reloaded project, Spring support disabled, or stale index cache | Reload Maven/Gradle, verify plugins/extensions, and restart indexing |
| File exists in `target/classes`, missing in JAR | Packaging/resource filtering/exclusion or inspecting the wrong module | Run `jar tf`, check Gradle/Maven packaging plugin and actual output artifact |
| Metadata has hints, yet users can supply other values | `hints` are not validation | Apply Bean Validation, enum types, or a runtime validator |
| Metadata only appears after running the app | Confusing build phase with runtime, or compile task had not run properly | Check metadata right after `compile`; running the app is not required |

### Isolating Errors Across Four Layers

**Layer 1 — Source model:** verify `@ConfigurationProperties`, getters/setters or record constructor, prefix, and nested types. Only change source code if metadata cannot be inferred from the current definition.

**Layer 2 — Build/processor:** verify the exact processor artifact/version, compiler plugin/toolchain, `annotationProcessorPaths` or Gradle `annotationProcessor`, and a clean compile.

**Layer 3 — Output/artifact:** read `META-INF/spring-configuration-metadata.json` directly and verify whether additional metadata was merged and packaged.

**Layer 4 — IDE/runtime:** once JSON is verified, check IDE support and the runtime binder. Do not edit metadata to work around Spring bean registration or `Environment` precedence bugs.

## 13. Practice Exercises

**Exercise 1 — Generate metadata:** Create a Maven Java 17 Boot 3.5.x project with the processor; add `DemoClientProperties` from section 6 and run `./mvnw clean compile`. Locate the JSON file and list the three keys `demo.client.name`, `demo.client.timeout`, and `demo.client.retry.max-attempts`. Note which `defaultValue` entries the processor inferred automatically.

**Exercise 2 — Add a manual default:** Add `additional-spring-configuration-metadata.json` to publish a default of `PT2S` for `timeout`. Run a clean rebuild, read the JSON, and verify `defaultValue` on `demo.client.timeout` without altering the Java runtime value.

**Exercise 3 — Separate runtime from metadata:** Temporarily remove `@ConfigurationPropertiesScan` while keeping the processor. Check whether the metadata file is still generated and whether the app can still obtain `DemoClientProperties` as a bean. Then restore scanning. Explain the two independent pipelines.

**Exercise 4 — Record:** Create the `MailProperties` record using `@param` tags to document components. Check `demo.mail.sender` and `demo.mail.retry-count` in metadata. Explain why records do not need JavaBean setters.

**Exercise 5 — Packaging:** Build an executable JAR, run `jar tf`, and locate the metadata file within the archive layout. Explain why IDEs can use this metadata file even when the application is not running.

## 14. Completion Checklist

- [ ] `@ConfigurationProperties` class is declared and registered properly at runtime when binding is required.
- [ ] Maven/Gradle build includes `spring-boot-configuration-processor` on the **annotation processor path**, compatible with the JDK.
- [ ] Ran `clean compile` and located `META-INF/spring-configuration-metadata.json`.
- [ ] Metadata contains the expected prefixes, property names, types, descriptions, and nested keys.
- [ ] Clearly distinguish **compile-time metadata** from **runtime binding/validation**.
- [ ] For complex defaults/hints, the additional metadata file is at the right path and merged into the output.
- [ ] If using Lombok/AspectJ or Java 23+, verified processor ordering and execution path.
- [ ] Metadata file is packaged inside the expected JAR artifact, not just left in a temporary build folder.
- [ ] Tested IDE completion and checked IDE/plugins as needed without confusing IDE caches with runtime errors.
- [ ] Metadata contains no secrets and hints are not treated as validation.

## 15. Official Documentation

- Spring Boot 3.5 — Annotation Processor and automatic metadata: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/annotation-processor.html
- Spring Boot 3.5 — Configuration Metadata Format: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/format.html
- Spring Boot 3.5 — Providing Manual Hints: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/manual-hints.html
- Spring Boot 3.5 — Externalized Configuration and `@ConfigurationProperties`: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Maven Compiler Plugin — Compiler configuration and annotation processing: https://maven.apache.org/plugins/maven-compiler-plugin/
- Gradle — Java Plugin, annotationProcessor configuration: https://docs.gradle.org/current/userguide/java_plugin.html

**Expected outcome:** From your project's Java configuration classes, you can generate `spring-configuration-metadata.json` at compile time, supplement uninferred metadata, verify the file inside packaged artifacts, and explain why IDEs provide completion without changing Spring Boot's runtime binding mechanism.
