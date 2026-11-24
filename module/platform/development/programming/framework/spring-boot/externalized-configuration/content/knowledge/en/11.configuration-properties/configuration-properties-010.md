# Separating Configuration Classes from Business Services and Other Bean Dependencies

## 1. Goal: Configuration Is Data, Services Are Behavior, Other Beans Are Collaborators

As a Spring Boot application grows, business classes often need numerous parameters: external service URLs, timeouts, retry counts, feature flags, size limits, queue names, or operational policies. If every service reads `Environment` directly or carries dozens of `@Value` annotations, property keys and technical decisions leak into business code.

A common example:

```java
@Service
public class ShippingService {

    @Value("${shipping.base-url}")
    private String baseUrl;

    @Value("${shipping.connect-timeout:2s}")
    private String connectTimeout;

    @Value("${shipping.max-attempts:3}")
    private int maxAttempts;

    // Below lies business logic for dispatching orders.
}
```

This style can work in small apps, yet carries several consequences:

- A group of related properties gets scattered across multiple fields and annotations.
- The service must know raw key names like `shipping.base-url` and `shipping.connect-timeout` instead of working with a typed Java contract.
- Checking required values, retry bounds, and timeouts is hard to centralize.
- When multiple services share a config group, key names easily get duplicated or defaults diverge.
- Unit testing business logic easily becomes coupled to loading YAML files and starting a Spring context.
- The service mixes **reading configuration**, **initializing infrastructure objects**, and **executing business logic**.

`@ConfigurationProperties` separates these responsibilities by **binding a group of external properties into a typed Java object**. Services receive that object as a dependency via constructor injection. Other infrastructure beans such as `HttpClient`, `Clock`, `DataSource`, or service adapters remain managed separately via dependency injection.

Desired model:

```text
application.yml / env vars / runtime args
                        |
                        v
                  Spring Environment
                        |
                        v
          Binder + @ConfigurationProperties
                        |
                        v
                ShippingProperties
             (values only, no IO behavior)
                  /           \
                 v             v
          HttpClient bean   ShippingService
                 |             ^
                 +-------------+
                               ^
                               |
                         Clock bean
                               |
                               v
                       Business outcome
```

An easy-to-remember separation:

1. **Configuration Properties:** describes *configuration data*.
2. **Infrastructure configuration:** uses data and related beans to *assemble technical components*.
3. **Business service:** uses assembled dependencies to *perform business behavior*.
4. **Spring container:** handles *creating beans and wiring dependencies*.

This lesson builds a cohesive example and explains why a `@ConfigurationProperties` class should not become a service or a "container holding arbitrary beans."

## 2. What Does `@ConfigurationProperties` Do and Not Do?

The annotation:

```java
@ConfigurationProperties(prefix = "shipping")
```

tells Spring Boot that properties under the `shipping` prefix bind to the corresponding Java type. For example:

```yaml
shipping:
  enabled: true
  base-url: https://shipping.example.invalid/api/
  connect-timeout: 2s
  max-attempts: 3
```

Values map to:

```java
boolean enabled
URI baseUrl
Duration connectTimeout
int maxAttempts
```

Spring Boot handles binding and type conversion from `Environment`. Properties sharing the same key in higher-precedence sources, such as environment variables or command-line arguments, override YAML values before the configuration object is created.

**`@ConfigurationProperties` is not responsible for sending HTTP requests, opening database connections, or orchestrating shipping workflows.** Nor is it a general mechanism to autowire other Spring beans into arbitrary constructor parameters of a record.

For example, in this properties class:

```java
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        URI baseUrl,
        Duration connectTimeout,
        boolean enabled,
        int maxAttempts
) {}
```

the four constructor parameters represent **four configuration values**. They are not `@Autowired` references to an HTTP client, repository, or another service. Constructor binding of a configuration object and dependency injection between Spring beans are **two distinct operations**, even though both occur while building the application context.

## 3. End-to-End Example: Shipping Service Integration

We will structure a simulated application whose job is building a call plan for a shipping service. The example only prints the plan and parameters; it **does not perform real network HTTP requests**, so illustrative URLs are safe.

Suggested layout:

```text
shipping-demo/
└── src/
    ├── main/
    │   ├── java/com/example/shipping/
    │   │   ├── ShippingApplication.java
    │   │   ├── config/
    │   │   │   ├── ShippingProperties.java
    │   │   │   └── InfrastructureConfiguration.java
    │   │   └── service/
    │   │       └── ShippingService.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-prod.yml
    └── test/
        └── java/com/example/shipping/
            └── ShippingApplicationTest.java
```

Package names are just one example of organizing code by role. In large projects, you can also organize by feature, such as `shipping/config` and `shipping/service`. More important than folder names is **dependency direction**: services receive configuration values, rather than configuration data classes pulling in business logic.

### 3.1. Base Configuration File

Create `src/main/resources/application.yml`:

```yaml
shipping:
  enabled: true
  base-url: https://shipping.example.invalid/api/
  connect-timeout: 2s
  max-attempts: 3
```

Meaning:

- `shipping.enabled`: flag determining whether the integration feature is enabled.
- `shipping.base-url`: base address of the shipping service, an illustrative URL here.
- `shipping.connect-timeout`: timeout for establishing connections.
- `shipping.max-attempts`: retry attempt limit per application policy.

The value `2s` represents a duration, not a string that the service must split into a number and unit. `base-url` converts to `URI` so code works with a structured address representation.

In real environments, parameters must be chosen according to SLAs, retry behavior, and system architecture. The values here are purely to help observe binding.

## 4. Creating a Pure-Data Configuration Class

Create `config/ShippingProperties.java`:

```java
package com.example.shipping.config;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        boolean enabled,
        URI baseUrl,
        Duration connectTimeout,
        int maxAttempts
) {
}
```

This is a Java record (compatible with Java 17+ and Spring Boot 3's standard constructor binding).

The record enforces several principles:

- Each component represents data the deployment environment can supply.
- Values are provided at object creation instead of having services call setters mid-flight.
- Services read via `properties.enabled()`, `properties.baseUrl()`, etc.
- No `Environment`, repository, HTTP client, access credentials, or business service in the constructor.
- No network calls, data writes, or system state mutation inside the record.

**Do not annotate this record with `@Component` to make Spring auto-create it.** We will register `@ConfigurationProperties` using a dedicated mechanism in the next section.

### Why Not Put Dozens of `@Value` Annotations in a Class?

Suppose three components in the system all need `shipping.connect-timeout`. With individual `@Value` fields, each place might write:

```java
@Value("${shipping.connect-timeout:2s}")
Duration timeout;
```

Another place could accidentally write `${shipping.connection-timeout:3s}` and produce different behavior. When properties are defined centrally via `ShippingProperties`, all beans receive **the same type and the same bound group of values**.

This is not a ban on `@Value`: that annotation remains useful for a few standalone properties. Once you have a domain-meaningful group of settings, `@ConfigurationProperties` is usually easier to maintain and test.

## 5. Registering `@ConfigurationProperties` in the Spring Container

A class annotated with `@ConfigurationProperties` must be made known to Spring Boot via an appropriate registration mechanism. For a single properties class, the explicit approach is `@EnableConfigurationProperties`.

Create `ShippingApplication.java`:

```java
package com.example.shipping;

import com.example.shipping.config.ShippingProperties;
import com.example.shipping.service.ShippingService;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableConfigurationProperties(ShippingProperties.class)
public class ShippingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShippingApplication.class, args);
    }

    @Bean
    ApplicationRunner demoRunner(ShippingService shippingService) {
        return args -> {
            System.out.println(shippingService.preview());
        };
    }
}
```

`@EnableConfigurationProperties(ShippingProperties.class)` registers the properties class so Spring Boot's binder populates values from the `shipping` prefix.

If the application has many configuration classes, you can opt for package scanning:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ShippingApplication {
    // ...
}
```

`@ConfigurationPropertiesScan` must be imported from `org.springframework.boot.context.properties.ConfigurationPropertiesScan`. Choose **one clear registration approach** for your classes; avoid randomly adding `@Component` or registering duplicate beans where it becomes unclear which bean gets injected.

### Constructor Binding and Bean Injection Are Not the Same

When Spring Boot constructor-binds `ShippingProperties`, it searches configuration sources for values matching field names. If the record includes a parameter of type `HttpClient`, the binder will not treat that parameter as a Spring bean dependency to `@Autowired` like a normal service. That is the wrong way to fold infrastructure clients into properties.

Do not write:

```java
// Design anti-pattern: do not mix configuration data with Spring beans
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        URI baseUrl,
        HttpClient httpClient,
        ShippingService shippingService
) {}
```

`httpClient` and `shippingService` are not externalized property data. They are beans created and managed by the Spring container. Putting them in a configuration record mixes two separate object-creation mechanisms.

## 6. Creating Infrastructure Beans from Bound Properties

Suppose the application needs a `java.net.http.HttpClient` using the configured connect timeout. A `@Configuration` class can accept `ShippingProperties` and construct the client.

Create `config/InfrastructureConfiguration.java`:

```java
package com.example.shipping.config;

import java.net.http.HttpClient;
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InfrastructureConfiguration {

    @Bean
    HttpClient shippingHttpClient(ShippingProperties properties) {
        return HttpClient.newBuilder()
                .connectTimeout(properties.connectTimeout())
                .build();
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

The two `@Bean` methods return real infrastructure objects:

- `shippingHttpClient` is an HTTP client initialized with the configured connect timeout.
- `clock` is a system clock for time-based operations. In tests, it can be swapped for a fixed clock without modifying configuration classes.

Assembled relationships:

```text
ShippingProperties ---connectTimeout()---> HttpClient.Builder
                              |
                              v
                         HttpClient bean

InfrastructureConfiguration ---clock()---> Clock bean
```

Key point: `ShippingProperties` **never calls `new HttpClient`** and does not know the `Clock` bean exists. Pure-data configuration is reused by the bean assembly class.

In a project with multiple `HttpClient` beans, use `@Qualifier` or explicit bean identifiers when injecting. In this minimal example there is only one `HttpClient` bean, so type-based injection works directly.

### Why Build the Client in `@Configuration` Instead of Inside the Service?

If every service wrote:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(properties.connectTimeout())
        .build();
```

in its constructor, the service would own both business logic and low-level client initialization details. Whenever TLS, proxies, interceptors, or test doubles are introduced, the service would have to change.

Moving assembly into `@Configuration` makes testing cleaner. The service simply requests a ready-to-use `HttpClient`; infrastructure configuration handles how to construct it.

Of course, not every technical object needs a standalone Spring bean. When an object has lifecycle management, needs reuse, needs swapping in tests, or needs centralized configuration, an infrastructure bean is usually appropriate.

## 7. Service Receiving Properties and Collaborator Beans via Constructor

Create `service/ShippingService.java`:

```java
package com.example.shipping.service;

import com.example.shipping.config.ShippingProperties;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Clock;
import java.time.Duration;

import org.springframework.stereotype.Service;

@Service
public class ShippingService {

    private final ShippingProperties properties;
    private final HttpClient httpClient;
    private final Clock clock;

    public ShippingService(
            ShippingProperties properties,
            HttpClient httpClient,
            Clock clock) {
        this.properties = properties;
        this.httpClient = httpClient;
        this.clock = clock;
    }

    public String preview() {
        if (!properties.enabled()) {
            return "Shipping integration disabled";
        }

        URI endpoint = properties.baseUrl().resolve("v1/shipments");
        Duration timeout = httpClient.connectTimeout()
                .orElse(Duration.ZERO);

        return "endpoint=" + endpoint
                + ", maxAttempts=" + properties.maxAttempts()
                + ", connectTimeout=" + timeout
                + ", observedAt=" + clock.instant();
    }
}
```

The service has three dependencies with three distinct roles:

| Dependency | Role | Where It Comes From |
| --- | --- | --- |
| `ShippingProperties` | Typed configuration data | Spring Boot Binder from `shipping.*` |
| `HttpClient` | HTTP communication tool | `@Bean` in `InfrastructureConfiguration` |
| `Clock` | Time source for observation | `@Bean` in `InfrastructureConfiguration` |

The `preview()` method only builds an illustrative string. It sends no HTTP requests. In a real application, business methods use the client to call APIs, whereas this lesson focuses on **separating dependencies**, not network communication itself.

With the configuration from section 3, output looks like:

```text
endpoint=https://shipping.example.invalid/api/v1/shipments,
maxAttempts=3,
connectTimeout=PT2S,
observedAt=<UTC runtime timestamp>
```

`Duration.toString()` prints two seconds in ISO-8601 format as `PT2S`. `observedAt` changes with execution time, which does not affect configuration binding.

Crucial benefit: **`ShippingService` does not look up `shipping.base-url` in YAML**, does not read environment variables directly, and does not decide how to build `HttpClient`.

## 8. Dependency Boundaries: Which Direction Makes Sense?

A clean design can be drawn as:

```text
       [External configuration sources]
                 |
                 v
       [ShippingProperties]
           |          |
           v          v
 [Infrastructure]  [ShippingService]
           |          ^
           v          |
        [HttpClient] -+
                       ^
                       |
                    [Clock]
```

Rules to preserve:

1. **Properties do not depend on services.** They define data, not invoke business operations.
2. **Properties do not depend on infrastructure built from them.** Never include `HttpClient` inside the configuration record.
3. **Infrastructure beans can read properties.** For example, timeouts to configure clients.
4. **Services can receive both properties and collaborator beans.** Some values directly drive business policy; others configure infrastructure beans.
5. **Avoid circular dependencies.** If a service needs properties and an infrastructure bean, do not make the infrastructure bean call the service just to fetch the same properties.

Cycle to avoid:

```text
ShippingService
    -> ShippingHttpClientFactory
          -> ShippingService
```

Instead of having the factory ask the service for timeouts, let both receive `ShippingProperties` directly, or let infrastructure configuration construct the client before the service receives it.

### Which Responsibilities Belong in the Service?

Just because a parameter comes from YAML does not mean all logic involving it belongs in the properties class. For instance, `maxAttempts` is a configuration parameter, whereas the **retry algorithm**—deciding when to retry, backoff, business error handling, and idempotency—belongs in the service or a dedicated retry component, not in the `ShippingProperties` record.

Think of it as:

```text
ShippingProperties.maxAttempts() = 3     // data
RetryPolicy / ShippingService           // retry decision
HttpClient                              // transport tool
```

This separation keeps configuration classes from turning into dumping grounds for arbitrary logic.

## 9. Anti-Pattern: Service Knowing Too Much About `Environment`

Examine this design:

```java
@Service
public class ShippingService {

    private final Environment env;

    public ShippingService(Environment env) {
        this.env = env;
    }

    public String baseUrl() {
        return env.getProperty("shipping.base-url");
    }

    public int maxAttempts() {
        return Integer.parseInt(
                env.getProperty("shipping.max-attempts", "3"));
    }
}
```

With this approach, the service handles key names, lookups, defaults, and type conversion. When `shipping.connect-timeout` is added, it must decide how to parse `2s` itself. Testing also tends to require mocking or loading an environment rather than passing a typed object directly.

Layered alternative:

```java
@Service
public class ShippingService {

    private final ShippingProperties properties;

    public ShippingService(ShippingProperties properties) {
        this.properties = properties;
    }

    public int maxAttempts() {
        return properties.maxAttempts();
    }
}
```

In this minimal example, the service receives only the data it needs. Binding already happened before the bean reached the service.

**Do not misinterpret this to mean `Environment` should never be used.** It is useful in infrastructure code, technical adapters, or cases genuinely requiring dynamic lookups. Yet when a service merely needs a fixed set of settings, a typed `@ConfigurationProperties` object expresses intent far more clearly.

## 10. Combining Multiple `@ConfigurationProperties` Groups

A real application typically spans multiple configuration domains:

```text
shipping.*          -> ShippingProperties
payment.*           -> PaymentProperties
notification.*      -> NotificationProperties
storage.*           -> StorageProperties
```

Do not create one giant record like:

```java
@ConfigurationProperties(prefix = "application")
public record ApplicationProperties(
        String shippingBaseUrl,
        int shippingAttempts,
        String paymentUrl,
        String mailHost,
        String storageBucket,
        // ... 70 unrelated fields
) {}
```

because it piles too many responsibilities into one object and forces unrelated features to depend on a massive configuration model. A change in storage affects the data structure passed to the shipping service.

Split by domain:

```java
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxAttempts
) {}

@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        URI gatewayUrl,
        Duration requestTimeout
) {}
```

Each service then injects only the object it needs. If a business workflow coordinates shipping and payment, an *orchestrator service* can inject both relevant services instead of forcing the two property groups to know about each other.

### Can One Service Receive Multiple Property Groups?

Yes, when genuinely required:

```java
@Service
public class CheckoutCoordinator {
    public CheckoutCoordinator(
            ShippingProperties shipping,
            PaymentProperties payment) {
        // Use the required policies for checkout.
    }
}
```

However, if the number of dependencies grows rapidly, reconsider the service's boundaries rather than letting its constructor turn into a list of every config in the application.

## 11. `@ConfigurationProperties` and Depending on Other Beans

A frequent question: "Can a properties class inject a repository, service, or technical bean to compute a value?"

Design-wise, **do not turn configuration properties classes into consumers of other beans**. Constructor-bound properties classes should focus on environment data. Whenever configuration needs to combine with another bean, perform that combination in the behavior-owning class or in a `@Configuration` factory method.

Example requirement: constructing an outbound gateway requires both a timeout from YAML and a Spring-managed `TokenProvider`.

Proper diagram:

```text
application.yml -> GatewayProperties ----+
                                         |
TokenProvider bean ---------------------+--> GatewayClient bean
                                         |
HttpClient bean ------------------------+
```

You can write a `@Bean` method:

```java
@Configuration
public class GatewayConfiguration {

    @Bean
    GatewayClient gatewayClient(
            GatewayProperties properties,
            TokenProvider tokenProvider,
            HttpClient httpClient) {
        return new GatewayClient(
                properties.baseUrl(),
                properties.timeout(),
                tokenProvider,
                httpClient
        );
    }
}
```

`GatewayClient` and `TokenProvider` here are application-defined types; the snippet mainly demonstrates **where bean dependency injection belongs**.

`GatewayProperties` should remain an object holding `URI baseUrl` and `Duration timeout`, without a constructor taking `TokenProvider`. Every piece fits in its proper place:

- Binder creates properties from configuration.
- Spring container injects `TokenProvider` and `HttpClient`.
- `@Bean` combines them to construct `GatewayClient`.

If `GatewayClient` has many methods and its own lifecycle, you can make it a `@Component`/`@Service` taking those three constructor parameters instead of a `@Bean`; the responsibility separation stays identical.

## 12. Validation: Checking Configuration Before Services Run

Binding into Java types does not automatically ensure sensible values. `maxAttempts = -3` is a valid `int` type-wise, yet nonsensical in a retry policy. `connectTimeout = 0ms` may be invalid for how your application constructs clients. `baseUrl` could be missing.

Jakarta Bean Validation can be used if the project includes a supporting dependency, typically `spring-boot-starter-validation`.

Updated record example:

```java
package com.example.shipping.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        boolean enabled,
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @Min(1) int maxAttempts
) {
}
```

With validation properly enabled:

- Missing `shipping.base-url` is caught by `@NotNull`.
- Missing `shipping.connect-timeout` is caught by `@NotNull`.
- `shipping.max-attempts=0` fails `@Min(1)`.
- A string like `shipping.max-attempts=lots` cannot convert to `int`, triggering a binding/conversion error before an invalid value is ever injected.

Some constraints cannot be expressed solely with `@NotNull` or `@Min`. For example, requiring an `https` URI scheme, positive timeouts, or allowing a missing endpoint when `enabled=false`. Such rules require validation tailored to your configuration contract, via custom validators or dedicated verification methods.

**Example configuration note:** plain `URI` and `Duration` fields do not enforce all business checks automatically. Never claim that merely converting to `URI` guarantees the URL is reachable or uses HTTPS.

### Should Checks Live in the Properties Class or Service?

A helpful division rule:

| Check | Usually Best Placed In |
| --- | --- |
| Is a required key provided? | Properties binding validation |
| Is `maxAttempts` positive? | Properties validation |
| Is timeout positive and within allowed bounds? | Properties validation or infrastructure initialization logic |
| Is the customer authorized to create a shipment? | Business service / authorization |
| Does the order have a complete shipping address? | Business logic |
| Is the external API currently reachable? | Health checks, clients, and operational monitoring |
| Have credentials expired? | Authentication and secret management mechanisms |

The aim is to **fail fast on bad configuration**, not turn properties records into runners of business workflows.

## 13. Default Values: Where Should They Live?

There are multiple ways to define defaults, each communicating a different contract.

### 13.1. Defaults in `application.yml`

```yaml
shipping:
  enabled: false
  connect-timeout: 2s
  max-attempts: 3
```

This is easy to read for shared values. Profile files or runtime environments can override individual keys. Other beans querying the same key via `Environment` also see values from this shared source.

### 13.2. Defaults in Configuration Classes

With records, an appropriate constructor or data model can apply defaults, provided you understand constructor binding rules and `null`/primitive behavior when properties are absent. Never write a constructor accepting extra Spring beans just to compute defaults.

Spring Boot also supports `@DefaultValue` in constructor binding contexts. Conceptual example:

```java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        @DefaultValue("false") boolean enabled,
        URI baseUrl,
        @DefaultValue("2s") Duration connectTimeout,
        @DefaultValue("3") int maxAttempts
) {}
```

The binder applies component defaults when matching properties are absent. This differs from fallbacks scattered across individual `@Value` annotations.

### 13.3. Defaults in Services

If a rule is genuinely a **business rule** (e.g., max processing steps when a business policy is unspecified), the service can hold that rule. However, if a default belongs to the **operational configuration contract**, keeping it in properties or shared base configuration files is much clearer.

Avoid giving the same setting three conflicting defaults:

```text
application.yml          max-attempts=3
ShippingProperties       default=5
ShippingService          fallback=10
```

Multiple sources of truth leave operators unsure which value actually applies and create subtle bugs across environments.

## 14. How Do Different Environments Reuse the Same Service?

`ShippingService` never changes when the application runs under different profiles. Only the effective configuration source changes.

Keep `application.yml` from section 3. Create `application-prod.yml`:

```yaml
shipping:
  enabled: true
  base-url: https://shipping-prod.example.invalid/api/
  connect-timeout: 800ms
  max-attempts: 2
```

To run with the production profile:

```bash
java -jar app.jar --spring.profiles.active=prod
```

When `prod` is active, Spring Boot loads profile configuration and the binder binds effective values into `ShippingProperties`. The `HttpClient` bean gets its timeout from properties; `ShippingService` receives that same properties object and configured client.

You do not write inside the service:

```java
if ("prod".equals(activeProfile)) {
    // Read production timeout
} else {
    // Read development timeout
}
```

Operational parameter selection belongs in configuration. The service executes consistent logic across every environment.

### Sources with Higher Precedence Than Profile Files

Example:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --shipping.max-attempts=4
```

In standard Spring Boot configuration, command-line arguments outrank Config Data in `application-prod.yml`. Thus `ShippingProperties.maxAttempts()` receives `4` instead of `2`. No service class needs to know where the value originated.

Similarly, environment variables can override values. Under Spring Boot's standard env var naming rule, `shipping.max-attempts` corresponds to `SHIPPING_MAXATTEMPTS`. With canonical key names, the binder binds matching sources via relaxed binding.

**Never put real passwords or tokens into committed YAML files.** When secrets are needed, supply them via your deployment platform's secret management. `@ConfigurationProperties` does not encrypt or protect configuration values on its own.

## 15. Testing `ShippingService` Without Starting Spring

This is a major payoff of separating configuration from business logic. In a unit test, you **instantiate a `ShippingProperties` directly** with desired values and pass it into the service like any ordinary Java object. No `application.yml` parsing and no application context startup are required.

Example using JUnit 5:

```java
package com.example.shipping.service;

import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.shipping.config.ShippingProperties;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class ShippingServiceTest {

    @Test
    void previewUsesProvidedConfigurationAndCollaborators() {
        ShippingProperties properties = new ShippingProperties(
                true,
                URI.create("https://test.example.invalid/api/"),
                Duration.ofSeconds(2),
                4
        );

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );

        ShippingService service = new ShippingService(
                properties, client, fixedClock
        );

        String preview = service.preview();

        assertTrue(preview.contains(
                "https://test.example.invalid/api/v1/shipments"));
        assertTrue(preview.contains("maxAttempts=4"));
        assertTrue(preview.contains("connectTimeout=PT2S"));
        assertTrue(preview.contains("2026-01-01T00:00:00Z"));
    }
}
```

This test highlights clean boundaries:

- `ShippingProperties` can be instantiated directly.
- `HttpClient` and `Clock` are independent collaborators.
- `ShippingService` is a plain Java class with an explicit constructor.
- No mocking `Environment`, no dependence on active profiles or YAML paths.
- The test sends zero network requests because `preview()` only constructs a string.

In real business code, `HttpClient` can be wrapped behind an application-defined adapter interface, using a fake in unit tests. Actual HTTP calls should be tested separately with a mock server or integration tests. Never force every unit test to depend on a live HTTP client when testing pure business decisions.

## 16. Testing Binding Separately from Business Logic

The service unit test above only verifies how the service handles objects passed into it. It **does not verify** that `shipping.connect-timeout: 2s` is converted to `Duration.ofSeconds(2)` by the binder.

To verify binding, use a test with a Spring context or `ApplicationContextRunner`.

Example with Spring Boot Test and JUnit 5:

```java
package com.example.shipping;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.shipping.config.ShippingProperties;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "shipping.enabled=true",
    "shipping.base-url=https://integration.example.invalid/api/",
    "shipping.connect-timeout=750ms",
    "shipping.max-attempts=5"
})
class ShippingApplicationTest {

    @Autowired
    ShippingProperties shippingProperties;

    @Test
    void bindsExternalizedValuesToTypedProperties() {
        assertTrue(shippingProperties.enabled());
        assertEquals(
            URI.create("https://integration.example.invalid/api/"),
            shippingProperties.baseUrl()
        );
        assertEquals(
            Duration.ofMillis(750),
            shippingProperties.connectTimeout()
        );
        assertEquals(5, shippingProperties.maxAttempts());
    }
}
```

This test specifically verifies:

1. Test properties are supplied to the Spring context.
2. The Binder converts values from configuration sources into Java types.
3. `ShippingProperties` is registered via `@EnableConfigurationProperties`.
4. Fields hold the expected values.

The sample app has an `ApplicationRunner` that prints the preview at context startup. That makes no HTTP calls, though it prints a log line during tests; in real applications, structure test startup so dangerous side effects do not execute during tests.

We can now separate two test categories:

| Test | Purpose | Needs Spring Context? |
| --- | --- | --- |
| `ShippingService` unit test | Logic using data and collaborators | No |
| `ShippingProperties` binding test | Key names, type conversion, and bean registration | Yes, or purposeful Binder setup in tests |
| Outbound gateway integration test | API interaction and client settings | Usually needs test environment / mock server |

Because of this separation, when a test fails, you immediately know whether the bug is in **configuration**, **bean wiring**, or **business logic**.

## 17. Should Computed Helper Methods Live in Properties Classes?

A pure-data record can include small derived helper methods if they are truly natural derivations of configuration itself. For example:

```java
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        URI baseUrl,
        Duration connectTimeout
) {
    public URI shipmentsUri() {
        return baseUrl.resolve("v1/shipments");
    }
}
```

Deriving a URI from existing values is a pure transformation with no external service calls. This can be reasonable if multiple components need the exact same derivation and the URL convention is stable.

However, pause and reconsider if a method begins:

- Calling an external API to look up an endpoint.
- Querying a database to determine shipping policies.
- Reading the user's security context.
- Writing files or updating a cache.
- Selecting complex multi-branch business workflows.

Those behaviors are no longer "configuration values"; they belong in services, adapters, or dedicated components.

A simple litmus test: **Properties should be instantiable with `new` and understandable without Spring or external environments.** If creating properties requires a repository, clock, HTTP client, and transaction manager, the boundary is wrong.

## 18. When a Bean Needs Configuration, Yet Its Source Code Cannot Be Edited

Many libraries provide infrastructure classes the application does not own. In such cases, use a `@Bean` method as a configuration adapter:

```java
@Configuration
public class ThirdPartyConfiguration {

    @Bean
    SomeThirdPartyClient thirdPartyClient(
            ThirdPartyProperties properties) {
        return SomeThirdPartyClient.builder()
                .endpoint(properties.endpoint())
                .timeout(properties.timeout())
                .build();
    }
}
```

`SomeThirdPartyClient` and `ThirdPartyProperties` here are illustrative types. The core idea is **keeping data in the properties class**, while the bean method builds the library object via the library's public API.

Spring Boot also allows placing `@ConfigurationProperties` directly on a `@Bean` method when binding onto a third-party mutable JavaBean with suitable setters. That is a distinct pattern dependent on the target class's bindability; it does not mean injecting services into a properties record constructor.

When a library uses builders and also requires other collaborator beans, an explicit `@Bean` factory method like the example above generally provides better control.

## 19. When Configuration Changes While the Application Is Running

Normally, `ShippingProperties` is bound during application context startup; `HttpClient` is also built from the timeout value at bean creation time.

Suppose an operator changes `shipping.connect-timeout` from `2s` to `500ms` in an external file after the process has started. Do not assume that:

- `ShippingProperties.connectTimeout()` automatically sees the new value.
- The existing `HttpClient` automatically changes its timeout.
- Every business bean holding the old reference automatically refreshes.

A standard Spring Boot application typically needs a restart to apply configuration changes cleanly and predictably. If dynamic configuration refresh is required, design explicit mechanisms to update properties objects, recreate infrastructure beans, and handle in-flight requests safely.

This also ties back to record immutability: records are convenient precisely because values stay fixed after creation. If live updates without restarts are required, build an explicit state-management model instead of silently mutating property fields across threads.

## 20. Common Mistakes When Separating Configuration

### 20.1. Both `@ConfigurationProperties` and `@Component` on a Record

`@Component` routes a class into component scanning under standard bean creation, whereas a `@ConfigurationProperties` record expects the Spring Boot binder to supply constructor arguments from external properties. For constructor binding, register the record via `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan` as shown, rather than relying on `@Component`.

### 20.2. Injecting Repositories/`HttpClient` into Properties Constructors

`@ConfigurationProperties` is not a service locator. `URI`, `Duration`, and `boolean` parameters are configuration data; `Repository` or `HttpClient` are bean dependencies. Create those in `@Configuration` or inject them straight into services that need them.

### 20.3. Service Reading `Environment` Again Despite Having Properties

If a service receives `ShippingProperties` yet still calls `environment.getProperty("shipping.max-attempts")`, the application has **two paths accessing the same value**. This complicates testing and risks divergence if one path has its own fallback. Stick to one explicit contract unless there is a genuine technical need for dynamic lookup.

### 20.4. Putting All Business Logic into Properties

`ShippingProperties` should hold timeouts and retry limits, not call APIs to dispatch shipments or decide refunds. Name classes to match their roles: `ShippingProperties` for data; `ShippingService` for business logic; `ShippingClient` for communication.

### 20.5. Splitting into Too Many Tiny Records Without Reason

If every single property gets its own class, reading and wiring become tedious. Group values that share lifecycles and domain meaning. There is no rule saying "one class per property"; the goal is **clear boundaries**, not maximizing class count.

### 20.6. Putting Real Passwords into Committed Files

Externalized configuration does not mean all data is safe to store in version control. Profiles and `@ConfigurationProperties` do not encrypt secrets. Use proper secret delivery channels and avoid logging entire properties objects.

### 20.7. Assuming YAML Always Wins

Command-line arguments, environment variables, external JAR configs, test properties, and other sources have distinct precedence ranks. The Binder uses the effective resolved value, not necessarily what appears in a specific YAML file.

### 20.8. Forgetting to Validate Business Constraints

Successfully converting `"-3"` to `int -3` does not make `maxAttempts=-3` valid configuration. Use validation during binding and cross-field consistency checks where needed.

### 20.9. Creating Cycles Between Services and Infrastructure Configuration

If `ShippingService` depends on `HttpClient`, while the `HttpClient` factory method calls `ShippingService` to ask for its timeout, you create a circular dependency. Fix it by having the client factory consume `ShippingProperties` directly instead of routing through the service.

## 21. Design Workflow When Adding a New Configuration Group

When asked to "integrate a new partner with timeout, URL, and retries," proceed in order:

1. **List operational parameters:** endpoints, timeouts, flags, retry limits.
2. **Choose a consistent prefix:** e.g., `partner.orders.*`, with readable kebab-case names.
3. **Create a typed `@ConfigurationProperties` class:** use `URI`, `Duration`, `int` rather than keeping everything as `String`.
4. **Register the class with the Boot Binder:** use `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`.
5. **Place defaults in one intentional location:** base configuration or binder defaults, avoiding conflicting defaults.
6. **Validate correctness:** required keys and value ranges.
7. **Assemble infrastructure beans in `@Configuration`:** e.g., HTTP clients, message producers, executors.
8. **Inject the configuration object and collaborators into services via constructors.**
9. **Unit test services with directly instantiated objects; test binding in a separate test.**
10. **Run once with a higher-precedence override** to prove no Java code changes are needed across environments.

Responsibility diagram:

```text
Key names + values
        |
        v
  ShippingProperties
        |
        +-----------------------+
        |                       |
        v                       v
InfrastructureConfiguration   ShippingService
        |                       ^
        v                       |
    HttpClient -----------------+
        |
        v
   Contains no business logic
```

This structure allows components to evolve relatively independently: settings can be supplied from new environments, clients can add proxy configuration, and services can update processing policies without changing how YAML is read.

## 22. Practice Exercises

### Exercise 1: Extracting Configuration from a Service Using `@Value`

Given:

```java
@Service
public class ImportService {

    @Value("${import.enabled:true}")
    private boolean enabled;

    @Value("${import.batch-size:100}")
    private int batchSize;

    @Value("${import.storage-url}")
    private String storageUrl;
}
```

Create `ImportProperties` with prefix `import`, using `boolean`, `int`, and `URI`, register it with `@EnableConfigurationProperties`, and refactor `ImportService` to constructor injection.

Once done, `ImportService` no longer knows the three raw key names and no longer has to convert the URL string to `URI`.

### Exercise 2: Creating a Bean Needing Both Properties and `Clock`

Suppose `BatchScheduler` needs `ImportProperties` and `Clock`. Place `Clock` in a separate `@Configuration` class, then inject both dependencies into `BatchScheduler`.

Do not add `Clock` to the `ImportProperties` record just to obtain system time. A clock is a collaborator bean, not configuration data.

### Exercise 3: Swapping an Infrastructure Bean Without Modifying the Service

Create an interface:

```java
public interface DeliveryGateway {
    String sendPreview(String orderId);
}
```

Create a real implementation and a fake implementation in two separate classes. `ShippingService` depends solely on `DeliveryGateway` and `ShippingProperties`. In a unit test, inject the fake gateway to verify service decisions without network calls.

Demonstrate that the service neither constructs the HTTP adapter directly nor reads YAML to find out which implementation is active.

### Exercise 4: Invalid Value Constraints

Provide in turn:

```properties
shipping.max-attempts=0
shipping.connect-timeout=-1s
shipping.base-url=
```

Determine which condition is caught by type conversion, which requires Bean Validation, and which requires a custom business rule. Do not expect defaults to silently fix every invalid case.

### Exercise 5: Source Override

Keep `shipping.max-attempts=3` in YAML, then launch with:

```bash
java -jar app.jar --shipping.max-attempts=7
```

Predict the value of `ShippingProperties.maxAttempts()` and the output of `ShippingService.preview()`. Explain why the service does not need to know a command-line argument was passed.

### Exercise 6: Identifying Responsibilities

Categorize these requirements:

| Task | Where Should It Live? |
| --- | --- |
| Declare endpoint | `@ConfigurationProperties` |
| Convert string `2s` to `Duration` | Spring Boot Binder |
| Construct client with 2-second timeout | `@Configuration` or client factory |
| Validate order has complete shipping address | Business service |
| Call shipping API | Gateway/client adapter |
| Simulate time in unit tests | Fake/fixed `Clock` in tests |
| Switch endpoint between staging and prod | External configuration sources |
| Choose retry policy based on error type | Service or retry policy |
| Verify `maxAttempts >= 1` | Configuration validation |

The objective is not memorizing a fixed folder layout, but recognizing the boundary between data, assembly, and behavior.

## 23. Summary

`@ConfigurationProperties` is used to **represent a group of configuration values** under one prefix, with concrete Java types and centralized validation. It establishes a clean contract between external configuration sources and the code consuming those values.

A well-separated design follows this flow:

```text
Config sources (application.yml, env, CLI...)
             |
             v
         Boot Binder
             |
             v
     ShippingProperties
             |
      +------+------+
      |             |
      v             v
Build HttpClient  ShippingService <--- Clock bean
      |             ^
      +-------------+
                    |
                    v
            Business logic
```

Remember three key distinctions:

1. **Configuration properties are not services:** they model data, not replace business logic.
2. **Configuration properties are not where arbitrary beans get injected:** combining properties with `HttpClient`, `Clock`, or repositories belongs in `@Configuration`, services, or dedicated factories.
3. **The same service runs across all environments:** the binder resolves configuration sources by precedence, builds typed objects, and the Spring container passes them to services without changing Java logic.

As the number of properties or collaborator beans grows, split groups by domain meaning, establish clear boundaries, use constructor injection and proper validation, and test binding separately from business logic. That is the greatest architectural value of `@ConfigurationProperties`: not merely "reading YAML," but making applications **easy to reconfigure, easy to swap infrastructure, easy to test, and easy to maintain**.

Further reading: [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties), and [Spring Framework — Bean Definitions](https://docs.spring.io/spring-framework/reference/core/beans/definition.html).
