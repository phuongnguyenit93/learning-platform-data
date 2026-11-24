# Inspecting Metadata in JARs and Distinguishing Metadata from Runtime Validation

## 1. Lesson Objectives

Spring Boot provides **Externalized Configuration** so configuration values are not hardcoded in Java code. With `@ConfigurationProperties`, keys like `gateway.connect-timeout` or `gateway.max-attempts` are bound into a typed configuration object.

As a project grows, another need emerges: authors writing `application.yml` want the IDE to **suggest exact property names**, show what type a property has, explain what it is used for, state any default value, and indicate whether it has been marked deprecated.

Spring Boot addresses most of this tooling need via **configuration metadata** — usually packaged in the file:

```text
META-INF/spring-configuration-metadata.json
```

Metadata can be generated at compile time from `@ConfigurationProperties` classes via `spring-boot-configuration-processor`, and can also be supplemented with manual metadata.

The most important takeaway of this lesson is **not to confuse metadata with runtime validation checks**:

- **Metadata** describes configuration so tools like IDEs support suggestions, documentation, and warnings.
- **Binder** actually reads property sources, converts types, and constructs `@ConfigurationProperties` beans while the application runs.
- **Validation** checks required constraints, numeric bounds, formats, or business invariants.
- A key's presence in metadata JSON **does not create that key in Spring Environment**, does not guarantee an actual value exists, and does not cause the application to reject every mistyped key.

After this lesson, you will be able to read metadata inside JARs, determine which module generated specific metadata, explain the difference between IDE suggestions and startup failures, and build an example testing both aspects.

## 2. A Practical Example

Suppose an application has the configuration:

```yaml
# src/main/resources/application.yml
gateway:
  base-url: "https://gateway.example.invalid"
  connect-timeout: 5s
  max-attempts: 3
  enabled: true
```

Corresponding Java class:

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxAttempts,
        boolean enabled) {
}
```

There are two completely different questions:

1. When a user types `gateway.connect-` in the IDE, how does the IDE know `gateway.connect-timeout` exists?
2. When a user writes `gateway.connect-timeout=wrong` and runs the application, who catches that `wrong` cannot become a `Duration`?

**Question 1 relates to configuration metadata and IDE capabilities. Question 2 relates to runtime configuration binding/conversion.**

If you add a `@Min(1)` constraint on `maxAttempts`, the value `-3` can be converted to `int` and then rejected by **Bean Validation**. That is yet another mechanism distinct from having JSON metadata.

## 3. What Is Configuration Metadata?

Configuration metadata is structured data, usually in JSON format, describing a module's configuration groups and properties.

A metadata file can contain three important arrays:

```json
{
  "groups": [],
  "properties": [],
  "hints": []
}
```

General meaning:

| Component | Role |
| --- | --- |
| `groups` | Describes property groups or configuration prefixes |
| `properties` | Describes specific configuration keys, data types, descriptions, defaults... |
| `hints` | Suggests valid values or input guidance for a property |

Not every metadata file contains all fields or all three arrays. Contents depend on source code, the annotation processor, additional metadata, and the build process.

An illustration:

```json
{
  "groups": [
    {
      "name": "gateway",
      "type": "com.example.configdemo.GatewayProperties",
      "sourceType": "com.example.configdemo.GatewayProperties"
    }
  ],
  "properties": [
    {
      "name": "gateway.base-url",
      "type": "java.net.URI",
      "sourceType": "com.example.configdemo.GatewayProperties",
      "description": "Gateway service address."
    },
    {
      "name": "gateway.connect-timeout",
      "type": "java.time.Duration",
      "sourceType": "com.example.configdemo.GatewayProperties",
      "description": "Timeout waiting to connect to the gateway."
    },
    {
      "name": "gateway.max-attempts",
      "type": "java.lang.Integer",
      "sourceType": "com.example.configdemo.GatewayProperties",
      "description": "Maximum number of attempts."
    }
  ],
  "hints": []
}
```

This is a **structure-illustrative example**, not a guarantee of the exact JSON fields a specific annotation processor version will emit. Some auto-generated metadata may omit `description` if Java code does not supply enough info to infer descriptions.

## 4. Distinguishing Name, Type, Description, and Default Value

Inside `properties` elements, you may see fields:

- `name`: canonical configuration key, such as `gateway.connect-timeout`.
- `type`: corresponding Java type name, such as `java.time.Duration`.
- `description`: text helping readers understand the property's meaning.
- `sourceType`: Java type that declared or created the property.
- `sourceMethod`: source method information in applicable cases.
- `defaultValue`: default value described by metadata, if determinable.
- `deprecation`: info indicating an outdated property should no longer be used, if applicable.

Example:

```json
{
  "name": "gateway.connect-timeout",
  "type": "java.time.Duration",
  "description": "Timeout waiting to connect to the gateway.",
  "defaultValue": "5s"
}
```

**Critically important:** the `defaultValue` field in JSON is **descriptive information**, not a directive forcing the runtime binder to use `5s` as the default.

For runtime to actually have a default, the application must supply it via a supported mechanism, such as:

```yaml
gateway:
  connect-timeout: 5s
```

or for constructor binding:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        @DefaultValue("5s") Duration connectTimeout) {
}
```

Changing JSON metadata alone without changing configuration sources or binding logic **does not necessarily make runtime receive that value**.

Similarly, the description `"Must be greater than 0"` is only documentation; enforcing it requires Bean Validation or constructor checks.

## 5. Generating Metadata with `spring-boot-configuration-processor`

Spring Boot provides the **annotation processor** tool:

```text
org.springframework.boot:spring-boot-configuration-processor
```

This tool analyzes configuration classes and creates metadata **during compilation**, not while the application is serving requests.

A high-level workflow:

```text
Java source:
  @ConfigurationProperties(prefix="gateway")
                     |
                     v
        Java annotation processing
                     |
          spring-boot-configuration-processor
                     |
                     v
   META-INF/spring-configuration-metadata.json
                     |
                     v
                 JAR
                     |
                     v
           IDE / developer tooling
```

Different workflow from:

```text
application.yml + environment + CLI
                     |
                     v
              Runtime Binder
                     |
                     v
          GatewayProperties bean
```

The same `GatewayProperties` class can participate in both paths, yet build-time metadata generation and runtime binding are two distinct stages.

### 5.1. Declaring with Maven

In a Spring Boot project using Maven, you can configure:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

This is common for projects following Spring Boot dependency management. In customized builds, annotation processing may be configured via `maven-compiler-plugin` and `annotationProcessorPaths`.

Because compiler plugin behavior, Java versions, and processor management vary, verify annotation processing is genuinely enabled in your active build rather than assuming adding the dependency to `pom.xml` always suffices in every setup.

Build:

```bash
./mvnw clean package
```

Or if the project has no Maven Wrapper:

```bash
mvn clean package
```

In a standard Maven build, the module's metadata may appear at:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

If missing, check whether the `@ConfigurationProperties` class is compiled in this module and whether the processor ran.

### 5.2. Declaring with Gradle

In Gradle Groovy DSL:

```groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
```

When using the Spring Boot plugin and proper dependency management, the processor version can be managed alongside the Boot version.

Build:

```bash
./gradlew clean build
```

Or if only building an executable JAR:

```bash
./gradlew bootJar
```

Build paths depend on Gradle version and configuration. Metadata generated by Java annotation processing typically sits in the module's class/resource output and gets packaged into the JAR when packaged properly.

If the project uses Kotlin, KAPT, or KSP and other processor setups, declaring the processor is not necessarily identical to Java's `annotationProcessor`. Follow the build configuration appropriate for your language and tooling.

## 6. Writing a `ConfigurationProperties` Class to Generate Metadata

A Java example using a record:

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        URI baseUrl,
        @DefaultValue("5s") Duration connectTimeout,
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("true") boolean enabled) {
}
```

When built with the processor, metadata can describe the keys:

```text
gateway.base-url
gateway.connect-timeout
gateway.max-attempts
gateway.enabled
```

CamelCase Java property names like `connectTimeout` are represented using canonical kebab-case configuration names like `connect-timeout`.

The processor helps the IDE know the expected data types. For example:

- `gateway.base-url` has type `URI`.
- `gateway.connect-timeout` has type `Duration`.
- `gateway.max-attempts` is an integer type.
- `gateway.enabled` is a Boolean type.

A good description also matters: type `Duration` says the value is a duration, but not **which stage's connection wait time to which system**. Appropriate Javadoc or additional metadata can be added to explain business meaning.

### 6.1. Having `@ConfigurationProperties` Does Not Guarantee JSON

Simply adding:

```java
@ConfigurationProperties(prefix = "gateway")
```

to Java code does not guarantee a metadata file is created. The annotation processor must actually run during compilation.

That does not mean the annotation stops working at runtime: **configuration binding can still work when metadata is not generated**, as long as the class is registered and other configuration binding conditions are met.

Therefore, when the IDE does not suggest properties while the app runs fine, inspect the processor and output JAR before concluding Spring Boot cannot read configuration.

## 7. Inspecting Processor Output Before Packaging

After a Maven build, inspect the file:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

On Linux/macOS:

```bash
ls -l target/classes/META-INF/spring-configuration-metadata.json
cat target/classes/META-INF/spring-configuration-metadata.json
```

With PowerShell:

```powershell
Get-Item .\target\classes\META-INF\spring-configuration-metadata.json
Get-Content .\target\classes\META-INF\spring-configuration-metadata.json -Raw
```

With Gradle, the exact path may differ, for example a path inside `build/classes/java/main/META-INF/`.

At this step, you are checking **the module's compilation output**, which is not necessarily the final contents inside the deployed JAR.

A metadata file present in the build directory yet excluded from packaging, or a stale JAR that was not rebuilt, can both cause the release artifact to lack the expected information.

## 8. Inspecting Metadata in a Regular JAR

A standard Java library JAR may have the structure:

```text
my-config-library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── spring-configuration-metadata.json
└── com/
    └── example/
        └── config/
            └── GatewayProperties.class
```

Use the JDK's `jar` tool to list entries inside:

```bash
jar tf my-config-library.jar
```

Search specifically for metadata on Linux/macOS:

```bash
jar tf my-config-library.jar | grep 'spring-configuration-metadata.json'
```

On PowerShell:

```powershell
jar tf .\my-config-library.jar |
    Select-String 'spring-configuration-metadata\.json'
```

In a regular library JAR, the path is typically:

```text
META-INF/spring-configuration-metadata.json
```

If the path is present, inspect the JSON contents rather than just checking the filename. An empty file, a file missing property groups, or a file from an older version may fail to provide expected IDE suggestions.

`jar tf` only **lists entries**; it does not verify that the JSON adheres to the schema or reflects current source code.

## 9. Inspecting Metadata in a Spring Boot Executable JAR

An application packaged by the Maven/Gradle Spring Boot plugin usually produces an **executable JAR** whose layout differs from a standard library JAR.

Illustration:

```text
my-app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/configdemo/...
    │   ├── application.yml
    │   └── META-INF/
    │       └── spring-configuration-metadata.json
    └── lib/
        ├── spring-boot-....jar
        ├── spring-boot-autoconfigure-....jar
        └── other-dependency.jar
```

Therefore, metadata generated by the **application module** usually resides at:

```text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

Inspection command:

```bash
jar tf target/my-app.jar | grep 'spring-configuration-metadata.json'
```

On PowerShell:

```powershell
jar tf .\target\my-app.jar |
    Select-String 'spring-configuration-metadata\.json'
```

To read the contents directly if `unzip` is installed:

```bash
unzip -p target/my-app.jar \
  BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

This prints the entry's contents to stdout without extracting the entire JAR. The path must match **the exact entry name** reported by `jar tf`.

Without `unzip`, you can use `jar xf` inside a temporary directory to extract the specific entry and open it with a JSON viewer; avoid extracting into the project source directory where existing files risk being overwritten.

### 9.1. Why Do Library JARs and Boot JARs Have Different Paths?

For regular Java libraries, classes and resources usually sit at the root of the JAR.

For Boot executable JARs, application classes/resources usually reside in `BOOT-INF/classes/`, while dependency JARs sit in `BOOT-INF/lib/`.

This layout explains why searching strictly for root `META-INF/spring-configuration-metadata.json` may miss application metadata when it actually lives under `BOOT-INF/classes/META-INF/`.

Do not treat every Spring Boot distribution format identically — there can be plain JARs, executable JARs, WARs, layered JARs, or custom layouts. Use `jar tf` to observe the artifact's actual structure.

## 10. Metadata Residing Inside Dependency JARs

An application may depend on a library:

```text
acme-client-spring-boot-starter.jar
```

That library exposes keys:

```text
acme.client.endpoint
acme.client.timeout
acme.client.retries
```

Metadata for those keys may live inside the **dependency JAR**, not in the application module's own metadata.

In a Boot executable JAR, dependencies are typically packaged under:

```text
BOOT-INF/lib/acme-client-spring-boot-starter.jar
```

**Important detail:** `jar tf my-app.jar` lists entries of the **outer JAR**, including dependency JAR filenames. It **does not automatically recurse into nested JARs** to list metadata at each dependency's root.

Therefore, if `jar tf my-app.jar | grep spring-configuration-metadata.json` shows only the application's metadata, you cannot conclude that dependencies lack metadata.

To inspect dependency metadata, you can:

1. Locate the dependency JAR in the Maven/Gradle cache, then run `jar tf` on that JAR directly.
2. Extract a dependency JAR from `BOOT-INF/lib/` into a temporary directory, then run `jar tf` on the extracted JAR.
3. Inspect the published library artifact if available.

A dependency can have metadata even when the application module generates none of its own. Conversely, application metadata may be complete while the dependency used by the IDE is an older version.

## 11. Distinguishing Application Metadata from Library Metadata

When seeing a metadata file, answer three questions:

**1. Which artifact contains the file?**

- The application module?
- A shared library JAR developed by the team?
- A third-party Spring Boot starter?
- A transitively included dependency?

**2. Which key group does the metadata describe?**

- `gateway.*` of the application itself?
- `spring.datasource.*` belonging to auto-configuration?
- `server.*` of the embedded server?
- `acme.client.*` of an external library?

**3. Which artifact version is the application running?**

A valid metadata file in source code alongside an outdated deployed JAR will not explain runtime state. And a runtime JAR with new metadata does not guarantee the IDE has updated its index or is using the same dependency version.

Avoid conflating two conclusions:

- "Metadata exists in a JAR" means **that artifact contains configuration description data**.
- "The application is using that module's configuration bean" also depends on **the classpath, bean registration mechanisms, auto-configuration, and runtime state**.

There is no automatic inference from the first conclusion to the second.

## 12. Inspecting Concrete JSON Metadata

Example abbreviated metadata file:

```json
{
  "groups": [
    {
      "name": "payment",
      "type": "com.example.configdemo.PaymentProperties",
      "sourceType": "com.example.configdemo.PaymentProperties"
    }
  ],
  "properties": [
    {
      "name": "payment.base-url",
      "type": "java.net.URI",
      "description": "Payment gateway URL."
    },
    {
      "name": "payment.max-attempts",
      "type": "java.lang.Integer",
      "description": "Maximum number of retry calls.",
      "defaultValue": 3
    },
    {
      "name": "payment.mode",
      "type": "com.example.configdemo.PaymentMode",
      "description": "Payment processing mode."
    }
  ],
  "hints": [
    {
      "name": "payment.mode",
      "values": [
        {"value": "sandbox", "description": "Use testing environment."},
        {"value": "live", "description": "Use production environment."}
      ]
    }
  ]
}
```

When inspecting JSON:

- Name `payment.max-attempts` indicates the canonical key.
- `type` specifies the corresponding Java type.
- `description` is the explanation for config authors.
- `defaultValue` describes a known default or one supplied by additional metadata.
- `hints.values` suggests choices when entering `payment.mode`.

**Hints do not imply a runtime enum constraint.** If metadata suggests `sandbox` and `live`, another value is only rejected by runtime when the target type, converter, or validator actually disallows it. Do not treat a hint list in JSON as an access control list or a mandatory value set in all cases.

## 13. Adding Descriptions with Javadoc

Good documentation reduces operational errors. The annotation processor can extract descriptive information from appropriate source code into metadata.

Example:

```java
package com.example.configdemo;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "cache")
public class CacheProperties {

    /**
     * Time to keep data in the cache before expiration.
     */
    private Duration ttl = Duration.ofMinutes(10);

    /**
     * Maximum number of entries in the cache.
     */
    private int maxEntries = 500;

    public Duration getTtl() {
        return ttl;
    }

    public void setTtl(Duration ttl) {
        this.ttl = ttl;
    }

    public int getMaxEntries() {
        return maxEntries;
    }

    public void setMaxEntries(int maxEntries) {
        this.maxEntries = maxEntries;
    }
}
```

When the annotation processor analyzes this configuration class, metadata can reflect data types and related descriptions. Exact description generation depends on declaration styles, Javadoc, the processor, and the build process.

If metadata lacks the desired descriptions, inspect the actual generated JSON; do not assume every Javadoc in every position appears automatically.

You can write additional metadata to update or clarify information when needed.

## 14. Supplementing Metadata Manually

Spring Boot supports an additional file typically named:

```text
META-INF/additional-spring-configuration-metadata.json
```

In a standard Maven/Gradle project, it can be placed at:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Example:

```json
{
  "properties": [
    {
      "name": "gateway.connect-timeout",
      "description": "Timeout waiting to establish a connection to the gateway."
    },
    {
      "name": "gateway.mode",
      "description": "Operating mode of the gateway."
    }
  ],
  "hints": [
    {
      "name": "gateway.mode",
      "values": [
        {
          "value": "sandbox",
          "description": "Use for testing environments."
        },
        {
          "value": "live",
          "description": "Use for live environments."
        }
      ]
    }
  ]
}
```

When processor configuration works properly, additional data can be merged into generated metadata to expand descriptions or provide hints the processor cannot infer.

**Do not confuse the two files:**

| File | Purpose |
| --- | --- |
| `spring-configuration-metadata.json` | Output metadata used by tooling, usually generated by the processor |
| `additional-spring-configuration-metadata.json` | Supplementary metadata source for the processor to merge into output |

Simply creating `additional-spring-configuration-metadata.json` does not guarantee runtime beans gain a new property; you still need corresponding binding code or actual configuration handling logic.

Additionally, if the module is packaging stale metadata and the processor did not run, the additional file may not merge into primary metadata as expected. Inspect the final artifact after building.

## 15. Additional Metadata Does Not Create Runtime Functionality

Suppose you add:

```json
{
  "properties": [
    {
      "name": "gateway.allow-unsafe-calls",
      "type": "java.lang.Boolean",
      "description": "Allow unsafe calls.",
      "defaultValue": false
    }
  ]
}
```

into the additional metadata source. Then the IDE can suggest a key with that name if metadata is generated and integrated.

However, that **does not create**:

```java
boolean allowUnsafeCalls;
```

inside a `@ConfigurationProperties` bean, nor does it cause services to change behavior.

Similarly, setting `defaultValue: false` only describes a default for tooling. If the binder does not recognize this property or code does not use it, metadata content does not become a runtime configuration value.

Therefore, three independent layers must be verified:

1. **Metadata:** Do IDEs/tooling have info about the key?
2. **Binding:** Does the runtime bean have the corresponding member and is it registered?
3. **Business logic:** Does the service actually use that value?

A system with clean metadata where application logic never reads the property still produces no corresponding behavior.

## 16. What Role Does Metadata Play for IDEs?

Many IDEs and extensions can read Spring configuration metadata to:

- Suggest property names while editing `application.yml` or `application.properties`.
- Display descriptions or value types.
- Offer suggestions for available values, such as enums or hint lists.
- Warn on keys that are no longer recommended for use.
- Detect unfamiliar configuration names within the metadata scope recognized by the tool.

**These are development tool features**, not a guarantee that Spring Boot runtime itself runs the same validation rule set.

Practical differences exist:

- IDE A may understand dependency metadata better than IDE B.
- An extension may need to be enabled or updated.
- After adding the processor, the IDE may need to sync dependencies or rebuild to pick up the new file.
- An "unknown property" warning in the IDE can be a **false positive** for dynamic properties or library properties whose metadata has not loaded.
- Having no IDE warnings does not mean runtime configuration is valid.

When troubleshooting autocomplete, verify the IDE has opened **the right module, classpath, and JAR version**. When troubleshooting application startup, inspect **Runtime Environment, binder, and validation**.

## 17. Deprecated Property Warnings in Metadata

Metadata can also describe an outdated property:

```json
{
  "name": "gateway.legacy-timeout",
  "type": "java.time.Duration",
  "description": "Legacy timeout name.",
  "deprecation": {
    "level": "warning",
    "reason": "The old property was replaced by connect-timeout.",
    "replacement": "gateway.connect-timeout"
  }
}
```

This information can help the IDE display warnings and suggest replacement names.

Distinguish:

- **Metadata deprecation:** signal for development tooling and documentation.
- **`@Deprecated` in Java:** marker that a Java API is no longer recommended.
- **Runtime rejection:** the application actually rejecting an old key.

You cannot conclude that a property marked deprecated in metadata will automatically cause a startup error. A library may keep supporting the old key for compatibility, or enforce a separate rejection policy.

When removing a property, make the change in binding code or the appropriate runtime check pipeline, while updating metadata to assist users in migrating.

## 18. Metadata Does Not Guarantee Runtime Validation

Consider the metadata:

```json
{
  "properties": [
    {
      "name": "worker.max-threads",
      "type": "java.lang.Integer",
      "description": "Thread count must be between 1 and 32."
    }
  ]
}
```

Someone writes:

```properties
worker.max-threads=-10
```

If the Java bean only has:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

then `-10` is still a valid `int` by type. Just because metadata says "1..32" **does not mean** Spring Boot automatically enforces that bound.

To reject it at startup, use Bean Validation:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @Min(1) @Max(32) int maxThreads) {
}
```

A Spring Boot 3.x project needs an appropriate Bean Validation provider, usually supplied via `spring-boot-starter-validation`.

Once `-10` is converted to an integer by the binder, validation can reject it and cause context initialization to fail.

**Metadata does not replace `@Validated`, `@Min`, `@NotBlank`, `@NotNull`, `@Valid`, or constraints inside constructors.**

## 19. Runtime Example: Real Configuration Constraints

File:

```yaml
# application.yml
payment:
  endpoint: "https://pay.example.invalid"
  max-retries: 4
```

Record:

```java
package com.example.configdemo;

import java.net.URI;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        @NotNull URI endpoint,
        @Min(1) int maxRetries) {
}
```

Application class:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

In the case of:

```properties
payment.max-retries=0
```

the runtime binder can convert `0` to `int`, yet the validator rejects it for violating `@Min(1)`.

Spring does not need to read `spring-configuration-metadata.json` at runtime to perform this check. Spring uses information from annotations on the configuration type and the configured Bean Validation mechanism.

If you remove the annotation processor so metadata is no longer generated, Bean Validation still works. If you remove `@Validated` or the validation provider, having metadata still present will not replace validation.

## 20. Four Easily Confused Scenarios

Look at the table:

| Scenario | Metadata present? | Can runtime bind/validate? |
| --- | --- | --- |
| Processor present, `@ConfigurationProperties` present, validation present | Likely yes | Yes, if bean is registered and provider works |
| No processor, `@ConfigurationProperties` still present | Likely missing | Can still bind normally |
| Manual metadata present, no bean/runtime handler | Yes | Features/binding do not appear automatically |
| Metadata present, yet value violates runtime constraints | Yes | Can be rejected during binding/validation |

Conclusion: **metadata, bean registration, type conversion, and validation are related, yet the presence of one component cannot be used to prove another component is working**.

## 21. Metadata and Catching Misspelled Keys

Suppose the bean expects:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

Metadata has the name:

```text
worker.max-threads
```

Yet YAML writes:

```yaml
worker:
  max-threds: 8
```

An IDE with appropriate metadata **may** warn that `max-threds` is unrecognized. However, if the IDE does not warn or someone edits YAML in a plain text editor without metadata support, runtime may still ignore the unknown property under default binding settings.

To help runtime reject unbound keys within the bean's scope, consider:

```java
@ConfigurationProperties(
        prefix = "worker",
        ignoreUnknownFields = false)
public record WorkerProperties(int maxThreads) {
}
```

For a misspelled key under prefix `worker` that the binder actually observes, this mode can cause binding to fail instead of silently ignoring it.

**Limitations remain:**

- This is not a global scanner across all keys in every `PropertySource`.
- Typos in the prefix itself, such as `wroker.max-threads`, may fall outside the bound bean's scope.
- Some namespaces contain maps or dynamic keys, so an "unknown key" may actually be valid data.
- The rule takes effect only when the bean is registered and bound.
- Configuration files not loaded because a profile is inactive are not checked in that run either.

Therefore, IDE metadata and `ignoreUnknownFields = false` **complement** one another, yet neither alone suffices to prove every file across every environment has zero typos.

## 22. Metadata Does Not Replace Testing Profile-Specific Configurations

Suppose the project has:

```text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
```

`application-prod.yml`:

```yaml
worker:
  max-threads: -2
```

Metadata may specify `worker.max-threads` as an integer and contain the description "Range 1..32". However, metadata does not open and check every profile-specific file prior to deployment.

If running the app only with profile `dev`, `application-prod.yml` may not be loaded. Runtime validation of `prod` configuration is therefore not triggered during the `dev` run.

To verify production configuration, start or test binding with the corresponding source/profile, such as in a test environment:

```bash
java -jar app.jar --spring.profiles.active=prod
```

If `WorkerProperties` has `@Validated @Min(1)` and the bean is registered, runtime will catch `-2` when the `prod` profile supplies the effective value.

Do not put real secrets into examples/tests or log the entire configuration object for diagnostics.

## 23. Testing Binding and Validation with `ApplicationContextRunner`

Spring Boot Test provides `ApplicationContextRunner` to construct a lightweight `ApplicationContext` and feed configuration values to it.

Example bean:

```java
package com.example.configdemo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @NotBlank String queueName,
        @Min(1) @Max(32) int maxThreads) {
}
```

Test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class WorkerPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void acceptsValidConfiguration() {
        runner.withPropertyValues(
                "worker.queue-name=orders",
                "worker.max-threads=8"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            WorkerProperties properties =
                    context.getBean(WorkerProperties.class);
            assertThat(properties.queueName()).isEqualTo("orders");
            assertThat(properties.maxThreads()).isEqualTo(8);
        });
    }

    @Test
    void rejectsInvalidThreadCount() {
        runner.withPropertyValues(
                "worker.queue-name=orders",
                "worker.max-threads=-5"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Test
    void rejectsMissingQueueName() {
        runner.withPropertyValues(
                "worker.max-threads=8"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class TestConfiguration {
    }
}
```

This test **does not check whether the metadata file is inside the JAR**. It tests something else, more grounded in runtime: does the binder construct the bean with valid data and reject data violating constraints?

Conversely, opening metadata JSON to find `worker.queue-name` does not prove the test above will pass if the validation provider is missing or the bean is unregistered.

These two test types serve two independent purposes.

## 24. Inspecting the Metadata File in a Build Pipeline

In CI/CD, a project can add an artifact structure verification step. The goal is to avoid publishing a configuration library whose properties development tools cannot discover.

Suggested workflow:

1. Build the module containing `@ConfigurationProperties`.
2. Verify the processor generated `spring-configuration-metadata.json`.
3. Verify the JSON is non-empty and includes important groups/properties.
4. Build the JAR.
5. Verify the metadata file sits inside the exact artifact to be published.
6. Run runtime binding/validation tests independently.

Example standard Java commands:

```bash
./mvnw clean package
jar tf target/my-app.jar
```

In a Linux CI environment with `unzip`:

```bash
unzip -p target/my-app.jar \
  BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

In Windows PowerShell, use `jar tf ... | Select-String ...` to verify the entry.

If the project produces a **library JAR** instead of a Boot executable JAR, the path is typically `META-INF/spring-configuration-metadata.json`. CI scripts should know the target artifact type or inspect actual entries rather than hardcoding a single path for every project.

Treat metadata verification as an **artifact/tooling check**, and validation testing as a **runtime behavior check**. Both can belong in a pipeline, yet their results do not substitute for one another.

## 25. Adding JSON Checks During the Build

When needing to confirm property names appeared, you can read the JSON with an appropriate tool.

Suppose a Linux pipeline has `jq`:

```bash
unzip -p target/my-app.jar \
  BOOT-INF/classes/META-INF/spring-configuration-metadata.json \
  | jq -r '.properties[]?.name'
```

This command lists property names in the application module's metadata inside a Boot executable JAR.

You can search specifically:

```bash
unzip -p target/my-app.jar \
  BOOT-INF/classes/META-INF/spring-configuration-metadata.json \
  | jq -e '.properties[]? | select(.name == "gateway.connect-timeout")'
```

If the second command does not find the property, recheck:

- Was the configuration class processed by the processor?
- Are the prefix name or Java members correct?
- Did the processor run in the current module?
- Is the JAR under inspection the freshly built artifact?
- Does metadata live in the application or in another dependency JAR?

Do not manually patch a JAR just to inject a JSON file and conclude a runtime feature was added. If source metadata is missing, fix the build/source and rebuild the artifact reproducibly.

## 26. Distinguishing Metadata from `spring-autoconfigure-metadata.properties`

In the Spring Boot ecosystem, you may encounter other files also under `META-INF`, such as:

```text
META-INF/spring-autoconfigure-metadata.properties
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

These files serve other parts of the auto-configuration mechanism or auto-configuration class registration, not documentation describing the list of properties an IDE will propose.

Do not conflate:

| File | High-level Role |
| --- | --- |
| `spring-configuration-metadata.json` | Describes groups and properties for configuration tooling |
| `additional-spring-configuration-metadata.json` | Supplementary metadata source at build time |
| `spring-autoconfigure-metadata.properties` | Metadata supporting auto-configuration mechanisms in applicable versions/setups |
| `AutoConfiguration.imports` | List of auto-configuration classes exposed by a module |

A project may contain all or only a few of these files. The presence of one file does not prove another was generated.

When an IDE does not suggest `gateway.connect-timeout`, inspect **configuration metadata JSON**, rather than searching for property names in auto-configuration class lists.

## 27. Do Not Read Metadata JSON in Application Code to Create Configuration

A design mistake is treating metadata as a runtime configuration source and reading it in code to construct values.

For example, do not assume:

```text
spring-configuration-metadata.json
       |
       v
Spring Boot reads defaultValue and populates Environment
```

The actual mechanism in standard applications is:

```text
application.yml / CLI / Environment
       |
       v
Spring Environment
       |
       v
ConfigurationProperties Binder
       |
       v
Configuration bean
```

Meanwhile:

```text
@ConfigurationProperties in source code
       |
       v
Annotation processor at build time
       |
       v
spring-configuration-metadata.json
       |
       v
IDE/tooling reference
```

Because metadata is primarily **descriptive**, building a custom runtime mechanism to read `defaultValue` from JSON usually adds complexity and risks conflicting with Spring's precedence order.

To set a real default, use a valid configuration source, `@DefaultValue`, JavaBean field defaults, or a mechanism supported by Spring Boot for your bean type.

## 28. What If the Metadata File Is Missing from the JAR?

Common causes:

### 28.1. Configuration Processor Not Declared

The project only has `spring-boot-starter` and `@ConfigurationProperties`, without configuring `spring-boot-configuration-processor`.

**Resolution:** add the processor per your build tool and recompile.

### 28.2. Annotation Processing Disabled

The IDE or compiler may be configured to skip annotation processing.

**Resolution:** check compiler settings, processor paths, and build logs. Prefer verifying with a reproducible Maven/Gradle CLI build rather than trusting IDE state alone.

### 28.3. Inspecting the Wrong JAR

The application module may be `my-app.jar`, while configuration is declared in module `my-common-config.jar`.

**Resolution:** locate the exact module containing the `@ConfigurationProperties` class and inspect its artifact.

### 28.4. Looking in the Wrong Path Inside a Boot JAR

You checked `META-INF/` at root while application metadata actually sits under `BOOT-INF/classes/META-INF/`.

**Resolution:** use `jar tf` to inspect the actual layout.

### 28.5. Metadata Lives in a Nested Dependency

The application depends on a starter whose metadata is inside the starter's JAR.

**Resolution:** inspect the dependency JAR directly; `jar tf` on the outer Boot JAR does not look inside nested JARs.

### 28.6. Processor Ran Yet Missed the Intended Type

The class may not be compiled in the active module, have a wrong annotation name, sit in another source set, be excluded by the build, or use a pattern hard to infer automatically.

**Resolution:** inspect compiled classes, annotation processor paths, incremental build settings, and pre-packaging metadata output.

### 28.7. Published JAR Is Stale

A cached pipeline or skipped packaging task caused the metadata inside the artifact not to reflect new code.

**Resolution:** run a clean build when needed, identify artifacts by version/checksum, and inspect the exact file prepared for deployment.

## 29. What If Metadata Exists Yet the IDE Still Shows No Suggestions?

Troubleshoot in this order:

1. Verify the metadata file resides in the module/JAR actually used by the IDE.
2. Verify the JSON contains the exact `properties[].name` you expect.
3. Verify the project was imported/synced with Maven or Gradle after adding the processor.
4. Check whether Spring Boot support in the IDE/extension is enabled.
5. Check that you are editing a supported configuration file and syntax (YAML, Properties).
6. Check the dependency version currently resolved by the IDE.
7. If needed, rebuild or refresh indexes via IDE controls.
8. Do not treat lack of autocomplete as a runtime error if the application binds properly.

Some configuration properties are created dynamically or handled by other frameworks, so they have no metadata for suggestions. That is not necessarily an error.

If the IDE warns about an unknown key while runtime receives the value, the IDE may lack metadata or hold stale metadata. Conversely, if the IDE suggests a key while runtime ignores it, the bean may be inactive, the wrong profile active, a dependency missing, or configuration overridden by another source.

## 30. Distinguishing Key Name Warnings from Type Conversion Errors

Consider the configuration:

```yaml
gateway:
  connect-timeout: "not-a-duration"
```

Metadata can state `gateway.connect-timeout` is `java.time.Duration`. The IDE may spot the invalid format if the tool supports corresponding rules, yet runtime still has to perform real binding.

At runtime, the binder cannot convert `not-a-duration` into a `Duration` normally and may cause context startup to fail.

Conversely:

```yaml
gateway:
  connect-timout: 5s
```

this is a **wrong key name**. An IDE with metadata can suggest the right name; the runtime binder may ignore the unknown key under default policy, or reject it if strict binding is enabled and the key falls within controlled scope.

Finally:

```yaml
gateway:
  max-attempts: -5
```

the key name is right, type `int` is right, yet the value may violate business requirements if `@Min(1)` is present.

Three scenarios require three distinct diagnostic approaches.

## 31. Misconceptions to Avoid

### 31.1. "Having metadata JSON means configuration was loaded by Spring"

False. Metadata is mainly for tooling; actual configuration loading belongs to `Environment` and Config Data.

### 31.2. "If the IDE knows a property name, runtime definitely has the bean"

False. A property in metadata might belong to a module not activated at runtime, conditional auto-configuration, or another version.

### 31.3. "Changing `defaultValue` in metadata changes the runtime default"

False. You must change actual defaults in configuration sources or binder/constructor mechanisms.

### 31.4. "Metadata already states numeric bounds so Bean Validation is unnecessary"

False. Describing bounds does not enforce `@Min` or `@Max`.

### 31.5. "A JAR without metadata means `@ConfigurationProperties` does not run"

Not necessarily. The runtime binder does not require metadata JSON to operate.

### 31.6. "`jar tf app.jar` searches inside all dependency JARs automatically"

False. `jar tf` only lists entries of the opened JAR; nested JARs must be inspected separately.

### 31.7. "Adding `additional-spring-configuration-metadata.json` is enough for both IDE and runtime to understand the property"

Not necessarily. The processor/build must merge the data; runtime still needs binding logic or property handling.

### 31.8. "IDE warnings are runtime validation results"

No. The IDE performs static analysis based on metadata, whereas runtime relies on beans and effective data.

### 31.9. "Having metadata means every profile was validated"

False. Metadata does not execute all profiles. Runtime checks the sources loaded during a specific startup.

### 31.10. "Every item in hints is a strict value set"

Not necessarily. Hints can be a suggestion list. Real acceptance rules must reside in target types, converters, or validators.

## 32. Question-Driven Error Investigation Workflow

| Question from the Development Team | Where to Check |
| --- | --- |
| IDE does not autocomplete `gateway.*` | Processor, metadata JSON, module/JAR, IDE |
| Metadata missing in executable JAR | `jar tf`, `BOOT-INF/classes/META-INF/` |
| Starter metadata missing in outer JAR | Inspect the nested dependency JAR itself |
| Property not bound at runtime | Bean registration, prefix, Config Data, profile |
| Wrong value bound | `PropertySource` precedence, type conversion |
| Negative value yet app raises no error | Bean Validation or constructor invariant |
| Typo key does not fail startup | Strict unknown fields and configuration tests |
| Metadata has default yet runtime gets null/0 | Actual defaults in YAML/Java/binder |
| IDE and runtime report different results | Versions, classpath, and scope of each mechanism |

The goal is **fixing at the right layer**. Editing JSON metadata does not fix an unregistered bean; adding `@Validated` will not give the IDE a property list if the processor has not generated metadata.

## 33. Exercise A: Finding the Exact Path Inside a JAR

A Boot executable JAR has the layout:

```text
BOOT-INF/classes/com/example/configdemo/GatewayProperties.class
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
BOOT-INF/lib/acme-starter.jar
```

**Question 1:** Where does metadata generated by the application module reside?

**Answer:** `BOOT-INF/classes/META-INF/spring-configuration-metadata.json`.

**Question 2:** Can you conclude `acme-starter.jar` lacks metadata just because `jar tf app.jar` does not list `acme-starter.jar!/META-INF/...`?

**No.** Library metadata may reside inside the dependency JAR. That JAR must be inspected separately.

## 34. Exercise B: Does Metadata Become a Runtime Default?

A metadata JSON contains:

```json
{
  "properties": [
    {
      "name": "task.batch-size",
      "type": "java.lang.Integer",
      "defaultValue": 100
    }
  ]
}
```

Record:

```java
@ConfigurationProperties(prefix = "task")
public record TaskProperties(int batchSize) {
}
```

`task.batch-size` is absent from all configuration sources.

**Question:** Can you be certain runtime receives `batchSize=100` just because JSON has `defaultValue:100`?

**Answer:** no. Metadata is descriptive data, not an effective binder default source. Defaults must be declared via YAML, `@DefaultValue`, or another supported mechanism.

## 35. Exercise C: Does Metadata Replace Validation?

Metadata describes:

```json
{
  "properties": [
    {
      "name": "task.max-attempts",
      "type": "java.lang.Integer",
      "description": "Value must be between 1 and 10."
    }
  ]
}
```

Yet the record only declares:

```java
@ConfigurationProperties(prefix = "task")
public record TaskProperties(int maxAttempts) {
}
```

With `task.max-attempts=-7`, will the application definitely report an error solely due to the description sentence in JSON?

**No.** `-7` is a valid integer. Validation such as `@Min(1) @Max(10)` or constructor checks are required to prevent out-of-range values.

## 36. Exercise D: Distinguishing Name Errors from Value Errors

Record:

```java
@Validated
@ConfigurationProperties(
        prefix = "mail",
        ignoreUnknownFields = false)
public record MailProperties(
        @NotBlank String sender,
        @Min(1) int retryCount) {
}
```

Examine:

**Case 1:**

```yaml
mail:
  sender: "ops"
  retry-count: many
```

**Case 2:**

```yaml
mail:
  sender: "ops"
  retry-coutn: 3
```

**Case 3:**

```yaml
mial:
  sender: "ops"
  retry-count: 3
```

Answers:

1. Name `retry-count` is right, yet `many` cannot convert to `int`.
2. `retry-coutn` is wrong inside prefix `mail`; strict binding can detect it as an unbound key.
3. Wrong prefix `mial`; the unknown-field rule of the `mail` bean does not guarantee catching a key outside its prefix. Validation on required fields may catch the missing data.

If the bean is unregistered or the validator is inactive, expected checks might not occur even when metadata exists.

## 37. Exercise E: Proposing a Complete Pipeline

A team publishes library `acme-gateway-starter` for multiple projects. They want IDEs to have autocomplete and applications to reject invalid timeouts.

A reasonable design includes:

1. Defining `@ConfigurationProperties(prefix = "acme.gateway")` with type `Duration`.
2. Declaring the annotation processor to generate `spring-configuration-metadata.json`.
3. Adding descriptions/hints if needed via additional metadata sources.
4. Packaging and verifying the metadata file is inside the published JAR.
5. Registering the configuration bean via proper Spring Boot mechanisms.
6. Adding validation or constructor checks to prevent invalid timeouts.
7. Writing binding tests with valid and invalid values.
8. Integrating artifact verification into CI.

**Question:** Which steps primarily serve IDEs, and which serve runtime?

**Answer:** steps 2–4 serve metadata/tooling and artifact verification; steps 5–7 serve runtime binding/validation; step 1 creates the Java contract underlying both.

## 38. Takeaways

- Spring Boot configuration metadata usually lives in **`META-INF/spring-configuration-metadata.json`**.
- `spring-boot-configuration-processor` generates metadata **at compile time** from configurations the processor can analyze.
- In a **library JAR**, metadata usually sits in `META-INF/`; in a **Boot executable JAR**, application metadata usually sits in `BOOT-INF/classes/META-INF/`.
- Dependency JARs in `BOOT-INF/lib/` can carry their own metadata; `jar tf` on the outer JAR does not automatically inspect inside them.
- Metadata describes `groups`, `properties`, `hints`, and info such as names, types, descriptions, defaults, and deprecations.
- `additional-spring-configuration-metadata.json` is a supplementary source for metadata generation, **not** a way to create runtime properties.
- IDEs can use metadata for autocomplete and warnings, though scope and accuracy depend on tools, modules, classpaths, and versions.
- **Having metadata does not mean runtime validation.** `@ConfigurationProperties` binding, type conversion, `@Validated`, and Bean Validation determine value acceptance at runtime.
- `defaultValue` or `description` contents in JSON do not set runtime values or enforce constraints.
- Verifying metadata artifacts and testing runtime configuration are **two independent, complementary steps**. Use both to improve developer experience and deployment reliability.
