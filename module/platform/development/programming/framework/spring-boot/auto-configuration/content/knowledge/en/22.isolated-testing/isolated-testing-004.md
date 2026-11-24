# withPropertyValues for Configuring Individual Property Cases

> **Spring Boot Auto Configuration → Isolated Testing.** This lesson focuses on using ApplicationContextRunner.withPropertyValues(...) to create context runs with dedicated property sets. We will test enabling/disabling auto-configuration conditions, default values when properties are missing, binding into @ConfigurationProperties, nested data types, invalid value cases, and application-replaced beans. Examples use Java 17+, Maven, and Spring Boot 3.3.13.

## 1. Why configure separate properties for each test?

Auto-configurations frequently change behavior based on environment configuration. A starter may create beans when:

- The user enables a feature via a property.
- A dependency is on the classpath.
- A foundational bean already exists.
- The application has not provided a replacement bean.
- Configuration values have been successfully bound.

If you only run one test with a single fixed configuration, you do not know whether the remaining cases behave correctly. For example:
- When a property does not exist, should the bean be created?
- When the property is false, does the auto-configuration actually stop?
- When the property is true, are URL, timeout, and retry counts bound properly?
- If the timeout value is malformed, does the context report a clear error?
- If the application supplies its own bean, does the default configuration yield?

Spring Boot provides ApplicationContextRunner to create a small context per scenario. The withPropertyValues(...) method lets you pass key=value pairs directly inside the test, without modifying application.properties or machine environment variables.

Each call to run(...) creates a fresh ApplicationContext, performs a refresh, executes the test callback, and closes the context afterward. Thus, each test can choose its own property set and avoid leaking state across cases.

## 2. How does withPropertyValues(...) work?

Basic syntax:

~~~java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
                NoticeAutoConfiguration.class
        ))
        .withPropertyValues(
                "acme.notice.enabled=true",
                "acme.notice.timeout=750ms"
        )
        .run(context -> {
            // assertions
        });
~~~

Each element is a string of the form:

~~~text
property.name=value
~~~

Example:

~~~java
.withPropertyValues(
        "acme.notice.enabled=true",
        "acme.notice.endpoint=https://api.example.test/v1",
        "acme.notice.timeout=750ms",
        "acme.notice.max-attempts=5"
)
~~~

Spring Boot adds these values to the test context's Environment. When auto-configurations are evaluated or configuration beans are bound, they are read like normal properties.

Several rules:
- Each property is a separate string in varargs.
- Use the exact public property names supported by the library.
- Separate name and value with the first equals sign.
- Use kebab-case for property names to stay consistent with Spring Boot configuration.
- Values remain strings when passed to the runner; the Binder or condition converts/compares them per its contract.
- No need to create an application.properties file just to test a value.
- Do not put real secrets into tests; use dummy, non-sensitive values.

### 2.1. Setting a single property

~~~java
runner.withPropertyValues("acme.notice.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(NoticeClient.class);
        });
~~~

### 2.2. Setting multiple properties at once

~~~java
runner.withPropertyValues(
        "acme.notice.enabled=true",
        "acme.notice.timeout=1s",
        "acme.notice.max-attempts=4"
).run(context -> {
    // verify all configurations in the same context
});
~~~

Because the values live in the same context, you can test both conditions and binding at once. For instance, enabled decides whether auto-configuration applies; timeout and max-attempts are bound into the properties bean if configuration is enabled.

### 2.3. Omitting a property is also a case to test

~~~java
runner.run(context -> {
    assertThat(context).doesNotHaveBean(NoticeClient.class);
});
~~~

Not calling withPropertyValues(...) means the runner does not add those properties. This is how you test behavior when users have configured nothing yet.

Do not substitute a missing property case with the string "null". The string null, an empty value, and a missing property are distinct states.

## 3. withPropertyValues and @ConditionalOnProperty

An auto-configuration often uses @ConditionalOnProperty to toggle beans based on configuration.

Example:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class NoticeAutoConfiguration {
    // bean definitions
}
~~~

With the declaration above:

| Property in test | Condition | Outcome |
| --- | --- | --- |
| No acme.notice.enabled | matchIfMissing=false | Does not match |
| acme.notice.enabled=true | havingValue=true | Matches |
| acme.notice.enabled=false | havingValue=true | Does not match |
| acme.notice.enabled=anything-else | havingValue=true | Does not match |

When havingValue="true" is declared, the condition requires the property value to equal true using case-insensitive comparison. In real configurations, stick to lowercase true/false for readability.

If havingValue is omitted, the default rule of @ConditionalOnProperty is that the property must be present and its value must not equal false. This is an important distinction: a property value of "maybe" can match when havingValue is omitted, whereas havingValue="true" requires an explicit true value.

### 3.1. Testing when a property is missing

~~~java
@Test
void missingEnabledPropertyDoesNotCreateClient() {
    runner.run(context -> {
        assertThat(context).doesNotHaveBean(NoticeClient.class);
    });
}
~~~

This test confirms matchIfMissing=false. If someone changes the configuration to matchIfMissing=true, the test fails and flags the change in default contract.

### 3.2. Testing when the feature is enabled

~~~java
@Test
void trueEnablesNoticeClient() {
    runner.withPropertyValues("acme.notice.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(NoticeClient.class);
            });
}
~~~

### 3.3. Testing when the feature is disabled

~~~java
@Test
void falseDisablesNoticeClient() {
    runner.withPropertyValues("acme.notice.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(NoticeClient.class);
            });
}
~~~

The true and false tests should be separate. When a test fails, its name immediately indicates which scenario broke.

### 3.4. Property with multiple conditions

If an auto-configuration requires multiple properties to be enabled together:

~~~java
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = {"enabled", "audit-enabled"},
        havingValue = "true",
        matchIfMissing = false
)
~~~

By default, every name in the list must satisfy the condition. Tests should cover all combinations:

~~~java
@Test
void bothFlagsMustBeTrue() {
    runner.withPropertyValues(
            "acme.notice.enabled=true",
            "acme.notice.audit-enabled=true"
    ).run(context ->
            assertThat(context).hasSingleBean(NoticeClient.class)
    );

    runner.withPropertyValues(
            "acme.notice.enabled=true",
            "acme.notice.audit-enabled=false"
    ).run(context ->
            assertThat(context).doesNotHaveBean(NoticeClient.class)
    );

    runner.withPropertyValues(
            "acme.notice.enabled=false",
            "acme.notice.audit-enabled=true"
    ).run(context ->
            assertThat(context).doesNotHaveBean(NoticeClient.class)
    );
}
~~~

Each run uses a fresh context. No property from the first run is automatically carried over to the next.

## 4. Distinguishing conditions from configuration properties binding

These two mechanisms solve different problems:

- @ConditionalOnProperty decides whether a configuration or bean is registered.
- @ConfigurationProperties reads and converts properties into a typed object.

Example:

~~~properties
acme.notice.enabled=true
acme.notice.endpoint=https://api.example.test/v1
acme.notice.timeout=750ms
acme.notice.max-attempts=5
~~~

enabled controls the condition. endpoint, timeout, and max-attempts supply configuration for the bean.

A good test must confirm both:
1. Does the bean appear when the condition matches?
2. Does the bean receive the bound values correctly?

If you only assert hasSingleBean, you know the bean exists, but you have not proven that configuration was applied.

## 5. Complete project example

This lab builds an auto-configuration for NoticeClient. The bean appears only when acme.notice.enabled=true. Other properties are bound into NoticeProperties and used to construct the client.

### 5.1. Directory structure

~~~text
notice-property-tests/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/notice/
    │   │   ├── NoticeClient.java
    │   │   └── autoconfigure/
    │   │       ├── NoticeProperties.java
    │   │       └── NoticeAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/acme/notice/autoconfigure/
            └── NoticeAutoConfigurationPropertyTest.java
~~~

### 5.2. pom.xml

File pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.acme.notice</groupId>
    <artifactId>notice-property-tests</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

spring-boot-autoconfigure provides annotations and auto-configuration support. spring-boot-starter-test provides JUnit 5, AssertJ, and Spring Boot test support, including ApplicationContextRunner.

### 5.3. NoticeClient.java

File src/main/java/com/acme/notice/NoticeClient.java:

~~~java
package com.acme.notice;

import java.net.URI;
import java.time.Duration;

public record NoticeClient(
        URI endpoint,
        Duration timeout,
        int maxAttempts) {

    public String send(String message) {
        return "sent:" + message;
    }
}
~~~

The client holds three configured values. The send method in the lab returns a deterministic result so tests focus on property binding; it does not make real HTTP requests.

### 5.4. NoticeProperties.java

File src/main/java/com/acme/notice/autoconfigure/NoticeProperties.java:

~~~java
package com.acme.notice.autoconfigure;

import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.notice")
public class NoticeProperties {

    private boolean enabled;
    private URI endpoint = URI.create("https://api.example.test/notice");
    private Duration timeout = Duration.ofSeconds(2);
    private int maxAttempts = 3;
    private List<String> tags = new ArrayList<>();
    private Map<String, String> headers = new LinkedHashMap<>();

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

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

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public Map<String, String> getHeaders() {
        return headers;
    }

    public void setHeaders(Map<String, String> headers) {
        this.headers = headers;
    }
}
~~~

Initial values act as defaults:
- endpoint defaults to an example domain.
- timeout defaults to 2 seconds.
- maxAttempts defaults to 3.
- tags and headers default to empty collections.

Do not use the example endpoint to send real requests. It is strictly a test value to observe the Binder.

### 5.5. NoticeAutoConfiguration.java

File src/main/java/com/acme/notice/autoconfigure/NoticeAutoConfiguration.java:

~~~java
package com.acme.notice.autoconfigure;

import com.acme.notice.NoticeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
@EnableConfigurationProperties(NoticeProperties.class)
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NoticeClient.class)
    NoticeClient noticeClient(NoticeProperties properties) {
        return new NoticeClient(
                properties.getEndpoint(),
                properties.getTimeout(),
                properties.getMaxAttempts()
        );
    }
}
~~~

This configuration has two layers of conditions:
- The class-level condition requires enabled=true. If missing or false, the configuration is not applied.
- The bean-level condition lets the application provide its own NoticeClient. When a matching bean already exists, the default factory method does not register another bean.

@EnableConfigurationProperties registers and binds NoticeProperties when the auto-configuration is applied.

### 5.6. AutoConfiguration.imports

Create the file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Contents:

~~~text
com.acme.notice.autoconfigure.NoticeAutoConfiguration
~~~

This file is required when the module is used as an auto-configuration JAR in a Spring Boot application. However, the tests below use AutoConfigurations.of(NoticeAutoConfiguration.class), meaning they load the configuration class directly to focus on testing property conditions and binding. That testing approach **does not verify that Boot discovers the imports metadata in the JAR**; a dedicated consumer test or packaging test is needed for that purpose.

## 6. Writing tests for individual property cases

File src/test/java/com/acme/notice/autoconfigure/NoticeAutoConfigurationPropertyTest.java:

~~~java
package com.acme.notice.autoconfigure;

import java.net.URI;
import java.time.Duration;

import com.acme.notice.NoticeClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeAutoConfigurationPropertyTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            NoticeAutoConfiguration.class
                    ));

    @Test
    void missingEnabledPropertyDoesNotCreateClient() {
        runner.run(context -> {
            assertThat(context)
                    .doesNotHaveBean(NoticeClient.class);

            assertThat(context)
                    .doesNotHaveBean(NoticeProperties.class);
        });
    }

    @Test
    void enabledPropertyCreatesClientAndBindsValues() {
        runner.withPropertyValues(
                "acme.notice.enabled=true",
                "acme.notice.endpoint=https://api.example.test/v1",
                "acme.notice.timeout=750ms",
                "acme.notice.max-attempts=5",
                "acme.notice.tags[0]=billing",
                "acme.notice.tags[1]=priority",
                "acme.notice.headers[x-region]=apac"
        ).run(context -> {
            assertThat(context).hasSingleBean(NoticeClient.class);
            assertThat(context).hasSingleBean(NoticeProperties.class);

            NoticeProperties properties =
                    context.getBean(NoticeProperties.class);

            assertThat(properties.isEnabled()).isTrue();
            assertThat(properties.getEndpoint())
                    .isEqualTo(URI.create("https://api.example.test/v1"));
            assertThat(properties.getTimeout())
                    .isEqualTo(Duration.ofMillis(750));
            assertThat(properties.getMaxAttempts()).isEqualTo(5);
            assertThat(properties.getTags())
                    .containsExactly("billing", "priority");
            assertThat(properties.getHeaders())
                    .containsEntry("x-region", "apac");

            NoticeClient client = context.getBean(NoticeClient.class);
            assertThat(client.endpoint())
                    .isEqualTo(properties.getEndpoint());
            assertThat(client.timeout())
                    .isEqualTo(properties.getTimeout());
            assertThat(client.maxAttempts())
                    .isEqualTo(5);
            assertThat(client.send("hello"))
                    .isEqualTo("sent:hello");
        });
    }

    @Test
    void falsePropertyDoesNotCreateClient() {
        runner.withPropertyValues("acme.notice.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(NoticeClient.class);
                    assertThat(context)
                            .doesNotHaveBean(NoticeProperties.class);
                });
    }

    @Test
    void defaultValuesAreUsedWhenOnlyEnabledIsSet() {
        runner.withPropertyValues("acme.notice.enabled=true")
                .run(context -> {
                    NoticeProperties properties =
                            context.getBean(NoticeProperties.class);

                    assertThat(properties.getEndpoint())
                            .isEqualTo(
                                URI.create("https://api.example.test/notice")
                            );
                    assertThat(properties.getTimeout())
                            .isEqualTo(Duration.ofSeconds(2));
                    assertThat(properties.getMaxAttempts()).isEqualTo(3);
                    assertThat(properties.getTags()).isEmpty();
                    assertThat(properties.getHeaders()).isEmpty();
                });
    }

    @Test
    void userProvidedClientMakesAutoConfigurationBackOff() {
        NoticeClient customClient = new NoticeClient(
                URI.create("https://custom.example.test/notice"),
                Duration.ofMillis(100),
                1
        );

        runner.withPropertyValues("acme.notice.enabled=true")
                .withBean(NoticeClient.class, () -> customClient)
                .run(context -> {
                    assertThat(context).hasSingleBean(NoticeClient.class);
                    assertThat(context.getBean(NoticeClient.class))
                            .isSameAs(customClient);
                });
    }

    @Test
    void malformedDurationCausesContextStartupFailure() {
        runner.withPropertyValues(
                "acme.notice.enabled=true",
                "acme.notice.timeout=not-a-duration"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
    }

    @Test
    void eachPropertyCaseUsesAnIndependentContext() {
        runner.withPropertyValues("acme.notice.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(NoticeClient.class)
                );

        runner.withPropertyValues("acme.notice.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(NoticeClient.class)
                );

        runner.run(context ->
                assertThat(context).doesNotHaveBean(NoticeClient.class)
        );
    }
}
~~~

The test class keeps a base runner without properties. Each test calls withPropertyValues(...) to produce a runner configured for that scenario. The base runner is never mutated; the runs remain independent.

### 6.1. Testing a missing property

The missingEnabledPropertyDoesNotCreateClient test passes no properties. The expected result is neither NoticeClient nor NoticeProperties, because the condition is on the entire auto-configuration class.

If matchIfMissing is changed to true, this test will catch the change in default behavior.

### 6.2. Testing enabled state and binding multiple data types

The enabledPropertyCreatesClientAndBindsValues test sets multiple properties in a single run:
- boolean: enabled=true.
- URI: endpoint.
- Duration: timeout=750ms.
- integer: max-attempts=5.
- List: tags[0], tags[1].
- Map: headers[x-region].

The Binder converts the strings into the corresponding Java types. The test checks both the NoticeProperties object and the NoticeClient created from it.

This catches property naming bugs, conversion errors, and factory methods failing to use bound values.

### 6.3. Testing property set to false

The falsePropertyDoesNotCreateClient test protects explicit opt-out behavior. When the feature is disabled, the default bean does not appear.

If the configuration only placed the condition on the factory method instead of the class, NoticeProperties might still exist. In this lab the condition is on the class, so the properties configuration is not registered either.

### 6.4. Testing default values

Users might only enable the feature without declaring every attribute. The defaultValuesAreUsedWhenOnlyEnabledIsSet test verifies that initial values in NoticeProperties are preserved.

Default values are part of the public configuration API. When changing default timeouts or retry counts, tests help detect behavior changes that could impact consumers.

### 6.5. Testing application-provided beans

The userProvidedClientMakesAutoConfigurationBackOff test registers a bean in the runner using withBean(...). Because the auto-configuration uses @ConditionalOnMissingBean, the competing default bean is not created.

Checking isSameAs confirms the context returns the exact instance supplied by the test. This tests the override contract, not just bean count.

### 6.6. Testing malformed values

The malformedDurationCausesContextStartupFailure test passes a string that cannot be converted to Duration. Because NoticeProperties is registered and bound on context startup, the context must fail.

In real tests, inspect the startup failure and root cause when specific diagnostics are needed. Avoid depending on the full exception message string, as wording can change across Binder versions.

### 6.7. Testing independence across runs

The eachPropertyCaseUsesAnIndependentContext test runs the same base runner three times:
1. enabled=true.
2. enabled=false.
3. No properties.

Each run produces its own result. This test illustrates reusing a runner without reusing the ApplicationContext or property sources from prior runs.

## 7. Running tests and reading results

From the directory containing pom.xml:

~~~bash
mvn clean test
~~~

The expected result is that all tests in NoticeAutoConfigurationPropertyTest pass. The sample class contains 7 tests.

Maven may print additional timing, plugin versions, and total test counts depending on the environment. Do not write tests relying on full Maven log lines; use assertions inside the tests as primary evidence.

If the malformed duration test fails because the context reports no error, check:
- Is NoticeProperties registered with @EnableConfigurationProperties?
- Did the property condition match so the configuration was applied?
- Did the test actually trigger the properties bean so binding occurred?
- Does the property name match the prefix and field?
- Does the field type support the expected conversion?

## 8. Common property formats in withPropertyValues

### 8.1. Boolean

~~~java
.withPropertyValues(
        "acme.notice.enabled=true",
        "acme.notice.audit-enabled=false"
)
~~~

Use booleans for feature flags. With @ConditionalOnProperty havingValue="true", enable explicitly using true. Avoid arbitrary words like on, yes, or enabled unless the library contract defines them.

### 8.2. Integer and decimal

~~~java
.withPropertyValues(
        "acme.notice.max-attempts=4",
        "acme.notice.failure-rate=0.25"
)
~~~

The Binder converts to int, long, double, or the matching numeric type. Tests should check valid boundaries and invalid values if the library enforces validation rules.

### 8.3. Duration

~~~java
.withPropertyValues(
        "acme.notice.timeout=750ms",
        "acme.notice.idle-timeout=2s"
)
~~~

Spring Boot supports binding Duration from unit suffixes such as ns, us, ms, s, m, h, and d. Using explicit unit suffixes makes tests easier to read. If unitless values are used, their meaning may depend on @DurationUnit or field conventions; document this clearly.

### 8.4. Data size

~~~java
.withPropertyValues(
        "acme.notice.buffer-size=16KB"
)
~~~

For DataSize fields, the Binder converts units such as B, KB, MB, and GB following Spring Boot rules. Tests should verify the actual byte count rather than just checking the input string.

### 8.5. URI and URL

~~~java
.withPropertyValues(
        "acme.notice.endpoint=https://api.example.test/v1"
)
~~~

If the field is a URI, tests check the converted URI value. If the field is a String, the Binder does not guarantee a valid URL automatically; validate separately in that case.

### 8.6. List and array

~~~java
.withPropertyValues(
        "acme.notice.tags[0]=billing",
        "acme.notice.tags[1]=priority"
)
~~~

Indexed notation works well when testing element ordering. Comma-separated strings work for some binding types, but indexed notation is clearer when element values might contain delimiters.

### 8.7. Map

~~~java
.withPropertyValues(
        "acme.notice.headers[x-region]=apac",
        "acme.notice.headers[x-client]=consumer-test"
)
~~~

Bracket notation preserves keys containing hyphens or special characters. Tests should verify both keys and values in the Map after binding.

### 8.8. Nested properties

Given the structure:

~~~java
public class RetryProperties {
    private int maxAttempts = 3;
    private Duration backoff = Duration.ofMillis(200);

    // getters and setters
}
~~~

and a retry field in NoticeProperties, you can pass:

~~~java
.withPropertyValues(
        "acme.notice.retry.max-attempts=5",
        "acme.notice.retry.backoff=500ms"
)
~~~

Dots represent paths to nested properties. Tests should verify both that the child object is created and that values inside it are bound.

## 9. Combining property conditions with multiple beans

An auto-configuration can register multiple beans under different conditions. For example:
- NoticeClient requires acme.notice.enabled=true.
- NoticeAuditPublisher requires acme.notice.audit.enabled=true and an AuditSink bean.
- NoticeMetricsBinder requires a MeterRegistry bean.

Do not lump every condition onto one class if the beans do not share the same dependencies. If a condition sits at the class level, one property can accidentally block all beans.

Nested configuration example:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = "enabled",
        havingValue = "true"
)
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    NoticeClient noticeClient() {
        return new NoticeClient();
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "acme.notice.audit",
            name = "enabled",
            havingValue = "true"
    )
    static class AuditConfiguration {

        @Bean
        @ConditionalOnMissingBean
        NoticeAuditPublisher noticeAuditPublisher(AuditSink sink) {
            return new NoticeAuditPublisher(sink);
        }
    }
}
~~~

You can test each combination:

~~~java
@Test
void auditRequiresBothCoreAndAuditFlags() {
    runner.withPropertyValues(
            "acme.notice.enabled=true",
            "acme.notice.audit.enabled=true"
    ).withBean(AuditSink.class, AuditSink::new)
     .run(context -> {
         assertThat(context).hasSingleBean(NoticeClient.class);
         assertThat(context).hasSingleBean(NoticeAuditPublisher.class);
     });

    runner.withPropertyValues(
            "acme.notice.enabled=true",
            "acme.notice.audit.enabled=false"
    ).withBean(AuditSink.class, AuditSink::new)
     .run(context -> {
         assertThat(context).hasSingleBean(NoticeClient.class);
         assertThat(context).doesNotHaveBean(NoticeAuditPublisher.class);
     });
}
~~~

This is an illustrative structural example; types such as AuditSink and NoticeAuditPublisher must be defined in the project to compile the test. The key point is testing combinations of flags and bean dependencies rather than only the all-enabled state.

## 10. withPropertyValues compared with other ways of supplying properties

| Approach | Scope | When appropriate |
| --- | --- | --- |
| ApplicationContextRunner.withPropertyValues | Single test runner/context | Fast, isolated auto-configuration testing |
| @SpringBootTest(properties = ...) | Spring Boot application context in integration tests | Broader application testing with custom properties |
| @TestPropertySource | Tests using the Spring TestContext Framework | Test configuration via annotations or property files |
| @DynamicPropertySource | Dynamic property registration in integration tests | Values provided by Testcontainers or test-initialized resources |
| withSystemProperties | System properties in the runner | Testing behavior dependent on specific system properties |

Example with a full application context:

~~~java
@SpringBootTest(properties = {
        "acme.notice.enabled=true",
        "acme.notice.timeout=500ms"
})
class NoticeApplicationTest {
}
~~~

This tests the full application more thoroughly, but initializes a heavier context. For conditions of a single auto-configuration, ApplicationContextRunner is generally faster and more focused.

Do not use withPropertyValues as a substitute for Testcontainers or real connectivity testing. It configures properties; it does not start a database, broker, or HTTP server.

## 11. Organizing tests to avoid bugs and poor readability

### 11.1. Each test should describe one scenario

Test names should state the condition and expected outcome clearly:
- missingEnabledPropertyDoesNotCreateClient
- trueEnablesNoticeClient
- falseDisablesNoticeClient
- customClientMakesAutoConfigurationBackOff
- malformedTimeoutFailsContext

Avoid cramming all assertions into one giant test. When a scenario fails, you need to know which property and behavior to investigate.

### 11.2. Create helpers for repeated configurations

If many tests need the feature enabled, you can create a helper:

~~~java
private ApplicationContextRunner enabledRunner() {
    return runner.withPropertyValues("acme.notice.enabled=true");
}
~~~

Then:

~~~java
enabledRunner().run(context -> {
    assertThat(context).hasSingleBean(NoticeClient.class);
});
~~~

Helpers should only consolidate shared setup. When each test needs different values, pass properties directly so the scenario remains easy to read.

### 11.3. Do not mutate the base runner with custom mutable state

ApplicationContextRunner follows a fluent design: configuration methods return a newly configured runner. You can keep a base runner and derive variants for each test.

Do not store an ApplicationContext in a static field to reuse across tests. Contexts should close after their callback; retaining references can lead to using beans after shutdown or order-dependent tests.

### 11.4. Assert both presence and absence

Condition tests should verify:
- Expected beans appear exactly once.
- Disallowed beans are genuinely absent.
- Replacement beans are the exact expected instances.
- Bound properties hold expected values.

Merely checking that the context does not fail is insufficient. A context can start successfully while auto-configuration registers no beans due to an incorrect condition.

### 11.5. Test intentional configuration failures

If a property is malformed, the test should confirm the context fails. If a value is syntactically valid but outside business bounds, Bean Validation or constructor validation can reject the configuration. When adding validation, declare the required dependencies and test messages/errors against the contract.

## 12. Limitations and caveats

- ApplicationContextRunner typically uses a non-web context; if configuration depends on a Servlet or Reactive web application type, use WebApplicationContextRunner or ReactiveWebApplicationContextRunner respectively.
- AutoConfigurations.of(...) loads configuration classes directly. It does not verify that AutoConfiguration.imports is packaged properly in the JAR.
- withPropertyValues(...) sets properties for the test context; it does not prove environment variables or production configs are deployed correctly.
- @ConditionalOnProperty is not ideal for checking the presence of a collection with only indexed entries; use an appropriate condition or binding logic for that case.
- Property conversion can succeed at the type level while still being invalid semantically. For example, a timeout of 0 may bind cleanly yet be unsuitable for the application.
- Default values are part of the public API; changing defaults can change consumer behavior.
- If a condition is placed at the class level, all beans and configuration properties in that class are governed by it.
- If only one bean needs a specific property, place the condition on that bean or a nested configuration so it does not block the rest.
- When multiple properties must match together, test missing, false, and true combinations.
- If tests only load auto-configuration classes via AutoConfigurations.of, a separate packaging/consumer test is still needed to verify discovery metadata.

## 13. Common mistakes when using withPropertyValues

1. **Misspelling the key:** the test passes acme.notice.enable while the code expects acme.notice.enabled. The test may pass along the no-bean branch and mask the typo.
2. **Using a colon instead of an equals sign:** each element should follow the key=value form.
3. **Confusing a missing property with an empty value:** omitting a key differs from passing key=.
4. **Testing only true:** misses defaults when the property is absent and misses the false branch.
5. **Not testing matchIfMissing:** changing defaults can break the contract silently without test alerts.
6. **Not verifying binding:** the bean may be created while timeout/endpoint still keep default values.
7. **Using unitless Duration values:** makes tests harder to read or dependent on implicit conventions.
8. **Using the wrong property prefix:** conditions fail to match or the Binder fails to bind fields.
9. **Combining too many scenarios into one test:** makes it hard to tell which assertion failed and which state caused the error.
10. **Reusing the context instead of the runner:** bean state and singletons can leak between tests.
11. **Assuming the runner checks AutoConfiguration.imports:** AutoConfigurations.of loads classes directly; metadata needs separate tests.
12. **Thinking property tests create real resources:** setting a URL does not start a database or server.
13. **Not testing malformed values:** conversion errors appear only when the context binds properties.
14. **Placing overly broad conditions:** disabling one integration drops unrelated beans.
15. **Asserting only that the context started:** you must assert bean presence/absence and bound values.
16. **Using real secrets:** tests must use dummy data to keep credentials out of source code and reports.
17. **Assuming runner properties modify application.properties:** they belong only to the test context and do not edit configuration files.
18. **Not testing user overrides:** the starter might create a competing default bean alongside the application's bean.

## 14. Workflow for writing a property test suite

1. List the properties controlling conditions and binding.
2. Document defaults when properties are missing.
3. Identify valid, invalid, and boundary values.
4. Create an ApplicationContextRunner with the auto-configurations under test.
5. Write a separate test for missing properties.
6. Write tests for true and false.
7. Pass multiple properties together to verify binding.
8. Verify default values when only the feature flag is enabled.
9. Verify bean overrides using withBean.
10. Verify conversion failures or validation failures.
11. Ensure each run uses an independent context.
12. Run mvn clean test.
13. If metadata or real application behavior must be verified, add separate consumer/integration tests.

## 15. Acceptance checklist

- [ ] Runner is configured via AutoConfigurations.of with the exact classes under test.
- [ ] Tests cover missing properties.
- [ ] Tests cover property set to true.
- [ ] Tests cover property set to false.
- [ ] matchIfMissing is verified.
- [ ] havingValue is verified.
- [ ] Multiple properties are passed in the same run when needed.
- [ ] Configuration properties are inspected after binding.
- [ ] Boolean, numeric, Duration, URI, and list/map types are tested if used.
- [ ] Default values are verified.
- [ ] Malformed values are tested where meaningful.
- [ ] User-provided beans cause auto-configuration to back off.
- [ ] Each test runs in an independent context.
- [ ] Assertions confirm bean presence/absence, not just context startup.
- [ ] No real secrets are used in tests.
- [ ] Property tests are distinguished from metadata/JAR checks and real connectivity tests.

## 16. Self-check questions

**Question 1.** What format of strings does withPropertyValues accept?  
**Answer:** Each element has the form key=value, for example acme.notice.enabled=true.

**Question 2.** How do you test when a property does not exist?  
**Answer:** Call runner.run(...) without adding withPropertyValues for that property, then assert bean presence/absence according to matchIfMissing.

**Question 3.** Does withPropertyValues modify application.properties?  
**Answer:** No. It adds properties to the test context's Environment.

**Question 4.** Why test both the condition and NoticeProperties?  
**Answer:** The condition decides whether the bean is registered; configuration binding determines which configuration values the bean receives.

**Question 5.** How do you set a list in a test?  
**Answer:** You can use indexed properties like acme.notice.tags[0]=billing and acme.notice.tags[1]=priority.

**Question 6.** How do you confirm an application-provided bean takes precedence?  
**Answer:** Add the bean via withBean(...), enable the property, then assert the context has only one bean and the returned instance is the custom bean.

**Question 7.** Does ApplicationContextRunner verify imports metadata in the JAR?  
**Answer:** Not when using AutoConfigurations.of(Class...). That loads classes directly; a consumer or packaged integration test is needed to verify discovery metadata.

**Question 8.** Why separate tests for true, false, and missing?  
**Answer:** The three states protect three distinct contract branches, making it easier to catch default changes and condition bugs.

## 17. Official reference documentation

- [Spring Boot 3.3 Reference — Testing Your Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).
- [Spring Boot 3.3 Javadoc — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).
- [Spring Boot 3.3 Javadoc — AbstractApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html).
- [Spring Boot 3.3 Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot 3.3 Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).
- [Spring Boot 3.3 Javadoc — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).