# Generating Metadata with spring-boot-configuration-processor

In a Spring Boot project with many `@ConfigurationProperties` classes, developers need to know which configuration keys are supported, what data type each key has, what their descriptions are, and what suggested values exist. Having to read every Java class just to know `app.mail.connect-timeout` or `app.storage.max-size` makes editing `application.yml` tedious and prone to typos.

The **`spring-boot-configuration-processor`** library solves this problem by running **annotation processing at compile time** and generating a JSON metadata file at the path:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Spring Boot support tools in IDEs can read this metadata to provide **key name suggestions, data types, descriptions, default values, and valid choices** when editing configuration files.

Most importantly: **metadata is not the mechanism that loads or binds configuration at runtime**. `@ConfigurationProperties` beans are still processed by the Spring Boot Binder through `Environment`. The configuration processor only assists developer tooling and documents configuration better.

This lesson uses Spring Boot 3.3.x and Java 21; it walks through declaring dependencies, creating configuration classes, compiling, reading the generated JSON, adding custom metadata, troubleshooting, and testing.

## 1. Distinguishing Configuration Metadata from Application Configuration

There are several concepts that are easy to confuse:

| Component | Purpose | Timing |
| --- | --- | --- |
| `application.yml` or `application.properties` | Supplies actual property values | When the application loads configuration |
| `@ConfigurationProperties` | Declares Java objects to bind properties by prefix | When Spring Boot creates configuration beans |
| `spring-boot-configuration-processor` | Analyzes configuration declarations and generates the JSON descriptor | During Java compilation |
| `spring-configuration-metadata.json` | Contains information supporting IDEs/documentation | Read by IDEs/build tools |
| `additional-spring-configuration-metadata.json` | Supplements information the processor cannot infer | Merged during metadata generation |

For example, a Java class declares:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String host, int port) {
}
~~~

`application.yml` supplies:

~~~yaml
app:
  mail:
    host: mail.example.org
    port: 2525
~~~

The configuration processor can generate property names like `app.mail.host` and `app.mail.port`. When the IDE reads the metadata, it can suggest those names.

However, metadata **does not hold secret deployment values** such as SMTP passwords or production tokens; and it must not be treated as a secret management system. Effective runtime values still come from PropertySources.

## 2. Why Use the Configuration Processor?

Common benefits:

- **Autocomplete:** The IDE suggests `app.mail.host` or `app.mail.connect-timeout` while writing `application.yml`.
- **Early typo detection:** Readers can notice that `app.mail.conect-timeout` is not in the described list.
- **Type display:** The IDE knows whether a property is `java.time.Duration`, `java.lang.String`, an enum, or a collection.
- **Inline descriptions:** Javadoc or manual metadata helps users understand what a key means.
- **Discoverability:** Operators and development teams can enumerate properties exposed by a module.
- **Shared library support:** If a Spring Boot library provides many customizable configurations, packaging metadata gives projects using the library better IDE suggestions.

These are **developer experience benefits**. Do not assume the processor makes the application run faster, automatically fixes misconfigurations, or guarantees every property is validated.

## 3. Adding the Dependency with Maven

If the project uses Maven and Spring Boot dependency management, add to `pom.xml`:

~~~xml
<dependencies>
    <!-- Usual application dependencies... -->

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-configuration-processor</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

`<optional>true</optional>` is commonly used to avoid forcing other projects to pull in the processor as an ordinary runtime/transitive dependency. It is a build tool, not a component that business services need to inject at runtime.

When using an appropriate Spring Boot parent/BOM, the dependency version is managed by Spring Boot. If the project does not use dependency management, you must supply a version compatible with the Boot version in use.

Try compiling:

~~~bash
./mvnw clean compile
~~~

On Windows PowerShell, you can run:

~~~powershell
.\mvnw.cmd clean compile
~~~

After compiling, view the generated metadata at:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

In some build configurations, intermediate files may reside elsewhere before being copied to output classes. Inspect the actual build output rather than assuming every project has the exact same directory layout.

### If Using maven-compiler-plugin with annotationProcessorPaths

Some projects configure a separate list of annotation processors:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-configuration-processor</artifactId>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

This is a guiding example; plugin/processor versions and version management mechanisms must match your project. If your build uses explicit `annotationProcessorPaths`, ensure the Spring Boot processor **is actually on the annotation processing path**. Simply adding a dependency in a way that is not picked up by the compiler can result in no metadata being generated.

Do not apply every Maven configuration style simultaneously just because you saw multiple examples online. Choose one processor management style suitable for your current Maven setup.

## 4. Adding the Dependency with Gradle Groovy DSL

For a Gradle project that already has the Java and Spring Boot plugins:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

The `annotationProcessor` configuration places the dependency on the **annotation processor path of the compileJava task**, matching the goal of generating metadata during compilation.

Run:

~~~bash
./gradlew clean compileJava
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean compileJava
~~~

The output directory typically looks like:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

The exact path may depend on Gradle or plugin configuration. When packaged as a Boot JAR, metadata may appear under:

~~~text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
~~~

### Gradle Kotlin DSL

If the project uses `build.gradle.kts`:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")

    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

The example above assumes dependency versions are managed by the project using an appropriate plugin/BOM. Otherwise, add a version matching the Spring Boot version.

### Distinguishing implementation and annotationProcessor

- `implementation`: Dependencies needed by Java code at compile time and runtime.
- `annotationProcessor`: Libraries that process annotations at compile time.
- `testAnnotationProcessor`: Processors dedicated to test code, only when needed.

For `spring-boot-configuration-processor`, declare it on the annotation processor path instead of putting it on the runtime classpath just for IDE hints. The processor does not need to be instantiated as a bean to work.

## 5. Creating a `@ConfigurationProperties` Record Analyzed by the Processor

Consider a notification-sending application. Create an enum:

~~~java
package com.example.notification.config;

public enum DeliveryChannel {
    EMAIL,
    SMS,
    WEBHOOK
}
~~~

Create the record:

~~~java
package com.example.notification.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * Application notification delivery settings.
 *
 * @param enabled whether sending notifications is enabled
 * @param channel default delivery channel
 * @param connectTimeout timeout waiting to connect to the provider
 * @param retry retry delivery configuration
 */
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("EMAIL") DeliveryChannel channel,
        @DefaultValue("3s") Duration connectTimeout,
        @DefaultValue Retry retry) {

    /**
     * Retry settings.
     *
     * @param maxAttempts maximum number of attempts
     * @param delay delay between attempts
     */
    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("200ms") Duration delay) {
    }
}
~~~

Expected property names include:

~~~text
app.notification.enabled
app.notification.channel
app.notification.connect-timeout
app.notification.retry.max-attempts
app.notification.retry.delay
~~~

Meaning:

- `prefix = "app.notification"` defines the root of the group.
- `enabled` is boolean.
- `channel` is the `DeliveryChannel` enum.
- `connectTimeout` is a `Duration`; its canonical config name is `connect-timeout`.
- `retry` is a nested record.
- `@DefaultValue` serves the Binder when a property is missing; the processor can represent appropriate default info in metadata depending on detection and version support.
- Javadoc provides useful descriptions for metadata/IDE when the processor can extract them according to the current code structure.

Example in `application.yml`:

~~~yaml
app:
  notification:
    channel: WEBHOOK
    connect-timeout: 5s
    retry:
      max-attempts: 5
      delay: 500ms
~~~

Values from the file are only **runtime configuration values**. The processor can generate metadata without running Spring Boot or reading production values from this file.

## 6. Registering the Configuration Properties Bean Is a Separate Step

A `@ConfigurationProperties` record needs to be registered by Spring Boot to be injectable as a bean.

Application class:

~~~java
package com.example.notification;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class NotificationApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotificationApplication.class, args);
    }
}
~~~

With the record located under the application package, `@ConfigurationPropertiesScan` finds and registers it.

An alternative:

~~~java
@EnableConfigurationProperties(NotificationProperties.class)
~~~

placed on an appropriate configuration class, importing `org.springframework.boot.context.properties.EnableConfigurationProperties`.

**Distinguish clearly:**

- `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`: helps create configuration properties beans when the application runs.
- `spring-boot-configuration-processor`: runs during compilation and creates JSON metadata.

Metadata can be generated for a class even if the current application has not registered that bean for use. Conversely, the application can still bind successfully without installing the processor, though it will lack processor-generated suggestion info.

## 7. Inspecting the Newly Generated Metadata

After adding the processor and compiling successfully, look for:

~~~text
META-INF/spring-configuration-metadata.json
~~~

in the classes output.

With Maven:

~~~bash
./mvnw clean compile
~~~

Then open:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

With Gradle:

~~~bash
./gradlew clean compileJava
~~~

Then inspect:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

**Illustrative** JSON structure example:

~~~json
{
  "groups": [
    {
      "name": "app.notification",
      "type": "com.example.notification.config.NotificationProperties",
      "sourceType": "com.example.notification.config.NotificationProperties"
    }
  ],
  "properties": [
    {
      "name": "app.notification.enabled",
      "type": "java.lang.Boolean",
      "description": "Whether sending notifications is enabled."
    },
    {
      "name": "app.notification.connect-timeout",
      "type": "java.time.Duration",
      "description": "Timeout waiting to connect to the provider."
    }
  ],
  "hints": []
}
~~~

This is an **abbreviated format example**, not a promise that the generated file will have exact matching fields or strings. The processor may output additional `sourceType`, `defaultValue`, deprecation info, multiple nested properties, and related metadata; actual values depend on the Java definition and processor version.

What you should verify is that names such as `app.notification.enabled` and `app.notification.connect-timeout` are recognized. If a key does not appear, check annotations, packages, structural types, compilation, and whether the processor actually executed.

### Inspecting the Boot JAR

For an application packaged as a Spring Boot executable JAR, metadata for application code is usually placed under the app's resource layer:

~~~text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
~~~

You can use:

~~~bash
jar tf build/libs/notification-app.jar
~~~

and search for paths named `spring-configuration-metadata.json`. The JAR filename is illustrative; replace it with the actual path produced by your build.

Runtime is not required to read this JSON for the Binder to work. IDEs or external tools use metadata as needed.

## 8. Metadata Format: groups, properties, and hints

A standard metadata file usually has three important arrays:

~~~json
{
  "groups": [],
  "properties": [],
  "hints": []
}
~~~

### 8.1. groups: Property Groups

A group describes a configuration prefix, for example:

~~~json
{
  "name": "app.notification",
  "type": "com.example.notification.config.NotificationProperties",
  "sourceType": "com.example.notification.config.NotificationProperties"
}
~~~

When a module has multiple classes annotated with `@ConfigurationProperties`, metadata may list multiple groups.

Groups can reflect a class and certain nested structures. Do not assume there is strictly one group per Java file.

### 8.2. properties: Individual Supported Properties

Example:

~~~json
{
  "name": "app.notification.connect-timeout",
  "type": "java.time.Duration",
  "description": "Timeout waiting to connect to the notification service.",
  "sourceType": "com.example.notification.config.NotificationProperties"
}
~~~

Information may include:

- `name`: canonical property name.
- `type`: Java type.
- `description`: helpful description for users.
- `sourceType` or `sourceMethod`: source declaration in code if available.
- `defaultValue`: default value when inferable.
- `deprecation`: info about an outdated key, possibly including a replacement.

Not every field is mandatory in each entry. If metadata lacks `description`, the IDE can still suggest the name and type without the explanation text.

### 8.3. hints: Value Suggestions and Providers

A hint can describe suggested values for a property name:

~~~json
{
  "name": "app.notification.channel",
  "values": [
    {
      "value": "EMAIL",
      "description": "Send via email."
    },
    {
      "value": "SMS",
      "description": "Send via SMS."
    },
    {
      "value": "WEBHOOK",
      "description": "Send via HTTP webhook."
    }
  ]
}
~~~

IDEs can use hints to suggest choices. For enum properties, tools and the processor can infer values from the enum type; however, manual metadata is useful when you want clear descriptions or when a property is a String with a list of proposed values.

**A hint is not necessarily runtime validation.** If the Java field is `String`, merely creating hints for `EMAIL`/`SMS` does not cause the Binder to reject other strings. To restrict runtime values, use an enum or appropriate validation.

## 9. Javadoc Helps Create Helpful Descriptions

Configuration metadata is easier to use when each property has a clear description of its meaning, units, and usage context.

Example with a JavaBean:

~~~java
package com.example.notification.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.gateway")
public class GatewayProperties {

    /** Timeout waiting to connect to the gateway. */
    private Duration connectTimeout = Duration.ofSeconds(3);

    /** System name displayed in logs and dashboards. */
    private String serviceName = "notification-service";

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public String getServiceName() {
        return serviceName;
    }

    public void setServiceName(String serviceName) {
        this.serviceName = serviceName;
    }
}
~~~

The processor can extract descriptions from Javadoc of appropriate fields/getters. For records, Javadoc on the record and corresponding `@param` tags clarify component meanings according to the mechanisms and versions supported by the processor.

Write descriptions focused on **business meaning**, rather than merely repeating the field name:

- Good: "Maximum time to wait when connecting to the gateway; use units such as 500ms or 3s."
- Less helpful: "Connect timeout of the gateway."

Do not put secrets, tokens, or sensitive operational data into Javadoc or metadata. Metadata can be packaged with artifacts and read by IDEs/tools of library consumers.

### Javadoc Should Not Carry Real Environment Values

If a default is only valid for local development, do not write descriptions like "Default password is secret123". Instead, state clearly that the property must be provided via the deployment environment's secret source and how required fields are validated.

## 10. Default Values in Metadata

Some defaults can be detected by the processor at compile time, such as simple field initializers or `@DefaultValue` in constructor binding when supported by the processor version.

Example:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("4") int concurrency,
        @DefaultValue("true") boolean enabled) {
}
~~~

Although metadata can describe defaults, the runtime mechanism remains:

- If the property exists, the Binder uses the effective value from the sources.
- If the property is absent, the Binder can use the appropriate `@DefaultValue`.
- Metadata **is not what decides runtime values**; do not manually put `defaultValue` in JSON just to make the application use a default.

Example of supplementing metadata:

~~~json
{
  "properties": [
    {
      "name": "app.worker.concurrency",
      "type": "java.lang.Integer",
      "description": "Number of configured workers.",
      "defaultValue": 4
    }
  ]
}
~~~

In JSON metadata, `defaultValue` is information for development tooling. It **does not automatically create** a default in the Binder if Java code or configuration sources do not supply a corresponding value.

Do not rely on generated metadata to determine the exact default of an expression with complex runtime logic, such as a default computed from CPU count, another bean, or system state. The compiler cannot infer every value only known when the application runs.

## 11. What Is additional-spring-configuration-metadata.json Used For?

Not every property is fully inferred by the processor from annotations. For example:

- A property read directly via `Environment.getProperty(...)`.
- A String configuration needing suggestions for supported values.
- Needing extra descriptions for properties where the processor has not produced a helpful description.
- Metadata needing `deprecation` or key rename information.

Spring Boot supports an additional file:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Create this JSON file in the project's source resources. For example:

~~~json
{
  "properties": [
    {
      "name": "app.notification.webhook-secret-ref",
      "type": "java.lang.String",
      "description": "Reference name to the webhook configuration secret, not the secret content itself."
    }
  ],
  "hints": [
    {
      "name": "app.notification.channel",
      "values": [
        {
          "value": "EMAIL",
          "description": "Send email."
        },
        {
          "value": "SMS",
          "description": "Send SMS message."
        },
        {
          "value": "WEBHOOK",
          "description": "Send HTTP webhook."
        }
      ]
    }
  ]
}
~~~

When the build runs the processor and detects the additional file, appropriate information is **merged with auto-generated metadata** into the result for development tools. For keys not discovered by the processor, the additional file ensures they still appear in metadata.

### Why Must It Be Placed at the Exact Path?

The filename and `META-INF` location have specific meaning. Do not name the additional file `additional-spring-configuration-metadata.yml` or place it in the root directory expecting the processor to pick it up automatically.

Create it with the exact name:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

and re-run compile. In custom builds, if resources are not present before the processor runs, you may need to check the resource processing task order so the processor reads the file at the right time.

### Do Not Use Additional Metadata to Declare Environment Values

For example:

~~~json
{
  "properties": [
    {
      "name": "app.payment.password",
      "defaultValue": "real-password"
    }
  ]
}
~~~

is neither a safe way to supply a password nor a way for Spring Boot to read the password at runtime. Metadata can be viewed by others and is not meant for secret management.

## 12. Providing Value Hints for String Properties

Suppose the application wants users to choose a provider:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(String provider) {
}
~~~

Because `provider` is a String, the IDE does not know for sure which values to suggest. You can create additional metadata:

~~~json
{
  "hints": [
    {
      "name": "app.payment.provider",
      "values": [
        {
          "value": "sandbox",
          "description": "Simulated provider used in development environments."
        },
        {
          "value": "internal",
          "description": "Internal provider."
        },
        {
          "value": "external",
          "description": "External provider."
        }
      ]
    }
  ]
}
~~~

When the user writes:

~~~yaml
app:
  payment:
    provider: sandbox
~~~

The IDE can suggest `sandbox`, `internal`, or `external`. However, if the code only has `String provider` with no validation, the Binder can still accept `other`.

If the set of values must genuinely be restricted, an enum is the clear choice:

~~~java
public enum PaymentProvider {
    SANDBOX,
    INTERNAL,
    EXTERNAL
}
~~~

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(PaymentProvider provider) {
}
~~~

Metadata assists development; **enum types and validation** are what ensure a valid runtime choice.

## 13. Value Providers and Advanced Suggestions

In metadata, `hints` can also contain `providers`, allowing IDEs to use dynamic suggestion mechanisms based on recognized value kinds.

Example of the data shape:

~~~json
{
  "hints": [
    {
      "name": "app.storage.directory",
      "providers": [
        {
          "name": "any"
        }
      ]
    }
  ]
}
~~~

This is just an example of provider syntax in metadata. Spring Boot defines several common providers/hints with their own parameters; IDE tools may support them partially, fully, or ignore them depending on capabilities.

**Do not invent provider names** without checking the metadata documentation for the version in use. For finite choices such as `sandbox`, `internal`, `external`, an explicit `values` list is usually simpler.

Metadata is not required to have `hints`. If a property already uses an enum, tools can rely on the type to offer suggestions.

## 14. Metadata for Nested Configuration Properties

Property groups often have multiple levels:

~~~yaml
app:
  mail:
    smtp:
      host: smtp.example.org
      port: 2525
    retry:
      max-attempts: 3
      backoff: 500ms
~~~

Record:

~~~java
package com.example.configdemo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        Smtp smtp,
        Retry retry) {

    public record Smtp(String host, int port) {
    }

    public record Retry(int maxAttempts, Duration backoff) {
    }
}
~~~

The processor can generate metadata for names such as:

~~~text
app.mail.smtp.host
app.mail.smtp.port
app.mail.retry.max-attempts
app.mail.retry.backoff
~~~

### When the Nested Type Is a Separate Class

For configuration classes that are not nested in their Java declaration, the processor may need guidance that a field with a custom type is **nested configuration**, rather than a scalar value. Spring Boot supports the annotation:

~~~java
import org.springframework.boot.context.properties.NestedConfigurationProperty;
~~~

Example on a JavaBean:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    @NestedConfigurationProperty
    private RetryProperties retry = new RetryProperties();

    public RetryProperties getRetry() {
        return retry;
    }

    public void setRetry(RetryProperties retry) {
        this.retry = retry;
    }
}
~~~

`RetryProperties` is another configuration class defined by the project, with appropriate getters/setters. The `@NestedConfigurationProperty` annotation **primarily supports the metadata model for nested properties**, and is not the sole condition determining whether the Binder can bind a nested object.

For inner types or ordinary nested types recognized by the processor, adding this annotation is not necessarily required. Use it when there is a clear reason and in accordance with Spring Boot's recommendations.

## 15. Metadata for `@ConfigurationProperties` from Shared Libraries

A library can define:

~~~java
@ConfigurationProperties(prefix = "acme.client")
public record AcmeClientProperties(
        String baseUrl,
        Duration timeout) {
}
~~~

and use the processor in the library module itself. When the library is compiled and packaged, metadata resides inside the JAR so dependent projects can receive IDE support for the `acme.client` prefix.

The library structure might look like:

~~~text
acme-client-spring-boot/
├── src/main/java/com/acme/client/AcmeClientProperties.java
├── src/main/resources/META-INF/additional-spring-configuration-metadata.json
└── build.gradle
~~~

After building:

~~~text
META-INF/spring-configuration-metadata.json
~~~

is packaged inside the resulting artifact.

This is why the annotation processor is useful not only for directly runnable applications. It holds great value for **starters**, configuration libraries, and modules reused across multiple projects.

### Metadata Does Not Automatically Register Library Beans

If a library only packages JSON metadata without Spring configuration registering `AcmeClientProperties`, the IDE may still suggest key names, while Spring Boot runtime might not have a bound bean.

The library needs an appropriate registration mechanism such as auto-configuration and `@EnableConfigurationProperties` in the relevant context. That is a separate runtime design concern, not the responsibility of the metadata processor.

## 16. Combining Lombok with the Configuration Processor

Some projects use Lombok to generate getters/setters or constructors:

~~~java
@Getter
@Setter
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private boolean enabled;
    private int maxEntries;
}
~~~

With the code above, most accessor methods may be generated by Lombok during annotation processing. If the Spring Boot configuration processor runs before Lombok provides the necessary information, metadata might be incomplete or fail to recognize the structure properly.

When using Lombok:

- Ensure both **Lombok** and the **Spring Boot configuration processor** are on the appropriate annotation processor path.
- Pay attention to processing order if required by the build tool/plugin, so Spring Boot's processor sees the structure generated by Lombok.
- Inspect the actual metadata file after compiling, rather than just checking whether the IDE recognizes getters/setters.
- With Java 21 and simple properties, records or classes with explicit accessors can reduce dependency on ordering across multiple processors.

Gradle Groovy DSL dependency-level example:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

This is an annotation processor path configuration example; versions must be managed appropriately for your project. Do not add Lombok if your code uses records and does not use Lombok.

## 17. Reasons Metadata Is Not Generated

### 17.1. Processor Not Added to the Compiler

Symptom: The application runs and binds `@ConfigurationProperties`, but `META-INF/spring-configuration-metadata.json` is missing after compiling.

Resolution: Check `pom.xml` or `build.gradle`, ensuring `spring-boot-configuration-processor` actually participates in annotation processing.

### 17.2. Not Recompiled After Changes

The processor runs at compile time. If you only save the Java file and open old metadata, the JSON might not be updated yet.

Resolution:

~~~bash
./mvnw clean compile
~~~

or:

~~~bash
./gradlew clean compileJava
~~~

and inspect the newly generated output file.

### 17.3. Annotation Processing Disabled in IDE/Build

If the compiler or IDE is configured to disable annotation processing, the processor will not run during that compilation.

Resolution: Check build and IDE annotation processing settings. Prioritize **reproducible CLI builds** first; the IDE may use the build tool or its own build mechanism.

### 17.4. Class Lacks Appropriate `@ConfigurationProperties`

Example:

~~~java
@Component
public class MailService {

    @Value("${app.mail.host}")
    private String host;
}
~~~

The processor does not automatically infer a complete **configuration properties group** from scattered `@Value` annotations. If you want good metadata for a configuration group, switch to `@ConfigurationProperties` or add manual metadata for keys that genuinely need suggestions.

### 17.5. Incorrect or Non-Standard Prefix

~~~java
@ConfigurationProperties(prefix = "app.notification")
~~~

differs from:

~~~yaml
app:
  notifications:
    enabled: true
~~~

Plural `notifications` and singular `notification` are two different prefixes. Metadata is generated from Java, and does not automatically fix a misspelled YAML key.

Use canonical lowercase kebab-case names, for example `app.notification.connect-timeout`.

### 17.6. Nested Structure Not Recognized

If a nested class is a separate Java type lacking guidance or required accessors, the processor may not infer child properties as expected. Consider `@NestedConfigurationProperty` when appropriate and check the actual JSON.

### 17.7. Lombok or Other Processors Affect Ordering

If accessors/constructors are generated at compile time, the Spring Boot processor must see the proper structure. Check the annotation processor path, processing order, and version compatibility.

### 17.8. Looking in the Wrong Output Location

With Maven it may be under `target/classes/META-INF`; with Gradle it is typically `build/classes/java/main/META-INF`. When packaged as a Boot executable JAR, application resources are usually under `BOOT-INF/classes/META-INF`. Do not look solely in `src/main/resources` and conclude metadata was not generated.

### 17.9. Invalid Additional Metadata JSON

If `additional-spring-configuration-metadata.json` has a trailing comma, mismatched brackets, or improper structure, the metadata merging process may fail or ignore data.

Check the JSON with a parser/linter, fix the `properties`/`hints` structure, and recompile.

### 17.10. IDE Has Not Updated Its Index

If the metadata file already exists but the IDE does not show suggestions:

- Check Spring Boot configuration metadata support in your IDE and installed plugins.
- Try re-syncing the project from Maven/Gradle.
- Check whether the module containing metadata is in the dependency path of the module where you are editing config.
- Check that the key being typed belongs to the actual metadata prefix.
- If needed, tell the IDE to reload the project/index according to your IDE's instructions.

Lack of autocomplete **is not enough to prove** the metadata file does not exist. Distinguish metadata build errors from errors where the IDE reads and displays metadata.

## 18. Metadata and Deprecated Properties

When renaming a public property, for instance moving from:

~~~text
app.mail.legacy-timeout
~~~

to:

~~~text
app.mail.connect-timeout
~~~

application or library users need to know that the old key is no longer recommended.

Configuration metadata can contain deprecation information:

~~~json
{
  "properties": [
    {
      "name": "app.mail.legacy-timeout",
      "type": "java.time.Duration",
      "description": "Legacy configuration name for connection timeout.",
      "deprecation": {
        "reason": "Renamed for clarity regarding connection.",
        "replacement": "app.mail.connect-timeout"
      }
    }
  ]
}
~~~

For a configuration properties class using JavaBean getters, Spring Boot provides `@DeprecatedConfigurationProperty` to supply deprecation details in appropriate cases, such as when the property has been marked deprecated.

**Note:** Deprecation metadata helps the IDE warn and suggest replacements; it does not automatically create a runtime alias from the old name to the new name. To continue supporting the old property at runtime, you must design compatibility and handle it explicitly in application code or appropriate binding logic.

Do not put both keys into metadata and assume the Binder automatically knows how to prioritize between them.

## 19. How to Systematically Inspect the Generated JSON File

A minimal sequence for a Java project:

1. Verify the class is annotated with `@ConfigurationProperties` using the right prefix.
2. Verify the processor dependency is in the build and placed on the annotation processor path.
3. Run a clean compile with Maven/Gradle.
4. Locate `META-INF/spring-configuration-metadata.json` in the classes output.
5. Open the JSON and check the expected group/property names.
6. If needed, add Javadoc or `additional-spring-configuration-metadata.json`.
7. Recompile and inspect the merged metadata.
8. Sync the IDE and test autocomplete in `application.yml`.

Example inspection using the JDK tool:

~~~bash
jar tf build/libs/notification-app.jar
~~~

Then search for `spring-configuration-metadata.json` in the JAR file listing.

Or view the JSON file directly with an editor or a file-reading script. To automate this in CI, you can write a test or script parsing the JSON to verify important properties appear without relying on an IDE.

### Distinguishing Metadata Checks from Binding Tests

Inspecting the JSON only proves the processor described the properties. To prove runtime can bind the configuration, write an `ApplicationContextRunner` test or an integration test with the corresponding `@EnableConfigurationProperties`.

These two checks complement each other, but neither replaces the other.

## 20. Testing Runtime with ApplicationContextRunner

Suppose the record is:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        boolean enabled,
        DeliveryChannel channel,
        Duration connectTimeout) {
}
~~~

A test:

~~~java
package com.example.notification;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import com.example.notification.config.DeliveryChannel;
import com.example.notification.config.NotificationProperties;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class NotificationPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BindingConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(NotificationProperties.class)
    static class BindingConfiguration {
    }

    @Test
    void bindsValuesFromEnvironment() {
        runner.withPropertyValues(
                "app.notification.enabled=true",
                "app.notification.channel=EMAIL",
                "app.notification.connect-timeout=5s")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    NotificationProperties properties =
                            context.getBean(NotificationProperties.class);

                    assertThat(properties.enabled()).isTrue();
                    assertThat(properties.channel())
                            .isEqualTo(DeliveryChannel.EMAIL);
                    assertThat(properties.connectTimeout())
                            .isEqualTo(Duration.ofSeconds(5));
                });
    }
}
~~~

The test assumes the project has `spring-boot-starter-test`, JUnit Jupiter, and AssertJ.

If you remove the processor dependency while keeping the runtime configuration and registration intact, the binding test can still pass. That is tangible proof that **the processor is not a runtime component of the Binder**.

Conversely, metadata may be generated completely while runtime fails to bind because the YAML file has the wrong prefix or the bean is unregistered. Always investigate the specific layer at fault.

## 21. Comparison Table of Related Annotations

| Annotation/Configuration | Purpose |
| --- | --- |
| `@ConfigurationProperties(prefix = "...")` | Declares a property group to bind and serves as a source for the processor |
| `@ConfigurationPropertiesScan` | Scans and registers configuration properties beans |
| `@EnableConfigurationProperties` | Explicitly registers specific configuration properties classes |
| `@DefaultValue` | Sets defaults for constructor/record parameters when the Binder does not find a property |
| `@NestedConfigurationProperty` | Assists the processor in describing nested properties in certain cases |
| `@DeprecatedConfigurationProperty` | Describes deprecated properties and replacements in metadata |
| `@Validated` | Enables Bean Validation checks for configuration properties |
| `@ConfigurationPropertiesBinding` | Registers converters dedicated to configuration binding |
| `annotationProcessor(...)` (Gradle) | Adds the processor to the `compileJava` process |
| `spring-boot-configuration-processor` | Tool that generates JSON metadata |

Do not use `@NestedConfigurationProperty` as a substitute for `@NotNull`/validation. Also, do not treat `@DeprecatedConfigurationProperty` as a tool that automatically renames keys at runtime.

## 22. Organizing Metadata for Large Modules

Suppose a project has three configuration groups:

~~~text
app.mail.*
app.storage.*
app.payment.*
~~~

You can create three separate classes:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(...) {}

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(...) {}

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(...) {}
~~~

The processor will process classes with appropriate annotations and generate the corresponding metadata in the output.

A source structure:

~~~text
src/main/
├── java/com/example/config/
│   ├── MailProperties.java
│   ├── StorageProperties.java
│   └── PaymentProperties.java
└── resources/
    ├── application.yml
    └── META-INF/
        └── additional-spring-configuration-metadata.json
~~~

You do not need a separate `additional-spring-configuration-metadata.json` file for each class. The module's additional file can describe multiple properties and hints, while the processor aggregates information for the classes within the module.

Place descriptions close to the Java source whenever possible; only put details into the additional JSON that cannot be conveniently expressed via annotations/Javadoc, such as hint values for Strings or dynamic properties.

## 23. Common Misconceptions

### "Installing the processor automatically enables `@ConfigurationProperties`"

False. The processor only generates metadata at compile time. To have a configuration bean at runtime, you must register it via an appropriate Spring Boot mechanism.

### "Without the processor, Spring Boot cannot read `application.yml`"

False. Spring Boot still reads Config Data and the Binder can still bind values into configuration objects. Only development-support metadata is missing.

### "Metadata is where default values are declared for the application"

Not quite. Metadata can describe `defaultValue` for tooling, but it is not a runtime source for the Binder to use automatically. Put defaults in Java (`@DefaultValue`, field initializers) or configuration as designed.

### "Every `@Value` will be listed automatically by the processor"

No. The processor mainly relies on the `@ConfigurationProperties` structure and has limitations regarding discovering manually read properties. For keys that need supplementing, create `additional-spring-configuration-metadata.json`.

### "If the IDE suggests it, the key is definitely valid at runtime"

No. Hints can exist for Strings without validation; prefixes might vary by profile; properties can be overridden by other sources. Metadata does not verify runtime state.

### "Adding deprecation metadata automatically maps the old key to the new key"

No. This is information for IDEs/tools. Runtime compatibility logic must be built separately if needed.

### "The processor must be included in the runtime JAR to work"

No. The processor runs during compilation. The metadata file can be packaged for IDEs or other tools to read; the runtime Binder does not need the processor itself.

## 24. Practice Exercises

### Exercise 1 — Add the Processor Dependency

For a Spring Boot Maven project, add `spring-boot-configuration-processor` with `optional=true`. Run `./mvnw clean compile` and locate `target/classes/META-INF/spring-configuration-metadata.json`.

If using Gradle, place the dependency in the `annotationProcessor` configuration and run `./gradlew clean compileJava`.

### Exercise 2 — Generate Metadata for a Record

Create:

~~~java
@ConfigurationProperties(prefix = "demo.worker")
public record WorkerProperties(
        @DefaultValue("4") int concurrency,
        @DefaultValue("true") boolean enabled) {
}
~~~

Compile and find the `demo.worker.concurrency` and `demo.worker.enabled` properties in the JSON.

### Exercise 3 — Write Javadoc for a Property

Create a JavaBean `@ConfigurationProperties(prefix="demo.cache")` with a `Duration ttl` field and Javadoc describing "Maximum time to live for a cache entry". Compile and locate the description of `demo.cache.ttl` in metadata.

### Exercise 4 — Add Hints for a String

A `demo.export.format` property of type String supports `csv`, `json`, `xml`. Write `additional-spring-configuration-metadata.json` with `hints` containing those three values and short descriptions. Recompile and inspect the output JSON.

### Exercise 5 — Nested Properties

Create a `DemoMailProperties(Smtp smtp)` record with a nested `Smtp(host,port)`. Verify the metadata contains `demo.mail.smtp.host` and `demo.mail.smtp.port`.

### Exercise 6 — Distinguish Metadata from Runtime

Create a valid `@ConfigurationProperties` class, compile to get metadata, but intentionally do not register the class in the Spring context. Explain why the JSON file can still contain properties while injecting the bean at runtime may fail.

### Exercise 7 — Troubleshooting Missing Autocomplete

After compiling, the JSON file already contains `demo.worker.concurrency`, yet the IDE does not suggest it. Check the Spring Boot plugin, module import, Maven/Gradle sync, and IDE cache/index instead of randomly changing annotations.

### Exercise 8 — Deprecated Property

An old configuration API `demo.mail.legacy-timeout` is replaced by `demo.mail.connect-timeout`. Create deprecation metadata with `replacement` and explain why that does not automatically provide a runtime alias.

### Exercise 9 — Testing Property Name Typos

The record expects `demo.worker.concurrency`, but YAML has `demo.worker.concurency`. Explain the difference between IDE autocomplete warnings, actual binding errors, and required validation.

### Exercise 10 — Distinguish Configuration Values from Value Hints

Metadata hints for `demo.export.format` list `csv` and `json`. If the Java field is String, will the Binder automatically reject `txt`? **Answer:** not just because of the hint; an enum or validation is needed to restrict values.

## 25. Summary

`spring-boot-configuration-processor` is a **compile-time annotation processing** tool to generate `META-INF/spring-configuration-metadata.json` from configuration declarations in Java code. Metadata helps IDEs suggest key names, types, descriptions, defaults, and hints, making it very useful for Spring Boot applications and libraries with many `@ConfigurationProperties`.

With Maven, add the appropriate processor dependency and ensure the Maven Compiler runs annotation processing. With Gradle, use the `annotationProcessor` configuration. After compiling, inspect the JSON file in the classes output or artifact and supplement with `src/main/resources/META-INF/additional-spring-configuration-metadata.json` when hints/info cannot be inferred automatically.

**Keep the two responsibilities separate:** the processor generates metadata to support tooling; the Spring Boot Binder along with configuration properties registration and validation determine configuration behavior at runtime.

## References

- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Spring Boot 3.3 — Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html)
- [Spring Boot 3.3 — Metadata Format](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html)
- [Spring Boot 3.3 — Manual Hints](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/manual-hints.html)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
