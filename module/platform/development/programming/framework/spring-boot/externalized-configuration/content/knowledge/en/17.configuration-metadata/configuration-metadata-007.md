# Supplementing Information with `additional-spring-configuration-metadata.json` in Spring Boot 3.3

## 1. Overview

Spring Boot uses **configuration metadata** to describe properties that can be declared in `application.properties`, `application.yaml`, and other configuration sources. Metadata helps IDEs display key name suggestions, data types, descriptions, suggested values, default values, and warnings for deprecated properties.

In projects with `@ConfigurationProperties`, most metadata can be **auto-generated at compile time** by `spring-boot-configuration-processor`. However, the processor cannot infer all business meanings solely from field names and Java types. There are properties read manually via `Environment` or `@Value`, `String` values that only allow a clear set of choices, or metadata requiring deprecation notes and a replacement path.

To address these cases, Spring Boot 3.3 supports an optional source file:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

When read by the annotation processor during the build, the contents of this file are **merged** with auto-generated metadata to produce the result:

```text
META-INF/spring-configuration-metadata.json
```

**This is metadata for development tooling, not a runtime configuration file.** Creating an additional file does not register beans, does not define properties in `Environment`, does not enforce types, does not add validation, does not replace `application.yaml`, and does not determine precedence among configuration sources.

This lesson walks from file organization and JSON schema to practical examples: adding descriptions to existing properties, declaring properties not discovered by the processor, suggesting values/providers, suggesting Map keys and Map values, marking deprecation, checking Maven/Gradle builds, and troubleshooting common errors.

## 2. Distinguishing Three Easily Confused Files

In a Spring Boot application, you may encounter the following files:

| File | Who creates or edits it? | Role |
| --- | --- | --- |
| `src/main/resources/application.properties` or `application.yaml` | Developers/operators | **Supplies runtime configuration values** |
| `src/main/resources/META-INF/additional-spring-configuration-metadata.json` | Developers | **Supplies supplementary metadata at build time** |
| `META-INF/spring-configuration-metadata.json` in build output or JAR | `spring-boot-configuration-processor` | **Merged metadata for IDEs and tooling** |

Example of a key appearing across all three layers:

**Java model:**

```java
@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {
    private String mode = "safe";

    public String getMode() {
        return mode;
    }

    public void setMode(String mode) {
        this.mode = mode;
    }
}
```

**Runtime value:**

```properties
# application.properties
acme.mode=fast
```

**IDE assistance information:**

```json
{
  "hints": [
    {
      "name": "acme.mode",
      "values": [
        {"value": "safe", "description": "Prioritize safer behavior."},
        {"value": "fast", "description": "Prioritize throughput."}
      ]
    }
  ]
}
```

Metadata in the JSON block allows the IDE *to* suggest `safe` and `fast`. It **does not make `acme.mode` automatically switch to `safe`** when operators omit it, does not make `fast` mandatory, and does not validate another string at runtime. The runtime default in the example comes from the `"safe"` field initializer in the Java model, while the actual value `"fast"` comes from Config Data.

## 3. Relationship with `spring-boot-configuration-processor`

The Spring Boot annotation processor reads types annotated with `@ConfigurationProperties` and generates the standard metadata file. Information that can be inferred automatically includes:

- Prefixes and properties declared in configuration classes.
- Canonical property names.
- Java types and nested properties recognized by the processor.
- Certain default values and descriptions from source.
- Deprecation info inferable from appropriate APIs.
- Metadata groups for configuration namespaces.

However, auto-inference still has limitations:

1. A `String mode` does not automatically reveal that business logic expects `safe` and `fast`.
2. A property accessed directly via `Environment#getProperty("acme.legacy-token")` may go undetected because it is not inside a `@ConfigurationProperties` bean.
3. A dynamically computed default is not necessarily inferable accurately at compile time.
4. A field may require clear descriptions of units, limits, or risks that code types do not convey.
5. A backward-compatible alias needs deprecation/replacement metadata, even when runtime handles it via separate code.

The `additional-spring-configuration-metadata.json` file **fills those gaps** without editing the auto-generated metadata file.

### 3.1. Is the Additional File Mandatory?

No. If metadata from the processor already suffices for the IDE, there is no need to create an additional file. If the project does not configure the annotation processor, merely placing a file named `additional-...json` in resources **is not enough to guarantee merged metadata is produced**; verify the build pipeline actually runs the processor and loads the additional file.

### 3.2. Do Not Edit the Generated File Directly

Maven output example:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

Gradle output example:

```text
build/classes/java/main/META-INF/spring-configuration-metadata.json
```

Output files can be overwritten on every compile/clean. Do not edit them directly to add descriptions: changes will not persist. Put manual data in `additional-spring-configuration-metadata.json` inside source code, commit it with the project, and rebuild.

## 4. File Location and Directory Structure

A typical Java project:

```text
my-app/
├── pom.xml                       # or build.gradle
└── src/
    └── main/
        ├── java/
        │   └── com/example/demo/config/
        │       └── AcmeProperties.java
        └── resources/
            ├── application.yaml
            └── META-INF/
                └── additional-spring-configuration-metadata.json
```

Exact name to note:

```text
META-INF/additional-spring-configuration-metadata.json
```

Do not misplace or misname it as:

```text
META-INF/spring-configuration-metadata-additional.json
META-INF/additional-spring-configuration-metadata.yaml
META-INF/additional-configuration-metadata.json
additional-spring-configuration-metadata.json     (at resources root)
```

Wrong names are not recognized by the processor under the contract for additional files.

**Path principle:** `src/main/resources` is the resources root; the path the processor looks for is `META-INF/additional-spring-configuration-metadata.json`. For projects with custom layouts, ensure it is present at the corresponding resource path during compilation.

## 5. JSON Metadata: `groups`, `properties`, and `hints`

The additional file uses the same JSON format as standard metadata, with three arrays:

```json
{
  "groups": [],
  "properties": [],
  "hints": []
}
```

You do not always need to declare all three arrays. Having only hints is valid too:

```json
{
  "hints": [
    {
      "name": "acme.mode",
      "values": [
        {"value": "safe"},
        {"value": "fast"}
      ]
    }
  ]
}
```

Roles:

| Array | Target | When to use |
| --- | --- | --- |
| `groups` | Namespace groups containing properties | Want to manually describe an additional group or an undiscovered namespace |
| `properties` | Properties with name, type, description, default, deprecation | Supplement keys outside `@ConfigurationProperties` or improve descriptions of processor-generated properties |
| `hints` | Suggested values and IDE-assisting providers | Want to suggest values, Map keys/values, bean names, profile names, classes, Resources... |

A JSON file may contain only `properties`; it may also contain `properties` and `hints` together. This is **a standard JSON document**, not JSON Lines, with no `//` or `#` comments and no trailing commas at the end of arrays/objects.

### 5.1. Combined Template

```json
{
  "groups": [
    {
      "name": "acme.feature",
      "type": "com.example.demo.config.FeatureProperties",
      "description": "Settings for the Acme feature."
    }
  ],
  "properties": [
    {
      "name": "acme.feature.mode",
      "type": "java.lang.String",
      "description": "Execution mode for the feature.",
      "defaultValue": "safe"
    },
    {
      "name": "acme.feature.max-retries",
      "type": "java.lang.Integer",
      "description": "Maximum number of retries.",
      "defaultValue": 3
    }
  ],
  "hints": [
    {
      "name": "acme.feature.mode",
      "values": [
        {"value": "safe", "description": "Prefer safety."},
        {"value": "fast", "description": "Prefer speed."}
      ]
    }
  ]
}
```

Names such as `com.example.demo.config.FeatureProperties` are **illustrative classes**; replace them with actual classes if applicable. Unnecessary `groups` and `type` entries can be omitted when auto-generated groups/items already exist. This template explains the schema, and does not mean every project needs to create manual groups.

## 6. Attributes in the `properties` Section

Each element of the `properties` array must specify `name`; additional attributes help tools describe the key more accurately.

| JSON field | Common type | Meaning |
| --- | --- | --- |
| `name` | String | Full name, for example `acme.http.connect-timeout`; **required** |
| `type` | String | Java type name (usually fully qualified), for example `java.lang.String` or `java.time.Duration` |
| `description` | String | Explanation of functionality, units, and property notes |
| `sourceType` | String | Fully qualified class name contributing the declaration if known |
| `defaultValue` | JSON primitive, String, or compatible form | Default value **described** for tooling |
| `deprecation` | Object | Info on deprecated property, reason, and replacement key |

Example:

```json
{
  "properties": [
    {
      "name": "acme.http.connect-timeout",
      "type": "java.time.Duration",
      "description": "Connection timeout. Configure an explicit unit, such as 500ms or 5s.",
      "defaultValue": "3s",
      "sourceType": "com.example.demo.config.AcmeHttpProperties"
    }
  ]
}
```

**Property names must be written consistently**, preferring lowercase kebab-case with hierarchical dots. `acme.http.connect-timeout` and `acme.http.connectTimeout` are representations that can bind to Java `connectTimeout`, but metadata should use the canonical name.

### 6.1. `defaultValue` Is Not a Runtime Default

`"defaultValue": "3s"` only **describes** the default for the IDE. If code does not initialize `connectTimeout` and the config file does not declare a value, writing that metadata **does not cause the Binder to construct a 3-second Duration**.

Runtime defaults must exist where execution occurs, for example:

```java
private Duration connectTimeout = Duration.ofSeconds(3);
```

or:

```java
public record AcmeHttpProperties(
    @DefaultValue("3s") Duration connectTimeout) {
}
```

with appropriate constructor binding; or via an `application.properties` source with the corresponding value. If metadata says 3s while actual code uses 5s, the IDE will display inaccurate info. Keep metadata synchronized with runtime default mechanisms.

### 6.2. `description` Should Describe Behavior, Not Repeat the Key Name

Weak description:

```json
{
  "name": "acme.http.connect-timeout",
  "description": "Connect timeout."
}
```

Helpful description:

```json
{
  "name": "acme.http.connect-timeout",
  "description": "Maximum time to establish a connection. Use an explicit Duration unit such as 500ms or 3s."
}
```

If 0 or negative values have special meaning, state it clearly. If a property holds sensitive data, metadata should only state a **description**, never put real secrets in `defaultValue` or `description`.

### 6.3. Full `type` and Generic Types

A property can use standard Java types:

```json
{
  "name": "acme.targets",
  "type": "java.util.List<java.lang.String>",
  "description": "Target identifiers."
}
```

Or:

```json
{
  "name": "acme.retry-limits",
  "type": "java.util.Map<java.lang.String,java.lang.Integer>",
  "description": "Per-client retry limits."
}
```

If the processor has already inferred the exact type from `@ConfigurationProperties`, it is usually **unnecessary** to repeat `type` in additional metadata just to add description/hints. Spring Boot 3.3 documentation explicitly notes that manual metadata can override `description`, `defaultValue`, and `deprecation` of generated items.

## 7. Overriding Info of an Auto-Generated Property

Suppose `spring-boot-configuration-processor` reads the class:

```java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {

    private String mode = "safe";

    public String getMode() {
        return mode;
    }

    public void setMode(String mode) {
        this.mode = mode;
    }
}
```

The project enables `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(AcmeProperties.class)` so runtime binds the bean. The processor can detect `acme.mode`, yet lacks a full business description.

In `additional-spring-configuration-metadata.json`:

```json
{
  "properties": [
    {
      "name": "acme.mode",
      "description": "Controls how the Acme feature executes. The safe mode prioritizes predictable behavior.",
      "defaultValue": "safe"
    }
  ],
  "hints": [
    {
      "name": "acme.mode",
      "values": [
        {"value": "safe", "description": "Prefer predictable behavior."},
        {"value": "fast", "description": "Prefer throughput."}
      ]
    }
  ]
}
```

When the processor merges successfully, generated metadata for `acme.mode` contains the manually provided description/default along with other info generated from the class, such as type.

**Merge rules explicitly stated by Spring Boot 3.3:** for properties already auto-discovered **within the current module**, the `description`, `defaultValue`, and `deprecation` fields from additional metadata **override if specified**. If a manual property does not match any item found by the processor in the module, it is added as a new property.

Do not generalize that every field such as `type`, `sourceType`, name, or group can be overridden by the same rule. For discovered properties, prefer letting the processor determine type/source and using the additional file for descriptions, default values, deprecations, and hints.

### If You Only Want to Add Value Suggestions

No need to redeclare the property:

```json
{
  "hints": [
    {
      "name": "acme.mode",
      "values": [
        {"value": "safe"},
        {"value": "fast"}
      ]
    }
  ]
}
```

This is an ideal use case for additional metadata: the Java model remains `String`, while the IDE gets a suggestion list to prevent typos.

## 8. Declaring Properties Not Discovered via `@ConfigurationProperties`

Some applications read a key manually:

```java
package com.example.demo.service;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class RuntimeOptions {

    private final Environment environment;

    public RuntimeOptions(Environment environment) {
        this.environment = environment;
    }

    public String getFeatureTokenMode() {
        return environment.getProperty(
                "acme.feature-token-mode", "standard");
    }
}
```

Here `acme.feature-token-mode` does not belong to a `@ConfigurationProperties` bean, so the annotation processor may not generate metadata for this key.

Supplement:

```json
{
  "properties": [
    {
      "name": "acme.feature-token-mode",
      "type": "java.lang.String",
      "description": "Selects how feature tokens are interpreted.",
      "defaultValue": "standard"
    }
  ],
  "hints": [
    {
      "name": "acme.feature-token-mode",
      "values": [
        {"value": "standard"},
        {"value": "strict"}
      ]
    }
  ]
}
```

After a successful build, merged metadata can contain the new key and the IDE can suggest it when editing:

```properties
acme.feature-token-mode=strict
```

However, note: **metadata does not give `RuntimeOptions` new methods or automatically validate the `strict` value**. Runtime code still decides how it reads, defaults, parses, and checks the value set. If code accepts any string, hints do not restrict those strings either.

### A Property Without a Bean Still Needs to Exist in Code

If you add:

```json
{
  "properties": [
    {
      "name": "acme.feature-enabled",
      "type": "java.lang.Boolean",
      "description": "Enables the Acme feature.",
      "defaultValue": false
    }
  ]
}
```

without **any code or framework reading `acme.feature-enabled`**, the application will not change behavior just because the key appears in metadata. Do not use the additional file to "declare runtime configuration" in the sense of creating a new configuration bean.

If manual keys accumulate, consider switching to a `@ConfigurationProperties` class for type-safe binding, validation, automatic metadata, and clean prefix management.

## 9. Hints: Value Suggestions for the IDE

The `hints` section provides extra data to assist editing configuration files. A hint typically has:

- `name`: property name the hint applies to.
- `values`: suggested values, each element having `value` and optionally `description`.
- `providers`: smart suggestion sources, such as enums, classes, bean names, logger names, or profile names.

Example:

```json
{
  "hints": [
    {
      "name": "acme.storage-mode",
      "values": [
        {
          "value": "memory",
          "description": "Keep data in memory for a lightweight setup."
        },
        {
          "value": "disk",
          "description": "Persist data on local storage."
        },
        {
          "value": "remote",
          "description": "Use an external storage service."
        }
      ]
    }
  ]
}
```

IDEs supporting metadata can use `values` for auto-complete or displaying descriptions when users type:

```properties
acme.storage-mode=
```

### 9.1. A Hint List Is Not Validation by Default

If the Java target is:

```java
private String storageMode;
```

metadata hints do not turn it into an enum or reject `"unknown"` at runtime. To restrict runtime values, you can:

- Use a Java enum with allowed values.
- Perform explicit checks in a service/constructor.
- Add Bean Validation or an appropriate custom converter/validator.

Metadata is **information for tools**, whereas validation is **execution rules**.

### 9.2. Hint Values Have JSON Types

For a boolean property:

```json
{
  "hints": [
    {
      "name": "acme.verbose",
      "values": [
        {"value": true, "description": "Enable verbose output."},
        {"value": false, "description": "Disable verbose output."}
      ]
    }
  ]
}
```

For a numeric property:

```json
{
  "hints": [
    {
      "name": "acme.batch-size",
      "values": [
        {"value": 16},
        {"value": 32},
        {"value": 64}
      ]
    }
  ]
}
```

Use proper JSON types when appropriate instead of always forcing numbers/booleans into strings. Even so, these hints are not authoritative sources for runtime domain constraints.

## 10. Suggesting Map Keys and Values

A `Map` property can hold dynamic keys and dynamic values:

```java
@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {

    private Map<String, String> channels = new LinkedHashMap<>();

    public Map<String, String> getChannels() {
        return channels;
    }

    public void setChannels(Map<String, String> channels) {
        this.channels = channels;
    }
}
```

Configuration:

```properties
acme.channels.billing=primary
acme.channels.inventory=secondary
```

For Maps, Spring Boot metadata allows suggesting **keys and values separately** via suffixes:

- `acme.channels.keys`: suggests Map key names.
- `acme.channels.values`: suggests entry values.
- **Do not use a hint named `acme.channels` expecting it to directly suggest the whole Map in a special way.**

Example:

```json
{
  "hints": [
    {
      "name": "acme.channels.keys",
      "values": [
        {
          "value": "billing",
          "description": "Billing workflow."
        },
        {
          "value": "inventory",
          "description": "Inventory workflow."
        }
      ]
    },
    {
      "name": "acme.channels.values",
      "values": [
        {
          "value": "primary",
          "description": "Primary processing channel."
        },
        {
          "value": "secondary",
          "description": "Secondary processing channel."
        }
      ]
    }
  ]
}
```

When editing:

```properties
acme.channels.billing=primary
```

the IDE can suggest key `billing` or `inventory` and value `primary`/`secondary`. Actual behavior depends on IDE support level.

**The `.keys` and `.values` suffixes in metadata are a hint protocol for Maps**, not two runtime properties to declare in `application.properties`. Do not write:

```properties
acme.channels.keys=billing
```

and assume Spring Boot treats this as a list of keys to create.

## 11. Value Providers: Context-Aware Smart Suggestions

Beyond fixed `values`, metadata can use `providers`. Providers declare how the IDE fetches suggestions based on the classpath, beans, profiles, or data types.

Common providers in Spring Boot 3.3 documentation:

| Provider | Function | Scenario |
| --- | --- | --- |
| `any` | Allows choosing values outside the suggested list | Value hints are only recommendations |
| `class-reference` | Suggests classes from project/classpath | Config holds a class name |
| `handle-as` | Treats as another data type for IDE support | String representing Resource/Charset/Locale/enum |
| `logger-name` | Suggests logger/group names | Map keys for log levels |
| `spring-bean-reference` | Suggests Spring bean names | String holding a bean name |
| `spring-profile-name` | Suggests profile names | Property using profile names |

A provider can have a `parameters` object depending on the provider type. IDEs are not required to support every provider, so the absence of a dropdown should not be viewed as a runtime error.

### 11.1. The `any` Provider

```json
{
  "hints": [
    {
      "name": "acme.storage-mode",
      "values": [
        {"value": "memory"},
        {"value": "disk"}
      ],
      "providers": [
        {
          "name": "any"
        }
      ]
    }
  ]
}
```

Meaning: the IDE can suggest `memory` and `disk` while still permitting other values at the metadata level. The `any` provider is not a way to make the Java Binder "accept every value regardless of target type": runtime conversion/validation remain unchanged.

### 11.2. The `class-reference` Provider

When a property stores a class name:

```json
{
  "hints": [
    {
      "name": "acme.plugin-class",
      "providers": [
        {
          "name": "class-reference",
          "parameters": {
            "target": "com.example.demo.spi.Plugin"
          }
        }
      ]
    }
  ]
}
```

The IDE can suggest classes matching base type `com.example.demo.spi.Plugin` on the classpath. `Plugin` is an illustrative interface defined by the project. The `target` parameter filters results; the provider also supports `concrete` when deciding whether to suggest only concrete classes.

### 11.3. The `handle-as` Provider

When the Java property is `String` yet its content represents a Resource path:

```json
{
  "hints": [
    {
      "name": "acme.template-location",
      "providers": [
        {
          "name": "handle-as",
          "parameters": {
            "target": "org.springframework.core.io.Resource"
          }
        }
      ]
    }
  ]
}
```

The IDE can provide suggestions tailored to Resource semantics such as `classpath:/templates/main.txt`. Still, the Java target remains `String`; metadata does not turn it into a `Resource` object or automatically open the file at runtime.

The `handle-as` provider can also be used with semantic types like Charset, Locale, MimeType, or enums when appropriate for the target.

### 11.4. The `logger-name` Provider

```json
{
  "hints": [
    {
      "name": "acme.logging.levels.keys",
      "providers": [
        {
          "name": "logger-name"
        }
      ]
    }
  ]
}
```

Example applicable when `acme.logging.levels` is a Map whose keys are logger names. The provider can help locate classes/packages/logger groups. Remember to write the `.keys` suffix when suggesting **Map keys**.

### 11.5. The `spring-bean-reference` Provider

```json
{
  "hints": [
    {
      "name": "acme.handler-bean",
      "providers": [
        {
          "name": "spring-bean-reference",
          "parameters": {
            "target": "com.example.demo.spi.Handler"
          }
        }
      ]
    }
  ]
}
```

The IDE can suggest bean names of type Handler. **The Binder does not automatically turn the string `"myHandler"` into a bean instance** just because provider metadata exists; if runtime needs a bean reference, application code must resolve the bean name via `ApplicationContext` or an appropriate injection mechanism.

### 11.6. The `spring-profile-name` Provider

```json
{
  "hints": [
    {
      "name": "acme.target-profile",
      "providers": [
        {
          "name": "spring-profile-name"
        }
      ]
    }
  ]
}
```

IDEs supporting this provider can suggest names of profiles existing in the project. Runtime handling of `acme.target-profile` still depends on application code; metadata does not activate that profile.

### 11.7. Order of Providers

Multiple providers can be declared for the same hint. The IDE uses the first provider **that it supports** in the declared list. Place the most semantically rich provider first, and fallback providers after it when appropriate.

```json
{
  "hints": [
    {
      "name": "acme.handler-bean",
      "providers": [
        {"name": "spring-bean-reference"},
        {"name": "any"}
      ]
    }
  ]
}
```

Do not expect every IDE to implement provider logic or render UI identically.

## 12. Deprecation Metadata: Announcing Old Keys and Replacement Paths

When renaming a public property, you may want to keep the old alias during a transition period while warning config authors.

For example:

- Old property: `acme.old-timeout`.
- New property: `acme.client.connect-timeout`.

Additional metadata can include:

```json
{
  "properties": [
    {
      "name": "acme.old-timeout",
      "type": "java.time.Duration",
      "description": "Legacy connection timeout setting.",
      "deprecation": {
        "reason": "Use the client-specific timeout property.",
        "replacement": "acme.client.connect-timeout"
      }
    }
  ]
}
```

IDEs supporting metadata can mark `acme.old-timeout` as deprecated and suggest `acme.client.connect-timeout`.

**Crucial limitation:** deprecation metadata does not remove the old key, does not transfer values from the old key to the new key, does not force the application to prefer the new key, and does not perform migration. Backward-compatibility runtime logic (if needed) must be implemented separately.

For example, if runtime continues accepting the old key, code must explicitly determine:

- If both new and old keys appear, which one wins?
- If the old key is absent, is there a fallback?
- Should a warning be logged when operators use the old key?
- When will the old alias be removed completely?

### 12.1. Fields Inside `deprecation`

Commonly used fields:

```json
{
  "deprecation": {
    "reason": "The old setting is no longer recommended.",
    "replacement": "acme.client.connect-timeout"
  }
}
```

Spring Boot 3.3 metadata also describes deprecation levels (such as `warning`/`error`) where supported; choose per the version contract and release policy. Do not use IDE warning levels in place of a runtime fail-fast mechanism.

### 12.2. Do Not Mark Deprecated Before the New Property Is Supported

If the replacement is not yet implemented at runtime, metadata could steer users to a non-working key. Ensure the replacement key exists in the corresponding release version; if not yet available, document the transition roadmap without giving error-inducing guidance.

## 13. End-to-End Practical Example

Suppose a microservice named Acme Gateway needs:

- `acme.gateway.mode`: String, default `safe`, suggestions `safe`/`fast`.
- `acme.gateway.connect-timeout`: Duration, default 3 seconds.
- `acme.gateway.client-tags`: Map whose keys and values need suggestions.
- `acme.gateway.custom-handler`: String pointing to a bean name.
- `acme.legacy-gateway-mode`: legacy key being phased out.

### 13.1. JavaBean Configuration

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.gateway")
public class GatewayProperties {

    private String mode = "safe";
    private Duration connectTimeout = Duration.ofSeconds(3);
    private Map<String, String> clientTags = new LinkedHashMap<>();
    private String customHandler;

    public String getMode() { return mode; }
    public void setMode(String mode) { this.mode = mode; }

    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Map<String, String> getClientTags() {
        return clientTags;
    }

    public void setClientTags(Map<String, String> clientTags) {
        this.clientTags = clientTags;
    }

    public String getCustomHandler() { return customHandler; }
    public void setCustomHandler(String customHandler) {
        this.customHandler = customHandler;
    }
}
```

Registration:

```java
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
```

Note that `@ConfigurationPropertiesScan` operates at runtime to register the bean, whereas the metadata processor operates at compile time. The two mechanisms are related but not identical.

### 13.2. Additional Metadata File

Place the following JSON verbatim into:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Content:

```json
{
  "properties": [
    {
      "name": "acme.gateway.mode",
      "description": "Gateway execution mode. Safe favors predictable behavior.",
      "defaultValue": "safe"
    },
    {
      "name": "acme.gateway.connect-timeout",
      "description": "Connection timeout. Specify a Duration unit such as 500ms or 3s.",
      "defaultValue": "3s"
    },
    {
      "name": "acme.legacy-gateway-mode",
      "type": "java.lang.String",
      "description": "Legacy gateway mode for older deployments.",
      "deprecation": {
        "reason": "The gateway settings are now grouped under acme.gateway.",
        "replacement": "acme.gateway.mode"
      }
    }
  ],
  "hints": [
    {
      "name": "acme.gateway.mode",
      "values": [
        {
          "value": "safe",
          "description": "Use the safe execution policy."
        },
        {
          "value": "fast",
          "description": "Prioritize throughput."
        }
      ]
    },
    {
      "name": "acme.gateway.client-tags.keys",
      "values": [
        {
          "value": "billing",
          "description": "Billing client tag."
        },
        {
          "value": "inventory",
          "description": "Inventory client tag."
        }
      ],
      "providers": [{"name": "any"}]
    },
    {
      "name": "acme.gateway.client-tags.values",
      "values": [
        {"value": "primary"},
        {"value": "secondary"}
      ],
      "providers": [{"name": "any"}]
    },
    {
      "name": "acme.gateway.custom-handler",
      "providers": [
        {
          "name": "spring-bean-reference",
          "parameters": {
            "target": "com.example.demo.spi.GatewayHandler"
          }
        }
      ]
    }
  ]
}
```

With the `@ConfigurationProperties` class in the example, the processor can auto-detect the new `acme.gateway.*` keys, and the additional file supplements descriptions/defaults/hints. `acme.legacy-gateway-mode` can be added to metadata even though it is not declared by the current class.

**Note for implementers:** `com.example.demo.spi.GatewayHandler` is an illustrative interface, not a built-in Spring Boot component. Change it to your project's actual interface if using the provider. Also, to preserve runtime support for `acme.legacy-gateway-mode`, you need code reading or mapping the alias; metadata does not do that.

### 13.3. Runtime Config Data

```properties
# src/main/resources/application.properties
acme.gateway.mode=fast
acme.gateway.connect-timeout=750ms
acme.gateway.client-tags.billing=primary
acme.gateway.client-tags.inventory=secondary
acme.gateway.custom-handler=defaultGatewayHandler
```

This configuration is read by runtime in the usual Spring Boot way. Additional metadata can help the IDE propose keys and values while editing the file, but **does not alter the precedence order** of Config Data, OS env, or CLI.

### 13.4. Expected Result

If the processor runs and merges successfully, output metadata contains:

- Property `acme.gateway.mode` with the added description/default.
- Property `acme.gateway.connect-timeout` with description and default 3s.
- Property `acme.legacy-gateway-mode` with deprecation/replacement.
- Hints `acme.gateway.mode`, `acme.gateway.client-tags.keys`, `acme.gateway.client-tags.values`, and `acme.gateway.custom-handler`.

Do not expect output JSON to match the input file **byte-for-byte**: the annotation processor can add fields such as type/sourceType, group items, or reorder metadata; what matters is that the needed metadata items are present with accurate names.

## 14. Configuring the Annotation Processor with Maven

If the project uses Maven with Spring Boot 3.3 version management (e.g., Spring Boot parent POM or an appropriate BOM), you can declare:

```xml
<dependencies>
    <!-- Other Spring Boot dependencies... -->

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-configuration-processor</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
```

`<optional>true</optional>` prevents propagating the processor dependency as a mandatory dependency to projects depending on your library. In many Maven setups with Spring Boot build configuration, the annotation processor is discovered and run during compilation.

If the project heavily customizes `maven-compiler-plugin`, you may need to configure an explicit **annotation processor path** to ensure the processor actually runs. Exact configuration depends on the JDK/Maven Compiler Plugin in use; do not rely solely on the dependency appearing in `pom.xml` to conclude metadata was definitely generated.

Example build command:

```bash
./mvnw clean compile
```

Or on Windows:

```powershell
.\mvnw.cmd clean compile
```

Inspect the generated file:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

If the additional file is valid yet output lacks new hints/properties, check whether the processor is enabled, the resource location at compile time, and compiler plugin settings.

### 14.1. `annotationProcessorPaths` Example When Needed

With a customized Maven Compiler Plugin setup, one approach is:

```xml
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
                        <version>${spring-boot.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
```

In the example above, the project must have a `spring-boot.version` property or equivalent version management; do not copy it as a standalone configuration without confirming the project's versioning system. When specifying annotation processors manually, ensure other active processors (Lombok, MapStruct...) are not accidentally omitted from the processor path list. Do not alter build configuration if the existing workflow already produces complete metadata.

## 15. Configuration with Gradle

Example `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
```

Plugin versions here are merely **illustrative for the 3.3 line**, not a requirement to use these exact patch versions. In real projects, align plugin and dependency versions according to shared build management.

Verification command:

```bash
./gradlew clean compileJava
```

Or on Windows:

```powershell
.\gradlew.bat clean compileJava
```

Output usually resides at:

```text
build/classes/java/main/META-INF/spring-configuration-metadata.json
```

### Note on Task Order When Using an Additional File

With certain Gradle configurations or custom resource processing, ensure `META-INF/additional-spring-configuration-metadata.json` is present where the annotation processor can read it **while `compileJava` runs**. If the processor does not receive the additional file, output contains only auto-generated metadata.

The `processResources`, `compileJava` tasks, and source set configurations can affect whether resources appear on the compilation path. When addressing this, inspect task ordering and inputs in the project, then adjust dependencies between tasks so full resources are available. **Do not blindly add a task dependency that could cause a cycle**; use `--info` or Gradle's task graph to inspect the actual pipeline.

### Kotlin Projects

For Kotlin, configuration metadata generation may require an appropriate annotation processing mechanism such as KAPT, depending on build setup and Spring Boot version. Java's `annotationProcessor` example does not automatically guarantee the processor runs on all Kotlin sources. In Kotlin projects, configure the processor per Kotlin/Gradle documentation instead of copying the Java Gradle snippet verbatim.

## 16. Inspecting Metadata After Building

### 16.1. Viewing the Output File

After Maven compile:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

After Gradle compileJava:

```text
build/classes/java/main/META-INF/spring-configuration-metadata.json
```

Open the file and search for key names:

```text
acme.gateway.mode
acme.gateway.connect-timeout
acme.legacy-gateway-mode
acme.gateway.client-tags.keys
```

Items may appear in different arrays. `hints` holds `.keys`/`.values`; `properties` holds actual property definitions.

### 16.2. Inspecting with `jq` if Available

Example checking a property:

```bash
jq '.properties[] | select(.name == "acme.gateway.mode")' \
  target/classes/META-INF/spring-configuration-metadata.json
```

Checking hints:

```bash
jq '.hints[] | select(.name == "acme.gateway.mode")' \
  target/classes/META-INF/spring-configuration-metadata.json
```

Checking deprecated:

```bash
jq '.properties[] | select(.name == "acme.legacy-gateway-mode")' \
  target/classes/META-INF/spring-configuration-metadata.json
```

If `jq` is not installed, open in an IDE or use another JSON viewer. Do not rely solely on plain text string search, since a key may appear in `hints` without appearing in `properties`, or reside in another module.

### 16.3. Validating Input JSON

This is a JSON file, not YAML:

```json
{
  "properties": [
    {
      "name": "acme.mode",
      "description": "Execution mode."
    }
  ]
}
```

Common mistakes causing parse failures:

- Forgetting double quotes around keys.
- Using `//` or `#` comments.
- Leaving a trailing comma after the last item.
- Incorrectly escaping `\` inside Strings.
- Including two separate root JSON objects instead of one object.
- Misspelling `properties` as `property` or `hints` as `hint`.
- Using a `defaultValue` whose JSON type does not fit what is being described.

A standard JSON validator can catch syntax errors. The next step is still to inspect the merged metadata output because **valid JSON does not guarantee valid schema/key names**.

### 16.4. Inspecting Metadata Inside a JAR

For an ordinary JAR, `META-INF/spring-configuration-metadata.json` may live at the JAR root. For a Spring Boot executable JAR, application resources may reside under:

```text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

For dependent libraries, metadata resides inside their dependency JARs. Example listing contents:

```bash
jar tf build/libs/my-app.jar | grep spring-configuration-metadata.json
```

Adjust the path to match your artifact name and output location. A successful build alone does not prove metadata was packaged at the right place for consumers; inspect the published artifact if the project builds a library for other modules' IDEs to use.

## 17. Why Does the IDE Not Show Suggestions Even Though the JSON Is Valid?

There are many causes unrelated to syntax directly:

1. **Annotation processor did not run:** no `spring-configuration-metadata.json` was generated.
2. **Additional file in wrong location:** processor could not find `META-INF/additional-spring-configuration-metadata.json`.
3. **Invalid JSON file:** parse failure or processor ignored malformed content.
4. **Non-canonical property name:** hint `acme.gateway.clientTags` does not match canonical property `acme.gateway.client-tags`.
5. **Inspecting stale output:** did not clean compile or IDE uses stale cache/index.
6. **Opened a different module:** IDE may need a dependency on the module containing metadata.
7. **IDE/plugin does not support the provider:** `spring-bean-reference` or `handle-as` support varies across tools.
8. **Property does not exist at runtime:** metadata has the key, but Java code does not read it, having no runtime effect.
9. **Metadata only in source, unmerged:** additional file exists, yet generated output lacks the hint/property.
10. **Build system did not copy/package metadata:** generated file existed temporarily, yet the artifact lacks it.

Troubleshooting should trace from **source file -> processor execution -> generated file -> packaged artifact -> IDE index**, instead of immediately tweaking JSON or bumping Spring Boot versions.

### 17.1. Distinguishing Suggestion Issues from Binding Issues

If the IDE does not propose `acme.gateway.mode`, yet the application binds the value from `application.yaml`, that is a **metadata/tooling** issue, not necessarily a runtime issue.

Conversely, if the IDE suggests the key yet runtime always ignores it, check `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`, prefix names, getters/setters or constructor binding, and whether code actually uses the property.

### 17.2. Right Name but Wrong Described Default

If additional metadata specifies:

```json
{
  "properties": [
    {
      "name": "acme.gateway.connect-timeout",
      "defaultValue": "10s"
    }
  ]
}
```

while the class has:

```java
private Duration connectTimeout = Duration.ofSeconds(3);
```

then the IDE may report default 10s while runtime keeps 3s when the key is missing. This is a **documentation discrepancy**, not the annotation processor changing the default. Synchronize metadata with code or change the actual runtime default.

## 18. Common Mistakes When Adding Manual Properties

### Mistake 1 — Treating the Additional File as Application Configuration

```json
{
  "properties": [
    {"name": "server.port", "defaultValue": 9090}
  ]
}
```

It **does not change the server port to 9090**. To change the runtime port, use:

```properties
server.port=9090
```

or effective programmatic configuration. Metadata only describes values for tooling.

### Mistake 2 — Adding a New Property Expecting Java to Gain a Field

```json
{
  "properties": [
    {"name": "acme.experimental-flag", "type": "java.lang.Boolean"}
  ]
}
```

No getter `isExperimentalFlag()` or Java field is generated. You must implement the property in runtime code or use `@ConfigurationProperties`.

### Mistake 3 — Declaring a Hint with the Wrong Name

```json
{
  "hints": [
    {"name": "acme.gateway.connectTimeout", "values": [{"value": "5s"}]}
  ]
}
```

Metadata should use the canonical name:

```text
acme.gateway.connect-timeout
```

CamelCase names may fail to match the target property in the IDE.

### Mistake 4 — Confusing Map Keys with Map Values

If the target is `Map<String,String> clientTags`, use:

```json
{"name": "acme.gateway.client-tags.keys"}
```

to suggest keys, and:

```json
{"name": "acme.gateway.client-tags.values"}
```

to suggest values. Adding a hint on `acme.gateway.client-tags` does not replace these two specific suffixes.

### Mistake 5 — Having Enum-Like Values in Metadata While Code Accepts Any String

When the Java property is `String`, hints are not validation. To restrict runtime to a fixed set of values, use an enum or explicit checks. Avoid making the IDE suggest a seemingly "strict" set while code accepts invalid values.

### Mistake 6 — Using an Unsupported Deprecated Replacement

If metadata points migration to `acme.new-key` while the current release does not read the new key yet, operators may create ineffective configurations. Only suggest replacements genuinely supported at runtime.

### Mistake 7 — Skipping the Annotation Processor

Simply committing `additional-spring-configuration-metadata.json` is not enough when the build does not run the processor. Inspect generated output to verify.

### Mistake 8 — Editing the Output File Directly

Editing `target/classes/META-INF/spring-configuration-metadata.json` may look right temporarily, yet vanishes after a clean build. The persistent file is source `additional-...json`.

### Mistake 9 — Redundant Unnecessary Manual Groups

A property does not require a user-declared group. If the processor already generated the group from `@ConfigurationProperties`, there is usually no need to repeat it in the additional file. Keep JSON focused for easier maintenance.

### Mistake 10 — Including Sensitive Data in Metadata

```json
{
  "properties": [
    {
      "name": "acme.auth.token",
      "defaultValue": "real-secret-token-here"
    }
  ]
}
```

This is a dangerous practice because metadata can be packaged and published with artifacts or displayed in tools. Metadata is not a secret store; only describe how to supply the secret via secure sources, never record real credentials.

### Mistake 11 — Using Providers as Runtime Resolvers

`spring-bean-reference` helps the IDE suggest bean names; code still needs to resolve the String name into a bean reference. `handle-as` helps the IDE understand semantic types; runtime code does not automatically turn a String into a Resource without appropriate logic.

### Mistake 12 — Failing to Check Metadata After Refactoring

Renaming Java field `connectTimeout` to `requestTimeout` changes the canonical key from `acme.gateway.connect-timeout` to `acme.gateway.request-timeout` if no alias remains. Additional metadata could continue describing the old key as a new property, even though runtime dropped it. When refactoring, update source JSON and migration strategies together.

## 19. Recommended Workflow When Developing a New Property

### Step 1 — Declare the Runtime Contract

Decide:

- Prefix and canonical property name.
- Java target type: String, enum, Duration, DataSize, List, Map, object...
- Execution default, if any.
- Valid values and units.
- Whether profile/environment overrides are supported.
- If renamed from an old key: migration rules and precedence.

### Step 2 — Use `@ConfigurationProperties` When Appropriate

Declare a type-safe Java model and register the bean so runtime binding works. Do not skip this automatic mechanism just because you know how to write JSON metadata manually.

### Step 3 — Create or Edit Additional Metadata

Add only information the processor cannot infer or that needs refinement: `description`, accurately recorded `defaultValue`, `deprecation`, `hints`, and special runtime keys outside the model.

### Step 4 — Run the Build

Enable the annotation processor, ensure resources are visible at compile time, and check for JSON/processor errors. Do not treat stale output as proof.

### Step 5 — Inspect Generated Metadata

Locate the exact `name` item in `properties` and corresponding items in `hints`. Distinguish real properties from suggestion-only hints.

### Step 6 — Check the IDE Experience

Open `application.properties` or `application.yaml`, test autocomplete, and hover descriptions. Display capabilities may vary by IDE/plugin and version.

### Step 7 — Verify Runtime Behavior Separately

Run tests/apps with values from Config Data/OS env/CLI; verify that the bean or service **actually receives the right values**, right defaults, and right validation. **Do not use generated metadata as sole proof of runtime behavior.**

## 20. Decision Table: When Is Additional Metadata Needed?

| Need | Suitable Approach |
| --- | --- |
| A `@ConfigurationProperties` bean with standard fields | Let the processor auto-generate most metadata |
| Field generated by processor, yet description is unclear | Add `properties` with `name` and `description` |
| Runtime default exists, yet metadata lacks it | Add `defaultValue` matching the runtime default |
| A property read directly from `Environment` | Add manual property with `name`, `type`, `description` |
| A String with a few common choices | Add `hints.values`; validate at runtime via another mechanism if needed |
| A Map with suggested key/value vocabulary | Use `.keys` and `.values` hints |
| A String holding a class name | `class-reference` provider |
| A String holding a bean name | `spring-bean-reference` provider |
| A String holding a Resource path | `handle-as` provider with target Resource |
| An old key with a replacement key | Add `deprecation.reason`/`replacement` and implement runtime compatibility |
| Want to change the runtime default value | Modify Java default/Config Data, **not only metadata** |
| Want to reject invalid values at startup | Enum, Bean Validation, custom validation/conversion |
| Want a property bound into a new field | Modify/register Java configuration properties, not just JSON file |
| IDE does not suggest key | Check processor, merged metadata, classpath, and IDE before editing runtime code |

## 21. Official References

- **Spring Boot 3.3 — Configuration Metadata**, including Metadata Format, Providing Manual Hints, and Generating Your Own Metadata by Using the Annotation Processor: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html
- **Spring Boot 3.3 — Metadata Format**, describing `groups`, `properties`, `hints` arrays and item attributes: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html
- **Spring Boot 3.3 — Providing Manual Hints**, including Map `.keys`/`.values` and standard value providers: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/manual-hints.html
- **Spring Boot 3.3 — Annotation Processor**, Adding Additional Metadata section: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html
- **Spring Boot 3.3.0-M2 — Configuration Metadata Reference** (3.3 development-line docs with additional metadata section): https://docs.spring.io/spring-boot/docs/3.3.0-M2/reference/html/configuration-metadata.html
- **Spring Boot 3.3 — Externalized Configuration**, `@ConfigurationProperties` binding and `PropertySource` precedence sections: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html

## 22. Summary

1. `additional-spring-configuration-metadata.json` is placed in `src/main/resources/META-INF/` and is **merged by the annotation processor at build time**, not as a runtime property source.
2. The file uses the metadata schema with `groups`, `properties`, and `hints` arrays; only declare the sections actually used.
3. For properties discovered by the processor within the module, additional metadata can override `description`, `defaultValue`, and `deprecation` **when specified**; undiscovered properties can be added as new entries.
4. Use `hints.values` and `hints.providers` to add IDE suggestions, but **do not treat them as validation or runtime conversion**.
5. For Maps, append `.keys` and `.values` for the two different suggestion kinds.
6. `deprecation.replacement` communicates the key migration direction, yet does not rewrite configurations or create runtime aliases.
7. What to verify is `META-INF/spring-configuration-metadata.json` created after compilation, and when publishing, check that metadata is present in the appropriate artifact.
8. All default/type/deprecation information must reflect the real runtime contract; keep metadata synchronized with classes, configurations, and tests.

**Final principle:** Additional metadata helps **tools understand configuration better**, rather than making **the application behave differently**. Use it as machine-readable documentation for IDEs and developers, while runtime behavior continues to be determined by Config Data, Java code, the Binder, and validation.
