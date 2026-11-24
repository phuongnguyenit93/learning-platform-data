# Binding Properties to Default Beans Without Mixing Business Logic into Configuration

## 1. The Problem to Solve

When building a library or Spring Boot starter, we usually want users to simply add a dependency, set a few properties in `application.yml`, and immediately get a default bean. At the same time, the library must let the application replace that bean when a custom implementation is needed.

For example, a library integrating with a product catalog system has a `CatalogClient`. The application needs to change `baseUri`, `timeout`, and maximum attempts via configuration. These values are **operational and connection parameters**; they should not pull business logic such as validating product codes, choosing queries, calculating prices, or processing responses into `@ConfigurationProperties` or the auto-configuration's `@Bean` method.

The design separates into **three responsibilities**:

1. **`@ConfigurationProperties`** — defines *configuration data*, default values, and configuration validity constraints. This class does not execute use cases.
2. **`@AutoConfiguration` + `@Bean`** — decides *when* to create the default bean and *wires configuration values* into the implementation's constructor/factory. This is the assembly (wiring/composition) layer.
3. **Implementation and business service** — executes *behavior*, validates business inputs, builds requests, calls dependencies, transforms results, and applies domain rules. This class receives needed configuration via constructor rather than reading `application.yml` directly.

Goal: users control supported options via properties, while business code remains independently testable; auto-configuration still backs off if the application supplies a replacement bean.

## 2. Dependency Model and Execution Flow

```text
application.yml / application.properties / env vars / CLI
                          |
                          v
                Spring Environment
                          |
                          v
                Spring Boot Binder
                          |
                          v
            CatalogClientProperties
              (baseUri, timeout,
                 maxAttempts)
                          |
                          v
             CatalogAutoConfiguration
      @EnableConfigurationProperties
      @ConditionalOnMissingBean(CatalogClient.class)
                          |
                          v
            new DefaultCatalogClient(...)
                          |
                          v
             CatalogClient interface
                          |
                          v
          ApplicationService / controller
               calls planFor(sku)
                          |
                          v
        Behavior executes in DefaultCatalogClient
```

What matters is the *dependency arrow*: the implementation receives type-converted values through its constructor; it does not depend on `Environment` or Spring Boot's binding API. The business service depends on the `CatalogClient` interface, not on the auto-configuration class.

### Concrete Separation of Responsibilities

| Component | Should contain | Should not contain |
| --- | --- | --- |
| `CatalogClientProperties` | `URI baseUri`, `Duration timeout`, `int maxAttempts`, defaults, configuration validation rules | Making HTTP calls, branching by order, calling repositories, actual request retries, transforming responses |
| `CatalogAutoConfiguration` | `@EnableConfigurationProperties`, bean/property conditions, concise `@Bean` factory, selecting default implementation | Business algorithms, retry loops, price calculation, JSON handling, controller logic |
| `DefaultCatalogClient` | Using endpoint/timeout/retry, building requests, error handling, and real client behavior | Reading `application.yml` directly, querying `Environment` on every call |
| `ApplicationService` | Use cases, domain rules, orchestrating multiple dependencies | Instantiating default clients directly or deciding starter bean conditions |

There is no rule banning every `if` statement in `@Configuration`: **configuration conditions** such as "library class present", "user provided a bean", or "enable property" still belong to the wiring layer. Separate **business logic** from **component selection logic**.

## 3. Naming and Defining Library Properties

Suppose the library chooses the `acme.catalog` prefix:

```yaml
acme:
  catalog:
    enabled: true
    base-uri: https://catalog.example.test/api
    timeout: 5s
    max-attempts: 4
```

Meaning:

- `enabled`: policy for creating **the default bean**, not a global switch forbidding the application from registering another client itself.
- `base-uri`: integration endpoint; use `URI` in Java to avoid manual string conversion everywhere.
- `timeout`: uses `Duration`, allowing the binder to accept `500ms`, `2s`, `1m` in Spring Boot's supported syntax.
- `max-attempts`: total number of attempts **the implementation** may use; the retry algorithm, retried exceptions, and backoff must live in the client code/retry policy, not in properties getters.

Key names should use the library's namespace to avoid conflicts with `spring.*` or another starter. Class names should also express clear boundaries, such as `CatalogClientProperties` and `CatalogAutoConfiguration`.

### Default Values Have Two Very Different Places

You can write:

```java
private Duration timeout = Duration.ofSeconds(2);
```

If `acme.catalog.timeout` is absent, the binder can leave this default intact on the `CatalogClientProperties` object. However:

```java
environment.getProperty("acme.catalog.timeout"); // may be null
```

Defaults in Java **do not automatically add keys to Environment**. Therefore, if `enabled` has default `true` in properties, the condition in auto-configuration needs `matchIfMissing=true` to explicitly describe the missing-key case. Do not assume `@ConditionalOnProperty` will read the properties bean's `isEnabled()` getter.

Set sensible defaults for the library, allow overrides from Environment, and **do not simultaneously hard-code a different default** in the implementation. The constructor may validate input values, but it should receive all final options passed from the wiring layer.

## 4. How to Connect Configuration to the Default Bean?

In Spring Boot 3.x, the clear approach for a library is:

```java
@AutoConfiguration
@EnableConfigurationProperties(CatalogClientProperties.class)
class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    @ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    CatalogClient catalogClient(CatalogClientProperties properties) {
        return new DefaultCatalogClient(
            properties.getBaseUri(),
            properties.getTimeout(),
            properties.getMaxAttempts()
        );
    }
}
```

*This is an illustrative snippet*. The related classes and full imports appear in the runnable example in section 6.

Four annotations play distinct roles:

- `@AutoConfiguration`: marks the library's configuration class so Spring Boot can apply it automatically when the starter is properly registered.
- `@EnableConfigurationProperties(CatalogClientProperties.class)`: requests creating and binding the properties bean. A library must not assume the application will enable `@ConfigurationPropertiesScan` for it.
- `@ConditionalOnMissingBean(CatalogClient.class)`: if the application has already declared a suitable `CatalogClient`, **do not create the default bean**. Users keep the right to swap implementations.
- `@ConditionalOnProperty(...)`: only decides whether to create the default bean when the property is enabled; `matchIfMissing=true` treats a missing key as enabled per the sample policy.

**Design point:** the `catalogClient(...)` method only wires dependencies and calls the constructor. All business code executed when using the client resides in `DefaultCatalogClient` or in corresponding services.

### Why Do Conditions Usually Need to Live in Auto-Configuration?

`@ConditionalOnMissingBean` inspects **bean definitions already processed up to the moment the condition runs**. Spring Boot orders auto-configuration after ordinary application configurations, making it the right place for defaults to back off before user beans. Placing this logic in an arbitrary `@Configuration` class and assuming all beans already exist can produce order-dependent results.

In addition, `@ConditionalOnMissingBean(CatalogClient.class)` checks **the type**, without requiring the user bean to be named `catalogClient`. A bean `@Bean CatalogClient customClient()` can prevent the default from being created. The condition also has candidate bean filtering rules and search strategies; check the Javadoc for your exact version when using complex hierarchies.

## 5. Keeping Business Logic Out of Configuration Classes: Right and Wrong Examples

### Example of What Not to Do

```java
// Anti-pattern: mixing wiring, I/O operations, and business logic
@Bean
CatalogClient catalogClient(CatalogClientProperties properties) {
    if (properties.getMaxAttempts() > 3) {
        // Call an API or repository to determine priority customers.
        // Retry loop and result handling right inside the bean factory.
    }
    return ...;
}
```

This is **non-compilable pseudocode**, meant only to highlight the crossed boundary. Loading data, computing policies, or performing I/O as part of bean selection makes startup hard to test and hard to trace.

### Better Structure

```java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient(CatalogClientProperties p) {
    return new DefaultCatalogClient(p.getBaseUri(), p.getTimeout(), p.getMaxAttempts());
}
```

And in the **implementation**:

```java
@Override
public QueryPlan planFor(String sku) {
    if (sku == null || sku.isBlank()) {
        throw new IllegalArgumentException("SKU must not be blank");
    }

    String code = URLEncoder.encode(sku, StandardCharsets.UTF_8);
    return new QueryPlan(
        URI.create(baseUriAsString + "/items?sku=" + code),
        timeout,
        maxAttempts
    );
}
```

This is also **an excerpt**; fields/imports appear in the full example below. The client class validates input and decides how to build a request plan; the properties class only holds configuration. If `planFor` is replaced with real HTTP operations, request/response handling still belongs to the adapter, while business decisions such as SKU selection and how results are used normally live in the application service.

In the example, building `QueryPlan` allows testing wiring without network access or credentials. It **does not send HTTP requests** or perform retries itself; `timeout`/`maxAttempts` are simply information the adapter will use when constructing the real HTTP client.

## 6. Java 17 + Spring Boot 3.5 Example: Runnable, Testing All Branches

The example consists of a Maven file and a test file. `CatalogClient` returns an immutable `QueryPlan`: a URI built from the base URI and URL-encoded SKU, along with timeout and maximum attempts. No real service is called, making it easy to verify bound values and each class's responsibility.

### Directory Structure

```text
catalog-starter-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── CatalogAutoConfigurationTest.java
```

### File `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>catalog-starter-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### File `src/test/java/example/CatalogAutoConfigurationTest.java`

```java
package example;

import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CatalogAutoConfigurationTest {

    // 1. Data-only: holds configuration and defaults, contains no business logic.
    @ConfigurationProperties(prefix = "acme.catalog")
    public static class CatalogClientProperties {
        private boolean enabled = true;
        private URI baseUri = URI.create("https://catalog.example.test/api");
        private Duration timeout = Duration.ofSeconds(2);
        private int maxAttempts = 3;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public URI getBaseUri() {
            return baseUri;
        }

        public void setBaseUri(URI baseUri) {
            this.baseUri = baseUri;
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
    }

    // 2. Library API, independent of Spring.
    record QueryPlan(URI uri, Duration timeout, int maxAttempts) {}

    @FunctionalInterface
    interface CatalogClient {
        QueryPlan planFor(String sku);
    }

    // 3. Behavior in the implementation, not inside @Configuration.
    static final class DefaultCatalogClient implements CatalogClient {
        private final URI baseUri;
        private final Duration timeout;
        private final int maxAttempts;

        DefaultCatalogClient(URI baseUri, Duration timeout, int maxAttempts) {
            this.baseUri = baseUri;
            this.timeout = timeout;
            this.maxAttempts = maxAttempts;
        }

        @Override
        public QueryPlan planFor(String sku) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("SKU must not be blank");
            }

            String encoded = URLEncoder.encode(sku, StandardCharsets.UTF_8);
            String root = baseUri.toString();
            if (root.endsWith("/")) {
                root = root.substring(0, root.length() - 1);
            }

            URI uri = URI.create(root + "/items?sku=" + encoded);
            return new QueryPlan(uri, timeout, maxAttempts);
        }
    }

    // 4. Auto-configuration only does binding + wiring + back-off.
    @AutoConfiguration
    @EnableConfigurationProperties(CatalogClientProperties.class)
    static class CatalogAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
        )
        CatalogClient catalogClient(CatalogClientProperties p) {
            return new DefaultCatalogClient(
                p.getBaseUri(), p.getTimeout(), p.getMaxAttempts()
            );
        }
    }

    // 5. User replaces the interface implementation as needed.
    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        CatalogClient customCatalogClient() {
            return sku -> new QueryPlan(
                URI.create("https://custom.example.test/request"),
                Duration.ofMillis(250),
                1
            );
        }
    }

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(CatalogAutoConfiguration.class)
            );

    @Test
    void defaultsAreBoundToTheAutoConfiguredClient() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(CatalogClient.class);
            assertThat(context).hasBean("catalogClient");
            assertThat(context)
                .hasSingleBean(CatalogClientProperties.class);

            CatalogClient client = context.getBean(CatalogClient.class);
            QueryPlan plan = client.planFor("ABC 1");

            assertThat(plan.uri().toString()).isEqualTo(
                "https://catalog.example.test/api/items?sku=ABC+1"
            );
            assertThat(plan.timeout()).isEqualTo(Duration.ofSeconds(2));
            assertThat(plan.maxAttempts()).isEqualTo(3);

            assertThat(context.getEnvironment()
                .containsProperty("acme.catalog.timeout")).isFalse();
            assertThat(context.getBean(CatalogClientProperties.class)
                .getTimeout()).isEqualTo(Duration.ofSeconds(2));
        });
    }

    @Test
    void environmentPropertiesOverrideTheJavaDefaults() {
        runner.withPropertyValues(
                "acme.catalog.base-uri=https://override.example.test/v2/",
                "acme.catalog.timeout=5s",
                "acme.catalog.max-attempts=6"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(CatalogClient.class);

                QueryPlan plan = context.getBean(CatalogClient.class)
                    .planFor("A/B");

                assertThat(plan.uri().toString()).isEqualTo(
                    "https://override.example.test/v2/items?sku=A%2FB"
                );
                assertThat(plan.timeout()).isEqualTo(Duration.ofSeconds(5));
                assertThat(plan.maxAttempts()).isEqualTo(6);
            });
    }

    @Test
    void businessValidationLivesInTheClientNotTheProperties() {
        runner.run(context -> {
            CatalogClient client = context.getBean(CatalogClient.class);

            assertThatThrownBy(() -> client.planFor("   "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("SKU must not be blank");
        });
    }

    @Test
    void userProvidedBeanMakesTheDefaultBackOff() {
        runner.withUserConfiguration(UserClientConfiguration.class)
            .withPropertyValues("acme.catalog.timeout=7s")
            .run(context -> {
                assertThat(context).hasSingleBean(CatalogClient.class);
                assertThat(context).hasBean("customCatalogClient");
                assertThat(context).doesNotHaveBean("catalogClient");

                QueryPlan plan = context.getBean(CatalogClient.class)
                    .planFor("SKU-42");

                assertThat(plan.uri().toString())
                    .isEqualTo("https://custom.example.test/request");
                assertThat(plan.timeout())
                    .isEqualTo(Duration.ofMillis(250));
                assertThat(plan.maxAttempts()).isEqualTo(1);

                // User-created bean is not reconfigured by the default factory.
                assertThat(context.getBean(CatalogClientProperties.class)
                    .getTimeout()).isEqualTo(Duration.ofSeconds(7));
            });
    }

    @Test
    void disabledPropertyTurnsOffOnlyTheDefaultBean() {
        runner.withPropertyValues("acme.catalog.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(CatalogClient.class);
                assertThat(context)
                    .hasSingleBean(CatalogClientProperties.class);
                assertThat(context.getBean(CatalogClientProperties.class)
                    .isEnabled()).isFalse();
            });
    }

    @Test
    void disablingDefaultDoesNotForbidAUserBean() {
        runner.withUserConfiguration(UserClientConfiguration.class)
            .withPropertyValues("acme.catalog.enabled=false")
            .run(context -> {
                assertThat(context).hasSingleBean(CatalogClient.class);
                assertThat(context).hasBean("customCatalogClient");
                assertThat(context).doesNotHaveBean("catalogClient");
            });
    }
}
```

### How to Run

Use JDK 17 or higher, Maven, and an internet connection for Maven to fetch initial dependencies:

```bash
java -version
mvn -version
mvn test
```

**Expected result:** six JUnit tests pass; Maven exits with `BUILD SUCCESS`. There is no fixed business stdout string because the test program uses assertions and does not call `System.out.println`; detailed reports are written by Maven Surefire under `target/surefire-reports`.

Explanation:

- **Default:** with no configuration keys, Spring Boot binds the initialized values of `CatalogClientProperties`; the factory creates `DefaultCatalogClient` and the client receives the configuration via constructor. `Environment` still does not need to contain missing keys.
- **Properties override:** the Binder converts `base-uri` to `URI`, `timeout=5s` to `Duration`, and `max-attempts=6` to an integer. The default bean is created with the new values.
- **Behavior:** `planFor("   ")` throws an error because the SKU is invalid. The input validation rule resides in `DefaultCatalogClient`; properties have no `planFor` method and know nothing about business rules.
- **User bean:** when a differently named `CatalogClient` is supplied, `@ConditionalOnMissingBean` causes the default factory to back off. Properties are still bound, but are not forced onto the replacement bean.
- **Disable:** `acme.catalog.enabled=false` makes the **default bean's** condition fail to match. When the application provides its own client, that client is kept.

### Intentional Limitations of the Example

`QueryPlan` is merely data describing a request. In a real HTTP library, `DefaultCatalogClient` might use `RestClient`, `WebClient`, or an official SDK, pass `Duration` as client timeouts, execute a retry policy, and transform responses. Those tasks require library/API documentation and separate integration tests. Do not interpret the example above as a network-capable HTTP client.

To use auto-configuration in a **real starter**, create `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` in the library artifact and write the fully qualified auto-configuration class name. In the demo, `ApplicationContextRunner` actively loads the class via `AutoConfigurations.of(...)`, so an imports file is not needed.

## 7. Binding Properties to Beans: Choosing the Right Mechanism

There are two common patterns.

### 7.1. Bind to a Dedicated Properties Bean and Pass via Constructor (Recommended for Integrations)

```java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient(CatalogClientProperties p) {
    return new DefaultCatalogClient(
        p.getBaseUri(), p.getTimeout(), p.getMaxAttempts()
    );
}
```

This is an illustrative snippet using the example's classes. The advantage is that `DefaultCatalogClient` stays independent of Spring Boot, receives immutable parameters at construction time, and can be used/tested with plain Java.

If the constructor has many parameters, they can be grouped into an immutable **configuration value object** `ClientOptions`, created once inside the factory:

```java
public record ClientOptions(URI baseUri, Duration timeout, int maxAttempts) {}

@Bean
CatalogClient catalogClient(CatalogClientProperties p) {
    ClientOptions options = new ClientOptions(
        p.getBaseUri(), p.getTimeout(), p.getMaxAttempts()
    );
    return new DefaultCatalogClient(options);
}
```

This is an **illustrative** design alternative; the `DefaultCatalogClient` constructor must be updated accordingly—do not copy it alongside the three-parameter constructor in the demo and expect it to compile. A value object helps prevent positional parameter mistakes and avoids coupling Spring types to processing logic.

### 7.2. Bind Directly onto an Existing Bean with @ConfigurationProperties on @Bean

Spring Boot also allows placing `@ConfigurationProperties` on a `@Bean` method to bind properties onto the returned object. This is useful when configuring a third-party library class that has setters but **whose source code cannot be modified**:

```java
@Bean
@ConfigurationProperties(prefix = "acme.third-party")
ThirdPartyOptions thirdPartyOptions() {
    return new ThirdPartyOptions();
}
```

This snippet requires a `ThirdPartyOptions` class compatible with JavaBean binding and must register the bean in a valid configuration. It **is not equivalent** to placing `@ConfigurationProperties` on a domain service with side effects; the binder will call the object's setters, so make sure the object is a configuration object, not a service executing business logic.

When designing a new starter, the clearest approach is still to separate properties into their own type and create the business bean via a concise factory. Direct binding onto a third-party bean should be used when that API genuinely has a compatible property model.

## 8. Configuration Constraints and Business Constraints Are Two Different Things

Not "mixing business logic" does not mean properties are never validated. A **technical configuration value** must be valid before initializing the client.

Examples of sensible rules for `CatalogClientProperties`:

- `baseUri` must not be null and must be `http` or `https` if the library only supports HTTP.
- `timeout` must be positive if the adapter requires a wait time greater than 0.
- `maxAttempts` must be 1 or more; 0 or negative makes no sense for this retry design.

Those rules relate directly to the **configuration contract**. You can apply Jakarta Bean Validation with `@Validated` and appropriate constraints plus the `spring-boot-starter-validation` dependency, or validate when building immutable options. **Do not assume `spring-boot-starter-test` always supplies a full Bean Validation runtime for every starter.**

Conversely, "SKU must exist in inventory", "VIP customers get a 10% discount", and "orders above the limit require approval" are **business rules**. They belong to the service/domain or client adapter depending on responsibility, not to `CatalogClientProperties`.

### Note on Immutability

A mutable `@ConfigurationProperties` JavaBean with setters is suitable for standard binding. If you want immutable configuration, in Spring Boot 3.x you can use a record with constructor binding and `@DefaultValue` for components needing defaults. In that case, instantiation and validation flows differ from JavaBeans; do not mix both binding styles on the same object arbitrarily. Choose **one clear strategy**, and write tests for missing/overridden/invalid keys.

## 9. Choosing Where to Apply Defaults, Customization, and Replacement

There are three common sources of confusion as a library grows:

| Need | Tool | Notes |
| --- | --- | --- |
| Configure host, timeout, pool size, retry parameters | Properties + Binder | Ensure keys exist and are used by the factory |
| Add interceptors, codecs, or client construction tweaks that properties cannot express | Customizer hook if provided by the library | Auto-configuration must **invoke** that customizer while creating the bean |
| Replace the entire implementation or lifecycle | User bean + `@ConditionalOnMissingBean` in auto-configuration | Default bean backs off; properties/customizers of the default factory are not automatically applied to the user bean |

In practice, a starter can support both customizers and properties when building the default bean. However, there is no universal rule that properties always win over customizers or vice versa: **application order is determined by the starter's code**. If the default bean is skipped, that bean creation path does not run, so distinguish between "a customizer bean was created" and "the customizer was actually applied."

## 10. Common Mistakes When Designing a Starter

### Mistake 1 — Putting Services and Repositories into @ConfigurationProperties

A properties class with a `calculateDiscount(customer)` method or database calls makes configuration depend on business logic, hard to bind, and hard to test. Store only parameters and configuration validation here; move behavior to services/adapters.

### Mistake 2 — Reading Environment on Every Request

Code like `environment.getProperty("acme.catalog.timeout")` inside `planFor` couples the implementation to Spring, makes reuse difficult, and can apply inconsistent conversion/defaulting. For options fixed over a bean's lifecycle, bind once and inject via constructor. If a real application needs dynamic refresh, design a controlled update mechanism instead of treating per-call Environment lookups as an automatic fix.

### Mistake 3 — Creating Two Different Sets of Defaults

Having `CatalogClientProperties.timeout=2s` while `DefaultCatalogClient` hard-codes `5s` when config is missing creates two sources of truth. Pick one authoritative place for defaults and pass the final values through. Fallbacks can exist in the implementation if it is used outside Spring, but the contract must be documented and tested.

### Mistake 4 — Placing @ConditionalOnMissingBean in the Wrong Place or with the Wrong Type

`@ConditionalOnMissingBean(CatalogClient.class)` in an ordinary configuration class may be evaluated before necessary user beans appear. Place it in auto-configuration. Also, if the application provides `@Bean Object customClient()` and returns a `CatalogClient` at runtime, the condition may fail to infer the proper type from the bean definition. Declare the return type as `CatalogClient` or a concrete subtype so metadata is clear.

### Mistake 5 — Adding @Primary and Assuming the Default Bean Disappears

`@Primary` only adjusts injection priority when multiple candidates exist. Whether a bean is created is governed by auto-configuration conditions. If two beans still exist and logic relies on bean names or `@Qualifier`, `@Primary` does not cleanly solve the issue.

### Mistake 6 — Treating the `enabled` Property as a Switch That Deletes Every Bean

If `enabled=false` sits only on the default bean factory, it **does not block user beans**. To forbid an entire feature across an application, define an explicit policy at usage sites rather than trusting a factory condition to delete other beans.

### Mistake 7 — Assuming Any YAML File Change Takes Effect Immediately

Beans are created in the context with a snapshot of configuration at initialization time. Editing a config file does not guarantee an existing bean updates its timeout/lifecycle. Any dynamic refresh mechanism must be designed and tested separately.

### Mistake 8 — Having a `@Bean` Factory Make HTTP Requests or Open Connections at Startup

If a constructor or factory performs I/O, startup can be blocked by the network, tests have to mock external services, and endpoint failures prevent the ApplicationContext from starting. If a library needs eager startup checks, treat that as an explicit feature configured and tested intentionally; do not hide side effects inside wiring code.

### Mistake 9 — Believing Every `@Bean` Backs Off Automatically

Spring Boot auto-configuration **only** backs off when the corresponding condition is declared and satisfies candidate lookup rules. Read the actual annotations and write tests; never infer behavior solely from the name "AutoConfiguration."

### Mistake 10 — Undocumented Configuration or Overlapping Namespace Keys

Inconsistent names like `acme.catalog.timeout` and `acme.catalog.request-timeout` can cause users to change the wrong key. Maintain a clear prefix, IDE suggestion metadata, and a changelog when contracts change. For a published starter, you can add `spring-boot-configuration-processor` to generate configuration metadata, though metadata only supports tooling; it **does not automatically bind** or instantiate beans.

## 11. Testing All Branches of Auto-Configuration

A starter test suite should verify:

1. **Missing keys:** property defaults are accurate, and the default bean appears or stays absent per the contract.
2. **Overridden properties:** values from Environment are converted accurately by the binder, and the factory actually passes them into the implementation.
3. **Standalone behavior:** unit tests for the client/domain using direct constructor calls without starting a Spring context; business logic is not hidden in config.
4. **User replacement bean:** place a properly typed `CatalogClient` bean in user configuration and ensure the default backs off.
5. **Disable flag:** confirm only the scoped bean is suppressed.
6. **Invalid values:** validation produces clear messages, and startup does not ignore bad config and silently fall back to defaults.
7. **Multiple beans/conditions:** if the library has multiple implementations or customizers, test type/name competition, ordering, and qualifiers.
8. **Framework upgrades:** test against the Spring Boot versions the library claims to support, as package/API contracts may shift.

`ApplicationContextRunner` is a useful tool for spinning up lightweight contexts for bean condition branches. Each test should run an isolated context, using `withPropertyValues(...)` and `withUserConfiguration(...)` to supply needed inputs.

For logic that actually makes HTTP calls, write **separate unit and integration tests** for timeouts/retries, network errors, HTTP statuses, idempotency, and shutdown. The `QueryPlan` demo does not replace those tests.

## 12. Checklist Before Releasing a Library

- [ ] Keys are placed in a dedicated namespace, with clear defaults and appropriate Java types (`URI`, `Duration`, enum…).
- [ ] The `@ConfigurationProperties` class holds only configuration data and validation; it does not call domain services or repositories.
- [ ] Auto-configuration uses `@EnableConfigurationProperties`, registers the default bean, and mixes in no business logic.
- [ ] Business interface and implementation are separated; the implementation receives options via constructor or immutable options.
- [ ] `@ConditionalOnMissingBean` uses the right type and lives in auto-configuration so applications can swap implementations.
- [ ] If `enabled` exists, missing keys are handled with `matchIfMissing` matching the published default.
- [ ] Tested defaults, property overrides, user bean replacement, disabled state, and invalid config.
- [ ] Created `AutoConfiguration.imports` for the real starter and registered appropriate properties metadata.
- [ ] Documentation clearly explains what each property adjusts, whether changes require a restart, and which beans back off.

## 13. Self-Check Questions

**Question 1:** A method inside `@ConfigurationProperties` calls a repository to check whether a SKU is in stock. Is this appropriate?  
**Answer:** No; that is business/I/O logic. The properties class only holds and validates connection/configuration settings.

**Question 2:** `acme.catalog.timeout` is absent while the `timeout` field initializes to 2 seconds. Does `Environment#getProperty("acme.catalog.timeout")` necessarily return `"2s"`?  
**Answer:** No. Java object defaults are not automatically pushed into Environment.

**Question 3:** If an application declares `@Bean CatalogClient ownClient()`, will `@ConditionalOnMissingBean(CatalogClient.class)` still allow the default bean to be created?  
**Answer:** Usually no, provided the application bean has already been processed and qualifies as a candidate at the time the condition is evaluated.

**Question 4:** If `acme.catalog.enabled=false`, do all `CatalogClient` beans in the entire context disappear?  
**Answer:** No. The condition in the sample only controls the default bean factory; a user-supplied client can still exist.

**Question 5:** To make an HTTP integration client execute retries and handle responses, where should the loop/algorithm live?  
**Answer:** In the implementation/adapter or a dedicated retry policy it uses; properties only hold parameters like `maxAttempts`, and auto-configuration only wires dependencies.

**Question 6:** A `CatalogClientProperties` bean was bound, yet `DefaultCatalogClient` did not receive the new timeout. What should you diagnose first?  
**Answer:** Check whether the factory uses `getTimeout()` when constructing the client, whether a user bean caused the default to back off, and whether the property source has the exact key. Successful binding does not automatically push values into a custom bean.

## References

- Spring Boot 3.5 Reference — Externalized Configuration and Binding `@ConfigurationProperties`: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, bean conditions, and `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot API — `@EnableConfigurationProperties`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/EnableConfigurationProperties.html
- Spring Boot API — `@ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot Reference — Configuration Metadata: https://docs.spring.io/spring-boot/3.5/reference/configuration-metadata/annotation-processor.html

**Remember:** Properties answer **"what parameters does the default bean need?"**; auto-configuration answers **"which bean should be created, and how are parameters wired?"**; implementation/domain answers **"what is the actual behavior?"**. Separating layers cleanly makes a starter easy to configure, easy to replace, and prevents business logic from depending on Spring Boot.
