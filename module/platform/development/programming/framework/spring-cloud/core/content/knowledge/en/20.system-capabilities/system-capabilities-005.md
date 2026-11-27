# Conditions for Enabling/Disabling Capabilities by Classpath and Configuration

## 1. Why Can a Capability Appear Automatically?

Spring Cloud is divided into multiple modules and starters. One application may only need centralized configuration, while another needs service discovery, load balancing, a circuit breaker, or refresh scope. If every capability were always created, applications would carry dependencies, beans, and background tasks they do not need.

Spring Boot and Spring Cloud solve this with conditional auto-configuration. When the application starts, the framework evaluates what is on the classpath, which beans already exist, and which properties are in the Environment. Only configurations whose conditions are satisfied are applied.

A capability is typically governed by three groups of conditions:

1. **Classpath:** whether the required library or API is present on the runtime classpath.
2. **ApplicationContext:** whether dependent beans already exist, or whether the application has provided a replacement bean.
3. **Configuration:** whether a property switch allows the capability to operate.

For example, adding the Spring Cloud LoadBalancer starter puts LoadBalancer classes on the classpath. However, if `spring.cloud.loadbalancer.enabled=false` is set, LoadBalancer auto-configuration will not be activated. Conversely, setting the property to `true` cannot conjure a library that is not in the dependencies.

## 2. How Does Auto-Configuration Evaluate Conditions?

A starter typically brings required dependencies and an auto-configuration module into the application. Spring Boot locates auto-configuration classes registered in the JAR, then evaluates the conditions declared on the configuration class and each bean.

In current Spring Boot, auto-configurations are listed in the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line is the fully qualified name of an auto-configuration class. Conditions on the class or `@Bean` methods determine whether that configuration is applied.

### 2.1. Classpath Conditions

`@ConditionalOnClass` only allows a configuration to activate when a class is present on the classpath. `@ConditionalOnMissingClass` does the opposite: the configuration only activates when the specified class is absent.

For example, an integration only needs to create beans when an optional client library has been added:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.vendor.InventoryClient")
class InventoryClientConfiguration {
    // Beans that depend on InventoryClient
}
```

Using the `name` attribute is helpful when the checked class belongs to an optional dependency and the auto-configuration module should not depend on it directly at compile time.

Do not put an optional type into a `@Bean` method signature inside an always-loaded configuration. The JVM may need to load that type before the method's condition is evaluated. Isolate the optional dependency in a nested configuration or separate configuration class annotated with `@ConditionalOnClass`.

### 2.2. ApplicationContext Bean Conditions

Two commonly used conditions:

- `@ConditionalOnBean`: activates a configuration or bean when a dependent bean already exists.
- `@ConditionalOnMissingBean`: only creates a default bean if the application has not already provided a corresponding bean.

`@ConditionalOnMissingBean` is the mechanism that lets an application override a starter's default. It does not remove the library from the classpath and does not mean the entire capability is disabled.

Example:

```java
@Bean
@ConditionalOnMissingBean(InventoryGateway.class)
InventoryGateway inventoryGateway(InventoryClient client) {
    return new InventoryGateway(client);
}
```

If the application has already declared its own `InventoryGateway`, the default bean is not created. Other beans in the same auto-configuration may still be created if their own conditions are satisfied.

### 2.3. Property Conditions

`@ConditionalOnProperty` allows a configuration to be applied based on a property in the Spring Environment:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "acme.inventory",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
class InventoryFeatureConfiguration {
    // Beans for the inventory capability
}
```

With this example, the capability is only enabled when `acme.inventory.enabled=true`. If the property is omitted or set to `false`, the configuration is not applied.

| Attribute | Meaning |
| --- | --- |
| `prefix` | Common prefix of the property |
| `name` | Property name to check |
| `havingValue` | Value that must match |
| `matchIfMissing` | Whether to match when the property does not exist; defaults to false |

If `havingValue` is omitted, a property that exists and does not have the value `false` is usually considered a match. For enable/disable flags, explicitly specify `havingValue = "true"` so readers understand the condition precisely.

### 2.4. Combining Multiple Conditions

A capability may simultaneously require a library, a foundational bean, and an enable property:

```java
@AutoConfiguration
class InventoryAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(InventoryClient.class)
    @ConditionalOnProperty(
            prefix = "acme.inventory",
            name = "enabled",
            havingValue = "true"
    )
    static class InventoryConfiguration {

        @Bean
        @ConditionalOnBean(InventoryClient.class)
        @ConditionalOnMissingBean
        InventoryGateway inventoryGateway(InventoryClient client) {
            return new InventoryGateway(client);
        }
    }
}
```

In this example, the nested configuration is only considered when `InventoryClient` is on the classpath and the property is enabled. The gateway bean is only created when an `InventoryClient` bean exists and no `InventoryGateway` has been provided by the application.

Conditions combine with AND logic. If one condition does not match, the configuration section governed by that condition will not be applied.

## 3. Classpath and Properties Are Two Independent Gates

Do not confuse adding a dependency with enabling a capability:

| Classpath | Property | Typical Result |
| --- | --- | --- |
| Library missing | true | No implementation to auto-configure; the property does not download dependencies |
| Library present | false | Auto-configuration is disabled by property |
| Library present | true | Capability can be configured if other bean/context conditions are also met |
| Library present | Not declared | Depends on `matchIfMissing` and the property's default value |

A starter can pull in transitive dependencies. Thus, a capability sometimes appears even though the development team did not directly declare that module. When investigating, check the dependency tree rather than only looking for dependency lines in the build file.

The following commands help inspect dependencies in a project:

```bash
# Maven
mvn dependency:tree

# Gradle
./gradlew dependencies
```

These commands only list dependencies. Having a JAR on the classpath does not prove a bean was created; you must check auto-configuration conditions and the ApplicationContext.

## 4. Capability Switches in Spring Cloud Commons

Spring Cloud Commons provides multiple property switches. These switches have different scopes; disabling one part does not mean disabling all related functionality.

### 4.1. Service Discovery

Providers such as Eureka, Consul, or ZooKeeper require their corresponding dependency to provide a `DiscoveryClient`. When an implementation is on the classpath, Spring Cloud can auto-configure the discovery client.

Commons currently does not require adding `@EnableDiscoveryClient` just to activate discovery. The presence of an implementation on the classpath is usually enough for auto-configuration to operate.

Key switches:

| Property | Scope |
| --- | --- |
| `spring.cloud.discovery.enabled=false` | Disables the service discovery capability under the general condition |
| `spring.cloud.discovery.blocking.enabled=false` | Disables blocking DiscoveryClient |
| `spring.cloud.discovery.reactive.enabled=false` | Disables reactive DiscoveryClient |

If only one programming model is used, you can disable the other. If the application does not use discovery, use the general switch. Check the properties and Spring Cloud version in use when multiple discovery providers appear on the classpath simultaneously.

### 4.2. Disabling Auto-Registration While Keeping Discovery

Looking up instances and registering the application itself are two separate behaviors.

```yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
```

`spring.cloud.service-registry.auto-registration.enabled=false` prevents Spring Cloud from automatically registering the local application instance. It is not a switch to disable `DiscoveryClient`; the application can still look up other services if the discovery client remains enabled.

This is useful for consumer-only applications, batch jobs, administrative tools, or cases where the deployment pipeline wants to register the service in a separate step. When auto-registration is disabled, `InstancePreRegisteredEvent` and `InstanceRegisteredEvent` are also not published along the auto-registration flow.

### 4.3. Discovery Health Indicator

DiscoveryClient can contribute a health indicator to Spring Boot Actuator. If you only want to omit the health indicator, there is no need to disable discovery:

```yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: false
        composite-indicator:
          enabled: false
```

Related properties:

| Property | Effect |
| --- | --- |
| `spring.cloud.discovery.client.health-indicator.enabled=false` | Disables DiscoveryClientHealthIndicator |
| `spring.cloud.discovery.client.composite-indicator.enabled=false` | Disables the composite indicator aggregating DiscoveryHealthIndicators |
| `spring.cloud.discovery.client.health-indicator.include-description=false` | Omits description from health results |
| `spring.cloud.discovery.client.health-indicator.use-services-query=false` | Uses `probe()` instead of querying the full `getServices()` when supported by the implementation |

The `use-services-query=false` property only changes how health is checked, not disabling the indicator. It is useful when the registry has a very large catalog and fetching the entire service list on every health check is costly.

### 4.4. Spring Cloud LoadBalancer

LoadBalancer is a separate capability from DiscoveryClient. It requires Spring Cloud LoadBalancer on the classpath and can obtain instances from a DiscoveryClient.

```yaml
spring:
  cloud:
    loadbalancer:
      enabled: true
      cache:
        enabled: true
      retry:
        enabled: false
```

The switches have different scopes:

| Property | Effect |
| --- | --- |
| `spring.cloud.loadbalancer.enabled=false` | Disables Spring Cloud LoadBalancer auto-configuration |
| `spring.cloud.loadbalancer.cache.enabled=false` | Disables LoadBalancer's instance list cache |
| `spring.cloud.loadbalancer.retry.enabled=false` | Disables LoadBalancer retry |

Disabling the cache does not disable discovery or LoadBalancer. Disabling retry also does not remove instance selection capability. If DiscoveryClient already has its own cache, evaluate whether enabling LoadBalancer's cache as well would cause two overlapping cache layers.

### 4.5. Refresh Scope

Spring Cloud Context provides refresh scope and related features. Auto-configuration for this feature group can be disabled:

```yaml
spring:
  cloud:
    refresh:
      enabled: false
```

`spring.cloud.refresh.enabled=false` is suitable for applications that do not use refresh scope or Spring AOT/native image environments, where Spring Cloud documentation requires disabling context refresh. Disabling refresh scope does not mean disabling all external configuration loading capabilities of Spring Boot or Config Client.

### 4.6. Features Endpoint

Spring Cloud Commons provides the `/features` endpoint to list features on the classpath and their recognized status. With Actuator using the default base path, the endpoint is typically called `/actuator/features`.

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - features

spring:
  cloud:
    features:
      enabled: true
```

`spring.cloud.features.enabled=false` disables the features endpoint. It does not disable the listed capabilities. The endpoint is for observing features, not a switch for enabling all features.

Features can be:

- **Abstract feature:** an interface or abstract class with an implementation bean, such as `DiscoveryClient` or `LoadBalancerClient`.
- **Named feature:** a capability published by name and representative bean type, such as another Spring Cloud module.

A listed feature does not prove all of its business operations are working. It shows that the feature is recognized in the application; health, connectivity, and actual behavior must be verified separately.

### 4.7. Compatibility Verifier

Spring Cloud Commons has a compatibility verifier to check whether the Spring Boot version on the classpath is within the compatible version range of the release train.

This verifier is not enabled by default in the current configuration. Set `spring.cloud.compatibility-verifier.enabled=true` to enable it:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
```

If you need to customize the accepted set of Boot versions, there is the `spring.cloud.compatibility-verifier.compatible-boot-versions` property. Only change this list after verifying the release train's compatibility matrix. Disabling the verifier to bypass startup errors does not make two incompatible versions compatible.

## 5. Example: Selecting Capabilities by Environment

Suppose a production service needs discovery to locate dependencies, while the deployment pipeline registers the service in a separate step. The application uses blocking clients, does not need reactive discovery, still uses LoadBalancer, and disables the discovery health indicator because it already has dedicated operational health checks.

```yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: false
      client:
        health-indicator:
          enabled: false
    service-registry:
      auto-registration:
        enabled: false
    loadbalancer:
      enabled: true
      cache:
        enabled: true
      retry:
        enabled: false
```

Read this configuration by scope:

1. Discovery remains active through the blocking client.
2. Reactive discovery is disabled.
3. The application does not auto-register itself with the registry.
4. LoadBalancer is still allowed to select instances.
5. The discovery health indicator is disabled; other health indicators are unaffected.

In a test environment where calling services via the registry is not needed, you can override:

```yaml
spring:
  cloud:
    discovery:
      enabled: false
    loadbalancer:
      enabled: false
```

Profiles can share dependencies while setting different properties. When a value comes from an environment variable, command-line argument, or Config Server, inspect the final resolved value in the Spring Environment rather than reading only `application.yml`.

## 6. Example: Building an Optional Capability in a Custom Starter

The same principles apply when a development team creates an internal starter.

Suppose the starter integrates with the `InventoryClient` library. The capability should only appear when:

- The dependency providing InventoryClient is on the classpath.
- The user sets `acme.inventory.enabled=true`.
- An InventoryClient bean exists for the gateway to use.
- The application has not provided its own InventoryGateway.

```java
@AutoConfiguration
public class InventoryAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(InventoryClient.class)
    @ConditionalOnProperty(
            prefix = "acme.inventory",
            name = "enabled",
            havingValue = "true"
    )
    static class InventoryConfiguration {

        @Bean
        @ConditionalOnBean(InventoryClient.class)
        @ConditionalOnMissingBean(InventoryGateway.class)
        InventoryGateway inventoryGateway(InventoryClient client) {
            return new InventoryGateway(client);
        }
    }
}
```

This example separates class conditions from bean conditions. The nested configuration prevents the optional class from being loaded when the dependency is absent. The gateway bean only appears when the client exists and has not been replaced by the application.

When packaging the starter:

1. Put the auto-configuration class into the auto-configuration module.
2. Register the class in `AutoConfiguration.imports`.
3. Mark optional dependencies as optional if the starter does not always require that library.
4. Use a dedicated namespace for the starter's properties, such as `acme.inventory`.
5. Document default values, `matchIfMissing`, and classpath conditions clearly.

## 7. Checking Why a Capability Is Enabled or Disabled

When a bean does not appear, do not add dependencies or change properties by guessing. Identify which condition did not match.

### 7.1. Checking the Dependency Tree

Verify that the starter and transitive dependencies are on the runtime classpath. For Maven, use `mvn dependency:tree`; for Gradle, use `./gradlew dependencies`. If a library was excluded via an exclusion or a scope that omits it from runtime, `@ConditionalOnClass` may fail to match.

### 7.2. Checking the Condition Evaluation Report

Spring Boot generates a condition evaluation report during auto-configuration. The report shows:

- Which configurations matched.
- Which configurations did not match.
- Which classpath or property conditions were missing.
- Which existing bean prevented `@ConditionalOnMissingBean` from creating the default bean.

You can view the report via the Actuator `conditions` endpoint if exposed and properly protected, or enable debug logging at startup to print the condition report.

### 7.3. Checking Features and Beans

If Actuator is enabled:

- `/actuator/features` shows Spring Cloud features that have been recognized.
- `/actuator/beans` shows which beans actually exist in the ApplicationContext.
- `/actuator/conditions` shows which auto-configuration conditions matched or did not match.
- `/actuator/configprops` shows bound ConfigurationProperties.

Endpoints must be explicitly exposed and protected with authentication/authorization. A feature missing from `/features` may be because the feature is not on the classpath, lacks a representative bean, or the endpoint is disabled; cross-check the condition report.

## 8. Testing Auto-Configuration Conditions

`ApplicationContextRunner` lets you test each combination of classpath, properties, and beans without starting the full application.

Example testing a capability enabled only when the property matches:

```java
class InventoryAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(InventoryAutoConfiguration.class)
                    );

    @Test
    void backsOffWhenFeatureIsDisabled() {
        contextRunner
                .withPropertyValues("acme.inventory.enabled=false")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(InventoryGateway.class));
    }

    @Test
    void createsGatewayWhenFeatureIsEnabledAndClientExists() {
        contextRunner
                .withPropertyValues("acme.inventory.enabled=true")
                .withBean(InventoryClient.class, FakeInventoryClient::new)
                .run(context -> assertThat(context)
                        .hasSingleBean(InventoryGateway.class));
    }
}
```

You can add classpath testing with `FilteredClassLoader`:

```java
contextRunner
        .withClassLoader(new FilteredClassLoader(InventoryClient.class))
        .withPropertyValues("acme.inventory.enabled=true")
        .run(context -> assertThat(context)
                .doesNotHaveBean(InventoryGateway.class));
```

At minimum, test these cases:

| Classpath | Property | Dependent Bean | Expected Result |
| --- | --- | --- | --- |
| Present | true | Present | Capability is created |
| Present | false | Present | Capability is not created |
| Present | Undeclared | Present | Follows `matchIfMissing` |
| Absent | true | Cannot exist | Optional auto-configuration is not applied |
| Present | true | Absent | Dependent bean is not created |
| Present | true | Custom bean present | Default bean backs off |

Testing these combinations helps prevent a starter from working in a sample app yet failing when added to an application that already has custom beans or lacks a transitive dependency.

## 9. Common Issues

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Property enabled yet bean does not appear | Dependency missing from runtime classpath | Inspect dependency tree and condition report |
| Starter is in build yet capability is disabled | Property switch is false or overridden by a profile | Check final resolved value in Environment and configprops |
| Discovery still runs after disabling auto-registration | Only local registration was disabled; DiscoveryClient still runs | Check `service-registry.auto-registration.enabled` and `discovery.enabled` |
| Disabled health indicator yet requests still resolve services | Only the health indicator was disabled | Check `health-indicator.enabled` |
| Disabled LoadBalancer yet DiscoveryClient still exists | Both capabilities have separate switches | Check `loadbalancer.enabled` and discovery switches |
| Default bean is not created | Application already declared a bean of the same type | Check bean list and ConditionalOnMissingBean condition |
| Capability appears unexpectedly | Another starter pulls a transitive dependency or a profile enables a property | Check dependency tree, profiles, and Environment |
| Application fails to start due to compatibility verifier | Spring Boot is not in the accepted version set | Check the release train/BOM matrix before changing verifier properties |
| `/actuator/features` returns 404 | Missing Actuator, endpoint not exposed, or features endpoint disabled | Check Actuator dependency, exposure, and `spring.cloud.features.enabled` |

## 10. Capability Design Principles

1. Include only necessary dependencies in the default starter; separate optional dependencies clearly.
2. Use `@ConditionalOnClass` to isolate external APIs and prevent errors when dependencies are absent.
3. Use `@ConditionalOnBean` when a capability requires an already configured infrastructure bean.
4. Use `@ConditionalOnMissingBean` to allow applications to override default implementations.
5. Use `@ConditionalOnProperty` with a dedicated namespace and clearly define default values.
6. Separate switches for distinct behaviors; do not use a single property to simultaneously disable discovery, registration, health, and load balancing.
7. Test auto-configuration conditions with `ApplicationContextRunner`.
8. Use the condition report, beans, and features endpoint for diagnostics.
9. Keep the Spring Cloud BOM and Spring Boot at compatible version pairs; do not disable the compatibility verifier just to hide dependency errors.
10. Protect actuator endpoints that can disclose internal information.

## 11. References

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): auto-configuration imports, class/bean/property conditions, and ApplicationContextRunner.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): discovery enablement conditions, blocking/reactive clients, health indicators, auto-registration, `/features`, and compatibility verifier.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): default values and descriptions of property switches.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): classpath conditions, LoadBalancer switches, and caching.
- [Spring Cloud Context — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): refresh scope switch and runtime environment limitations.

The classpath determines which libraries and implementations are available; bean conditions determine which components can be wired together; property switches determine whether operators want that capability enabled. Separating these three layers makes adding starters, swapping implementations, or disabling a feature predictable and testable.
