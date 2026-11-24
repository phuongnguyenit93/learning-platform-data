# Distinguishing Auto-Configuration Metadata and Configuration Properties Metadata

## 1. Why Does Spring Boot Have Multiple Metadata Types?

When building a Spring Boot library, you often encounter several files under the META-INF directory. Their names look quite similar, but each file solves a different problem:

- Spring Boot needs to know which auto-configuration classes are candidates to be imported into an application.
- Spring Boot can use condition metadata to filter out auto-configurations that are definitely inapplicable early, reducing startup work.
- The IDE needs to know which properties a library supports, their data types, descriptions, default values, and suggested options for completing configuration in application.yml.

These three needs do not share a single file. With Spring Boot 3.3, you need to distinguish at least three artifacts:

1. META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
2. META-INF/spring-autoconfigure-metadata.properties
3. META-INF/spring-configuration-metadata.json

In addition, a library can provide a manually written property metadata file:

META-INF/additional-spring-configuration-metadata.json

This lesson explains the purpose, generation time, where Spring Boot/the IDE uses each file, and how to inspect each file in the JAR. Examples use Java 17+, Maven, and Spring Boot 3.3.13.

## 2. Quick Comparison Table

| File | Who creates it? | Who uses it? | Purpose |
|---|---|---|---|
| AutoConfiguration.imports | Library author maintains in resources | Spring Boot when discovering auto-configuration candidates | Declares which classes are eligible to participate in the auto-configuration mechanism |
| spring-autoconfigure-metadata.properties | Annotation processor spring-boot-autoconfigure-processor | Spring Boot during the early candidate filtering phase | Optimizes startup by filtering out certain configurations early that cannot match known conditions |
| spring-configuration-metadata.json | Annotation processor spring-boot-configuration-processor, can be supplemented manually | IDEs and configuration support tools | Describes groups, properties, types, defaults, deprecations, and hints for configuration authors |
| additional-spring-configuration-metadata.json | Library author writes manually | Configuration processor during build | Supplements or refines property metadata before generating the main JSON file |

Key points to remember:

- **Imports answers “which auto-configuration classes exist?”**
- **Auto-config metadata answers “which classes can be filtered out early based on known conditions?”**
- **Configuration metadata answers “which keys can users configure and how should the IDE guide them?”**

The property metadata file does not cause an auto-configuration to be imported. The auto-config metadata file also does not generate suggestions for application.yml. One file can exist without the other two; they serve different flows.

## 3. AutoConfiguration.imports: The List of Auto-Configuration Candidates

### 3.1. Role

Spring Boot reads the file:

META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

from JARs on the classpath. Each line is the fully qualified name of an auto-configuration class. For example:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
com.acme.catalog.autoconfigure.CatalogWebAutoConfiguration
```

Spring Boot uses this list in the @EnableAutoConfiguration mechanism (included in @SpringBootApplication) to find auto-configurations that may apply.

This file is the **candidate registration input**. If a class is not declared in imports and is not loaded through a separate path, Spring Boot does not automatically discover the class just because it has the @AutoConfiguration annotation.

Comments starting with the # character can be added. Each class should reside in a dedicated package for auto-configuration and should not be picked up by regular component scanning.

### 3.2. Who Creates This File?

In typical setups, the library author **creates this resource file manually**. The two annotation processors discussed in later sections do not replace the candidate-list declaration role of the imports file.

Source structure:

```text
catalog-autoconfigure/
└── src/main/
    ├── java/
    │   └── com/acme/catalog/autoconfigure/
    │       └── CatalogAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Contents of the imports file:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

When building the JAR, the resource is packaged with the exact path under META-INF/spring/. Do not rename the file arbitrarily, do not misplace it under a Java package, and do not write bean names instead of class names.

### 3.3. Do Not Confuse Imports with Condition Metadata

Suppose a JAR has imports but does not have spring-autoconfigure-metadata.properties. Spring Boot still knows which candidates to consider and can still evaluate conditions through the normal mechanism.

Conversely, having a condition metadata file without declaring the auto-configuration class in imports does not make the condition file a replacement list for imports. The candidate list and condition metadata are two separate pieces.

### 3.4. Relationship with spring.factories

In older Spring Boot versions, libraries typically registered auto-configuration via the org.springframework.boot.autoconfigure.EnableAutoConfiguration key in META-INF/spring.factories. The modern way to declare auto-configuration in Spring Boot 3.x is the AutoConfiguration.imports file.

spring.factories can still be used for some other SPIs/extension points; that does not make it a candidate-list replacement for imports in Boot 3.x.

## 4. spring-autoconfigure-metadata.properties: Condition Metadata for Early Filtering

### 4.1. Role

The file:

META-INF/spring-autoconfigure-metadata.properties

is generated by the annotation processor:

org.springframework.boot:spring-boot-autoconfigure-processor

The processor collects certain conditions that can be derived from the auto-configuration source and writes metadata into the properties file. Spring Boot can read this file to **eagerly filter** auto-configurations that definitely do not apply before executing the full configuration steps.

The main goal is **optimizing startup time**, especially when an application has many auto-configurations from multiple starters.

For example: an auto-configuration only applies when the class com.vendor.sdk.Client is on the classpath. If the metadata lets Boot know about that classpath condition, Boot can filter out the candidate early when the class does not exist.

### 4.2. This Is Not a Candidate List

This file is not responsible for declaring all auto-configuration classes. Declaration is still handled by AutoConfiguration.imports.

You also should not manually write this file to replace condition annotations in code. Real conditions still need to be declared in the auto-configuration using annotations such as:

- @ConditionalOnClass
- @ConditionalOnMissingClass
- @ConditionalOnBean
- @ConditionalOnMissingBean
- Other conditions suited to the requirements

The processor only creates a metadata representation for conditions that it supports/can read. It does not turn arbitrary custom Java logic into a pre-evaluatable metadata expression.

### 4.3. What Happens If This Metadata File Does Not Exist?

Normally, auto-configuration still works. Spring Boot still reads the candidate list and evaluates conditions through the standard process. The application may lose the early-filtering benefit, but lacking this metadata file **does not mean auto-configuration is disabled**.

This is an important difference compared to imports:

- Missing imports: the class is not declared through the auto-configuration mechanism.
- Missing auto-config metadata: the candidate can still be considered; Boot simply lacks the corresponding optimization index.

### 4.4. Generating the File with the Processor

With Maven, you can configure spring-boot-autoconfigure-processor in the annotation processor path of the Maven Compiler Plugin. A complete configuration example is in section 7.

With Gradle, declare the processor in the annotationProcessor configuration:

```groovy
dependencies {
    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )
}
```

Do not include the processor in the runtime dependencies of a consuming application. This is a tool for compiling the library module.

## 5. spring-configuration-metadata.json: Property Metadata for IDEs

### 5.1. Role

The file:

META-INF/spring-configuration-metadata.json

describes the configuration keys that a library or Spring Boot supports. Compatible IDEs can use this metadata to:

- Suggest key names when users type in application.properties or application.yml.
- Suggest appropriate data types.
- Display descriptions and default values.
- Provide valid values or examples via hints.
- Mark deprecated properties and suggest replacement keys.

Most of this file is generated at compile time by the processor:

org.springframework.boot:spring-boot-configuration-processor

The processor finds classes/methods annotated with @ConfigurationProperties and analyzes properties from constructors, record components, getters/setters, and supported structures.

### 5.2. Metadata Is Not a Runtime Binding Mechanism

This is the most important point to remember:

**The JSON file only describes configuration for tooling support; it does not automatically register beans, does not automatically create properties, and does not replace Spring Boot's Binder.**

For example, if the metadata declares:

```json
{
  "properties": [
    {
      "name": "acme.catalog.enabled",
      "type": "java.lang.Boolean",
      "description": "Whether the catalog integration is enabled."
    }
  ]
}
```

The IDE can suggest acme.catalog.enabled. However, if the application does not have a corresponding @ConfigurationProperties class, does not register the properties bean, and has no code reading that key, the JSON metadata does not make the feature turn on/off automatically.

Runtime binding still requires the proper code structure, such as @ConfigurationProperties registered via @EnableConfigurationProperties or the corresponding scan mechanism. Conditions such as @ConditionalOnProperty are still evaluated from Environment; they do not read the JSON metadata file to decide.

### 5.3. Data Groups in the JSON

The metadata has these main sections:

| Section | Contents |
|---|---|
| groups | Groups/namespaces containing related properties; a group does not carry a configuration value by itself |
| properties | List of configuration keys, types, descriptions, sources, and defaults |
| hints | Valid value suggestions, option descriptions, or providers supplying suggestion content |
| ignored | Properties intentionally excluded from the generated metadata list |

A condensed example:

```json
{
  "groups": [
    {
      "name": "acme.catalog",
      "type": "com.acme.catalog.CatalogProperties",
      "sourceType": "com.acme.catalog.CatalogProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.catalog.enabled",
      "type": "java.lang.Boolean",
      "description": "Whether the catalog integration is enabled.",
      "defaultValue": false,
      "sourceType": "com.acme.catalog.CatalogProperties"
    },
    {
      "name": "acme.catalog.timeout",
      "type": "java.time.Duration",
      "description": "Maximum time to wait for a catalog response.",
      "defaultValue": "3s",
      "sourceType": "com.acme.catalog.CatalogProperties"
    }
  ],
  "hints": [
    {
      "name": "acme.catalog.mode",
      "values": [
        {
          "value": "fast",
          "description": "Prioritize throughput."
        },
        {
          "value": "safe",
          "description": "Prefer conservative request behavior."
        }
      ]
    }
  ]
}
```

This is illustrative JSON for understanding the structure, not the exact processor output for every class. Property ordering, sourceType, and discovered values depend on the source code.

### 5.4. Meaning of Metadata Attributes

| Field | Meaning |
|---|---|
| name | Full name of the group/property |
| type | Java type or generic type of the property |
| description | Description for configuration authors |
| sourceType | Class contributing the property/group |
| sourceMethod | Method contributing the group/property if any |
| defaultValue | Known or declared default value |
| deprecation | Information about a deprecated property |
| values | Suggested choices for a property |
| providers | Providers that can supply dynamic suggestions to the IDE |

Property names in metadata typically use lowercase separated by dots, for example acme.catalog.request-timeout. This is also the canonical form that should be used in configuration documentation.

### 5.5. Deprecation Metadata

A property can contain:

```json
{
  "name": "acme.catalog.legacy-mode",
  "type": "java.lang.String",
  "deprecation": {
    "level": "warning",
    "reason": "Use acme.catalog.mode instead.",
    "replacement": "acme.catalog.mode",
    "since": "1.4"
  }
}
```

Meaning:

- level can be warning or error; if omitted, it defaults to warning.
- reason explains why it is deprecated.
- replacement indicates the replacement property.
- since records the version when deprecation started.

With the warning level, the property can still be bound to support the transition period. With the error level, the property is no longer managed and is not bound according to the deprecation metadata. Choose the level that matches the library's backward-compatibility policy.

Deprecation metadata only describes status and supports IDEs. If an old property needs to keep working as an alias, the library's binding/migration code must implement that; merely adding JSON does not automatically transfer the old value to the new key.

## 6. additional-spring-configuration-metadata.json: Supplementing Metadata Manually

Not every property is discovered automatically. Some cases require supplementation:

- Properties read manually from Environment, not residing in a @ConfigurationProperties bean.
- Dynamic defaults or collection defaults that the processor cannot infer accurately.
- Descriptions that need to be more specific.
- Suggested values for the IDE.
- Deprecation or replacement information.
- Metadata for properties not declared using standard Java structures.

Create the source file:

src/main/resources/META-INF/additional-spring-configuration-metadata.json

Example:

```json
{
  "properties": [
    {
      "name": "acme.catalog.timeout",
      "type": "java.time.Duration",
      "description": "Maximum time to wait for a catalog response.",
      "defaultValue": "3s"
    },
    {
      "name": "acme.catalog.legacy-mode",
      "type": "java.lang.String",
      "deprecation": {
        "level": "warning",
        "reason": "Use acme.catalog.mode instead.",
        "replacement": "acme.catalog.mode",
        "since": "1.4"
      }
    }
  ],
  "hints": [
    {
      "name": "acme.catalog.mode",
      "values": [
        {
          "value": "fast",
          "description": "Prioritize throughput."
        },
        {
          "value": "safe",
          "description": "Prefer conservative request behavior."
        }
      ]
    }
  ],
  "ignored": {
    "properties": [
      {
        "name": "acme.catalog.internal-cache-path"
      }
    ]
  }
}
```

The configuration processor will merge these manual entries into the main metadata file spring-configuration-metadata.json.

Important merge rules:

1. If a property was already discovered automatically, manual metadata can override attributes such as description, defaultValue, and deprecation.
2. If a property was not discovered in the module, the manual entry can be added to the metadata.
3. Entries in ignored.properties are used to exclude the corresponding properties from the generated metadata properties list.
4. The additional file is optional; there is no need to create it if there is no supplemental metadata.

**The additional file is not a runtime configuration file.** Putting a key in this file does not make Binder recognize that key, does not create beans, and does not automatically change auto-configuration behavior. If you want a key to actually work, library code must read/bind that key.

## 7. Complete Example: Generating Both Metadata Types with Maven

This example creates a library module catalog-autoconfigure. The module has:

- An auto-configuration class declared via imports.
- A properties class for Binder to receive configuration.
- An illustrative client bean.
- Two annotation processors to generate build-time metadata.
- A manually written additional metadata file to add hints and deprecation.

### 7.1. Directory Structure

```text
catalog-autoconfigure/
├── pom.xml
└── src/
    └── main/
        ├── java/com/acme/catalog/
        │   ├── CatalogClient.java
        │   ├── CatalogProperties.java
        │   └── autoconfigure/
        │       └── CatalogAutoConfiguration.java
        └── resources/META-INF/
            ├── additional-spring-configuration-metadata.json
            └── spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.acme</groupId>
    <artifactId>catalog-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
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
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-configuration-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Both processors are placed in annotationProcessorPaths, so they serve compilation. They are not dependencies that consuming applications need at runtime. Keep the processor versions synchronized with the Spring Boot version the module uses.

With Gradle, the equivalent configuration is:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")
    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )
    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )
}
```

### 7.3. CatalogProperties.java

```java
package com.acme.catalog;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.catalog")
public class CatalogProperties {

    /**
     * Whether the catalog integration is enabled.
     */
    private boolean enabled = false;

    /**
     * Maximum time to wait for a catalog response.
     */
    private Duration timeout;

    /**
     * Selects the request handling mode.
     */
    private String mode = "fast";

    /**
     * Legacy timeout key retained during migration.
     */
    private Duration legacyTimeout;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public String getMode() {
        return mode;
    }

    public void setMode(String mode) {
        this.mode = mode;
    }

    public Duration getLegacyTimeout() {
        return legacyTimeout;
    }

    public void setLegacyTimeout(Duration legacyTimeout) {
        this.legacyTimeout = legacyTimeout;
    }
}
```

The configuration processor can use @ConfigurationProperties and JavaBean accessors to discover properties. Field Javadoc is used to generate descriptions. Simple defaults declared directly in the source can be inferred.

In the example, timeout is not assigned directly on the field. The auto-configuration will use a 3-second default when both the new key and old key are missing; additional metadata describes that effective default for the IDE.

### 7.4. CatalogClient.java

```java
package com.acme.catalog;

import java.time.Duration;

public record CatalogClient(Duration timeout, String mode) {
}
```

This is a minimal client type to illustrate receiving configuration. In a real library, the client would call the catalog's SDK or service.

### 7.5. CatalogAutoConfiguration.java

```java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

import com.acme.catalog.CatalogClient;
import com.acme.catalog.CatalogProperties;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(CatalogClient.class)
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    CatalogClient catalogClient(CatalogProperties properties) {
        Duration timeout = properties.getTimeout();

        if (timeout == null) {
            timeout = properties.getLegacyTimeout();
        }

        if (timeout == null) {
            timeout = Duration.ofSeconds(3);
        }

        return new CatalogClient(timeout, properties.getMode());
    }
}
```

Here:

- @AutoConfiguration marks the auto-configuration class.
- @ConditionalOnClass and @ConditionalOnProperty determine when the configuration applies.
- @EnableConfigurationProperties registers the properties bean so Binder binds values from Environment.
- @ConditionalOnMissingBean allows the application to replace the default client.
- Java code performs the fallback from the old key to the new key; deprecation metadata only notifies the IDE and does not write fallback logic automatically.

### 7.6. AutoConfiguration.imports

File:

src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

Contents:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

This is a file maintained by the library author. When packaging the JAR, Spring Boot uses this file to discover CatalogAutoConfiguration.

### 7.7. additional-spring-configuration-metadata.json

File:

src/main/resources/META-INF/additional-spring-configuration-metadata.json

Contents:

```json
{
  "properties": [
    {
      "name": "acme.catalog.timeout",
      "type": "java.time.Duration",
      "description": "Maximum time to wait for a catalog response.",
      "defaultValue": "3s"
    },
    {
      "name": "acme.catalog.legacy-timeout",
      "type": "java.time.Duration",
      "deprecation": {
        "level": "warning",
        "reason": "Use acme.catalog.timeout instead.",
        "replacement": "acme.catalog.timeout",
        "since": "1.4"
      }
    }
  ],
  "hints": [
    {
      "name": "acme.catalog.mode",
      "values": [
        {
          "value": "fast",
          "description": "Prioritize throughput."
        },
        {
          "value": "safe",
          "description": "Prefer conservative request behavior."
        }
      ]
    }
  ]
}
```

The processor will merge this information with the metadata automatically discovered from CatalogProperties. In the example, the legacy key is still bound and used by the code when the new key is not provided; the metadata only marks it as deprecated and guides users to the new key.

### 7.8. Building and Inspecting the JAR

From the directory containing pom.xml, run:

```bash
mvn clean package
```

After a successful build, the JAR is expected to contain the main resources:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
META-INF/spring-configuration-metadata.json
META-INF/additional-spring-configuration-metadata.json
```

Inspect the file list:

```bash
jar tf target/catalog-autoconfigure-1.0.0.jar
```

Metadata files generated by processors typically reside in the module's output directory before packaging. The imports file and additional metadata come from the project's resources.

You can separately inspect the JSON contents in target/classes/META-INF/spring-configuration-metadata.json to confirm the keys exist:

- acme.catalog.enabled
- acme.catalog.timeout
- acme.catalog.mode
- acme.catalog.legacy-timeout

JSON structure and entry ordering may vary depending on the processor; verify keys, types, descriptions, defaults, and deprecations rather than comparing the entire file in a fixed order.

### 7.9. Testing the IDE Experience

Install the library JAR into the local repository or publish it to a test repository, then add it as a dependency of a small Spring Boot application.

In application.yml, try typing:

```yaml
acme:
  catalog:
    enabled: true
    timeout: 5s
    mode: safe
```

In an IDE that supports Spring configuration metadata, users should receive:

- Suggestions for the keys acme.catalog.enabled, timeout, and mode.
- Boolean type for enabled.
- Duration type for timeout.
- Descriptions for each property.
- Value suggestions fast/safe for mode.
- Deprecation information for legacy-timeout if the old key is entered.

If the IDE does not show suggestions, verify that the JAR contains the JSON file, the processor ran during compile, the consuming application uses the right JAR version, and the IDE supports Spring Boot configuration metadata.

## 8. Why Are Two Annotation Processors Needed?

| Processor | Generated Artifact | Contents | Benefit |
|---|---|---|---|
| spring-boot-autoconfigure-processor | spring-autoconfigure-metadata.properties | Metadata of supported conditions on auto-configurations | Helps Spring Boot filter out inapplicable candidates early |
| spring-boot-configuration-processor | spring-configuration-metadata.json | Property groups, keys, types, descriptions, defaults, hints, and deprecations | Helps IDEs and configuration support tools |

They can run together in one module, as in the Maven example above. There is no requirement to choose one over the other; each processor generates a different artifact.

### 8.1. If Only Using the Autoconfigure Processor

Auto-configuration can benefit from early-filtering optimization, but users do not necessarily receive rich property suggestions in the IDE. If the library has @ConfigurationProperties, you should also enable the configuration processor.

### 8.2. If Only Using the Configuration Processor

The IDE can understand the properties, but that does not help Spring Boot find auto-configuration classes. You still have to declare candidates via imports and may lose the early condition-filtering benefit if autoconfigure metadata is missing.

### 8.3. If Using Neither Processor

The application can still run if imports and runtime code are correct. However:

- No condition metadata is generated for early filtering.
- No JSON file is automatically generated for IDEs.
- Users have less completion/documentation support.
- The library needs to maintain metadata manually if it wants to provide a similar experience.

Do not add a processor just because you saw a META-INF file in another library's JAR; identify the actual need and the module that actually contains the corresponding source.

## 9. Creation and Usage Timing: A Lifecycle View

```text
SOURCE CODE + RESOURCES
        |
        | Maven/Gradle compile
        v
ANNOTATION PROCESSORS
        |
        +--> spring-autoconfigure-metadata.properties
        |
        +--> spring-configuration-metadata.json
        |       ^
        |       |
        |       +-- additional-spring-configuration-metadata.json
        |
        v
PACKAGED LIBRARY JAR
        |
        +--> AutoConfiguration.imports
        +--> spring-autoconfigure-metadata.properties
        +--> spring-configuration-metadata.json
        |
        +------------------------------+
                                       |
                     +-----------------+------------------+
                     |                                    |
                     v                                    v
              SPRING BOOT RUNTIME                      IDE / EDITOR
                     |                                    |
             imports: discover candidates          configuration JSON:
                     |                              completion/documentation
             autoconfigure metadata:
             eager condition filtering
                     |
             evaluate remaining conditions
                     |
             register applicable bean definitions
                     |
             bind @ConfigurationProperties
```

The diagram emphasizes that the two JSON/properties files are not interchangeable. The imports and autoconfigure metadata files serve runtime configuration discovery/filtering; configuration metadata serves configuration authoring tools.

## 10. Common Issues

| Symptom | Cause | Resolution |
|---|---|---|
| Auto-configuration class has annotation but is not discovered | Missing or misnamed imports file, or incorrect class name | Check AutoConfiguration.imports in the JAR |
| Has imports but spring-autoconfigure-metadata.properties is missing | Processor not configured or no suitable source conditions to record metadata | Check annotation processor path and compile output |
| Missing autoconfigure metadata causes application not to run | Confusing the optimization file with the candidate registration file | Keep imports; condition metadata does not replace the candidate list |
| IDE does not suggest keys | Missing configuration processor or JSON not packaged | Check the processor and the JAR |
| IDE suggests keys but runtime does not recognize them | Metadata JSON has the key but code does not bind/read the key | Add @ConfigurationProperties/Binder or property-reading logic |
| JSON has default different from actual behavior | Metadata default is out of sync with code | Synchronize field initializers, runtime fallbacks, and additional metadata |
| Added additional metadata but JSON did not change | File placed in wrong path or processor did not run | Check META-INF/additional-spring-configuration-metadata.json and run a clean build |
| Deprecated property still works despite metadata warning | Warning level still allows binding or code has an alias | This may be intentional for backward compatibility; check deprecation level and code |
| Property has hints but IDE does not suggest them | IDE does not read metadata or key/hint mismatch | Check the final JSON file and IDE support |
| Processor JAR appears unexpectedly in executable app | Processor declared as a regular runtime dependency | Use annotationProcessorPaths/annotationProcessor or exclude the processor from repackaging |
| Metadata only has type, missing description | Missing proper Javadoc or source is only a compiled dependency | Add Javadoc in source or manual additional metadata |
| Collection default is not generated properly | Processor cannot infer complex collection values | Declare defaultValue using additional metadata |
| Renamed auto-config class but forgot imports | Resource still references the old class | Update imports at the same time as refactoring package/class |

## 11. Checklist for Releasing an Auto-Configuration Library

Before releasing the JAR, verify:

1. **Candidate list:** Does imports have the exact fully qualified names of all auto-configurations to declare?
2. **Package:** Is the auto-config outside the application's regular component scan area?
3. **Conditions:** Are classpath, property, and missing-bean conditions declared in the source code?
4. **Autoconfigure processor:** Does the module containing auto-config run spring-boot-autoconfigure-processor?
5. **Configuration processor:** Does the module containing @ConfigurationProperties run spring-boot-configuration-processor?
6. **Properties Javadoc:** Do keys have clear descriptions, and do types and defaults match runtime behavior?
7. **Additional metadata:** Do hints, deprecations, and manual properties follow the valid JSON schema?
8. **JAR:** Are both imports and metadata inside the artifact after building?
9. **Consumer test:** Does a sample application adding the starter discover the auto-config and receive property suggestions in the IDE?
10. **Do not confuse roles:** Do not use JSON metadata to replace binding code, and do not use condition metadata to replace imports.

## 12. Self-Check Questions

**Question 1.** Which file lists auto-configuration class names for Spring Boot to discover?

**Answer:** META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports.

**Question 2.** Which processor generates spring-autoconfigure-metadata.properties and what is it used for?

**Answer:** spring-boot-autoconfigure-processor generates this file so Spring Boot can filter out certain auto-configurations early based on known conditions, optimizing startup.

**Question 3.** Does spring-configuration-metadata.json make Binder automatically bind properties?

**Answer:** No. It describes properties for IDEs/tools. Runtime binding still requires a registered @ConfigurationProperties class or appropriate property-reading code.

**Question 4.** If you want to add hints for a key that the processor cannot infer, which file do you use?

**Answer:** META-INF/additional-spring-configuration-metadata.json; the configuration processor merges it into the main metadata JSON.

**Question 5.** If you remove spring-autoconfigure-metadata.properties while keeping imports and condition code, can auto-configuration still run?

**Answer:** Yes. Candidates are still discovered via imports and conditions are still evaluated normally; only the early filtering step based on that metadata is lost.

**Question 6.** If you only add a key to additional metadata without a properties bean or key-reading logic, will values in application.yml automatically be used?

**Answer:** No. Metadata does not create bindings or change runtime behavior.

**Question 7.** Is a property with deprecation level warning still bound?

**Answer:** Yes. Warning allows binding to continue during the transition period; the error level indicates the property is no longer managed and is not bound.

## 13. Key Takeaways

- **AutoConfiguration.imports** is the list of auto-configuration candidates; the library author maintains it.
- **spring-autoconfigure-metadata.properties** is generated by the autoconfigure processor for early condition filtering and improved startup.
- **spring-configuration-metadata.json** is generated by the configuration processor so IDEs can support completion, documentation, and hints.
- **additional-spring-configuration-metadata.json** is a manual input to supplement/refine property metadata.
- Property metadata does not replace @ConfigurationProperties, Binder, or Environment-reading logic.
- Condition metadata does not replace imports and condition annotations in source code.
- Inspect the final JAR and test with a real consuming application to verify both runtime discovery and the IDE experience.

### Official Documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Spring Boot 3.3 — Generating Metadata by Using the Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html)
- [Spring Boot 3.3 — Metadata Format](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html)
