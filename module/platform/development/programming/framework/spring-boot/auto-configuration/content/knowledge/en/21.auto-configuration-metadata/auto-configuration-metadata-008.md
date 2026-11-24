# Deprecated Property Metadata and Replacement Key Guidance

## 1. Why Mark Properties as Deprecated?

Properties are part of the public API of a Spring Boot library. Users may store them in `application.yml`, `application.properties`, environment variables, ConfigMaps, Helm charts, deployment pipelines, or command-line arguments. When a key needs to be renamed, change meaning, or be removed, silent changes can cause applications to:

- Keep using the old key without knowing it is about to be removed.
- Not know which new key replaces the old key.
- Lose configuration after upgrading the library version.
- Use a different default value because the old key is no longer bound.
- Have documentation and IDE suggestions that mismatch runtime behavior.

Spring Boot provides **configuration metadata** so IDEs and configuration support tools display property names, data types, descriptions, defaults, and deprecation information. When a property is deprecated, metadata can indicate:

- Deprecation level: `warning` or `error`.
- Reason why the property is being replaced.
- Full name of the replacement property.
- Version when deprecation started.

In this article, examples use Java 17 and Spring Boot 3.3.13. This is an illustrative baseline for concrete code and dependencies; for real projects, use the exact release line the library supports.

**Important point:** deprecation metadata helps users know they need to update configuration. It does not automatically perform key migration, does not automatically transfer the old value to the new key, and does not automatically emit runtime warning logs.

## 2. Where Does Configuration Metadata Live?

Spring Boot packages metadata in the JAR at:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Metadata is divided into several groups:

| Group | Purpose |
| --- | --- |
| `groups` | Describes configuration groups/prefixes, e.g., `acme.client` |
| `properties` | Describes individual value-bearing keys, e.g., `acme.client.endpoint` |
| `hints` | Suggests valid values or suggestion providers for IDEs |
| `ignored` | Properties intentionally excluded from generated metadata |

Condensed structure example:

~~~json
{
  "groups": [
    {
      "name": "acme.client",
      "type": "com.acme.ClientProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.client.endpoint",
      "type": "java.lang.String",
      "description": "Base endpoint used by the client."
    }
  ],
  "hints": []
}
~~~

This file primarily serves the developer experience: autocomplete, contextual help, IDE validation/suggestions, and configuration documentation. The annotation processor generates most metadata from classes annotated with `@ConfigurationProperties`; special cases can add manual metadata.

Do not confuse metadata with runtime configuration:

- `@ConfigurationProperties` and Binder decide which values are bound into objects.
- `@DeprecatedConfigurationProperty` helps the annotation processor generate deprecation metadata.
- `additional-spring-configuration-metadata.json` supplements or adjusts metadata.
- Migration/alias code or removing accessors is what decides whether runtime still accepts the old key.

## 3. Four Deprecation Fields in Metadata

In each element of the `properties` array, deprecation info sits inside the `deprecation` object:

~~~json
{
  "name": "acme.client.url",
  "type": "java.lang.String",
  "deprecation": {
    "level": "warning",
    "reason": "Use the endpoint property instead.",
    "replacement": "acme.client.endpoint",
    "since": "2.0.0"
  }
}
~~~

| Field | Meaning | Good Practice |
| --- | --- | --- |
| `level` | Deprecation level: `warning` or `error`; defaults to `warning` | Choose based on whether the property is still supported or no longer managed |
| `reason` | Concise reason why the property was deprecated | State the issue and the action users should take |
| `replacement` | Full name of the replacement property | Use the canonical key, e.g., `acme.client.endpoint` |
| `since` | Version when deprecation began | Record the library/Boot version where the contract announced deprecation |

### 3.1. level=warning

`warning` is the default level. The property is still considered supported during a transition period. Configuration tools can display warnings and suggest the replacement property, while the library retains the ability to bind the old key.

Example:

~~~json
{
  "name": "acme.client.url",
  "type": "java.lang.String",
  "deprecation": {
    "level": "warning",
    "reason": "Renamed to make the meaning explicit.",
    "replacement": "acme.client.endpoint",
    "since": "2.0.0"
  }
}
~~~

Use this level when the library still keeps getters/setters or constructor binding for backward compatibility. Users have time to migrate configuration before the old key is removed.

### 3.2. level=error

`error` indicates the property is no longer managed/supported and metadata does not treat it as a still-bound key. This is a strong signal for IDEs/tools to warn users not to keep using the old key.

Example:

~~~json
{
  "name": "acme.client.legacy-url",
  "type": "java.lang.String",
  "deprecation": {
    "level": "error",
    "reason": "This property was removed. Configure the endpoint property instead.",
    "replacement": "acme.client.endpoint",
    "since": "3.0.0"
  }
}
~~~

Distinguish **metadata reporting the key was removed** from **runtime code actually no longer binding that key**. JSON metadata is descriptive data for tooling; merely adding `level=error` does not write conversion logic, does not delete Java fields, and does not throw an exception in Spring Binder. When you want the old key to stop binding, remove the corresponding accessor/constructor parameter or implement an explicit rejection policy at runtime. Error metadata helps users know the key is no longer supported.

### 3.3. reason

Write an actionable reason. Good example:

~~~text
The url property was renamed to endpoint to clarify that it is a base URI.
Use acme.client.endpoint instead.
~~~

Avoid vague reasons like `Old property`, `Deprecated`, or `Use new config`. You should state:

1. What changed.
2. Why it changed.
3. Which key users need to configure.

The description should be short and easy to read in an IDE. Spring Boot recommends writing a short paragraph; the first line states the main point and the last line ends with a period.

### 3.4. replacement

`replacement` is the **full name of the new property**, not the Java field name and not just the suffix.

Correct:

~~~json
"replacement": "acme.client.endpoint"
~~~

Unclear:

~~~json
"replacement": "endpoint"
~~~

If the old property does not have a single direct replacement property, you can omit the `replacement` field. When multiple old keys need to move into a new structure, describe the detailed mapping in the reason, migration guide, and release notes; a single replacement field cannot express complex transformations completely.

## 4. Using @DeprecatedConfigurationProperty in Code

Spring Boot provides the annotation:

~~~java
org.springframework.boot.context.properties.DeprecatedConfigurationProperty
~~~

This annotation:

- Must be placed on the **getter** of the deprecated property in a `@ConfigurationProperties` class.
- Tells the annotation processor that the property needs deprecation metadata generated.
- Has attributes `reason`, `replacement`, `since`.
- Does not have a `level` attribute; auto-generated metadata always assumes `warning`, because code is still handling that property.
- **Does not directly affect the binding process.**

You should also use Java's `@Deprecated` annotation so Java/Kotlin code consuming the old accessor also knows the API is deprecated.

### 4.1. Example: Renaming acme.client.url to acme.client.endpoint

Suppose version 2.0 of the library renames the key from:

~~~yaml
acme:
  client:
    url: https://api.example.test
~~~

to:

~~~yaml
acme:
  client:
    endpoint: https://api.example.test
~~~

During the compatibility period, the properties class can keep both accessors:

**ClientProperties.java**

~~~java
package com.acme.client;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.DeprecatedConfigurationProperty;

@ConfigurationProperties(prefix = "acme.client")
public class ClientProperties {

    private String endpoint;

    // Old accessor retained for compatibility with published configuration.
    private String url;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    @Deprecated
    @DeprecatedConfigurationProperty(
            reason = "The url property was renamed to endpoint for clarity. "
                    + "Use acme.client.endpoint instead.",
            replacement = "acme.client.endpoint",
            since = "2.0.0")
    public String getUrl() {
        return url;
    }

    @Deprecated
    public void setUrl(String url) {
        this.url = url;
    }

    /**
     * The new property takes precedence when both keys are configured.
     */
    public String effectiveEndpoint() {
        return endpoint != null ? endpoint : url;
    }
}
~~~

Explanation:

- `getEndpoint()/setEndpoint()` creates the new property `acme.client.endpoint`.
- `getUrl()/setUrl()` still lets Binder receive the old property `acme.client.url`.
- `@Deprecated` marks the old Java accessor.
- `@DeprecatedConfigurationProperty` is placed on the old getter so the processor generates metadata.
- `effectiveEndpoint()` is runtime logic written by the library itself: use the new key if present; otherwise fall back to the old key.

**Note:** Spring Boot does not automatically call `effectiveEndpoint()` and does not automatically treat `replacement` as an alias. The library intentionally keeps both properties and defines how to pick the value. If both keys appear together, this example specifies that the new key wins. This is a code policy that must be tested and documented.

### 4.2. Expected Auto-Generated Metadata

After compiling with the configuration processor, metadata will have both the new property and the old property. The deprecation part of the old key looks similar to:

~~~json
{
  "name": "acme.client.url",
  "type": "java.lang.String",
  "sourceType": "com.acme.client.ClientProperties",
  "deprecation": {
    "level": "warning",
    "reason": "The url property was renamed to endpoint for clarity. Use acme.client.endpoint instead.",
    "replacement": "acme.client.endpoint",
    "since": "2.0.0"
  }
}
~~~

The metadata processor may generate additional description, group, and source information. The example above only illustrates the key portion to verify; it is not the entire JSON file.

### 4.3. Do Not Put the Annotation on the Setter Instead of the Getter

Wrong target:

~~~java
@DeprecatedConfigurationProperty(replacement = "acme.client.endpoint")
public void setUrl(String url) {
    this.url = url;
}
~~~

Correct:

~~~java
@DeprecatedConfigurationProperty(replacement = "acme.client.endpoint")
public String getUrl() {
    return url;
}
~~~

The annotation is designed for getters, and the annotation processor looks up deprecation metadata from getters. You can simultaneously mark the setter with `@Deprecated`, but `@DeprecatedConfigurationProperty` must sit on the getter.

## 5. Adding Manual Metadata with additional-spring-configuration-metadata.json

There are cases where you cannot keep the old getter just to generate metadata:

- The property was already deleted from the Java class.
- The property does not bind to a `@ConfigurationProperties` class.
- You want to continue showing deprecation info after the old accessor was removed.
- You need to set `level=error`, which `@DeprecatedConfigurationProperty` does not support.
- You want to adjust description, default, or deprecation of auto-generated metadata.

In those cases, create the file:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

### 5.1. Keeping Hints After Removing the Old Accessor

Suppose version 3.0 removed `getUrl()/setUrl()`, leaving only the `acme.client.endpoint` property. We still want the IDE to report that the old key is no longer supported:

~~~json
{
  "properties": [
    {
      "name": "acme.client.url",
      "type": "java.lang.String",
      "description": "Removed in version 3.0.0. Configure acme.client.endpoint instead.",
      "deprecation": {
        "level": "error",
        "reason": "The url property was removed in 3.0.0. Configure endpoint instead.",
        "replacement": "acme.client.endpoint",
        "since": "3.0.0"
      }
    }
  ]
}
~~~

The additional file is merged by the annotation processor into the main metadata file. When the property is no longer in the properties class, the manual entry can still preserve information so tooling recognizes the old key.

**Runtime still must be handled in actual code:** if the class no longer has the `url` accessor or corresponding constructor parameter, Binder has no target property to bind under the current JavaBean/constructor model. The JSON file does not replace removing accessors or writing migration logic.

### 5.2. Adding Deprecation to an Auto-Detected Property

If the annotation processor already found `acme.client.url`, manual metadata can override metadata fields such as description, default value, and deprecation when these fields are provided.

Example:

~~~json
{
  "properties": [
    {
      "name": "acme.client.url",
      "deprecation": {
        "level": "warning",
        "reason": "Use the endpoint property instead.",
        "replacement": "acme.client.endpoint",
        "since": "2.0.0"
      }
    }
  ]
}
~~~

Only `name` is needed to identify an existing property; the provided fields adjust the corresponding metadata. If the property was not detected in the current module, the manual entry can be added as new property metadata.

### 5.3. When to Use ignored Instead of deprecation?

Metadata has an `ignored.properties` section to exclude intentionally ignored properties from the generated metadata list. This is not a replacement for deprecation guidance:

- Use `deprecation` when you want users to see the old key and learn the replacement key.
- Use `ignored` when you want to exclude a property from metadata because it should not be suggested as supported configuration.
- Do not delete a property from metadata just because it is old if users need migration info.

## 6. Generating Metadata with Spring Boot Configuration Processor

The processor dependency is typically declared as optional because it is a build-time tool:

**Maven**

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

If configuring the annotation processor explicitly via Maven Compiler Plugin, add the processor to that configuration:

~~~xml
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
                        <version>3.3.13</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

In the example above, the processor version is aligned with Spring Boot 3.3.13. If the build has Lombok or other annotation processors, declare them in `annotationProcessorPaths` and ensure appropriate processing order.

**Gradle**

~~~groovy
dependencies {
    annotationProcessor "org.springframework.boot:spring-boot-configuration-processor:3.3.13"
}
~~~

If using `additional-spring-configuration-metadata.json` with Gradle, the `compileJava` task needs to depend on `processResources` so supplemental metadata is present when the annotation processor runs:

~~~groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
~~~

After building, inspect:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

And inside the packaged JAR:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Do not inspect only the source JSON in `src/main/resources`: you need to confirm the final metadata file after processor merge was generated and packaged into the published artifact.

## 7. Complete Maven Project Example and Migration Tests

The example below illustrates the version 2.0 phase: the new key is `acme.client.endpoint`, the old key `acme.client.url` still binds at warning level and is resolved into the effective value using the new-key-wins rule.

### 7.1. Structure

~~~text
client-metadata-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/client/
    │   │   └── ClientProperties.java
    │   └── resources/
    └── test/
        └── java/com/acme/client/
            └── ClientPropertiesTests.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>client-metadata-demo</artifactId>
    <version>2.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot</artifactId>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
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
~~~

### 7.3. ClientProperties.java

Create `src/main/java/com/acme/client/ClientProperties.java` using the complete class from section 4.1.

### 7.4. ClientPropertiesTests.java

~~~java
package com.acme.client;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ClientPropertiesTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PropertiesConfiguration.class);

    @Test
    void legacyKeyStillBindsDuringWarningPeriod() {
        runner.withPropertyValues(
                "acme.client.url=https://legacy.example.test")
                .run(context -> {
                    assertThat(context).hasSingleBean(ClientProperties.class);

                    ClientProperties properties =
                            context.getBean(ClientProperties.class);

                    assertThat(properties.getUrl())
                            .isEqualTo("https://legacy.example.test");
                    assertThat(properties.effectiveEndpoint())
                            .isEqualTo("https://legacy.example.test");
                });
    }

    @Test
    void replacementKeyBinds() {
        runner.withPropertyValues(
                "acme.client.endpoint=https://new.example.test")
                .run(context -> {
                    ClientProperties properties =
                            context.getBean(ClientProperties.class);

                    assertThat(properties.getEndpoint())
                            .isEqualTo("https://new.example.test");
                    assertThat(properties.effectiveEndpoint())
                            .isEqualTo("https://new.example.test");
                });
    }

    @Test
    void replacementWinsWhenBothKeysArePresent() {
        runner.withPropertyValues(
                "acme.client.url=https://legacy.example.test",
                "acme.client.endpoint=https://new.example.test")
                .run(context -> {
                    ClientProperties properties =
                            context.getBean(ClientProperties.class);

                    assertThat(properties.effectiveEndpoint())
                            .isEqualTo("https://new.example.test");
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class PropertiesConfiguration {
    }
}
~~~

Run:

~~~bash
mvn clean test
~~~

Expect **three passing tests**:

1. Old key still binds during the warning phase.
2. New key binds normally.
3. If both keys are present, the library's code selects the new key.

Calls to `getUrl()` in tests may produce compiler deprecation warnings. That is intentional: the test is verifying compatibility of the old accessor.

### 7.5. Checking Generated Metadata

After `mvn clean test`, inspect the file:

~~~text
target/classes/META-INF/spring-configuration-metadata.json
~~~

Find `acme.client.url` and confirm it contains:

~~~json
"deprecation": {
  "level": "warning",
  "reason": "The url property was renamed to endpoint for clarity. Use acme.client.endpoint instead.",
  "replacement": "acme.client.endpoint",
  "since": "2.0.0"
}
~~~

You can check with the command:

~~~bash
grep -n -A8 -B2 '"name": "acme.client.url"' target/classes/META-INF/spring-configuration-metadata.json
~~~

In PowerShell:

~~~powershell
Select-String -Path target/classes/META-INF/spring-configuration-metadata.json -Pattern 'acme.client.url' -Context 0,8
~~~

Metadata contents may differ in field ordering or have additional attributes. What must be verified is the right property name, warning level, reason, replacement, and since.

## 8. Safe Deprecation Roadmap Across Multiple Releases

Do not deprecate and delete a property at the same time if the library already has users. A manageable roadmap:

### Phase A — Introduce the New Key

Version 2.0:

- Publish `acme.client.endpoint`.
- Keep `acme.client.url` for compatibility.
- Attach `@Deprecated` and `@DeprecatedConfigurationProperty` to the old getter.
- Leave the default metadata level at warning.
- If both keys appear, clearly specify which key wins.
- Update documentation, YAML examples, release notes, and migration guide.

### Phase B — Remind and Measure Usage

In subsequent patch/minor releases:

- Maintain the runtime alias per the published policy.
- State the planned removal timeline for the old key.
- If using telemetry/logging, only log warnings in a way that does not expose property values or secrets; do not log raw config.
- Do not add startup warnings for all users unless the library has an established logging policy.
- Test both old-key-only and new-key-only configurations.

### Phase C — Remove the Runtime Alias

In a major release with breaking changes:

- Delete the old getter/setter or old constructor parameter.
- Keep the new property and test that the new key still binds.
- Add manual metadata with `level=error`, replacement, and since so IDEs still explain the old key.
- Update migration guide, changelog, and configuration examples.
- If you want to explicitly reject when an application still declares the old key, implement a separate check (e.g., an early Environment check or intentional validation); error metadata alone does not raise a runtime exception.

### Phase D — Clean Up Metadata When No Longer Needed

After one or more releases, if there is no longer a need to remind users about the old key, you can remove the deprecated metadata entry. This decision depends on the library's lifecycle and migration support needs; do not remove guidance while significant legacy configs remain.

## 9. Non-Trivial Replacement Cases

### 9.1. One-to-One Rename

This is the easiest case:

~~~text
acme.client.url  ->  acme.client.endpoint
~~~

Metadata can use `replacement` directly.

### 9.2. One Old Key Split into Multiple New Keys

Example:

~~~text
acme.client.timeout
    -> acme.client.connect-timeout
    -> acme.client.read-timeout
~~~

A single `replacement` field cannot describe two replacement keys. Write a reason clearly stating the mapping, provide a migration guide, and implement runtime conversion per published rules. Do not arbitrarily pick one replacement and leave users thinking it is the complete mapping.

### 9.3. Multiple Old Keys Merged into One Object

Example:

~~~text
acme.client.ssl-key-store
acme.client.ssl-key-store-password
    -> acme.client.ssl.bundle
~~~

You can point replacement to the new group if appropriate, but you must describe how to convert values, where to store secrets, and which attributes no longer have direct equivalents. One replacement key cannot carry all the data of two old keys.

### 9.4. Changing Data Types

For example, the old key was an integer in milliseconds, and the new key is `Duration`:

~~~text
acme.client.timeout-ms=3000
acme.client.timeout=3s
~~~

Metadata can point to the new key name, while runtime migration must convert units accurately. Test boundaries such as 0, negative numbers, overflow, and invalid values. Do not assume the IDE will automatically convert `3000` into `3s`.

## 10. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| IDE does not show old key as deprecated | Missing processor, annotation placed in wrong location, or metadata not packaged | Place annotation on getter, build, and inspect JAR |
| Placing `@DeprecatedConfigurationProperty` on setter | Annotation processor does not look up metadata on setters | Move annotation to getter; setter can use `@Deprecated` only |
| Assuming annotation auto-converts old key to new key | Confusing metadata with runtime binder | Keep alias getter/setter and write explicit migration logic |
| Assuming `replacement` auto-edits YAML | Replacement is only metadata guidance | Update config files via migration guide or migration code |
| Wanting level=error but annotation lacks that attribute | Annotation only generates warning | Use additional metadata JSON |
| Removing old accessor without keeping guidance | Auto-generated metadata for old accessor disappears too | Add manual metadata with level=error |
| Error metadata yet runtime still reads old key | Code still has accessor/constructor parameter or custom migration | Review runtime model; metadata does not replace removal logic |
| Both old and new keys configured produce unpredictable results | Precedence not defined | Write precedence logic and test the both-present case |
| Replacement only lists suffix | Incomplete property name | Write full canonical property path |
| Reason is too generic | Users do not know why/what to switch to | Write specific reason and action |
| Metadata source is right yet JAR lacks file | Processor did not run or resource not packaged | Check annotation processor and post-build output |
| Renaming key in code without updating docs | Contract diverges between metadata, README, and samples | Synchronize release notes, sample YAML, docs, and tests |

## 11. Pre-Release Review Checklist

### Metadata

- [ ] Old key has full canonical name in the right namespace.
- [ ] `level` is appropriate: warning when still supported, error when removed.
- [ ] `reason` clearly states why and what action to take.
- [ ] `replacement` is the full property name, not just a suffix.
- [ ] `since` is the version where deprecation began.
- [ ] Annotation is placed on the getter if using `@DeprecatedConfigurationProperty`.
- [ ] Manual metadata is at the right path and gets merged.
- [ ] Final metadata is packaged inside the JAR.

### Runtime compatibility

- [ ] Decided how long the old key will remain bound.
- [ ] Runtime alias has explicit code, not relying on metadata.
- [ ] Precedence is defined if both old and new keys appear together.
- [ ] New key is tested independently.
- [ ] Old key is tested during the warning phase.
- [ ] When dropping the old key, the runtime model no longer binds it or has an explicit rejection policy.
- [ ] Secrets are never logged in warnings.

### Documentation/release

- [ ] Sample YAML uses the new key.
- [ ] Migration guide has before/after examples.
- [ ] Release notes state the deprecation version and planned removal version.
- [ ] Compatibility matrix across library versions is updated.
- [ ] Consumer test confirms the published artifact contains the right metadata.

## 12. Self-Check Questions

**Question 1.** Where must `@DeprecatedConfigurationProperty` be placed?  
**Answer:** On the getter of the old property in the `@ConfigurationProperties` class. You can mark the setter with `@Deprecated`, but the metadata annotation must be on the getter.

**Question 2.** Does this annotation change runtime binding?  
**Answer:** No. It only helps `spring-boot-configuration-processor` generate deprecation metadata. Getters/setters and migration code determine whether the old property is still bound/used.

**Question 3.** Why does the annotation generate the warning level?  
**Answer:** The annotation has no level attribute and is used while code still handles the old property; therefore auto-generated metadata assumes warning.

**Question 4.** When the old accessor has been deleted but you still want the IDE to show a replacement, what do you use?  
**Answer:** Add an entry in `META-INF/additional-spring-configuration-metadata.json` with deprecation level error, reason, replacement, and since.

**Question 5.** Should the replacement field record `endpoint` or `acme.client.endpoint`?  
**Answer:** Record the full property name `acme.client.endpoint`.

**Question 6.** Does adding `level=error` to JSON automatically throw an exception when an application declares the old key?  
**Answer:** No. Metadata serves tooling; if you want runtime to reject the old key, remove the accessor or implement separate checking/validation.

**Question 7.** If both old and new keys are declared, does Spring Boot automatically understand replacement and pick the new key?  
**Answer:** No. The library must define precedence in runtime code and test the case where both keys exist.

**Question 8.** If one old property is replaced by two new properties, can you just record one replacement and consider it sufficient?  
**Answer:** No. Describe the multi-key mapping in reason/migration guide and implement intentional conversion.

## 13. Official References

- [Spring Boot 3.3.13 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Spring Boot — Metadata Format](https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html)
- [Spring Boot — Generating Metadata with the Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html)
- [DeprecatedConfigurationProperty — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3.9/api/java/org/springframework/boot/context/properties/DeprecatedConfigurationProperty.html)

**Takeaway:** Deprecation metadata is structured guidance for users and IDEs. `@DeprecatedConfigurationProperty` is placed on the getter to generate warning metadata while the old key is still supported; additional metadata lets you keep error hints after the old accessor is removed. **Replacement does not automatically migrate runtime configuration**: the library must maintain aliases, define precedence, test compatibility, and publish a removal roadmap for the old key.
