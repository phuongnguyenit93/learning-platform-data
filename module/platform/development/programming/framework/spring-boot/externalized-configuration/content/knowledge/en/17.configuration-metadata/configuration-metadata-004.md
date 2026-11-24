# Structure of groups, properties, and hints in Metadata JSON

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** Configuration Metadata

## 1. Why Does Spring Boot Have Configuration Metadata?

When working with Spring Boot, developers often edit keys like `server.port`, `spring.datasource.url`, or custom properties like `catalog.client.timeout`. An IDE with Spring Boot support can suggest key names, indicate types, display descriptions, and propose appropriate values. This information is typically provided by **configuration metadata**.

The metadata JSON file is packaged at the path:

~~~text
META-INF/spring-configuration-metadata.json
~~~

This is data **for development tooling**, not a runtime configuration file. Spring Boot can generate metadata using `spring-boot-configuration-processor` based on `@ConfigurationProperties` classes and corresponding source information. Developers can also add metadata manually.

A typical metadata file has three top-level arrays:

~~~json
{
  "groups": [],
  "properties": [],
  "hints": []
}
~~~

Meaning:

- **`groups`**: groups of properties sharing the same namespace/prefix, for example `catalog.client`.
- **`properties`**: full property names, Java types, descriptions, default metadata, and source info.
- **`hints`**: additional suggestions for values, such as a list of choices or a provider for context-aware IDE suggestions.

Critically important: **metadata does not create beans automatically, does not supply default values to the application itself, does not alter PropertySource precedence, and does not validate data at runtime**.

### Learning Objectives

After this lesson, you will be able to:

1. Read `groups`, `properties`, and `hints` in JSON.
2. Distinguish a group prefix from an actual scalar property.
3. Explain `name`, `type`, `sourceType`, `sourceMethod`, `description`, `defaultValue`, and `deprecation`.
4. Use `hints.values` and `hints.providers` for their intended purpose.
5. Declare hints for a `Map` using the `.keys` and `.values` suffixes.
6. Generate metadata via the annotation processor and supplement info with `additional-spring-configuration-metadata.json`.
7. Diagnose cases where the IDE shows no suggestions while runtime binding still works.
8. Understand the difference between metadata, validation, and configuration sources at startup.

## 2. Relationship Between `@ConfigurationProperties` and Metadata

Suppose we have a record:

~~~java
package com.example.catalog.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        URI endpoint,
        Duration timeout,
        int maxConnections,
        String mode
) {}
~~~

Corresponding configuration in `application.yml`:

~~~yaml
catalog:
  client:
    endpoint: "https://catalog.example.test"
    timeout: 3s
    max-connections: 20
    mode: safe
~~~

At build time, the annotation processor can analyze the configuration type and generate metadata. When a developer types YAML, the IDE can use metadata to show suggestions. At runtime, the Binder reads properties from `Environment` to construct the record.

~~~text
Java @ConfigurationProperties
             |
             v
Annotation processor (build)
             |
             v
spring-configuration-metadata.json
    |             |             |
 groups       properties       hints
    \             |             /
             IDE / tooling

application.yml / env / CLI / imports
             |
             v
     Spring Environment
             |
             v
      Spring Boot Binder
             |
             v
   CatalogClientProperties bean
~~~

The two branches serve distinct purposes: metadata serves tooling; the Binder serves the application.

Illustrative metadata example:

~~~json
{
  "groups": [
    {
      "name": "catalog.client",
      "type": "com.example.catalog.config.CatalogClientProperties",
      "sourceType": "com.example.catalog.config.CatalogClientProperties"
    }
  ],
  "properties": [
    {
      "name": "catalog.client.endpoint",
      "type": "java.net.URI",
      "description": "Catalog API address."
    },
    {
      "name": "catalog.client.timeout",
      "type": "java.time.Duration",
      "description": "Wait timeout limit."
    },
    {
      "name": "catalog.client.max-connections",
      "type": "java.lang.Integer",
      "defaultValue": 20
    },
    {
      "name": "catalog.client.mode",
      "type": "java.lang.String"
    }
  ],
  "hints": [
    {
      "name": "catalog.client.mode",
      "values": [
        {"value": "safe", "description": "Safe mode."},
        {"value": "fast", "description": "Fast mode."}
      ]
    }
  ]
}
~~~

This is **structure-illustrative JSON**, not a claim that the processor always generates every description, hint, or default identically to the above. For a `String mode`, the processor does not automatically know the two business choices `safe` and `fast` if they are not expressed in source or additional metadata.

## 3. The `groups` Section: Describing Configuration Groups

A `groups` element describes a namespace:

~~~json
{
  "groups": [
    {
      "name": "catalog.client",
      "type": "com.example.catalog.config.CatalogClientProperties",
      "sourceType": "com.example.catalog.config.CatalogClientProperties",
      "description": "Catalog connection settings."
    }
  ]
}
~~~

### 3.1. The `name` Field

`groups[].name` is the prefix name, usually written with lowercase letters, hierarchical dots, and kebab-case. Examples:

~~~text
catalog.client
mail.sender
batch.import-job
payment.gateway.retry
~~~

`catalog.client` is a **group prefix**. On its own, it is typically not a scalar property to be assigned a string or number. Concrete properties live under the prefix, such as `catalog.client.timeout`.

### 3.2. The `type` Field

`groups[].type` describes the Java type representing the group. If the bound class is `CatalogClientProperties`, metadata can contain the fully qualified name of that class.

Do not confuse metadata `type` with JSON Schema types like `object`. Spring Boot metadata usually uses Java type names.

### 3.3. `sourceType` and `sourceMethod`

`sourceType` indicates the source Java type used to define the group/property. When a group or property relates to a Java method, such as a `@Bean` method annotated to bind configuration properties, metadata may contain `sourceMethod`.

Table:

| Field | Meaning |
| --- | --- |
| `name` | Group/prefix name |
| `type` | Java type representing the group |
| `sourceType` | Java type declaring/exposing the metadata source |
| `sourceMethod` | Source Java method name if applicable |
| `description` | Description of the namespace's purpose |

Not every entry has all optional fields. Generated metadata may vary depending on code declarations, processor version, and available information.

### 3.4. Nested Groups

Java example:

~~~java
@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        URI endpoint,
        Retry retry
) {
    public record Retry(int maxAttempts, Duration backoff) {}
}
~~~

YAML:

~~~yaml
catalog:
  client:
    endpoint: "https://catalog.example.test"
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

Metadata can describe both `catalog.client` and `catalog.client.retry` as groups. The scalar properties are `catalog.client.endpoint`, `catalog.client.retry.max-attempts`, and `catalog.client.retry.backoff`.

A nested group does not mean a scalar property `catalog.client.retry` can be read directly to obtain the whole object.

## 4. The `properties` Section: Describing Each Key

`properties` is usually the most useful section when developers type YAML or properties files.

~~~json
{
  "properties": [
    {
      "name": "catalog.client.timeout",
      "type": "java.time.Duration",
      "description": "Maximum wait time per call.",
      "sourceType": "com.example.catalog.config.CatalogClientProperties"
    }
  ]
}
~~~

### 4.1. `name` Is the Full Property Name

`name` usually includes the full prefix:

~~~text
catalog.client.timeout
catalog.client.max-connections
catalog.client.retry.max-attempts
~~~

It is not just `timeout`. This helps the IDE recognize the property under the right namespace and avoids collisions between classes having fields with the same name.

### 4.2. `type` Describes the Java Type

Examples:

| Property | Typical Java type |
| --- | --- |
| `catalog.client.endpoint` | `java.net.URI` |
| `catalog.client.timeout` | `java.time.Duration` |
| `catalog.client.enabled` | Boolean/boolean type represented per schema |
| `catalog.client.max-connections` | Integer/int represented in metadata |
| `catalog.client.regions` | List of String |
| `catalog.client.labels` | Map of String to String |

A metadata entry `"type":"java.time.Duration"` helps tooling understand the expected value type, but **it is not a runtime instruction creating a Duration field**. The Java type in configuration code is what dictates what type the Binder must convert data into.

For collection/generic types, the `type` string has an appropriate Java representation and may reflect generic type arguments. Do not build application logic that hardcodes an exact type string from an example, in case a different processor version formats it differently.

### 4.3. `description`

`description` should explain what the property means:

~~~json
{
  "name": "catalog.client.timeout",
  "type": "java.time.Duration",
  "description": "Wait timeout for each Catalog request."
}
~~~

A good description can state units, impact when missing, whether it is required, and relationships with other properties. Do not write only `"description":"Timeout"` if users would not know whether the timeout applies to connecting or the entire request.

### 4.4. `defaultValue`

~~~json
{
  "name": "catalog.client.max-connections",
  "type": "java.lang.Integer",
  "defaultValue": 20
}
~~~

`defaultValue` is **a descriptive piece** of the property's default for tooling display. Manually editing `defaultValue` in metadata does not make the Binder assign `20` to the Java bean when runtime lacks a value.

To have a real default, you can use `@DefaultValue` in constructor binding:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        @DefaultValue("20") int maxConnections
) {}
~~~

Or place it in a config file:

~~~yaml
catalog:
  client:
    max-connections: 20
~~~

Or use an initializer with a JavaBean:

~~~java
private int maxConnections = 20;
~~~

These approaches have different semantics and override orders. Metadata should **accurately describe the actual default behavior**. When the processor cannot infer a default, update documentation/additional metadata accurately rather than inventing a default that only exists on paper.

### 4.5. `sourceType` and `sourceMethod`

A property may have `sourceType` pointing to the declaring class. `sourceMethod` is optional information when the source is a method. If an entry lacks `sourceMethod`, do not conclude it is invalid.

### 4.6. `deprecation`

When a property is no longer recommended:

~~~json
{
  "name": "catalog.client.legacy-timeout",
  "type": "java.time.Duration",
  "description": "Legacy timeout name.",
  "deprecation": {
    "level": "warning",
    "reason": "Renamed to distinguish request timeout from connect timeout.",
    "replacement": "catalog.client.timeout"
  }
}
~~~

Common fields in the deprecation object:

- `level`: level such as `warning` or `error`.
- `reason`: why it should no longer be used.
- `replacement`: suggested replacement property name.
- `since`: version info if provided.

A deprecation warning **does not automatically alias the old property to the new property**. If the application must preserve temporary compatibility, a dedicated runtime mechanism to read the old name or migrate it is needed.

### 4.7. Metadata Does Not Blindly Describe Every Java Field

The processor recognizes types and elements according to `@ConfigurationProperties` rules. A Java class having computed methods, internal fields, or nested classes does not mean all of them should appear as public properties.

For declarations where the processor cannot infer everything, an additional metadata file can supply the missing information.

## 5. The `hints` Section: Helping IDEs Suggest Values

`hints` differs from `properties` in that it focuses on **inputtable values** rather than property names and Java types.

For example, `catalog.client.mode` has type String, yet the application recommends two modes:

~~~json
{
  "hints": [
    {
      "name": "catalog.client.mode",
      "values": [
        {
          "value": "safe",
          "description": "Policy prioritizing safety."
        },
        {
          "value": "fast",
          "description": "Policy prioritizing response time."
        }
      ]
    }
  ]
}
~~~

### 5.1. `name` Links the Hint to a Property

`hints[].name` is usually the full name of the property receiving the hint, such as `catalog.client.mode`.

Do not use the short field name `mode` if the property actually sits under prefix `catalog.client`; the IDE needs to match the exact key.

### 5.2. `values`: Static Choices

Each element in `values` typically has:

- `value`: suggested value, which may be a string, number, or corresponding JSON type.
- `description`: explanation for that choice.

Example:

~~~json
{
  "name": "catalog.client.retry-limit",
  "values": [
    {
      "value": 2,
      "description": "Fewer retries."
    },
    {
      "value": 5,
      "description": "Broader retry policy."
    }
  ]
}
~~~

**Hints are not constraints.** The IDE can suggest `2` or `5`, but the Binder does not reject `3` by default just because `3` is absent from the `values` list.

To enforce that retries belong to a specific set, use an enum, Bean Validation, or an appropriate custom validator.

### 5.3. `providers`: Dynamic Suggestions

A hint can declare `providers` so the IDE suggests values contextually rather than from a fixed list alone.

~~~json
{
  "hints": [
    {
      "name": "app.handler-class",
      "providers": [
        {
          "name": "class-reference",
          "parameters": {
            "target": "com.example.spi.Handler"
          }
        }
      ]
    }
  ]
}
~~~

Idea: an IDE supporting `class-reference` can suggest compatible Java class names. `parameters` is an object supplying parameters to the provider when that provider kind requires them.

Provider names commonly documented by Spring Boot include:

| Provider | Suggestion target |
| --- | --- |
| `any` | Allows unrestricted values |
| `class-reference` | Reference to a Java class |
| `handle-as` | Interpret/suggest according to a desired type |
| `logger-name` | Logger name |
| `spring-bean-reference` | Bean name in the Spring context |
| `spring-profile-name` | Spring profile name |
| `spring-property-name` | Spring property name |

IDE support can be uneven. Hint providers do not create class instances, beans, or profiles at runtime.

### 5.4. Are Both `values` and `providers` Needed?

A hint can have static values, contextual providers, or both if the schema and tooling support it. However, do not add noisy providers just to populate all three JSON arrays. There should be a **genuine suggestion purpose**, and you should verify how the IDE uses it.

An enum property may already carry enough info for tooling to propose enum constants; in some situations manual `values` are unnecessary.

## 6. Hints for Maps: `.keys` and `.values` Suffixes

When a Java properties class has `Map<String,String>`:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        Map<String, String> channels
) {}
~~~

YAML may be:

~~~yaml
routing:
  channels:
    email: enabled
    sms: disabled
~~~

The IDE may need different suggestions for **keys** and **values**. Spring Boot metadata supports two hint suffixes:

- `routing.channels.keys`: list of proposals for **map keys**.
- `routing.channels.values`: list of proposals for **map values**.

Example:

~~~json
{
  "hints": [
    {
      "name": "routing.channels.keys",
      "values": [
        {"value": "email", "description": "Email channel."},
        {"value": "sms", "description": "SMS channel."},
        {"value": "push", "description": "Push channel."}
      ]
    },
    {
      "name": "routing.channels.values",
      "values": [
        {"value": "enabled", "description": "Enable channel."},
        {"value": "disabled", "description": "Disable channel."}
      ]
    }
  ]
}
~~~

In Map `hints`, the `.keys` and `.values` suffixes are **special metadata conventions**, not mandatory runtime properties named `routing.channels.keys` or `routing.channels.values`.

### 6.1. Hints Do Not Create Entries

Just because JSON hints suggest `email`, `sms`, `push` does not mean the Binder creates three map entries. At runtime, the Map still comes from effective configuration values.

### 6.2. Bracket Notation and Special Keys

If a key contains `/` or certain special characters, the Binder has rules to preserve the key verbatim. For example in YAML:

~~~yaml
routing:
  channels:
    "[/api]": enabled
~~~

A hint suggesting `/api` does not fix YAML syntax or guarantee a mistyped key binds properly. Metadata and map binding rules are two different mechanisms.

## 7. Complete Metadata Example: groups + properties + hints

Suppose the application has the configuration contract:

~~~text
shipping.gateway.endpoint
shipping.gateway.timeout
shipping.gateway.mode
shipping.gateway.retry.max-attempts
shipping.gateway.retry.backoff
shipping.gateway.extra-headers
~~~

An illustrative JSON with all three arrays:

~~~json
{
  "groups": [
    {
      "name": "shipping.gateway",
      "type": "com.example.shipping.GatewayProperties",
      "sourceType": "com.example.shipping.GatewayProperties",
      "description": "Shipping Gateway connection configuration."
    },
    {
      "name": "shipping.gateway.retry",
      "type": "com.example.shipping.GatewayProperties$Retry",
      "description": "Retry policy."
    }
  ],
  "properties": [
    {
      "name": "shipping.gateway.endpoint",
      "type": "java.net.URI",
      "description": "Shipping Gateway address."
    },
    {
      "name": "shipping.gateway.timeout",
      "type": "java.time.Duration",
      "description": "Call timeout duration.",
      "defaultValue": "5s"
    },
    {
      "name": "shipping.gateway.mode",
      "type": "java.lang.String",
      "description": "Request delivery mode."
    },
    {
      "name": "shipping.gateway.retry.max-attempts",
      "type": "java.lang.Integer",
      "defaultValue": 3
    },
    {
      "name": "shipping.gateway.retry.backoff",
      "type": "java.time.Duration",
      "defaultValue": "250ms"
    },
    {
      "name": "shipping.gateway.extra-headers",
      "type": "java.util.Map<java.lang.String,java.lang.String>",
      "description": "Additional headers."
    }
  ],
  "hints": [
    {
      "name": "shipping.gateway.mode",
      "values": [
        {"value": "standard", "description": "Standard mode."},
        {"value": "priority", "description": "Priority mode."}
      ]
    },
    {
      "name": "shipping.gateway.extra-headers.keys",
      "values": [
        {"value": "x-trace-tag", "description": "Trace tag."},
        {"value": "x-client-name", "description": "Client name."}
      ]
    }
  ]
}
~~~

Reading in order:

1. `groups` identifies the namespaces `shipping.gateway` and `shipping.gateway.retry`.
2. `properties` specifies concrete keys and Java types.
3. `hints` suggests `standard`/`priority` modes and two map keys for `extra-headers`.

### 7.1. Corresponding YAML

~~~yaml
shipping:
  gateway:
    endpoint: "https://shipping.example.test"
    timeout: 5s
    mode: standard
    retry:
      max-attempts: 3
      backoff: 250ms
    extra-headers:
      x-trace-tag: batch-a
      x-client-name: catalog
~~~

The IDE can rely on metadata to suggest property names and values. Spring Boot runtime still loads this YAML using the config-data loader and binds into typed objects according to actual precedence.

### 7.2. Corresponding Record

~~~java
package com.example.shipping;

import java.net.URI;
import java.time.Duration;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "shipping.gateway")
public record GatewayProperties(
        URI endpoint,
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("standard") String mode,
        Retry retry,
        Map<String, String> extraHeaders
) {
    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("250ms") Duration backoff
    ) {}
}
~~~

If you want nested `retry` to always be created when all `shipping.gateway.retry.*` keys are absent, consider an empty `@DefaultValue` on the `Retry retry` component. Otherwise, a constructor-bound nested field can be null when no properties exist for that group.

The example focuses on metadata; a production HTTP client also needs validation, network error handling, and appropriate security.

## 8. How to Generate Metadata with the Annotation Processor

Spring Boot provides `spring-boot-configuration-processor` to generate metadata at build time.

### 8.1. Maven

For a project using Spring Boot dependency management, you can add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Depending on the Maven Compiler Plugin/JDK version and project configuration, you may need to declare annotation processor paths or enable annotation processing explicitly. Use a processor version compatible with the project's Spring Boot version.

### 8.2. Gradle

Gradle Groovy DSL:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

The processor runs during build/compile. With Kotlin, annotation processing configuration differs depending on plugins and versions; consult the corresponding Kotlin documentation rather than mechanically applying Java settings.

### 8.3. Output

After compiling, you may see:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

or:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

depending on build configuration. When packaged, metadata can reside at `META-INF/spring-configuration-metadata.json` inside the JAR.

### 8.4. Processor Not Required for Runtime Binding

A `@ConfigurationProperties` class can still be bound without generated metadata, provided Spring Boot has registered the bean and loaded the appropriate configuration data. The processor helps IDEs understand properties; **it is not a required Binder library for runtime operation**.

If the IDE shows no suggestions while the bean still receives values, investigate metadata/build/IDE separately.

## 9. `additional-spring-configuration-metadata.json`

The annotation processor may not infer complete descriptions, default metadata, or business hints. Spring Boot supports an additional file in the source tree:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Example:

~~~json
{
  "properties": [
    {
      "name": "catalog.client.mode",
      "type": "java.lang.String",
      "description": "Catalog client operating mode."
    }
  ],
  "hints": [
    {
      "name": "catalog.client.mode",
      "values": [
        {"value": "safe", "description": "Prioritize safety."},
        {"value": "fast", "description": "Prioritize speed."}
      ]
    }
  ]
}
~~~

The processor can merge this supplementary data with generated metadata, according to mechanisms and toolchains supported by Spring Boot.

Comparison:

| File | Source | Role |
| --- | --- | --- |
| `spring-configuration-metadata.json` | Usually generated by processor in build output | Metadata read by IDEs/tooling |
| `additional-spring-configuration-metadata.json` | Written by developers in source resources | Supplements/adjusts metadata info |

Do not directly edit the metadata copy **inside the build output directory** and treat it as a persistent change. The next build can regenerate and overwrite it. Edit Javadoc sources or additional metadata instead.

### 9.1. Additional Metadata Does Not Create Runtime Properties

If you add:

~~~json
{
  "properties": [
    {
      "name": "custom.feature.enabled",
      "type": "java.lang.Boolean",
      "description": "Enable custom feature."
    }
  ]
}
~~~

The IDE may suggest the property name. However, if the application has no code reading/binding `custom.feature.enabled`, adding metadata will not make that feature work on its own.

### 9.2. Multiple Modules

A library or starter should package metadata for **the configuration properties provided by that module itself**. IDEs can collect metadata from multiple JARs on the classpath.

If a module is released with stale metadata, IDEs of applications using that module may suggest wrong keys compared to runtime code. Keep metadata and library versions maintained together.

## 10. Descriptions from Javadoc

The processor can use Javadoc and source declarations to create descriptions. Example:

~~~java
package com.example.demo.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * Configuration for the data import job.
 *
 * @param enabled whether the import job is enabled
 * @param batchSize number of records per batch
 * @param timeout maximum wait time
 */
@ConfigurationProperties(prefix = "demo.import-job")
public record ImportJobProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("100") int batchSize,
        @DefaultValue("10s") Duration timeout
) {}
~~~

When annotation processing is configured properly, tooling can receive metadata for the keys:

~~~text
demo.import-job.enabled
demo.import-job.batch-size
demo.import-job.timeout
~~~

Do not assume every processor version collects Javadoc on records in a single uniform way. Ensure the IDE/build tool and actual processor support the source model in use.

## 11. Metadata, Defaults, Validation, and Precedence: Four Different Things

### 11.1. Default Metadata Does Not Decide Runtime Defaults

Metadata:

~~~json
{
  "properties": [
    {
      "name": "app.retry.attempts",
      "type": "java.lang.Integer",
      "defaultValue": 3
    }
  ]
}
~~~

If the Java class has no default, and configuration sources do not supply `app.retry.attempts`, the application **does not automatically receive value 3 because of metadata**. Source order and the Binder determine the outcome, where primitive types may fall back to `0` when the object is constructed.

For a real default, use `@DefaultValue("3")` or an appropriate runtime source.

### 11.2. Hints Do Not Enforce Validation

Metadata:

~~~json
{
  "hints": [
    {
      "name": "app.mode",
      "values": [
        {"value": "safe"},
        {"value": "fast"}
      ]
    }
  ]
}
~~~

If code binds `String mode`, the value `experimental` may still be accepted even though it is unlisted. To allow only two modes, use an enum or validation.

### 11.3. Metadata Does Not Create Beans

You must register `@ConfigurationProperties` with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` as appropriate. JSON metadata does not replace that step.

### 11.4. Metadata Does Not Override Higher-Precedence Sources

Suppose YAML has `app.client.timeout=5s`, an environment variable has `APP_CLIENT_TIMEOUT=2s`, and metadata describes default `3s`. The typical runtime result takes `2s` from the OS environment if no higher source overrides it; metadata does not participate in `Environment` lookups.

### 11.5. Metadata Does Not Replace JSON Schema

Although it is JSON, the `groups`/`properties`/`hints` structure **differs from JSON Schema**. It does not enforce constraints such as `required` or `minimum` on YAML files.

Bean Validation, Binder conversion, and business checks remain separate responsibilities.

## 12. Deprecation and Property Migration

When renaming a key, for example:

~~~text
Before: catalog.client.retry-count
After:  catalog.client.retry.max-attempts
~~~

you can describe deprecation:

~~~json
{
  "properties": [
    {
      "name": "catalog.client.retry-count",
      "type": "java.lang.Integer",
      "deprecation": {
        "level": "warning",
        "reason": "Moved to the structured retry group.",
        "replacement": "catalog.client.retry.max-attempts"
      }
    }
  ]
}
~~~

The IDE can help configurators spot the old key and propose the new key. However, metadata **does not automatically turn the old key into an alias**.

If older deployments must continue using the old key, the application must supply a real compatibility policy, such as code reading both forms with explicit precedence or a designed mapping mechanism.

When removing runtime support for the old key, update documentation and metadata so users are not suggested a configuration that no longer works.

## 13. How to Read Optional Fields

Not every group or property includes every field. Some cases:

~~~json
{
  "properties": [
    {
      "name": "app.enabled",
      "type": "java.lang.Boolean"
    }
  ]
}
~~~

This entry is still meaningful: it describes the name and type. Missing `description` does not mean the property is broken. Missing `defaultValue` does not mean the runtime value is necessarily null. Missing `sourceMethod` does not mean the processor failed.

When reading metadata, distinguish:

- **Known metadata info.**
- **Undescribed info.**
- **Runtime Binder behavior.**

Do not infer from a missing field that the framework enforces some mandatory behavior.

## 14. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| IDE does not autocomplete `catalog.client.*` | Missing processor or annotation processing disabled | Enable processor and rebuild |
| Metadata file missing in output | Not compiled, different toolchain, processor did not run | Check build output in the right module |
| Runtime binds fine but IDE does not suggest | Missing metadata or limited IDE support | Check processor, classpath, plugin |
| IDE suggests unused properties | Stale additional metadata or old dependency JAR | Sync metadata with code |
| `defaultValue` displays 20 but runtime receives 0 | Metadata does not create runtime defaults | Add actual default in code/config |
| Hints `safe`/`fast` yet app accepts `other` | Hints are not validation | Use enum or Bean Validation |
| Hints do not appear | Wrong `name` or IDE lacks provider support | Verify canonical name, schema, and IDE |
| Provider cannot find bean/class | Context/tooling lacks info or provider unsupported | Check provider name and parameters |
| Group exists without properties | Class has no bindable members or insufficient manual metadata | Review property definitions |
| Map key hint does not work | Missing `.keys`/`.values` suffix | Use proper Map hint naming |
| Additional JSON cannot be read | Invalid JSON syntax, wrong resource location | Fix JSON and place in the right folder |
| `sourceMethod` missing | No relevant method or processor did not record it | Do not treat as an error unless required |
| Metadata lost after clean build | Edited generated file instead of source | Use additional metadata or Javadoc |
| IDE suggests old type | Metadata and Java type out of sync | Sync metadata and rebuild |

### 14.1. Validating JSON Syntax

Files written by developers must be standard JSON: double quotes around key names and strings, no comments, no trailing commas, and properly closed objects/arrays.

Invalid example:

~~~text
{
  'hints': [
    {name: "app.mode"}
  ]
}
~~~

Valid example:

~~~json
{
  "hints": [
    {
      "name": "app.mode"
    }
  ]
}
~~~

Valid syntax is a baseline requirement; proper schema key names, accurate descriptions, and IDE compatibility still require careful design.

## 15. Practice: Creating and Viewing Metadata

### Step 1: Create the Configuration Record

~~~java
package com.example.demo;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "lesson.cleanup")
public record CleanupProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("10s") Duration timeout,
        @DefaultValue("100") int batchSize
) {}
~~~

Enable scanning:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {}
~~~

### Step 2: Enable the Processor

Gradle Groovy DSL:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Or use the corresponding Maven configuration mentioned earlier.

### Step 3: Compile and Inspect Output

After building, locate `META-INF/spring-configuration-metadata.json` and check that it contains group `lesson.cleanup` and properties `lesson.cleanup.enabled`, `lesson.cleanup.timeout`, `lesson.cleanup.batch-size`.

Do not treat the element order in JSON arrays as runtime property precedence. Metadata is a descriptive listing.

### Step 4: Add Hints

Create `src/main/resources/META-INF/additional-spring-configuration-metadata.json`:

~~~json
{
  "hints": [
    {
      "name": "lesson.cleanup.batch-size",
      "values": [
        {
          "value": 100,
          "description": "Small batch."
        },
        {
          "value": 500,
          "description": "Large batch."
        }
      ]
    }
  ]
}
~~~

### Step 5: Write the YAML File

~~~yaml
lesson:
  cleanup:
    enabled: true
    timeout: 30s
    batch-size: 500
~~~

Observe whether the IDE shows completion/hints, then launch the application to see the actual typed values. Distinguish the IDE using metadata from the Binder using YAML.

## 16. Self-Check Exercises

### Exercise A: Groups and Properties

JSON:

~~~json
{
  "groups": [
    {"name": "billing.client", "type": "com.example.BillingProperties"}
  ],
  "properties": [
    {"name": "billing.client.endpoint", "type": "java.net.URI"},
    {"name": "billing.client.timeout", "type": "java.time.Duration"}
  ]
}
~~~

Question: what is the group name, how many properties are there, and can you infer the actual runtime timeout?

Answer: `billing.client`, two properties, and you cannot infer the runtime timeout from metadata alone.

### Exercise B: Are Hints Mandatory?

Hints propose `mode=safe` and `mode=fast`. If the app binds `String mode` and the file has `mode=experimental`, will metadata cause startup to fail?

Answer: no. A separate runtime rule is needed to restrict the set of values.

### Exercise C: Map Hint Name

For a property `app.channels` of type `Map<String,String>`, which hint name suggests the key `email`?

Answer: `app.channels.keys`. For value suggestions, use `app.channels.values`.

### Exercise D: Metadata Default

A metadata file declares `"defaultValue":5` for `app.retries`, yet code only has `int retries` without an initializer. If the runtime property is missing, is the value guaranteed to be 5?

Answer: no; metadata does not supply runtime defaults.

### Exercise E: Provider

A hint uses `"name":"spring-profile-name"`. What does it help with?

Answer: the IDE can suggest profile names based on tooling support; it does not activate any profile.

### Exercise F: Migration

An old property is marked with `replacement` in metadata. Is runtime guaranteed to read the old name and automatically transfer it to the new name?

Answer: no; explicit compatibility support is needed in code or configuration mechanisms.

## 17. Checklist When Developing Metadata for a Library

- [ ] `@ConfigurationProperties` classes have canonical and stable prefixes.
- [ ] The processor is in the right configuration and annotation processing is enabled.
- [ ] Descriptions clearly state property meaning instead of repeating field names.
- [ ] `properties[].name` values include the full prefix.
- [ ] `type` matches the bound Java type.
- [ ] `defaultValue` in metadata matches the runtime default if one exists.
- [ ] Nested groups are described following the required code structure.
- [ ] Hint `values` contain genuinely useful choices.
- [ ] Hint `providers` use valid names and schema-compliant parameters.
- [ ] Map hints use `.keys` or `.values` suffixes.
- [ ] Deprecated keys have clear `reason`/`replacement` and a separate runtime strategy.
- [ ] Additional metadata resides in `src/main/resources/META-INF/`.
- [ ] Generated output is not edited as the sole source of truth.
- [ ] Published JARs/modules contain metadata compatible with the code.
- [ ] IDE completion has been tested with an application consuming the module.
- [ ] Binding and Bean Validation are tested independently of metadata.
- [ ] Real secret values are excluded from descriptions, hints, and examples.

## 18. Takeaways

1. **`spring-configuration-metadata.json` is metadata for tooling**, not a config data file controlling the application at runtime.
2. **`groups`** describes prefixes, types, and sources of configuration groups.
3. **`properties`** describes concrete keys, Java types, descriptions, default metadata, sources, and deprecations.
4. **`hints`** describes value suggestions using `values` and `providers`, and can add Map key/value hints using `.keys` and `.values`.
5. **`spring-boot-configuration-processor`** generates metadata at build time; use `additional-spring-configuration-metadata.json` to supplement manually.
6. Defaults in metadata **do not create runtime defaults**; hints in metadata **do not enforce validation**.
7. When the IDE does not suggest keys, check the processor, build output, classpath, and IDE; do not conclude the Binder is broken.
8. Good metadata is maintained alongside the real configuration API, accurately describes behavior, and never exposes sensitive information.

## References

- [Spring Boot — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html): purpose and overview.
- [Spring Boot — Metadata Format](https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html): structure of `groups`, `properties`, `hints`.
- [Spring Boot — Providing Manual Hints](https://docs.spring.io/spring-boot/specification/configuration-metadata/manual-hints.html): `values`, `providers`, and Map hints.
- [Spring Boot — Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html): generating metadata and additional metadata.
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): Bean registration, Binder, and typed configuration.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): real value sources and precedence.
