# Building a Sample Application with an External Service Configuration Group — Spring Boot 3.3

## 1. Practice Objectives

This practice builds a **Spring Boot 3.3 / Java 17 / Maven** application responsible for calling an **external Catalog service** over HTTP. The application must read all connection details from externalized configuration instead of hard-coding them in the service:

- Partner base URL.
- API key used in the request header.
- Connection timeout and read timeout.
- Integration enable/disable flag.
- How to override values when deploying to local, staging, and production.

Example configuration group:

```yaml
integrations:
  catalog:
    base-url: "http://localhost:9091"
    enabled: true
    auth:
      api-key: "..."              # do not commit real keys to Git
    timeouts:
      connect: 2s
      read: 5s
```

Once completed, the request flow is:

```text
GET http://localhost:8080/demo/products/p-100
              |
              v
     CatalogController
              |
              v
       CatalogClient
              |
              v
     Configured RestClient
     - baseUrl
     - X-Api-Key
     - connect timeout
     - read timeout
              |
              v
GET http://localhost:9091/products/p-100
              |
              v
        JSON ProductDto
              |
              v
  Return result to HTTP caller
```

Here, `CatalogClient` and `RestClient` are Spring-managed components; the connection data is encapsulated in an immutable `CatalogProperties` bean.

**Learning outcomes:** know how to design a nested property group, register and validate `@ConfigurationProperties`, build an outbound client decoupled from the controller, use environment/profile/secret mechanisms to vary values per deployment, and write tests without sending requests to a real external service.

All hosts, API keys, and product data in this lab are **simulated**. Do not use real endpoints or production credentials in examples.

## 2. Why Group Connection Configuration Together?

A common initial approach looks like this:

```java
@Service
public class OldCatalogService {

    private static final String BASE_URL =
            "https://partner.example.internal";
    private static final String API_KEY = "example-key";

    // Make HTTP calls using URLs and tokens written directly in code
}
```

This approach causes several problems:

1. Changing the URL between local/staging/prod requires editing or rebuilding code.
2. API keys can easily leak into source control, Docker images, or logs.
3. Timeouts are hard to tune for each environment's network latency.
4. There is no single place to validate required values.
5. Tests have to modify code or use hacks to swap the partner address.
6. When integrating multiple services, dozens of `@Value` annotations scattered across services become difficult to manage.

A better approach is to define a **configuration contract**:

```text
integrations.catalog
    ├── base-url
    ├── enabled
    ├── auth
    │   └── api-key
    └── timeouts
        ├── connect
        └── read
```

Each field belongs to one group and one Java type; the Spring Boot Binder binds values from `application.yaml`, environment variables, JVM properties, CLI arguments, Config Data imports, or other appropriate PropertySources.

### 2.1. Separating Configuration Data from Behavior

`CatalogProperties` should only describe connection settings, constraints, and defaults. It must **not** open sockets, create threads, make HTTP calls, or inject other services.

`CatalogClientConfiguration` creates the `RestClient` from the properties; `CatalogClient` calls the upstream service; `CatalogController` handles internal inbound requests.

This separation makes it possible to test each piece independently of any specific deployment environment.

## 3. Technologies and Versions

Sample tech stack:

| Component | Usage |
| --- | --- |
| Java | 17 or higher, compatible with Spring Boot 3.3 |
| Spring Boot | 3.3.x line |
| Spring Framework | 6.1 line managed by Boot 3.3 |
| Maven | Maven Wrapper if generated with Spring Initializr |
| HTTP inbound | `spring-boot-starter-web` (Spring MVC) |
| HTTP outbound | `RestClient` — blocking API |
| Binding | `@ConfigurationProperties` + `@ConfigurationPropertiesScan` |
| Validation | `spring-boot-starter-validation` |
| IDE Metadata | `spring-boot-configuration-processor` |
| Testing | `spring-boot-starter-test`, JUnit 5, AssertJ, mock HTTP |

This lab uses `RestClient` because it is a blocking Spring MVC application. If a project uses the reactive stack/WebFlux and requires non-blocking I/O, `WebClient` can be used instead; do not arbitrarily swap in WebClient in this sample without a need.

**Version note:** the sample POM below uses Spring Boot `3.3.13`, a patch in the 3.3 line shown on the 3.3 reference documentation page. For real projects, use a patch version aligned with your organization's policy, artifact repository, and security updates; do not manually mix Spring Framework dependency versions from another line.

## 4. Creating the Project with Spring Initializr

You can generate the project from https://start.spring.io with these selections:

```text
Project: Maven
Language: Java
Spring Boot: 3.3.x (if this option is still offered)
Group: com.example
Artifact: catalog-demo
Name: catalog-demo
Package: com.example.catalogdemo
Packaging: Jar
Java: 17

Dependencies:
- Spring Web
- Validation
- Spring Boot Actuator (optional)
- Spring Configuration Processor
- Spring Boot Starter Test
```

If Initializr only offers newer releases, generate a Java/Maven skeleton and set the parent version in the POM according to this lab's Spring Boot 3.3 policy. Do not assume the newest template matches 3.3 syntax/behavior out of the box.

### 4.1. Sample pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>catalog-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>catalog-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The Maven parent manages the versions of the Spring starters, Jakarta Validation, Jackson, JUnit, and the corresponding Spring Framework release. You do not need to declare the `spring-web` version manually.

If you use Java 21 instead of Java 17, still verify compatibility across all project libraries; this lab chooses Java 17 for clarity.

### 4.2. Role of Each Dependency

- `starter-web`: inbound Spring MVC, Jackson JSON serialization, and the `RestClient` API via `spring-web`.
- `starter-validation`: Jakarta Bean Validation provider, enabling `@Validated` and constraint annotations.
- `starter-test`: JUnit Jupiter, AssertJ, Spring Boot test utilities, and Spring HTTP mock testing.
- `configuration-processor`: generates `META-INF/spring-configuration-metadata.json` for IDEs. **It is not a required dependency for the Binder to work at runtime.**

## 5. Project Directory Structure

```text
catalog-demo/
├── pom.xml
├── .gitignore
├── mvnw
├── mvnw.cmd
└── src/
    ├── main/
    │   ├── java/com/example/catalogdemo/
    │   │   ├── CatalogDemoApplication.java
    │   │   ├── config/
    │   │   │   ├── CatalogProperties.java
    │   │   │   └── CatalogClientConfiguration.java
    │   │   ├── catalog/
    │   │   │   ├── ProductDto.java
    │   │   │   ├── CatalogClient.java
    │   │   │   ├── CatalogController.java
    │   │   │   └── CatalogErrorHandler.java
    │   └── resources/
    │       ├── application.yaml
    │       └── application-prod.yaml
    └── test/
        └── java/com/example/catalogdemo/
            ├── config/CatalogPropertiesTest.java
            └── catalog/CatalogClientTest.java

mock_catalog.py             # optional, local fake upstream
```

You could place the classes in fewer files, but splitting them as shown organizes code by responsibility: `config` holds only configuration and the HTTP factory, while `catalog` holds the business operations.

**Package convention:** the main application class `com.example.catalogdemo` is the parent of the subpackages; this allows `@ConfigurationPropertiesScan` and component scanning to discover the sample components.

## 6. Creating the Spring Boot Application

File:

```text
src/main/java/com/example/catalogdemo/CatalogDemoApplication.java
```

Content:

```java
package com.example.catalogdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogDemoApplication.class, args);
    }
}
```

`@SpringBootApplication` enables auto-configuration, component scanning, and core configuration. `@ConfigurationPropertiesScan` discovers classes annotated with `@ConfigurationProperties` in the application's package and subpackages.

**Do not mark `CatalogProperties` as `@Component` in this record constructor-binding model.** Spring Boot 3.3 expects constructor-bound configuration properties to be registered via configuration properties scanning or `@EnableConfigurationProperties`; do not instantiate the record via a regular `@Bean` method and expect identical constructor binding behavior.

If you use `@EnableConfigurationProperties(CatalogProperties.class)` instead of scanning, pick only one primary registration approach in the project to avoid confusion.

## 7. Immutable Configuration Model: CatalogProperties

File:

```text
src/main/java/com/example/catalogdemo/config/CatalogProperties.java
```

Content:

```java
package com.example.catalogdemo.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "integrations.catalog")
public record CatalogProperties(
        @NotNull URI baseUrl,
        @DefaultValue("true") boolean enabled,
        @Valid @NotNull Auth auth,
        @Valid @NotNull Timeouts timeouts) {

    public record Auth(
            @NotBlank String apiKey) {
    }

    public record Timeouts(
            @NotNull @DefaultValue("2s") Duration connect,
            @NotNull @DefaultValue("5s") Duration read) {
    }
}
```

### 7.1. Java Types Explained

| Canonical property | Java component | Meaning |
| --- | --- | --- |
| `integrations.catalog.base-url` | `URI baseUrl` | Base address of the external service |
| `integrations.catalog.enabled` | `boolean enabled` | Whether the integration is enabled |
| `integrations.catalog.auth.api-key` | `Auth.apiKey` (String) | API key for requests |
| `integrations.catalog.timeouts.connect` | `Timeouts.connect` (Duration) | Wait time to establish a connection |
| `integrations.catalog.timeouts.read` | `Timeouts.read` (Duration) | Wait time to read data from the server |

Using `URI` instead of `String` separates basic address syntax checking from the HTTP client. However, a syntactically valid URI **does not guarantee** an `http/https` scheme or a reachable host; if you need those constraints, add custom validation or checks when initializing the client.

Use `Duration` for timeouts so configuration can clearly express `500ms`, `2s`, `1m`. Avoid storing every timeout as an `int` without an explicit unit.

### 7.2. Record Constructor Binding

A record has a canonical constructor, so Spring Boot 3.3 can bind by component names. No setters are needed; the object is created immutable at the reference level.

`@DefaultValue("true")` and `@DefaultValue("2s")` provide defaults at the **binding constructor** if the child field has no property value. This differs from `defaultValue` metadata, which is only for IDEs.

**Important nuance:** If the entire `timeouts` group is omitted, the nested `Timeouts` record may be `null`; `@DefaultValue` on nested components does not necessarily cause the nested group itself to be instantiated. In this example, `@NotNull` on `timeouts` turns a missing group into a clear error when Bean Validation is active.

### 7.3. Validation

- `@Validated` instructs Spring Boot to apply Bean Validation to the configuration properties bean.
- `@NotNull` prevents missing `baseUrl`, `auth`, or `timeouts`.
- `@NotBlank` rejects a null, empty, or whitespace-only API key.
- `@Valid` cascades validation into the nested `Auth` and `Timeouts` records.

If no Bean Validation provider is on the classpath, constraints may not run as expected. That is why `spring-boot-starter-validation` was added to the POM.

**Warning:** `@NotNull` on `Duration` does not forbid `0s` or negative durations. An HTTP client may interpret zero as an *infinite timeout*; add a positive-duration check if that is your operational contract, for example with a custom Bean Validation constraint or an explicit check in the bean factory.

### 7.4. Keep HTTP Logic Out of the Record

Wrong responsibility:

```java
public record CatalogProperties(...) {
    public ProductDto fetchProduct(...) {
        // Making HTTP calls inside an object meant only for configuration
    }
}
```

Right responsibility:

```text
CatalogProperties (data)
       |
       v
CatalogClientConfiguration (builds client)
       |
       v
CatalogClient (makes HTTP calls)
       |
       v
CatalogController (inbound HTTP)
```

This keeps the configuration class easy to test, avoids side effects during binding, and prevents forcing the binder to inject services into the constructor.

## 8. Declaring Default Configuration in application.yaml

File:

```text
src/main/resources/application.yaml
```

Content:

```yaml
server:
  port: 8080

spring:
  application:
    name: catalog-demo

integrations:
  catalog:
    base-url: "http://127.0.0.1:9091"
    enabled: true
    auth:
      api-key: "${CATALOG_API_KEY:}"
    timeouts:
      connect: 2s
      read: 5s
```

**Why does the API key use a placeholder?** The real value does not belong in a version-controlled file; it is supplied via the `CATALOG_API_KEY` environment variable. If the env var is absent, the placeholder defaults to an empty string, and `@NotBlank` causes the application to **fail fast** when the configuration bean is created.

This policy fits a lab that **always requires a key at service startup**, even locally (using a dummy key). Another approach is to omit `auth.api-key` from YAML and supply the canonical env var `INTEGRATIONS_CATALOG_AUTH_APIKEY` directly.

### 8.1. Two Ways to Supply the Key

**Option A — Alias variable referenced in YAML:**

```bash
CATALOG_API_KEY=local-demo-key
```

Corresponding placeholder:

```yaml
api-key: "${CATALOG_API_KEY:}"
```

**Option B — OS env matching the canonical property:**

```bash
INTEGRATIONS_CATALOG_AUTH_APIKEY=local-demo-key
```

Option B typically overrides the Config Data property directly according to Spring Boot's PropertySource order. You do not need to set both variables or store a duplicate copy in a file unless explicitly required.

**Canonical env var naming rule:**

```text
integrations.catalog.auth.api-key
  -> INTEGRATIONS_CATALOG_AUTH_APIKEY
```

Replace dots with underscores, remove dashes, and convert to uppercase. `INTEGRATIONS_CATALOG_AUTH_API_KEY` is not the canonical transformation recommended by Boot 3.3.

### 8.2. Never Put Production API Keys in Git

Avoid doing this:

```yaml
integrations:
  catalog:
    auth:
      api-key: "real-production-secret"
```

Even in a private repository, secrets can persist in Git history, build artifacts, CI logs, deployment copies, or backups. Use an organization-approved secret delivery mechanism, such as environment injection from a Secret manager or a secret volume + Config Data `configtree:`.

## 9. Config Data and Environment Overrides

Spring Boot has a default PropertySource order: Config Data (application files) has lower precedence than OS environment variables, and OS environment variables have lower precedence than JVM system properties and command-line arguments across the corresponding sources.

File example:

```properties
integrations.catalog.timeouts.read=5s
```

Environment:

```bash
INTEGRATIONS_CATALOG_TIMEOUTS_READ=8s
```

The bound result will typically be **8 seconds** if no higher-precedence source overrides it.

In Spring Boot 3.3:

- `integrations.catalog.timeouts.read` → `INTEGRATIONS_CATALOG_TIMEOUTS_READ`.
- `integrations.catalog.base-url` → `INTEGRATIONS_CATALOG_BASEURL`.
- `integrations.catalog.enabled` → `INTEGRATIONS_CATALOG_ENABLED`.
- `integrations.catalog.auth.api-key` → `INTEGRATIONS_CATALOG_AUTH_APIKEY`.

### 9.1. Production Run Example

```bash
CATALOG_API_KEY=... \
INTEGRATIONS_CATALOG_BASEURL=https://catalog.partner.example \
INTEGRATIONS_CATALOG_TIMEOUTS_CONNECT=3s \
INTEGRATIONS_CATALOG_TIMEOUTS_READ=8s \
java -jar target/catalog-demo-0.0.1-SNAPSHOT.jar
```

The ellipsis represents the secret; this command merely **illustrates which variables must be provided**, not a recommendation to put real secrets into shell history. In production, use an appropriate secret provisioning system and runtime environment.

### 9.2. Profile-Specific Configuration

You can create:

```text
src/main/resources/application-prod.yaml
```

```yaml
integrations:
  catalog:
    base-url: "https://catalog.partner.example"
    timeouts:
      connect: 3s
      read: 8s
```

Activate it with:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Spring Boot loads the matching profile file, overriding properties defined in Config Data according to profile rules. However, an OS environment variable for the same key still generally takes precedence over `application-prod.yaml`. Do not assume the `"prod"` filename guarantees it wins over every other source.

### 9.3. Avoid Mixing Too Many Sources

If the API key can appear simultaneously in:

1. `application-prod.yaml`.
2. Docker/Kubernetes Secret volume.
3. OS environment.
4. `SPRING_APPLICATION_JSON`.
5. CLI `--integrations.catalog.auth.api-key=...`.

then it becomes hard to tell which credential is active and manage its rotation lifecycle. Pick a single **operational source of truth**, restrict unintended overrides, and control who can modify deployments.

## 10. Building RestClient from CatalogProperties

Spring Boot 3.3 provides an auto-configured prototype `RestClient.Builder` bean when Spring Web is appropriately configured. Inject the builder rather than calling `RestClient.create()` everywhere so you retain the message converters and customizers prepared by Boot.

File:

```text
src/main/java/com/example/catalogdemo/config/CatalogClientConfiguration.java
```

Content:

```java
package com.example.catalogdemo.config;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean("catalogRestClient")
    RestClient catalogRestClient(
            RestClient.Builder builder,
            CatalogProperties properties) {

        Duration connect = properties.timeouts().connect();
        Duration read = properties.timeouts().read();

        if (connect.isZero() || connect.isNegative()
                || read.isZero() || read.isNegative()) {
            throw new IllegalArgumentException(
                    "Catalog timeouts must be positive");
        }

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(connect);
        factory.setReadTimeout(read);

        return builder
                .baseUrl(properties.baseUrl().toString())
                .requestFactory(factory)
                .defaultHeader(
                    "X-Api-Key", properties.auth().apiKey())
                .build();
    }
}
```

### 10.1. Why Explicitly Choose SimpleClientHttpRequestFactory?

The `RestClient.Builder` supplied by Spring Boot may already have an HTTP request factory auto-selected from the classpath and configuration. In this lab, we **intentionally** use `SimpleClientHttpRequestFactory` to directly demonstrate both `Duration` timeouts using Spring Framework 6.1 APIs.

The `setConnectTimeout(Duration)` and `setReadTimeout(Duration)` methods are available on Spring Framework 6.1's `SimpleClientHttpRequestFactory`. It is backed by `HttpURLConnection`; this is easy to understand for learning, **not a blanket recommendation** for every high-throughput application, HTTP/2 workload, or specialized connection-pooling requirement.

In production, you may use Apache HttpComponents, the JDK HttpClient request factory, or another client depending on your needs; when switching factories, verify timeout, pooling, proxy, TLS, and retry semantics for the actual client.

### 10.2. Connect and Read Timeouts Are Not the Same

| Configuration | Example | What it controls |
| --- | --- | --- |
| `timeouts.connect` | `2s` | Wait time to establish the connection |
| `timeouts.read` | `5s` | Wait time to read data from the connection per the request factory |
| End-to-end deadline | Not implemented in example | Total duration across request, DNS, connect, response, and retries per custom design |
| Retry policy | Not implemented | Whether failed requests are retried |

Do not mistake `readTimeout=5s` for a guarantee that **the entire request will definitely finish within 5 seconds**. Timeout semantics depend on the HTTP stack, execution phase, DNS, and downstream behavior.

### 10.3. A Timeout of 0 Is a Trap

With `SimpleClientHttpRequestFactory`, a timeout of 0 can mean **no timeout limit** in the underlying API. That is why the bean factory in this example rejects zero or negative values.

If you want a different policy, change the check deliberately and write tests for boundary values. Never pass `0s` assuming it means "do not wait".

### 10.4. Give Each RestClient a Clear Identity

The bean name:

```java
@Bean("catalogRestClient")
```

lets you distinguish it from other outbound clients such as `billingRestClient` or `inventoryRestClient` if the application integrates additional partners later.

When there is only one `RestClient` bean, injection by type also works. Using an explicit qualifier avoids ambiguous dependency errors when a second service is added.

### 10.5. Headers Containing Secrets

`defaultHeader("X-Api-Key", properties.auth().apiKey())` attaches the API key to requests made by this client unless overridden per request according to builder/client semantics.

Never log the entire `RestClient` builder, request headers, or `CatalogProperties`. Also avoid printing the secret when an upstream returns 401/403; log only the upstream name, status code, correlation ID, and non-sensitive data.

If a partner's policy uses a Bearer token instead of `X-Api-Key`, adapt to the real API's scheme and requirements (for example `Authorization: Bearer ...`) rather than assuming this illustrative header fits every provider.

## 11. Creating the ProductDto Result Model

File:

```text
src/main/java/com/example/catalogdemo/catalog/ProductDto.java
```

```java
package com.example.catalogdemo.catalog;

public record ProductDto(
        String id,
        String name,
        int stock) {
}
```

Simulated JSON response:

```json
{
  "id": "p-100",
  "name": "Notebook",
  "stock": 12
}
```

Spring Web starter already provides standard message converters with Jackson to deserialize the JSON response into `ProductDto`. For real APIs, the DTO must reflect the external JSON schema, versioning contract, and nullability. If the API uses different field names such as `product_id`, use Jackson annotations or an explicit DTO mapping.

**Do not use a JPA entity** directly as an outbound DTO just because field names match. Separating DTOs shields your internal system from partner schema changes.

## 12. Writing CatalogClient to Call the External Service

File:

```text
src/main/java/com/example/catalogdemo/catalog/CatalogClient.java
```

```java
package com.example.catalogdemo.catalog;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CatalogClient {

    private final RestClient client;

    public CatalogClient(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    public ProductDto getProduct(String id) {
        ProductDto product = client
                .get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(ProductDto.class);

        if (product == null) {
            throw new IllegalStateException(
                    "Catalog service returned an empty body");
        }
        return product;
    }
}
```

### 12.1. Explaining the HTTP Call

- `.get()`: outbound HTTP GET.
- `.uri("/products/{id}", id)`: builds the URI with a path variable instead of manual string concatenation.
- `.retrieve()`: retrieves the response via `RestClient` response handling.
- `.body(ProductDto.class)`: decodes JSON into the record using the appropriate converter.

If the upstream returns 4xx or 5xx, `retrieve()` by default can throw `RestClientResponseException` or a subtype instead of returning a DTO. If the connection times out or the upstream is unreachable, you may encounter `ResourceAccessException`; handle these at an appropriate boundary.

### 12.2. Do Not Build URLs via String Concatenation

Prefer:

```java
.uri("/products/{id}", id)
```

over:

```java
.uri("/products/" + id)
```

because template variables clearly express the URI structure and path encoding behavior. For parameters containing slashes, spaces, or special characters, still understand encoding semantics and the downstream path contract; do not treat templates as a substitute for validation.

### 12.3. The Service No Longer Reads Environment Directly

A design flaw:

```java
String url = System.getenv("CATALOG_URL");
String apiKey = System.getenv("CATALOG_API_KEY");
```

repeated across outbound methods. This bypasses the configuration properties group, makes profiles/defaults/precedence hard to test, and can create multiple sources of truth.

Instead, `CatalogClient` receives an already-configured `RestClient` without needing to know whether connection settings came from YAML, Docker, Kubernetes, or a Secret manager.

## 13. Creating an Internal HTTP Endpoint to Test the Client

File:

```text
src/main/java/com/example/catalogdemo/catalog/CatalogController.java
```

```java
package com.example.catalogdemo.catalog;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo/products")
public class CatalogController {

    private final CatalogClient catalogClient;

    public CatalogController(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @GetMapping("/{id}")
    public ProductDto getProduct(@PathVariable String id) {
        return catalogClient.getProduct(id);
    }
}
```

When calling:

```http
GET /demo/products/p-100 HTTP/1.1
Host: localhost:8080
```

the controller calls `CatalogClient`, and `CatalogClient` calls `GET /products/p-100` on the upstream service. This lab **intentionally leaves the internal endpoint unauthenticated** to demonstrate binding/client wiring. Before exposing anything publicly on the Internet, add authentication/authorization, input validation, rate limiting, and appropriate access policies; do not deploy this sample controller to public production as a secure-by-default API.

## 14. Handling Upstream Errors Clearly

Do not conflate partner connection errors with startup configuration errors. You can add a `@RestControllerAdvice` to return clear HTTP status codes without exposing upstream response bodies or credentials.

File:

```text
src/main/java/com/example/catalogdemo/catalog/CatalogErrorHandler.java
```

```java
package com.example.catalogdemo.catalog;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientResponseException;

@RestControllerAdvice
public class CatalogErrorHandler {

    public record ErrorMessage(
            String code,
            String message) {
    }

    @ExceptionHandler(RestClientResponseException.class)
    public ResponseEntity<ErrorMessage> upstreamHttpError(
            RestClientResponseException ex) {
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(new ErrorMessage(
                        "UPSTREAM_HTTP_ERROR",
                        "External catalog returned an error"));
    }

    @ExceptionHandler(ResourceAccessException.class)
    public ResponseEntity<ErrorMessage> upstreamNetworkError(
            ResourceAccessException ex) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ErrorMessage(
                        "UPSTREAM_UNAVAILABLE",
                        "External catalog is temporarily unavailable"));
    }
}
```

This is a minimal mapping for demo purposes. In production, a 404 from upstream might mean "product not found", 429 means rate-limited, 401/403 means a credential/authorization error, and 5xx means an upstream failure; you may need distinct handling strategies rather than mapping every status to 502.

### 14.1. Avoid Leaking Secrets and Internal Information

Do not return raw:

```java
ex.getResponseBodyAsString()
```

to external clients if the upstream response could contain sensitive details. Do not dump headers because `Authorization` or `X-Api-Key` may be in the request context/logging. Error responses should carry a stable error code, correlation ID, and short standardized message.

### 14.2. Startup Validation Failures

If `CatalogProperties` is missing `api-key`, startup may fail with `ConfigurationPropertiesBindException` / validation failure before the controller ever runs. That is a **configuration** error, not "upstream temporarily unavailable".

The right fix is to supply the proper secret and restart/roll out, not to catch exceptions in every HTTP method to mask configuration errors.

## 15. Creating a Fake Upstream for Local Practice

If you do not have a real Catalog service, you can run a fake HTTP server using the **Python standard library**. It is strictly for learning; it contains no real secrets and must not be used in production networks.

Create file:

```text
mock_catalog.py
```

```python
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path

        if not path.startswith("/products/"):
            self.send_response(404)
            self.end_headers()
            return

        # Dummy key for testing environments only.
        if self.headers.get("X-Api-Key") != "local-demo-key":
            self.send_response(401)
            self.end_headers()
            return

        product_id = unquote(path.removeprefix("/products/"))
        data = {
            "id": product_id,
            "name": "Notebook",
            "stock": 12,
        }
        body = json.dumps(data).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 9091), Handler).serve_forever()
```

Start the upstream in the first terminal:

```bash
python3 mock_catalog.py
```

On Windows you can run:

```powershell
py -3 mock_catalog.py
```

If an older Python version lacks `str.removeprefix`, use Python 3.9+ or replace it with slicing. The mock server binds to `127.0.0.1` to avoid accidentally exposing it to external machines.

### 15.1. Test the Upstream First

```bash
curl -i -H "X-Api-Key: local-demo-key" \
  http://127.0.0.1:9091/products/p-100
```

Expected output:

```http
HTTP/1.0 200 OK
Content-Type: application/json

{"id":"p-100","name":"Notebook","stock":12}
```

Header order and output details may vary, but the HTTP status and JSON fields are what matter. Do not expect byte-for-byte matches with the example.

### 15.2. Run the Spring Boot Application

Second terminal on Linux/macOS:

```bash
export CATALOG_API_KEY=local-demo-key
./mvnw spring-boot:run
```

Or using a system Maven installation:

```bash
mvn spring-boot:run
```

On Windows PowerShell:

```powershell
$env:CATALOG_API_KEY = "local-demo-key"
.\mvnw.cmd spring-boot:run
```

With the `application.yaml` from section 8, the app will:

- Bind `baseUrl = http://127.0.0.1:9091`.
- Bind `auth.apiKey = local-demo-key`.
- Bind `timeouts.connect = 2s`.
- Bind `timeouts.read = 5s`.
- Create the `RestClient` and controller on port 8080.

### 15.3. Send a Request Through the Spring App

```bash
curl -i http://localhost:8080/demo/products/p-100
```

Expected HTTP 200 and body:

```json
{
  "id": "p-100",
  "name": "Notebook",
  "stock": 12
}
```

The flow proves that the API key passed through the configuration group into `RestClient`, while the response does not expose the secret.

### 15.4. Failure Experiments

1. Unset `CATALOG_API_KEY` and restart the app: `@NotBlank` in `CatalogProperties.Auth` reports a configuration error if validation is active.
2. Set `INTEGRATIONS_CATALOG_TIMEOUTS_CONNECT=not-a-duration`: the Binder fails conversion.
3. Stop the mock server and call the endpoint: the client hits a connection error, and the controller advice returns 503.
4. Keep the mock server running but pass a dummy API key other than `local-demo-key`: the upstream returns 401, and the demo advice returns 502.
5. Set `INTEGRATIONS_CATALOG_BASEURL=http://127.0.0.1:9999`: the app can still start (valid URI), but outbound requests fail to connect.
6. Set `INTEGRATIONS_CATALOG_TIMEOUTS_READ=0s`: the bean factory explicitly rejects a zero timeout.
7. Set `SPRING_PROFILES_ACTIVE=prod` while the local upstream is running: the app uses the base URL from the production profile unless overridden by env, demonstrating how profiles alter the target.

In each experiment, distinguish **startup configuration errors**, **conversion/validation errors**, and **runtime HTTP errors**.

## 16. Testing Binding Without Calling a Real Upstream

You can use `@SpringBootTest` to verify that Boot registered the configuration properties record and bound values correctly.

File:

```text
src/test/java/com/example/catalogdemo/config/CatalogPropertiesTest.java
```

```java
package com.example.catalogdemo.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "integrations.catalog.base-url=http://localhost:19091",
    "integrations.catalog.auth.api-key=test-only-key",
    "integrations.catalog.timeouts.connect=250ms",
    "integrations.catalog.timeouts.read=3s"
})
class CatalogPropertiesTest {

    @Autowired
    CatalogProperties properties;

    @Test
    void bindsStructuredExternalServiceSettings() {
        assertThat(properties.baseUrl())
                .isEqualTo(URI.create("http://localhost:19091"));
        assertThat(properties.auth().apiKey())
                .isEqualTo("test-only-key");
        assertThat(properties.timeouts().connect())
                .isEqualTo(Duration.ofMillis(250));
        assertThat(properties.timeouts().read())
                .isEqualTo(Duration.ofSeconds(3));
        assertThat(properties.enabled()).isTrue();
    }
}
```

**This test does not call `http://localhost:19091`.** It only starts the context and verifies binding. The `RestClient` bean may be created from `baseUrl` during the test, but it does not necessarily open a network connection at creation time.

When writing tests, properties in `@SpringBootTest(properties=...)` act as high-priority **test overrides** under the test context framework; do not use them to infer all production precedence rules.

### 16.1. Testing Missing Auth

To verify fail-fast behavior, use `ApplicationContextRunner` or a dedicated `@SpringBootTest` with missing/blank properties. With `ApplicationContextRunner`, register the configuration-properties type and the appropriate validation auto-configuration:

```java
package com.example.catalogdemo.config;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class CatalogValidationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withConfiguration(
                    AutoConfigurations.of(
                        ValidationAutoConfiguration.class))
                .withUserConfiguration(TestConfig.class);

    @Test
    void failsWhenApiKeyIsBlank() {
        runner.withPropertyValues(
            "integrations.catalog.base-url=http://localhost:19091",
            "integrations.catalog.auth.api-key=",
            "integrations.catalog.timeouts.connect=2s",
            "integrations.catalog.timeouts.read=5s")
            .run(context -> {
                assertThat(context).hasFailed();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CatalogProperties.class)
    static class TestConfig {
    }
}
```

`hasFailed()` confirms the context could not be created; to check the exact root cause, inspect `context.getStartupFailure()` and its cause chain. Depending on auto-configuration/test setup, ensure a Bean Validation provider is present. Do not assume every failure is caused by `@NotBlank` if the test fails due to another infrastructure error.

### 16.2. Testing Bare Duration Values

```properties
integrations.catalog.timeouts.connect=2
```

In Spring Boot 3.3, a `Duration` without a unit annotation typically defaults to milliseconds, so `2` means **2ms**, not 2s. Writing a test asserting `Duration.ofMillis(2)` helps catch this confusion; in deployment configurations, always use explicit suffixes such as `2s` or `500ms`.

### 16.3. Testing Nested Validation

With `@Valid @NotNull Auth auth` and `@NotBlank String apiKey`, both cases must be rejected: omitting the entire `auth` group, and supplying the `auth` group with a whitespace-only `api-key`.

If `@Valid` is omitted, nested constraints may not cascade as expected. This lab places `@Valid` directly on the record component to make the requirement explicit.

## 17. Testing CatalogClient with Mock HTTP

Never run integration tests against production endpoints. Spring Framework provides `MockRestServiceServer`, which binds to a `RestClient.Builder` to return fake responses and verify request paths, headers, and JSON mapping.

File:

```text
src/test/java/com/example/catalogdemo/catalog/CatalogClientTest.java
```

```java
package com.example.catalogdemo.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class CatalogClientTest {

    @Test
    void sendsApiKeyAndReadsProduct() {
        RestClient.Builder builder = RestClient.builder();

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder
                .baseUrl("http://example.test")
                .defaultHeader("X-Api-Key", "test-only-key")
                .build();

        CatalogClient gateway = new CatalogClient(client);

        server.expect(requestTo(
                "http://example.test/products/p-100"))
            .andExpect(header("X-Api-Key", "test-only-key"))
            .andRespond(withSuccess(
                """
                {"id":"p-100","name":"Notebook","stock":12}
                """,
                MediaType.APPLICATION_JSON));

        ProductDto result = gateway.getProduct("p-100");

        assertThat(result.id()).isEqualTo("p-100");
        assertThat(result.name()).isEqualTo("Notebook");
        assertThat(result.stock()).isEqualTo(12);
        server.verify();
    }
}
```

This tests **CatalogClient behavior**, not the full HTTP request factory or timeouts. Here, `MockRestServiceServer` attaches request handling to the builder before constructing `RestClient`, so the test does not exercise the production bean factory code that customizes `requestFactory`.

If you need to test that timeout configuration is passed to the real factory, write a dedicated test for the bean configuration or an integration test against a mock HTTP server with real delays. Never conclude that timeouts work solely from an in-memory mock with no network.

### 17.1. Adding Upstream Error Tests

You can set up an expectation that returns HTTP 503:

```java
server.expect(requestTo(
        "http://example.test/products/p-100"))
    .andRespond(org.springframework.test.web.client.response
        .MockRestResponseCreators.withServerError());
```

Then assert that `CatalogClient` throws `RestClientResponseException` or the appropriate subtype. Test `@RestControllerAdvice` separately to prove inbound HTTP returns 502/503. Do not catch all exceptions inside `CatalogClient` and return an empty `ProductDto`, as that hides real outages.

## 18. Building and Packaging

On Linux/macOS:

```bash
./mvnw clean test
./mvnw package
java -jar target/catalog-demo-0.0.1-SNAPSHOT.jar
```

Without Maven Wrapper:

```bash
mvn clean test
mvn package
java -jar target/catalog-demo-0.0.1-SNAPSHOT.jar
```

On Windows PowerShell:

```powershell
.\mvnw.cmd clean test
.\mvnw.cmd package
$env:CATALOG_API_KEY = "local-demo-key"
java -jar target/catalog-demo-0.0.1-SNAPSHOT.jar
```

For the sample to start successfully, `CATALOG_API_KEY` (or its canonical env equivalent) must be provided along with the required configuration groups. Because the YAML in this lab has `api-key: "${CATALOG_API_KEY:}"`, omitting the env var causes `@NotBlank` to fail startup by design.

### 18.1. IDE Metadata

With `spring-boot-configuration-processor`, the build can generate:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

This file informs IDEs about keys like `integrations.catalog.base-url` and `integrations.catalog.timeouts.read`. It is **tooling metadata**, not a store for runtime values. Never put real API keys into metadata or default metadata values.

### 18.2. Verifying Dependency Versions

Do not hard-code Spring Framework versions outside the parent POM unless necessary. If a dependency pulls in a `spring-web` version from outside the 6.1 line, the application may hit a `NoSuchMethodError` on `RestClient` or timeout methods. Run:

```bash
./mvnw dependency:tree
```

to diagnose conflicts; do not arbitrarily bump individual Spring Framework JARs while bypassing the BOM.

## 19. Docker Compose: Overriding URLs and Timeouts per Deployment

You can package the app as an image following your project workflow. Compose example:

```yaml
services:
  catalog-demo:
    image: example/catalog-demo:1.0
    ports:
      - "8080:8080"
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      INTEGRATIONS_CATALOG_BASEURL: "https://catalog.partner.example"
      INTEGRATIONS_CATALOG_TIMEOUTS_CONNECT: "3s"
      INTEGRATIONS_CATALOG_TIMEOUTS_READ: "8s"
      CATALOG_API_KEY: "${CATALOG_API_KEY}"
```

In Compose YAML, `${CATALOG_API_KEY}` is variable interpolation **resolved by Compose before the container starts**. Only use this when Compose's environment source is securely managed; for real secrets, prefer Docker secrets or a secret manager and never print values with debug commands.

**Distinguish two layers:**

1. Docker Compose determines which environment variables the container receives.
2. Spring Boot determines whether those variables override `application.yaml` or other Config Data.

A `.env` file in a Compose project is typically used for interpolation and does **not automatically** turn every line into container environment variables unless the service declares `environment` or `env_file` entries for them.

### 19.1. Docker Secret Volume and configtree

If the Docker service mounts the file:

```text
/run/secrets/integrations.catalog.auth.api-key
```

Boot can import it with:

```properties
spring.config.import=configtree:/run/secrets/
```

The file content becomes the value of `integrations.catalog.auth.api-key`. Dotted filenames or subdirectories must match the canonical key; do not write `key=value` inside the file when using `configtree` in the one-file-per-key model.

When using this approach, consider removing the `CATALOG_API_KEY` placeholder from YAML or maintaining a clear policy on Config Data import ordering. If the canonical env var `INTEGRATIONS_CATALOG_AUTH_APIKEY` is also present, the env source takes higher default precedence than Config Data files. Avoid duplicating secrets across both sources unnecessarily.

### 19.2. Avoid Baking Secrets into Images

Do not write:

```dockerfile
ENV CATALOG_API_KEY=real-secret
```

and do not `COPY` files containing secrets into image layers. Build secret-free images, supply secrets at container runtime, and configure volume/process permissions plus a separate rotation process.

## 20. Kubernetes: Reading Configuration from ConfigMap and Secret

A Deployment can supply non-sensitive values via `env`:

```yaml
env:
  - name: INTEGRATIONS_CATALOG_BASEURL
    value: "https://catalog.partner.example"
  - name: INTEGRATIONS_CATALOG_TIMEOUTS_READ
    value: "8s"
```

And supply credentials via a Kubernetes Secret:

```yaml
env:
  - name: CATALOG_API_KEY
    valueFrom:
      secretKeyRef:
        name: catalog-client-credentials
        key: api-key
```

These blocks are **configuration snippets**; in a real Deployment, merge them into a single `env` array on the container.

### 20.1. Valid Complete Deployment Snippet

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog-demo
  template:
    metadata:
      labels:
        app: catalog-demo
    spec:
      containers:
        - name: app
          image: example/catalog-demo:1.0
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: INTEGRATIONS_CATALOG_BASEURL
              value: "https://catalog.partner.example"
            - name: INTEGRATIONS_CATALOG_TIMEOUTS_CONNECT
              value: "3s"
            - name: INTEGRATIONS_CATALOG_TIMEOUTS_READ
              value: "8s"
            - name: CATALOG_API_KEY
              valueFrom:
                secretKeyRef:
                  name: catalog-client-credentials
                  key: api-key
```

Kubernetes requires the corresponding Secret to exist in the namespace with proper access permissions. The snippet above **does not create** the Secret object. Also, the sample HTTP endpoint has no authentication and the image name is illustrative; do not deploy directly to the public Internet.

### 20.2. Secret Mount via configtree

Another option is mounting a Kubernetes Secret as files:

```text
/etc/secrets/catalog/integrations.catalog.auth.api-key
```

Inside the container:

```text
SPRING_CONFIG_IMPORT=configtree:/etc/secrets/catalog/
```

Spring Boot reads the filename as the property key and the file content as the value. No plaintext credential needs to be placed in OS environment variables.

**Update behavior:** Kubernetes can update projected Secret volumes according to its own mechanism, but `@ConfigurationProperties` beans and `RestClient` instances created at startup **do not hot-reload automatically** just because the file changes. You need a rollout/restart or a deliberately designed and tested refresh mechanism. When a header is pre-configured on `RestClient` at initialization, the client continues using the snapshot key until recreated.

## 21. enabled=true/false: Define Semantics Up Front

In the current model:

```java
@DefaultValue("true") boolean enabled
```

is bound, but **not yet used to disable `CatalogClient`** in code. That means setting `enabled=false` only changes the bean property value and does not automatically stop the controller from calling the upstream.

If a project needs an actual disable toggle, options include:

1. Have the controller/service check `properties.enabled()` and return a clear business error before making an outbound call.
2. Use conditional bean registration (`@ConditionalOnProperty`) for enabled vs. disabled client strategies, handling injection accordingly.
3. Design a `CatalogGateway` interface with real and disabled/no-op implementations, selected in a controlled manner based on the property.

**Do not just add an `enabled` field and claim the feature is turned off.** In the current example, it is a bound property for learning; real behavior requires code that consumes it.

### 21.1. Checking `enabled` in CatalogClient

To make the field take effect immediately, update the constructor to accept `CatalogProperties` and check it:

```java
private final RestClient client;
private final CatalogProperties properties;

public CatalogClient(
        @Qualifier("catalogRestClient") RestClient client,
        CatalogProperties properties) {
    this.client = client;
    this.properties = properties;
}

public ProductDto getProduct(String id) {
    if (!properties.enabled()) {
        throw new IllegalStateException(
            "Catalog integration is disabled");
    }
    // call client as in the main snippet
}
```

You must import `CatalogProperties` and add an appropriate handler/response mapping if exposing the error over HTTP. **This is an advanced variation**—do not paste it straight into the main class without updating constructors and tests.

If your policy is that no API key is needed when disabled, use appropriate **conditional validation**; the main model always requires a key even when `enabled=false`. Changing semantics requires updating Bean Validation, the bean factory, and tests together.

## 22. Securing the API Key in the Sample Application

### 22.1. Why `String` Secrets Carry Risk

`String apiKey` is convenient for HTTP headers, but it resides in memory and can easily leak through:

- Default `record.toString()`.
- Logging the `CatalogProperties` object.
- Exceptions containing raw configuration values.
- Debug dumps of the full Environment or HTTP requests.
- Unsecured Actuator endpoints.
- Session recordings or HTTP tracing that capture headers.

Java records have an auto-generated `toString()`. Therefore:

```java
logger.info("Properties: {}", properties);
```

is **unsafe** when the record holds an API key. Log only non-sensitive fields (validated base URL, timeouts, enabled flag), and redact URL components containing credentials or query parameters if URLs can carry sensitive data.

### 22.2. Security Checklist

- Never commit a real `CATALOG_API_KEY` to Git.
- Never store keys in `application-prod.yaml`.
- Never put keys into IDE metadata.
- Never embed secrets in Dockerfiles, image layers, command-line args, or screenshots.
- Never log `X-Api-Key` or `Authorization` headers.
- Secure `/actuator/env` and `/actuator/configprops`; verify masking/sanitization.
- Use HTTPS and verify TLS on production upstreams.
- Scope secrets per workload/principal and rotate them periodically.
- Never echo raw upstream error bodies on public endpoints.
- Plan restarts/rollouts when secrets rotate if the client holds a key snapshot.
- Apply network egress rules so the app can only call approved hosts.

**Do not treat Config Data or `@ConfigurationProperties` as a secret vault.** They are mechanisms for delivering configuration; real security comes from secret provisioning, access control, transport security, logging hygiene, and operations.

## 23. Preventing SSRF When `base-url` Is Configurable

`integrations.catalog.base-url` is a URI the application uses as an outbound destination. If untrusted users can control it, the application risks becoming a Server-Side Request Forgery (SSRF) vector, calling internal addresses or metadata services.

For production:

- Only allow host/service endpoints on an organization allowlist.
- Require `https` except intentionally in local/test.
- Never let inbound HTTP users pass arbitrary URLs to `RestClient`.
- Restrict outbound network egress via infrastructure policies.
- Review the HTTP client's redirect policy if the API does not require redirects.
- Distinguish URI syntax validation from host authorization.
- Never put credentials in URL query strings.

Simple check example in the bean factory:

```java
var scheme = properties.baseUrl().getScheme();
if (!"https".equalsIgnoreCase(scheme)
        && !"http".equalsIgnoreCase(scheme)) {
    throw new IllegalArgumentException(
            "Catalog URL must use HTTP or HTTPS");
}
```

Checking the scheme alone is not enough to prevent SSRF; hostname/IP-range allowlisting and egress controls are necessary additional layers. Never disable TLS verification as a "quick fix" for certificate errors.

## 24. Retries, Circuit Breakers, and Idempotency

This sample application **does not automatically retry** on HTTP failures. Creating a `RestClient` with timeouts does not imply a retry or circuit-breaker policy. If resilience is needed:

- Define maximum retry attempts, backoff, and jitter.
- Classify retryable errors: timeouts, connection resets, 429, and select 5xx responses.
- Avoid retrying 401/403 or unrecoverable configuration errors.
- Account for POST/PUT side effects and idempotency keys.
- Enforce an overall request deadline so retries do not extend indefinitely.
- Add circuit breakers and bulkheads under high load with unstable upstreams.
- Monitor latency, error rates, and retry counts via metrics/traces.
- Never log request bodies or headers containing secrets during retries.

If you add `integrations.catalog.retry.*` properties, extend `CatalogProperties` and implement the actual logic, validation, and tests; new metadata/config keys **do not enable retries automatically**.

### When to Choose WebClient?

`RestClient` is blocking; it fits Spring MVC thread-per-request or imperative code. `WebClient` uses reactive streams and has different timeout/retry semantics. Do not carelessly mix `WebClient.block()` into a reactive event loop or assume swapping the class alone makes the whole system non-blocking.

## 25. Adding a Second External Service

When adding a Billing API, do not copy-paste code and swap URL strings in multiple places. Define a separate group:

```yaml
integrations:
  catalog:
    base-url: "https://catalog.partner.example"
    auth:
      api-key: "${CATALOG_API_KEY:}"
    timeouts:
      connect: 2s
      read: 5s

  billing:
    base-url: "https://billing.partner.example"
    auth:
      api-key: "${BILLING_API_KEY:}"
    timeouts:
      connect: 3s
      read: 8s
```

Then create:

- `CatalogProperties` with prefix `integrations.catalog`.
- `BillingProperties` with prefix `integrations.billing`.
- Two `RestClient` beans with distinct qualifiers.
- Two service clients with clear responsibilities.
- Dedicated validation and tests for each partner.

You can reuse nested immutable types for auth/timeouts, but avoid stuffing everything into one giant `"GenericExternalServiceProperties"` if each partner has a different contract.

### Is `Map<String, ServiceSettings>` Appropriate?

If there are many dynamic endpoints with a uniform structure, a `Map<String, ServiceSettings>` under `integrations.services` can be useful. However:

- Map keys require naming and normalization rules.
- Enforcing per-service required properties can be harder.
- IDE hints/metadata are less specific than per-service records.
- You may need an allowlist of valid service keys.
- Per-key secret security and rotation must be designed explicitly.

For a few fixed integrations, separate typed `@ConfigurationProperties` records are usually easier to read and test.

## 26. Analyzing Real Startup Errors

### 26.1. Missing API Key

Symptom: the app fails to create `CatalogProperties` because `auth.apiKey` is blank or missing; the failure may be wrapped in `ConfigurationPropertiesBindException` or a bean creation exception.

How to troubleshoot:

1. Check whether `CATALOG_API_KEY` reaches the right JVM.
2. If using the canonical env var, check `INTEGRATIONS_CATALOG_AUTH_APIKEY`.
3. If using `configtree`, check the mounted file and import root.
4. Inspect the active profile and source precedence.
5. Never print the raw key while diagnosing.

### 26.2. Invalid Timeout Format

Example:

```text
INTEGRATIONS_CATALOG_TIMEOUTS_READ=fast
```

`Duration` cannot parse `fast`; this is a conversion error, not a DNS or HTTP connection error.

Use:

```text
INTEGRATIONS_CATALOG_TIMEOUTS_READ=5s
```

### 26.3. Writing `"5"` and Having It Interpreted as 5ms

Spring Boot `Duration` defaults to milliseconds for bare numbers without `@DurationUnit`. Write `5s`, `500ms`, or ISO-8601 format so operators do not guess wrong.

### 26.4. Valid Base URL, Failed Connection

`http://127.0.0.1:9091` has valid URI syntax. But if the app runs inside a Docker container, `127.0.0.1` refers to **that container itself**, not the host machine or another upstream container.

In Docker Compose deployments, use the service DNS name such as `http://mock-catalog:9091` on the same network if the upstream is another service. In Kubernetes, use the Kubernetes Service DNS name/port. The `localhost` address in the sample YAML applies only when both the Java app and the mock server run directly on the same machine.

### 26.5. 401 Unauthorized from Upstream

This can happen due to a missing, wrong, or expired API key, wrong header name, URL pointing to the wrong environment, or the partner using Bearer auth instead of `X-Api-Key`.

`@NotBlank` only checks that the key is **non-empty**; it cannot prove the partner accepts the key. Authentication is only verified when calling the upstream or via a dedicated check.

### 26.6. 404 from Upstream

This may be due to a wrong endpoint path, missing version prefix, nonexistent ID, or improper joining between base URL and relative path. Inspect the request path without logging sensitive headers.

### 26.7. 502/503 from the Internal Controller

In the example advice:

- Upstream HTTP error status → 502.
- I/O/network exception → 503.

This is a demo mapping. In production, distinguish timeouts, rate limiting, not-found, and upstream auth errors according to your system's API contract.

### 26.8. Bean Ambiguity

If there are two `RestClient` beans, a constructor:

```java
public CatalogClient(RestClient client)
```

can fail with `NoUniqueBeanDefinitionException` without a matching primary or qualifier. Use:

```java
@Qualifier("catalogRestClient")
```

matching the bean factory method name.

### 26.9. CatalogProperties Bean Not Found

If the main package does not cover the config package, or `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` is missing, Boot does not register the record. Fix package scanning/registration rather than manually instantiating `new CatalogProperties(...)` in a service.

### 26.10. Configuration Changed, App Still Uses Old Value

Once the JVM has started, the `CatalogProperties` record and `RestClient` hold a snapshot from bind time. Editing env vars, secret files, or deployment YAML does not automatically mutate running objects. A restart/rollout or deliberate refresh infrastructure is required.

## 27. Reading Binding Errors and Origin Properly

When Spring Boot fails during binding, the message typically includes details like:

```text
Property: integrations.catalog.timeouts.read
Value: "fast"
Origin: class path resource [application.yaml] - ...
Reason: failed to convert String to Duration
```

Exact field names/formats vary by version, source, and target. If the value came from an environment variable, `Origin` may lack line/column numbers; do not mistake a missing line number for a missing source.

Analysis steps:

1. Locate `ConfigurationPropertiesBindException` or `BindException` in the cause chain.
2. Check the property path and target Java type.
3. Check which source wins precedence.
4. Verify value syntax and units.
5. If binding succeeded but `@NotBlank`/`@NotNull` failed, check Bean Validation.
6. Check YAML indentation and active profiles.
7. Never log raw API key values or HTTP headers.

When the app starts successfully, you can inspect non-sensitive fields:

```java
@Bean
ApplicationRunner describeCatalog(CatalogProperties props) {
    return args -> {
        System.out.println("Catalog URL: " + props.baseUrl());
        System.out.println("Connect timeout: "
                + props.timeouts().connect());
        System.out.println("Read timeout: "
                + props.timeouts().read());
        System.out.println("Enabled: " + props.enabled());
    };
}
```

This snippet belongs in a `@Configuration` class importing `org.springframework.boot.ApplicationRunner` and `org.springframework.context.annotation.Bean`. It is an optional diagnostic, not required in the main project. **Never call `System.out.println(props)`**, because the record's `toString()` can expose the API key.

## 28. Testing Precedence and Profiles

A short matrix:

| application.yaml | application-prod.yaml | OS env | Effective `timeouts.read` |
| --- | --- | --- | --- |
| `5s` | Inactive | None | `5s` |
| `5s` | `8s`, prod profile active | None | `8s` |
| `5s` | `8s`, prod profile active | `10s` | `10s` |
| `5s` | Inactive | `500ms` | `500ms` |
| `5s` | Inactive | `not-time` | Likely conversion failure |
| `5s` | Inactive | `0s` | Rejected by sample bean factory |

This illustrative table considers only the listed sources, with no higher-priority CLI/JVM/JSON/custom sources. Also, if the entire `timeouts` subtree is omitted, configuration validation may fail before any other intended fallback applies.

To test **real OS env precedence**, launch the process with the environment variable set before startup rather than calling `System.setProperty(...)` after the context has already been created.

## 29. Extending Validation for Production

The sample validation ensures the URL is non-null, the `auth` and `timeouts` groups exist, and `apiKey` is non-blank. Stronger rules may be needed in real systems:

- `baseUrl` scheme must be `https` in the production profile.
- Host must belong to an internal/partner allowlist.
- Timeouts must be positive and not exceed a policy ceiling.
- API key matches an expected format.
- Whether `enabled=false` should waive the key requirement.
- If using client certificates, keystore file paths and passwords must be valid.
- Header namespace must conform to the partner contract.

Cross-field constraints can live in a custom validator or a configuration-checking bean invoked before the client is used. Avoid turning `@ConfigurationProperties` into a network-calling service to "validate credentials" during constructor binding; verifying remote credentials is a **runtime integration check**, not config parsing/binding.

### 29.1. Fail-Fast vs. Graceful Degradation

For an integration **required** by core business logic, failing startup when the API key or URL is missing is the desired behavior.

For an **optional** integration, the policy might be:

- Allow startup without a key if `enabled=false`.
- Create a `DisabledCatalogClient` implementation returning an appropriate status.
- Skip creating `RestClient`/secret-dependent beans when disabled.
- Validate credentials only when enabled.

Each policy leads to different code and validation. This lab chooses **fail-fast always requiring a key** to keep the example simple and highlight Spring Boot's structured configuration handling.

## 30. Pitfalls to Avoid in Deployment

| Mistake | Why it is a problem | Better approach |
| --- | --- | --- |
| Hard-coding URL/API key in a service | Hard to switch environments, leaks secrets | `@ConfigurationProperties` and secret injection |
| Scattering multiple `@Value` annotations | Hard to manage groups and validation | Typed config record |
| Missing `@ConfigurationPropertiesScan` | Bean is never registered | Scan or `@EnableConfigurationProperties` |
| Annotating the record with `@Component` | Breaks standard constructor-binding strategy | Register via configuration properties support |
| Using unitless String timeouts | Easy to misread `5` as 5ms | `Duration` + `5s` |
| Allowing startup with an empty API key | Fails late when calling upstream | `@NotBlank`/fail-fast when required |
| Assuming `@NotNull URI` guarantees reachability | Does not check DNS/TLS/host authorization | Check scheme, allowlist, egress |
| Setting `enabled=false` without reading it in code | Flag has no effect | Implement an explicit disabled strategy |
| Calling `RestClient.create()` directly | Skips Boot builder customizations | Inject `RestClient.Builder` |
| Replacing request factory without understanding HTTP stack | Timeouts/pooling/TLS may differ | Choose factory intentionally and test |
| Retrying every POST on timeout | Can cause duplicate side effects | Idempotency and retry policy |
| Calling production partners in tests | Flaky tests, cost/risk | `MockRestServiceServer` or mock server |
| Logging the whole config record | `toString()` exposes the key | Log safe fields only |
| Using `localhost` inside Docker | Points to the container itself | Use the proper service DNS/host |
| Exposing Actuator `env`/`configprops` publicly | Risks leaking configuration | Auth, masking, minimal exposure |
| Assuming secret mount changes auto-refresh client | Config/RestClient snapshots do not hot-reload | Rollout/restart or explicit refresh |
| Disabling TLS validation after seeing 401 | Does not solve authentication | Verify the right credentials and endpoint |
| Putting real default API keys in YAML | Secrets leak via artifacts/repos | Provision from a Secret manager |

## 31. Practice Completion Checklist

- [ ] Created a Java 17, Spring Boot 3.3 Maven project.
- [ ] Added Spring Web, Validation, Test, and configuration processor.
- [ ] Created `CatalogDemoApplication` with `@ConfigurationPropertiesScan`.
- [ ] Created `CatalogProperties` record with prefix `integrations.catalog`.
- [ ] Declared nested `Auth` and `Timeouts` records.
- [ ] Placed `@Validated`, `@Valid`, `@NotNull`, and `@NotBlank` in the right spots.
- [ ] Added base-url, timeouts, and API key placeholder to `application.yaml`.
- [ ] Supplied a dummy API key locally without hard-coding a real secret.
- [ ] Created `catalogRestClient` bean using the Boot-provided `RestClient.Builder`.
- [ ] Configured connect/read timeouts on the chosen request factory.
- [ ] Created `ProductDto` and `CatalogClient` with the right qualifier.
- [ ] Created `CatalogController` to trigger outbound calls via the client.
- [ ] Mapped outbound errors without leaking sensitive response bodies or headers.
- [ ] Ran the fake HTTP Catalog server on port 9091.
- [ ] Started the Boot app on port 8080 and called the demo endpoint.
- [ ] Verified the JSON response does not contain the API key.
- [ ] Tested config binding, nested validation, and mock `RestClient` requests.
- [ ] Tested invalid timeout units and missing API key.
- [ ] Created `application-prod.yaml` or env overrides for deployment.
- [ ] Verified canonical env naming, especially removing dashes and converting dots to underscores.
- [ ] Replaced `127.0.0.1` with the proper upstream service address when running in containers.
- [ ] Established a plan to keep secrets outside source/images and rotate them.
- [ ] Did not assume `enabled` works automatically without code consuming it.
- [ ] Prepared a runbook for DNS, timeout, 401/403, 4xx/5xx, and startup config errors.
- [ ] Kept the unauthenticated demo endpoint off public production.

## 32. Next Steps

Once the example works, you can extend it in a controlled way:

1. **Add an external Billing service**: create `BillingProperties`, a `billingRestClient` bean, and a dedicated `BillingClient`.
2. **Move the API key to a Secret volume**: use `spring.config.import=configtree:/etc/secrets/` with a file named after the canonical property.
3. **Add a request correlation ID**: propagate context via outbound headers and filter secrets before logging.
4. **Observability**: configure HTTP client metrics/traces per your infrastructure and Boot setup without logging sensitive payloads/headers.
5. **Retries/circuit breakers**: add a resilience library when required, testing idempotency, backoff, and total timeout deadlines.
6. **Container testing**: mock the upstream within the same Docker Compose network or Kubernetes namespace.
7. **Contract tests**: verify JSON schema and HTTP status rules against a simulated upstream.
8. **Configuration metadata**: add descriptions in Javadoc or additional metadata so IDEs suggest keys and units.
9. **Dynamic secret rotation**: design client recreation and rollback rather than assuming Spring Boot auto-refreshes.
10. **HTTPS/mTLS**: configure SSL bundles, keystores/truststores, or request factories per partner policy.

You do not need to implement all of these in the sample lab; the key foundation is **separating configuration values, connection wiring, and business logic**.

## 33. Official References

- **Spring Boot 3.3 — Externalized Configuration**, PropertySource order, Config Data, YAML, placeholders, type-safe configuration properties, constructor binding, relaxed binding, validation, Duration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 — Calling REST Services**, `RestClient` section, builder auto-configuration, and customizers: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
- **Spring Framework 6.1 — RestClient**, fluent blocking HTTP API guide: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-restclient
- **Spring Framework 6.1 — SimpleClientHttpRequestFactory Javadoc**, `setConnectTimeout(Duration)` and `setReadTimeout(Duration)`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html
- **Spring Boot 3.3 — Configuration Metadata**, processor and IDE metadata: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html
- **Spring Boot 3.3 — Testing Spring Boot Applications**, test context and test utilities: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- **Spring Framework — MockRestServiceServer**, testing outbound clients with mock requests/responses: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html
- **Docker Compose — Environment variables**, interpolation and service environments: https://docs.docker.com/compose/how-tos/environment-variables/
- **Kubernetes — Secrets**, delivering credentials to workloads: https://kubernetes.io/docs/concepts/configuration/secret/

## 34. Summary

In Spring Boot 3.3, an application integrating with an external service should follow a clear chain of responsibility:

```text
Config Data / OS env / secrets
           |
           v
@Validated @ConfigurationProperties
  CatalogProperties (typed record)
           |
           v
@Configuration building RestClient
  URL + timeout + API key
           |
           v
@Service CatalogClient
  HTTP requests / responses / errors
           |
           v
@RestController CatalogController
  Internal HTTP API
```

Three key takeaways:

1. **A configuration group with canonical names and clear Java types** lets local/staging/prod vary URLs, timeouts, and credentials without rebuilding business logic.
2. **Spring Boot only binds and supplies the data**; creating the client, applying timeouts, attaching auth headers, handling HTTP errors, and enforcing the `enabled` flag all require explicit code.
3. **Testing and security are part of the design**: fail-fast validation for required fields, mocked outbound HTTP in tests, never hard-coding or logging secrets, controlling override sources, and planning restarts/rotations when configuration changes.

This lab establishes a small but extensible pattern: add each external service with an independent `@ConfigurationProperties` contract, a clearly configured outbound client bean, and tests proving the connection uses the bound values.
