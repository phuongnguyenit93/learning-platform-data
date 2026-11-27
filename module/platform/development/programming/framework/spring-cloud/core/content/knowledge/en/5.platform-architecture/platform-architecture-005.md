# How Application-Declared Configuration Overrides Defaults

In Spring Boot and Spring Cloud, libraries commonly provide default values or default beans so applications can start with minimal configuration. When bringing an application into a concrete system, the development team needs to replace those defaults with appropriate choices: internal endpoints, timeouts, service discovery sources, instance selection rules, or implementations of an abstraction.

**Application-declared configuration overriding defaults** is how an application actively provides its own values or components for Spring to use instead of fallback options. Two mechanisms must be distinguished: **overriding properties in the Environment** and **replacing beans created by auto-configuration**. These two mechanisms are related, not identical.

This lesson belongs to the **Platform Architecture** chapter of the **SPRING_CLOUD_CORE** module. It focuses on Spring Boot configuration, Spring Cloud Commons/Context, extensibility via beans and customizers, interaction with external configuration, testing, and operations.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish library defaults, application configuration, per-environment configuration, and secrets.
- Explain how Spring Boot merges configuration sources in `Environment` and why environment variables or command-line arguments can override YAML files.
- Use `@ConfigurationProperties` to bind typed configuration, set defaults, and validate data.
- Understand how auto-configuration backs off when the application supplies its own beans, especially via `@ConditionalOnMissingBean`.
- Distinguish bean replacement from `@Primary`, `@Qualifier`, `@Order`, and bean definition overriding.
- Recognize Spring Cloud Commons extension points such as discovery, service registry, and load balancing.
- Test the configuration and actual bean selected, and diagnose why defaults are still used or why multiple beans of the same type exist.

## 2. Two Kinds of Defaults to Distinguish

The word "default" in Spring can refer to at least two different things.

### 2.1. Default of a Property

A library can provide a default value for a property, such as a timeout, port, strategy name, or feature flag. The application changes behavior by supplying the same key in a higher-precedence configuration source.

For example, a library uses a fallback value `demo.client.timeout=2s`. The application declares:

```yaml
demo:
  client:
    timeout: 5s
```

When a bean reads `demo.client.timeout`, the value `5s` is bound instead of the `2s` fallback. No bean is replaced in this example; only the **configuration value** changes.

### 2.2. Default of a Bean

Auto-configuration can create a default bean when classpath and conditions match. For example, a library supplies an `EndpointResolver` bean to choose default addresses. An application wanting its own rules can declare its own `EndpointResolver` bean.

Many auto-configurations are designed with `@ConditionalOnMissingBean`. When an application-declared bean already exists, the corresponding auto-configuration will **back off** and skip creating the fallback bean. Here, the application replaces the **injected component**, not just a property string.

| Question | Overriding a property | Replacing a bean |
| --- | --- | --- |
| What changes | Value of a configuration key | Object managed by the Spring container |
| Primary mechanism | `Environment`, `PropertySource`, binding | `@Bean`, component scanning, auto-configuration conditions |
| Example | Change timeout from `2s` to `5s` | Use a custom-written resolver |
| What to verify | Final value and source of the property | Which bean is created and injected |
| Common risk | Higher-precedence source overrides unexpectedly | Multiple beans of the same type or auto-configuration fails to back off |

Not every property can replace a bean, and not every default bean has a property to replace it. Inspect the API and conditions of the component you are using.

## 3. How Spring Boot Merges Configuration in Environment

Spring Boot creates an `Environment` containing multiple `PropertySource`s. Each source provides key–value pairs. When the application reads a key, Spring searches for a value in the precedence order of active sources.

Common configuration sources:

- `application.yml` or `application.properties` files inside the artifact.
- External configuration files outside the artifact and profile-specific files like `application-prod.yml`.
- Process environment variables, e.g., `DEMO_CLIENT_TIMEOUT`.
- Java system properties, e.g., `-Ddemo.client.timeout=3s`.
- Command-line arguments, e.g., `--demo.client.timeout=4s`.
- Sources imported via `spring.config.import`, such as Config Server or config trees.
- Configuration sources added by frameworks or applications via Spring APIs.

In typical Spring Boot setups, command-line arguments take higher precedence than environment variables, and environment variables take higher precedence than regular config files. External configuration can override configuration packaged inside the JAR. However, exact precedence also depends on source type, file location, profiles, imports, and Boot version; do not apply one abbreviated list to every situation.

### 3.1. Example: Same Key Appearing in Multiple Sources

`application.yml`:

```yaml
demo:
  client:
    timeout: 2s
```

`application-prod.yml`:

```yaml
demo:
  client:
    timeout: 3s
```

Start with the production profile and an environment variable:

```powershell
$env:DEMO_CLIENT_TIMEOUT = '5s'
java -jar app.jar --spring.profiles.active=prod
```

If no higher-precedence source intervenes, the environment variable supplies `5s` and overrides the values in the config files. If you add an argument:

```bash
java -jar app.jar --spring.profiles.active=prod --demo.client.timeout=4s
```

then the command-line argument `4s` typically wins over the environment variable `5s` in a standard Spring Boot application.

**Key point:** a profile file does not automatically win over an environment variable just because it is named `prod`. Profiles decide which configuration documents are activated; precedence order between sources decides the final value.

### 3.2. External Configuration and Profiles

You can place configuration files outside the JAR and specify their location at runtime:

```bash
java -jar app.jar --spring.config.additional-location=file:./config/
```

`spring.config.additional-location` adds locations for Spring Boot to search for configuration; `spring.config.location` replaces default locations in certain usages. Read the docs for your exact Boot version before choosing, because replacing locations by mistake can stop the application from loading expected config files.

In deployment environments, clearly specify:

- Which default configuration is packaged inside the artifact.
- Which configuration is supplied externally by the platform.
- Which profiles are enabled per environment.
- Which keys are mandatory and must fail fast if missing.
- Which sources are allowed to override sensitive or security-affecting keys.

Do not provide harmless default values for mandatory production keys if doing so could let the application run against the wrong environment without failing.

## 4. Setting Defaults and Binding Typed Configuration

For a single property, `@Value` supports expressions with fallback values:

```java
@Value("${demo.client.timeout:2s}")
private Duration timeout;
```

If `demo.client.timeout` does not exist, the expression uses `2s`. If a configuration source supplies a value, Spring converts it to `Duration`. This is convenient for simple values, but when multiple related keys exist, use `@ConfigurationProperties`.

### 4.1. Creating a Properties Class

`ClientProperties.java`:

```java
package com.example.platform.config;

import java.time.Duration;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.client")
public class ClientProperties {

    @NotBlank
    private String baseUrl = "http://localhost:8081";

    @NotNull
    private Duration timeout = Duration.ofSeconds(2);

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

Registering the properties class in the application:

```java
package com.example.platform;

import com.example.platform.config.ClientProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class PlatformApplication {

    public static void main(String[] args) {
        SpringApplication.run(PlatformApplication.class, args);
    }
}
```

In large projects, `@ConfigurationPropertiesScan` can scan properties classes instead of listing each one individually. Ensure scanned packages reside under the root package or specify scan packages explicitly.

### 4.2. Application Replaces Fallback Values

`application.yml`:

```yaml
demo:
  client:
    base-url: https://inventory.internal
    timeout: 5s
```

`ClientProperties` defaults to `localhost:8081` and `2s`. The application's config file supplies a different endpoint and timeout, so the values bound to the bean become `https://inventory.internal` and `5s`.

You can use the `DEMO_CLIENT_TIMEOUT` environment variable or `--demo.client.timeout` argument to further override the YAML file when running in a specific environment.

### 4.3. Default Does Not Equal Safe Fallback

Java field initializers or annotation defaults are used only when no other value is bound. Evaluate whether a fallback makes sense:

- Timeouts can have reasonable defaults, yet must still be safe for latency and retry budgets.
- Mock server URLs fit dev/test only; they should never be production fallbacks.
- API keys and passwords must never have default values in source code.
- Mandatory properties should be validated and prevent startup if missing.

If you want a production endpoint to be mandatory, omit the default value and declare validation:

```java
@NotBlank
private String baseUrl;
```

When `demo.client.base-url` is missing, validation fails during properties bean creation (with an appropriate validation dependency), catching missing configuration before the application receives traffic.

## 5. Auto-Configuration and the Back-Off Mechanism

Spring Boot auto-configuration relies on classpath, conditions, and beans already in the container to create appropriate configuration. Libraries can provide default beans to reduce boilerplate for applications. A common pattern is `@ConditionalOnMissingBean`.

The following example simulates an internal library providing a default endpoint resolver.

### 5.1. Shared Contract

`EndpointResolver.java`:

```java
package com.example.platform.endpoint;

public interface EndpointResolver {
    String resolve(String serviceName);
}
```

### 5.2. Library's Default Configuration

`DefaultEndpointAutoConfiguration.java`:

```java
package com.example.platform.endpoint.autoconfigure;

import com.example.platform.endpoint.EndpointResolver;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class DefaultEndpointAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(EndpointResolver.class)
    EndpointResolver defaultEndpointResolver() {
        return serviceName -> "http://" + serviceName + ":8080";
    }
}
```

`@ConditionalOnMissingBean(EndpointResolver.class)` means: create the default bean only if, at condition evaluation time, the container does not already contain a matching bean of type `EndpointResolver`. When the application declares a bean implementing the same contract, auto-configuration can back off.

In a real auto-configuration library, the configuration class must be registered via Spring Boot's auto-configuration imports mechanism (`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` in modern Boot generations). This example illustrates the condition mechanism; placing a class in a package alone does not make it automatically discovered as auto-configuration by every application.

### 5.3. Application Provides Its Own Implementation

`ApplicationEndpointConfiguration.java`:

```java
package com.example.platform;

import com.example.platform.endpoint.EndpointResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ApplicationEndpointConfiguration {

    @Bean
    EndpointResolver applicationEndpointResolver() {
        return serviceName -> {
            if ("inventory".equals(serviceName)) {
                return "https://inventory.prod.internal";
            }
            return "https://" + serviceName + ".prod.internal";
        };
    }
}
```

When this bean is already registered before auto-configuration evaluates conditions, `@ConditionalOnMissingBean` does not match and the default bean is not created. The application uses its own implementation.

Expected results:

| Service name | Default resolver | Application-provided resolver |
| --- | --- | --- |
| `inventory` | `http://inventory:8080` | `https://inventory.prod.internal` |
| `catalog` | `http://catalog:8080` | `https://catalog.prod.internal` |

In real projects, endpoints should normally be configured via properties or discovery rather than string-concatenating hosts as shown here. This example merely clarifies replacing an implementation at an abstraction boundary.

### 5.4. Why Does Auto-Configuration Order Matter?

Bean conditions are evaluated during application context refresh. Spring Boot auto-configurations are ordered by the framework's mechanisms; bean definitions from regular application configurations can usually be detected so `@ConditionalOnMissingBean` backs off.

Do not create an arbitrary auto-configuration at the same priority level and assume its conditions will always see beans registered later. For libraries, use proper auto-configuration annotations and ordering, test with `ApplicationContextRunner`, and check the condition evaluation report if behavior differs from expectations.

## 6. Replacing a Bean Differs from Selecting a Bean at Injection

Several annotations are frequently misunderstood as "overriding defaults".

### 6.1. `@Primary` Selects a Preferred Bean

`@Primary` marks one bean as the preferred candidate when Spring needs to inject a single bean among multiple beans of the same type. It **does not remove** the other beans. If auto-configuration uses `@ConditionalOnMissingBean`, the presence of an application bean of the same type causes the condition to back off; that happens because the bean already exists, not because of `@Primary`.

```java
@Bean
@Primary
EndpointResolver preferredEndpointResolver() {
    return serviceName -> "https://" + serviceName + ".internal";
}
```

If there is a default bean and a `@Primary` bean, both can coexist when the default configuration does not use a back-off condition. Single-bean injection of `EndpointResolver` picks the primary bean where applicable, yet code injecting a list of beans still sees both.

### 6.2. `@Qualifier` Specifies Exactly Which Bean to Use

```java
public InventoryClient(
        @Qualifier("inventoryEndpointResolver")
        EndpointResolver resolver) {
    this.resolver = resolver;
}
```

`@Qualifier` selects a specific bean by qualifier/name at injection time. It does not replace the default implementation across the entire application.

### 6.3. `@Order` Affects Ordering, Not Replacement

For extensions collected into a list by Spring or executed sequentially, `@Order` can influence processing order. It does not make another bean of the same type disappear and is not a tool for replacing auto-configuration.

### 6.4. Bean Definition Overriding

Spring has a setting that allows or rejects a later-registered bean definition with the same name replacing an earlier definition, depending on configuration. Do not rely on bean name collisions to customize auto-configuration. A cleaner approach is using documented extension points, `@ConditionalOnMissingBean`, or dedicated configuration per the library's API.

Do not enable `spring.main.allow-bean-definition-overriding=true` merely to mask conflicts. Duplicate names can make outcomes depend on configuration load order and become hard to diagnose during upgrades.

## 7. Overriding Defaults in Spring Cloud Commons

Spring Cloud Commons provides abstractions so applications can work with distributed infrastructure without coupling directly to a specific product. Applications can choose implementations or customize via extension points provided by components.

### 7.1. DiscoveryClient and ServiceRegistry

`DiscoveryClient` provides an API to look up service instances by name. `ServiceRegistry` provides an abstraction to register and deregister instances. These abstractions do not create a registry themselves; a concrete implementation (such as Eureka or Consul) and connection configuration are needed.

When using a discovery implementation, start by configuring the client according to its documentation. Provide your own `DiscoveryClient` or `ServiceRegistry` implementation only when you genuinely need custom registry integration or a specialized instance source. Adding a bean of the same type can affect auto-configuration conditions and client selection; verify against the exact release train in use.

Example of how an application uses the abstraction:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class ServiceLookup {

    private final DiscoveryClient discoveryClient;

    public ServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances(String serviceId) {
        return discoveryClient.getInstances(serviceId);
    }
}
```

This code only queries instances provided by the discovery client. If no registry is configured or the implementation returns an empty list, the result can also be empty. You cannot conclude the application registered successfully simply because the context started.

### 7.2. Spring Cloud LoadBalancer

Spring Cloud LoadBalancer provides an abstraction for selecting an instance from `ServiceInstance` sources. Applications can use the default strategy or customize per service. For a specific service, `@LoadBalancerClient` allows declaring custom configuration for a named client.

Example illustrating custom configuration for the `inventory` service:

```java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
    name = "inventory",
    configuration = InventoryLoadBalancerConfiguration.class
)
public class LoadBalancerClientsConfiguration {
}
```

Named client configuration:

```java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryInstances(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withCaching()
            .build(context);
    }
}
```

This example illustrates declaring an instance supplier for a named client; it requires LoadBalancer and matching discovery dependencies. Do not place named-client-specific configuration into global component scanning if doing so makes its beans global configuration; keep the configuration class out of normal application scanning and let `@LoadBalancerClient` reference it.

When you need to change instance selection strategy, use the extension points supported by your Spring Cloud LoadBalancer version (e.g., `ReactorLoadBalancer` or `ServiceInstanceListSupplier`), and determine whether the scope is global or single-service. Do not replace the entire LoadBalancer just to change an existing property.

### 7.3. Customizers Are Often Better Than Replacing the Whole Bean

Many libraries provide `Customizer` interfaces or callbacks to modify part of an auto-configured object's setup. When your goal is only adjusting timeouts, default headers, retry policies, or client builder settings, prefer library-supported customizers instead of rebuilding the entire bean yourself.

Reasons:

- Preserves other framework-optimized default settings.
- Reduces the risk of omitting metrics, tracing, security, or lifecycle hooks.
- Reduces coupling to constructors and internal implementation details that may change across versions.
- Clarifies customization scope and makes testing easier.

## 8. Spring Cloud Context and Refreshed Configuration

Spring Cloud Context adds context management and refresh capabilities to Spring applications. When external configuration changes, a refresh workflow can update `Environment` and refresh appropriately annotated beans.

Example:

```java
@Component
@RefreshScope
public class GreetingPolicy {

    private final String greeting;

    public GreetingPolicy(
            @Value("${app.greeting:Hello}") String greeting) {
        this.greeting = greeting;
    }

    public String greeting() {
        return greeting;
    }
}
```

When a valid refresh mechanism runs, the refresh-scope proxy can recreate the bean target on subsequent access after the scope is invalidated. The new value is read from the effective configuration at the time the new target is created.

Distinguish three operations:

1. **Source change:** editing a Git repository, environment variables supplied for the next run, or a secret manager.
2. **Configuration load/refresh:** the application updates `Environment` via its integrated mechanism.
3. **Applying to resources:** beans, caches, connection pools, or clients must support receiving new configuration.

These three steps do not happen automatically at once. Changing an environment variable outside a running process usually does not change values already received by the JVM. Nor does `@RefreshScope` watch Git or a secret manager on its own.

Stateful or long-lived resource beans (such as connection pools, TLS contexts, clients with open connections) need proper replacement, resource-closing, and rollout strategies. For changes affecting security or connections, a controlled restart is often more predictable than ad-hoc refresh.

If an Actuator refresh endpoint is used, restrict its access, authentication, and exposure. Never expose management endpoints on public networks; refresh can alter production behavior.

## 9. Testing to Prove Defaults Were Overridden

Tests should not verify only that the context starts. They must prove **which values are bound** or **which bean is created**.

### 9.1. Testing Property Binding

`ClientPropertiesTest.java`:

```java
package com.example.platform.config;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientPropertiesTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class);

    @Test
    void usesApplicationValuesWhenProvided() {
        runner.withPropertyValues(
                "demo.client.base-url=https://inventory.test",
                "demo.client.timeout=5s")
            .run(context -> {
                ClientProperties properties =
                    context.getBean(ClientProperties.class);

                assertThat(properties.getBaseUrl())
                    .isEqualTo("https://inventory.test");
                assertThat(properties.getTimeout())
                    .isEqualTo(java.time.Duration.ofSeconds(5));
            });
    }

    @Test
    void fallsBackWhenPropertyIsAbsent() {
        runner.run(context -> {
            ClientProperties properties =
                context.getBean(ClientProperties.class);

            assertThat(properties.getBaseUrl())
                .isEqualTo("http://localhost:8081");
            assertThat(properties.getTimeout())
                .isEqualTo(java.time.Duration.ofSeconds(2));
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class TestConfig {
    }
}
```

`ApplicationContextRunner` creates lightweight contexts with controlled properties. The two tests prove both the application-supplied values case and the fallback default case.

### 9.2. Testing Auto-Configuration Back-Off

You can test default configuration independently using `ApplicationContextRunner`:

```java
private final ApplicationContextRunner runner =
    new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
            DefaultEndpointAutoConfiguration.class));

@Test
void createsDefaultWhenApplicationHasNoResolver() {
    runner.run(context -> {
        EndpointResolver resolver =
            context.getBean(EndpointResolver.class);

        assertThat(resolver.resolve("inventory"))
            .isEqualTo("http://inventory:8080");
    });
}

@Test
void backsOffWhenApplicationProvidesResolver() {
    runner.withUserConfiguration(ApplicationEndpointConfiguration.class)
        .run(context -> {
            EndpointResolver resolver =
                context.getBean(EndpointResolver.class);

            assertThat(resolver.resolve("inventory"))
                .isEqualTo("https://inventory.prod.internal");
        });
}
```

This example requires importing `org.springframework.boot.autoconfigure.AutoConfigurations`, `org.springframework.boot.test.context.runner.ApplicationContextRunner`, and AssertJ. It verifies the contract: the default bean exists when no application bean is present, and is not created when the application supplies an implementation.

If the auto-configuration is in a separate library, also test registration via imports metadata and classpath/property conditions, rather than only invoking the configuration class directly.

### 9.3. Testing Source Precedence

In Spring Boot integration tests, you can pass test properties:

```java
@SpringBootTest(properties = {
    "demo.client.timeout=7s"
})
class ClientConfigurationIntegrationTest {
    // Inject ClientProperties and assert timeout is 7 seconds.
}
```

To test real environment variables, run integration tests in a process or container with explicitly configured environment variables. `@DynamicPropertySource` fits injecting dynamic endpoints/ports from Testcontainers into the context. Do not write unit tests attempting to assert the precedence of every `PropertySource` across every version; test against the actual configuration layout your application deploys.

### 9.4. Testing Refresh

Refresh is a separate flow from startup binding. When testing, you need to:

- Set an initial property value and verify the bean reads it.
- Update the configuration source using the mechanism supported by the real system.
- Trigger the configured refresh event/mechanism.
- Verify the refresh-scoped bean receives the new value after its target is recreated.
- Check whether non-refresh-scoped beans or long-lived resources require restart or special handling.

Do not treat a startup-binding test as proof that refresh works.

## 10. Diagnosing Why Defaults Are Still Used

When the application does not pick up custom values or beans, follow this order:

1. **Check key and type:** does the property have the right prefix, exact name, valid format, and convertible type?
2. **Check sources:** is the profile active, was the file loaded, did the environment variable reach the right process?
3. **Check precedence:** is a higher-precedence source overriding the application value?
4. **Check binding:** is the properties bean registered and does it have valid setters or constructor binding?
5. **Check auto-configuration conditions:** which conditions matched, was the default bean created, did the application provide a bean of the right type?
6. **Check injection:** are there multiple beans of the same type, and which qualifier/primary is injection using?
7. **Check timing:** were properties or beans updated after refresh/restart, or is the application still holding an old instance?

When inspecting auto-configuration conditions, run with `--debug` to print the condition evaluation report:

```bash
java -jar app.jar --debug
```

Actuator exposes endpoints such as `conditions`, `env`, or `configprops` depending on dependencies and exposure settings. They can reveal internal information, so enable them selectively, secure them, and restrict network access. Never paste full environment output into public tickets; strip tokens, passwords, URLs with credentials, and sensitive data before sharing.

## 11. Spring Boot and Spring Cloud Compatibility

Customization approaches depend on version APIs. An example using `@AutoConfiguration` or `@LoadBalancerClient` must match the release train; do not copy code verbatim from one Cloud generation into a project on a different Boot generation.

Dependency management principles:

- Select the Spring Boot version based on runtime requirements and project support policies.
- Consult the Spring Cloud release train compatibility matrix for Spring Boot.
- Import the corresponding `spring-cloud-dependencies` BOM and let the BOM manage Cloud module versions.
- Do not manually pin separate versions for `spring-cloud-commons`, `spring-cloud-context`, or LoadBalancer without a verified reason.
- When upgrading versions, read release notes and test extension points, auto-configuration conditions, and refresh behavior.

If a custom bean suddenly stops being selected after an upgrade, inspect the condition report, package/API changes, and new version's auto-configuration ordering before making global configuration changes.

## 12. Real-World Scenario: Application Wants to Replace Default Discovery

Suppose a team uses an internal service registry and wants applications to call services by logical name. Three approaches exist:

- If the registry already has a supported Spring Cloud integration, use the corresponding discovery starter and configure endpoints/credentials via external configuration sources.
- If instance lists come from custom data, consider implementing the appropriate abstraction or LoadBalancer extension point; do so only once contracts and lifecycles are clear.
- If you only want to change instance selection rules (such as preferring the nearest zone), keep the existing discovery source and customize the supplier/load balancer for the needed service.

Do not write a brand-new discovery client merely to change a timeout or instance selection order. Pinpoint whether the change belongs to the **configuration source**, the **instance list source**, or the **instance selection strategy**.

Safe rollout workflow:

1. Record current default behavior with tests and logs.
2. Identify the abstraction/extension point supported in your release train.
3. Configure or provide the custom implementation within the needed scope.
4. Test both with and without the custom bean.
5. Test registry failures, empty instance lists, missing config, and refresh/restart.
6. Roll out incrementally, monitoring connection errors and routing accuracy; keep a rollback path to known working config.

## 13. Practice Exercise

An internal library supplies `PaymentEndpointProvider` with a default bean pointing to `http://localhost:9000`. In production the application wants `https://payment.prod.internal`, default timeout `2s`, while staging wants `4s`.

Complete the following:

1. Define `PaymentEndpointProvider` and an auto-configuration using `@ConditionalOnMissingBean`.
2. Write an application-supplied bean to replace the default endpoint.
3. Create `PaymentProperties` with `@ConfigurationProperties` and `Duration`; set default `2s`.
4. Declare timeout `4s` in `application-staging.yml` and activate the `staging` profile.
5. Also pass `--payment.timeout=6s`; explain why the effective value can be `6s`.
6. Write tests proving the auto-configuration creates the default when no application bean exists and backs off when a custom bean is supplied.
7. Describe how to protect diagnostic endpoints and secrets when using Config Server or Actuator.

**Evaluation criteria:** distinguish property overrides from bean replacement; do not rely on bean name collisions; include tests for both condition branches; understand that profiles select configuration sets while `PropertySource` precedence decides the final value.

## 14. Key Takeaways

- Default values are starting points; applications can replace them with higher-precedence properties or suitable bean implementations.
- `Environment` and `PropertySource`s determine effective configuration values; profile files do not automatically override environment variables or command-line arguments.
- `@ConfigurationProperties` suits typed, defaulted, validatable configuration groups.
- `@ConditionalOnMissingBean` is the standard pattern allowing auto-configuration to back off when the application provides its own bean.
- `@Primary`, `@Qualifier`, and `@Order` control bean selection/ordering; they are not equivalent to removing or replacing a default bean.
- In Spring Cloud Commons, customize the right abstraction: discovery source, service registry, instance supplier, or load-balancer strategy.
- `@RefreshScope` only supports refreshing beans under a refresh mechanism; it does not monitor configuration sources automatically and does not guarantee every resource updates dynamically.
- Test both final bound values and created beans; use the condition report and secured diagnostic tools when investigating causes.
