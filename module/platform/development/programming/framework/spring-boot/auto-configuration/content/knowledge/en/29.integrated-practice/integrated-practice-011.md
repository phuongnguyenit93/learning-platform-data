# Building a Test Matrix and Contract Documentation to Finalize an Auto-Configuration Library

## 1. Goal: A Library Must Be Easy to Integrate, Verifiable, and Have a Clearly Committed Behavior

A complete Spring Boot auto-configuration library needs to do three things well:

1. **Auto-configure properly:** beans appear only when conditions match, required dependencies are present, properties are valid, and the application has not supplied a replacement implementation.
2. **Be testable:** every condition branch, configuration value, override path, classpath, and environment is verified by a purposeful test suite.
3. **Have a usage contract:** users know what the starter provides, which properties are supported, default values, activation conditions, which beans can be replaced, what errors occur, and which versions were tested.

Having unit tests for services alone is not enough. Auto-configuration also depends on the Environment, classpath, bean definitions, configuration order, web application type, and the consumer's dependency graph. A README with just a few installation lines is also insufficient if it fails to state default behavior and how applications customize it.

This lesson uses **Spring Boot 3.3.13, Spring Framework 6.1, and Java 17+**. The example builds a `catalog-spring-boot-autoconfigure` library, then tests it via ApplicationContextRunner, a consumer application, and packaged-artifact verification steps.

After this lesson, you can:

- Choose the right testing layer for each risk.
- Build a test matrix covering conditions, properties, bean overrides, classpath, web contexts, failures, and packaging.
- Use ApplicationContextRunner, FilteredClassLoader, WebApplicationContextRunner, and @SpringBootTest.
- Inspect the auto-configuration imports file and configuration metadata inside the JAR.
- Write contract documentation covering activation rules, properties, beans, override points, dependency requirements, failure behavior, and compatibility.
- Place checks in CI according to risk level and execution stage.
- Define completion criteria before releasing a starter.

## 2. What Does an Auto-Configuration Library Contract Include?

An auto-configuration library is not merely a collection of @Bean methods. When users add the dependency, they accept a behavioral contract. That contract should answer the following questions:

| Contract section | Questions users need answered |
| --- | --- |
| Activation | Which dependencies/classes/properties/profiles are required for auto-configuration to activate? |
| Defaults | If properties are omitted, what are the default values? |
| Conditions | When are beans created, and when are they skipped? |
| Bean API | Which bean types are provided? Which beans are extension points? |
| Override | Can users supply their own beans to replace defaults? |
| Configuration | Which properties are supported, and what are their types and constraints? |
| Dependencies | Which dependencies does the library pull in? Which dependencies are optional? |
| Startup | Do beans open network connections or read files during startup? |
| Errors | What errors occur—and when—if configuration is invalid or dependencies are unavailable? |
| Compatibility | Which Spring Boot, Java, and third-party library versions were tested? |
| Packaging | Does the JAR include auto-configuration imports and required metadata? |
| Migration | When properties, beans, or defaults change, what must users do? |

If a behavior can alter consumer outcomes when upgrading versions, that behavior must be documented clearly and guarded by tests.

### 2.1. Distinguishing implementation details from the public contract

Not every class in the autoconfigure package is part of the public API.

For example:

- CatalogClient is the interface applications are allowed to inject and replace.
- CatalogProperties is part of the public configuration API if users are encouraged to bind or import it directly.
- DefaultCatalogClient can be an implementation detail if the library does not commit to the concrete type.
- Users should not rely on internal bean names, helper conditions, or method order in source unless published in documentation.

Decide clearly which classes form the public API. Types published in the README, Javadoc, or consumer examples become anchor points users rely on across upgrades.

### 2.2. The contract includes inactive behavior as well

Users need to know:

- Does `enabled=false` disable the entire auto-configuration?
- If an optional dependency is absent, does the application continue running?
- If a user bean already exists, does the default bean back off?
- If a property is missing, is the feature enabled or disabled by default?
- If configuration is invalid, does the error happen during property binding, context refresh, or the first service call?

Inactive scenarios must also be tested. A good starter never fails application startup merely because an optional feature is unused.

## 3. Dividing Tests Into Layers with Distinct Purposes

Do not rely on one kind of test to prove everything. Each layer answers a specific set of questions.

| Layer | Tools | Goal | Relative duration |
| --- | --- | --- | --- |
| Unit tests | JUnit, AssertJ, Mockito when needed | Pure logic, mapping, retry policies, parsers, and validation helpers | Fast |
| Auto-configuration tests | ApplicationContextRunner | Conditions, property binding, bean creation, back-off, and failures | Fast |
| Environment/classpath tests | Runner + FilteredClassLoader | Optional dependencies, missing classes, differing property sources | Fast |
| Web-context tests | WebApplicationContextRunner, ReactiveWebApplicationContextRunner | Servlet/reactive conditions and web-specific beans | Fast to medium |
| Consumer integration tests | @SpringBootTest in a consumer app | Real artifact discovered, bound, and consumed | Medium |
| Packaging tests | Maven verify, JAR content inspection | Imports file, metadata, dependency scopes, and resources | Fast |
| Compatibility matrix | CI across multiple Boot/JDK/dependency versions | Verify published support ranges | Medium to long |
| End-to-end tests | Test environment with real services or containers | Protocol, authentication, timeouts, serialization, and network behavior | Long |
| Release verification | Consumer project using exact artifact version | Verify installation experience after publishing | Medium |

Spring Boot recommends ApplicationContextRunner to create an ApplicationContext with deterministic configuration for each combination of user beans, Environment, and classpath. The runner does not replace consumer application integration tests; it tests auto-configuration in isolation and quickly.

**Native note:** ApplicationContextRunner cannot run when the test suite itself is compiled into a native image. Run these tests on the JVM; native integration tests form a separate layer if the library claims native support.

## 4. Building a Test Matrix Before Writing Tests

A test matrix maps committed behaviors to inputs, expected outcomes, and test types. It exposes gaps before release.

### 4.1. Matrix by activation condition

| Group | Case | Expected result | Suitable test | Priority |
| --- | --- | --- | --- | --- |
| Feature property | Property absent | Published default applies | ApplicationContextRunner | P0 |
| Feature property | enabled=true | Default beans created | Runner | P0 |
| Feature property | enabled=false | Feature beans not created | Runner | P0 |
| Feature property | Wrong type/invalid value | Clear binding/validation failure or documented behavior | Runner | P0 |
| Classpath | Required dependency present | Related configuration applied | Runner | P0 |
| Classpath | Optional dependency missing | Dependent part skipped; context stays valid | FilteredClassLoader | P0 |
| Bean condition | No user bean | Default bean created | Runner | P0 |
| Bean condition | User bean of same type present | Default bean backs off | Runner | P0 |
| Bean condition | Multiple candidates present | @Primary/qualifier or clearly defined error | Runner | P1 |
| Resource condition | Resource present | Corresponding branch enabled | Runner | P1 |
| Resource condition | Resource missing | Branch skipped or startup fails per contract | Runner | P1 |
| Web condition | Servlet context | Only servlet beans created | Web runner | P1 |
| Web condition | Reactive context | Only reactive beans created | Reactive runner | P1 |
| Web condition | Non-web context | No web-specific beans created | Runner | P1 |
| Profile | Supported profile active | Behavior matches contract | Runner/consumer test | P1 |
| Ordering | Dependent auto-config loaded together | Bean definitions registered in right order | Runner | P1 |

### 4.2. Matrix by property and data

| Property group | Cases to test | What to assert |
| --- | --- | --- |
| Default | Key omitted | Default value is accurate |
| Override | Value supplied by application.properties | Binding is accurate |
| Environment | Environment variable or system property | Relaxed binding and precedence are accurate |
| Command line | --acme.catalog.timeout=750ms | Value overrides per Spring Boot rules |
| Duration | 750ms, 2s, unitless value | Conversion and units are accurate |
| Numeric | Minimum, maximum, out of range | Constraints are enforced |
| String | Empty, whitespace-only, special characters | Validation and escaping are accurate |
| Collection | Empty, single item, multiple items, invalid item | Binding and per-item validation |
| Nested object | Missing child field, valid object | Nested validation cascades when required |
| Deprecated key | Old key and new key present together | Precedence/migration clearly defined |
| Unknown key | Consumer misspells prefix or property | Metadata/docs help detect; do not promise Boot always rejects every unknown key |

Spring Boot supports multiple external configuration sources and a defined property source precedence order. Tests should use withPropertyValues for simple cases; cases involving real Environment behavior can use @SpringBootTest, @DynamicPropertySource, or appropriate property sources.

### 4.3. Matrix by bean contract

| Behavior | Test case | Assertion |
| --- | --- | --- |
| Default bean | No user implementation | Exactly one bean for the interface |
| User override | Bean of same type registered | Default bean is not created |
| Customization callback | Customizer provided | Customizers applied in published order |
| Multiple candidates | Two implementations | Clear injection resolution |
| Bean naming | User uses @Qualifier if supported | Names/qualifiers kept stable |
| Lazy/eager | Bean created per policy | Failures surface at expected time |
| Lifecycle | Context closes | Disposable resources closed if required by contract |
| Failure | Constructor/factory method throws exception | Error has actionable cause and message |

Do not assert a concrete implementation class if the documentation promises only an interface. Assert the public type, behavior, and override semantics.

### 4.4. Matrix by dependency and environment

| Axis | Combinations to consider |
| --- | --- |
| Spring Boot | Each minor line the library claims to support; at least lowest and highest versions |
| Java | Minimum supported JDK and published LTS versions |
| Third-party dependencies | Minimum version, recommended version, latest version in supported range |
| Optional module | Module present/absent; only features depending on it are affected |
| Application type | Non-web, Servlet, Reactive if supported by the library |
| Build tool | Maven/Gradle if the library provides instructions for both |
| Runtime | JVM; Native Image if the library declares support |
| Platform | OS/architecture relevant to native dependencies or file/network behavior |

There is no need to run the full Cartesian product of all axes. Pick high-risk combinations, boundary versions, and frequently conflicting dependency pairs. Explicitly document untested combinations.

## 5. End-to-End Example Library

We build a small auto-configuration for a Catalog client. Contract of the example:

- Feature enabled by default when the property is omitted.
- acme.catalog.enabled=false disables the auto-configuration.
- Default client is created only if the application has not provided a CatalogClient.
- Endpoint must not be blank.
- Default timeout is two seconds.
- Max attempts is between 1 and 10, defaulting to 3.
- The example client holds configuration; actual network calls can be implemented in a separate adapter.

### 5.1. Module structure

~~~text
catalog-parent/
├── pom.xml
├── catalog-spring-boot-autoconfigure/
│   ├── pom.xml
│   └── src/
│       ├── main/java/com/acme/catalog/autoconfigure/
│       │   ├── CatalogProperties.java
│       │   ├── CatalogClient.java
│       │   ├── DefaultCatalogClient.java
│       │   └── CatalogAutoConfiguration.java
│       ├── main/resources/META-INF/spring/
│       │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│       └── test/java/com/acme/catalog/autoconfigure/
│           └── CatalogAutoConfigurationTests.java
├── catalog-spring-boot-starter/
│   └── pom.xml
└── catalog-consumer/
    ├── pom.xml
    └── src/test/java/demo/consumer/
        └── CatalogStarterIntegrationTests.java
~~~

Separating autoconfigure and starter distinguishes configuration code from the dependency bundle. For a very small library with no optional features, both modules can be merged; when multiple optional integrations exist, splitting modules lets consumers select only what they need.

### 5.2. Properties class

File CatalogProperties.java:

~~~java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "acme.catalog")
@Validated
public class CatalogProperties {

    private boolean enabled = true;

    @NotBlank
    private String endpoint = "https://catalog.example.test";

    @NotNull
    private Duration timeout = Duration.ofSeconds(2);

    @Min(1)
    @Max(10)
    private int maxAttempts = 3;

    public boolean isEnabled() {
        return this.enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getEndpoint() {
        return this.endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return this.timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxAttempts() {
        return this.maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
~~~

@ConfigurationProperties groups related properties into a typed object. @Validated enables Bean Validation when properties are bound; @NotBlank, @NotNull, @Min, and @Max express constraints.

### 5.3. Public bean contract

File CatalogClient.java:

~~~java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

public interface CatalogClient {

    String endpoint();

    Duration timeout();

    int maxAttempts();
}
~~~

File DefaultCatalogClient.java:

~~~java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

public record DefaultCatalogClient(
        String endpoint,
        Duration timeout,
        int maxAttempts) implements CatalogClient {
}
~~~

In the public contract, applications inject CatalogClient. DefaultCatalogClient is the default implementation; if you do not want to support users depending on the concrete type, document it clearly as an implementation detail.

### 5.4. Auto-configuration

File CatalogAutoConfiguration.java:

~~~java
package com.acme.catalog.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "acme.catalog",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    public CatalogClient catalogClient(CatalogProperties properties) {
        return new DefaultCatalogClient(
            properties.getEndpoint(),
            properties.getTimeout(),
            properties.getMaxAttempts()
        );
    }
}
~~~

The class-level condition decides whether the feature applies. @ConditionalOnMissingBean on the method lets the application supply its own CatalogClient to replace the default.

Declare return types as specifically as possible when conditions depend on bean types. In this public contract, CatalogClient is the supported abstraction; there is no need to publish the bean name if users can inject by type.

### 5.5. Registering the auto-configuration

File src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports:

~~~text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
~~~

Spring Boot looks for the imports file inside the published JAR. Each line is the fully qualified name of an auto-configuration class. Auto-configurations should be registered via the imports file, live in their own package, and never be discovered by component scanning. Do not enable @ComponentScan on auto-configuration; use @Import for specific configurations when needed.

## 6. POM and Annotation Processors

An auto-configuration module typically needs spring-boot-autoconfigure, a validation implementation when using Jakarta constraints, a test starter, and annotation processors.

Example POM for catalog-spring-boot-autoconfigure:

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
    <artifactId>catalog-spring-boot-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                        </path>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-configuration-processor</artifactId>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The two processors serve two different purposes:

| Processor | Metadata file | Purpose |
| --- | --- | --- |
| spring-boot-autoconfigure-processor | META-INF/spring-autoconfigure-metadata.properties | Collects condition metadata so Spring Boot can quickly filter out non-matching auto-configurations |
| spring-boot-configuration-processor | META-INF/spring-configuration-metadata.json | Describes properties so IDEs support completion, types, defaults, and descriptions |

If using the Maven compiler plugin with annotationProcessorPaths, list all required processors there. With Lombok, configure annotation processor ordering per its guidelines so Lombok runs before the configuration processor.

### 6.1. Configuration metadata is part of the developer experience

Add Javadoc to every property. Spring Boot uses field descriptions to generate metadata; for records, record component descriptions should be written with Javadoc @param.

Example:

~~~java
/**
 * Configuration for the Acme catalog client.
 */
@ConfigurationProperties(prefix = "acme.catalog")
@Validated
public class CatalogProperties {

    /**
     * Whether to enable the Acme catalog integration.
     */
    private boolean enabled = true;

    /**
     * Base URL used by the catalog client.
     */
    @NotBlank
    private String endpoint = "https://catalog.example.test";

    /**
     * Timeout for a catalog request.
     */
    @NotNull
    private Duration timeout = Duration.ofSeconds(2);

    // Remaining fields and accessors...
}
~~~

Descriptions should explain meaning rather than repeating the property name or just saying "the value". For booleans, start with "Whether" or "Enable"; for Duration, clearly note the default unit if users might enter values without a suffix.

### 6.2. Additional metadata

When a property is not auto-detected, needs value hints, or requires extra descriptions, you can add:

File src/main/resources/META-INF/additional-spring-configuration-metadata.json:

~~~json
{
  "properties": [
    {
      "name": "acme.catalog.enabled",
      "type": "java.lang.Boolean",
      "description": "Whether to enable the Acme catalog integration.",
      "defaultValue": true
    }
  ],
  "hints": [
    {
      "name": "acme.catalog.mode",
      "values": [
        {
          "value": "sync",
          "description": "Use synchronous request processing."
        },
        {
          "value": "async",
          "description": "Use asynchronous request processing."
        }
      ]
    }
  ]
}
~~~

The processor automatically merges the additional file into spring-configuration-metadata.json. The additional file is optional; create it only when metadata cannot be inferred by the annotation processor.

## 7. Testing Auto-Configuration with ApplicationContextRunner

The runner lets you test each scenario with an isolated context. Each test should represent a meaningful combination of properties, user beans, and classpath.

### 7.1. Creating a shared runner

File CatalogAutoConfigurationTests.java:

~~~java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(CatalogAutoConfiguration.class)
            );

    @Test
    void createsDefaultClientWhenEnabledPropertyIsMissing() {
        this.contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(CatalogClient.class);

            CatalogClient client = context.getBean(CatalogClient.class);

            assertThat(client).isInstanceOf(DefaultCatalogClient.class);
            assertThat(client.endpoint())
                .isEqualTo("https://catalog.example.test");
            assertThat(client.timeout()).isEqualTo(Duration.ofSeconds(2));
            assertThat(client.maxAttempts()).isEqualTo(3);
        });
    }

    @Test
    void backsOffWhenFeatureIsDisabled() {
        this.contextRunner
            .withPropertyValues("acme.catalog.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(CatalogClient.class);
                assertThat(context).doesNotHaveBean(CatalogProperties.class);
            });
    }

    @Test
    void bindsCustomProperties() {
        this.contextRunner
            .withPropertyValues(
                "acme.catalog.enabled=true",
                "acme.catalog.endpoint=https://catalog.test",
                "acme.catalog.timeout=750ms",
                "acme.catalog.max-attempts=5"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();

                CatalogClient client = context.getBean(CatalogClient.class);

                assertThat(client.endpoint())
                    .isEqualTo("https://catalog.test");
                assertThat(client.timeout()).isEqualTo(Duration.ofMillis(750));
                assertThat(client.maxAttempts()).isEqualTo(5);
            });
    }

    @Test
    void backsOffWhenUserProvidesCatalogClient() {
        this.contextRunner
            .withUserConfiguration(UserCatalogConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(CatalogClient.class);

                CatalogClient client = context.getBean(CatalogClient.class);

                assertThat(client.endpoint())
                    .isEqualTo("https://custom.example.test");
            });
    }

    @Test
    void rejectsBlankEndpoint() {
        this.contextRunner
            .withPropertyValues("acme.catalog.endpoint= ")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .hasStackTraceContaining("must not be blank");
            });
    }

    @Test
    void rejectsMaxAttemptsOutsideSupportedRange() {
        this.contextRunner
            .withPropertyValues("acme.catalog.max-attempts=0")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .hasStackTraceContaining("must be greater than or equal to 1");
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {

        @Bean
        CatalogClient customCatalogClient() {
            return new DefaultCatalogClient(
                "https://custom.example.test",
                Duration.ofSeconds(1),
                1
            );
        }
    }
}
~~~

### 7.2. Why is each test important?

- **Default case:** confirms behavior when users only add the starter without declaring properties.
- **Disabled case:** confirms the feature actually turns off and the properties bean is not created unintentionally.
- **Binding case:** confirms relaxed binding, Duration conversion, and values passed to the bean.
- **Back-off case:** confirms applications can replace the default implementation.
- **Validation cases:** confirms errors are caught at startup instead of surfacing later when the client is used.

These tests make no real HTTP calls. They verify the auto-configuration contract and created objects. Protocol/network behavior belongs in separate integration tests.

### 7.3. Testing optional dependencies with FilteredClassLoader

If an integration works only when a third-party SDK is present, isolate that configuration:

~~~java
@AutoConfiguration
public class OptionalCatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
    static class VendorSdkConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient vendorCatalogClient(CatalogProperties properties) {
            return new VendorCatalogClient(
                new com.vendor.catalog.CatalogSdk(properties.getEndpoint())
            );
        }
    }
}
~~~

Placing @ConditionalOnClass on a nested configuration isolates code depending on the optional SDK. Do not place the condition solely on a @Bean method whose return type or signature references a class that might be absent, because the JVM may need to load that class before the method condition is evaluated.

Test classpath missing the SDK:

~~~java
@Test
void optionalIntegrationIsSkippedWhenVendorSdkIsMissing() {
    this.contextRunner
        .withConfiguration(
            AutoConfigurations.of(OptionalCatalogAutoConfiguration.class)
        )
        .withClassLoader(new FilteredClassLoader(CatalogSdk.class))
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(VendorCatalogClient.class);
        });
}
~~~

CatalogSdk.class in the test is supplied by a test dependency or test fixture. FilteredClassLoader simulates the class/package not existing when the real application runs.

If using a composed meta-annotation containing @ConditionalOnClass, pay attention to how `name` is declared per Spring Boot guidelines. For conditions on configuration classes, ASM can read annotation metadata without loading the optional class in the usual way.

### 7.4. Testing web-specific auto-configuration

If a library only creates servlet beans, use WebApplicationContextRunner. If it only creates reactive beans, use ReactiveWebApplicationContextRunner.

~~~java
private final WebApplicationContextRunner webRunner =
    new WebApplicationContextRunner()
        .withConfiguration(
            AutoConfigurations.of(CatalogWebAutoConfiguration.class)
        );
~~~

Servlet context test:

~~~java
@Test
void createsServletAdapterOnlyInServletContext() {
    this.webRunner.run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context).hasSingleBean(CatalogServletAdapter.class);
    });
}
~~~

If the same library supports both servlet and reactive, write separate tests for both contexts. Do not use a non-web ApplicationContextRunner to infer web application behavior.

### 7.5. Showing the condition report when tests are unclear

You can attach a listener to log ConditionEvaluationReport:

~~~java
new ApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(CatalogAutoConfiguration.class))
    .withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
    )
    .run(context -> {
        // Assertions for the selected condition branch.
    });
~~~

The condition report helps identify which conditions matched or did not match. When a test fails, also inspect the exception chain if the error occurred during bean creation or configuration binding.

## 8. Complete Test Matrix for the Catalog Library

From the behaviors above, the release matrix can be written as follows:

| ID | Scenario | Input/setup | Expected result | Level |
| --- | --- | --- | --- | --- |
| CAT-001 | Default activation | enabled omitted | Default client present | Runner |
| CAT-002 | Explicit enable | enabled=true | Default client present | Runner |
| CAT-003 | Explicit disable | enabled=false | No Catalog beans | Runner |
| CAT-004 | Property binding | Custom endpoint, timeout, attempts | Bean receives exact values | Runner |
| CAT-005 | Blank endpoint | Whitespace-only endpoint | Context fails validation | Runner |
| CAT-006 | Attempts too small | max-attempts=0 | Context fails validation | Runner |
| CAT-007 | Attempts too large | max-attempts=11 | Context fails validation | Runner |
| CAT-008 | User override | User registers CatalogClient | Default bean backs off | Runner |
| CAT-009 | Optional SDK present | SDK on classpath | SDK integration can be created | Runner |
| CAT-010 | Optional SDK missing | Filter SDK from classpath | Context does not fail; integration skipped | Runner |
| CAT-011 | Servlet mode | Servlet context | Servlet adapter present | Web runner |
| CAT-012 | Reactive mode | Reactive context | Reactive adapter present | Reactive runner |
| CAT-013 | Non-web mode | Generic context | No web adapter | Runner |
| CAT-014 | Custom property source | Properties from Environment/test override | Precedence values accurate | Runner/integration |
| CAT-015 | Configuration ordering | Loaded with dependent auto-config | Bean definitions registered in right order | Runner |
| CAT-016 | Context close | Close context | Disposable resources closed | Runner |
| CAT-017 | Imports discovery | Consumer depends only on JAR | Auto-configuration discovered | Consumer test |
| CAT-018 | Metadata packaging | Build JAR | Both required metadata files present | Packaging |
| CAT-019 | Dependency scopes | Inspect dependency tree | Optional SDK not pulled into wrong module | Build check |
| CAT-020 | Consumer override | Consumer declares own client | Override behavior matches contract | Consumer test |
| CAT-021 | Supported Boot/JDK | Each published combination | Compiles and tests pass | CI matrix |
| CAT-022 | Runtime failure | Fake transport returns error/timeout | Exception/retry behavior accurate | Integration |
| CAT-023 | Documentation example | Consumer sample follows README | Builds and tests pass | Docs verification |
| CAT-024 | Upgrade compatibility | Previous and new artifact versions | No undocumented contract changes | Compatibility |

### 8.1. P0, P1, and P2

Not every test needs to run on every pull request.

- **P0 — required before merge:** default activation, enabled/disabled, property binding/validation, user override, optional class missing, imports packaging, and consumer smoke test.
- **P1 — run on main CI or before release:** web contexts, ordering, resource cleanup, supported Boot/JDK matrix, dependency scopes, and configuration metadata.
- **P2 — nightly or release qualification:** multiple SDK versions, network integration, native targets, performance/startup, and migration tests.

Every row in the matrix should reference a test ID or concrete test path. If a scenario is dropped, document the reason instead of letting it vanish from the checklist.

### 8.2. Avoiding combinatorial test explosion

Suppose there are 8 properties, 3 profiles, 2 web modes, and 4 dependency versions. Testing every combination could create hundreds or thousands of tests.

Practical approach:

1. Test each property individually at default, boundary, and invalid values.
2. Test independent conditions with small tests.
3. Test selected important combinations that interact with each other.
4. Test user overrides in every major bean-creating branch.
5. Test optional dependencies in both present and absent states.
6. Pick boundary versions in the compatibility matrix.
7. Use consumer integration tests for end-to-end flows.

The goal is verifying risks and the contract, not generating every meaningless permutation.

## 9. Consumer Integration Test: Verifying the Exact Artifact Users Install

ApplicationContextRunner usually loads the auto-configuration class directly. It does not prove the imports file was packaged correctly or that the starter's dependency graph is complete.

An independent consumer project answers the more important question: **does an application adding only the starter dependency actually receive the behavior promised in documentation?**

### 9.1. Consumer POM

Example consumer depending on a starter already published or installed in the local Maven repository:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>catalog-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

The consumer neither imports CatalogAutoConfiguration directly nor component-scans the library package. Spring Boot must discover the auto-configuration on its own via the JAR imports file.

### 9.2. Consumer application properties

File src/test/resources/application.properties:

~~~properties
acme.catalog.enabled=true
acme.catalog.endpoint=https://consumer.example.test
acme.catalog.timeout=1s
acme.catalog.max-attempts=4
~~~

### 9.3. Consumer integration test

File CatalogStarterIntegrationTests.java:

~~~java
package demo.consumer;

import java.time.Duration;

import com.acme.catalog.autoconfigure.CatalogClient;
import com.acme.catalog.autoconfigure.DefaultCatalogClient;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class CatalogStarterIntegrationTests {

    @Autowired
    private CatalogClient catalogClient;

    @Test
    void starterDiscoversAndConfiguresCatalogClient() {
        assertThat(catalogClient)
            .isInstanceOf(DefaultCatalogClient.class);

        assertThat(catalogClient.endpoint())
            .isEqualTo("https://consumer.example.test");

        assertThat(catalogClient.timeout())
            .isEqualTo(Duration.ofSeconds(1));

        assertThat(catalogClient.maxAttempts())
            .isEqualTo(4);
    }
}
~~~

If the concrete class is not part of the public contract, consumer tests should assert behavior through CatalogClient rather than isInstanceOf(DefaultCatalogClient.class). In this example, the concrete type assertion merely illustrates the default implementation; release tests are more resilient when depending solely on the interface.

### 9.4. Running the consumer after packaging the library

If the consumer lives in the same Maven reactor, build the modules and related dependencies via the reactor. If the consumer is a standalone project, install/publish the library first and then run the consumer:

~~~bash
mvn -f catalog-spring-boot-autoconfigure/pom.xml clean install
mvn -f catalog-spring-boot-starter/pom.xml clean install
mvn -f catalog-consumer/pom.xml clean verify
~~~

This is a high-value pre-release check because it verifies dependency coordinates, transitive dependencies, and auto-configuration discovery from the packaged artifacts.

## 10. Inspecting JAR Contents and Metadata

Tests inside a module can pass while the published JAR lacks the imports file. Inspect the artifact itself.

Build:

~~~bash
mvn clean verify
~~~

List JAR contents:

~~~bash
jar tf target/catalog-spring-boot-autoconfigure-1.0.0.jar
~~~

Important files to look for:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
META-INF/spring-configuration-metadata.json
~~~

- The imports file must list the exact configuration classes.
- Auto-configuration metadata can be generated by spring-boot-autoconfigure-processor.
- Configuration metadata must describe the required properties, types, defaults, and descriptions.

If processors are not configured, one or more metadata files may not be generated. Treat this as a build configuration error if the library claims to provide IDE metadata or requires condition metadata.

### 10.1. Inspecting the dependency graph

Run:

~~~bash
mvn dependency:tree
~~~

Read the output to verify:

- spring-boot-autoconfigure has a compatibly managed version.
- Optional SDKs are not pulled in by the starter if that feature is genuinely optional.
- A validation provider is present when the contract relies on Bean Validation.
- Two incompatible versions of the same library are not pulled in.
- Test-only dependencies do not appear in the consumer's runtime graph.

The autoconfigure module should mark underlying library dependencies optional where appropriate so consumers can choose their own dependency set. The starter module supplies an intentional default dependency set. Do not bundle every optional integration into a single starter if doing so forces consumers to pull in unused libraries.

## 11. Writing Contract Documentation for Library Users

The README should enable a new developer to add the dependency, toggle the feature, configure properties, and replace the default bean without reading source code.

### 11.1. Suggested README outline

~~~markdown
# Acme Catalog Spring Boot Starter

## What it provides
- CatalogClient auto-configuration
- Default request timeout and retry settings
- Optional vendor transport integration

## Requirements
- Spring Boot: supported versions
- Java: supported versions
- Optional SDK: version range

## Installation
Maven and Gradle coordinates.

## Quick start
A minimal application.properties example and injection example.

## Auto-configuration behavior
- Activation conditions
- Default enabled/disabled behavior
- Optional classpath conditions
- User-defined bean back-off behavior

## Configuration properties
A complete property table with type, default, validation and description.

## Beans and customization
- Public bean types
- Custom implementation example
- Customizer/callback extension points
- Ordering and qualifier notes

## Startup and runtime behavior
- What is initialized at startup
- When network calls happen
- Timeout and retry behavior
- Resource cleanup

## Failure behavior
- Invalid configuration
- Missing optional dependency
- Remote service unavailable
- Actionable troubleshooting

## Compatibility
Spring Boot, Java, SDK and platform support matrix.

## Migration
Deprecated properties and behavior changes by version.

## Testing
How to run unit, auto-configuration and consumer tests.

## License and support
Support channels and issue reporting.
~~~

### 11.2. Property table must be informative

Example README section:

| Property | Type | Default | Validation | Behavior |
| --- | --- | --- | --- | --- |
| acme.catalog.enabled | boolean | true | Boolean | Disables all Catalog auto-configuration when false |
| acme.catalog.endpoint | String | https://catalog.example.test | Must not be blank | Base endpoint of the client |
| acme.catalog.timeout | Duration | 2s | Not null, must be positive per contract | Request timeout |
| acme.catalog.max-attempts | int | 3 | From 1 to 10 | Total attempts as defined by the library |

Do not write just "timeout in milliseconds" if the binder accepts duration suffixes. Document clearly what 750ms, 2s, and 1m mean and the default unit when users omit a suffix.

If a property takes effect only when an optional module is installed, note that clearly in the Behavior column or a dedicated note.

### 11.3. Publishing activation conditions

Example:

~~~markdown
Catalog auto-configuration is activated when:

1. acme.catalog.enabled is absent or true.
2. The Catalog auto-configuration module is present.
3. Any optional integration requiring a vendor SDK is activated only when that SDK is present.

The default CatalogClient backs off when the application provides its own
CatalogClient bean.
~~~

Describe matchIfMissing, class conditions, and bean back-off accurately. Avoid vague phrasing like "auto-configures automatically" without stating conditions.

### 11.4. Publishing beans and extension points

Example:

| Bean type | When created | How to override |
| --- | --- | --- |
| CatalogClient | Feature enabled and no user bean exists | Provide a @Bean CatalogClient |
| CatalogProperties | Auto-configuration is activated | Configure via property sources |
| CatalogMetricsBinder | Metrics dependency present and bean not replaced | Provide a custom implementation if supported by the API |

For each public bean, document its type, lifecycle, dependencies, qualifiers, and how to replace it if committed to by the library.

### 11.5. Publishing failure behavior

Users need to know where errors occur:

| Situation | Committed behavior | Action |
| --- | --- | --- |
| Blank endpoint | Startup fails due to validation | Provide a valid endpoint |
| Invalid timeout | Startup fails due to validation | Use a positive duration |
| Optional SDK missing | Optional integration not created | Add the SDK if that feature is needed |
| User provides CatalogClient | Default client backs off | Check bean type and qualifiers |
| Remote service unresponsive | Client reports error per timeout/retry contract | Check endpoint, credentials, and network |

If a service opens network connections during startup, document startup timeouts and failure policies clearly. If connections are established only on the first request, state that clearly so operators understand when failures may surface.

## 12. Compatibility Matrix and Versioning Rules

Do not claim "supports Spring Boot 3+" if CI tests only a single version. Document the tested version range.

Example support matrix:

| Component | Supported range (example) | Evidence to keep |
| --- | --- | --- |
| Spring Boot | 3.3.x | CI build/test on minimum and latest patches |
| Java | 17, 21 | JDK matrix |
| Catalog vendor SDK | 2.4.x | Dependency matrix and integration tests |
| Maven | 3.8+ | Maven wrapper or CI image |
| Servlet container | Only if a web adapter exists | Web-context integration test |
| GraalVM Native Image | Only when explicitly published | Native build/run on stated target |

This is an example presentation. Libraries must replace ranges with the combinations actually supported.

### 12.1. Distinguishing source, binary, and behavior compatibility

- **Source compatibility:** consumer source code still compiles.
- **Binary compatibility:** the new artifact remains compatible with previously compiled consumer bytecode.
- **Behavior compatibility:** the same properties and dependency set still produce the same beans, defaults, and side effects.

A change can preserve compilation yet still break behavior—for example, changing default enabled state, modifying conditions, or altering bean back-off. Therefore, compatibility reviews must include behavioral tests.

### 12.2. Changes to evaluate as breaking changes

- Removing or renaming a property.
- Changing the data type or unit of a property.
- Changing defaults so a feature turns on/off differently than before.
- Changing bean types or removing extension points.
- Changing @ConditionalOnMissingBean so user overrides stop working.
- Changing transitive dependencies or removing modules the starter previously provided.
- Changing exception/failure timing in ways consumers rely on.
- Narrowing supported Spring Boot/JDK/SDK ranges.

### 12.3. Deprecation and migration

When changing a property:

1. Publish both the new key and the old key.
2. Mark the old key deprecated in configuration metadata/Javadoc.
3. Document the version in which deprecation began.
4. Describe precedence if both keys are configured together.
5. Maintain compatibility for the announced deprecation window.
6. Add tests for the old key, the new key, and both present together.
7. Write a migration guide before removing the old key.

Do not delete a property simply because code moved to the new name. Users may still have many deployment configurations not yet updated.

## 13. Organizing CI Around the Development Lifecycle

A sensible pipeline can be split into four groups.

### 13.1. Pull request

Runs quickly to prevent common regressions:

- Compile and static checks.
- Unit tests.
- P0 ApplicationContextRunner matrix.
- Optional classpath tests.
- Metadata generation.
- JAR imports verification.
- Consumer smoke test with reactor dependencies.

### 13.2. Main branch

Expands coverage:

- Supported Java versions.
- Supported Spring Boot patch versions.
- Minimum/current SDK versions.
- Servlet/reactive contexts if present.
- Dependency tree checks.
- Consumer integration tests.

### 13.3. Nightly

Runs time-consuming checks:

- Full dependency compatibility combinations.
- Container-backed integration tests.
- Network failures, retries, timeouts, and recovery.
- Native Image tests if the library claims support.
- Startup/performance regressions if required by product goals.

### 13.4. Release candidate

Uses the exact candidate artifact:

1. Build JAR/starter.
2. Install or publish to a staging repository.
3. Create a consumer project depending solely on candidate coordinates.
4. Run quick-start and integration tests.
5. Inspect JAR contents, generated metadata, and dependency tree.
6. Verify README examples and migration guide.
7. Archive test reports, dependency versions, and checksums.
8. Release only when the support matrix and release notes match CI evidence.

Do not rely solely on a consumer project referencing source classes in the reactor as proof of packaging. A consumer using packaged artifacts can catch missing imports files or dependencies.

## 14. Documentation Examples Must Also Be Tested

A README containing uncompilable code wastes consumer time even when the library itself is sound.

Ways to keep docs synchronized:

- Place sample applications in a samples/ folder or catalog-consumer module.
- Run that exact sample in CI.
- Copy property examples into test fixtures when they represent the default contract.
- Verify version coordinates in docs match the release candidate.
- Every property in the doc table has at least one test for default or key behavior.
- Every extension point has an override test.
- Every optional feature has classpath present/missing tests.
- Migration guides have tests for old/new properties when behavior changes.

A minimal README example should be tested like a real consumer: add the starter, declare properties, inject the interface, and run the application context.

## 15. Common Pitfalls When Finalizing a Library

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Testing only service logic | Conditions and back-off can be wrong while tests pass | Add ApplicationContextRunner matrix |
| Testing only classes directly | Fails to check imports file in JAR | Add a consumer project using the artifact |
| Not testing missing properties | Default behavior is unprotected | Test missing property separately |
| Testing only enabled=true | Feature might fail to disable | Test false and default |
| Not testing user bean override | Starter might hijack application beans | Test @ConditionalOnMissingBean |
| Not testing optional class missing | Consumers not using the integration may fail startup | Use FilteredClassLoader |
| Testing only non-web context | Servlet/reactive conditions may be wrong | Use appropriate web context runners |
| Asserting only bean existence | Bean might receive wrong properties/defaults | Assert values and behavior |
| Not inspecting metadata | IDE gives no hints or displays wrong properties | Inspect generated JSON in JAR |
| Not checking dependency tree | Starter pulls unnecessary dependencies or wrong versions | Run mvn dependency:tree |
| README lacks a property table | Consumers must read source to learn configuration | Document type/default/validation/activation |
| Not documenting bean override contract | Users do not know how to swap implementations | Document interfaces and back-off behavior |
| Not publishing a support matrix | Users assume an overly broad support range | Document versions and CI evidence |
| Changing defaults without migration notes | Upgrading versions may alter production behavior | Treat default changes as contract changes |
| Using @ComponentScan in auto-configuration | May accidentally scan application packages | Register imports and use explicit @Import |
| Condition on method signature with optional class | JVM may load the type before method condition is checked | Isolate optional integration in nested configuration |
| Running ApplicationContextRunner in native tests | Runner does not support native images | Run runner on JVM; use separate native integration tests |
| Testing only source modules | Published JAR might lack metadata/resources | Package verification and consumer smoke tests |

## 16. Release Readiness Checklist

### Auto-configuration behavior

- [ ] Activation conditions are clearly described.
- [ ] Missing/default, true, and false property states are tested.
- [ ] Invalid and boundary property values are tested.
- [ ] Default beans have appropriate @ConditionalOnMissingBean.
- [ ] User-defined beans are tested.
- [ ] Optional dependencies have classpath-present and classpath-missing tests.
- [ ] Web contexts are tested if web-specific beans exist.
- [ ] Auto-configuration ordering has tests when ordering is part of behavior.

### Configuration metadata

- [ ] Property prefix belongs to the library's own namespace.
- [ ] Field Javadoc describes every property.
- [ ] Types/defaults/validation match README.
- [ ] spring-configuration-metadata.json is generated.
- [ ] Additional metadata is added only when needed.
- [ ] Deprecated properties have replacements and migration notes.

### Packaging and dependencies

- [ ] AutoConfiguration.imports is present in the JAR.
- [ ] spring-autoconfigure-metadata.properties is generated if the processor is configured.
- [ ] Optional dependencies have proper scopes/optional flags.
- [ ] Starter contains an intentional default dependency set.
- [ ] dependency:tree has no unintended conflicts.
- [ ] Consumer test uses packaged artifacts.

### Documentation and compatibility

- [ ] README has a runnable quick start.
- [ ] Property table includes type/default/validation/behavior.
- [ ] Bean types and override points are documented.
- [ ] Failure behavior and troubleshooting are clearly written.
- [ ] Spring Boot/JDK/SDK support matrix reflects CI.
- [ ] Breaking changes and deprecations have migration guides.
- [ ] Release notes reflect behavioral changes.

## 17. Self-Check Questions

**Question 1.** Why are unit tests for DefaultCatalogClient insufficient to finalize a starter?  
**Answer:** They do not test auto-configuration conditions, property binding, user bean back-off, classpath, imports discovery, or the consumer's dependency graph.

**Question 2.** Which kind of test is ApplicationContextRunner best suited for?  
**Answer:** Testing combinations of Environment, user configuration, classpath, and conditions in a fast, isolated context.

**Question 3.** When do you use FilteredClassLoader?  
**Answer:** When simulating a class or package absent from the runtime classpath, especially for optional dependencies.

**Question 4.** Why must consumer integration tests depend on packaged JARs?  
**Answer:** To confirm auto-configuration imports, resources, metadata, and transitive dependencies are present in the actual artifact users install.

**Question 5.** What metadata do spring-boot-autoconfigure-processor and spring-boot-configuration-processor generate?  
**Answer:** The first collects condition metadata; the second generates configuration metadata for properties and IDE assistance.

**Question 6.** Why test when enabled is omitted?  
**Answer:** Because matchIfMissing and default behavior are part of the contract; testing only true/false does not prove the default works properly.

**Question 7.** If the user supplies a CatalogClient, how should the default bean behave?  
**Answer:** If the contract allows overriding, @ConditionalOnMissingBean(CatalogClient.class) must make the default bean back off.

**Question 8.** Do you need to test every combination of properties, profiles, SDKs, and JDKs?  
**Answer:** No. Use single-axis tests, boundary cases, high-risk combinations, and a deliberate compatibility matrix.

**Question 9.** Can changing the default timeout from 2 seconds to 10 seconds be a breaking change?  
**Answer:** Yes. It changes consumer behavior and latency contracts even though source code still compiles.

**Question 10.** Why should README samples be run in CI?  
**Answer:** To ensure dependency coordinates, property names, bean injection, and examples continue working as documented.

**Question 11.** When do you use WebApplicationContextRunner?  
**Answer:** When auto-configuration depends on a Servlet web context. For Reactive contexts, use ReactiveWebApplicationContextRunner.

**Question 12.** When can you publish a supported version range?  
**Answer:** When representative versions across the range have been built/tested according to the compatibility matrix and untested limits are clearly documented.

## 18. Key Takeaways and Official References

- An auto-configuration contract covers activation conditions, defaults, properties, beans, override behavior, dependencies, failure behavior, and a support matrix.
- Use ApplicationContextRunner to test each Environment/user beans/classpath combination; use FilteredClassLoader to simulate missing optional dependencies.
- Use WebApplicationContextRunner or ReactiveWebApplicationContextRunner when behavior depends on web contexts.
- Consumer integration tests must use packaged artifacts to confirm imports discovery and dependency graphs.
- Inspect AutoConfiguration.imports, spring-autoconfigure-metadata.properties, and spring-configuration-metadata.json in the JAR.
- Use @ConfigurationProperties Javadoc and configuration metadata to improve IDE completion.
- The README needs a property table, bean override contract, failure behavior, compatibility, and migration guide.
- CI should have P0 for pull requests, compatibility tests for main/release, and a broader integration matrix for nightly.
- Changing defaults, properties, bean types, or activation conditions can be a behavior-breaking change even when source code still compiles.

Official Spring Boot 3.3.13 documentation:

1. [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html) — imports file, condition annotations, ApplicationContextRunner, FilteredClassLoader, starter modules, naming, and configuration key guidelines.
2. [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html) — property sources, precedence, binding, and configuration properties.
3. [Configuration Metadata: Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html) — generating metadata from @ConfigurationProperties and additional metadata.
4. [Configuration Metadata Format](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html) — groups, properties, hints, and ignored items.
5. [ApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html) — runner for auto-configuration tests.
6. [FilteredClassLoader Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html) — simulating missing classes/packages on the classpath.
7. [WebApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html) — testing Servlet web contexts.
8. [ReactiveWebApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ReactiveWebApplicationContextRunner.html) — testing Reactive web contexts.
9. [Spring Boot Auto-configuration Processor](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.custom-starter.autoconfigure-module) — condition metadata and annotation processor configuration.
