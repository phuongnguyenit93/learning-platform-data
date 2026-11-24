# Minimal defaults, transparent customizability, and consistent feature disabling

## 1. Design goals of a good auto-configuration

A Spring Boot starter can make an application runnable simply by adding a dependency. However, that convenience is only valuable when the starter behaves predictably and does not seize control of the application.

A well-designed auto-configuration should satisfy three principles:

1. **Minimal defaults:** do not enable integrations with side effects merely because the library appears on the classpath. Default values must be safe, light on resources, and not automatically open connections or start unnecessary background work.
2. **Transparent customizability:** the application knows which beans and properties can be replaced, what the precedence order is, and when the starter will back off. Users should not have to cast to internal implementations or depend on arbitrary bean names.
3. **Consistent feature disabling:** when a feature is disabled, every component managed by the starter for that feature must follow the same state. Never leave the client disabled while a scheduler, listener, connection pool, or background task keeps running.

These three principles reinforce one another. Safe defaults reduce surprises; a clear customization contract avoids bean conflicts; a consistent feature switch lets the application control lifecycle and resources.

This article uses Java 17+, Maven, and Spring Boot 3.3.13. The example is a Catalog library with an optional HTTP client. The goal is to illustrate how to design and test auto-configuration; real-world applications should adapt endpoints, authentication, retries, and error policies to the service API.

## 2. Minimal defaults: do only what the user asked for

### 2.1. Having a dependency does not mean enabling the feature

An application adding a starter might only want to use an API, inspect metadata, or prepare configuration for another environment. If the starter eagerly connects to a service at startup, it can:

- Cause startup failures when the external service is temporarily unavailable.
- Open sockets, spawn threads, or allocate connection pools even when the application does not use the feature.
- Send unexpected requests.
- Increase startup time and resource consumption.
- Produce different behavior across local, test, staging, and production.

For integrations with external effects, a safe choice is **opt-in**: the feature stays disabled when the property is undeclared, and turns on only when the user explicitly sets **enabled=true**.

Example:

```yaml
acme:
  catalog:
    enabled: true
```

In auto-configuration:

```java
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
```

**matchIfMissing=false** ensures that a missing property has the same effect as the feature being disabled. Writing this value explicitly helps readers spot the opt-in policy directly in code.

### 2.2. Choose bounded and explainable defaults

Good defaults typically share these traits:

- Do not create network connections or background workers when the feature is not enabled.
- Do not auto-detect and use unintended credentials or endpoints.
- Have finite timeouts instead of waiting indefinitely.
- Have bounded pool, queue, and retry sizes when those resources are created.
- Do not enable sensitive logging or log request/response bodies by default.
- Do not implicitly alter the behavior of application-provided beans.
- Can be overridden via documented properties or extension points.

Not every property should have a default. Required values such as an endpoint, tenant, or credentials should be left unset and fail clearly when the user enables the feature without providing them. Fabricating a default production endpoint or credential creates false convenience.

### 2.3. Distinguish default configuration from default action

Creating a configuration object or client wrapper does not necessarily mean performing I/O. However, an object's constructor might open connections, run migrations, spawn threads, or call remote APIs.

Keep initialization lightweight:

- Creating an HttpClient or configuration object can happen when the feature is enabled.
- Send HTTP requests only when the consumer invokes the corresponding method.
- Create schedulers only when polling is explicitly enabled.
- Register listeners with side effects only when the feature is active.
- Do not make network calls inside constructors or @Bean factory methods.

The example in this article builds a JDK HttpClient when the feature is enabled, but sends no requests during startup. Requests are sent only when the consumer calls findById.

## 3. Customizability must be an explicit contract

### 3.1. Use a public interface as the replacement point

If an application can supply its own client, expose an interface as the contract:

```java
public interface CatalogClient {

    Optional<String> findById(String id)
            throws IOException, InterruptedException;
}
```

Business code depends on CatalogClient. The starter can provide a default implementation, while the application can supply its own bean.

Do not require consumers to cast beans to DefaultCatalogClient, import nested configurations, or invoke internal implementation constructors. Those details can change without breaking the contract.

### 3.2. @ConditionalOnMissingBean expresses precedence

A default bean commonly uses:

```java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient(CatalogProperties properties) {
    return new DefaultCatalogClient(properties);
}
```

Meaning: if the context already contains a bean matching CatalogClient, auto-configuration will not create the default bean.

This rule establishes an intuitive precedence order:

1. The application provides its own implementation.
2. If the application does not provide one, the starter creates the default implementation.
3. If the feature is disabled, auto-configuration does not create starter-managed beans.

@ConditionalOnMissingBean is a common customization hook in auto-configuration. It does not automatically turn every bean into a stable API; the library still needs to document which types are meant to be replaced and what back-off behavior users can rely on.

### 3.3. Place conditions at the right scope

If a feature is disabled, @ConditionalOnProperty should be placed on the configuration class or nested configuration encompassing all beans belonging to that feature. Then the default client, properties bean, and dependent components are enabled/disabled together.

Example:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {
    // Feature beans live in this configuration.
}
```

If a condition is placed on only one @Bean method while other beans still get registered, the application can fall into a half-enabled state. For instance, the client disappears while the scheduler still starts and repeatedly looks for the client.

For large auto-configurations, each feature can be split into a separate nested configuration. What matters is that every component sharing the same lifecycle is guarded by the same condition or equivalent conditions.

### 3.4. Distinguish starter-managed beans from application-owned beans

The property **acme.catalog.enabled=false** can prevent auto-configuration from creating beans. It does not remove beans that the application declared itself.

This is an intentional ownership boundary:

- The starter controls the beans inside its auto-configuration.
- The application controls the beans declared by the application.
- If the application wants all Catalog consumers/schedulers to stop as well, those components must honor the same feature switch or be controlled accordingly by the application.

Do not claim that a starter property removes every bean of that type from the ApplicationContext. Spring does not automatically delete beans registered by other configurations just because an auto-configuration was excluded by a condition.

## 4. Feature disabling behavior must be consistent

### 4.1. Define clearly what disabled means

For an optional integration, the disabled state can be defined as follows:

| Component | When the feature is disabled |
|---|---|
| Default client | Not registered |
| Feature-specific properties bean | Not registered if only needed when the feature is active |
| HTTP requests at startup | Not sent |
| Connection pool / scheduler | Not created |
| Listeners with side effects | Not registered |
| Integration-specific metrics | Not initialized if they only serve the feature |
| Application-declared beans | Remain owned by the application |

This table is a design contract. If the library wants to keep a properties bean even when the feature is disabled so the application can read its values, state that exception explicitly and test it. Do not let actual state depend on accidental annotation placement.

### 4.2. Avoid creating side effects before conditions are evaluated

Do not do the following in a static initializer or constructor of an auto-configuration class:

- Open sockets or call remote services.
- Start threads.
- Register global shutdown hooks.
- Mutate system properties.
- Read credentials from locations not configured by the user.
- Run migrations or create resources outside the ApplicationContext.

These operations can happen before Spring evaluates bean conditions or be hard to roll back when context startup fails.

Place side effects inside the lifecycle of condition-guarded beans, and prefer lazy initialization when the feature permits. When beans close or the context shuts down, release resources via an appropriate lifecycle contract such as close() or @PreDestroy.

### 4.3. Disabling a feature must not leave parts running in the background

Suppose Catalog has a client, a polling scheduler, and a metrics exporter. If only the client has the condition, the scheduler may still be created and throw errors or consume CPU.

A shared nested configuration can be used:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true")
static class CatalogEnabledConfiguration {

    // Client, scheduler, and beans that only exist when the feature is enabled.
}
```

If a component has a different lifecycle, document its separate condition and explain why it still needs to exist when the main feature is disabled. Avoid undocumented exceptions.

### 4.4. Distinguish disabled from misconfiguration

Three states must carry distinct meanings:

- **Disabled:** the user has not enabled the feature; the starter registers no feature beans and produces no side effects.
- **Enabled and valid:** the starter creates the default bean or uses a custom bean.
- **Enabled but missing required configuration:** startup fails fast with a message specifying which property needs to be supplied.

Do not silently treat a missing endpoint as disabled when the user explicitly set enabled=true. That hides configuration errors and makes the feature appear enabled while actually doing nothing.

## 5. Designing the Catalog example

We build a library with the following contracts:

- CatalogClient: public interface for looking up items.
- CatalogProperties: public configuration with prefix acme.catalog.
- CatalogAutoConfiguration: creates the default client automatically when the feature is enabled and the application has not provided a client.
- DefaultCatalogClient: internal implementation using JDK HttpClient.

Policies of the example:

| Property | Default | Rule |
|---|---|---|
| acme.catalog.enabled | false | Must be explicitly enabled with true |
| acme.catalog.base-url | None | Required when the starter creates the default client |
| acme.catalog.connect-timeout | 2s | Must be positive |
| acme.catalog.request-timeout | 3s | Must be positive |

When the feature is disabled, CatalogAutoConfiguration does not apply and neither starter-managed CatalogProperties nor CatalogClient is registered. When enabled, the endpoint must be an absolute HTTP(S) URI with a host, and without query or fragment.

If the application provides its own CatalogClient, the starter backs off. The application is responsible for that client's endpoint, timeouts, retries, and lifecycle. base-url is required only for the default implementation.

## 6. Complete Maven example with Spring Boot 3.3.13

### 6.1. Directory structure

```text
catalog-starter/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/catalog/
    │   │   ├── CatalogClient.java
    │   │   └── CatalogProperties.java
    │   ├── java/com/acme/catalog/autoconfigure/
    │   │   └── CatalogAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/acme/catalog/autoconfigure/
        └── CatalogAutoConfigurationTests.java
```

### 6.2. pom.xml

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
    <artifactId>catalog-starter</artifactId>
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

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>
    </dependencies>
</project>
```

The configuration processor is optional and only assists with generating IDE metadata during the build. It is not a runtime dependency that consuming applications must declare for the client to work.

### 6.3. CatalogClient.java — public contract

```java
package com.acme.catalog;

import java.io.IOException;
import java.util.Optional;

public interface CatalogClient {

    Optional<String> findById(String id)
            throws IOException, InterruptedException;
}
```

The application depends on this interface. The contract specifies that a non-existent item returns Optional.empty(), while I/O errors or interrupted requests propagate to the caller.

### 6.4. CatalogProperties.java — public configuration

```java
package com.acme.catalog;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.catalog")
public class CatalogProperties {

    private boolean enabled = false;
    private URI baseUrl;
    private Duration connectTimeout = Duration.ofSeconds(2);
    private Duration requestTimeout = Duration.ofSeconds(3);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

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

    public Duration getRequestTimeout() {
        return requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }
}
```

enabled defaults to false. baseUrl intentionally has no default so requests are never sent to a fictional endpoint. The two timeouts have finite defaults so requests do not wait indefinitely.

### 6.5. CatalogAutoConfiguration.java — conditions, override, and default client

```java
package com.acme.catalog.autoconfigure;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Optional;

import com.acme.catalog.CatalogClient;
import com.acme.catalog.CatalogProperties;

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
        matchIfMissing = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient(CatalogProperties properties) {
        return new DefaultCatalogClient(properties);
    }

    private static final class DefaultCatalogClient
            implements CatalogClient {

        private final HttpClient httpClient;
        private final URI baseUrl;
        private final Duration requestTimeout;

        private DefaultCatalogClient(CatalogProperties properties) {
            this.baseUrl = requireBaseUrl(properties.getBaseUrl());
            Duration connectTimeout = requirePositive(
                    properties.getConnectTimeout(),
                    "acme.catalog.connect-timeout");
            this.requestTimeout = requirePositive(
                    properties.getRequestTimeout(),
                    "acme.catalog.request-timeout");

            this.httpClient = HttpClient.newBuilder()
                    .connectTimeout(connectTimeout)
                    .build();
        }

        @Override
        public Optional<String> findById(String id)
                throws IOException, InterruptedException {

            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException(
                        "Catalog item id must not be blank.");
            }

            String encodedId = URLEncoder.encode(
                    id,
                    StandardCharsets.UTF_8);

            URI requestUri = URI.create(
                    baseUrl.toASCIIString() + "?id=" + encodedId);

            HttpRequest request = HttpRequest.newBuilder(requestUri)
                    .timeout(requestTimeout)
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 404) {
                return Optional.empty();
            }

            if (response.statusCode() < 200
                    || response.statusCode() >= 300) {
                throw new IOException(
                        "Catalog returned HTTP " + response.statusCode());
            }

            return Optional.of(response.body());
        }

        private static URI requireBaseUrl(URI value) {
            String scheme = value == null ? null : value.getScheme();

            boolean valid = value != null
                    && value.isAbsolute()
                    && value.getHost() != null
                    && ("http".equalsIgnoreCase(scheme)
                        || "https".equalsIgnoreCase(scheme))
                    && value.getQuery() == null
                    && value.getFragment() == null;

            if (!valid) {
                throw new IllegalStateException(
                        "Property acme.catalog.base-url must be an "
                                + "absolute HTTP(S) URI with a host "
                                + "and without query or fragment.");
            }

            return value;
        }

        private static Duration requirePositive(
                Duration value,
                String propertyName) {

            if (value == null || value.isZero() || value.isNegative()) {
                throw new IllegalStateException(
                        "Property " + propertyName
                                + " must be greater than zero.");
            }

            return value;
        }
    }
}
```

Key decisions:

1. @ConditionalOnProperty is placed on the entire auto-configuration. When the property is missing or false, starter-managed beans are not registered.
2. @EnableConfigurationProperties sits on the guarded class, so CatalogProperties is created only when the feature is enabled.
3. @ConditionalOnMissingBean(CatalogClient.class) allows the application to replace the default client by type.
4. DefaultCatalogClient is a private nested class; consumers only see CatalogClient.
5. Endpoint and timeouts are validated when creating the default client. Invalid configuration causes fail-fast startup naming the specific property.
6. HttpClient is constructed without sending requests at startup. I/O happens only when the caller invokes findById.
7. No scheduler, dedicated thread, or remote side effect is created when the feature is disabled.

The endpoint in the example is treated as a resource collection URL; requests are sent to base-url?id=... Real HTTP contracts should match the API of the integrated service.

### 6.6. AutoConfiguration.imports

Create file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Content:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

Register only the top-level auto-configuration. Consumers do not need to import the implementation or bean methods.

### 6.7. application.yml when enabling the feature

```yaml
acme:
  catalog:
    enabled: true
    base-url: https://catalog.example.test/items
    connect-timeout: 2s
    request-timeout: 3s
```

Without enabled: true, the feature stays disabled. If enabled without base-url, the starter raises an error rather than silently creating a non-functional client.

## 7. Testing default, override, and disabled policies

ApplicationContextRunner allows testing auto-configuration in a lightweight context without starting a web server or calling real services.

### 7.1. CatalogAutoConfigurationTests.java

```java
package com.acme.catalog.autoconfigure;

import java.net.URI;
import java.time.Duration;
import java.util.Optional;

import com.acme.catalog.CatalogClient;
import com.acme.catalog.CatalogProperties;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class));

    @Test
    void featureIsDisabledWhenPropertyIsMissing() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(CatalogClient.class);
            assertThat(context).doesNotHaveBean(CatalogProperties.class);
        });
    }

    @Test
    void explicitFalseKeepsAllStarterManagedBeansDisabled() {
        runner.withPropertyValues("acme.catalog.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(CatalogClient.class);
                    assertThat(context).doesNotHaveBean(
                            CatalogProperties.class);
                });
    }

    @Test
    void enabledFeatureCreatesDefaultClientWithBoundSettings() {
        runner.withPropertyValues(
                        "acme.catalog.enabled=true",
                        "acme.catalog.base-url=https://catalog.example.test/items",
                        "acme.catalog.connect-timeout=1s",
                        "acme.catalog.request-timeout=4s")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);

                    CatalogProperties properties =
                            context.getBean(CatalogProperties.class);

                    assertThat(properties.getBaseUrl())
                            .isEqualTo(URI.create(
                                    "https://catalog.example.test/items"));
                    assertThat(properties.getConnectTimeout())
                            .isEqualTo(Duration.ofSeconds(1));
                    assertThat(properties.getRequestTimeout())
                            .isEqualTo(Duration.ofSeconds(4));
                });
    }

    @Test
    void applicationClientOverridesTheDefaultClient() {
        runner.withPropertyValues("acme.catalog.enabled=true")
                .withUserConfiguration(UserCatalogConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);

                    CatalogClient client =
                            context.getBean(CatalogClient.class);

                    assertThat(client.findById("42"))
                            .isEqualTo(Optional.of("custom-item:42"));
                });
    }

    @Test
    void enabledFeatureWithoutBaseUrlFailsFast() {
        runner.withPropertyValues("acme.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasStackTraceContaining(
                                    "Property acme.catalog.base-url");
                });
    }

    @Test
    void disabledAutoConfigurationDoesNotRemoveAnApplicationOwnedBean() {
        runner.withPropertyValues("acme.catalog.enabled=false")
                .withUserConfiguration(UserCatalogConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);

                    assertThat(context.getBean(CatalogClient.class)
                            .findById("42"))
                            .isEqualTo(Optional.of("custom-item:42"));
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {

        @Bean
        CatalogClient customCatalogClient() {
            return id -> Optional.of("custom-item:" + id);
        }
    }
}
```

### 7.2. Meaning of the six tests

| Test | Configuration | Verified outcome |
|---|---|---|
| featureIsDisabledWhenPropertyIsMissing | enabled not declared | No starter client or properties bean |
| explicitFalseKeepsAllStarterManagedBeansDisabled | enabled=false | No starter-managed beans |
| enabledFeatureCreatesDefaultClientWithBoundSettings | enabled=true and valid endpoint | Client present; properties bound correctly |
| applicationClientOverridesTheDefaultClient | enabled=true and user bean | Only application-provided client present |
| enabledFeatureWithoutBaseUrlFailsFast | enabled=true without endpoint | Context fails with property message |
| disabledAutoConfigurationDoesNotRemoveAnApplicationOwnedBean | enabled=false and user bean | Application-declared bean still exists |

The last test clarifies ownership: the disabled property prevents the starter from creating the default bean; it does not remove beans registered by the application itself. If an application wants to disable the entire Catalog business flow, it must apply the same state to its own managed consumers or schedulers.

### 7.3. Run tests

Using JDK 17+ and Maven in the directory containing pom.xml:

```bash
mvn test
```

With the six tests above, the expected output is:

```text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

This is the expected output from the example code, not a log from an executed run. The tests do not invoke findById, so no HTTP requests are sent to external endpoints.

## 8. Precedence rules between properties and custom beans

A starter typically supports both customization mechanisms:

- Properties that tune the default implementation.
- Application-provided beans that replace the default implementation.

The precedence order should be published. The example in this article uses these rules:

1. enabled determines whether the starter participates.
2. If disabled, auto-configuration creates no feature beans.
3. If enabled and the application has a CatalogClient, the starter backs off.
4. If enabled and no CatalogClient exists, the starter requires base-url, validates timeouts, and creates the default client.
5. When a custom client is used, the application is responsible for that client's configuration and lifecycle.

Do not force users to guess whether base-url applies to a custom client. In the example, this property is used only by the default implementation. If a property is meant to take effect even when a custom client is supplied, the library needs a different contract, such as a CatalogClientCustomizer invoked after client creation or a properties object passed into the user's implementation.

### 8.1. Do not silently override application beans

Avoid registering a default bean without a condition:

```java
@Bean
CatalogClient catalogClient() {
    return new DefaultCatalogClient(...);
}
```

If the application also registers a CatalogClient, the context may have two candidates, causing NoUniqueBeanDefinitionException or qualifier-dependent injection behavior.

Use @ConditionalOnMissingBean(CatalogClient.class) when the library intentionally permits overriding. If the default bean must be unique and cannot be replaced, state that explicitly and design the contract accordingly; do not let bean conflicts become an accidental barrier to customization.

### 8.2. Do not use properties to silently swap implementations

For instance, a property acme.catalog.custom=true without documented bean precedence can make it unclear which implementation is active in the application.

If the starter provides multiple implementations, define separate conditions, publish the corresponding properties, and test each option. @ConditionalOnProperty, @ConditionalOnClass, or customizers can be used, but there must be clear rules when multiple conditions match simultaneously.

## 9. Designing a feature switch across multiple beans

In a real feature, an integration may involve multiple beans:

- Client.
- Health indicator.
- Metrics binder.
- Scheduler or listener.
- Cache.
- Retry infrastructure.
- Connection pool.

If all of them only make sense when Catalog is enabled, place them under one shared configuration:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class CatalogEnabledConfiguration {

        // Client, metrics, scheduler, and feature beans.
    }
}
```

If a bean can exist independently, extract it into a separate auto-configuration and document its conditions. For example, IDE metadata hints need no runtime bean; a health indicator should appear only when a client is actually present.

For schedulers, check both task creation and task shutdown. A bean condition on the scheduler alone is insufficient if another singleton or static initializer already spawned a thread earlier.

For listeners, determine whether the listener is registered via a bean, spring.factories, or another API. A listener loaded very early may not share the same lifecycle as beans inside auto-configuration. If disabling the feature must disable the listener, the condition must reside in the corresponding registration mechanism.

## 10. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Adding the starter causes the app to call an external service | Feature enabled by default or bean constructor performs I/O | Use opt-in when appropriate; send requests only when consumers invoke methods |
| App configures no endpoint yet still gets a useless client | Endpoint has a dummy default or overly lax validation | Make endpoint required when enabling default client and fail fast |
| Two beans of the same type exist | Default bean lacks @ConditionalOnMissingBean | Express override rights explicitly by type |
| Custom bean is not used | Condition placed at wrong scope or auto-configuration runs before app beans | Use standard auto-configuration ordering and test with user configuration |
| Client disabled yet scheduler keeps running | Feature condition guards only one bean | Place beans sharing a lifecycle under a common configuration |
| Feature disabled yet properties bean still appears unexpectedly | @EnableConfigurationProperties placed outside guarded configuration | Move annotation inside the conditional region or document the exception |
| Property false removes application-created beans | Confusing starter conditions with whole-ApplicationContext ownership | Condition only starter beans; let the application manage its own beans |
| Enabled=true with missing endpoint raises no error | Code silently falls back or unintentionally defers failure | Validate required settings when creating the default bean |
| Client opens socket during startup | Constructor or factory method performs I/O | Separate object creation from sending requests; use timeouts and clear lifecycle |
| Zero or negative timeout | Properties are not validated | Validate positive values and report the property name |
| Custom client still forced to supply default client's endpoint | Validation placed in a shared layer despite user bean replacing default | Validate only dependencies needed by the selected implementation |
| Disabling does not stop created threads or connections | Side effects live outside bean lifecycle or lack cleanup | Manage resources via lifecycle and close them on context shutdown |

## 11. Design and maintenance workflow

Before releasing an auto-configuration, follow these steps:

1. Clearly document the feature switch: which property enables it, what the default is, and what missing means.
2. List all beans, threads, listeners, schedulers, connection pools, and side effects belonging to the feature.
3. Choose the least impactful default; do not open connections or background tasks if the feature is not enabled.
4. Identify required properties vs. properties with defaults; validate values as soon as the default implementation is created.
5. Publish interfaces or customization hooks that the application can replace.
6. Use @ConditionalOnMissingBean for default beans if overriding is supported.
7. Place conditions around all beans sharing the same lifecycle to avoid half-enabled states.
8. Clarify whether user-owned beans remain when the feature is disabled; normally starters do not remove application beans.
9. Write tests for missing property, false, true, missing configuration, custom beans, and disabled state.
10. Verify there are no network calls or background activity at startup or when the feature is disabled.
11. Verify resources are properly closed when the ApplicationContext shuts down.
12. Read the Condition Evaluation Report whenever behavior diverges from the published policy.

## 12. Self-check questions

**Question 1.** Why should an integration with side effects usually be disabled when the enabled property is missing?

**Answer:** Because adding a dependency does not mean the user wants to open connections, run threads, or send requests. Opt-in reduces unexpected impact and keeps the application in control of the feature.

**Question 2.** What does matchIfMissing=false mean for @ConditionalOnProperty?

**Answer:** If the property does not exist, the condition does not match. This is an explicit way to express default disabled.

**Question 3.** What does @ConditionalOnMissingBean(CatalogClient.class) allow?

**Answer:** When the application already provides a CatalogClient bean, the starter does not create its default implementation.

**Question 4.** Does a disabled property delete beans declared by the application itself?

**Answer:** No. It only prevents the guarded auto-configuration from registering the starter's beans. Application-owned beans remain intact.

**Question 5.** Why should the feature condition be placed on a configuration enclosing both the client and the scheduler?

**Answer:** So beans sharing the same lifecycle are enabled/disabled consistently, avoiding a scheduler or listener continuing to run after the client is disabled.

**Question 6.** When enabled=true but a required endpoint is missing, what should happen?

**Answer:** Fail fast with a message naming the property. Do not silently create a broken client or treat misconfiguration as feature disabled.

**Question 7.** Does a custom client necessarily need to provide the endpoint required by the default client?

**Answer:** No, if the endpoint only serves the default implementation. When a custom bean replaces the default, the application is responsible for whatever configuration its own implementation needs.

**Question 8.** Does creating an HttpClient mean an HTTP request has already been sent?

**Answer:** No. In the example, HttpClient is only built when the feature is enabled; requests are sent only when the consumer calls findById.

## 13. Takeaways

- Choose minimal defaults; for integrations with side effects, prefer opt-in and use matchIfMissing=false.
- Never fabricate endpoints, credentials, or remote actions the user did not request.
- Timeouts and resources must have bounds, valid values, and clear documentation.
- Use public interfaces and @ConditionalOnMissingBean to allow applications to replace default implementations.
- State clearly which properties apply to the default client and which still apply to custom clients.
- Place feature conditions at the right scope so the client, scheduler, listener, metrics, and related resources stay in a consistent state.
- Disabled prevents the starter from registering its beans; it does not remove application-declared beans.
- Separate object initialization from network I/O and background activity.
- Enabled without required configuration must fail fast with actionable error messages.
- Test missing/false/true, overrides, invalid configurations, and application-owned beans.

### Official Documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Spring Boot 3.3 API — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.3 API — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.3 API — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
