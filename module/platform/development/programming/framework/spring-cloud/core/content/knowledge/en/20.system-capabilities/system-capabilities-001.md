# Features Endpoint and Active Capability Information

> **Chapter:** System Capabilities  
> **Module:** SPRING_CLOUD_CORE

When operating a Spring Cloud application, development teams often need to know which capabilities are actually configured in the ApplicationContext: whether the application has a DiscoveryClient, whether it has a LoadBalancer, which integration modules have been enabled, and what implementation version is running. Checking dependencies in the build file alone is not enough, because auto-configuration may be conditional, a bean may not be created, or a provider may be replaced by another implementation.

Spring Cloud Commons provides the **Features Actuator Endpoint** to publish an inventory of declared features and their enabled/disabled status. The endpoint is typically accessed at `/actuator/features` when Actuator uses the default base path. It provides feature type, name, version, and vendor information for enabled features; abstract features without a corresponding bean are reported in the disabled list.

This lesson covers the endpoint's data structure, how Spring Cloud detects abstract features, how to declare named features via `HasFeatures`, how to configure endpoint exposure and security, as well as how to test and interpret results in the **SPRING_CLOUD_CORE** module.

## 1. What Need Does the Features Endpoint Solve?

An application may declare multiple Spring Cloud starters and libraries. However, the presence of a dependency does not mean the corresponding capability is active:

- A dependency may not be activated by auto-configuration due to missing conditions.
- A bean may be excluded from the context by a profile or property.
- The application may use a different discovery implementation than expected.
- A capability may be declared by a custom feature provider.
- The version in the dependency tree may differ from the implementation's package metadata version reported by the endpoint.

The Features Endpoint provides an ApplicationContext-level view. It aggregates features registered through `HasFeatures` beans and determines the status for each feature type.

Example questions it can answer:

- Does the context currently have a bean implementing `DiscoveryClient`?
- Is `LoadBalancerClient` created in the context?
- Does the integration module declare a capability named "Partner API"?
- What package version and vendor does the reported implementation have?
- Does a declared abstract feature without a bean appear in the disabled list?

The endpoint helps diagnose configuration and verify auto-configuration. It does not replace health checks, readiness probes, network connectivity checks, or business logic checks.

## 2. Endpoint and Returned Data

Spring Cloud Commons provides an Actuator endpoint with the ID `features`. With Spring Boot's default web management configuration, the URL is typically:

~~~http
GET /actuator/features
~~~

If the application changes `management.endpoints.web.base-path` or runs the management server on a separate port, the actual address changes accordingly. The endpoint requires Spring Boot Actuator and the corresponding Spring Cloud Commons auto-configuration.

The returned data has two main groups:

| Field | Contents |
| --- | --- |
| `enabled` | Features determined to be enabled; each element contains feature metadata |
| `disabled` | Names of abstract features that were declared but no corresponding bean was found |

An element in `enabled` has the following fields:

| Field | Meaning |
| --- | --- |
| `type` | Fully qualified name of the implementation class (or the class declared for a named feature) |
| `name` | Contract name for an abstract feature; declared name for a named feature |
| `version` | Version retrieved from package implementation metadata |
| `vendor` | Vendor retrieved from package implementation metadata |

Illustrative JSON example:

~~~json
{
  "enabled": [
    {
      "type": "com.example.catalog.CatalogDiscoveryClient",
      "name": "DiscoveryClient",
      "version": "2.4.1",
      "vendor": "Example Platform"
    },
    {
      "type": "com.example.partner.PartnerApiClient",
      "name": "Partner API",
      "version": "1.8.0",
      "vendor": "Example Platform"
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
~~~

The version/vendor values in the example are only for illustrating the format. Version and vendor may be null if the package does not provide the corresponding metadata. Do not treat the numbers in the example JSON as the application's actual Spring Cloud version.

### 2.1. The Endpoint Does Not Scan the Entire Classpath

The Features Endpoint does not automatically list every class or every dependency in JARs. Integration modules and applications declare features via `HasFeatures` beans. The endpoint aggregates those declarations and checks them according to the rules of each feature type.

Therefore, if a library is present on the classpath but does not register a corresponding feature, the endpoint may not display that library. Conversely, a named feature declaration should be placed in an appropriate conditional configuration to avoid reporting a capability as enabled when the actual component has not been created.

## 3. Two Feature Types: Abstract and Named

Spring Cloud Commons distinguishes two feature types.

### 3.1. Abstract Feature

An abstract feature represents a strongly typed contract, usually an interface or abstract class whose implementation is registered as a bean. Examples:

- `DiscoveryClient`
- `LoadBalancerClient`
- `LockService`

When an abstract feature is declared, the endpoint searches for a bean by the contract type in the ApplicationContext:

- If a corresponding bean is found, the feature is included in `enabled`.
- If no bean is found, the simple name of the contract type is included in `disabled`.

This helps detect cases where the application declares that it expects a capability, but auto-configuration did not create the corresponding bean.

For example: the application declares `DiscoveryClient.class` as a required feature. If there is no discovery provider or no implementation bean, the endpoint can report `DiscoveryClient` in the disabled list.

### 3.2. Named Feature

A named feature is used for capabilities that do not have a common abstraction interface/abstract class for the endpoint to look up. Examples might be API Gateway, Spring Cloud Bus, Circuit Breaker, or an internal integration.

A named feature requires:

- A display name.
- A class representing the implementation or component providing the feature.

`NamedFeature` holds the name and the class type used to retrieve type/version/vendor metadata. The endpoint places declared named features into `enabled`.

Important point: a named feature is recorded based on the `HasFeatures` bean that declares it; the endpoint does not automatically verify whether a bean instance of the named feature's type exists. Therefore, you should create the bean declaring the named feature in the same conditional configuration as the actual capability, or require the implementation bean as a parameter in the declaration method.

### 3.3. Comparison of the Two Types

| Criterion | Abstract feature | Named feature |
| --- | --- | --- |
| Representation | Interface or abstract class | Capability with a custom name |
| Declaration | Contract class | Name and implementation class |
| How enabled is determined | Search for bean by contract type in ApplicationContext | Declared in HasFeatures |
| How disabled is determined | No corresponding bean found | Not automatically inferred as disabled if undeclared |
| Examples | DiscoveryClient, LoadBalancerClient | API Gateway, Partner API |

Do not use a named feature instead of an abstract feature when a suitable contract already exists. Abstract features let the endpoint verify that the bean actually exists; named features are suitable for capabilities without a common abstraction.

## 4. HasFeatures and NamedFeature

Spring Cloud Commons uses `HasFeatures` beans to declare features that a module wants the endpoint to observe. Either abstract features or named features can be declared.

Example of a module declaring the abstractions it depends on:

~~~java
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DiscoveryCapabilityConfiguration {

    @Bean
    HasFeatures discoveryFeatures() {
        return HasFeatures.abstractFeatures(
                DiscoveryClient.class,
                LoadBalancerClient.class);
    }
}
~~~

The endpoint will check for `DiscoveryClient` and `LoadBalancerClient` beans in the ApplicationContext. If a type has no bean, that type's name appears in the disabled list.

In a real application, Spring Cloud Commons or discovery/load-balancer integrations may already declare the standard features. Do not re-register framework features just to add more lines to the endpoint output. The example above illustrates the declaration mechanism; check existing feature providers in your version before adding more.

### 4.1. Declaring a Named Feature

Suppose an application has a client integrating with a partner system without a corresponding Spring Cloud Commons interface. It can be declared as:

~~~java
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.actuator.NamedFeature;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PartnerCapabilityConfiguration {

    @Bean
    HasFeatures partnerApiFeature(PartnerApiClient partnerApiClient) {
        return HasFeatures.namedFeatures(
                new NamedFeature("Partner API", PartnerApiClient.class));
    }
}
~~~

The `partnerApiClient` parameter ensures that the client bean exists before the feature bean is created. In this example, the client object is injected to bind the feature declaration to the configuration that provides that client. If the capability is only enabled by a profile or property, place this configuration under the same condition as the client bean.

Do not declare a named feature in an always-active configuration if the actual implementation can be disabled. Otherwise, the endpoint might report "Partner API" in enabled even though the application cannot call the partner system.

### 4.2. Placing Feature Configuration Under Conditions

Example where a capability only exists when a property is enabled:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "partner.api",
        name = "enabled",
        havingValue = "true")
public class PartnerApiConfiguration {
    // Declare PartnerApiClient and HasFeatures here.
}
~~~

When `partner.api.enabled=false`, both the client and the bean declaring the named feature will not be created if they reside in this configuration. This prevents the endpoint from mistakenly reporting the capability as enabled.

If a module uses multiple conditional configurations, ensure the `HasFeatures` bean is enabled/disabled with the same logic as the capability it describes.

## 5. Where Are Version and Vendor Retrieved From?

The Features Endpoint displays version and vendor based on Java Package metadata:

- `Package.getImplementationVersion()`
- `Package.getImplementationVendor()`

For an abstract feature, the endpoint retrieves the implementation bean found in the ApplicationContext and reads the package metadata of its actual class. For a named feature, metadata is read from the class passed to `NamedFeature`.

This has several implications:

1. If the JAR is packaged with a manifest containing Implementation-Version and Implementation-Vendor, the endpoint can display those values.
2. If metadata is missing from the manifest or classes are run from a directory without metadata, the values may be null.
3. The displayed version is the implementation's package metadata, not a consolidated dependency tree summary.
4. A feature's version does not prove Spring Boot/Spring Cloud release train compatibility.

For example, the endpoint reporting a discovery client's version does not mean the entire system has been verified for compatibility. To verify compatibility, you still need dependency management/BOM and Spring Cloud's compatibility checks.

Do not use the Features Endpoint's version field as the sole source for license inventory, SBOM, or vulnerability scanning. Those tasks require dedicated artifact and dependency analysis tools.

## 6. Enabling and Exposing the Endpoint via Actuator

To access the endpoint over HTTP, the application needs Actuator and the corresponding web exposure configuration.

Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Spring Cloud Commons provides the endpoint when the Actuator endpoint API and matching auto-configuration conditions are present. The `spring.cloud.features.enabled` property defaults to true in the current Spring Cloud Commons configuration; set it to false to disable creating the Features Endpoint.

Example exposure configuration:

~~~yaml
spring:
  cloud:
    features:
      enabled: true

management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - features
~~~

The two settings have different meanings:

- `spring.cloud.features.enabled` controls whether Spring Cloud creates the features endpoint.
- `management.endpoints.web.exposure.include` controls which endpoints are exposed over HTTP.

If the endpoint does not appear, check the Actuator dependency, the endpoint enable property, web exposure, management base path, and management port. Do not confuse an endpoint not being exposed over HTTP with the capability inside the application being disabled.

### 6.1. Accessing the Endpoint

With the default base path:

~~~bash
curl http://localhost:8080/actuator/features
~~~

If the application configures a different `management.endpoints.web.base-path` or the management server uses a separate port, adjust the URL according to that configuration.

Some applications only expose `health` by default. Therefore, having the Actuator dependency does not guarantee `/actuator/features` is accessible over the web. Explicitly declare the endpoints to expose in each environment.

### 6.2. Disabling the Endpoint When Not Needed

This feature can be disabled:

~~~yaml
spring:
  cloud:
    features:
      enabled: false
~~~

When the endpoint is disabled, HTTP requests to the corresponding path will typically not find a registered endpoint. This is an observability decision; it does not mean DiscoveryClient, LoadBalancer, or other business capabilities are disabled.

## 7. Reading Results to Diagnose Configuration

When inspecting `/actuator/features`, read both enabled and disabled.

### 7.1. Abstract Feature Appears in Enabled

If `DiscoveryClient` has an implementation bean, the endpoint records the implementation class, name, version, and vendor. You can use this information to confirm the actual provider created in the context.

For example, the application is expected to use Consul, but the endpoint shows a different implementation. In that case, check dependencies, auto-configuration conditions, profiles, and application-declared beans.

### 7.2. Abstract Feature Appears in Disabled

If an abstract feature is declared but has no corresponding bean, the contract name appears in disabled. Check:

- Is the required starter/provider in the dependency graph?
- Is the auto-configuration excluded?
- Has a property or profile unintentionally disabled the capability?
- Is the bean created in the ApplicationContext being observed?
- Is a classpath or bean condition causing the configuration to back off?

A disabled feature does not by itself state the specific cause. The endpoint tells you the contract bean was not found; combine it with the Condition Evaluation Report, startup logs, and other diagnostic endpoints to find the reason.

### 7.3. Named Feature Appears in Enabled

For a named feature, the endpoint reflects the `HasFeatures` bean that declared the capability. It does not perform a health check against the partner service or verify that the remote API is responding.

If a named feature appears but requests to the external system fail, separately check health indicators, connectivity, credentials, DNS, TLS, and client logs. Do not interpret enabled as "the target service is healthy".

## 8. How Is the Features Endpoint Different from Health and Readiness?

Actuator endpoints serve different purposes:

| Endpoint | Primary Question | Scope |
| --- | --- | --- |
| `/actuator/features` | Which capabilities are declared and recognized as enabled? | Feature inventory in the ApplicationContext |
| `/actuator/health` | Are the application and its health contributors healthy? | Health status |
| `/actuator/info` | What informational metadata does the application publish? | Configurable build/deployment information |
| `/actuator/conditions` | Which auto-configuration conditions matched or did not match? | Configuration condition diagnostics |
| `/actuator/beans` | Which beans are registered in the context? | Bean inventory |

A DiscoveryClient may be reported as enabled while the registry is unreachable. Similarly, a named feature may be declared enabled while the partner endpoint is failing. Health indicators and readiness probes are what answer questions about serving readiness at the time of the check.

With Kubernetes, do not use the Features Endpoint as the sole readiness probe. Readiness should reflect whether the application can accept traffic according to system policy; a feature inventory does not provide that conclusion.

## 9. Securing Capability Information

The Features Endpoint may disclose:

- Libraries or integrations in use.
- Implementation class names.
- Version and vendor metadata.
- The presence or absence of certain internal capabilities.

This information is useful for operations, but it also helps outsiders infer technologies and attack surface. Therefore:

- Only expose the endpoint on an administrative network or behind appropriate authentication.
- Do not open all Actuator endpoints to the public Internet.
- Apply role/authorization controls for users who need to view capability information.
- Restrict logging and storage of responses according to security policies.
- Do not put secrets, tokens, or sensitive configuration into feature names or metadata.
- Consider disabling the endpoint in environments where capability observability is not needed.

Do not embed credential information in `NamedFeature`. The endpoint only needs the capability name and class metadata; secrets must be managed in an appropriate secret store.

## 10. Testing the Features Endpoint

You can use a Spring Boot integration test to verify that the endpoint is exposed and declared named features appear in the output.

Suppose the application has a `PartnerApiClient` class and the following configuration:

~~~java
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.actuator.NamedFeature;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureInventoryConfiguration {

    @Bean
    PartnerApiClient partnerApiClient() {
        return new PartnerApiClient();
    }

    @Bean
    HasFeatures partnerApiFeature(PartnerApiClient client) {
        return HasFeatures.namedFeatures(
                new NamedFeature("Partner API", PartnerApiClient.class));
    }

    @Bean
    HasFeatures inventoryFeature() {
        return HasFeatures.abstractFeatures(InventoryClient.class);
    }
}
~~~

In this example, `InventoryClient` is an application-defined interface with no implementation bean in the test context. Therefore, the endpoint can place the name `InventoryClient` into the disabled list. `PartnerApiClient` is created and the named feature is declared in the same context.

HTTP test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,features"
})
@AutoConfigureMockMvc
@Import(FeatureInventoryConfiguration.class)
class FeaturesEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesDeclaredCapabilities() throws Exception {
        mockMvc.perform(get("/actuator/features"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled[*].name",
                        hasItem("Partner API")))
                .andExpect(jsonPath("$.disabled",
                        hasItem("InventoryClient")));
    }
}
~~~

The test assumes the application has Spring MVC test support, Spring Boot Actuator, Spring Cloud Commons, and the features endpoint auto-configured. If the application uses WebFlux, use WebTestClient or an appropriate test client. If the management base path has changed, adjust the test URL.

### 10.1. Testing the Endpoint When Disabled

You can create a separate test context with:

~~~properties
spring.cloud.features.enabled=false
~~~

Then verify that the endpoint is not created/exposed. Isolating the test context avoids sharing an ApplicationContext where the endpoint was already initialized from another test.

### 10.2. Testing That a Feature Is Actually Activated

For an abstract feature, tests should verify both cases:

- With a contract implementation bean present: the feature name appears in enabled.
- Without a contract implementation bean: the feature name appears in disabled.

For a named feature, verify that the `HasFeatures` bean is only created when the capability is actually enabled. This prevents misreporting status due to declaration configuration not sharing the same conditions as the implementation.

## 11. Common Mistakes and How to Avoid Them

1. **Having Actuator but unable to access the endpoint:** check web exposure, base path, and management port.
2. **Assuming the endpoint automatically scans all dependencies:** only features declared via HasFeatures are aggregated.
3. **Confusing a named feature with a health-checked bean:** named features reflect declarations; health checks require a separate mechanism.
4. **Abstract feature appears in disabled:** check the contract bean, dependencies, profiles, and auto-configuration conditions.
5. **Version or vendor is null:** check the package manifest; do not conclude the application has no version.
6. **Duplicate registration of framework features:** check existing HasFeatures beans from Spring Cloud integrations before adding declarations.
7. **Always-on named feature declaration:** place the HasFeatures bean in a conditional configuration or depend on the implementation bean.
8. **Using the endpoint as a readiness probe:** use appropriate health/readiness contributors.
9. **Treating feature versions as a full dependency report:** use dependency trees/SBOMs for inventory and compatibility.
10. **Exposing the endpoint publicly:** restrict network access and protect with authentication/authorization.
11. **Disabling the endpoint and thinking the capability is disabled:** `spring.cloud.features.enabled` only controls the inventory endpoint.
12. **Not testing the disabled state:** add tests for cases where the contract bean does not exist.

## 12. Workflow for Applying in a Spring Cloud Project

When you want to observe an application's capabilities:

1. Add Spring Boot Actuator and confirm Spring Cloud Commons is present.
2. Verify the features endpoint is enabled with `spring.cloud.features.enabled`.
3. Expose `features` over management HTTP in environments that need diagnostics.
4. Check framework features already declared by integration modules.
5. Use abstract features for contracts with an interface/abstract class.
6. Use named features for capabilities without a common abstraction.
7. Place HasFeatures beans in conditional configurations matching the implementation.
8. Read enabled/disabled and cross-check version/vendor metadata.
9. Combine Conditions, Beans, Health, and logs to investigate root causes.
10. Secure the endpoint and do not use it as a replacement for readiness/health checks.

## 13. Key Takeaways

The Spring Cloud Commons Features Endpoint provides an inventory of capabilities declared in the ApplicationContext. Abstract features are checked by looking up a bean by contract; named features are placed in enabled when declared via `HasFeatures`. Enabled results may include type, name, version, and vendor retrieved from package metadata; disabled lists names of abstract features without a corresponding bean.

This endpoint helps verify configuration and diagnose auto-configuration, but does not prove that dependencies are healthy, remote endpoints are reachable, or the application is ready to receive traffic. Combine it with health/readiness, conditions, and logs, and protect capability information in deployment environments of **SPRING_CLOUD_CORE**.

## References

- [Spring Cloud Commons — Common Abstractions, Enabled Features](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Boot Actuator — Endpoint Exposure](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
