# Documenting properties, extension points, replacement beans, and supported exclusions

## Learning objectives

A Spring Boot starter can start up immediately after adding a dependency, yet the developer experience is only genuinely good when users know clearly:

- Which properties are supported, their data types, default values, and validation rules.
- Which beans, interfaces, callbacks, or customizers they can use to customize the library.
- When default beans yield to application-provided beans.
- How they can exclude an entire auto-configuration or merely disable one specific feature.
- From which version those contracts are supported and how they change across upgrades.

Documenting these areas is part of API design. Property names, default values, bean types, extension interfaces, and FQCNs used in exclusions can all become contracts that applications depend on.

This lesson uses Spring Boot 3.3 and Java 17+ to establish a maintainable documentation practice: from `@ConfigurationProperties` and IDE metadata to customizers, `@ConditionalOnMissingBean`, exclusions, testing, and migration notes.

After this lesson, you will be able to:

- Design stable configuration property namespaces and groups.
- Generate configuration metadata so IDEs suggest keys, types, descriptions, values, and deprecations.
- Document properties in tables ready for use in READMEs/reference guides.
- Distinguish bean overrides, customizers, qualifiers, and auto-configuration exclusions.
- Clearly publish supported extension points and their boundaries.
- Explain ways to exclude auto-configuration at the application level or for a set of imports.
- Test binding, validation, default bean back-off, and exclusions.
- Manage changes to properties, bean contracts, and FQCNs across versions.

## 1. Four contract groups to publish

A Spring Boot integration library typically has four public contract groups:

| Group | What users need to know | Example |
| --- | --- | --- |
| Configuration properties | How to enable/disable and configure behavior | `acme.enabled`, `acme.connect-timeout` |
| Extension points | How to customize or replace implementations | `AcmeClient`, `AcmeClientCustomizer` |
| Default bean behavior | When the library creates beans and when it backs off for user beans | `@ConditionalOnMissingBean(AcmeClient.class)` |
| Supported exclusions | How to exclude one or more auto-configurations | `spring.autoconfigure.exclude`, `excludeName` |

These four groups are related but do not replace each other.

For example, setting `acme.enabled=false` can turn off only the Acme feature via a property condition. Excluding `AcmeAutoConfiguration` with `spring.autoconfigure.exclude` prevents the entire auto-configuration from participating. Providing an `AcmeClient` bean replaces only the default client implementation; other beans in the same auto-configuration may still be created.

Good documentation must describe the exact scope of impact of each mechanism.

## 2. Design configuration property namespaces

Use `@ConfigurationProperties` for structured configuration groups. Choose a dedicated namespace owned by the library, such as `acme`, `acme.client`, or `acme.codec`.

Do not place library properties under Spring Boot-owned namespaces such as `spring`, `server`, `management`, or another integration's namespace. Using a dedicated namespace reduces the risk of collisions when Spring Boot introduces new properties.

Configuration example:

~~~yaml
acme:
  enabled: true
  endpoint: https://api.acme.example
  connect-timeout: 3s
  read-timeout: 10s
  max-in-flight: 64
  codec:
    enabled: false
    mode: safe
~~~

Property names should use kebab-case:

- `acme.connect-timeout`
- `acme.max-in-flight`
- `acme.codec.enabled`

Spring Boot supports relaxed binding across compatible formats, but documentation should use canonical kebab-case as the standard form. Users will find it easier to search and match against metadata.

### 2.1. Choose data types that convey exact intent

| Meaning | Type to consider | Why |
| --- | --- | --- |
| Timeout duration | `java.time.Duration` | Allows writing `3s`, `500ms`, `2m` instead of unitless numbers |
| Data capacity | `org.springframework.util.unit.DataSize` | Allows writing `10MB`, `512KB` |
| Toggle on/off | `boolean` or `Boolean` | Distinguishes fixed defaults from unconfigured state if needed |
| URL/endpoint | `URI` | Represents addresses and schemes structurally |
| Retry counts | `int` or `Integer` | Easy to apply bounds and validation |
| Finite set of choices | `enum` | Restricts valid values and supports IDE metadata hints |
| Lists | `List<T>` or `Set<T>` | Expresses collections instead of manual string parsing |

Avoid `long timeout` without stating the unit. If a numeric type is unavoidable, state the unit explicitly in the property name or description. For new configurations, `Duration` is usually more readable.

### 2.2. Split property groups by responsibility

Do not create one giant class containing every starter key. You can split them:

~~~text
AcmeProperties
  enabled
  endpoint
  connectTimeout
  readTimeout

AcmeRetryProperties
  maxAttempts
  backoff

AcmeCodecProperties
  enabled
  mode
~~~

Property groups should reflect features that can be toggled or changed independently. If a group only exists when an optional dependency is present, place it in the corresponding integration/autoconfigure module.

## 3. Declare properties and default values

Example using a Java record, suitable for Java 17 and Spring Boot 3.3:

**File:** `src/main/java/com/acme/autoconfigure/AcmeProperties.java`

~~~java
package com.acme.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

@ConfigurationProperties(prefix = "acme")
@Validated
public record AcmeProperties(
        @DefaultValue("true")
        boolean enabled,

        @NotNull
        URI endpoint,

        @DefaultValue("3s")
        Duration connectTimeout,

        @DefaultValue("10s")
        Duration readTimeout,

        @DefaultValue("64")
        @Min(1)
        @Max(4096)
        int maxInFlight
) {
}
~~~

A record has a single canonical constructor, so Spring Boot can use constructor binding. `@DefaultValue` provides values when properties are omitted. `@Validated` enables validation on configuration properties; constraints such as `@NotNull`, `@Min`, and `@Max` help catch invalid configuration at startup.

If validation annotations are used, the module needs an appropriate validation dependency, typically `spring-boot-starter-validation` or a matching Jakarta Validation provider. Do not declare constraints and forget the runtime validator, as validation may then not execute as expected.

### 3.1. Register properties in auto-configuration

~~~java
package com.acme.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@AutoConfiguration
@EnableConfigurationProperties(AcmeProperties.class)
public class AcmeAutoConfiguration {
}
~~~

`@ConfigurationPropertiesScan` can be used in applications to locate application property classes. For auto-configuration libraries, `@EnableConfigurationProperties` clearly declares the exact property classes registered by the library.

### 3.2. Defaults in code and defaults in documentation must match

If a record uses `@DefaultValue("3s")`, documentation must not state `5s`. If a property has an environment-dependent or runtime-computed default, state "determined by..." and explain the rule.

Never list a default in the README that is missing from binding code. Metadata, runtime behavior, and documentation need one single source of truth.

## 4. Document every property

Each public property should include at minimum:

- Canonical name.
- Data type.
- Default value.
- Meaning and runtime impact.
- Constraints/validation.
- Valid example.
- Version introduced.
- Deprecation status and replacement property, if any.

Example reference table:

| Property | Type | Default | Description |
| --- | --- | --- | --- |
| `acme.enabled` | boolean | `true` | Enable or disable the Acme core bean group |
| `acme.endpoint` | URI | None; required | Acme service endpoint |
| `acme.connect-timeout` | Duration | `3s` | Maximum time to establish a connection |
| `acme.read-timeout` | Duration | `10s` | Maximum time to wait for response data |
| `acme.max-in-flight` | int | `64` | Maximum concurrent requests; from 1 to 4096 |
| `acme.codec.enabled` | boolean | `false` | Enable optional codec integration when the corresponding dependency is present |
| `acme.codec.mode` | enum | `safe` | Supported codec mode |

This table illustrates the Acme contract in this lesson; actual default values must stay synchronized with the library's property classes.

### 4.1. Write helpful descriptions

Good descriptions answer "what does this property change?" rather than repeating the key name.

Poor:

~~~text
acme.read-timeout: Read timeout.
~~~

Better:

~~~text
acme.read-timeout: Maximum time to wait for response data after a connection has been established. Values support ms, s, m, and h suffixes.
~~~

For booleans, descriptions should start with "Whether..." or "Enable...". For collections, clarify whether it is a list, whether order matters, and whether duplicates are supported. For Duration/DataSize, state the default unit if the format allows omitting suffixes.

### 4.2. Javadoc for properties metadata

Spring Boot recommends Javadoc on fields for JavaBean properties. For records, use class-level Javadoc with `@param` tags for each record component:

~~~java
/**
 * Configuration for the Acme client.
 *
 * @param enabled whether the Acme integration is enabled
 * @param endpoint service endpoint used by the client
 * @param connectTimeout maximum time allowed to establish a connection
 * @param readTimeout maximum time allowed to wait for a response
 * @param maxInFlight maximum number of concurrent requests
 */
@ConfigurationProperties(prefix = "acme")
public record AcmeProperties(
        boolean enabled,
        URI endpoint,
        Duration connectTimeout,
        Duration readTimeout,
        int maxInFlight
) {
}
~~~

The configuration metadata processor collects these descriptions and supplies them to IDEs. Keep descriptions plain text, concise, ending with a period, and avoid repeating the default value when metadata already represents the default separately.

## 5. Generate configuration metadata for IDEs

Spring Boot provides the `spring-boot-configuration-processor` annotation processor. It scans `@ConfigurationProperties` classes at compile time and generates:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Metadata helps IDEs:
- Autocomplete property names.
- Display data types.
- Display descriptions.
- Display default values.
- Suggest enum values or declared hints.
- Show deprecation warnings and replacements.

### 5.1. Gradle

In the module containing `@ConfigurationProperties`:

~~~kotlin
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

If using Kotlin, configure annotation processing to match the Kotlin build (such as KAPT/KSP per your toolchain and plugins). Do not assume Java `annotationProcessor` automatically processes Kotlin sources.

### 5.2. Maven

Declare the processor in the compiler annotation processor path according to the project's Maven Compiler Plugin setup. As a regular dependency, Spring Boot documentation recommends marking the configuration processor as optional in the POM so it does not become a required runtime dependency for consumers.

Example dependency declaration:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

With Maven Compiler Plugin, include the processor in `annotationProcessorPaths` if the project configures annotation processing explicitly. Use the version matching the project's Spring Boot BOM.

### 5.3. Inspect generated metadata

After building, inspect the file in output classes or the JAR:

~~~bash
jar tf build/libs/acme-spring-boot-autoconfigure-1.2.0.jar
~~~

Look for:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Read the JSON file and confirm:
- Namespace is accurate.
- Property names use canonical form.
- Types are accurate.
- Descriptions are non-empty.
- Default values match the code.
- Deprecated properties have accurate replacements.

Do not edit generated metadata files by hand. Fix source/Javadoc/annotations and rebuild.

## 6. Additional metadata for special cases

Some properties cannot be inferred automatically, such as keys read directly from `Environment` without binding to `@ConfigurationProperties`, or properties needing custom IDE hints.

You can add:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Example:

~~~json
{
  "properties": [
    {
      "name": "acme.codec.mode",
      "type": "java.lang.String",
      "description": "Codec mode used by the optional integration.",
      "defaultValue": "safe"
    }
  ],
  "hints": [
    {
      "name": "acme.codec.mode",
      "values": [
        {
          "value": "safe",
          "description": "Use the conservative codec behavior."
        },
        {
          "value": "fast",
          "description": "Prefer throughput when the payload is trusted."
        }
      ]
    }
  ]
}
~~~

Additional metadata is merged into the main metadata by the annotation processor. If a property was already auto-detected, details such as description, default, and deprecation can be supplemented or overridden by manual metadata.

Add this file only when it adds value. If all properties are already completely represented via `@ConfigurationProperties`, do not create an empty file.

## 7. Deprecate properties without surprising users

Property names may be stored in application.yml, Helm charts, environment variables, and deployment automation. Renaming a property is a contract change.

A common deprecation path:

1. Introduce the new property.
2. Keep the old property during a compatibility window.
3. Mark the old property deprecated and specify the replacement property.
4. If needed, handle the old property by forwarding it to the new value.
5. Announce the target removal version.
6. Remove it only after the published migration window.

For JavaBean properties, use `@DeprecatedConfigurationProperty` on the old property's getter to generate deprecation metadata:

~~~java
@ConfigurationProperties("acme")
public class AcmeProperties {

    private String endpointName;

    public String getEndpointName() {
        return this.endpointName;
    }

    public void setEndpointName(String endpointName) {
        this.endpointName = endpointName;
    }

    /**
     * @deprecated use {@code endpoint-name} instead.
     */
    @Deprecated
    @DeprecatedConfigurationProperty(
            replacement = "acme.endpoint-name",
            since = "2.1.0")
    public String getLegacyEndpoint() {
        return this.endpointName;
    }

    @Deprecated
    public void setLegacyEndpoint(String legacyEndpoint) {
        this.endpointName = legacyEndpoint;
    }
}
~~~

This is a JavaBean example illustrating deprecation metadata. The old getter still returns the forwarded value, so the old property continues to bind during the warning period.

In manual JSON metadata, deprecation can be described with:
- `level`: `warning` or `error`.
- `reason`: why it is deprecated.
- `replacement`: new property name.
- `since`: version when deprecation began.

`warning` level means the property is still handled/bound. `error` level means the property is no longer handled or bound. Choose the behavior matching your library's compatibility policy.

## 8. Publish supported extension points

Documentation must clearly distinguish three customization mechanisms:

1. **Replace an entire bean:** users provide their own implementation of a public interface.
2. **Customize the default implementation:** users supply one or more customizers invoked by the library.
3. **Select among multiple beans:** users use `@Primary`, `@Qualifier`, or collection injection when the library allows multiple implementations.

Not every internal bean is an extension point. Publish only the types, callbacks, and replacement points the library commits to supporting. If users override an undocumented internal bean, an implementation change in a later release could break their application.

### 8.1. Extension point via a public interface

Example API:

~~~java
package com.acme.api;

public interface AcmeClient {
    AcmeResponse send(AcmeRequest request);
}
~~~

The application can provide its own implementation:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomAcmeConfiguration {

    @Bean
    AcmeClient customAcmeClient() {
        return new MyAcmeClient();
    }
}
~~~

Auto-configuration provides the default bean:

~~~java
@AutoConfiguration
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AcmeClient.class)
    AcmeClient acmeClient(AcmeProperties properties) {
        return new DefaultAcmeClient(properties.endpoint());
    }
}
~~~

When the user's `AcmeClient` bean is registered before auto-configuration, `@ConditionalOnMissingBean` does not match and the default client is not created.

In a real library, provide rich enough type information in the bean method's return type so bean conditions can evaluate against the declared type. Where appropriate, use concrete return types if consistent with the public contract and without leaking unintended internals.

### 8.2. Extension point via customizers

If users only want to change a few options without rewriting the entire client, a customizer contract may fit better.

Sample API:

~~~java
package com.acme.api;

public interface AcmeClientCustomizer {
    void customize(AcmeClient.Builder builder);
}
~~~

Auto-configuration applies customizers in order:

~~~java
@Bean
@ConditionalOnMissingBean(AcmeClient.class)
AcmeClient acmeClient(
        AcmeProperties properties,
        ObjectProvider<AcmeClientCustomizer> customizers) {

    AcmeClient.Builder builder = AcmeClient.builder()
            .endpoint(properties.endpoint());

    customizers.orderedStream()
            .forEach(customizer -> customizer.customize(builder));

    return builder.build();
}
~~~

Users can register:

~~~java
@Bean
AcmeClientCustomizer addTenantHeader() {
    return builder -> builder.defaultHeader("X-Tenant", "billing");
}
~~~

Documentation must clarify:
- In what order customizers are invoked.
- Whether multiple customizers may be declared.
- Whether customizers apply only to the default client or to custom beans as well.
- Whether customizers are allowed to override endpoints/timeouts supplied by properties.
- If two customizers modify the same value, which one wins.

In the example above, customizers are invoked only when the default bean is created. If the user supplies a complete `AcmeClient`, the default factory does not run and customizers do not automatically modify the custom bean.

### 8.3. @Primary and @Qualifier do not replace back-off

If an application has two beans implementing `AcmeClient`, `@Primary` helps Spring pick a candidate during by-type injection. `@Qualifier` selects a specific bean.

However:
- `@Primary` does not prevent auto-configuration from creating the default bean.
- `@Qualifier` does not cause `@ConditionalOnMissingBean` to back off automatically.
- If the goal is to replace the default, provide an appropriate bean so the missing-bean condition does not match.
- If the goal is to retain multiple implementations and pick one, clearly document qualifiers or collection injection.

## 9. Bean replacement and condition ordering

### 9.1. Use @ConditionalOnMissingBean for default beans

This is the standard pattern for auto-configuration to yield control to the application:

~~~java
@Bean
@ConditionalOnMissingBean(AcmeClient.class)
AcmeClient acmeClient(AcmeProperties properties) {
    return new DefaultAcmeClient(properties.endpoint());
}
~~~

The condition is evaluated against bean definitions processed up to that point. Therefore, Spring Boot recommends placing `@ConditionalOnBean` and `@ConditionalOnMissingBean` in auto-configuration, which is processed after user-defined bean definitions.

Do not place these annotations on ordinary user configurations to guess which beans will appear later.

### 9.2. Distinguish bean replacement from disabling an entire auto-configuration

| Action | Result |
| --- | --- |
| User provides `AcmeClient` | Default AcmeClient backs off; other beans may still be created |
| User provides `AcmeClientCustomizer` | Customizer is applied if the default factory uses customizers |
| User uses `@Primary` | Selects preferred candidate on autowiring; default bean may still exist |
| User sets `acme.enabled=false` | Beans inside the property condition branch may not be created |
| User excludes `AcmeAutoConfiguration` | That entire configuration class is not applied |

Documentation must specify which properties disable only one feature and which exclusions remove an entire configuration.

### 9.3. Place conditions at the right scope

If an auto-configuration provides multiple independent beans, it is usually best to place `@ConditionalOnMissingBean` on each overridable bean method. If placed at the class level, the entire configuration class may be skipped when one condition fails to match.

Example:
- The user replaces `AcmeClient`, yet still wants `AcmeHealthIndicator`.
- The user replaces `AcmeConnectionPool`, yet still wants `AcmeMetricsBinder`.

Per-bean conditions keep customization narrowly scoped and predictable.

## 10. Supported ways to exclude auto-configuration

Spring Boot provides different mechanisms depending on scope:

| Mechanism | Scope | When to use |
| --- | --- | --- |
| `@SpringBootApplication(exclude = ...)` | One application, class reference | Application compiles with the class to exclude |
| `@EnableAutoConfiguration(exclude = ...)` | One application, class reference | Explicit auto-configuration setup |
| `excludeName = "..."` | One application, String FQCN | Want to avoid direct class reference |
| `spring.autoconfigure.exclude` | One application/environment | Configuration via YAML, properties, environment, or command line |
| `@ImportAutoConfiguration(exclude = ...)` | Explicitly imported auto-config set | Tests or configs selecting only a subset of candidates |

### 10.1. Exclude by class

~~~java
@SpringBootApplication(
        exclude = {
                AcmeAutoConfiguration.class,
                AcmeMetricsAutoConfiguration.class
        })
public class BillingApplication {
}
~~~

The `exclude` attribute can similarly be used on `@EnableAutoConfiguration`. Since these are class literals, the application must have the classes on the compile classpath.

### 10.2. Exclude by class name

~~~java
@SpringBootApplication(
        excludeName = {
                "com.acme.autoconfigure.AcmeAutoConfiguration",
                "com.acme.autoconfigure.AcmeMetricsAutoConfiguration"
        })
public class BillingApplication {
}
~~~

Use `excludeName` when storing FQCNs as Strings, such as in a module that does not want a direct dependency on the artifact containing the auto-configuration.

### 10.3. Exclude via spring.autoconfigure.exclude

In `application.yml`:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.acme.autoconfigure.AcmeAutoConfiguration
      - com.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

In `application.properties`:

~~~properties
spring.autoconfigure.exclude=com.acme.autoconfigure.AcmeAutoConfiguration,com.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

This property works well when exclusions vary by deployment environment. Document the exact FQCNs and remind users to check active profiles/property sources if an exclusion does not behave as expected.

### 10.4. Exclude in @ImportAutoConfiguration

`@ImportAutoConfiguration` lets you import a specific set of auto-configurations and exclude certain classes from that set:

~~~java
@ImportAutoConfiguration(
        classes = {
                AcmeAutoConfiguration.class,
                AcmeMetricsAutoConfiguration.class
        },
        exclude = AcmeMetricsAutoConfiguration.class)
class AcmeTestConfiguration {
}
~~~

This annotation is often useful in tests or when an explicit import set is desired. It applies ordering rules like `@EnableAutoConfiguration`, but restricts candidates to the specified classes instead of reading all ImportCandidates.

In Spring Boot 3.3, `@ImportAutoConfiguration`'s `exclude` attribute accepts class literals. Do not assume this annotation has an `excludeName` attribute like `@SpringBootApplication` or `@EnableAutoConfiguration`.

### 10.5. Exclusion is not the same as a feature toggle

Example:

~~~yaml
acme:
  codec:
    enabled: false
~~~

This property controls the codec feature. It does not necessarily exclude all of `AcmeAutoConfiguration`.

Conversely:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.acme.autoconfigure.AcmeAutoConfiguration
~~~

removes the auto-configuration class from processing. None of the beans provided by that class are registered through this branch.

If a library has multiple independent features, publish per-feature toggle properties instead of forcing users to exclude an entire auto-configuration just to disable one bean.

## 11. FQCNs and exclusions are contracts to manage

Auto-configuration names can appear in:
- `excludeName`.
- `spring.autoconfigure.exclude`.
- `beforeName` and `afterName` of other auto-configurations.
- Tests, sample apps, deployment configs, and documentation.

Therefore, renaming a package or class can affect consumers. Audit all references before renaming.

Spring Boot 3.4+ supports replacement metadata at:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Example:

~~~properties
com.acme.autoconfigure.AcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

The imports file lists only the new class. Replacement metadata helps handle old references in supported exclusions and before/after ordering. Spring Boot 3.3 does not read this replacement file, so 3.3 consumers must update FQCNs or the library must preserve old names within compatible release lines.

Do not describe replacement metadata as a general-purpose renaming mechanism for arbitrary Java strings. It does not rewrite reflection strings, direct class imports, bean names, or arbitrary property names.

## 12. Write a reference guide for starter users

A reference guide should provide easy-to-scan sections:

### 12.1. Quick start

Give a dependency declaration, minimal YAML, and an API injection example. Users must know whether the feature is enabled by default or requires opt-in.

### 12.2. Configuration properties

Provide one table per namespace containing key, type, default, description, constraints, and deprecation. Add realistic YAML examples.

### 12.3. Customization

List:
- Replaceable bean interfaces.
- Supported customizer/callback beans.
- Customizer invocation order.
- How multiple beans are handled.
- Default bean back-off behavior.
- Internal beans that are not public extension points.

### 12.4. Exclusions

State full auto-configuration FQCNs and supported exclusion methods. Clarify scope: whether excluding drops the whole class or toggles one feature.

### 12.5. Compatibility and migration

For each public contract change, record:
- Version introduced.
- Version deprecated.
- Replacement property or class.
- Last version supporting the old path.
- How to update the application.
- Differences across Spring Boot versions if metadata APIs change.

Never write only "improved configuration". Provide the old key, the new key, and before/after YAML examples.

## 13. Test documentation and auto-configuration behavior

Documentation is part of the contract, so examples and property tables should be tested alongside code.

### 13.1. Test default properties and custom bean back-off

**File:** `src/test/java/com/acme/autoconfigure/AcmeAutoConfigurationTests.java`

~~~java
package com.acme.autoconfigure;

import java.net.URI;
import java.time.Duration;

import com.acme.api.AcmeClient;
import com.acme.api.AcmeRequest;
import com.acme.api.AcmeResponse;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AcmeAutoConfiguration.class));

    @Test
    void bindsDocumentedDefaultsAndProperties() {
        this.runner
                .withPropertyValues(
                        "acme.endpoint=https://tenant.example",
                        "acme.connect-timeout=5s",
                        "acme.max-in-flight=128")
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeClient.class);

                    AcmeProperties properties =
                            context.getBean(AcmeProperties.class);

                    assertThat(properties.enabled()).isTrue();
                    assertThat(properties.endpoint())
                            .isEqualTo(URI.create("https://tenant.example"));
                    assertThat(properties.connectTimeout())
                            .isEqualTo(Duration.ofSeconds(5));
                    assertThat(properties.readTimeout())
                            .isEqualTo(Duration.ofSeconds(10));
                    assertThat(properties.maxInFlight()).isEqualTo(128);
                });
    }

    @Test
    void userClientReplacesDefaultClient() {
        this.runner
                .withPropertyValues("acme.endpoint=https://tenant.example")
                .withUserConfiguration(UserClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context.getBean(AcmeClient.class))
                            .isInstanceOf(CustomAcmeClient.class);
                });
    }

    @Test
    void invalidConcurrencyValueFailsValidation() {
        this.runner
                .withPropertyValues(
                        "acme.endpoint=https://tenant.example",
                        "acme.max-in-flight=0")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    jakarta.validation.ConstraintViolationException.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        AcmeClient customAcmeClient() {
            return new CustomAcmeClient();
        }
    }

    static class CustomAcmeClient implements AcmeClient {
        @Override
        public AcmeResponse send(AcmeRequest request) {
            throw new UnsupportedOperationException(
                    "Not exercised by this bean back-off test");
        }
    }
}
~~~

This is a test pattern for property contracts and bean back-off. Types `AcmeClient`, `AcmeProperties`, `AcmeAutoConfiguration`, and `DefaultAcmeClient` must be defined in the corresponding source module; tests do not invent default implementations themselves. Validation tests require a Jakarta Validation provider on the test runtime classpath.

### 13.2. Test property conditions and feature toggles

If codec is an optional feature, test its property condition separately:

~~~java
@Test
void codecFeatureCanBeDisabledWithoutExcludingCore() {
    runner.withPropertyValues(
            "acme.endpoint=https://tenant.example",
            "acme.codec.enabled=false")
            .run(context -> {
                assertThat(context).hasSingleBean(AcmeClient.class);
                assertThat(context).doesNotHaveBean(AcmeCodec.class);
            });
}
~~~

This test proves the feature toggle affects only the codec; the core client remains registered.

### 13.3. Test global exclusions properly via the auto-configuration selector

To verify `spring.autoconfigure.exclude`, write an integration test going through `@EnableAutoConfiguration` or `@SpringBootApplication`, so Boot actually reads candidate lists and exclusions. Do not rely solely on `AutoConfigurations.of(AcmeAutoConfiguration.class)`, because direct importing does not exercise the full selector/import metadata pipeline like a real Boot app.

Example test configuration:

~~~java
@SpringBootConfiguration(proxyBeanMethods = false)
@EnableAutoConfiguration
class ExclusionTestApplication {
}
~~~

The test can launch the context with property:

~~~properties
spring.autoconfigure.exclude=com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Then assert that beans provided by that auto-configuration do not appear. For `@ImportAutoConfiguration(exclude=...)`, create a dedicated test configuration using that annotation directly.

### 13.4. Verify metadata and examples in the JAR

After building:
- Confirm `META-INF/spring-configuration-metadata.json` is inside the JAR.
- Check property names, defaults, descriptions, and deprecations.
- Confirm `AutoConfiguration.imports` lists the exact candidates.
- Run a sample consumer that adds only the starter.
- If deprecations exist, compile/run tests with both old and new properties during the compatibility window.

## 14. Common documentation mistakes

1. **Omitting a dedicated namespace.** Properties can collide with Spring Boot or other libraries; use a starter-owned namespace.
2. **Using long for timeouts without units.** Choose Duration or document units clearly.
3. **Defaults in docs differ from defaults in code.** Synchronize @DefaultValue, field initializers, and metadata.
4. **Listing only property names.** Users need types, defaults, descriptions, constraints, and examples.
5. **Not generating configuration metadata.** IDEs lack completions/descriptions; add the configuration processor.
6. **Hand-editing generated metadata files.** Subsequent builds overwrite them; use Javadoc or additional metadata.
7. **Failing to mark old properties deprecated.** Users lack migration guidance; provide replacements and since versions.
8. **Treating every bean as an extension point.** Internal implementations are not public contracts; publish only supported interfaces/callbacks.
9. **Using @Primary to replace defaults.** Default beans may still exist; use @ConditionalOnMissingBean for back-off.
10. **Using @Qualifier to disable auto-configuration.** Qualifiers only pick candidates on injection; they do not exclude configurations.
11. **Placing ConditionalOnMissingBean on user configuration.** Conditions may run before expected bean definitions; prefer placing them in auto-configuration.
12. **Not documenting customizer ordering.** Multiple customizers can overwrite each other; define ordering rules and test them.
13. **Confusing feature toggles with exclusions.** Properties disable one feature; exclusions remove the entire auto-configuration class.
14. **Omitting auto-configuration FQCNs.** Consumers do not know which Strings to pass to excludeName/properties.
15. **Misusing excludeName on @ImportAutoConfiguration.** Spring Boot 3.3 @ImportAutoConfiguration has a Class-typed `exclude` attribute, not `excludeName`.
16. **Not testing the selector for spring.autoconfigure.exclude.** Directly importing auto-configurations does not verify the global exclusion pipeline.
17. **Renaming auto-configuration packages while forgetting exclusion references.** Audit YAML, source, ordering, and tests; use replacement metadata on Boot 3.4+ when appropriate.
18. **Not documenting Spring Boot version differences.** Newer metadata features may not be read by older versions; state compatibility ranges clearly.
19. **Docs showing only YAML without behavior.** State clearly which beans appear, which back off, and the property condition scope.
20. **Untested examples.** Use sample consumers and context tests so docs never describe imaginary behavior.

## 15. Pre-release starter checklist

### Configuration properties

- [ ] Namespace is owned by the library.
- [ ] Canonical names use kebab-case.
- [ ] Every key has a type, default, description, and constraints.
- [ ] Duration/DataSize are used where appropriate.
- [ ] Code defaults match documentation.
- [ ] Configuration processor is configured.
- [ ] Generated metadata is inspected inside the JAR.
- [ ] Additional metadata is used only for special cases.
- [ ] Deprecated properties have replacements and version milestones.

### Extension points and bean behavior

- [ ] Public replaceable APIs/interfaces are published.
- [ ] Supported customizers/callbacks are documented.
- [ ] Customizer ordering and application scope are clear.
- [ ] Default beans use @ConditionalOnMissingBean when overriding is allowed.
- [ ] @Primary, @Qualifier, and bean back-off are clearly distinguished.
- [ ] Internal beans are not mistakenly documented as extension points.

### Exclusions

- [ ] Public list of auto-configuration FQCNs is provided.
- [ ] Examples exist for class `exclude` and `excludeName`.
- [ ] Examples exist for `spring.autoconfigure.exclude`.
- [ ] Examples exist for `@ImportAutoConfiguration(exclude=...)` when needed.
- [ ] Feature properties are distinguished from full configuration exclusion.
- [ ] FQCNs were audited when renaming classes.
- [ ] Differences across Spring Boot versions are documented.

### Verification

- [ ] Default property binding tests pass.
- [ ] Validation failure tests pass.
- [ ] Custom bean back-off tests pass.
- [ ] Customizer ordering tests pass if applicable.
- [ ] Feature toggle tests pass.
- [ ] Global exclusion tests pass via `@EnableAutoConfiguration`.
- [ ] Targeted `@ImportAutoConfiguration` exclusion tests pass.
- [ ] Configuration metadata verified in artifact.
- [ ] Sample consumer runs against the published starter.

## 16. Self-check questions

**Question 1.** Why should a starter use its own namespace such as `acme`?

**Answer:** To avoid collisions with namespaces owned by Spring Boot or other libraries, while helping users clearly identify which library owns each property.

**Question 2.** Which metadata file helps IDEs suggest configuration properties?

**Answer:** `META-INF/spring-configuration-metadata.json`, typically generated by `spring-boot-configuration-processor`.

**Question 3.** What mechanism should be used so users can replace the default AcmeClient?

**Answer:** Publish the AcmeClient interface and guard the default bean with `@ConditionalOnMissingBean(AcmeClient.class)`. When the user provides a matching bean, the default backs off.

**Question 4.** Does @Primary prevent auto-configuration from creating the default bean?

**Answer:** No. @Primary only affects candidate selection during autowiring; to make the default bean back off, use a missing-bean condition.

**Question 5.** What is the difference between `acme.codec.enabled=false` and `spring.autoconfigure.exclude=...`?

**Answer:** A feature toggle property may disable only the codec; global exclusion drops the entire specified auto-configuration.

**Question 6.** In Spring Boot 3.3, which attribute does `@ImportAutoConfiguration` use to exclude classes?

**Answer:** The `exclude` attribute accepting class literals. Do not assume `excludeName` exists on this annotation.

**Question 7.** Why must tests for `spring.autoconfigure.exclude` go through `@EnableAutoConfiguration`?

**Answer:** To verify the selector reads the candidate list and global exclusions. Loading directly with `AutoConfigurations.of` does not test that full pipeline.

**Question 8.** When renaming a property, what must migration docs state?

**Answer:** Old key, new key, deprecated version, support window, forwarding behavior, and before/after YAML examples.

## 17. Takeaways

Starter documentation must clarify four contracts: supported properties, committed extension points, how default beans yield to user beans, and how to exclude auto-configuration. These contracts directly govern application configuration, source code, deployment, and upgradeability.

Use `@ConfigurationProperties` with a dedicated namespace, meaningful data types, clear defaults, and validation. Generate configuration metadata so IDEs provide completion and descriptions. Publish supported interfaces/customizers; use `@ConditionalOnMissingBean` so default beans back off; explain clearly that `@Primary` and `@Qualifier` only control autowiring.

Finally, list FQCNs and exclusion mechanisms: class literals, `excludeName`, `spring.autoconfigure.exclude`, and `@ImportAutoConfiguration(exclude=...)`. Test binding, overrides, feature toggles, and global exclusions through the proper selector. When public contracts change, publish migration paths alongside supported versions.

### Official Spring Boot 3.3 Documentation

- [Creating Your Own Auto-configuration — configuration keys, customization and testing](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Configuration Metadata — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Configuration Metadata Format — Spring Boot](https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html)
- [@ConfigurationProperties Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
- [@DeprecatedConfigurationProperty Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/DeprecatedConfigurationProperty.html)
- [@ConditionalOnMissingBean Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [@EnableAutoConfiguration Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html)
- [@ImportAutoConfiguration Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/ImportAutoConfiguration.html)
