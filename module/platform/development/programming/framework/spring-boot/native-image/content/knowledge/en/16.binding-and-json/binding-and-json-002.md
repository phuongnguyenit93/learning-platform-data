# @NestedConfigurationProperty When Nested Structures Need Explicit Recognition

Spring Boot allows grouping related configurations into nested groups, such as `acme.client.timeout`, `acme.client.base-url`, or `acme.security.enabled`. When a nested structure uses a separate class outside the root `@ConfigurationProperties` class, **`@NestedConfigurationProperty` helps the configuration metadata processor recognize that type as a nested configuration group**.

The key distinction is that this annotation primarily serves **developer tooling metadata**. It is not an instruction for Spring Binder to instantiate an object, it does not replace getters/setters or constructor binding, and it does not automatically register reflection hints for GraalVM Native Image. Runtime binding, configuration metadata, and Spring AOT are three related yet distinct tasks.

This guide builds a Spring Boot configuration with nested groups, explains when the annotation is needed, inspects the generated metadata, and verifies the configuration on both the JVM and the native executable.

## 1. Why Do Nested Structures Need Explicit Recognition?

Suppose an application has configuration for connecting to an external service:

~~~yaml
acme:
  client:
    base-url: https://api.example.test
    connect-timeout: 2s
    read-timeout: 5s
  security:
    enabled: true
    issuer-uri: https://identity.example.test
~~~

The properties are grouped by relationship:

- `acme.client.*` describes the HTTP client configuration.
- `acme.security.*` describes the authentication configuration.
- The `acme` prefix groups them into a single application configuration namespace.

A `@ConfigurationProperties` class can represent that structure using nested objects. For example, `AcmeProperties` has a `client` field of type `ClientSettings` and a `security` field of type `SecuritySettings`.

There are two separate questions:

1. **Can Spring Binder bind the properties into the object?** This is a question about runtime binding.
2. **Do IDEs and metadata tools properly display the nested groups and properties for autocomplete and documentation?** This is a question about configuration metadata.

`@NestedConfigurationProperty` addresses the second question in cases where the metadata processor cannot automatically infer the nested type.

## 2. What Does the Annotation Actually Do?

`org.springframework.boot.context.properties.NestedConfigurationProperty` marks a field or method in a `@ConfigurationProperties` class so that **the configuration metadata processor treats that type as a nested group**.

For example:

~~~java
@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {

    @NestedConfigurationProperty
    private ClientSettings client = new ClientSettings();

    public ClientSettings getClient() {
        return client;
    }
}
~~~

If `ClientSettings` is a standalone class outside `AcmeProperties`, the annotation tells the metadata processor that its properties belong to the `acme.client` group.

### What the Annotation Does Not Do

- It does not automatically instantiate `ClientSettings`.
- It does not automatically bind properties if the object cannot be instantiated or updated by Spring Binder.
- It does not replace `@ConfigurationProperties`, `@EnableConfigurationProperties`, or `@ConfigurationPropertiesScan`.
- It does not register reflection hints, resource hints, or JSON serialization hints.
- It does not change how Jackson binds request bodies.
- It is not an annotation to mark a new Spring bean.

**Important rule:** if the application fails to bind at runtime, adding `@NestedConfigurationProperty` will not fix the error. Inspect the class structure, instantiation capability, property names, and how configuration properties are registered.

## 3. When Is It Needed and When Is It Not?

The configuration metadata processor can automatically recognize certain nested structures. The annotation is most useful when the nested type is a **standalone class** that the processor cannot infer as a nested configuration group from the source structure.

| Structure | Is `@NestedConfigurationProperty` Needed? | Explanation |
| --- | --- | --- |
| Nested class declared inside the `@ConfigurationProperties` class | Usually no | The metadata processor can recognize inner class structures |
| Field typed as a standalone class without its own `@ConfigurationProperties` | Usually yes if you want metadata to represent it as a nested group | The annotation clarifies intent for the metadata processor |
| Field typed as a class that carries its own `@ConfigurationProperties` | No, not for nested metadata | That type already has its own metadata/configuration properties |
| Collection or array | Usually no | The metadata processor detects element types using collection rules |
| Map | Usually no | Maps are processed according to their corresponding metadata structure |
| Any arbitrary Java object unrelated to configuration | No | It does not turn that object into Spring configuration |

Example of a nested class inside the configuration class:

~~~java
@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {

    private final Client client = new Client();

    public Client getClient() {
        return client;
    }

    public static class Client {
        private URI baseUrl;

        public URI getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(URI baseUrl) {
            this.baseUrl = baseUrl;
        }
    }
}
~~~

In this case, `Client` is a nested class of `AcmeProperties`; the annotation is generally unnecessary for the metadata processor to recognize the structure.

Conversely, if `ClientSettings` resides in a separate Java file and is only referenced via a field, consider adding `@NestedConfigurationProperty` so metadata clearly exposes the `acme.client` group.

## 4. Complete Example with Standalone Nested Classes

Create the `com.example.nativeimage.config` package.

**`AcmeProperties.java`**

~~~java
package com.example.nativeimage.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.NestedConfigurationProperty;

@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {

    @NestedConfigurationProperty
    private final ClientSettings client = new ClientSettings();

    @NestedConfigurationProperty
    private final SecuritySettings security = new SecuritySettings();

    public ClientSettings getClient() {
        return client;
    }

    public SecuritySettings getSecurity() {
        return security;
    }
}
~~~

**`ClientSettings.java`**

~~~java
package com.example.nativeimage.config;

import java.net.URI;
import java.time.Duration;

public class ClientSettings {

    private URI baseUrl;
    private Duration connectTimeout = Duration.ofSeconds(2);
    private Duration readTimeout = Duration.ofSeconds(5);

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

**`SecuritySettings.java`**

~~~java
package com.example.nativeimage.config;

import java.net.URI;

public class SecuritySettings {

    private boolean enabled = true;
    private URI issuerUri;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public URI getIssuerUri() {
        return issuerUri;
    }

    public void setIssuerUri(URI issuerUri) {
        this.issuerUri = issuerUri;
    }
}
~~~

Register the properties in the application:

~~~java
package com.example.nativeimage;

import com.example.nativeimage.config.AcmeProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(AcmeProperties.class)
public class NativeImageApplication {

    public static void main(String[] args) {
        SpringApplication.run(NativeImageApplication.class, args);
    }
}
~~~

You can use `@ConfigurationPropertiesScan` instead of `@EnableConfigurationProperties` if you want to scan properties classes in appropriate packages. Choose one clear registration mechanism and avoid accidentally registering the same properties class multiple times.

### Corresponding YAML Configuration

**`src/main/resources/application.yml`**

~~~yaml
acme:
  client:
    base-url: https://api.example.test
    connect-timeout: 2s
    read-timeout: 5s
  security:
    enabled: true
    issuer-uri: https://identity.example.test
~~~

Spring Boot Binder converts kebab-case names like `base-url` to the corresponding Java property `baseUrl`, and parses duration strings like `2s` into `Duration`.

In this example, the nested objects are pre-initialized using field initializers. Binder updates the values through JavaBean accessors. `@NestedConfigurationProperty` only clarifies the nested group for metadata; the getters/setters and Binder are what participate in the actual binding process.

## 5. Verifying Runtime Binding Independently of Metadata

You can inject `AcmeProperties` into a bean to observe the bound values:

~~~java
package com.example.nativeimage;

import com.example.nativeimage.config.AcmeProperties;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationReport implements CommandLineRunner {

    private final AcmeProperties properties;

    public ConfigurationReport(AcmeProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(String... args) {
        System.out.println("client.baseUrl="
                + properties.getClient().getBaseUrl());
        System.out.println("client.connectTimeout="
                + properties.getClient().getConnectTimeout());
        System.out.println("security.enabled="
                + properties.getSecurity().isEnabled());
    }
}
~~~

With the YAML file above, the expected output includes:

~~~text
client.baseUrl=https://api.example.test
client.connectTimeout=PT2S
security.enabled=true
~~~

`Duration.toString()` represents two seconds as `PT2S`. If the application binds these values, that proves runtime binding works in the JVM run under test. It does not prove that autocomplete metadata was completely generated, nor does it prove that the native executable binds successfully.

You can also verify with a test:

~~~java
@SpringBootTest
class AcmePropertiesTests {

    @Autowired
    AcmeProperties properties;

    @Test
    void bindsNestedClientSettings() {
        assertEquals(
                URI.create("https://api.example.test"),
                properties.getClient().getBaseUrl()
        );
        assertEquals(
                Duration.ofSeconds(2),
                properties.getClient().getConnectTimeout()
        );
        assertTrue(properties.getSecurity().isEnabled());
    }
}
~~~

The test example needs to import `URI`, `Duration`, the corresponding JUnit assertions, and run within an application context containing the sample YAML configuration.

## 6. What Does the Configuration Metadata Processor Generate?

Spring Boot provides `spring-boot-configuration-processor`, an annotation processor that reads `@ConfigurationProperties` classes and generates metadata files for IDEs, documentation, and configuration tooling.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Gradle Groovy DSL:

~~~groovy
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

This is a dependency for **compile-time annotation processing**. You do not need to include it as an application runtime library just for Binder to work.

After compiling, metadata is typically generated at:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

With Gradle, the location is typically:

~~~text
build/classes/java/main/META-INF/spring-configuration-metadata.json
~~~

The exact path depends on the build tool and output configuration. You can verify after a clean compile:

~~~bash
# Maven
./mvnw clean compile

# Gradle
./gradlew clean compileJava
~~~

Then open the metadata file and look for properties such as:

~~~json
{
  "groups": [
    {
      "name": "acme.client",
      "type": "com.example.nativeimage.config.ClientSettings"
    },
    {
      "name": "acme.security",
      "type": "com.example.nativeimage.config.SecuritySettings"
    }
  ],
  "properties": [
    {
      "name": "acme.client.base-url",
      "type": "java.net.URI"
    },
    {
      "name": "acme.client.connect-timeout",
      "type": "java.time.Duration"
    },
    {
      "name": "acme.security.enabled",
      "type": "java.lang.Boolean"
    }
  ]
}
~~~

This is an **illustrative example of the metadata structure**, not a verbatim copy of a specific processor version's output. Actual metadata may contain additional fields such as `sourceType`, `defaultValue`, `description`, `deprecation`, and others.

### How Does the Annotation Affect Metadata?

If `ClientSettings` and `SecuritySettings` are standalone classes, the annotation helps the processor recognize them as subgroups of `AcmeProperties`. The desired outcome is that IDE tooling can suggest:

- `acme.client.base-url`
- `acme.client.connect-timeout`
- `acme.client.read-timeout`
- `acme.security.enabled`
- `acme.security.issuer-uri`

If a group is missing from metadata, check whether the annotation processor ran, whether the properties class is properly recognized, and whether the source structure allows the processor to infer the properties.
## 7. Distinguishing Configuration Metadata from Spring AOT

In a Native Image project, there are at least three distinct activities:

| Activity | Tool | Purpose | Output |
| --- | --- | --- | --- |
| Configuration metadata processing | `spring-boot-configuration-processor` | Support IDEs, autocomplete, and configuration docs | `spring-configuration-metadata.json` |
| Runtime configuration binding | Spring Boot Binder | Read properties and bind into objects when running or during appropriate context preparation | Populated configuration instance |
| Spring AOT processing | Spring Boot AOT engine | Analyze application context and prepare code/metadata for native | Generated initialization code and appropriate runtime hints |

`@NestedConfigurationProperty` affects **metadata processing**. It does not instruct Spring AOT to generate extra reflection hints, and it is not a mechanism for the native executable to find a class that is missing from the build.

Spring AOT recognizes configuration properties registered via `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan` and prepares support for binding in native mode according to the Spring Boot version in use. Therefore, ensure properties classes are explicitly registered and included in the build input.

### Overview Diagram

~~~mermaid
flowchart TD
    S["Class @ConfigurationProperties"] --> M["Configuration metadata processor"]
    S --> R["Spring configuration binding"]
    A["@NestedConfigurationProperty"] --> M
    M --> J["spring-configuration-metadata.json"]
    R --> B["Bind properties to object"]
    B --> C["Spring AOT analyzes context"]
    C --> H["Generated code and runtime hints"]
    H --> N["GraalVM Native Image"]
    N --> X["Native runtime"]
~~~

The diagram emphasizes that the annotation flows into the metadata processor branch. Runtime binding and Spring AOT have separate inputs and responsibilities.

## 8. Impact on GraalVM Native Image

When building native, the application needs to ensure:

1. `AcmeProperties` is discovered and registered by Spring.
2. `ClientSettings` and `SecuritySettings` can be instantiated or updated according to the chosen binding model.
3. Required property sources exist in the runtime environment.
4. Required type converters are available.
5. AOT processing sees the configuration properties and generates appropriate support.
6. The native executable is tested with the same set of configurations the application will use.

**Do not add `@NestedConfigurationProperty` just to fix a native reflection error.** If an error occurs in native while the JVM works, read the specific exception and identify the failing layer: missing configuration properties registration, constructor/binding error, converter, reflection, or another JSON library.

### Build and Test

For a Maven project configured with Spring AOT and a native profile:

~~~bash
./mvnw -Pnative clean native:compile
~~~

For a Gradle project configured with Native Build Tools:

~~~bash
./gradlew clean nativeCompile
~~~

The exact command depends on the project's plugin/profile configuration. After building, run the native executable with the corresponding `application.yml` file or environment variables and verify that the nested values are bound correctly.

You should run the same tests on both JVM and native:

- Verify default values when properties are omitted.
- Verify nested properties overridden by YAML.
- Verify the same properties via environment variables.
- Verify conversion for `URI`, `Duration`, enums, or custom types.
- Verify validation if the configuration has constraints.
- Verify missing required properties or malformed formats.

When using environment variables, Spring Boot relaxed binding typically maps names like `ACME_CLIENT_CONNECTTIMEOUT` according to property naming rules. Check the exact rules and avoid guessing variable names from field names, especially with hyphens, collection indices, and map keys.

## 9. Nested Properties with Immutable Objects and Constructor Binding

Not every configuration uses JavaBean setters. Spring Boot also supports constructor binding for immutable configuration properties, including records in supported Java/Spring Boot versions.

Record example:

~~~java
@ConfigurationProperties(prefix = "acme")
public record AcmeProperties(
        ClientSettings client,
        SecuritySettings security
) {
    public record ClientSettings(
            URI baseUrl,
            Duration connectTimeout,
            Duration readTimeout
    ) {
    }

    public record SecuritySettings(
            boolean enabled,
            URI issuerUri
    ) {
    }
}
~~~

In this model, nested records sit inside the properties structure and Spring Binder constructs objects via constructor binding. `@NestedConfigurationProperty` is not the annotation that enables constructor binding. Metadata detection for inner types and binding capabilities are determined by the type structure, how properties are registered, and the Spring Boot version.

If using standalone nested classes in an immutable configuration, inspect the constructor/record components and how the binder infers property names. Do not add metadata annotations to substitute for the constructor binding contract.

### Validation for Nested Groups

You can use Bean Validation to validate nested groups:

~~~java
@ConfigurationProperties(prefix = "acme")
@Validated
public class AcmeProperties {

    @Valid
    @NestedConfigurationProperty
    private final ClientSettings client = new ClientSettings();

    public ClientSettings getClient() {
        return client;
    }
}
~~~

The nested field uses `@Valid` to cascade validation if `ClientSettings` has constraints like `@NotNull`, `@NotBlank`, or `@Min`. `@NestedConfigurationProperty` still only serves the metadata processor; the two annotations solve two different tasks.

## 10. Do Not Confuse with Jackson JSON Binding

The module name includes both Binding and JSON, so distinguish them clearly:

- `@ConfigurationProperties` binds application configuration from properties, YAML, environment variables, and other property sources.
- Jackson binds JSON requests/responses into Java objects, typically via `@RequestBody`, `ObjectMapper`, serializers/deserializers.
- `@NestedConfigurationProperty` does not control Jackson serialization/deserialization.

JSON request example:

~~~json
{
  "customer": {
    "id": "C-100",
    "name": "Lan"
  }
}
~~~

If `OrderRequest` has a `CustomerRequest customer` field, Jackson processes the nested JSON based on class structure, constructors, accessors, annotations, and `ObjectMapper` configuration. Adding `@NestedConfigurationProperty` to that field is not how Jackson recognizes nested JSON.

In Native Image, Jackson may require reflection/binding metadata or integration hints depending on DTO types and configuration. That is a separate concern from the configuration metadata generated by `spring-boot-configuration-processor`.

## 11. Common Errors and Troubleshooting

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| IDE does not suggest `acme.client.*` | Metadata processor did not run or nested type is unrecognized | Check the annotation processor dependency and `@NestedConfigurationProperty` |
| Metadata has the group, but runtime does not bind | Class is not registered, object cannot be instantiated, or accessors are unsuitable | Check `@EnableConfigurationProperties`, scan, constructor/getter/setter |
| JVM binds, but native does not | Different AOT/native configuration, unrecognized class or converter | Inspect AOT logs, root exception, and native tests |
| Adding the annotation produces no runtime change | Expected behavior since the annotation does not control binding | Fix class structure or properties registration as actually required |
| Nested property is null | Object is uninitialized or binder cannot instantiate the nested type under the chosen model | Check field initializer, setter, or constructor binding |
| `Duration`/`URI` conversion error | Invalid configuration value or unsuitable converter | Check input format and conversion service |
| Property does not appear in metadata | Annotation processor does not see source or nested type is unmarked | Check compile task and JSON metadata output |
| JSON request does not bind nested object | Jackson DTO/constructor/accessors or hints are incorrect | Check ObjectMapper and JSON binding metadata; nested config annotation is unrelated |

### Layered Investigation Process

1. **IDE/autocomplete wrong:** check `spring-boot-configuration-processor`, compile output, and metadata JSON.
2. **JVM runtime binding wrong:** check prefix, property names, configuration properties registration, object construction, and type conversion.
3. **Native runtime binding wrong:** compare JVM and native with identical input, inspect AOT/native logs and root errors.
4. **JSON request binding wrong:** check DTOs, Jackson configuration, constructors/accessors, and native hints for JSON.
5. **After fixing:** perform a clean build, re-read metadata if source structure changed, and run tests on the native executable.

## 12. Lab Exercise: Adding a Nested Group to Native Configuration

Create a Spring Boot application with the prefix `acme` and the class `AcmeProperties`. Extract `ClientSettings` into a standalone Java class; add `@NestedConfigurationProperty` to the `client` field.

Steps:

1. Declare `spring-boot-configuration-processor` as a Maven or Gradle annotation processor.
2. Register `AcmeProperties` with `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`.
3. Create `application.yml` with `acme.client.base-url`, `connect-timeout`, and `read-timeout`.
4. Compile and open `META-INF/spring-configuration-metadata.json`; verify that the nested group/properties appear.
5. Run on the JVM, inject `AcmeProperties`, and verify the bound values.
6. Build a native executable using Spring AOT/GraalVM.
7. Run the native binary with the same YAML and environment variables; compare the results.
8. Remove the annotation in an experimental branch, recompile, and observe the effect on metadata; verify that runtime binding cannot be inferred solely from metadata changes.
9. Create a JSON request DTO with a similar nested structure and test it separately to demonstrate that this annotation does not control Jackson.

### Self-Check Questions

1. Which Spring Boot component uses `@NestedConfigurationProperty`?
2. Why can the annotation improve IDE autocomplete without altering runtime binding?
3. When is a nested class recognized without the annotation?
4. Why is `spring-boot-configuration-processor` not a required runtime dependency?
5. How does configuration metadata JSON differ from Spring AOT generated code?
6. If nested properties bind on the JVM but fail in native, which problem layers should you check?
7. Does `@NestedConfigurationProperty` affect Jackson `@RequestBody`? Why or why not?
8. Why must both metadata JSON and the native executable be verified?

**Passing criteria:** accurately explain the metadata role of `@NestedConfigurationProperty`; properly choose when to mark standalone nested types; configure `@ConfigurationProperties` and nested binding; inspect configuration metadata produced by the annotation processor; distinguish metadata from runtime binding and Spring AOT; and verify that configuration works on the native executable without confusing this annotation with Jackson hints.
