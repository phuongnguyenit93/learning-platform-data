# Distinguishing Abstract Features and Named Features

This lesson belongs to the **System Capabilities** chapter of the **SPRING_CLOUD_CORE** module. Spring Cloud Commons provides the `/features` Actuator endpoint to list the capabilities announced by Spring Cloud modules and indicate whether they are recognized as enabled or disabled in the ApplicationContext. The endpoint distinguishes two ways of describing a capability: **abstract feature** and **named feature**.

- **Abstract feature** has an interface or abstract class as a common contract, such as `DiscoveryClient`, `LoadBalancerClient`, or `LockService`. The endpoint looks up a bean by contract type to determine whether the feature is enabled.
- **Named feature** does not have a common interface/abstract class representing the capability. A module declares the feature using a display name and a class that provides metadata, such as Circuit Breaker, API Gateway, or Spring Cloud Bus.

This difference directly affects how `HasFeatures` is declared, how the endpoint classifies results, and how reports are interpreted. In particular, named features are added to the enabled list based on the `HasFeatures` declaration; the endpoint does not perform a bean lookup as it does for abstract features. Therefore, configuration declaring a named feature should be placed in an appropriately conditional `@Configuration`.

## 1. Learning Outcomes

After this lesson, you can:

1. Explain the purpose of the `/features` endpoint in Spring Cloud Commons.
2. Distinguish between abstract features and named features by contract and detection mechanism.
3. Describe how the endpoint checks beans for abstract features.
4. Explain how a named feature is described using a name and metadata class.
5. Read the `enabled` and `disabled` groups in the response.
6. Understand the `name`, `type`, `version`, and `vendor` fields.
7. Declare `HasFeatures` using `abstractFeatures`, `namedFeatures`, or the builder.
8. Place feature declarations in properly conditioned configurations.
9. Enable, expose, and query the endpoint via Spring Boot Actuator.
10. Recognize the endpoint's limitations and avoid treating it as a health check or runtime feature flag.
11. Write tests for features with a bean, missing a bean, and undeclared named features.
12. Use the endpoint to help diagnose dependencies, auto-configuration, and application integration capabilities.

## 2. Why Describe System Capabilities?

A Spring Cloud application can combine many modules: discovery, load balancing, circuit breaker, gateway, messaging, or bus. Looking only at dependencies in the build file is not enough to know which capabilities have actually been configured in the ApplicationContext.

For example, a Eureka dependency may appear on the classpath while discovery configuration is excluded by a property or auto-configuration condition. Similarly, a module may declare a circuit breaker abstraction without a matching implementation factory.

The `/features` endpoint provides an inventory contributed by Spring Cloud modules. Each module creates one or more `HasFeatures` beans to describe the capabilities it provides. The endpoint aggregates those declarations and returns metadata for operations tooling or developers.

~~~mermaid
flowchart TD
    MODULES["Spring Cloud modules"] --> DECL["HasFeatures beans"]
    DECL --> ENDPOINT["FeaturesEndpoint"]
    CONTEXT["Spring ApplicationContext"] --> ENDPOINT
    ENDPOINT --> ABSTRACT["Abstract features"]
    ENDPOINT --> NAMED["Named features"]
    ABSTRACT --> LOOKUP["Lookup bean by contract type"]
    LOOKUP --> RESULT["enabled / disabled"]
    NAMED --> DECLARED["Use declared name and type metadata"]
    DECLARED --> RESULT
    RESULT --> HTTP["GET /actuator/features"]
~~~

The endpoint helps answer the question: *which capabilities have been published by modules and how does the endpoint recognize them?* It does not automatically verify all runtime behaviors of each capability.

## 3. What Is an Abstract Feature?

### 3.1. Having a Common Contract Type

An abstract feature is a capability that has an interface or abstract class as a contract. Implementations may vary while providing a bean under that same contract.

Examples:

| Contract type | Represented capability |
| --- | --- |
| `DiscoveryClient` | Query service instances from a discovery provider. |
| `LoadBalancerClient` | Select an instance to send a request to a service. |
| `LockService` | Provide an abstraction for distributed locking. |

An application can swap Eureka for Consul or Zookeeper while code consuming `DiscoveryClient` continues working through the common contract. The endpoint uses that same contract type to ask the ApplicationContext whether a matching bean exists.

### 3.2. How Does the Endpoint Check the Bean?

For each declared abstract feature, `FeaturesEndpoint` performs this general logic:

1. Retrieve the contract class/interface from the abstract features list.
2. Retrieve the simple name of the contract, such as `DiscoveryClient`.
3. Call `ApplicationContext.getBean(contractType)` to look up a bean by type.
4. If a matching bean is found, add the feature to the `enabled` list.
5. If no bean is found by type, add the feature name to the `disabled` list.
6. For enabled features, use the bean's actual class to extract package metadata, including implementation version and vendor.

This is a check for bean presence/resolvability in the context. It does not call the registry, does not send requests to external services, and does not confirm that every method of the implementation works.

### 3.3. Abstract Feature Example in Spring Cloud Commons

Spring Cloud Commons declares common capabilities as follows:

~~~java
@Bean
public HasFeatures commonsFeatures() {
    return HasFeatures.abstractFeatures(
            DiscoveryClient.class,
            LoadBalancerClient.class
    );
}
~~~

If the ApplicationContext has `DiscoveryClient` and `LoadBalancerClient` beans resolvable by type, the corresponding features are placed in `enabled`. If no bean is found for a contract, that contract's name appears in `disabled`.

In other modules, a custom abstract feature can be declared:

~~~java
public interface InvoiceClient {
    Invoice findById(String invoiceId);
}

@Configuration(proxyBeanMethods = false)
class InvoiceClientConfiguration {

    @Bean
    InvoiceClient invoiceClient() {
        return new HttpInvoiceClient();
    }

    @Bean
    HasFeatures invoiceClientFeature() {
        return HasFeatures.abstractFeatures(InvoiceClient.class);
    }
}
~~~

`InvoiceClient` is the capability's contract. The implementation `HttpInvoiceClient` is the actual bean registered in the context. When the endpoint checks `InvoiceClient.class`, Spring looks up the bean by the contract interface.

### 3.4. What Does a Missing Bean Mean?

If an abstract feature is declared in `HasFeatures` but has no corresponding bean, the endpoint puts the feature name into `disabled`.

Common causes include:

- The provider starter has not been added to dependencies.
- Auto-configuration was not activated.
- A property disabled the capability.
- `@ConditionalOnClass`, `@ConditionalOnBean`, or `@ConditionalOnProperty` did not match.
- User configuration excluded the bean or component scan did not cover the configuration.
- The bean was declared under a different type than the contract registered by the feature.

Treat `disabled` as a signal to investigate bean creation conditions. It does not pinpoint the exact cause on its own.

## 4. What Is a Named Feature?

### 4.1. No Single Common Abstraction Type

Some capabilities are meaningful at the product/functional level, yet do not have a single interface or abstract class that every implementation must implement.

Spring Cloud gives these examples:

- Circuit Breaker.
- API Gateway.
- Spring Cloud Bus.

These capabilities can be implemented by different classes or different modules. Therefore, instead of looking up a common contract type in the ApplicationContext, a module publishes the feature using:

- A **name** so readers can identify the capability.
- A **class type** to provide metadata about type, version, and vendor.

### 4.2. NamedFeature Consists of a Name and a Class Type

Example following Spring Cloud's pattern:

~~~java
new NamedFeature(
        "Spring Cloud Bus",
        ConsulBusAutoConfiguration.class
)
~~~

The name `Spring Cloud Bus` is the displayed feature label. `ConsulBusAutoConfiguration.class` is the class used as the metadata type.

For a custom application module, you can declare:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true"
)
class PaymentGatewayFeatureConfiguration {

    @Bean
    PaymentGatewayClient paymentGatewayClient() {
        return new HttpPaymentGatewayClient();
    }

    @Bean
    HasFeatures paymentGatewayFeature() {
        return HasFeatures.namedFeatures(
                new NamedFeature(
                        "Payment Gateway",
                        PaymentGatewayFeatureConfiguration.class
                )
        );
    }
}
~~~

When the property `app.payment.enabled=true` is set, the configuration is activated and the `HasFeatures` bean publishes the named feature. When the property is false or conditions are not met, the configuration does not contribute this feature declaration.

### 4.3. How Does the Endpoint Process Named Features?

Unlike abstract features, the endpoint does not call `ApplicationContext.getBean(namedFeature.getType())` to verify a named feature.

The endpoint takes each `NamedFeature` declared in `HasFeatures` and adds it directly to the `enabled` list, using:
- The feature name from `NamedFeature`.
- The canonical class name from the type.
- The implementation version of the package containing the type.
- The implementation vendor of the package containing the type.

Therefore, the presence of a named feature in `enabled` reflects that a module published it via `HasFeatures`. That declaration must be placed inside an appropriate conditional configuration so it does not report the capability as enabled when the actual feature is turned off.

### 4.4. Named Features Have No Automatic Disabled Entry

The endpoint does not automatically add missing named features to `disabled`. If a configuration does not create a `HasFeatures` bean declaring a named feature, that feature simply does not appear in the response.

This is an important distinction when reading results:

- Declared abstract feature with no bean found: name appears in `disabled`.
- Named feature with a declaration: appears in `enabled`.
- Named feature without a declaration: does not appear in either list.

Do not infer that a named feature absent from the response means the endpoint checked and confirmed it is disabled.

## 5. Comparing Abstract Features and Named Features

| Criterion | Abstract feature | Named feature |
| --- | --- | --- |
| Basis of identification | Interface or abstract class contract. | Feature name and class type providing metadata. |
| Examples | DiscoveryClient, LoadBalancerClient, LockService. | Circuit Breaker, API Gateway, Spring Cloud Bus. |
| Declaration | `HasFeatures.abstractFeatures(Type.class)`. | `HasFeatures.namedFeatures(new NamedFeature(name, Type.class))`. |
| Bean check | Endpoint looks up a bean by contract type in the ApplicationContext. | Endpoint does not look up a bean by the named feature type. |
| When considered enabled | A bean can be resolved by contract type. | A declaration in `HasFeatures` is loaded into the endpoint. |
| When not enabled | Contract name appears in `disabled` if lookup fails. | Without a declaration, the feature does not appear; the endpoint does not automatically add it to `disabled`. |
| Version/vendor metadata | Retrieved from the actual class of the found bean. | Retrieved from the class type passed into `NamedFeature`. |

Both types are aggregated through `HasFeatures` and displayed at the same endpoint. The difference lies in how a module proves its capability.

## 6. Reading the /features Response

### 6.1. Enabling the Endpoint

Spring Cloud Commons provides an Actuator endpoint with ID `features`. The endpoint is enabled by default when matching auto-configuration conditions apply and the `spring.cloud.features.enabled` property is not turned off.

Current property:

~~~yaml
spring:
  cloud:
    features:
      enabled: true
~~~

You can disable creating the endpoint with:

~~~yaml
spring:
  cloud:
    features:
      enabled: false
~~~

The default value of `spring.cloud.features.enabled` is `true`.

### 6.2. Exposing the Endpoint over HTTP

If the application uses Spring Boot Actuator, add `features` to the list of exposed endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,features
~~~

Default HTTP path:

~~~text
GET /actuator/features
~~~

If the application changes `management.endpoints.web.base-path` or uses a separate management port, the actual URL will change accordingly. Exposure only determines whether the endpoint is published over HTTP; it still needs protection via authentication, authorization, and network policies.

### 6.3. Calling the Endpoint

~~~bash
curl --request GET \
  http://localhost:8080/actuator/features
~~~

The endpoint is read-only. It returns the list of declared features categorized by recognition status.

### 6.4. Response Structure

Illustrative example response:

~~~json
{
  "enabled": [
    {
      "type": "com.example.payment.PaymentGatewayFeatureConfiguration",
      "name": "Payment Gateway",
      "version": "1.4.0",
      "vendor": "Example Team"
    },
    {
      "type": "com.example.discovery.EurekaDiscoveryClient",
      "name": "DiscoveryClient",
      "version": "5.0.4",
      "vendor": "Broadcom"
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
~~~

Meaning of the fields:

| Field | Meaning |
| --- | --- |
| `enabled` | List of features recognized as enabled by the endpoint. |
| `disabled` | List of abstract feature names that were declared but no bean could be resolved. |
| `name` | Display name of the feature. |
| `type` | Canonical class name of the type used to describe the feature. |
| `version` | Package implementation version if metadata is available. |
| `vendor` | Package implementation vendor if metadata is available. |

The values in the example are only to illustrate the structure. Actual version and vendor depend on the JAR's manifest metadata; they may be null if the package does not provide that information.

### 6.5. Do Not Confuse Contract Version with Implementation Version

For an abstract feature, the endpoint takes the actual class of the found bean and reads its package implementation version. Therefore, the displayed version reflects the implementation class, not necessarily the version of the contract interface.

For a named feature, the endpoint uses the class type passed into `NamedFeature` to get the canonical name, version, and vendor. Choose a class belonging to the module providing the capability so the metadata is meaningful.

## 7. Declaring HasFeatures in a Module

### 7.1. One Bean Can Declare Multiple Features

A module can publish multiple abstract and named features in a single `HasFeatures` bean.

~~~java
@Bean
HasFeatures localFeatures() {
    return new HasFeatures(
            List.of(InvoiceClient.class, PricingClient.class),
            List.of(
                    new NamedFeature(
                            "Invoice Export",
                            InvoiceExportConfiguration.class
                    ),
                    new NamedFeature(
                            "Pricing Rules",
                            PricingRulesConfiguration.class
                    )
            )
    );
}
~~~

This structure helps a module centralize feature metadata. If using the constructor directly, pass the list of abstract classes and the list of named features in the exact constructor order of the Spring Cloud version in use.

### 7.2. Using the Builder

You can use the builder to interleave feature declarations:

~~~java
@Bean
HasFeatures billingFeatures() {
    return HasFeatures.builder()
            .abstractFeature(InvoiceClient.class)
            .abstractFeature(PricingClient.class)
            .namedFeature(
                    new NamedFeature(
                            "Invoice Export",
                            InvoiceExportConfiguration.class
                    )
            )
            .build();
}
~~~

The builder is suitable when the list contains both types and each declaration should be clearly expressed.

### 7.3. Separating Configuration by Module/Provider

Each module should publish features in a configuration matching that module's conditions:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(DiscoveryClient.class)
@ConditionalOnBean(DiscoveryClient.class)
class DiscoveryFeatureConfiguration {

    @Bean
    HasFeatures discoveryFeatures() {
        return HasFeatures.abstractFeatures(DiscoveryClient.class);
    }
}
~~~

This example illustrates only declaring the feature when the contract is present and the corresponding bean is created. In real auto-configuration, additional conditions based on properties, providers, discovery modes, or versions can be used.

Do not bundle features from every module into an always-enabled configuration. That easily causes a named feature to be reported as enabled even though the module is not actually activated.

## 8. Configuration Conditions and Report Accuracy

### 8.1. Abstract Features Must Match the Contract Bean

When declaring an abstract feature, choose the exact interface/abstract class that the actual bean implements.

For example:
- Declare `DiscoveryClient.class` if you want to check for a bean under the discovery contract.
- Do not declare a concrete implementation class if the goal is to verify the common abstraction.
- If a module has multiple implementations, check how Spring resolves the bean by type and configure primary/qualifier appropriately.

An abstract feature that is declared but whose bean cannot be resolved will appear in `disabled`. Use the condition report and bean inspection to find the reason.

### 8.2. Named Features Must Be Properly Guarded

Named features are not verified by the endpoint via bean lookup. Therefore, the conditions on creating the `HasFeatures` bean are what determine whether the feature is published.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.gateway",
        name = "enabled",
        havingValue = "true"
)
class GatewayFeatureConfiguration {

    @Bean
    HasFeatures gatewayFeature() {
        return HasFeatures.namedFeatures(
                new NamedFeature(
                        "API Gateway",
                        GatewayFeatureConfiguration.class
                )
        );
    }
}
~~~

If the property disables the gateway, the configuration is not loaded and the named feature is not published. If the configuration is always loaded, the endpoint will report the named feature in `enabled` even if another runtime bean was disabled by its own condition.

### 8.3. Separating Dependency Conditions and Property Conditions

A feature may simultaneously require:
- The library/provider present on the classpath.
- The implementation bean created.
- A property enabling the capability.
- Another module providing a required dependency.

Spring Boot conditions can be combined:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(GatewayClient.class)
@ConditionalOnBean(GatewayClient.class)
@ConditionalOnProperty(
        prefix = "app.gateway",
        name = "enabled",
        havingValue = "true"
)
class GatewayFeatureConfiguration {
    // HasFeatures bean is declared here.
}
~~~

Conditions must accurately reflect the semantics of the feature. Do not add conditions just to make endpoint output look good; ensure feature declarations reflect the true configuration state.

## 9. Examples of Spring Cloud Features

### 9.1. Discovery and LoadBalancer

Spring Cloud Commons declares abstract features for common contracts such as `DiscoveryClient` and `LoadBalancerClient`.

This helps the endpoint show whether foundational abstractions are resolved in the ApplicationContext. Implementations like Eureka, Consul, or Zookeeper can provide beans under the discovery contract.

### 9.2. Reactive Discovery and Reactive LoadBalancer

Reactive modules may publish their own contracts such as `ReactiveDiscoveryClient` or `ReactiveLoadBalancer`. These are still abstract features because there is a common type for the endpoint to look up a bean.

Do not confuse blocking and reactive features. An application may have one type of client without the other depending on providers, dependencies, and auto-configuration conditions.

### 9.3. Circuit Breaker, API Gateway, and Spring Cloud Bus

These are examples of named features in the Spring Cloud Commons documentation. They represent functional-level capabilities and do not necessarily have a single common interface for the endpoint to look up a bean.

Implementing modules should publish these named features in a `HasFeatures` bean guarded by the module's actual conditions.

## 10. How Does the Features Endpoint Differ from Health and Compatibility Verification?

| Mechanism | Primary Question | How It Works |
| --- | --- | --- |
| `/actuator/features` | Which capabilities are declared by modules and recognized by the endpoint? | Aggregates `HasFeatures`; abstract features use bean lookup, named features use declarations. |
| Health indicator | Is the component healthy or reachable? | Calls health contributors/probes and aggregates status. |
| Compatibility verifier | Is the Spring Boot version compatible with the Spring Cloud release train? | Checks versions and fails if the configuration is incompatible. |
| Application startup condition | Was auto-configuration activated? | Evaluates classpath, beans, properties, and conditions. |

For example, `DiscoveryClient` may appear in `enabled` because the bean exists, while the remote registry may be unreachable. A health indicator is the appropriate component to check discovery reachability in the way supported by the provider.

Similarly, the features endpoint does not confirm that requests routed through LoadBalancer succeed, whether a circuit breaker is open, or whether API Gateway routes work properly. Combine the feature inventory with health, metrics, logs, and integration tests.

## 11. Securing and Using the Endpoint in Operations

The `/features` endpoint is read-only, yet its response can still disclose:
- Internal module and capability names.
- Canonical class names.
- Implementation versions.
- Vendor metadata.
- The presence or absence of certain integrations.

Only expose the endpoint in appropriate environments and networks. In production:
1. Only add `features` to actuator exposure if operations teams genuinely need it.
2. Protect the endpoint with authentication and authorization.
3. Restrict access via a management network or network policy.
4. Do not expose all actuator endpoints publicly just to read features.
5. Do not use the response as an access control list or for security decisions.
6. Control exposure of class names if internal metadata must be kept confidential.

Example exposure configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,features
~~~

If you want to disable the endpoint completely in a profile:

~~~yaml
spring:
  cloud:
    features:
      enabled: false
~~~

Disabling the endpoint only removes the ability to query the feature inventory via Actuator; it does not disable capabilities such as discovery or load balancing.

## 12. Testing Abstract and Named Features

### 12.1. Testing an Abstract Feature with a Bean

Prepare an interface and implementation bean:

~~~java
public interface StockQuery {
    int available(String sku);
}

@Component
class DefaultStockQuery implements StockQuery {
    @Override
    public int available(String sku) {
        return 10;
    }
}
~~~

Declare the feature:

~~~java
@Bean
HasFeatures stockFeatures() {
    return HasFeatures.abstractFeatures(StockQuery.class);
}
~~~

After the context starts, call `/actuator/features` and verify that `StockQuery` is in `enabled`.

### 12.2. Testing an Abstract Feature Missing a Bean

Keep the `HasFeatures` declaration but do not create a `StockQuery` bean. The expected result is that the name `StockQuery` appears in `disabled`.

This test helps verify that the endpoint performs lookups by contract type.

### 12.3. Testing a Conditional Named Feature

Create a named feature in a configuration with `@ConditionalOnProperty`. Run two contexts:

| Configuration | Expected result |
| --- | --- |
| `app.payment.enabled=true` | Named feature `Payment Gateway` appears in `enabled`. |
| `app.payment.enabled=false` | Declaration is not loaded; the feature does not appear in `enabled` or `disabled`. |

The second result is very important: a named feature without a declaration is not automatically added to `disabled`.

### 12.4. Testing the HTTP Endpoint

Example Spring Boot test with the Actuator endpoint exposed:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "management.endpoints.web.exposure.include=features"
)
class FeaturesEndpointIntegrationTest {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void featuresEndpointReturnsEnabledAndDisabledGroups() {
        ResponseEntity<Map> response =
                restTemplate.getForEntity("/actuator/features", Map.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .containsKeys("enabled", "disabled");
    }
}
~~~

This is an integration test skeleton. Add assertions for feature names and types according to your application's fixtures. If the endpoint is protected by Spring Security, configure a test principal with permission to read the actuator endpoint.

### 12.5. Test Matrix

| ID | Scenario | Result to verify |
| --- | --- | --- |
| F1 | Abstract feature has a bean matching the contract. | Feature is in `enabled`. |
| F2 | Abstract feature is declared but missing a bean. | Contract name is in `disabled`. |
| F3 | Named feature is declared in HasFeatures. | Feature is in `enabled`. |
| F4 | Named feature configuration is disabled by property. | Feature does not appear in either list. |
| F5 | Named feature type has package metadata. | `type`, `version`, and `vendor` reflect the declared class. |
| F6 | Package lacks implementation version/vendor. | Corresponding metadata may be null. |
| F7 | `spring.cloud.features.enabled=false`. | Features endpoint is not auto-configured. |
| F8 | Endpoint does not have HTTP exposure. | URL is not accessible over HTTP even though the endpoint may exist in the context. |
| F9 | Principal lacks authorization. | Security policy rejects the request. |
| F10 | Discovery bean exists but registry is down. | Feature may still be enabled; health/registry tests detect the connection failure. |

## 13. Common Errors and How to Handle Them

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| `/actuator/features` returns 404. | Missing Actuator, endpoint not exposed, or `spring.cloud.features.enabled=false`. | Check dependencies, exposure, and properties. |
| Abstraction feature is in disabled. | No bean resolvable by contract type. | Check starter, condition report, component scan, and bean type. |
| Abstract feature has an implementation but is still disabled. | Bean is registered under a different type, multiple beans cause ambiguous lookup, or proxy/configuration is incorrect. | Check beans by contract type and how they resolve in the ApplicationContext. |
| Named feature appears enabled even though service is inactive. | `HasFeatures` declaration is always created, not guarded by capability conditions. | Move the declaration into a properly conditioned configuration. |
| Named feature does not appear in disabled when property is off. | Named feature is not declared so the endpoint has no entry to mark disabled. | This is expected behavior; check conditions for creating the HasFeatures bean. |
| Version or vendor is null. | JAR/package lacks Implementation-Version or Implementation-Vendor metadata. | Check manifest/build packaging; do not treat null as an endpoint error. |
| Feature is duplicated in response. | Multiple HasFeatures beans declare the same feature or multiple modules publish identical names. | Review declarations and unify owner/name. |
| Endpoint lists feature but real requests fail. | Feature inventory only checks beans/declarations, not full behavior. | Check health indicators, logs, metrics, and integration tests. |
| Endpoint disabled yet discovery still runs. | `spring.cloud.features.enabled` only disables the feature inventory endpoint. | Use the dedicated discovery toggle if the goal is to disable discovery. |
| Endpoint exists in context but HTTP returns 404. | Actuator endpoint is not exposed over the web. | Add `features` to management exposure. |
| Response leaks internal classes. | Endpoint is broadly exposed or lacks security policy. | Restrict management network and access permissions. |

## 14. Implementation Principles

1. **Choose the right feature type.** Use an abstract feature if there is a contract interface/abstract class; use a named feature for capabilities without a common contract.
2. **Use stable contracts.** An abstract feature should point to the interface that consumers actually depend on, not arbitrarily to an implementation class.
3. **Guard named features.** Only create the HasFeatures declaration when the capability is truly activated.
4. **Choose meaningful metadata types.** A named feature type should belong to the module providing the capability so version/vendor reflect the true source.
5. **Do not over-infer from the response.** Enabled does not mean remote dependencies are healthy; absent does not mean the endpoint checked and confirmed it disabled.
6. **Read the two lists separately.** Abstract features can appear in enabled or disabled; declared named features appear in enabled.
7. **Check manifest metadata.** Version/vendor depend on package implementation metadata.
8. **Combine health and metrics.** Use appropriate tools to check connectivity, latency, and runtime errors.
9. **Restrict the endpoint.** Features can disclose information about application structure.
10. **Verify against your release train.** Check the HasFeatures, NamedFeature API, and auto-configuration for your actual Spring Cloud version.

## 15. Completion Checklist

- [ ] Can explain the purpose of the Spring Cloud Features endpoint.
- [ ] Know the endpoint ID is `features` and the default HTTP path is `/actuator/features`.
- [ ] Distinguish abstract features that have an interface/abstract class contract.
- [ ] Distinguish named features described by a name and type.
- [ ] Understand that abstract features are checked by the endpoint via bean lookup by type.
- [ ] Understand that named features are added to enabled from HasFeatures declarations.
- [ ] Know that abstract features missing a bean can appear in disabled.
- [ ] Know that undeclared named features do not automatically appear in disabled.
- [ ] Can read enabled, disabled, name, type, version, and vendor.
- [ ] Understand that version/vendor for abstract features come from the runtime bean class.
- [ ] Understand that version/vendor for named features come from the declared class type.
- [ ] Can declare HasFeatures using abstractFeatures, namedFeatures, or builder.
- [ ] Place named feature declarations in conditional configurations.
- [ ] Enable/disable the endpoint with spring.cloud.features.enabled.
- [ ] Expose the endpoint via Actuator and protect it with a security policy.
- [ ] Distinguish the features endpoint from health indicators and compatibility verifiers.
- [ ] Have tests for abstract enabled/disabled and named features with/without declarations.
- [ ] Do not use the feature inventory as sole proof of runtime health.

**Official documentation to cross-check for your project version:**

- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): Enabled Features, abstract/named features, and how to declare HasFeatures.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): `spring.cloud.features.enabled` property and default value.
- [Spring Cloud Commons – FeaturesEndpoint source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/actuator/FeaturesEndpoint.java): how the endpoint finds beans for abstract features and adds named features to the response.
- [Spring Cloud Commons – FeaturesEndpoint tests](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/test/java/org/springframework/cloud/client/actuator/FeaturesEndpointTests.java): examples testing enabled and disabled features.

Endpoints, metadata, and auto-configuration may vary by release train. Check the Spring Cloud BOM in use, verify HasFeatures declarations, and read the actual endpoint response in a test environment.
