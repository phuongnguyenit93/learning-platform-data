# Testing Configuration Beans with ApplicationContextRunner.withPropertyValues

## 1. Why Test Configuration as an Independent Component?

In Spring Boot, an application can run cleanly on a developer's machine yet fail to start in staging or production due to a missing property, wrong data type, misspelled environment variable name, or violated cross-field constraint.

Example:

~~~yaml
demo:
  delivery:
    endpoint: "https://delivery.example.invalid"
    timeout: 5s
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

This configuration looks simple, yet several bugs occur easily:

- Typing **demo.delivery.time-out** instead of the name used by the model.
- Writing **timeout: five-seconds**, which fails conversion to **Duration**.
- Leaving **endpoint** blank even though the client requires a URL.
- Passing **retry.max-attempts: 0**, violating the minimum-one-attempt rule.
- Forgetting to register **@ConfigurationProperties** so the bean is never created.
- Assuming a default inside a Java record is also added back into **Environment**.
- Testing only **application.yml** without testing overridden startup values.

You could use **@SpringBootTest**, but when the goal is just **one configuration bean** and its Environment values, booting the whole application creates unrelated beans and infrastructure, slowing down tests and obscuring failure causes.

Spring Boot Test's **ApplicationContextRunner** creates a **small, controlled ApplicationContext** populated with properties specified directly by the test:

~~~java
new ApplicationContextRunner()
    .withPropertyValues("demo.delivery.timeout=5s")
    .run(context -> {
        // Assert the bean and bound values
    });
~~~

This is an ideal practice for **configuration testing**, especially when writing **@ConfigurationProperties**, auto-configurations, or libraries that must support multiple property combinations.

This lesson uses **Spring Boot 3.3.x**, **Java 21**, JUnit 5, AssertJ, and standalone examples without calling real APIs. The domain **example.invalid** is for illustration only.

## 2. Learning Outcomes

After this lesson, you will be able to:

1. Explain how **ApplicationContextRunner** builds a test context.
2. Use **withPropertyValues("key=value", ...)** to supply and override test properties.
3. Register a configuration bean via **@EnableConfigurationProperties** in a test configuration.
4. Test **successful binding** into a **record** or JavaBean.
5. Verify **Duration**, URI, boolean, enum, and numeric types after conversion.
6. Test nested properties and collections such as **List** and **Map**.
7. Test **default values** and omitted-property scenarios.
8. Test **Bean Validation** with **@Validated**, **@NotBlank**, **@NotNull**, **@Min**, and **@Valid**.
9. Distinguish **missing bean**, **conversion/binding**, and **validation** failures.
10. Test conditional beans with **@ConditionalOnProperty**.
11. Keep test cases isolated without leaking state across runs.
12. Recognize the limits of ApplicationContextRunner compared to **@SpringBootTest** and full SpringApplication startup.

## 3. What Is ApplicationContextRunner?

**org.springframework.boot.test.context.runner.ApplicationContextRunner** is a test utility that creates a **standard non-web ApplicationContext**, letting you specify the exact configuration classes, beans, and Environment property values needed.

Minimal example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingConfigTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withPropertyValues("app.greeting=Hello");

    @Test
    void suppliesPropertyToEnvironment() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context.getEnvironment()
                    .getProperty("app.greeting"))
                    .isEqualTo("Hello");
        });
    }
}
~~~

Key points:

- **withPropertyValues(...)** adds properties to the Environment of the context created for the test run.
- **run(context -> { ... })** initializes the context and provides an **AssertableApplicationContext** for assertions.
- The context is **closed after the callback**, preventing singletons or resources from accumulating across runs.
- This is a **non-web context**; the test does not start embedded Tomcat, Jetty, or a REST server.
- **Application auto-configurations are not enabled by default**. You must register the configurations/auto-configurations your test requires.

A single ApplicationContextRunner can act as a **template** for many tests, each supplying a different property set without rebuilding the whole system's ApplicationContext.

### 3.1. Difference from ApplicationRunner

Easily confused names:

| Type | Purpose |
| --- | --- |
| **ApplicationContextRunner** | Utility in **spring-boot-test** that creates a small context for assertions |
| **ApplicationRunner** | Callback interface executed after the Spring Boot application context is prepared |
| **CommandLineRunner** | Callback interface receiving raw arguments after startup |
| **SpringApplication** | Orchestrates the entire Spring Boot startup lifecycle |
| **@SpringBootTest** | Supports integration tests with an application context via Spring Boot Test |

Do not use **ApplicationRunner** in place of **ApplicationContextRunner** in JUnit tests.

## 4. Dependencies and Project Structure

Gradle example:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**The version in the example is a release from the Spring Boot 3.3 line**, not a strict requirement to use those exact patch versions; in real projects, use the version managed/approved by your build system.

Maven example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

The Maven snippet assumes the project declares an appropriate Spring Boot parent/BOM or manages dependency versions elsewhere.

Important components:

- **spring-boot-starter-test** provides Spring Boot Test, JUnit 5, AssertJ, and common test utilities.
- **spring-boot-starter-validation** provides a Bean Validation implementation for **jakarta.validation** annotations.
- **ApplicationContextRunner** lives in **org.springframework.boot.test.context.runner**, not in core Spring Framework.
- Plain JUnit tests here do not need the **@SpringBootTest** annotation.

Directory tree:

~~~text
src/
├── main/
│   └── java/
│       └── com/example/delivery/
│           ├── DeliveryProperties.java
│           └── DeliveryClient.java
└── test/
    └── java/
        └── com/example/delivery/
            ├── DeliveryPropertiesTest.java
            ├── DeliveryDefaultsTest.java
            └── DeliveryFeatureConditionTest.java
~~~

The test files below are independent examples or additions to the same structure; you do not need to copy all of them if your exercise focuses on a single aspect.

## 5. Creating the @ConfigurationProperties Under Test

A configuration record for a delivery client:

~~~java
package com.example.delivery;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.delivery")
public record DeliveryProperties(
        @NotBlank String endpoint,
        @NotNull Duration timeout,
        @Valid @NotNull Retry retry) {

    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff) {
    }
}
~~~

**Endpoint** uses **String** here so emptiness/blankness can be checked with **@NotBlank**. For stricter typing, you can use **URI** and add scheme/host constraints. Do not assume a syntactically parseable URI automatically proves an endpoint is safe or reachable.

Canonical property names:

~~~text
demo.delivery.endpoint
demo.delivery.timeout
demo.delivery.retry.max-attempts
demo.delivery.retry.backoff
~~~

Illustrative YAML:

~~~yaml
demo:
  delivery:
    endpoint: "https://delivery.example.invalid"
    timeout: 5s
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

In tests using **withPropertyValues**, we supply these properties directly as **"key=value"** strings without creating temporary YAML files.

### 5.1. Why @Validated and @Valid?

- **@Validated** requests validation on the configuration properties type when the binding infrastructure is active.
- **@NotBlank** on endpoint requires non-whitespace content.
- **@NotNull** on timeout and retry requires those values to be present.
- **@Min(1)** on maxAttempts requires at least one attempt.
- **@Valid** on retry cascades validation into the nested record.

Spring Boot Binder converts properties into Java types. Jakarta Bean Validation checks constraints after binding. The two mechanisms are distinct.

### 5.2. Registering the Type in Production

The real application can use:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DeliveryApplication {
}
~~~

Or:

~~~java
@SpringBootApplication
@EnableConfigurationProperties(DeliveryProperties.class)
public class DeliveryApplication {
}
~~~

These two approaches are alternatives.

In **ApplicationContextRunner**, to keep test scope minimal, we typically use a **nested @Configuration** registering only the specific type via **@EnableConfigurationProperties**.

## 6. Writing the First Test with @EnableConfigurationProperties

This is the core example of the lesson and can serve as a template for subsequent tests.

~~~java
package com.example.delivery;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class TestConfiguration {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(TestConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        ValidationAutoConfiguration.class));

    @Test
    void bindsDeliveryProperties() {
        runner.withPropertyValues(
                "demo.delivery.endpoint=https://delivery.example.invalid",
                "demo.delivery.timeout=5s",
                "demo.delivery.retry.max-attempts=3",
                "demo.delivery.retry.backoff=250ms"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DeliveryProperties.class);

            DeliveryProperties properties =
                    context.getBean(DeliveryProperties.class);

            assertThat(properties.endpoint())
                    .isEqualTo("https://delivery.example.invalid");
            assertThat(properties.timeout())
                    .isEqualTo(Duration.ofSeconds(5));
            assertThat(properties.retry().maxAttempts())
                    .isEqualTo(3);
            assertThat(properties.retry().backoff())
                    .isEqualTo(Duration.ofMillis(250));
        });
    }
}
~~~

Detailed explanation:

1. **TestConfiguration** is a Spring **@Configuration** responsible for activating the type under test.
2. **@EnableConfigurationProperties(DeliveryProperties.class)** registers the configuration properties bean and required infrastructure.
3. **withUserConfiguration(TestConfiguration.class)** tells the runner to load that class.
4. **withConfiguration(AutoConfigurations.of(ValidationAutoConfiguration.class))** explicitly includes validation auto-configuration so the test clearly declares the infrastructure it uses. In an environment with a suitable Bean Validation implementation, this is a transparent way to test validation.
5. **withPropertyValues(...)** supplies four keys with test values.
6. **run(...)** creates the context, initializes beans, and executes assertions.
7. **hasSingleBean(...)** verifies the bean is registered cleanly with no duplicates of that type.
8. **Duration.ofSeconds(5)** and **Duration.ofMillis(250)** confirm Spring Boot converted the types rather than leaving strings.

**No @SpringBootTest is needed** on this class. That is the strength of ApplicationContextRunner: narrow scope that initializes only declared components.

### 6.1. Why Not Just Add @ConfigurationProperties and Call getBean?

**@ConfigurationProperties** alone does not guarantee a type becomes a bean in a minimal ApplicationContextRunner. You must register the type via **@EnableConfigurationProperties**, **@ConfigurationPropertiesScan** in a loaded configuration, or an equivalent mechanism.

The following is insufficient:

~~~java
new ApplicationContextRunner()
    .withPropertyValues("demo.delivery.timeout=5s")
    .run(context -> context.getBean(DeliveryProperties.class));
~~~

Without TestConfiguration or an appropriate registration, the context will not contain DeliveryProperties. **Having a property in Environment does not mean a configuration bean exists.**

## 7. How Does withPropertyValues Work?

Primary API:

~~~java
ApplicationContextRunner withPropertyValues(String... pairs)
~~~

In the example:

~~~java
runner.withPropertyValues(
        "demo.delivery.timeout=5s",
        "demo.delivery.retry.max-attempts=3"
);
~~~

**String... pairs** means one or more property pairs passed to the method. The syntax supports **=** and the API also supports **:** as a separator; in this curriculum, consistently use **=**.

Breakdown:

~~~text
demo.delivery.timeout=5s
|-------------------| |-|
       key           value
~~~

The method adds these values to the **Environment** of the context runner. It does not modify **application.yml**, does not set OS environment variables, and does not alter the machine's real Java system properties.

### 7.1. withPropertyValues Returns a Configured Runner

Suppose:

~~~java
ApplicationContextRunner base =
        new ApplicationContextRunner();

ApplicationContextRunner fiveSeconds =
        base.withPropertyValues(
                "demo.delivery.timeout=5s");

ApplicationContextRunner tenSeconds =
        base.withPropertyValues(
                "demo.delivery.timeout=10s");
~~~

Each runner is a separate configuration instance for building its own context. **withPropertyValues does not start the context immediately**; the context is only created when **run(...)** is called.

This makes writing multiple test scenarios very convenient.

### 7.2. withPropertyValues Can Override Keys Configured Earlier on the Runner

~~~java
ApplicationContextRunner base =
        new ApplicationContextRunner()
            .withPropertyValues(
                    "demo.delivery.timeout=5s");

base.withPropertyValues(
        "demo.delivery.timeout=10s"
).run(context -> {
    assertThat(context.getEnvironment()
            .getProperty("demo.delivery.timeout"))
            .isEqualTo("10s");
});
~~~

Property pairs supplied in a later runner call can override the same key declared earlier in the runner.

**Do not confuse this with full runtime precedence across CLI, env, profiles, and Config Data.** This is test setup for the runner-created Environment.

### 7.3. Each Run Creates a Fresh Context

~~~java
runner.withPropertyValues("app.mode=alpha")
        .run(context -> {
            assertThat(context.getEnvironment()
                    .getProperty("app.mode"))
                    .isEqualTo("alpha");
        });

runner.withPropertyValues("app.mode=beta")
        .run(context -> {
            assertThat(context.getEnvironment()
                    .getProperty("app.mode"))
                    .isEqualTo("beta");
        });
~~~

The two callbacks operate on two independent contexts. The value **alpha** from the first run does not leak into singleton bean state on the next run.

This is why ApplicationContextRunner suits testing many configuration combinations in sequence.

## 8. Testing Type Conversion: Strings to Duration, Numbers, and Booleans

In tests, pairs like:

~~~text
demo.delivery.timeout=5s
demo.delivery.retry.max-attempts=3
~~~

are **strings**, while the target type has:

~~~java
Duration timeout
int maxAttempts
~~~

Binder converts:

~~~text
"5s"  -> Duration.ofSeconds(5)
"3"   -> int 3
~~~

If you only assert:

~~~java
context.getEnvironment()
        .getProperty("demo.delivery.timeout")
~~~

you only know the key holds the string **5s**, not that binding into **Duration** works.

**Assertions should inspect the bean**, for example:

~~~java
DeliveryProperties p =
        context.getBean(DeliveryProperties.class);

assertThat(p.timeout())
        .isEqualTo(Duration.ofSeconds(5));
~~~

### 8.1. Other Supported Types

Spring Boot Binder also supports types such as:

- **Duration**: **500ms**, **5s**, **PT5S**.
- **DataSize**: **10MB**, **512KB**.
- **URI**: URL as a URI.
- **Boolean**: **true** or **false** via converter.
- **Integer/Long**: valid numeric values.
- **Enum**: one of the enum constants via conversion.
- **List/Map** and nested configuration objects.

Do not test only property names; verify the **final bound Java type** whenever conversion matters to business logic.

## 9. Testing Duration in Multiple Formats

A parameterized test or multiple test cases can verify the same Duration across different representations.

Example using the base runner from section 6:

~~~java
@Test
void understandsIsoDuration() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=PT5S",
            "demo.delivery.retry.max-attempts=2",
            "demo.delivery.retry.backoff=PT0.25S"
    ).run(context -> {
        assertThat(context).hasNotFailed();

        DeliveryProperties p =
                context.getBean(DeliveryProperties.class);

        assertThat(p.timeout())
                .isEqualTo(Duration.ofSeconds(5));
        assertThat(p.retry().backoff())
                .isEqualTo(Duration.ofMillis(250));
    });
}
~~~

Another example:

~~~java
@Test
void understandsMilliseconds() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=5000ms",
            "demo.delivery.retry.max-attempts=2",
            "demo.delivery.retry.backoff=100ms"
    ).run(context -> {
        assertThat(context).hasNotFailed();

        DeliveryProperties p =
                context.getBean(DeliveryProperties.class);

        assertThat(p.timeout())
                .isEqualTo(Duration.ofMillis(5000));
    });
}
~~~

When testing a bare number without a unit suffix:

~~~text
demo.delivery.timeout=5000
~~~

it is typically interpreted as **5000 milliseconds** under Spring Boot's default Duration configuration. If the field has **@DurationUnit(ChronoUnit.SECONDS)**, the meaning of a bare number changes.

**Do not test Duration configuration by comparing the string "5000" to the string "5s"**. Bind to Duration and compare Java values.

## 10. Testing Nested Properties

DeliveryProperties has a nested record:

~~~java
public record Retry(
        @Min(1) int maxAttempts,
        @NotNull Duration backoff) {
}
~~~

Canonical names:

~~~text
demo.delivery.retry.max-attempts
demo.delivery.retry.backoff
~~~

Test:

~~~java
@Test
void bindsNestedRetrySettings() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=3s",
            "demo.delivery.retry.max-attempts=5",
            "demo.delivery.retry.backoff=750ms"
    ).run(context -> {
        assertThat(context).hasNotFailed();

        DeliveryProperties p =
                context.getBean(DeliveryProperties.class);

        assertThat(p.retry()).isNotNull();
        assertThat(p.retry().maxAttempts()).isEqualTo(5);
        assertThat(p.retry().backoff())
                .isEqualTo(Duration.ofMillis(750));
    });
}
~~~

**@Valid @NotNull Retry retry** requires the nested object to exist and lets Bean Validation check constraints inside it.

If a test passes **demo.delivery.retry.max-attempts** while omitting **retry.backoff**, the nested record can be instantiated with backoff missing; validation with **@NotNull** should fail the context when validation is configured.

This is a valuable test because it proves **nested validation**, not only parent binding.

## 11. Checking Missing Properties

A common production failure is incomplete configuration. Tests should clearly express which fields are required.

Example omitting endpoint:

~~~java
@Test
void rejectsMissingEndpoint() {
    runner.withPropertyValues(
            "demo.delivery.timeout=5s",
            "demo.delivery.retry.max-attempts=3",
            "demo.delivery.retry.backoff=250ms"
    ).run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure()).isNotNull();
    });
}
~~~

**Key point:** Binder can instantiate the record with a null endpoint; Bean Validation sees **@NotBlank** is unsatisfied and context initialization reports the failure.

Avoid asserting exact full exception messages, since message details, exception wrapping, and formatting can vary across patch versions.

If you want to inspect the exact error class or property path, traverse the root cause intentionally in your test. However, simple tests should avoid depending on every line of a stack trace.

### 11.1. Missing Nested Field

~~~java
@Test
void rejectsMissingRetryBackoff() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=5s",
            "demo.delivery.retry.max-attempts=3"
    ).run(context -> {
        assertThat(context).hasFailed();
    });
}
~~~

Because **retry.backoff** has **@NotNull** and the parent declares **@Valid**, nested validation catches the missing value.

### 11.2. Missing Entire Nested Object

~~~java
@Test
void rejectsMissingRetryObject() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=5s"
    ).run(context -> {
        assertThat(context).hasFailed();
    });
}
~~~

**@NotNull Retry retry** expresses the contract that the entire retry branch must not be omitted.

Test both "entire branch missing" and "branch present with some fields missing" when configuration is critical.

## 12. Testing Type Conversion Errors

Validation is not the same as type conversion.

An invalid value:

~~~text
demo.delivery.timeout=not-a-duration
~~~

cannot convert to Duration. The error usually occurs during binding/conversion, before validation can inspect the full object.

Test:

~~~java
@Test
void rejectsInvalidDuration() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=not-a-duration",
            "demo.delivery.retry.max-attempts=3",
            "demo.delivery.retry.backoff=250ms"
    ).run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure())
                .isNotNull();
    });
}
~~~

A similar case is:

~~~text
demo.delivery.retry.max-attempts=three
~~~

When the target is int, Binder fails conversion.

**Distinguish three situations**:

| Situation | Error layer |
| --- | --- |
| Missing endpoint | Validation, @NotBlank |
| max-attempts equals 0 | Validation, @Min(1) |
| timeout equals "abc" | Conversion/binding |
| retry.backoff missing | Nested validation, @NotNull |
| Misspelled property leaving field unset | May surface as missing-field validation error |

A test failure should never be simplified to "context failed = validation worked." Keep separate tests for conversion and validation so you know the exact cause.

## 13. Testing Value Constraints

Example:

~~~text
demo.delivery.retry.max-attempts=0
~~~

The value **0** binds cleanly to int, yet violates **@Min(1)**.

~~~java
@Test
void rejectsZeroRetryAttempts() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=5s",
            "demo.delivery.retry.max-attempts=0",
            "demo.delivery.retry.backoff=250ms"
    ).run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure()).isNotNull();
    });
}
~~~

This test verifies a business constraint on a field whose type conversion already succeeded.

If no validation implementation is on the classpath, or **@Validated** is not applied as expected, this case may silently pass. Writing this test catches missing validation infrastructure.

### 13.1. Testing Cross-Field Relationships

Example business rule:

~~~text
connect-timeout < request-timeout
~~~

Two Durations may each be valid individually yet invalid together when **connect-timeout=8s** and **request-timeout=3s**. Checking this requires a custom class-level Bean Validation constraint or an appropriate **@AssertTrue** method on the model.

ApplicationContextRunner can supply both properties and assert context failure. The runner itself does not know business relationships; a validator must be defined on the bound class.

## 14. Testing Default Values

Spring Boot constructor binding supports **@DefaultValue**. Example of a dedicated type:

~~~java
package com.example.delivery;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "demo.worker")
public record WorkerProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("10s") Duration timeout,
        @DefaultValue("3") int maxAttempts) {
}
~~~

Test configuration:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class WorkerDefaultsTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class Config {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(Config.class);

    @Test
    void usesDeclaredDefaultsWhenOnePropertyProvided() {
        runner.withPropertyValues(
                "demo.worker.enabled=false"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            WorkerProperties p =
                    context.getBean(WorkerProperties.class);

            assertThat(p.enabled()).isFalse();
            assertThat(p.timeout())
                    .isEqualTo(java.time.Duration.ofSeconds(10));
            assertThat(p.maxAttempts()).isEqualTo(3);
        });
    }
}
~~~

The test supplies at least one property under prefix **demo.worker** while omitting **timeout** and **maxAttempts** to prove **@DefaultValue** works.

### 14.1. Java Defaults Are Not Automatically Environment Properties

In the test above, **WorkerProperties.timeout()** is **Duration.ofSeconds(10)** even though the test did not pass **demo.worker.timeout**.

However:

~~~java
context.getEnvironment()
        .getProperty("demo.worker.timeout")
~~~

does not necessarily return **10s**, because defaults declared on configuration objects are not written back into the Environment.

This matters when testing:

- **Bound beans** must be asserted via getters/record accessors.
- **Environment** reflects property sources, not Java object defaults.

### 14.2. JavaBean Defaults Differ from Constructor @DefaultValue

If a mutable JavaBean initializes:

~~~java
private Duration timeout = Duration.ofSeconds(10);
~~~

setter-based binding retains that default when no matching property exists. With record constructor binding, **@DefaultValue** is the explicit way to express defaults.

Do not mix both styles in the same class without understanding how the object is instantiated.

## 15. Testing Relaxed Binding

Spring Boot supports **relaxed binding** for **@ConfigurationProperties**. A camelCase Java name:

~~~java
Duration connectTimeout;
~~~

typically corresponds to the canonical key:

~~~text
demo.client.connect-timeout
~~~

A dedicated configuration record:

~~~java
package com.example.delivery;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.client")
public record ClientProperties(Duration connectTimeout) {
}
~~~

Test:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
static class ClientConfig {
}

@Test
void bindsCanonicalKebabCase() {
    new ApplicationContextRunner()
        .withUserConfiguration(ClientConfig.class)
        .withPropertyValues("demo.client.connect-timeout=5s")
        .run(context -> {
            assertThat(context.getBean(ClientProperties.class)
                    .connectTimeout())
                    .isEqualTo(Duration.ofSeconds(5));
        });
}
~~~

You can also test other Binder-supported formats in appropriate property sources, such as camelCase or underscores. However, **prefer canonical lowercase kebab-case keys in tests and documentation** to avoid inconsistent conventions.

### 15.1. Does This Test Real Environment Variables?

**withPropertyValues("DEMO_CLIENT_CONNECTTIMEOUT=5s")** does not replicate an OS environment variable named **DEMO_CLIENT_CONNECTTIMEOUT** identically. It passes a property string into a test PropertySource.

To test **mapping rules from a SystemEnvironmentPropertySource**, create an appropriate property source and attach it to the Environment, or run an integration test with real environment variables.

Do not pass an uppercase key to the runner and conclude Docker/Kubernetes env mapping will definitely work in every scenario.

## 16. Testing Lists and Maps via withPropertyValues

When configuration contains a List or Map, structured keys can be expressed with indexed notation.

Example type:

~~~java
package com.example.delivery;

import java.net.URI;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.routing")
public record RoutingProperties(
        List<Endpoint> endpoints,
        Map<String, Integer> limits) {

    public record Endpoint(String name, URI url) {
    }
}
~~~

Equivalent configuration:

~~~yaml
demo:
  routing:
    endpoints:
      - name: primary
        url: "https://primary.example.invalid"
      - name: backup
        url: "https://backup.example.invalid"
    limits:
      asia: 100
      europe: 150
~~~

Test:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RoutingProperties.class)
static class RoutingConfig {
}

@Test
void bindsListAndMap() {
    new ApplicationContextRunner()
        .withUserConfiguration(RoutingConfig.class)
        .withPropertyValues(
            "demo.routing.endpoints[0].name=primary",
            "demo.routing.endpoints[0].url=https://primary.example.invalid",
            "demo.routing.endpoints[1].name=backup",
            "demo.routing.endpoints[1].url=https://backup.example.invalid",
            "demo.routing.limits.asia=100",
            "demo.routing.limits.europe=150"
        )
        .run(context -> {
            assertThat(context).hasNotFailed();

            RoutingProperties p =
                    context.getBean(RoutingProperties.class);

            assertThat(p.endpoints()).hasSize(2);
            assertThat(p.endpoints().get(0).name())
                    .isEqualTo("primary");
            assertThat(p.endpoints().get(1).url())
                    .isEqualTo(java.net.URI.create(
                            "https://backup.example.invalid"));
            assertThat(p.limits().get("asia"))
                    .isEqualTo(100);
            assertThat(p.limits().get("europe"))
                    .isEqualTo(150);
        });
}
~~~

Key takeaways:

- **endpoints[0]** and **endpoints[1]** tell Binder the element order.
- **limits.asia** and **limits.europe** become Map entries.
- No real YAML file is required; for testing mapping, flattened keys are usually sufficient.

### 16.1. Limitation Around List Merging

In Spring Boot runtime, if the same List is declared across sources with different precedence, the higher-priority source **replaces the entire List** instead of merging element by element.

A runner with a single **withPropertyValues** source is great for testing List structure, but does not verify merging/replacement across **application.yml**, profile files, and OS env. To test multi-source precedence, construct tests with appropriate PropertySources or integration tests.

## 17. Testing Property-Conditional Beans

Beyond configuration beans themselves, many applications enable or disable features via properties:

~~~text
demo.feature.enabled=true
~~~

In auto-configuration, **@ConditionalOnProperty** is a common mechanism.

Example:

~~~java
package com.example.delivery;

public final class FeatureWorker {
}
~~~

Configuration:

~~~java
package com.example.delivery;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.feature",
            name = "enabled",
            havingValue = "true")
    public FeatureWorker featureWorker() {
        return new FeatureWorker();
    }
}
~~~

Test:

~~~java
package com.example.delivery;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureConditionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(FeatureConfiguration.class);

    @Test
    void createsBeanWhenEnabled() {
        runner.withPropertyValues(
                "demo.feature.enabled=true"
        ).run(context -> {
            assertThat(context).hasSingleBean(FeatureWorker.class);
        });
    }

    @Test
    void skipsBeanWhenDisabled() {
        runner.withPropertyValues(
                "demo.feature.enabled=false"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FeatureWorker.class);
        });
    }

    @Test
    void skipsBeanWhenPropertyMissing() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(FeatureWorker.class);
        });
    }
}
~~~

**Key point:** the runner is useful for both **binding** and **conditional bean registration**. It directly checks whether the ApplicationContext contains the bean, not just what value sits in Environment.

### 17.1. Default Behavior of @ConditionalOnProperty

When **matchIfMissing** is not enabled, an absent property fails the condition in the example above. If your use case requires enabled by default, declare **matchIfMissing=true** and write a corresponding test.

Do not confuse a default value inside a **@ConfigurationProperties** Java object with a **@ConditionalOnProperty** condition reading from Environment. An object-only default does not automatically appear as a key in Environment.

## 18. Not Every Test Needs @SpringBootTest

Comparing tools:

| Tool | Scope | When to use |
| --- | --- | --- |
| **ApplicationContextRunner** | Small test-specified context, non-web | Testing config beans, auto-configuration, conditional beans, conversion |
| **WebApplicationContextRunner** | Simulates a Servlet web application context | Auto-configurations active only in a Servlet context |
| **ReactiveWebApplicationContextRunner** | Simulates a reactive web context | Auto-configurations targeted at WebFlux/reactive |
| **@SpringBootTest** | Boots an application context via Spring Boot Test | Integration tests spanning many beans, profiles/Config Data, and real wiring |
| **Plain Java unit test** | No Spring context initialized | Testing pure validator or object logic |

**ApplicationContextRunner** is not intended to replace all end-to-end testing. It shines when a test can specify the exact beans and properties needed.

### 18.1. When Should You Use @SpringBootTest?

Use **@SpringBootTest** when you genuinely need to:

- Verify the real application's auto-configurations and component scan.
- Load Config Data/profile-specific files through the full SpringApplication lifecycle.
- Verify dependency wiring across multiple subsystems.
- Integrate Testcontainers, databases, or complex network mocks.
- Test a real web application with an actual server.

A small runner test does not prove all YAML files in the repository load properly during a production launch.

### 18.2. Native Image Tests

According to Spring Boot's documentation on testing auto-configuration, **ApplicationContextRunner does not work when running tests in a native image**. That does not mean application configuration properties cannot work in native applications; it is simply a documented limitation of this test utility.

When working with Spring AOT/native workflows, choose an appropriate testing strategy and do not assume the runner tests native image behavior.

## 19. Avoid Misunderstanding Config Data Sources with the Runner

A misleading example:

~~~java
new ApplicationContextRunner()
    .withPropertyValues("spring.profiles.active=prod")
    .run(context -> {
        // Do not assume application-prod.yml was definitely loaded
    });
~~~

Merely adding **spring.profiles.active=prod** to the Environment of a minimal test context **does not run the full Config Data bootstrap** of SpringApplication.

If a test truly needs to verify **application-prod.yml**, **spring.config.import**, or location precedence, use:

1. **@SpringBootTest** with the appropriate profile; or
2. A test harness that explicitly activates the Config Data infrastructure.

Do not take a bare ApplicationContextRunner and claim it fully models how Spring Boot resolves **application.yml** and profile files.

This is a critical boundary between **testing property binding** and **testing bootstrap configuration**.

### 19.1. withPropertyValues Also Does Not Create Real OS Env Vars

Calling:

~~~java
.withPropertyValues("demo.delivery.timeout=5s")
~~~

creates a property for the test context. It does not set **DEMO_DELIVERY_TIMEOUT** in the OS and does not alter the process launch command.

To test real environment variables or mounted secret files, use an appropriate integration test or launch environment.

## 20. Testing Overriding Sources in a Controlled Way

Suppose you want to verify a test can override a default:

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(Config.class)
            .withPropertyValues("demo.worker.timeout=10s");
~~~

A test:

~~~java
@Test
void overridesTimeoutForScenario() {
    runner.withPropertyValues(
            "demo.worker.timeout=3s"
    ).run(context -> {
        WorkerProperties p =
                context.getBean(WorkerProperties.class);

        assertThat(p.timeout())
                .isEqualTo(Duration.ofSeconds(3));
    });
}
~~~

This helps when many tests share baseline values, while each scenario overrides specific keys.

**Do not call System.setProperty(...) across parallel tests** just to pass a property to a runner; that creates JVM-wide shared state. **withPropertyValues(...)** is safer and cleanly scoped.

### 20.1. When to Use withSystemProperties?

ApplicationContextRunner provides **withSystemProperties(...)** to set Java system properties for the duration of the context run and restore them afterward.

Use it when the behavior under test genuinely depends on System properties and cannot be modeled adequately with a test property source.

Still, because System properties are JVM-global state, be careful with parallel test execution. For standard binding, **withPropertyValues** is the safer default.

## 21. Checking Specific Failures Without Brittle Tests

Configuration errors may be wrapped across multiple exceptions:

~~~text
Context startup failure
  -> bean creation / binding failure
     -> conversion failure or validation failure
~~~

If a test just needs to confirm the app fails fast on invalid configuration:

~~~java
runner.withPropertyValues(
        "demo.delivery.endpoint=https://delivery.example.invalid",
        "demo.delivery.timeout=bad",
        "demo.delivery.retry.max-attempts=3",
        "demo.delivery.retry.backoff=250ms"
).run(context -> {
    assertThat(context).hasFailed();
    assertThat(context.getStartupFailure()).isNotNull();
});
~~~

If the test must prove the failure belongs specifically to timeout, inspect the stack trace/cause chain at a reasonable level of detail. Avoid asserting on full message strings containing internal class names, file paths, or punctuation that Spring Boot may tweak across patch versions.

### 21.1. When a Failure Is Not Caused by Configuration

A context can fail for many reasons:

- Bean was never registered.
- Missing dependency for a business bean.
- Unmet auto-configuration condition.
- Validation implementation is absent.
- A ConstraintValidator threw an error.
- Property value has the wrong type.
- Circular dependency or bean definition conflict.

Therefore, if a test's job is proving **@Min(1)** works, do not accidentally let it fail because a datasource lacks a URL. Keep the context as small as possible and check the root cause when needed.

A well-designed test fails when configuration code is wrong, not when an external service happens to be unreachable.

## 22. Testing Mutable JavaBeans with Setters

Not every project uses records. For a mutable JavaBean configuration:

~~~java
package com.example.delivery;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.cache")
public class CacheProperties {

    private boolean enabled = true;
    private Duration ttl = Duration.ofMinutes(5);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getTtl() {
        return ttl;
    }

    public void setTtl(Duration ttl) {
        this.ttl = ttl;
    }
}
~~~

Test configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CacheProperties.class)
static class CacheConfig {
}
~~~

Test:

~~~java
@Test
void bindsJavaBeanAndRetainsDefault() {
    new ApplicationContextRunner()
        .withUserConfiguration(CacheConfig.class)
        .withPropertyValues("demo.cache.enabled=false")
        .run(context -> {
            assertThat(context).hasNotFailed();

            CacheProperties p = context.getBean(CacheProperties.class);

            assertThat(p.isEnabled()).isFalse();
            assertThat(p.getTtl())
                    .isEqualTo(Duration.ofMinutes(5));
        });
}
~~~

Here, ttl keeps its initialized JavaBean default. This differs from **@DefaultValue** on a record's constructor parameter.

The test also verifies **setter-based binding** works, not just constructor binding.

## 23. Testing Unknown Property Names and Binding Flags

In some situations, configuration contains a typo yet Binder does not fail if **@ConfigurationProperties** still allows unknown fields.

For example, the user supplies:

~~~text
demo.delivery.time-out=5s
~~~

whereas the target expects **timeout**.

With **@NotNull Duration timeout**, an error still occurs because timeout stays null. With an optional field that has a default, however, a wrong key can be ignored silently without an obvious failure.

Spring Boot provides options on **@ConfigurationProperties**, where **ignoreUnknownFields** defaults to true and **ignoreInvalidFields** defaults to false in the relevant Spring Boot line.

When designing a configuration API:

- Keep property names canonical and readable.
- Test that critical keys actually bind as expected.
- Use validation for required fields.
- Consider strict binding / unknown-field rejection if your module requires it; when changing that policy, test unknown keys explicitly.
- Do not assume every typo guarantees failure in every setup.

### 23.1. Checking Wrong Prefixes

Suppose the record has:

~~~java
@ConfigurationProperties(prefix = "demo.delivery")
~~~

but the test supplies only:

~~~text
demo.deliveries.endpoint=...
demo.deliveries.timeout=...
~~~

Those are two different prefixes. When no data exists under **demo.delivery**, the registered bean may still be created using the type's default/null semantics, and validation then decides pass/fail.

**Do not assume Binder treats delivery and deliveries as aliases.** Relaxed binding covers formatting variations per its rules, not singular/plural or semantic differences.

## 24. Testing Special Values: Zero, Negative, and Boundaries

A Duration can parse cleanly yet violate business rules:

~~~text
demo.delivery.timeout=0s
demo.delivery.timeout=-5s
~~~

**@NotNull** only checks presence; it does not forbid zero or negative durations.

If the contract requires a positive timeout, add an appropriate constraint, such as a custom Bean Validation constraint for Duration or a class-level validation method/validator.

Once that constraint exists, ApplicationContextRunner can test:

~~~text
timeout=1ms  -> pass if min=1ms
timeout=0s   -> fail
timeout=-1s  -> fail
timeout=24h  -> may fail if a max limit exists
~~~

Do not attach **@Min(1)** or **@Positive** onto Duration assuming every validation provider supports them. Standard numeric annotations do not necessarily ship validators for Duration.

Similarly for retry counts, test:

~~~text
max-attempts=1 -> pass
max-attempts=0 -> fail
max-attempts=3 -> pass
max-attempts=-1 -> fail
~~~

These boundaries provide far more test value than testing only a single "clean" configuration.

## 25. Using @AssertTrue for Cross-Field Relationships

Example of another configuration type:

~~~java
package com.example.delivery;

import java.time.Duration;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.timeout")
public record TimeoutRangeProperties(
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout) {

    @AssertTrue(message =
        "request-timeout must exceed connect-timeout")
    public boolean isTimeoutOrderValid() {
        if (connectTimeout == null || requestTimeout == null) {
            return true;
        }
        return requestTimeout.compareTo(connectTimeout) > 0;
    }
}
~~~

Test:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(TimeoutRangeProperties.class)
static class TimeoutConfig {
}

@Test
void rejectsInvalidTimeoutOrder() {
    new ApplicationContextRunner()
        .withUserConfiguration(TimeoutConfig.class)
        .withConfiguration(AutoConfigurations.of(
                ValidationAutoConfiguration.class))
        .withPropertyValues(
                "demo.timeout.connect-timeout=8s",
                "demo.timeout.request-timeout=3s")
        .run(context -> {
            assertThat(context).hasFailed();
        });
}
~~~

This is an **illustrative** business rule. Not every HTTP client requires request timeout to exceed connect timeout, since timeout semantics vary by library. Only add constraints that your system contract actually demands.

If violations need to point to a specific field rather than an inferred boolean property, write a custom **class-level Jakarta Bean Validation constraint**.

## 26. Organizing Multiple Tests Around a Base Runner

A common pattern:

~~~java
class PaymentConfigTests {

    private final ApplicationContextRunner baseRunner =
            new ApplicationContextRunner()
                .withUserConfiguration(PaymentTestConfig.class);

    @Test
    void scenarioA() {
        baseRunner.withPropertyValues(
                "demo.payment.enabled=true"
        ).run(context -> {
            // assertions specific to scenario A
        });
    }

    @Test
    void scenarioB() {
        baseRunner.withPropertyValues(
                "demo.payment.enabled=false"
        ).run(context -> {
            // assertions specific to scenario B
        });
    }
}
~~~

Meaning:

- **baseRunner** holds shared beans and configuration classes.
- Each test adds scenario-specific properties.
- Each **run(...)** creates a fresh context and closes it after the callback finishes.
- No global JVM System properties or Spring profiles need to be mutated.

**Pitfall to avoid:** inside a single test, do not pass multiple naming variants for the same property with conflicting values and rely on obscure precedence. Keep test inputs clear, with one intended final value per key.

### 26.1. Test Failures Must Belong to the Scenario Under Test

For instance, a missing-endpoint test must supply valid **timeout** and nested retry properties so the failure comes from the missing endpoint. If timeout and retry are also omitted, the context still fails, but no longer isolates @NotBlank on endpoint.

Purposeful tests are much easier to maintain and diagnose during refactoring.

## 27. Inspecting Auto-Configuration Conditions

In a module with many **@ConditionalOn...** annotations, a test may pass or fail because a condition did not match. Spring Boot provides **ConditionEvaluationReport** and logging utilities for auto-configuration tests to inspect condition outcomes.

You can use:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

Then:

~~~java
new ApplicationContextRunner()
    .withInitializer(
        ConditionEvaluationReportLoggingListener
            .forLogLevel(LogLevel.INFO))
    .withUserConfiguration(FeatureConfiguration.class)
    .withPropertyValues("demo.feature.enabled=true")
    .run(context -> {
        assertThat(context).hasSingleBean(FeatureWorker.class);
    });
~~~

The purpose is gaining extra diagnostic signals when a bean is missing. Do not enable report logging on every test; use it only when troubleshooting or verifying complex auto-configurations.

### 27.1. ConditionEvaluationReport Does Not Replace Assertions

Seeing "matched" or "did not match" in a report does not prove wiring is correct. Tests should still assert **bean presence**, **bound values**, and **context status**.

## 28. When Are End-to-End Tests Needed Outside the Runner?

A configuration bean may bind cleanly with test property values yet still fail in production because:

- **application-prod.yml** was not packaged or is not at the expected path.
- ConfigMap/Secret namespaces do not match env variable names.
- Secret files were not mounted into the container.
- **SPRING_CONFIG_IMPORT** or **spring.config.additional-location** was supplied too late.
- The active profile differs from the deployment profile.
- Source precedence lets an env var override a profile-specific value.
- A component only initializes when a web context exists.
- An auto-configuration depends on real dependencies or classpath entries.
- AOT/native mode exhibits different behavior.

In those cases, supplement with:

1. Integration tests using **@SpringBootTest** and the appropriate profile.
2. Smoke tests when deploying to a real environment.
3. Contract tests for platform-supplied configuration.
4. Security tests ensuring secrets do not leak via Actuator/logs.
5. Readiness probes and dependency connectivity checks.

**ApplicationContextRunner.withPropertyValues** excels at testing **binding logic**, not the delivery path from Secrets/ConfigMaps/CLI into the Java process.

## 29. Common Pitfalls

### 29.1. Forgetting withUserConfiguration or @EnableConfigurationProperties

The runner has properties, yet no target bean exists. Use **withUserConfiguration(TestConfiguration.class)** and **@EnableConfigurationProperties**.

### 29.2. Using @SpringBootTest Just to Test One Duration

The test initializes too many beans, runs slowly, and pulls in external dependencies. For a single configuration type, the runner is much leaner.

### 29.3. Calling withPropertyValues Without Calling run

**withPropertyValues** only configures the runner. You must call **run(context -> ...)** to build the context and run assertions.

### 29.4. Assuming withPropertyValues Edits application.yml

The method adds keys to the test Environment; it does not touch Config Data files on disk.

### 29.5. Assuming @Validated Works Without a Validation Provider

A Jakarta Bean Validation implementation and supporting infrastructure are required. Include starter-validation and write explicit failure tests.

### 29.6. Attributing hasFailed() to the Wrong Cause

The context might fail due to a missing unrelated bean or conversion error rather than the constraint under test. Keep the context minimal and populate all other required fields.

### 29.7. Testing Environment Instead of the Bound Bean

Reading **getProperty("demo.delivery.timeout")** only checks the string value in Environment; it does not prove Binder converted it to Duration.

### 29.8. Using Non-Canonical Keys

Stick to **demo.delivery.retry.max-attempts** rather than mixing camelCase and underscores arbitrarily.

### 29.9. Assuming an Active Profile in the Runner Loads Config Data

A minimal runner does not equate to full SpringApplication startup. To verify files and profiles, use an appropriate test.

### 29.10. Testing List Merging with a Single PropertySource

List merging/replacement across prioritized sources cannot be verified completely from a single withPropertyValues source.

### 29.11. Sharing Mutable State Across Tests

Avoid mutable static maps or uncleaned System.setProperty calls. Leverage immutable runners and independent contexts.

### 29.12. Failing to Close Manually Created Contexts

A key benefit of **run(...)** is closing the context after the callback. If you write another manual harness, manage resource lifecycles explicitly.

### 29.13. Matching Full Exception Messages Verbatim

Wrappers and messages can change between patch versions. Assert failures at a level stable enough for the test's purpose.

### 29.14. Forgetting Nested Validation Checks

A parent with @Validated will not necessarily cascade constraints into nested objects if **@Valid** is missing.

### 29.15. Treating Java Record Defaults as Environment Properties

Defaults inside objects are not written back into property sources. Assert them through bean accessors.

### 29.16. Leaking Secrets in Test Logs

Never print records containing passwords/apiKeys or dump the entire Environment. Use dummy tokens and log key names, never sensitive values.

## 30. Practice Exercises

### Exercise A — Successful Binding

1. Create **DeliveryProperties** as in section 5.
2. Create **TestConfiguration** with @EnableConfigurationProperties.
3. Create an **ApplicationContextRunner**.
4. Supply endpoint, timeout, and retry with **withPropertyValues**.
5. Assert hasSingleBean and that accessors return expected values.

**Goal:** prove binding occurs and types convert properly.

### Exercise B — Missing Property

1. Run a test omitting **demo.delivery.endpoint**.
2. Keep all other fields valid.
3. Assert the context fails validation.
4. Add endpoint back, rerun, and assert pass.

**Goal:** verify required-field contracts.

### Exercise C — Conversion Error

1. Change timeout to **nonsense**.
2. Run the runner.
3. Assert hasFailed.
4. Change it to **500ms**, rerun, and assert the Duration.

**Goal:** distinguish syntax errors from business constraints.

### Exercise D — Nested Validation

1. Set retry.max-attempts=0.
2. Run the context with all other fields valid.
3. Assert failure.
4. Set max-attempts=1 and verify it passes.

**Goal:** confirm @Valid cascades into nested types.

### Exercise E — Default Values

1. Create WorkerProperties with **@DefaultValue("10s")**.
2. Supply only **demo.worker.enabled=false**.
3. Assert timeout equals Duration.ofSeconds(10).
4. Compare with Environment.getProperty("demo.worker.timeout").

**Goal:** understand how object defaults differ from Env sources.

### Exercise F — Lists and Maps

1. Create RoutingProperties.
2. Supply endpoints[0], endpoints[1], and limits.asia/europe.
3. Assert size, ordering, and map entries.
4. Try omitting an element field if validated and observe failure.

**Goal:** test object binding for structured collections.

### Exercise G — Conditional Bean

1. Create FeatureConfiguration with @ConditionalOnProperty.
2. Run with enabled=true.
3. Run with enabled=false.
4. Run with the key absent.
5. Assert bean presence matches expectations.

**Goal:** test configuration-driven registration, not only field values.

### Exercise H — Runner Limitations

1. Create **application-prod.yml** with a distinct key.
2. Run the runner with only **spring.profiles.active=prod**.
3. Observe that the test cannot rely on SpringApplication's Config Data pipeline by default.
4. Write an appropriate integration test to load the real profile.
5. Compare the scope of the two tests.

**Goal:** pick the right tool for the right system layer.

## 31. Checklist for a Configuration Bean Test

A solid test should verify:

- Is the target type registered with **@EnableConfigurationProperties** or an equivalent mechanism?
- Are ValidationAutoConfiguration and a Bean Validation implementation included if needed?
- Are keys passed to **withPropertyValues** canonical and spelled accurately?
- Are test values sensible and independent of developer machines?
- Do assertions verify the bean exists and bound into the right Java types?
- Are missing required properties tested?
- Are conversion failures tested?
- Are @NotBlank, @Min, and critical constraints tested?
- Is nested @Valid tested?
- Are default values and overrides tested?
- Are Lists/Maps checked if the model uses collections?
- Is condition evaluation distinguished from configuration binding?
- Do assertions avoid matching brittle patch-version error messages verbatim?
- Are unnecessary real files, network calls, databases, or real secrets avoided?
- Is it clear which behaviors the runner does not simulate, such as profile Config Data?
- Do critical runtime/production boundaries have dedicated integration tests?

## 32. Summary

- **ApplicationContextRunner** creates a small, controllable **non-web Spring ApplicationContext** for testing.
- **withPropertyValues("key=value", ...)** adds Environment property pairs for a scenario.
- **run(context -> ...)** initializes the context, runs assertions, and closes the context after the callback.
- **@EnableConfigurationProperties** registers the configuration bean under test without loading the entire application.
- Assertions should inspect the **configuration bean** itself, not only string properties in Environment.
- **Duration**, numeric values, booleans, and nested objects are converted by Spring Boot Binder into the target model.
- **@Validated**, **@Valid**, and Jakarta Bean Validation enable fail-fast startup when configuration is missing or violates constraints.
- **hasNotFailed()**, **hasSingleBean()**, **hasFailed()**, and **getStartupFailure()** are useful assertions.
- Use a shared base runner across scenarios and override test-specific properties per case.
- **Lists/Maps** can be tested via directly supplied indexed/structured keys.
- **@ConditionalOnProperty** can be tested by asserting bean presence or absence.
- **withPropertyValues** does not load profile-specific Config Data, set real OS env vars, or replace full integration tests.
- When proving application.yml, profiles, mounted secrets, CLI arguments, or container deployments work, add tests at the appropriate integration/runtime layer.

## Official Documentation References

- Spring Boot 3.3 API — **ApplicationContextRunner**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.3 API — **AbstractApplicationContextRunner** and **withPropertyValues**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html
- Spring Boot 3.3 — **Testing Auto-configuration**: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — **Externalized Configuration**, Type-safe Configuration Properties, Binding, Validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — **Testing**: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
