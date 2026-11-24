# Defining Library Capabilities, Activation Conditions, and Customization Contracts

## Learning Objectives

A Spring Boot library does more than provide a few Java classes. When publishing a starter, the author is designing **an integration contract with the consuming application**: which capabilities the library provides, under which conditions each capability is activated, how users configure it, and how they can replace or extend default beans.

If the contract is unclear, the application may pull in unnecessary dependencies, unintentionally enable features, encounter multiple beans of the same type, or not know how to change the default implementation. Conversely, a well-designed auto-configuration behaves predictably: it activates only when conditions are met, provides useful defaults, and yields control to the application when the user has configured their own.

After this lesson, you will be able to:

- Catalog library capabilities and distinguish core features from optional integrations.
- Define classpath, property, bean, resource, and web context conditions for each capability.
- Design namespaces, data types, and defaults into a stable configuration API.
- Specify how users replace beans, provide callbacks, or disable auto-configuration.
- Organize modules, starters, and `AutoConfiguration.imports` to avoid unnecessary dependencies.
- Write tests for activation branches, back-off, missing dependencies, and custom implementations.

## 1. Start with a Capability Catalog, Not with Annotations

Before writing `@AutoConfiguration`, answer the question: **what does the library actually provide to the application?**

Suppose a hypothetical `Acme` library provides a client for calling a remote service along with several optional integrations:

| Capability | Value delivered to the application | Required dependencies | Activation policy |
| --- | --- | --- | --- |
| Core client | `AcmeClient` to call the Acme API | Core API and HTTP client implementation | Enabled by general configuration, with clear defaults |
| HTTP web integration | Servlet endpoint/controller or adapter | Spring MVC/Servlet API | Only when the application is a servlet web app and the feature is enabled |
| Codec integration | Payload conversion using a third-party codec | Vendor SDK/codec | Only when the SDK is present and the feature is opted in |
| Metrics integration | Recording call counts and latency | Appropriate Micrometer API/registry | Only when the metrics API is present and required beans exist |
| Custom implementation | Application replaces the default client itself | Acme extension API | When the user registers a compatible bean |
| Configuration metadata | Configuration autocomplete/hints in the IDE | Configuration processor at build time | Generated as metadata when packaging the library |

This catalog helps identify what is **required**, **optional**, **replaceable**, and **meaningful only in a specific type of application**.

Do not create a single auto-configuration containing every feature if they have different dependencies or lifecycles. A library can have:
- Core auto-configuration: provides the core functionality.
- Web auto-configuration: only for servlet or reactive web.
- Vendor auto-configuration: only for a specific vendor SDK.
- Metrics auto-configuration: only for observability.

Each class should represent a group of capabilities that share activation conditions and dependencies.

## 2. Write an Activation Contract for Each Capability

A capability should only be enabled when its prerequisites hold. You can use the following matrix to review before implementation:

| Question | Common Spring Boot mechanism | Example |
| --- | --- | --- |
| Are the required APIs/classes on the runtime classpath? | `@ConditionalOnClass` / `@ConditionalOnMissingClass` | `com.vendor.codec.Codec` is present |
| Has the user enabled the feature? | `@ConditionalOnProperty` | `acme.codec.enabled=true` |
| Has a foundational bean already been registered? | `@ConditionalOnBean` | A `MeterRegistry` or vendor client exists |
| Has the user already provided a replacement bean? | `@ConditionalOnMissingBean` | No `AcmeClient` exists yet |
| Does the application have the right context type? | `@ConditionalOnWebApplication` | Servlet web application |
| Does a required resource exist? | `@ConditionalOnResource` | A schema or template file |
| Is there a single candidate to inject? | `@ConditionalOnSingleCandidate` | One `DataSource` or one primary bean |
| Can a specialized condition be expressed with SpEL? | `@ConditionalOnExpression` | Simple expression that does not reference beans |

These conditions answer different questions. Having the SDK on the classpath does not mean the SDK client bean has been created; enabling a property does not mean the application is a servlet web app; the presence of a bean does not mean a custom replacement bean is absent.

### 2.1. Classpath Conditions

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.Codec")
class AcmeCodecAutoConfiguration {
    // Beans dedicated to the codec integration only.
}
~~~

`@ConditionalOnClass` allows the configuration to be applied only when the class is found. Use `name` when you want to declare the class name as a string, especially for optional dependencies.

**Place the condition at the configuration class level** if a bean method signature uses types from an optional library. If the condition is placed only on the method, the JVM may have to resolve the return type or parameters before the method condition is evaluated. Spring Boot recommends isolating optional integrations in a separate configuration class with a class-level condition.

### 2.2. Property Conditions

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
class AcmeAutoConfiguration {
}
~~~

The snippet above clearly defines: if the user does not declare `acme.enabled`, the feature remains enabled; if declared, only the value `true` matches. For an optional integration, it is usually best to set `matchIfMissing=false` so users must explicitly opt in.

Keep in mind that `@ConditionalOnProperty` by default matches when the property **exists and differs from the string `false`**. Without `havingValue="true"`, values such as `off`, `no`, or `0` may still match. When a property is a boolean flag, write an explicit contract rather than relying on how readers interpret strings.

### 2.3. Bean Conditions

- `@ConditionalOnBean(MyClient.class)`: creates the integration only when the required bean already exists.
- `@ConditionalOnMissingBean(MyClient.class)`: provides a default only if the user has not registered a compatible bean.
- `@ConditionalOnSingleCandidate(MyClient.class)`: requires a single candidate or a primary candidate that can be selected.

Bean conditions are evaluated against bean definitions processed **up to that point**. Therefore, they work best in auto-configurations applied after user configurations. If you need to depend on a bean provided by another auto-configuration, declare the ordering with `after` or `afterName` and test both sides.

### 2.4. Web and Resource Conditions

~~~java
@AutoConfiguration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
class AcmeServletAutoConfiguration {
}
~~~

Web conditions prevent creating servlet beans in CLI or reactive applications. Similarly, `@ConditionalOnResource` can be used when a feature requires a schema or template to be present. Do not use a web condition as a substitute for a classpath condition: a servlet app may still lack an optional SDK.

## 3. Define Defaults and Opt-In/Opt-Out Policies

Each capability needs a policy when the user **does not declare the property**:

- **Default-on:** suited for core functionality that is safe and expected when the user adds the starter.
- **Default-off:** suited for optional integrations that incur overhead, make external connections, expose endpoints, or have operational impact.
- **Required configuration:** no default if a missing value prevents the application from running safely; fail fast with a clear message.

Example:

| Property | Default | Behavior |
| --- | --- | --- |
| `acme.enabled` | `true` | Enables the core client when the user adds the starter |
| `acme.timeout` | `3s` | Default request wait limit |
| `acme.codec.enabled` | `false` (opt-in) | Creates the codec integration only when enabled by the user |
| `acme.web.enabled` | `true` but requires a servlet context | Enables web integration in servlet apps |
| `acme.endpoint` | No real production environment endpoint | User must supply an appropriate endpoint if a default is unsafe |

These defaults are only examples for a hypothetical library. The author must choose based on business requirements, cost, security, and backward compatibility.

A feature flag and a classpath condition are often combined:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.Codec")
@ConditionalOnProperty(
        prefix = "acme.codec",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
class AcmeCodecAutoConfiguration {
}
~~~

Result:
- SDK absent: the configuration is not applied.
- SDK present but property missing: the integration is not enabled.
- SDK present and property is `true`: eligible to apply; additional bean conditions must still match.
- Property is `false`: not applied.

## 4. Design the Configuration API as Part of the Library Contract

Public keys should use a dedicated namespace owned by the library, such as `acme`. Do not add library keys into namespaces managed by Spring Boot such as `spring`, `server`, or `management`.

Example:

~~~yaml
acme:
  enabled: true
  endpoint: https://api.acme.example
  timeout: 3s
  codec:
    enabled: false
  web:
    enabled: true
~~~

Use `@ConfigurationProperties` to bind a group of keys into a typed object:

~~~java
@ConfigurationProperties(prefix = "acme")
public class AcmeProperties {

    /**
     * Endpoint used by the Acme client.
     */
    private URI endpoint = URI.create("https://api.acme.example");

    /**
     * Timeout for an Acme request.
     */
    private Duration timeout = Duration.ofSeconds(3);

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Choose types that reflect the actual semantics:
- `Duration` for timeouts and retry delays.
- `DataSize` for payload and buffer limits.
- `URI` for endpoints.
- `enum` for a closed set of choices.
- `boolean` for two-state toggle flags.
- `List<T>` or `Map<K,V>` for configuration sets that genuinely require collections.

Every public property should document its meaning, unit, valid range, and default. For a Java record, use record-level `@param` Javadoc tags to describe components. Do not cram multiple unrelated features under one prefix or into one monolithic properties class.

### 4.1. Metadata and IDE Hints

Add `spring-boot-configuration-processor` to `annotationProcessor` to generate `META-INF/spring-configuration-metadata.json`. This metadata enables IDEs to suggest keys, types, and descriptions.

Gradle example:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

In addition, `spring-boot-autoconfigure-processor` can generate auto-configuration condition metadata (`META-INF/spring-autoconfigure-metadata.properties`) so Boot can filter out non-matching configurations early. The two metadata files serve different purposes: one describes configuration properties for users/IDEs, while the other assists in filtering auto-configurations.

## 5. Define the Customization Contract: Replace or Extend?

A library should clearly state to what extent users can customize it. There are typically three options:

1. **Replace the entire bean:** the application registers an implementation of the public interface; auto-configuration uses `@ConditionalOnMissingBean` to back off.
2. **Adjust the default:** the application registers one or more callbacks/customizers that the library applies when building the default implementation.
3. **Configure via properties:** users change endpoints, timeouts, modes, or limits without writing a new bean.

Do not force users to replace the entire client just to change one minor attribute. Conversely, do not expose too many internal details through dozens of callbacks that make the API hard to maintain.

### 5.1. Bean Back-Off

~~~java
@Bean
@ConditionalOnMissingBean(AcmeClient.class)
DefaultAcmeClient acmeClient(AcmeProperties properties) {
    return new DefaultAcmeClient(
            properties.getEndpoint(),
            properties.getTimeout());
}
~~~

When the application already provides an `AcmeClient` bean, the default is not registered. Use a public interface as the contract so implementations can vary. Provide a sufficiently specific return type so Spring can infer the bean type; the condition can also explicitly declare the interface type it checks.

Avoid relying on bean-definition overriding to replace a bean with the same name. Type-based back-off expresses intent more clearly and does not force users to know internal bean names.

### 5.2. Callbacks/Customizers

If you want to keep the default implementation while allowing fine-tuning, provide a small interface:

~~~java
public interface AcmeClientCustomizer {
    void customize(AcmeClientBuilder builder);
}
~~~

Auto-configuration can accept `ObjectProvider<AcmeClientCustomizer>` and invoke them in order:

~~~java
@Bean
@ConditionalOnMissingBean(AcmeClient.class)
DefaultAcmeClient acmeClient(
        AcmeProperties properties,
        ObjectProvider<AcmeClientCustomizer> customizers) {

    AcmeClientBuilder builder = new AcmeClientBuilder(
            properties.getEndpoint(),
            properties.getTimeout());

    customizers.orderedStream()
            .forEach(customizer -> customizer.customize(builder));

    return builder.build();
}
~~~

The contract should specify:
- Whether customizers run before or after defaults are applied.
- In what order multiple customizers execute (`Ordered`/`@Order`).
- Whether overwriting the same attribute multiple times is allowed.
- Whether the callback only configures the object or may perform I/O.
- Whether an exception from a customizer fails startup or is handled separately.

Keep callbacks short and avoid network calls during bean configuration. Documentation must clearly state that customizers have no effect if the user has replaced the entire `AcmeClient`, unless the library intentionally designs a separate hook for custom implementations.

### 5.3. Bean Names, Qualifiers, and Multiple Implementations

If the library only provides one default, users typically inject by interface. If there are multiple implementations, publish clear qualifiers or selection rules. Do not treat internal bean names such as `acmeClient` as stable API unless the documentation commits to that name.

If an application registers multiple `AcmeClient` beans, single-type injection may become ambiguous; the user must choose `@Primary` or `@Qualifier`. Auto-configuration should not register an extra default bean when the application has already provided a suitable implementation.

## 6. Complete Core Auto-Configuration Example

The following example illustrates a default client, typed properties, and customizers. In real projects, API classes should reside in separate files in the library's public package.

~~~java
@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
@ConditionalOnProperty(
        prefix = "acme",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
@EnableConfigurationProperties(AcmeProperties.class)
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AcmeClient.class)
    DefaultAcmeClient acmeClient(
            AcmeProperties properties,
            ObjectProvider<AcmeClientCustomizer> customizers) {

        AcmeClientBuilder builder = new AcmeClientBuilder(
                properties.getEndpoint(),
                properties.getTimeout());

        customizers.orderedStream()
                .forEach(customizer -> customizer.customize(builder));

        return builder.build();
    }
}
~~~

This is an **illustrative configuration snippet**; appropriate annotations and types must be imported. `AcmeClient`, `DefaultAcmeClient`, `AcmeProperties`, `AcmeClientBuilder`, and `AcmeClientCustomizer` are APIs/implementations owned by the library.

The configuration above expresses a clear contract:
- The core API must be on the classpath.
- The feature is enabled by default, but users can disable it with `acme.enabled=false`.
- Properties are bound when the auto-configuration matches.
- The default client is created only when no user implementation exists.
- Customizers are applied in the defined order.

### 6.1. Optional Integration as a Separate Auto-Configuration

~~~java
@AutoConfiguration(
        afterName = "com.vendor.codec.autoconfigure.CodecAutoConfiguration")
@ConditionalOnClass(name = "com.vendor.codec.Codec")
@ConditionalOnProperty(
        prefix = "acme.codec",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
public class AcmeCodecAutoConfiguration {

    @Bean
    @ConditionalOnBean(type = "com.vendor.codec.Codec")
    @ConditionalOnMissingBean(AcmeCodec.class)
    DefaultAcmeCodec acmeCodec(com.vendor.codec.Codec codec) {
        return new DefaultAcmeCodec(codec);
    }
}
~~~

The snippet above only illustrates how to organize an optional integration. Because the method signature references a vendor type, the class-level `@ConditionalOnClass` protects the entire configuration when the SDK is absent. `afterName` only orders it after the vendor's auto-configuration if it is a selected candidate; it does not install the SDK or create the `Codec` bean itself. `@ConditionalOnBean` verifies that the client bean actually exists, while `@ConditionalOnMissingBean` lets the application replace the default adapter.

## 7. Packaging as an Autoconfigure Module and Starter

A common layout:

~~~text
acme-spring-boot-autoconfigure/
  AcmeAutoConfiguration.java
  AcmeProperties.java
  AcmeClientCustomizer.java
  META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports

acme-spring-boot-starter/
  build.gradle

acme-spring-boot-codec/
  AcmeCodecAutoConfiguration.java
  META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

- The `autoconfigure` module contains auto-configurations, configuration properties, and extension APIs.
- The starter provides a curated set of dependencies so applications can start using it easily.
- Optional integrations can be split into separate modules/starters when they have distinct dependencies, lifecycles, or versioning.

You do not have to create multiple modules if the library is simple. When there are no optional features and the dependency graph is stable, they can be combined. When there are multiple flavors, splitting modules lets users pull in only what they need.

### 7.1. Registering Auto-Configuration

In the JAR, the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example content:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

If an optional integration is a class published by another artifact, that artifact's imports file lists the corresponding class. Do not component-scan the auto-configuration package and do not hard-import all optional configurations from the core class. Use `@Import` deliberately for supporting configurations inside an already guarded branch.

### 7.2. Optional Dependencies

The core autoconfigure module should not pull every optional SDK into every application. You can:
- Split integrations into separate artifacts so the dependency graph includes them only when chosen by the user.
- Mark dependencies as optional in Maven metadata when you want users to decide whether to pull in that library.
- Use classpath conditions so optional configurations do not apply when the SDK is absent.

A condition does not replace dependency management. If the module's source code directly references the SDK, the module still needs the appropriate compile dependency; what matters is that a core-only application is not forced to receive unnecessary runtime SDKs.

### 7.3. Artifact and Starter Naming

Use your own brand namespace, such as `acme-spring-boot-autoconfigure`, `acme-spring-boot-starter`, and `acme-spring-boot-starter-codec`. Avoid starting your library module names with `spring-boot`, as that can cause confusion with official Spring Boot modules.

## 8. Ordering and Interaction with User Configuration

Auto-configuration is typically applied after user configurations. This is the foundation that allows `@ConditionalOnMissingBean` to yield to custom beans.

If depending on another auto-configuration:
~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
class AcmeJdbcAutoConfiguration {
}
~~~

Or when you do not want to reference the class directly:
~~~java
@AutoConfiguration(afterName = "com.vendor.autoconfigure.VendorAutoConfiguration")
class AcmeVendorBridgeAutoConfiguration {
}
~~~

Ordering affects only the order of **bean definition** processing. It does not guarantee bean constructor execution order. When one bean genuinely depends on another bean, declare the dependency via constructor/method parameters; use `@DependsOn` only for specific initialization relationships that the dependency graph cannot express.

Avoid using `@ConditionalOnBean` on a regular configuration parsed too early if the checked bean might not be processed yet. Bean conditions work best inside auto-configurations and with explicit ordering when needed.

## 9. Testing the Contract with ApplicationContextRunner

Auto-configuration is affected by classpath, properties, user-defined beans, and context type. Therefore, tests need to create small contexts for each important combination. `ApplicationContextRunner` is a suitable choice for non-web branches.

The example below is **a complete test file** covering defaults, property overrides, disabling, custom beans, and customizers. Nested classes in the test are only to keep the example in one file; in production implementations, move them to their respective files/packages.

**File:** `src/test/java/example/acme/AcmeAutoConfigurationContractTest.java`

~~~java
package example.acme;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationContractTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AcmeAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenFeaturePropertyIsMissing() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(AcmeClient.class);

            AcmeClient client = context.getBean(AcmeClient.class);
            assertThat(client.endpoint())
                    .isEqualTo(URI.create("https://api.acme.example"));
            assertThat(client.timeout()).isEqualTo(Duration.ofSeconds(3));
        });
    }

    @Test
    void bindsUserProvidedProperties() {
        runner.withPropertyValues(
                        "acme.endpoint=https://tenant.example",
                        "acme.timeout=1500ms")
                .run(context -> {
                    AcmeClient client = context.getBean(AcmeClient.class);
                    assertThat(client.endpoint())
                            .isEqualTo(URI.create("https://tenant.example"));
                    assertThat(client.timeout())
                            .isEqualTo(Duration.ofMillis(1500));
                });
    }

    @Test
    void explicitFalseDisablesTheCoreFeature() {
        runner.withPropertyValues("acme.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AcmeClient.class));
    }

    @Test
    void userImplementationReplacesTheDefault() {
        runner.withUserConfiguration(UserClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context.getBean(AcmeClient.class).endpoint())
                            .isEqualTo(URI.create("https://custom.example"));
                    assertThat(context.containsBean("acmeClient")).isFalse();
                });
    }

    @Test
    void orderedCustomizersChangeTheDefaultClient() {
        runner.withUserConfiguration(UserCustomizerConfiguration.class)
                .run(context -> {
                    AcmeClient client = context.getBean(AcmeClient.class);
                    assertThat(client.endpoint())
                            .isEqualTo(URI.create("https://customized.example"));
                    assertThat(client.timeout())
                            .isEqualTo(Duration.ofSeconds(8));
                });
    }

    interface AcmeClient {
        URI endpoint();
        Duration timeout();
    }

    record DefaultAcmeClient(URI endpoint, Duration timeout)
            implements AcmeClient {
    }

    static class AcmeClientBuilder {

        private URI endpoint;
        private Duration timeout;

        AcmeClientBuilder(URI endpoint, Duration timeout) {
            this.endpoint = endpoint;
            this.timeout = timeout;
        }

        void endpoint(URI endpoint) {
            this.endpoint = endpoint;
        }

        void timeout(Duration timeout) {
            this.timeout = timeout;
        }

        DefaultAcmeClient build() {
            return new DefaultAcmeClient(endpoint, timeout);
        }
    }

    interface AcmeClientCustomizer {
        void customize(AcmeClientBuilder builder);
    }

    @ConfigurationProperties(prefix = "acme")
    public static class AcmeProperties {

        private URI endpoint = URI.create("https://api.acme.example");
        private Duration timeout = Duration.ofSeconds(3);

        public URI getEndpoint() {
            return endpoint;
        }

        public void setEndpoint(URI endpoint) {
            this.endpoint = endpoint;
        }

        public Duration getTimeout() {
            return timeout;
        }

        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }
    }

    @AutoConfiguration
    @ConditionalOnClass(AcmeClient.class)
    @ConditionalOnProperty(
            prefix = "acme",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @EnableConfigurationProperties(AcmeProperties.class)
    static class AcmeAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(AcmeClient.class)
        DefaultAcmeClient acmeClient(
                AcmeProperties properties,
                ObjectProvider<AcmeClientCustomizer> customizers) {

            AcmeClientBuilder builder = new AcmeClientBuilder(
                    properties.getEndpoint(),
                    properties.getTimeout());

            customizers.orderedStream()
                    .forEach(customizer -> customizer.customize(builder));

            return builder.build();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        AcmeClient customAcmeClient() {
            return new DefaultAcmeClient(
                    URI.create("https://custom.example"),
                    Duration.ofSeconds(9));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCustomizerConfiguration {

        @Bean
        @Order(1)
        AcmeClientCustomizer endpointCustomizer() {
            return builder ->
                    builder.endpoint(URI.create("https://customized.example"));
        }

        @Bean
        @Order(2)
        AcmeClientCustomizer timeoutCustomizer() {
            return builder -> builder.timeout(Duration.ofSeconds(8));
        }
    }
}
~~~

### 9.1. Dependencies and Run Commands

Requires Java 17+ and Spring Boot 3.3.x. In a Gradle project that already has the Spring Boot plugin or BOM managing versions:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run in the module containing the test:

~~~bash
# Linux/macOS
./gradlew test --tests "example.acme.AcmeAutoConfigurationContractTest"

# Windows
gradlew.bat test --tests "example.acme.AcmeAutoConfigurationContractTest"
~~~

**Expected result:** five tests PASS:
- Missing property: default client is created with default endpoint and timeout.
- Property override: values are bound to the client.
- `acme.enabled=false`: default client is not registered.
- User bean: auto-configuration backs off.
- Customizer: default client is adjusted according to `@Order`.

The tests use AssertJ and have no `System.out.println`, so there is no fixed stdout output. Console output depends on Gradle/JUnit logging. The code is presented to run in a matching project; execute the command against a real dependency graph to verify the build.

### 9.2. Testing Optional Dependencies

For SDK-dependent integrations, add tests using `FilteredClassLoader`:

~~~java
runner.withClassLoader(new FilteredClassLoader(OptionalVendorClient.class))
        .run(context ->
                assertThat(context).doesNotHaveBean(OptionalVendorAdapter.class));
~~~

This is an **illustrative snippet** for testing an optional auto-configuration. It simulates a runtime classpath without the SDK class and confirms the adapter is not registered. If the feature is servlet/reactive, use `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner` to create the appropriate context type.

## 10. Diagnosing Why a Capability Was Not Activated

Enable debug mode when running the application:

~~~bash
java -jar app.jar --debug
~~~

The Condition Evaluation Report shows which auto-configurations matched or did not match. When investigating, check in order:

1. **Candidate:** Is the class listed in `AutoConfiguration.imports` of the published JAR?
2. **Classpath:** Does `@ConditionalOnClass` find all required APIs?
3. **Exclusion:** Did the application exclude the configuration via `spring.autoconfigure.exclude` or the `exclude` attribute?
4. **Property:** Does the key exist and match the expected `havingValue`/`matchIfMissing`?
5. **Bean:** Did `@ConditionalOnBean` find the foundational bean; was `@ConditionalOnMissingBean` blocked by a user bean?
6. **Context type:** Does the application have the expected servlet/reactive/non-web context?
7. **Bean creation:** Did the definition exist, but constructor/dependency/initialization failed?

Distinguish between a configuration **not selected**, **selected but condition did not match**, **bean definition not registered**, and **bean registered but initialization failed**. These are distinct stages.

Do not use `@ConditionalOnExpression` to reference a bean in SpEL just to check a capability; referencing a bean can cause it to initialize very early, before post-processing steps such as configuration properties binding. Prefer dedicated condition annotations or write a custom `Condition` if the logic is genuinely complex.

## 11. Common Mistakes When Designing a Library Contract

1. **Not cataloging capabilities.** Everything is lumped into one auto-configuration with unnecessary dependencies.
2. **Sharing one flag across multiple independent integrations.** A single `acme.enabled` key should not accidentally enable web, codec, and metrics if they have different policies.
3. **Enabling high-side-effect features by default.** Public endpoints, outbound telemetry, or service connections should be considered for explicit opt-in.
4. **Confusing classpath presence with bean presence.** Having the SDK on the classpath does not guarantee the client bean exists; use `@ConditionalOnBean` when a bean is actually required.
5. **Placing `@ConditionalOnClass` only on a method with optional types.** The JVM may resolve method signatures beforehand; split into a separate configuration class and guard at the class level.
6. **Omitting `@ConditionalOnMissingBean`.** Users define their own implementation, yet a second default is still registered, causing injection ambiguity.
7. **Placing bean conditions too early.** Results may depend on already processed bean definitions; use them in auto-configurations and declare ordering if needed.
8. **Configuration API without its own namespace.** Keys easily collide and depend on namespaces managed by Spring Boot.
9. **Inconsistent defaults.** Properties, conditions, and services use different defaults; missing-key tests catch this issue.
10. **No extension points.** Users are forced to replace the entire bean just to change one small attribute.
11. **Too many unordered customizers.** The final outcome depends on an undocumented order; define `Ordered` or `@Order` and test it.
12. **Internal bean names becoming an implicit contract.** Users rely on uncommitted names, turning refactoring into a breaking change.
13. **Starter pulling in every optional dependency.** Users who only need core still receive unnecessary SDK/web/metrics dependencies.
14. **Incorrect imports registration.** The class exists in the JAR but is missing from `AutoConfiguration.imports`, or the resource is overwritten during packaging.
15. **Component-scanning the auto-configuration package.** Configurations may be loaded outside the standard ordering/exclusion mechanism; publish them only through the imports file.
16. **Not testing negative branches.** Only testing the happy-path default while skipping false properties, missing classes, custom beans, and mismatched contexts.
17. **Not inspecting the published JAR.** The source tree looks right, but imports/metadata resources are not packaged as expected.
18. **Changing defaults or property names without migration.** This is a public API/behavior change that can break downstream applications.

## 12. Pre-Release Checklist for a Library or Starter

### Capabilities and Conditions

- [ ] Core and optional capabilities are listed.
- [ ] Each capability has its required dependencies and dedicated classpath condition.
- [ ] Activation properties have clear defaults and semantics.
- [ ] Bean conditions and ordering accurately reflect dependency provision order.
- [ ] Servlet/reactive/non-web features are restricted to the appropriate context.

### Configuration API

- [ ] Namespace is owned by the library.
- [ ] Java types accurately reflect property semantics.
- [ ] Every default is documented and tested.
- [ ] Each key has a description, unit, and valid value range.
- [ ] IDE metadata is generated and verified.

### Customization Contract

- [ ] Default beans have `@ConditionalOnMissingBean`.
- [ ] Public interfaces are stable and do not leak optional vendor details.
- [ ] Customizers exist when users need to adjust defaults.
- [ ] Customizer ordering is specified.
- [ ] Qualifiers/primary rules are documented when multiple implementations exist.
- [ ] How to disable or exclude auto-configuration is documented.

### Build and Testing

- [ ] `AutoConfiguration.imports` contains the exact classes.
- [ ] Optional dependencies are not pulled into core-only usage.
- [ ] Tests cover defaults, overrides, disabled state, missing classes, missing beans, and context types.
- [ ] Final artifact/JAR is tested, not only source files.
- [ ] Condition Evaluation Report is readable when conditions do not match.

## 13. Self-Check Questions

**Question 1.** The vendor SDK is on the classpath, but no client bean exists yet. Is `@ConditionalOnClass` sufficient to register the adapter?

**Answer:** No. A classpath condition only confirms the class exists; the adapter may also need `@ConditionalOnBean` to verify the client bean has been registered.

**Question 2.** The user declares their own `AcmeClient`. How do you prevent registering an extra default?

**Answer:** Use `@ConditionalOnMissingBean(AcmeClient.class)` on the default bean in the auto-configuration.

**Question 3.** Why should optional integrations have separate auto-configurations?

**Answer:** They may have different classpath, property, bean, and context conditions from core; separating classes protects optional types and reduces coupling.

**Question 4.** `acme.enabled` is missing and `matchIfMissing=true`. Does the condition match?

**Answer:** Yes, provided the other conditions also hold. If you want opt-in behavior, set `matchIfMissing=false`.

**Question 5.** An application wants to change the endpoint while still using the default client. Does it need to declare its own full `AcmeClient`?

**Answer:** No. Use `@ConfigurationProperties` to configure the endpoint; a customizer is an option when client creation behavior needs customization beyond properties.

## 14. Design Takeaways

A good auto-configuration contract must clearly state **what the library provides, what conditions cause each capability to appear, and how users can adjust or replace it**.

Start with a capability matrix, separate core from optional integrations, define a typed property namespace with clear defaults, guard default beans with `@ConditionalOnMissingBean`, and provide ordered customizers when needed. Register auto-configurations via `AutoConfiguration.imports`, keep optional dependencies off the core path whenever possible, and test every branch with `ApplicationContextRunner`.

When these decisions are captured as a contract, applications using the starter know exactly what happens when adding dependencies, enabling properties, missing an SDK, or providing their own beans. That is the foundation for evolving a library while preserving compatibility.

### Official Spring Boot Documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — @AutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3 — @ConditionalOnClass Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Spring Boot 3.3 — @ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
