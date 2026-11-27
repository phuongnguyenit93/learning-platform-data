# Building a PropertySourceLocator for a Custom Configuration Source

A Spring Cloud application may need to read configuration from an internal system instead of Spring Cloud Config Server. For example, an organization might already have a Configuration API, a tenant configuration service, or a platform-operated configuration store. The application still needs to load these values into the Spring Environment so they can be bound with `@ConfigurationProperties`, read via `Environment`, or injected with `@Value`.

Spring Cloud Commons provides `PropertySourceLocator` as a bootstrap extension point. A locator receives the `Environment` about to be used for the `ApplicationContext`, queries the external configuration source, and returns a `PropertySource`. Spring Cloud adds that `PropertySource` to the `Environment` before application beans are initialized.

This hands-on lab builds a locator that reads configuration from a custom HTTP API. The API accepts an application name and active profiles, authenticates with a bearer token, and returns key-value JSON. The locator converts the JSON into a `MapPropertySource`, validates allowed namespaces, handles timeouts and fail-fast behavior, and supports profile-specific invocations.

This is Spring Cloud's bootstrap mechanism. For new projects aiming to integrate a configuration source directly into Spring Boot's Config Data pipeline, consider `ConfigDataLocationResolver` and `ConfigDataLoader`. This exercise focuses on `PropertySourceLocator` as specified, while highlighting the boundary between the two extension points.

## 1. Expected Outcomes

Upon completing this lab, learners will be able to:

1. Explain the role of `PropertySourceLocator` in the bootstrap context.
2. Design an HTTP contract for a custom configuration service.
3. Create a `PropertySourceLocator` that reads the application name and profiles from `Environment`.
4. Read HTTP configuration and convert JSON into a `MapPropertySource`.
5. Register a bootstrap configuration using `META-INF/spring.factories`.
6. Ensure the locator lives in the bootstrap context and is not accidentally component-scanned.
7. Handle timeouts, HTTP errors, JSON errors, and fail-fast policies.
8. Restrict which property keys an external source is permitted to supply.
9. Understand why a locator can be invoked twice when profiles are used.
10. Verify `PropertySource`, precedence, and binding results in the application.
11. Write tests with a local HTTP server without depending on a live environment.
12. Distinguish `PropertySourceLocator` from the Config Data API and choose the right extension approach.

The final result is an Orders application that can receive payment endpoints, timeouts, and feature flags from a custom configuration API before business beans are created.

## 2. Context and Architecture

### 2.1. Problem Statement

Suppose an organization's platform provides an existing configuration API:

- Each application has its own configuration set.
- Each environment or profile can override shared configuration.
- The API requires a bearer token.
- The response is JSON with flat property keys.
- The application must load configuration before creating DataSources, HTTP clients, or dependent beans.

For example, Orders needs the following configuration:

~~~properties
app.payment.base-url=https://payment-staging.internal
app.payment.timeout=450ms
feature.checkout.enabled=true
~~~

These values are managed in the configuration service. The application does not hard-code staging or production endpoints in the artifact.

### 2.2. Startup Flow

~~~mermaid
flowchart TD
    A[SpringApplication starts] --> B[Bootstrap context]
    B --> C[Load bootstrap properties]
    C --> D[Discover BootstrapConfiguration]
    D --> E[Create PropertySourceLocator]
    E --> F[Read application name and profiles]
    F --> G[Call custom configuration API]
    G --> H[Validate response]
    H --> I[Create MapPropertySource]
    I --> J[Add source to Environment]
    J --> K[Create main ApplicationContext]
    K --> L[Bind ConfigurationProperties]
    L --> M[Application ready]
~~~

The locator runs during the bootstrap phase. It must finish retrieving the configuration source before the main `ApplicationContext` creates beans that depend on those properties.

### 2.3. Component Roles

| Component | Responsibility |
| --- | --- |
| Bootstrap context | Prepares external configuration sources before the main context |
| BootstrapConfiguration | Registers configurations and beans dedicated to bootstrap |
| PropertySourceLocator | Queries and returns a PropertySource |
| Environment | Supplies application name, profiles, and existing property sources |
| MapPropertySource | Inserts loaded key-value pairs into the Environment |
| ConfigurationProperties | Binds configuration into typed objects in the application |
| Custom configuration API | Stores and serves configuration per application/profile |

### 2.4. Responsibility Boundaries

`PropertySourceLocator` is only responsible for locating and returning a property source. It should not:

- Create business beans of the application.
- Initialize the entire `ApplicationContext`.
- Poll configuration continuously on its own.
- Hold a mutable `Environment` instance for use across the entire application lifecycle.
- Write secrets or response bodies containing sensitive data to logs.
- Decide to mutate the bean graph after the main context has initialized.

If you want to update configuration after startup, design a separate refresh mechanism, event broadcast, or runtime configuration provider. Running a locator at bootstrap does not create a continuous synchronization stream.

## 3. Designing the Configuration API Contract

### 3.1. Request

The locator calls the endpoint:

~~~http
GET /v1/config?application=orders-service&profiles=staging HTTP/1.1
Host: config.internal
Accept: application/json
Authorization: Bearer <token>
~~~

Parameters:

| Parameter | Meaning |
| --- | --- |
| application | Value of spring.application.name |
| profiles | Comma-separated list of active profiles |
| Authorization | Bearer token supplied by the deployment environment |

When no active profile is set yet, the locator sends an empty `profiles` parameter so the API returns shared configuration. Once profiles are determined, the locator may be called again with the corresponding profile list.

### 3.2. Successful Response

The API returns HTTP 200 with a JSON object containing flat keys:

~~~json
{
  "app.payment.base-url": "https://payment-staging.internal",
  "app.payment.timeout": "450ms",
  "feature.checkout.enabled": true
}
~~~

Each key is a Spring property. Values may be a String, number, or boolean. Nested structures are outside this lab's contract; if nested configuration is needed, the API should return flat keys using dot notation.

### 3.3. Status Codes

| HTTP status | Meaning | Recommended Behavior |
| --- | --- | --- |
| 200 | Configuration found | Parse and create PropertySource |
| 404 | No configuration for application/profile | Fail or ignore according to fail-fast |
| 401/403 | Invalid token or insufficient permissions | Abort startup |
| 400 | Invalid request | Abort startup |
| 5xx | Configuration service error | Abort startup if configuration is required |
| Timeout/network error | Cannot reach API | Fail-fast or ignore if the source is optional |

Do not return internal details such as tokens, stack traces, or credentials in error responses.

### 3.4. Profile-Based Data Examples

Shared configuration:

~~~json
{
  "app.payment.timeout": "800ms",
  "feature.checkout.enabled": false
}
~~~

Staging configuration:

~~~json
{
  "app.payment.base-url": "https://payment-staging.internal",
  "app.payment.timeout": "450ms",
  "feature.checkout.enabled": true
}
~~~

Production configuration:

~~~json
{
  "app.payment.base-url": "https://payment.internal",
  "app.payment.timeout": "300ms",
  "feature.checkout.enabled": true
}
~~~

The API can merge shared configuration with profile configuration before returning the response. Alternatively, the API can return separate layers and let the locator merge them. In this lab, the API returns a pre-merged map for the requested application/profile.

## 4. Preparing the Project

### 4.1. Platform Versions

Use JDK 17 or later and a compatible Spring Boot/Spring Cloud pair from the release train. Manage Spring Cloud dependencies via the BOM rather than picking individual starter versions manually.

The APIs in this guide use Spring Cloud Context with `PropertySourceLocator` and modern Spring Boot Config Data. If your project uses a different release train, check the Javadoc and reference documentation for that exact version before applying.

### 4.2. Maven Dependencies

Example dependency management section:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>${spring-cloud.version}</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Required dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-json</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-bootstrap</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-cloud-starter-bootstrap` enables the bootstrap infrastructure required for this example. If you do not use the starter, you must enable bootstrap using the mechanism supported by that release train's Spring Cloud documentation.

### 4.3. Directory Structure

Organize the sources as follows:

~~~text
orders-service/
  src/
    main/
      java/
        com/example/orders/
          OrdersApplication.java
          config/
            PaymentProperties.java
            CheckoutFeatureProperties.java
        com/example/bootstrap/
          CustomBootstrapConfiguration.java
          HttpPropertySourceLocator.java
      resources/
        bootstrap.yml
        application.yml
        META-INF/
          spring.factories
    test/
      java/
        com/example/bootstrap/
          HttpPropertySourceLocatorTest.java
~~~

The `bootstrap` package is placed outside `com.example.orders` to prevent it from being discovered by `OrdersApplication` component scanning and registered again in the main context.

## 5. Declaring Bootstrap Configuration

### 5.1. The bootstrap.yml File

Create `src/main/resources/bootstrap.yml`:

~~~yaml
spring:
  application:
    name: orders-service

app:
  config-source:
    enabled: ${CUSTOM_CONFIG_ENABLED:false}
    uri: ${CUSTOM_CONFIG_URI:http://localhost:8099/v1/config}
    token: ${CUSTOM_CONFIG_TOKEN:}
    fail-fast: true
~~~

Properties:

- `spring.application.name` identifies the application for which the API should return configuration.
- `app.config-source.enabled` toggles the locator on or off per environment.
- `app.config-source.uri` is the custom configuration API endpoint.
- `app.config-source.token` receives the bearer token from an environment variable.
- `app.config-source.fail-fast` determines behavior when the API has no configuration or is unreachable.

In local environments, `enabled` defaults to `false` so the application can still start when no mock configuration service is running. In staging/production, the pipeline should enable the config source and supply the token via a secret store.

Do not write real tokens into `bootstrap.yml`, `application.yml`, or the repository.

### 5.2. The application.yml File

Create safe default configuration:

~~~yaml
app:
  payment:
    base-url: https://payment-default.internal
    timeout: 800ms

feature:
  checkout:
    enabled: false
~~~

The custom `PropertySource` may supply keys with the same names. Once the locator is properly registered, the application reads the final values from `Environment` and binds them into objects.

### 5.3. Why Does Application Name Need to Be Available at Bootstrap?

The locator needs to know which service it is loading configuration for. If `spring.application.name` only appears in a source not yet loaded when the locator runs, the API may receive the wrong application or no name at all.

Placing the application name in `bootstrap.yml` ensures it is available during the bootstrap phase. You can use an environment variable if multiple deployments share the same artifact and each deployment has a distinct application name.

## 6. Registering BootstrapConfiguration

### 6.1. Creating the Bootstrap Configuration

Create `com.example.bootstrap.CustomBootstrapConfiguration`:

~~~java
package com.example.bootstrap;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomBootstrapConfiguration {

    @Bean
    PropertySourceLocator httpPropertySourceLocator() {
        return new HttpPropertySourceLocator();
    }
}
~~~

This class is loaded in the bootstrap context. The bean returns a `PropertySourceLocator` for Spring Cloud to invoke while preparing property sources.

### 6.2. Registering via META-INF/spring.factories

Create `src/main/resources/META-INF/spring.factories`:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=com.example.bootstrap.CustomBootstrapConfiguration
~~~

Spring Cloud reads the `BootstrapConfiguration` entries, creates the bootstrap context, and loads the declared configurations. `PropertySourceLocator` is registered inside this context.

### 6.3. Avoiding Accidental Component Scanning

A bootstrap configuration can be scanned into the main context if its package sits underneath the root package of `@SpringBootApplication`.

Example to avoid:

~~~text
com.example.orders/
  OrdersApplication.java
  bootstrap/
    CustomBootstrapConfiguration.java
~~~

If `OrdersApplication` uses default component scanning from `com.example.orders`, the bootstrap class may be scanned a second time.

Recommended layout:

~~~text
com.example/
  bootstrap/
    CustomBootstrapConfiguration.java
  orders/
    OrdersApplication.java
~~~

In large applications, the bootstrap package should be kept separate and verified in integration tests to prevent duplicate bean registration.

## 7. Implementing HttpPropertySourceLocator

### 7.1. Required Imports

Create `com.example.bootstrap.HttpPropertySourceLocator`:

~~~java
package com.example.bootstrap;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;
import org.springframework.util.StringUtils;
~~~

### 7.2. Declaring the Locator

~~~java
@Order(Ordered.LOWEST_PRECEDENCE)
public class HttpPropertySourceLocator implements PropertySourceLocator {

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;

    public HttpPropertySourceLocator() {
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        this.objectMapper = new ObjectMapper();
    }

    @Override
    public PropertySource<?> locate(Environment environment) {
        boolean enabled = environment.getProperty(
                "app.config-source.enabled",
                Boolean.class,
                false
        );

        if (!enabled) {
            return null;
        }

        String endpoint = environment.getProperty(
                "app.config-source.uri"
        );

        if (!StringUtils.hasText(endpoint)) {
            throw new IllegalStateException(
                    "app.config-source.uri must be configured when the source is enabled"
            );
        }

        String application = environment.getProperty(
                "spring.application.name"
        );

        if (!StringUtils.hasText(application)) {
            throw new IllegalStateException(
                    "spring.application.name is required by the custom configuration source"
            );
        }

        String token = environment.getProperty(
                "app.config-source.token"
        );

        if (!StringUtils.hasText(token)) {
            throw new IllegalStateException(
                    "app.config-source.token must be supplied when the source is enabled"
            );
        }

        boolean failFast = environment.getProperty(
                "app.config-source.fail-fast",
                Boolean.class,
                true
        );

        String profiles = String.join(
                ",",
                environment.getActiveProfiles()
        );

        URI requestUri = buildRequestUri(
                endpoint,
                application,
                profiles
        );

        HttpRequest request = HttpRequest.newBuilder(requestUri)
                .timeout(Duration.ofSeconds(3))
                .header("Accept", "application/json")
                .header("Authorization", "Bearer " + token)
                .GET()
                .build();

        return loadPropertySource(
                request,
                application,
                profiles,
                failFast
        );
    }
}
~~~

This is the skeleton of the class. In the following sections, place the helper methods inside `HttpPropertySourceLocator`, before the final closing brace of the class.

The locator performs these steps:

1. Check whether the source is enabled.
2. Read the endpoint, application name, and token.
3. Retrieve active profiles from `Environment`.
4. Build an HTTP request with a timeout.
5. Call the API and convert the response into a `PropertySource`.

When the source is disabled, the locator returns `null`. This signals that the locator does not contribute any property source.

### 7.3. Building the URI by Application and Profiles

Add the following methods to the class:

~~~java
private URI buildRequestUri(
        String endpoint,
        String application,
        String profiles
) {
    String separator = endpoint.contains("?") ? "&" : "?";

    String query = "application="
            + encode(application)
            + "&profiles="
            + encode(profiles);

    return URI.create(endpoint + separator + query);
}

private String encode(String value) {
    return URLEncoder.encode(value, StandardCharsets.UTF_8);
}
~~~

Do not concatenate the application name or profiles directly into the URL without encoding. Values containing spaces, commas, or special characters must be safely encoded in the query string.

### 7.4. Calling the API and Handling the Response

Add the method:

~~~java
private PropertySource<?> loadPropertySource(
        HttpRequest request,
        String application,
        String profiles,
        boolean failFast
) {
    try {
        HttpResponse<String> response = httpClient.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        if (response.statusCode() == 404 && !failFast) {
            return null;
        }

        if (response.statusCode() >= 500 && !failFast) {
            return null;
        }

        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IllegalStateException(
                    "Custom configuration service returned HTTP "
                            + response.statusCode()
            );
        }

        Map<String, Object> values = objectMapper.readValue(
                response.body(),
                new TypeReference<LinkedHashMap<String, Object>>() {
                }
        );

        if (values == null || values.isEmpty()) {
            return null;
        }

        validateValues(values);

        String profilePart = StringUtils.hasText(profiles)
                ? profiles.replace(",", "_")
                : "base";

        String sourceName = "custom-http:"
                + application
                + ":"
                + profilePart;

        Map<String, Object> immutableValues =
                Collections.unmodifiableMap(new LinkedHashMap<>(values));

        return new MapPropertySource(
                sourceName,
                immutableValues
        );
    }
    catch (InterruptedException exception) {
        Thread.currentThread().interrupt();

        throw new IllegalStateException(
                "Interrupted while loading custom configuration",
                exception
        );
    }
    catch (JsonProcessingException exception) {
        throw new IllegalStateException(
                "Custom configuration service returned invalid JSON",
                exception
        );
    }
    catch (IOException exception) {
        if (!failFast) {
            return null;
        }

        throw new IllegalStateException(
                "Could not load custom configuration",
                exception
        );
    }
}
~~~

Several notable decisions:

- Connect timeout and request timeout are bounded.
- 404 can be ignored if the source is optional.
- Any non-2xx HTTP status fails by default; only 404 and 5xx are ignored when `fail-fast=false`.
- When the thread is interrupted, the locator restores the interrupt flag before throwing.
- The response body is excluded from exception messages because it may contain sensitive data.
- The map is wrapped as read-only to prevent modifications to the property source after it is added to `Environment`.

### 7.5. Accepting Only Property Keys in Allowed Namespaces

Add the method:

~~~java
private void validateValues(Map<String, Object> values) {
    for (Map.Entry<String, Object> entry : values.entrySet()) {
        String key = entry.getKey();
        Object value = entry.getValue();

        boolean allowedNamespace = key != null
                && (key.startsWith("app.")
                || key.startsWith("feature."));

        if (!allowedNamespace) {
            throw new IllegalArgumentException(
                    "Custom configuration contains a property outside the allowed namespaces"
            );
        }

        if (value == null
                || value instanceof Map<?, ?>
                || value instanceof List<?>) {
            throw new IllegalArgumentException(
                    "Custom configuration values must be non-null scalar values"
            );
        }
    }
}
~~~

This lab allows the API to provide properties only under `app.*` and `feature.*`. Platform-controlling keys such as `spring.*`, `management.*`, or `server.*` cannot be modified by this API.

This is an important boundary. If an external configuration source could arbitrarily change any property, it could alter profiles, security, management endpoints, or the application's bean graph.

In production systems, the allowlist should be designed around property ownership. Do not rely solely on API authentication to permit arbitrary keys.

## 8. Completing the Orders Application

### 8.1. Main Application

Create `OrdersApplication`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

`ConfigurationPropertiesScan` locates classes annotated with `@ConfigurationProperties` inside the application package.

### 8.2. PaymentProperties

Create the configuration class:

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        String baseUrl,
        Duration timeout
) {
}
~~~

A record fits well because these values are loaded at startup and do not need mutable rebinding in this exercise.

### 8.3. CheckoutFeatureProperties

~~~java
package com.example.orders.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "feature.checkout")
public record CheckoutFeatureProperties(
        boolean enabled
) {
}
~~~

### 8.4. Verifying Bound Configuration

You can create an `ApplicationRunner` that logs only non-sensitive information:

~~~java
package com.example.orders;

import com.example.orders.config.CheckoutFeatureProperties;
import com.example.orders.config.PaymentProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrdersStartupConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(OrdersStartupConfiguration.class);

    @Bean
    ApplicationRunner showConfiguration(
            PaymentProperties payment,
            CheckoutFeatureProperties checkout
    ) {
        return args -> log.info(
                "Payment endpoint configured: {}, timeout: {}, checkout enabled: {}",
                payment.baseUrl(),
                payment.timeout(),
                checkout.enabled()
        );
    }
}
~~~

Do not log bearer tokens, passwords, or the entire `Environment`. The goal of the runner is to confirm that configuration was loaded and bound properly.

## 9. Understanding Ordering and Double Invocation with Profiles

### 9.1. Locator Receives the Environment of the Initializing Application

The `Environment` passed into `locate` is the `Environment` of the `ApplicationContext` for which Spring Cloud is preparing property sources.

The `Environment` already contains the standard property sources provided by Spring Boot. Therefore, the locator can read `spring.application.name`, active profiles, and the bootstrap settings needed to resolve the data source.

### 9.2. Since Spring Cloud 2022.0.3, the Locator Can Be Called Twice

Spring Cloud Commons notes that since version 2022.0.3, `PropertySourceLocators` are invoked twice:

1. First, to fetch property sources when active profiles are not yet set. The configuration source can supply shared data.
2. After the main `ApplicationContext` initializes, the locator is called again with active profiles to fetch profile-specific configuration.

Consequently, implementations must be idempotent and must not assume they are called only once.

For example:

~~~text
Call 1:
application = orders-service
profiles   =

Call 2:
application = orders-service
profiles   = staging
~~~

The `PropertySource` name in the example includes both the application and the profile to distinguish the two loads.

### 9.3. Do Not Store Profiles in Static Fields

Do not use static fields to cache active profiles or responses from a previous call. A locator may be invoked multiple times during the bootstrap lifecycle and may be used in a context hierarchy.

Each `locate` invocation should read the `Environment` passed to it, construct the corresponding request, and return an independent `PropertySource`.

### 9.4. Shared vs. Profile-Specific Sources

The Configuration API may return:

- Shared configuration when `profiles` is empty.
- Additional or overriding configuration when active profiles are present.

In this lab, the API already merges shared and profile-specific configuration into a single map per request. If the API returns two separate layers, you must clearly define precedence and `PropertySource` names so the profile-specific source wins as designed.

### 9.5. Ordering Across Multiple Locators

If an application has multiple `PropertySourceLocator` instances, processing order can be controlled with `@Order` or `Ordered`. This example uses `LOWEST_PRECEDENCE` so the HTTP locator sits at low priority in the locator list.

When multiple sources provide the same key, inspect the actual order of the composite property source in `Environment`. Do not rely solely on source names or declaration order within a single file.

### 9.6. Remote Property Sources and Local Overrides

Property sources added from bootstrap often have high precedence. This can cause values from the external source to override `application.yml` or local files.

Spring Cloud Config has `allowOverride` and related override properties specifically for Config Server's remote property source. Do not assume those flags control this custom locator. For a custom source, define the override policy explicitly and verify it with tests.

## 10. Testing the Locator with a Local HTTP Server

### 10.1. Test Goals

Do not call a live configuration service in unit tests. Use `com.sun.net.httpserver.HttpServer` to create a temporary endpoint on loopback.

Tests should verify that:

- The locator calls the expected path.
- The query includes the application name and profiles.
- The bearer token is sent.
- JSON is converted into a `MapPropertySource`.
- Property keys conform to the allowlist.
- When the source is disabled, the locator returns `null`.
- API errors are handled according to the fail-fast policy.

### 10.2. Testing Successful Configuration Loading

~~~java
package com.example.bootstrap;

import static org.assertj.core.api.Assertions.assertThat;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.core.env.PropertySource;
import org.springframework.mock.env.MockEnvironment;

class HttpPropertySourceLocatorTest {

    @Test
    void loadsPropertiesForApplicationAndProfile() throws IOException {
        AtomicReference<String> query = new AtomicReference<>();
        AtomicReference<String> authorization = new AtomicReference<>();

        String json = """
                {
                  "app.payment.base-url": "https://payment-staging.internal",
                  "app.payment.timeout": "450ms",
                  "feature.checkout.enabled": true
                }
                """;

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0),
                0
        );

        server.createContext("/v1/config", exchange -> {
            query.set(exchange.getRequestURI().getRawQuery());
            authorization.set(
                    exchange.getRequestHeaders().getFirst("Authorization")
            );

            byte[] body = json.getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type",
                    "application/json"
            );

            exchange.sendResponseHeaders(200, body.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
            finally {
                exchange.close();
            }
        });

        server.start();

        try {
            String uri = "http://127.0.0.1:"
                    + server.getAddress().getPort()
                    + "/v1/config";

            MockEnvironment environment = new MockEnvironment()
                    .withProperty("app.config-source.enabled", "true")
                    .withProperty("app.config-source.uri", uri)
                    .withProperty("app.config-source.token", "test-token")
                    .withProperty("app.config-source.fail-fast", "true")
                    .withProperty("spring.application.name", "orders-service");

            environment.setActiveProfiles("staging");

            HttpPropertySourceLocator locator =
                    new HttpPropertySourceLocator();

            PropertySource<?> source = locator.locate(environment);

            assertThat(source).isNotNull();

            assertThat(source.getProperty("app.payment.base-url"))
                    .isEqualTo("https://payment-staging.internal");

            assertThat(source.getProperty("app.payment.timeout"))
                    .isEqualTo("450ms");

            assertThat(source.getProperty("feature.checkout.enabled"))
                    .isEqualTo(true);

            assertThat(query.get())
                    .contains("application=orders-service")
                    .contains("profiles=staging");

            assertThat(authorization.get())
                    .isEqualTo("Bearer test-token");
        }
        finally {
            server.stop(0);
        }
    }
}
~~~

The test uses a dynamic port to avoid port conflicts. The token is a dummy test value and must not be used in real environments.

### 10.3. Testing Disabled Source

~~~java
@Test
void returnsNullWhenSourceIsDisabled() {
    MockEnvironment environment = new MockEnvironment()
            .withProperty("app.config-source.enabled", "false");

    HttpPropertySourceLocator locator =
            new HttpPropertySourceLocator();

    assertThat(locator.locate(environment)).isNull();
}
~~~

When disabled, the locator does not require a URI, token, or HTTP server.

### 10.4. Testing Profile Changes Between Two Calls

Create a test with the HTTP server that records the query string. Call the locator the first time with no active profile. Then call:

~~~java
environment.setActiveProfiles("staging");
~~~

Call the locator a second time and verify that the query contains `profiles=staging`.

This test simulates the locator being invoked again after active profiles have been determined. Do not use a static cache to retain the first call's result.

### 10.5. Testing Disallowed Property Keys

Have the HTTP server return the response:

~~~json
{
  "app.payment.timeout": "450ms",
  "spring.datasource.password": "not-allowed"
}
~~~

Expect the locator to throw `IllegalArgumentException` because the response contains a key outside the allowed namespaces.

This test verifies that HTTP authentication does not grant a configuration source permission to overwrite arbitrary properties.

### 10.6. Testing HTTP Errors and Fail-Fast

Write cases for:

- HTTP 404 with `fail-fast=true`: startup must fail.
- HTTP 404 with `fail-fast=false`: locator returns `null`.
- HTTP 401/403: always fail with an authentication error.
- HTTP 500: fail if `fail-fast=true`; return `null` if the source is optional and `fail-fast=false`.
- Timeout or connection refused with `fail-fast=true`: startup fails.
- Timeout or connection refused with `fail-fast=false`: locator skips the source if policy allows.

Malformed JSON or property keys outside the allowlist should always cause the locator to fail. Do not use `fail-fast=false` to mask 401/403 errors or contract-violating responses.

## 11. Verifying Application Integration

### 11.1. Enabling the Bootstrap Source Locally

In PowerShell:

~~~powershell
$env:CUSTOM_CONFIG_ENABLED = "true"
$env:CUSTOM_CONFIG_URI = "http://localhost:8099/v1/config"
$env:CUSTOM_CONFIG_TOKEN = "local-test-token"
~~~

Start the test configuration API on port 8099 and then run `OrdersApplication`.

If the API is not running and `fail-fast=true`, the application must abort startup. This is the expected behavior when configuration is required.

### 11.2. Inspecting the Environment

In an integration test or debugger, read:

~~~java
environment.getProperty("app.payment.base-url");
environment.getProperty("app.payment.timeout");
environment.getProperty("feature.checkout.enabled");
~~~

Confirm that the values come from the custom source.

You can inspect the list of `PropertySource` entries:

~~~java
environment.getPropertySources().forEach(source ->
        System.out.println(source.getName())
);
~~~

Print only source names in diagnostic logs. Do not print all property values because configuration sources may contain sensitive information.

### 11.3. Verifying ConfigurationProperties

Inject `PaymentProperties` and `CheckoutFeatureProperties` and verify:

- `baseUrl` matches the response.
- `timeout` converts to `Duration`.
- `enabled` converts to `boolean`.

If `Environment` holds the right values but the bean receives different ones, check property source precedence, prefix, property names, and binding timing.

### 11.4. Testing Bootstrap Registration

If the locator unit tests pass but the application does not contain the custom `PropertySource`, check:

1. `spring-cloud-starter-bootstrap` is on the classpath.
2. The `BootstrapConfiguration` key in `spring.factories` is exact.
3. The file is located at `META-INF/spring.factories` inside the artifact.
4. The bootstrap package is not accidentally component-scanned.
5. `spring.cloud.bootstrap.enabled` is not disabled.
6. `app.config-source.enabled` is `true`.
7. `bootstrap.yml` is packaged and read properly.
8. `spring.application.name` has a value before the locator runs.

### 11.5. Inspecting JAR Contents

After building, verify the artifact contains these files:

~~~text
BOOT-INF/classes/bootstrap.yml
BOOT-INF/classes/META-INF/spring.factories
BOOT-INF/classes/com/example/bootstrap/CustomBootstrapConfiguration.class
BOOT-INF/classes/com/example/bootstrap/HttpPropertySourceLocator.class
~~~

If `META-INF/spring.factories` is missing or has a misspelled key, the bootstrap configuration will not be discovered.

## 12. PropertySource Ordering and Precedence Diagnostics

### 12.1. PropertySource Is Not a Standalone Map

`Environment` contains multiple `PropertySource` entries. When `getProperty` is called, Spring searches for the key in precedence order. If multiple sources define the same key, the higher-precedence source determines the effective value.

Example:

| Source | app.payment.timeout |
| --- | --- |
| Command line | 900ms |
| Custom bootstrap source | 450ms |
| application.yml | 800ms |

The actual value depends on the order of sources in `Environment` and bootstrap override rules. Do not infer precedence solely from the fact that a source is fetched remotely.

### 12.2. Avoid Duplicating the Same Key Across Locations Unnecessarily

If the custom source owns the endpoint and timeout, avoid redeclaring those keys across many sources. Default configuration can serve local runs, while deployment environments supply real values.

When local overrides are needed, define a clear policy and test both local and production configurations.

### 12.3. Recording the Source Name

Source names in this guide look like:

~~~text
custom-http:orders-service:base
custom-http:orders-service:staging
~~~

These names help identify the source and profile when inspecting `Environment`. Do not include tokens or secret data in the source name.

### 12.4. Ordering Multiple Locators

When multiple locators exist, annotate with `@Order` or implement `Ordered`. Then inspect the composite `PropertySource` to confirm which source wins on key collisions.

If one locator provides defaults and another provides overrides, design the order deliberately. Do not reuse the same source name for sources with different semantics.

## 13. Security and Reliability

### 13.1. Protecting the Token

Tokens should be supplied via environment variables or a secret manager. Do not commit tokens to Git, bake tokens into images, or pass tokens on the command line whenever avoidable.

Use HTTPS for HTTP requests in real environments. Do not disable certificate validation to work around TLS errors.

### 13.2. Never Log Secrets or Response Bodies

Do not log:

- Authorization headers.
- Bearer tokens.
- Passwords or private keys.
- Full JSON responses.
- The entire `Environment`.
- Exception messages returned by the server if they might contain sensitive data.

Logs should include the application name, profile, source name, call duration, and status code. Never record the token.

### 13.3. Restricting Property Namespaces

The `app.*` and `feature.*` allowlist limits the blast radius of the custom source. Before permitting additional properties, review each group and test its impact on bootstrap, security, and bean creation.

Do not allow the configuration service to arbitrarily modify `spring.profiles.active`, `spring.main.*`, `management.*`, or security properties without a corresponding governance workflow.

An allowlist restricts key scope; it does not turn the API into a secret manager. Do not serve passwords or private keys through a general configuration endpoint; use Vault or a dedicated secret manager. If a system has a valid reason to distribute credentials via this API, enforce dedicated permissions, TLS, auditing, rotation, and appropriate masking rules.

### 13.4. Timeouts and Retries

The locator runs during startup. A request without a timeout can stall a deployment indefinitely.

This lab uses:

- 2-second connect timeout.
- 3-second request timeout.
- No unbounded retry loops.

If retries are required, use a finite attempt count, backoff, and an overall deadline. Bootstrap duration must fit within the deployment platform's startup budget.

### 13.5. Fail-Fast vs. Optional

Use `fail-fast=true` when the configuration is required for safe application operation. Use optional when the source is truly supplemental and the application has valid defaults.

Never treat authentication errors or schema-invalid responses as optional. Doing so could allow the application to start with wrong configuration unnoticed.

### 13.6. Caching and Consistency

If the API uses caching, cache keys must include both `application` and `profiles`. Do not share a single response across different services or environments.

If configuration versioning exists, return revision metadata in a response header or a dedicated allowlisted property. You can log the revision for auditing without logging the full payload.

### 13.7. Multiple Replicas

Each replica may call the custom API at startup. The API must tolerate bursts during rollouts or autoscaling. Consider server-side caching, reasonable rate limits, and concurrent request capacity.

`PropertySourceLocator` does not automatically synchronize replicas after startup. When configuration changes, you need an appropriate deployment or broadcast mechanism.

## 14. When to Use the Config Data API Instead of PropertySourceLocator?

### 14.1. PropertySourceLocator Belongs to Bootstrap Extensions

`PropertySourceLocator` is registered in the bootstrap context via `BootstrapConfiguration` and `spring.factories`. It fits when an application uses the Spring Cloud bootstrap model and needs to inject a configuration source into `Environment` during the bootstrap phase.

### 14.2. The Config Data API Is Spring Boot's Extension Point

Since Spring Boot 2.4, the Config Data API provides two key interfaces:

- `ConfigDataLocationResolver`: resolves locations declared by the application into one or more resources.
- `ConfigDataLoader`: loads resources into `ConfigData` for Spring Boot to add to `Environment`.

For example, the application declares:

~~~yaml
spring:
  config:
    import: customconfig:https://config.internal/orders
~~~

The resolver recognizes the `customconfig:` prefix and identifies the resource; the loader queries the configuration source and returns `ConfigData`.

### 14.3. Comparing the Two Approaches

| Criterion | PropertySourceLocator | Config Data API |
| --- | --- | --- |
| Lifecycle owner | Spring Cloud bootstrap | Spring Boot Config Data |
| Registration mechanism | BootstrapConfiguration in spring.factories | Resolver/loader in spring.factories |
| Activation mechanism | Bootstrap infrastructure | spring.config.import |
| Profile-specific loading | Locator may be re-invoked with active profiles depending on version | Resolver supports resolveProfileSpecific |
| Optional location | Custom locator policy | Built-in optional: support in Config Data |
| Configuration origin | Custom metadata required | Integrated with Config Data origin/resource model |
| Best fit | Integrating with existing bootstrap model | Custom locations for modern Boot applications |

### 14.4. Do Not Mix Both Mechanisms Arbitrarily

Do not register the same configuration source via both `PropertySourceLocator` and `ConfigDataLoader` without clear rules. Two sources providing the same keys can produce confusing precedence behavior.

If the current module already relies on Spring Cloud bootstrap and the task calls for `PropertySourceLocator`, complete it using the bootstrap model. For a new custom config location in a modern Spring Boot application, evaluate the Config Data API before choosing bootstrap.

## 15. Extending the Lab

### 15.1. Supporting Profile-Specific API Responses

Update the mock server to return different responses based on `profiles`. Test both the profile-less call and the `staging` call. Verify the source name and final effective values.

### 15.2. Supporting Revisions

Add an `X-Config-Revision` header to the response. The locator can read the header and populate a non-sensitive metadata property, such as `app.config-source.revision`.

Do not place tokens or authentication details into the revision value.

### 15.3. Supporting ETag

The Configuration API can return an `ETag`. The locator can send `If-None-Match` if a valid cache entry exists within the same lifecycle.

With a bootstrap locator, caching must be designed carefully because the locator may be called twice for profiles. Do not reuse a base configuration `ETag` for a profile-specific response.

### 15.4. Supporting Multiple Tenants

If a single process serves multiple tenants, do not use a `PropertySourceLocator` to load a single tenant-specific config and assume every request shares it. `PropertySource` entries in `Environment` are typically application/context-level configuration.

Request-varying tenant configuration should be managed by a dedicated tenant configuration provider with per-tenant cache keys and policies.

### 15.5. Supporting Multiple Sources

You can build multiple locators for:

- Platform defaults.
- Application settings.
- Feature flags.

Each locator has its own source name and explicit order. When sources declare overlapping keys, precedence tests must prove the expected outcome.

### 15.6. Adding Contract Validation

You can use a schema version or response version to verify compatibility. For example, the API returns an `X-Config-Schema-Version` header. The locator rejects incompatible responses instead of binding malformed keys.

## 16. Common Errors

| Symptom | Possible Cause | Troubleshooting Direction |
| --- | --- | --- |
| Locator is never called | Bootstrap starter missing or bootstrap disabled | Check dependencies and bootstrap enabled flag |
| Custom PropertySource missing | Wrong key in spring.factories or wrong package | Inspect META-INF/spring.factories in the JAR |
| spring.application.name is empty | Declared only in a source loaded after bootstrap | Place it in bootstrap.yml or an early environment variable |
| API receives wrong profile | Locator uses default profile or static cache | Read active profiles from Environment on every locate call |
| API is called twice | Spring Cloud since 2022.0.3 calls in two profile phases | Make locator idempotent and scope source names by profile |
| Bean does not receive remote value | Wrong PropertySource precedence or prefix | Check Environment and ConfigurationProperties |
| Local value always wins | Custom source has lower precedence than another source | Check locator ordering and PropertySource order |
| 401/403 | Missing/expired token or wrong policy | Supply a valid token and verify permissions |
| Startup hangs when API fails | HTTP request has no timeout | Configure finite connect/request timeouts |
| JSON parse error | API returns HTML, array, or invalid schema | Check Content-Type and response contract |
| Property fails to bind | Key does not match prefix or type conversion fails | Verify key names and data types |
| One source alters system properties | Missing allowlist | Restrict namespaces and reject sensitive keys |
| Test depends on a real server | Test does not isolate HTTP | Use local HttpServer with a dynamic port |
| Locator created twice in main context | Bootstrap package was component-scanned | Move bootstrap package outside application scan |
| Replicas use different configs | Source changed between startups | Use immutable revisions and audit config revisions |
| Post-startup changes not reflected | Locator only loads config at bootstrap | Design separate refresh/broadcast or restart mechanism |

## 17. Lab Completion Checklist

### Bootstrap integration

- [ ] `spring-cloud-starter-bootstrap` dependency is present.
- [ ] `BootstrapConfiguration` is registered in `spring.factories`.
- [ ] Bootstrap package sits outside the application's component scan.
- [ ] `spring.application.name` is available before the locator runs.
- [ ] Locator returns `null` when the source is disabled.
- [ ] Locator reads `Environment` on every invocation.

### HTTP source

- [ ] Request includes `application` and `profiles`.
- [ ] Query parameters are URL-encoded.
- [ ] Bearer token is obtained from secret/environment.
- [ ] Connect timeout and request timeout are finite.
- [ ] JSON is parsed into a key-value map.
- [ ] Property keys are validated against the allowlist.
- [ ] Response bodies and tokens are never logged.
- [ ] Fail-fast policy is tested.

### Profiles and precedence

- [ ] Tested invocation without profiles.
- [ ] Tested invocation with profiles.
- [ ] Locator uses no static cache.
- [ ] `PropertySource` name distinguishes application/profile.
- [ ] Ordering among multiple locators is defined.
- [ ] Final effective values are verified in `Environment`.

### Testing and operations

- [ ] Unit tests use a local HTTP server.
- [ ] Disabled source is tested.
- [ ] Success path and bearer token are tested.
- [ ] Keys outside the allowlist are tested.
- [ ] 404, 401/403, and 5xx are tested.
- [ ] Timeout and fail-fast are tested.
- [ ] Integration test verifies `ConfigurationProperties` binding.
- [ ] Artifact contains `bootstrap.yml` and `spring.factories`.
- [ ] Production uses HTTPS and a secret manager.
- [ ] A plan exists for post-startup configuration updates.

## 18. Practice Exercises

**Exercise 1 — Simple PropertySource.** Write a locator that returns a `MapPropertySource` with a fixed property. Verify `Environment` reads the key.

**Exercise 2 — Application-aware source.** Read `spring.application.name` and return different configurations for `orders-service` and `inventory-service`.

**Exercise 3 — Profile-aware source.** Read active profiles and return different timeouts for `local`, `staging`, and `production`.

**Exercise 4 — HTTP source.** Implement `HttpPropertySourceLocator` calling a mock HTTP API, parsing JSON, and returning a `MapPropertySource`.

**Exercise 5 — Authentication.** Send a bearer token from an environment variable. Test missing, valid, and invalid tokens.

**Exercise 6 — Fail-fast.** Simulate 404, 401, and 503. Identify which cases can be skipped and which must abort startup.

**Exercise 7 — Property allowlist.** Have the API return `spring.datasource.password`. Confirm the locator rejects this key.

**Exercise 8 — Double locate invocation.** Invoke the locator without profiles and then invoke it again with `staging`. Confirm both requests receive the expected query parameters.

**Exercise 9 — Precedence.** Define `app.payment.timeout` in both `application.yml` and the custom source. Observe the effective value and explain the `PropertySource` order.

**Exercise 10 — Config Data API.** Create a separate experiment with `ConfigDataLocationResolver` and `ConfigDataLoader` for the `customconfig:` prefix. Compare activation and profile handling with `PropertySourceLocator`.

**Exercise 11 — Multiple locators.** Create two locators for platform defaults and application settings. Use `@Order` and verify which source wins when both declare the same key.

**Exercise 12 — Revision and rollout.** Add a config revision to the response. Log the revision at startup, deploy two replicas, and confirm both use the same revision.

## 19. Key Takeaways and Reference Sources

- `PropertySourceLocator` is a Spring Cloud bootstrap extension point for discovering property sources for `Environment`.
- The locator receives the `Environment` of the `ApplicationContext` being created and can read the application name, profiles, and existing properties.
- Register locators via `BootstrapConfiguration` in `META-INF/spring.factories`.
- Keep the bootstrap package outside the main application's component scan.
- Since Spring Cloud 2022.0.3, `PropertySourceLocators` are invoked twice: before active profiles are resolved and after profiles are determined.
- Locators should be idempotent, avoid static caching, and generate source names that distinguish application and profile.
- `MapPropertySource` is well suited for inserting key-value maps into `Environment`.
- External configuration sources require clear timeouts, authentication, allowlists, error policies, and fail-fast rules.
- Never log bearer tokens, sensitive response bodies, or the entire `Environment`.
- `PropertySourceLocator` loads configuration during bootstrap; it does not poll or synchronize replicas after startup.
- For new custom config locations in Spring Boot, consider `ConfigDataLocationResolver` and `ConfigDataLoader` activated via `spring.config.import`.
- Verify the exact Spring Boot/Spring Cloud release train and documentation for the version in use.

Official sources:

1. [Spring Cloud Commons 5.0.4 – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
2. [Spring Cloud Commons – PropertySourceLocator API](https://docs.spring.io/spring-cloud-commons/reference/)
3. [Spring Cloud Commons – BootstrapConfiguration and PropertySourceLocator source](https://github.com/spring-cloud/spring-cloud-commons/tree/main/spring-cloud-context)
4. [Spring Boot 4.1 – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
5. [Spring Boot – ConfigDataLocationResolver API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/config/ConfigDataLocationResolver.html)
6. [Spring Boot – ConfigDataLoader API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/config/ConfigDataLoader.html)
7. [Spring Cloud – Release train and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
