# @ConfigurationProperties and Binding in Native Applications

## 1. Two Phases to Distinguish

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring AOT prepares the application at build time so GraalVM Native Image can analyze and build the executable. When using `@ConfigurationProperties`, it is important to understand the boundary between the two phases:

1. **Build time (Spring AOT):** Spring analyzes the application structure, bean definitions, configuration classes, and required access patterns. AOT can generate initialization code and runtime hints so Native Image preserves binding capabilities.
2. **Runtime (when the native application starts):** Spring Boot reads actual property sources, converts values to Java types, validates them, and creates configuration beans. Values such as URLs, buckets, timeouts, or feature settings can still come from the runtime environment.

Key point: **AOT prepares the binding capability; it does not by default freeze every configuration value into the executable.** However, values used to determine the bean graph during AOT, such as auto-configuration conditions, can affect the structure prepared at build time.

## 2. What Is `@ConfigurationProperties` Used For?

`@ConfigurationProperties` groups properties sharing a common prefix into a strongly typed Java object. Instead of scattering configuration strings across code with `@Value`, the application can declare a structured model, leveraging centralized type conversion, default values, and validation.

For example, an application has a storage configuration group:

~~~yaml
app:
  storage:
    bucket: invoices
    connect-timeout: 5s
    endpoint: https://storage.example.internal
~~~

We want Spring to bind these values into a typed object:

~~~java
StorageProperties properties;

String bucket = properties.getBucket();
Duration timeout = properties.getConnectTimeout();
URI endpoint = properties.getEndpoint();
~~~

The Binder handles mapping from property names to Java properties, converting types such as `Duration` and `URI`, and placing the object into the ApplicationContext for other beans to consume.

## 3. Declaring a Configuration Class and Registering It with Spring

### 3.1. JavaBean Binding

Declaring a mutable JavaBean is straightforward and compatible with many Spring Boot versions:

~~~java
package com.example.storage;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

@Validated
@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {

    @NotBlank
    private String bucket;

    @NotNull
    private Duration connectTimeout = Duration.ofSeconds(5);

    @NotNull
    private URI endpoint;

    public String getBucket() {
        return bucket;
    }

    public void setBucket(String bucket) {
        this.bucket = bucket;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

`@ConfigurationProperties(prefix = "app.storage")` specifies the prefix. Spring Boot will bind properties whose names start with `app.storage` to the corresponding attributes. `@Validated` enables validation; annotations such as `@NotBlank` and `@NotNull` come from Jakarta Bean Validation.

For validation to work, the project needs a validation provider, typically added via the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

If the project uses Spring Boot 2.x, the validation namespace may be `javax.validation` instead of `jakarta.validation`. Use the namespace matching your application's major version.

### 3.2. Registering Configuration Properties

There are two common ways.

**Option A — scan configuration classes:**

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class StorageApplication {
    public static void main(String[] args) {
        SpringApplication.run(StorageApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` discovers classes annotated with `@ConfigurationProperties` in the scanned package and subpackages. Place configuration classes within the scan scope or specify appropriate packages.

**Option B — explicit registration:**

~~~java
@SpringBootApplication
@EnableConfigurationProperties(StorageProperties.class)
public class StorageApplication {
    public static void main(String[] args) {
        SpringApplication.run(StorageApplication.class, args);
    }
}
~~~

`@EnableConfigurationProperties` directly registers the configuration type to use. This is useful when you want explicit control over which properties types are enabled.

Merely placing `@ConfigurationProperties` on a class **does not make that class a bean**. It must be registered via scanning or `@EnableConfigurationProperties`. This is also what AOT needs to see in order to prepare appropriate metadata.

## 4. Binding Still Occurs When the Native Application Starts

Suppose the configuration in `application.yml` is:

~~~yaml
app:
  storage:
    bucket: invoices
    connect-timeout: 5s
    endpoint: https://storage.example.internal
~~~

Both the JVM application and the native application can read these values at startup. When running the native executable:

~~~bash
./storage-service
~~~

Spring Boot loads Config Data, creates the `Environment`, and binds values into `StorageProperties`. If a value is supplied via an environment variable or system property at runtime, the Binder can pick up that value according to property source precedence.

Example overriding `bucket` without rebuilding the native image:

~~~bash
APP_STORAGE_BUCKET=archive ./storage-service
~~~

For the canonical property `app.storage.bucket`, the corresponding environment variable name is `APP_STORAGE_BUCKET`. When running in a container, environment variables can be passed through deployment configuration:

~~~bash
docker run --rm \
  -e APP_STORAGE_BUCKET=archive \
  -p 8080:8080 \
  storage-service:native
~~~

Thus, **configuration values can change per runtime environment** without recompiling the executable, provided they do not change the bean structure already decided during AOT.

## 5. Relaxed Binding and Type Conversion

Spring Boot supports relaxed binding so common property notations map to the same field. For instance, the Java property `connectTimeout` can be declared in YAML in kebab case:

~~~yaml
app:
  storage:
    connect-timeout: 5s
~~~

Or supplied via an environment variable following the name conversion rules:

~~~bash
APP_STORAGE_CONNECTTIMEOUT=8s
~~~

For environment variables, Spring Boot converts a canonical property name by:

1. Replacing dots (`.`) with underscores (`_`).
2. Removing dashes (`-`).
3. Converting everything to uppercase.

Therefore `app.storage.connect-timeout` becomes `APP_STORAGE_CONNECTTIMEOUT`. Do not insert underscores between individual words of a dashed name if you want to follow canonical conversion rules.

The Binder also supports converting common types:

| Java type | Example config value | Result |
| --- | --- | --- |
| `Duration` | `5s`, `250ms`, `PT2M` | Time duration |
| `DataSize` | `16MB`, `512KB` | Data size |
| `URI` / `URL` | `https://storage.example.internal` | Resource address |
| `InetAddress` | `127.0.0.1` | Network address |
| Enum | `S3`, `LOCAL` | Matching enum constant |
| List/Set | YAML list or indexed properties | Collection of elements |
| Map | Child keys under prefix | Key/value map |

Prefer kebab-case property names in configuration files. For collections and maps, pay attention to index and key syntax when passing via environment variables; for complex structures, YAML files or Config Data are usually easier to read and less error-prone.

## 6. Nested Binding, Collections, and Default Values

Real-world configuration often includes nested groups:

~~~yaml
app:
  storage:
    bucket: invoices
    connect-timeout: 5s
    endpoint: https://storage.example.internal
    retry:
      max-attempts: 3
      backoff: 200ms
    allowed-regions:
      - ap-southeast-1
      - ap-southeast-2
~~~

The configuration class can be extended:

~~~java
@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {

    private String bucket;
    private Duration connectTimeout = Duration.ofSeconds(5);
    private URI endpoint;
    private Retry retry = new Retry();
    private List<String> allowedRegions = new ArrayList<>();

    public static class Retry {
        private int maxAttempts = 3;
        private Duration backoff = Duration.ofMillis(200);

        public int getMaxAttempts() { return maxAttempts; }
        public void setMaxAttempts(int value) { this.maxAttempts = value; }
        public Duration getBackoff() { return backoff; }
        public void setBackoff(Duration value) { this.backoff = value; }
    }

    public String getBucket() { return bucket; }
    public void setBucket(String value) { this.bucket = value; }
    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration value) { this.connectTimeout = value; }
    public URI getEndpoint() { return endpoint; }
    public void setEndpoint(URI value) { this.endpoint = value; }
    public Retry getRetry() { return retry; }
    public void setRetry(Retry value) { this.retry = value; }
    public List<String> getAllowedRegions() { return allowedRegions; }
    public void setAllowedRegions(List<String> value) { this.allowedRegions = value; }
}
~~~

The snippet above illustrates JavaBean binding; in a real project, add validation, constructors, and accessors per codebase conventions. Nested objects can be bound through their corresponding properties. For mutable nested objects, initializing defaults gives the application fallback values when sub-properties are not provided.

A note about collections: when the Binder receives a list value from a higher-precedence property source, the list can be replaced by that source rather than always merging elements across all sources. Test collection override behavior if staging/production environments supply different configurations.

## 7. Constructor Binding and Immutable Configuration

Instead of a JavaBean with setters, constructor binding can be used to create immutable configuration objects. Example using a record in Spring Boot 3:

~~~java
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
    String bucket,
    Duration connectTimeout,
    URI endpoint
) {
}
~~~

A record has a single canonical constructor, so Spring Boot 3 can use constructor binding without setters. If a class has multiple constructors, specify constructor binding according to the rules of your Spring Boot version. Older Boot versions differ in the placement/usage of `@ConstructorBinding`, so check the API for your project's major version.

Constructor binding offers advantages:

- Objects are fully constructed via the constructor, fitting immutable designs well.
- Default values and nested objects can be declared via constructor parameters and appropriate annotations.
- No need to expose setters for configuration properties.

However, nested types, optional parameters, default values, and validation must be declared clearly. Do not mix constructor binding with arbitrary manual bean registration via `@Component` or `@Bean`; use scanning or `@EnableConfigurationProperties` properly.

## 8. How Do Spring AOT and Native Image Prepare Binding?

On the JVM, the Binder can use reflection and Java type metadata to read property names, constructors, getters/setters, annotations, and field types. GraalVM Native Image operates under a closed-world analysis; members only accessed dynamically may be removed without the necessary metadata.

For configuration properties properly registered with Spring Boot via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, Spring Boot AOT/native support can contribute runtime hints for the necessary types so binding works in the native executable.

Conceptual flow:

~~~mermaid
flowchart TB
    P["@ConfigurationProperties type"] --> R["Register via scan or EnableConfigurationProperties"]
    R --> A["Spring AOT detects configuration type"]
    A --> H["Runtime hints / metadata for Native Image"]
    H --> N["GraalVM analyzes and retains required access"]
    N --> E["Native executable"]
    E --> S["Runtime: read Environment / Config Data"]
    S --> B["Binder converts and validates values"]
    B --> O["ConfigurationProperties bean"]
~~~

This **does not mean the Binder has already run and real values were written into the executable at build time**. AOT prepares the types, structure, and required metadata. When the executable starts, the Binder still reads property sources present in the runtime environment and builds the object with those values.

### 8.1. Why Must Types Be Registered Properly?

If a class has `@ConfigurationProperties` but is neither scanned nor enabled, it may not become a bean, will not be recognized by AOT as a configuration properties bean, and other code will be unable to inject it.

Use one of these two approaches:

~~~java
@ConfigurationPropertiesScan
@SpringBootApplication
class Application {
}
~~~

Or:

~~~java
@EnableConfigurationProperties(StorageProperties.class)
@SpringBootApplication
class Application {
}
~~~

There is no need to add `@Component` just to turn the class into a bean when using one of the two mechanisms above.

### 8.2. When Is a Custom `RuntimeHintsRegistrar` Needed?

First check whether the error truly comes from configuration properties binding. Spring Boot already provides native support for many common cases. Only add manual hints when:

- A type or member is accessed via reflection outside what the framework detects.
- A custom binder/converter uses reflection or dynamic resources.
- A third-party library lacks required reachability metadata.
- The native failure explicitly points to a missing constructor, method, field, or resource.

Example registering a reflection-invoked constructor for an application-defined type:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(StorageRuntimeHints.class)
class StorageNativeConfiguration {
}

class StorageRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            LegacyStorageDescriptor.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
    }
}
~~~

This is only an example for one specific access pattern. If the Binder needs to invoke setters, read fields, or call a different constructor, the hints must reflect those exact members. Do not register whole classes or entire packages broadly without reason.

## 9. Two Kinds of Configuration: Runtime Values vs. Build-Time Structure

This is the easiest point to confuse when bringing `@ConfigurationProperties` into a native image.

| Configuration kind | Example | Decision timing |
| --- | --- | --- |
| Values used inside existing beans | bucket, endpoint, timeout, retry count | Typically bound when the native app starts |
| Secrets/credentials supplied by environment | API key, database password | Runtime via environment/secret/config source |
| Bean structure depending on conditions | `@ConditionalOnProperty` toggling a bean | Can be evaluated during AOT processing |
| Auto-configuration depending on classpath | Presence/absence of a library or class | Build time/AOT based on classpath |
| Runtime profile affecting bean graph | Profile altering bean definitions | Must account for when AOT evaluates profiles/conditions |

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class StorageConfiguration {
    @Bean
    StorageClient storageClient(StorageProperties properties) {
        return new StorageClient(
            properties.getEndpoint(),
            properties.getBucket()
        );
    }
}
~~~

The `StorageClient` bean is still created at application startup and receives values bound from `StorageProperties`. If the endpoint differs between staging and production, a different property can be supplied when running the native binary.

Conversely:

~~~java
@Bean
@ConditionalOnProperty(prefix = "app.storage", name = "enabled", havingValue = "true")
StorageClient storageClient(StorageProperties properties) {
    return new StorageClient(properties.getEndpoint(), properties.getBucket());
}
~~~

The condition deciding **whether the bean exists** can be processed during AOT. If the AOT build ran under a configuration where the bean was not registered, changing `app.storage.enabled=true` at runtime will not make Spring recreate the generated bean graph.

Do not put secret credentials into build-time configuration or generated artifacts. Secrets should be supplied via a secret manager, environment variables, or an appropriate runtime configuration source; avoid writing them into logs, generated files, or container layers.

## 10. Validation and Binding Errors

`@ConfigurationProperties` supports validation when the class is annotated with `@Validated` and a validation provider is on the classpath.

Example:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {

    @NotBlank
    private String bucket;

    @Min(1)
    @Max(60)
    private int connectTimeoutSeconds = 5;

    // getters/setters
}
~~~

If `bucket` is blank or timeout is out of range, the application can fail immediately at startup. This is helpful behavior: misconfiguration is caught before endpoints accept traffic.

For nested objects, use `@Valid` to cascade validation into the child object:

~~~java
@Valid
private Credentials credentials;
~~~

When errors appear in native mode:

- Check whether the property key has the right prefix and canonical name.
- Verify the property source was actually loaded.
- Check for type conversion errors (e.g., a string that is not a valid duration).
- Check validation constraints and the validation provider dependency.
- Distinguish Binder errors from Native Image reflection/reachability errors.

## 11. Testing Binding on the JVM and Native Executable

Do not rely solely on a successful native image build. Verify the values actually bound at runtime.

### 11.1. Context Tests with Explicit Properties

Spring Boot integration test example:

~~~java
@SpringBootTest(properties = {
    "app.storage.bucket=test-bucket",
    "app.storage.connect-timeout=2s",
    "app.storage.endpoint=https://localhost"
})
class StoragePropertiesTest {

    @Autowired
    private StorageProperties properties;

    @Test
    void bindsConfiguredValues() {
        assertThat(properties.getBucket()).isEqualTo("test-bucket");
        assertThat(properties.getConnectTimeout()).isEqualTo(Duration.ofSeconds(2));
        assertThat(properties.getEndpoint()).isEqualTo(URI.create("https://localhost"));
    }
}
~~~

The test requires appropriate AssertJ static imports and the project's test dependencies. The goal is to confirm the Binder produces the right types/values and applies validation.

### 11.2. Testing Environment Overrides on Native Runs

After building the executable, run with different properties:

~~~bash
APP_STORAGE_BUCKET=runtime-bucket ./target/storage-service
~~~

Expose a safe endpoint or log to confirm the active bucket is the runtime value. Do not print credentials/secrets to verify configuration.

### 11.3. Native Tests and Smoke Tests

If the project configures native tests via GraalVM Native Build Tools, run the appropriate native tests. In addition, a smoke test executing the binary/container in a production-like environment helps catch failures JVM tests cannot simulate, such as missing reflection metadata or resources.

A useful test matrix:

| Case | JVM test | Native test/smoke |
| --- | --- | --- |
| YAML binding | Verify default and declared values | Confirm binary reads Config Data |
| Environment override | Pass env var in test/process | Run binary with env var differing from build time |
| Type conversion | Duration, URI, enum, list/map | Confirm conversion matches JVM |
| Validation | Missing/invalid values must error | Confirm native fails startup clearly |
| Nested properties | Bind child objects and collections | Confirm nested types work |
| Conditional bean | Test condition configuration | Confirm bean graph matches AOT variant |

## 12. Common Pitfalls and How to Diagnose Them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Cannot inject properties bean | Class not scanned or enabled | Add `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` |
| Values always null/default | Wrong prefix/key or property source not loaded | Check canonical names, profiles, and Config Data |
| JVM binds fine, native fails with reflection error | Dynamic type/member lacks metadata | Confirm properties type is registered; check runtime hints and exact error |
| Environment variable does not override | Wrong env var name conversion | Apply uppercase, dots to underscores, remove dashes |
| Error converting Duration/URI/enum | Invalid config value or missing converter | Use a supported format; check custom converters |
| Validation does not run | Missing `@Validated` or validation provider | Add the annotation and matching dependency |
| Nested object is not validated | Missing `@Valid` on parent field | Enable cascade validation |
| Runtime enables feature, bean does not appear | Condition/bean graph was processed during AOT with another config | Build AOT with matching config or redesign feature as runtime logic |
| Secret appears in artifact | Secret placed in build-time property or generated output | Remove secret from build; supply via secret store at runtime |

When diagnosing in native mode, classify the issue:

1. **Missing bean:** inspect configuration properties registration and AOT conditions.
2. **Bean exists but wrong values:** inspect property sources, key names, conversion, and validation.
3. **Fails only in native:** inspect reachability metadata/runtime hints for the involved types or converters.
4. **Runtime config changed but bean graph unchanged:** check whether a condition was decided at AOT time.

## 13. Practical Workflow from Source to Native

Suppose a storage service uses `app.storage` and needs the same binary to run in staging and production with different buckets, endpoints, and timeouts.

**Step 1 — Declare and register properties**

- Create `StorageProperties` with appropriate Java types.
- Use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.
- Add validation if values are required.

**Step 2 — Default configuration without secrets**

~~~yaml
app:
  storage:
    bucket: local-test
    connect-timeout: 5s
    endpoint: https://storage.example.internal
~~~

Do not commit credentials to configuration files or JARs.

**Step 3 — Run JVM tests**

~~~bash
./mvnw test
# Or:
./gradlew test
~~~

Verify binding, conversion, nested values, and validation.

**Step 4 — Run Spring AOT and build native image**

With Maven, use the profile/goal configured in the POM; with Gradle, use the `nativeCompile` task once Spring Boot and Native Build Tools plugins are configured. Inspect AOT and native compilation logs.

**Step 5 — Run executable with runtime configuration**

~~~bash
APP_STORAGE_BUCKET=staging-invoices ./target/storage-service
~~~

For production, supply bucket/endpoint/secrets from a secret manager or deployment platform environment. Do not rebuild merely to change runtime property values.

**Step 6 — Test the bean graph and conditional features**

If a property used in `@ConditionalOnProperty` alters bean registration, verify that configuration was applied during AOT. When distinct bean graph variants are needed, consider building separate native artifacts or redesigning so conditions are handled at runtime.

## 14. Takeaways

- `@ConfigurationProperties` defines a typed configuration model; the Binder still reads values from `Environment`/Config Data when the native application starts.
- Spring AOT detects registered properties types and prepares the metadata needed for Native Image to preserve binding.
- Environment variables, system properties, and runtime configuration files can supply different values to the same native executable.
- Bean conditions and ApplicationContext structure can be decided at build time; do not confuse them with property values bound at runtime.
- If the JVM works but native fails, inspect registration, conversion, validation, and reachability hints according to the exact symptom before adding manual metadata.

Understanding the boundary **AOT prepares binding capability — Binder reads values at runtime — Native Image retains required types/members** helps configure a Spring Boot native executable that is secure, portable across environments, and easy to diagnose.
