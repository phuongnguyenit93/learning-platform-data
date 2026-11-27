# Cross-Checking Actual Beans Against Published Information

A Spring Cloud application may have discovery, load balancer, circuit breaker, or bus libraries on the classpath. However, having a dependency present does not mean the feature has been configured and its bean created in the ApplicationContext. A capability can also be published by a module in metadata even when the corresponding runtime component does not exist.

Spring Cloud Commons provides the **Features** Actuator endpoint to aggregate features declared by modules. The endpoint returns two groups, enabled and disabled, along with metadata such as name, type, version, and vendor. To read results accurately, you must understand how the endpoint cross-checks each feature type against the ApplicationContext: **abstract features** are checked via bean lookup by type; **named features** are published directly from declared metadata.

This lesson belongs to the **System Capabilities** chapter of **SPRING_CLOUD_CORE**. Its focus is using the Features endpoint to inspect declared capabilities, cross-checking against actual beans via Actuator beans and auto-configuration conditions via conditions, thereby identifying missing beans, misconfigured metadata, or features that are not actually operating.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain the purpose and response structure of the Spring Cloud Features endpoint.
2. Distinguish abstract features from named features.
3. Describe how FeaturesEndpoint looks up beans for abstract features.
4. Explain why a named feature can appear in enabled even when the corresponding bean does not exist.
5. Declare HasFeatures and NamedFeature in appropriate Spring configurations.
6. Understand the origin of the type, version, and vendor fields.
7. Distinguish classpath, auto-configuration, beans in context, and actual runtime capability.
8. Cross-check features with the beans, conditions, and health endpoints.
9. Diagnose disabled results, missing features, or inaccurate metadata.
10. Write tests confirming that published information accurately reflects bean status.

## 2. Why Cross-Check Features Against Beans?

Suppose an application has a dependency for service discovery. The build succeeds and the EurekaDiscoveryClient class is on the classpath. However, discovery configuration is disabled or auto-configuration conditions do not match, so there is no discovery client bean in the context.

If operations only checks dependencies, the team might conclude service discovery is ready. Meanwhile, the application has no bean to query the service list.

Another scenario: a module itself declares NamedFeature("Inventory Bus", InventoryBusConfiguration.class). If the configuration declaring HasFeatures is still created even though the runtime bus is not enabled, the endpoint may publish the feature in the enabled list even though the bus processing bean does not exist.

When checking system capabilities, distinguish four layers:

| Layer | Question | Inspection Tool or Source |
| --- | --- | --- |
| Classpath | Is the library or class present in the application? | Dependency tree, classpath |
| Auto-configuration | Are the configuration creation conditions satisfied? | /actuator/conditions |
| ApplicationContext | Does the required bean actually exist? | /actuator/beans, bean lookup |
| Runtime capability | Does the component connect and operate properly? | Health indicator, metrics, integration test |

The Features endpoint sits between feature declarations and beans in the context. It is useful for checking Spring Cloud metadata, but it does not replace checking system health and behavior.

## 3. Spring Cloud Commons Features Endpoint

Spring Cloud Commons provides an endpoint with ID features. By Spring Boot Actuator defaults, if web exposure is used and the management base path is unchanged, the URL is typically:

```http
GET /actuator/features
```

Spring Cloud documentation often refers to it shortly as /features because that is the endpoint ID. The full HTTP path is constructed according to Actuator rules. If the application changes management.endpoints.web.base-path, the path changes accordingly.

The endpoint returns two groups:

- enabled: list of features published as enabled.
- disabled: names of abstract features declared without finding a matching bean.

An illustrative response:

```json
{
  "enabled": [
    {
      "type": "com.example.discovery.EurekaDiscoveryClient",
      "name": "DiscoveryClient",
      "version": "5.0.4",
      "vendor": "Example Vendor"
    },
    {
      "type": "com.example.bus.InventoryBusConfiguration",
      "name": "Inventory Bus",
      "version": "5.0.4",
      "vendor": "Example Vendor"
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
```

This is JSON illustrating the structure, not a fixed result for every application. The number of features and metadata values depend on the HasFeatures beans provided by modules present in the context.

### 3.1. The Endpoint Does Not Scan the Entire Classpath

The Features endpoint does not automatically list every library in dependencies. Modules must declare features via HasFeatures beans. The endpoint only aggregates the declarations it receives.

This means:

- A library on the classpath that does not declare HasFeatures may not appear in the results.
- An abstract feature declared without an existing bean will appear in disabled.
- A declared named feature will be added to enabled based on metadata.
- If the configuration publishing HasFeatures is not loaded, the feature may not appear in either group.

Do not interpret a feature not appearing as certainty that the dependency or bean is absent. Check feature publishing configuration and bean registration.

## 4. Conditions for the Endpoint to Be Created and Accessed

The Features endpoint integrates with Spring Boot Actuator. In current Spring Cloud Commons, endpoint configuration is created when relevant conditions are satisfied:

1. The Actuator endpoint API is on the classpath.
2. The property spring.cloud.features.enabled is not set to false.
3. The endpoint is considered available by Spring Boot according to Actuator conditions.
4. Exposure configuration and access permissions allow clients to call the endpoint over the desired channel.

The spring.cloud.features.enabled property defaults to true. Creating the endpoint can be disabled separately:

```yaml
spring:
  cloud:
    features:
      enabled: false
```

This property only controls the Features endpoint. It does not disable all discovery, load balancing, or circuit breaker features in the application.

### 4.1. Exposing the Endpoint over HTTP

Spring Boot only exposes the health endpoint over HTTP by default in current Actuator configurations. To access the Features endpoint and supporting cross-check endpoints, you can configure:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - features
          - beans
          - conditions
```

Only expose endpoints needed for the operational environment. beans and conditions provide internal information about application structure, so network restrictions, authentication, and proper authorization are required. If the management base path or management port is customized, use the URL matching the actual configuration.

### 4.2. Distinguishing an Uncreated Endpoint from an Unexposed Endpoint

If calling /actuator/features returns HTTP 404, you cannot yet conclude the feature is disabled. One of the following cases may have occurred:

- Spring Cloud Commons did not create the Features endpoint due to missing Actuator API.
- spring.cloud.features.enabled=false.
- The endpoint is unavailable according to Actuator access configuration.
- The endpoint has not been exposed over HTTP.
- Management base path or port differs from the URL being called.
- Security or a gateway hides the endpoint with a non-descriptive response.

Check Actuator configuration, auto-configuration conditions, and startup logs before drawing conclusions.

## 5. Two Feature Types: Abstract and Named

Spring Cloud Commons classifies features into two types. The classification determines whether the endpoint checks actual beans or merely publishes metadata.

| Type | Declared Data | How the Endpoint Processes It | Result |
| --- | --- | --- | --- |
| Abstract feature | An interface or abstract class | Looks up a bean by type in the ApplicationContext | Enabled if bean exists; disabled if no bean found |
| Named feature | Display name and a representative class | Adds metadata directly to enabled | Does not perform bean lookup for the declared class |

For example, DiscoveryClient fits an abstract feature because it is an abstraction for which an application can have an implementation bean. A capability such as Spring Cloud Bus can be published as a named feature, using a readable name and representative configuration class.

### 5.1. Abstract Feature

A module declares:

```java
@Bean
HasFeatures commonsFeatures() {
    return HasFeatures.abstractFeatures(
        DiscoveryClient.class,
        LoadBalancerClient.class
    );
}
```

When the endpoint is invoked, it takes each class in the abstract features list and looks up a corresponding bean in the ApplicationContext. If a bean is found, the endpoint takes the object's actual class and adds the feature to enabled. If the lookup throws NoSuchBeanDefinitionException, the simple name of the declared type is added to disabled.

For example:

- DiscoveryClient.class is declared.
- The context has an EurekaDiscoveryClient implementation bean.
- The endpoint publishes a feature named DiscoveryClient in enabled.
- The type field uses the actual implementation class name EurekaDiscoveryClient.

If the context has no bean matching LoadBalancerClient.class, the endpoint adds LoadBalancerClient to disabled.

### 5.2. Named Feature

A module can declare:

```java
@Bean
HasFeatures inventoryBusFeatures() {
    return HasFeatures.namedFeatures(
        new NamedFeature(
            "Inventory Bus",
            InventoryBusConfiguration.class
        )
    );
}
```

The endpoint adds the named feature to enabled using NamedFeature metadata. It does not call ApplicationContext.getBean(InventoryBusConfiguration.class) to verify whether a bean exists.

Therefore, a named feature needs to be declared in a configuration with conditions matching the actual feature. If the HasFeatures bean exists while the feature is turned off, the endpoint can still publish the named feature as enabled.

This is the most important difference when cross-checking published information against actual beans.

## 6. How FeaturesEndpoint Processes Abstract Features

The current implementation performs the following general logic:

```java
private void addAbstractFeature(
        Features features,
        Class<?> type) {

    String featureName = type.getSimpleName();

    try {
        Object bean = this.context.getBean(type);
        Class<?> beanClass = bean.getClass();

        addFeature(
            features,
            new NamedFeature(featureName, beanClass)
        );
    }
    catch (NoSuchBeanDefinitionException ex) {
        features.getDisabled().add(featureName);
    }
}
```

This is a simplified snippet to explain the processing flow; variable names and class details may differ by version.

There are three points to note:

1. Lookup uses the type declared in the abstract feature.
2. The feature name in the response comes from type.getSimpleName(), not from the bean name in the registry.
3. Class metadata is built from bean.getClass(), i.e., the class of the found object.

### 6.1. One Bean Can Represent an Abstract Feature

Example:

```java
public interface InventoryClient {
    InventoryItem findById(String id);
}

@Component
class HttpInventoryClient implements InventoryClient {

    @Override
    public InventoryItem findById(String id) {
        // Call the inventory service.
        return null;
    }
}
```

Feature declaration:

```java
@Bean
HasFeatures inventoryFeatures() {
    return HasFeatures.abstractFeatures(InventoryClient.class);
}
```

If the context has a bean matching InventoryClient, the endpoint can publish:

- name: InventoryClient.
- type: actual class of the bean, e.g., HttpInventoryClient.
- version/vendor: package metadata of that actual class.

### 6.2. Multiple Beans Implementing One Type

ApplicationContext.getBean(Class) needs to find a single matching bean. If multiple beans implement the interface without a clear primary choice, Spring can throw NoUniqueBeanDefinitionException.

In Spring Framework, NoUniqueBeanDefinitionException extends NoSuchBeanDefinitionException. Because the FeaturesEndpoint implementation catches NoSuchBeanDefinitionException, a non-unique lookup can also be placed into disabled even though multiple matching beans actually exist.

When seeing an abstract feature in disabled while the beans endpoint shows multiple implementations, check:

- How many beans have the same type.
- Whether any bean is marked `@Primary`.
- Whether a more specific abstraction should be declared.
- Whether the feature configuration is describing the right contract to check.

Do not jump to concluding the library was not loaded when the actual cause is a non-unique bean lookup.

## 7. How NamedFeature Is Published

For a named feature, the endpoint uses the name and class passed in NamedFeature:

```java
private void addFeature(
        Features features,
        NamedFeature feature) {

    Class<?> type = feature.getType();

    features.getEnabled().add(
        new Feature(
            feature.getName(),
            type.getCanonicalName(),
            type.getPackage().getImplementationVersion(),
            type.getPackage().getImplementationVendor()
        )
    );
}
```

There is no bean query step in this processing block. The passed-in class primarily provides the type and package metadata for the published information.

Example:

```java
@Bean
HasFeatures paymentFeatures() {
    return HasFeatures.namedFeatures(
        new NamedFeature(
            "Payment Integration",
            PaymentAutoConfiguration.class
        )
    );
}
```

If paymentFeatures is created, the endpoint places Payment Integration in enabled. Whether the PaymentClient bean exists must be guaranteed by appropriate configuration conditions or separate checks.

### 7.1. Guard Named Features with the Same Conditions as the Real Feature

A good declaration pattern:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(PaymentClient.class)
@ConditionalOnProperty(
    prefix = "app.payment",
    name = "enabled",
    havingValue = "true"
)
class PaymentFeatureMetadataConfiguration {

    @Bean
    HasFeatures paymentFeatures() {
        return HasFeatures.namedFeatures(
            new NamedFeature(
                "Payment Integration",
                PaymentAutoConfiguration.class
            )
        );
    }
}
```

Metadata configuration should be enabled under the same conditions as the integration it describes. If the feature also depends on another bean, place the bean condition on the proper configuration or structure the auto-configuration so metadata and integration share the same lifecycle.

### 7.2. When to Choose Abstract vs. When to Choose Named?

| Need | Type to Use |
| --- | --- |
| Want to confirm a contract bean is present in the context | Abstract feature |
| Want to publish a capability with a friendly name and no single bean interface | Named feature |
| Have a clear interface representing the integration | Abstract feature |
| An auto-configuration group creates multiple beans and needs a summary label | Named feature, guarded by the group's conditions |
| Need to prove the component is connecting successfully | Health check or integration test, not just Features endpoint |

Do not choose a named feature just to avoid bean lookup if the real goal is confirming a bean exists. Conversely, do not use an abstract feature for a capability without a suitable representative bean type.

## 8. Understanding Metadata Fields

The Features endpoint publishes four fields in each enabled item:

| Field | Source | Interpretation |
| --- | --- | --- |
| name | Abstract: simple name of declared type; Named: name set by module | Display label |
| type | Abstract: actual bean class; Named: class passed to NamedFeature | Representative Java type |
| version | type.getPackage().getImplementationVersion() | Implementation version in package metadata |
| vendor | type.getPackage().getImplementationVendor() | Implementation vendor in package metadata |

### 8.1. Version Is Not Necessarily the Whole Application's Version

The version field comes from the package of the class used in metadata. It is not:

- The Spring Boot version of the entire application.
- The Spring Cloud release train version.
- The dependency version declared in the build file.
- The running image/container version.

For an abstract feature, the class used is the actual class returned from bean lookup. For a named feature, the class used is the class passed into NamedFeature.

### 8.2. Version or Vendor May Be Null

Package.getImplementationVersion() and getImplementationVendor() read package metadata, usually from the JAR's manifest. If the package lacks the corresponding fields, the result may be null.

This commonly occurs when running from build output directories, test environments, or artifacts that did not package manifest metadata as expected. Do not treat a null version as proof that the bean does not exist.

When you need to determine exact dependency versions, cross-check the dependency tree, artifact metadata, or SBOM. The Features endpoint provides convenient information for diagnostics, not a complete dependency inventory source.

### 8.3. Proxies Can Affect the Published Class

A bean may be wrapped in a proxy by AOP, transactions, refresh scope, or another mechanism. When the endpoint calls bean.getClass(), the observed class may be the proxy class.

In that case, the type field and package metadata may reflect the proxy class instead of the original implementation class expected by the reader. If version/vendor are unclear, inspect the bean in the beans endpoint, check the proxy target with an appropriate tool, or log the actual class in tests.

## 9. Registering HasFeatures in a Module

A module can declare multiple HasFeatures beans. Spring Cloud Commons uses this list to aggregate the response.

Example for a custom-built module:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(InventoryClient.class)
class InventoryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    InventoryClient inventoryClient() {
        return new DefaultInventoryClient();
    }

    @Bean
    HasFeatures inventoryFeatures() {
        return HasFeatures.abstractFeatures(
            InventoryClient.class
        );
    }
}
```

Both the business bean and the metadata bean reside in the same configuration guarded by a classpath condition. When the configuration is loaded, the feature is declared; the endpoint continues checking the contract bean in the ApplicationContext.

For modules with multiple independent integrations, you can separate each metadata group so each group has its own conditions. Do not bundle every capability into an unconditional HasFeatures bean if some integrations can be disabled per environment.

### 9.1. Example Combining Abstract and Named

```java
@Bean
HasFeatures applicationFeatures() {
    return HasFeatures.builder()
        .abstractFeature(InventoryClient.class)
        .abstractFeature(PaymentClient.class)
        .namedFeature(
            new NamedFeature(
                "Event Publishing",
                EventPublisherAutoConfiguration.class
            )
        )
        .build();
}
```

In this example:

- InventoryClient is cross-checked against the actual bean.
- PaymentClient is cross-checked against the actual bean.
- Event Publishing is published according to named feature metadata.

If a module enables only inventory while disabling payment, ensure the HasFeatures configuration and feature list reflect the desired state. If both abstract features are declared together, payment will appear in disabled when its bean is absent.

## 10. Cross-Checking with the Beans Endpoint

The /actuator/beans endpoint provides the list of beans in the ApplicationContext. This is where you inspect bean names, bean types, and the context containing each bean.

You can expose both endpoints to cross-check:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - features
          - beans
```

Workflow:

1. Call /actuator/features and note which features are enabled/disabled.
2. Call /actuator/beans and locate the corresponding bean type or name.
3. For an abstract feature in disabled, check whether any bean is assignable to the declared type.
4. For a named feature in enabled, verify that metadata configuration was properly guarded and the actual business bean is present.
5. Check whether the bean resides in a child context or parent context matching where the endpoint is running.

beans displays bean names and types, while features provides capability labels. The two endpoints answer different questions and should be read together.

### 10.1. Beans Residing in a Child ApplicationContext

Some Spring Cloud systems create separate child contexts, such as per-service-ID contexts in LoadBalancer or named contexts. The features endpoint runs inside a specific ApplicationContext.

If a bean resides in a child context and is not visible from the context hosting FeaturesEndpoint, or vice versa, lookup results may differ from expectations. Check context ownership and parent-child relationships when diagnosing missing beans.

## 11. Cross-Checking with the Conditions Endpoint

The /actuator/conditions endpoint displays evaluated auto-configuration conditions and why they matched or did not match.

When an abstract feature is in disabled:

1. Identify which configuration class is expected to create the bean.
2. Find that class in conditions.
3. Inspect `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnProperty`, and other conditions.
4. Compare actual properties against active profiles and property sources.
5. Check whether the auto-configuration was excluded or affected by configuration ordering.

For example, the discovery client class may be on the classpath yet `@ConditionalOnProperty("spring.cloud.discovery.enabled")` does not match. In that case, auto-configuration may skip registering the DiscoveryClient bean.

The Features endpoint tells you the contract is missing from the context; the conditions endpoint helps explain why auto-configuration did not create the bean.

## 12. Cross-Checking with Health and Operational Capability

A bean existing does not mean the capability is operating properly. For example, a DiscoveryClient bean may be created successfully while the registry is unreachable.

Distinguish clearly:

| Tool | What Does It Verify? | What Does It Not Prove on Its Own? |
| --- | --- | --- |
| /actuator/features | Feature was declared; abstract feature had a successful bean lookup | External connectivity or business execution works |
| /actuator/beans | Bean is present in context and its bean type | Bean can serve requests successfully |
| /actuator/conditions | Reasons why auto-configuration conditions matched/did not match | Runtime dependency is healthy |
| /actuator/health | Status of configured health contributors | Every feature is published or every business path succeeds |
| Metrics/logs | Activity observed at runtime | Complete state coverage if instrumentation is absent |

For example, a discovery feature in enabled only tells you the bean lookup succeeded. To verify the registry is reachable, inspect the discovery health indicator or test service queries in an integration test.

## 13. Diagnosing Common Outcomes

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| /actuator/features returns 404 | Missing Actuator, feature endpoint disabled, not exposed, or different base path | Check dependencies, spring.cloud.features.enabled, and Actuator exposure |
| Feature appears in neither enabled nor disabled | Module did not declare HasFeatures or metadata configuration was not loaded | Check auto-configuration and HasFeatures creation conditions |
| Abstract feature in disabled yet class is on classpath | Bean was not registered or lookup is non-unique | Check beans and conditions |
| Named feature in enabled yet bean does not exist | Metadata is published directly, no bean lookup | Guard HasFeatures with capability conditions and check beans |
| Version or vendor is null | Package manifest lacks Implementation-Version/Vendor | Check JAR manifest or dependency metadata |
| Type is a proxy class | Bean is wrapped by AOP or scope proxy | Check bean type and target class |
| Feature reported enabled yet service does not work | Bean exists but dependency or runtime path fails | Check health, logs, metrics, and test integration calls |
| Abstract feature disabled despite multiple implementations | Lookup by Class could not pick a single unique bean | Check NoUniqueBeanDefinitionException, `@Primary`, or feature type |

### 13.1. When a Feature Does Not Appear

The Features endpoint only processes features added to HasFeatures lists. If a feature appears in neither group, do not start by checking beans. First verify:

- Whether the configuration declaring HasFeatures is created.
- Whether classpath/property/bean conditions match.
- Whether the module declares the feature in the running version.
- Whether metadata configuration was excluded by a profile or exclusion.

### 13.2. When a Named Feature Falsely Reports Enabled

This is usually a metadata publishing condition issue. For example, HasFeatures is created unconditionally while the integration client is only created when app.payment.enabled=true.

Move the metadata bean into the same configuration guarded by the integration's conditions, or add matching conditions. Test both enabled and disabled cases to ensure the enabled list reflects intent.

## 14. Testing FeaturesEndpoint

You do not need to run a real service registry to test feature publishing logic. You can create a small test ApplicationContext with one real bean, one abstract feature without a bean, and one named feature.

The example below illustrates a test in an appropriate package to access the endpoint's result types:

```java
@Configuration(proxyBeanMethods = false)
class FeatureTestConfiguration {

    @Bean
    InventoryClient inventoryClient() {
        return new StubInventoryClient();
    }

    @Bean
    HasFeatures declaredFeatures() {
        return HasFeatures.builder()
            .abstractFeature(InventoryClient.class)
            .abstractFeature(PaymentClient.class)
            .namedFeature(
                new NamedFeature(
                    "Inventory Bus",
                    InventoryBusConfiguration.class
                )
            )
            .build();
    }
}
```

Test:

```java
@Test
void publishesAbstractAndNamedFeatures() {
    try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(
                 FeatureTestConfiguration.class
             )) {

        List<HasFeatures> declarations =
            new ArrayList<>(
                context.getBeansOfType(HasFeatures.class).values()
            );

        FeaturesEndpoint endpoint =
            new FeaturesEndpoint(declarations);

        endpoint.setApplicationContext(context);

        FeaturesEndpoint.Features result =
            endpoint.features();

        assertThat(result.getEnabled())
            .extracting(FeaturesEndpoint.Feature::getName)
            .contains("InventoryClient", "Inventory Bus");

        assertThat(result.getDisabled())
            .contains("PaymentClient");
    }
}
```

The test demonstrates three outcomes:

- InventoryClient is declared and the bean exists, so it appears in enabled.
- PaymentClient is declared yet the bean does not exist, so it appears in disabled.
- Inventory Bus is a named feature, so it appears in enabled from metadata even though the test does not register an InventoryBusConfiguration bean.

This directly verifies the difference between abstract and named features.

### 14.1. Testing Version/Vendor Metadata

You can assert type and metadata:

```java
FeaturesEndpoint.Feature feature =
    result.getEnabled().stream()
        .filter(item -> item.getName().equals("InventoryClient"))
        .findFirst()
        .orElseThrow();

assertThat(feature.getType())
    .isEqualTo(StubInventoryClient.class.getCanonicalName());
```

Version/vendor values depend on the manifest of the artifact running the test. Do not hard-code a value if tests run from a build output directory without package metadata. You can assert null or prepare a test JAR with a defined manifest if you need to verify specific versions.

### 14.2. Testing Named Features When Conditions Are Off

Create two ApplicationContexts or two test configurations:

- Condition enabled case: the HasFeatures bean is created and the named feature appears in enabled.
- Condition disabled case: the HasFeatures bean is not created and the named feature does not appear.

This test confirms that metadata is properly guarded alongside the capability's lifecycle.

### 14.3. Testing Non-Unique Bean Lookup

If an abstract feature uses an interface with multiple implementations, explicitly test behavior when there is no primary candidate. A non-unique lookup may be placed into disabled by the endpoint because the exception is caught in the implementation.

You can write a dedicated test demonstrating this behavior, then decide whether to use a more specific feature type or configure a primary candidate.

## 15. Endpoint Security and Operations

The Features endpoint is read-only, yet its metadata can disclose:

- Integration components in use.
- Implementation class names.
- Library versions.
- Artifact vendors.
- Capabilities currently declared or missing.

In production:

1. Only expose the endpoint when there is an operational need.
2. Restrict the management port or access network.
3. Require authentication and authorization.
4. Do not expose all of Actuator just to use the Features endpoint.
5. Avoid putting sensitive internal metadata into feature names.
6. Ensure beans/conditions endpoints are also protected if exposed for diagnostics.

If using Spring Security with a custom SecurityFilterChain, confirm that rules for Actuator endpoints still apply. Do not assume default protection configurations continue working after an application defines its own security chain.

## 16. Cross-Checking Workflow During Deployment

When a capability does not behave as expected, you can follow this sequence:

1. Call /actuator/features to determine whether the feature is published.
2. Identify whether the feature is abstract or named based on how the module declares it.
3. For an abstract feature, check the bean type in /actuator/beans.
4. For a named feature, check the HasFeatures bean creation conditions and the actual business bean.
5. If the bean is missing, inspect /actuator/conditions to find unmatched conditions.
6. Check properties, profiles, dependencies, and auto-configuration exclusions.
7. Check /actuator/health to verify whether runtime dependencies are healthy.
8. Use logs, metrics, and integration tests to confirm the business path.
9. Check version/vendor metadata if you need to verify the running artifact.
10. Fix the feature publishing configuration and re-test both enabled and disabled cases.

This workflow avoids confusing "declared", "bean created", and "operating".

## 17. Common Misconceptions

**"If a dependency is on the classpath, the feature always appears."** The Features endpoint aggregates HasFeatures declarations. Classpath presence alone is not enough.

**"Enabled means every named feature has a corresponding bean."** Named features are published from metadata without performing a bean lookup. Declaration configurations must be properly guarded.

**"Disabled means the class is not on the classpath."** For an abstract feature, disabled indicates that bean lookup by type failed in the inspected context; the class may still be on the classpath.

**"Version is the Spring Cloud version of the whole application."** Version comes from package metadata of the class representing the feature.

**"Null version means the feature is broken."** The manifest may not contain Implementation-Version or Implementation-Vendor.

**"Bean present means the service is healthy."** A bean can exist yet fail to connect to the registry or dependency.

**"Feature not appearing means the bean does not exist."** The module may not have declared the feature in HasFeatures.

**"An abstract feature always finds a bean if at least one implementation exists."** Lookup by Class may be non-unique when multiple beans share the type without a primary candidate.

**"The Features endpoint replaces the beans and conditions endpoints."** Each endpoint provides a different perspective; combine them when diagnosing.

## 18. Practice Exercises

### Exercise 1. Reading the Response

A response has:

```json
{
  "enabled": [
    {
      "name": "DiscoveryClient",
      "type": "com.example.EurekaDiscoveryClient",
      "version": "5.0.4",
      "vendor": "Example"
    },
    {
      "name": "Inventory Bus",
      "type": "com.example.InventoryBusConfiguration",
      "version": null,
      "vendor": null
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
```

Explain:

1. Why is DiscoveryClient in enabled?
2. Why can Inventory Bus be enabled even though version/vendor are null?
3. What needs to be checked to confirm the Inventory Bus bean actually exists?
4. Does LoadBalancerClient being disabled prove the dependency is absent from the classpath?

### Exercise 2. Guarding a Named Feature

A module declares the named feature Payment Integration unconditionally, while the payment client is only created when app.payment.enabled=true.

Fix the configuration so metadata is only created when payment integration is enabled. Write tests for both true and false values.

### Exercise 3. Multiple Implementations

A MessageTransport interface has two beans: KafkaTransport and RabbitTransport. An abstract feature is declared with MessageTransport.class, yet the endpoint places the feature in disabled.

Explain the possible cause and propose a configuration or feature type so the result is meaningful.

### Exercise 4. Cross-Checking Auto-Configuration

The Features endpoint reports DiscoveryClient disabled. Build an investigation workflow from beans to conditions, the spring.cloud.discovery.enabled property, dependencies, and health indicators.

### Exercise 5. Designing Module Metadata

A module has three capabilities: HTTP inventory client, event publisher, and background scheduler. Choose abstract/named feature for each capability, write the HasFeatures beans, and identify the conditions that need guarding.

## 19. Self-Check Questions

1. What is the ID of the Features endpoint and what is its typical default HTTP URL?
2. What data do the enabled and disabled groups contain?
3. By what mechanism is an abstract feature checked?
4. Does a named feature perform an ApplicationContext bean lookup?
5. Why should a named feature be declared inside a conditional configuration?
6. Which class does the type field of an abstract feature come from?
7. Where are version and vendor retrieved from?
8. Why can version/vendor be null?
9. How can NoUniqueBeanDefinitionException affect abstract feature results?
10. Why does a feature not appearing not necessarily mean the bean does not exist?
11. When should you cross-check with the beans endpoint?
12. What root causes does the conditions endpoint help locate?
13. Does the Features endpoint confirm a successful registry connection?
14. How can you test for a named feature being published when the actual bean is absent?
15. Why should you not expose all of Actuator just to inspect features?

## 20. References

- [Spring Cloud Commons Reference — Enabled Features](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): the two feature types, how to declare HasFeatures, and the meaning of published information.
- [FeaturesEndpoint.java — Spring Cloud Commons source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/actuator/FeaturesEndpoint.java): how the endpoint cross-checks abstract features with ApplicationContext and builds enabled/disabled lists.
- [CommonsClientAutoConfiguration.java — Spring Cloud Commons source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/CommonsClientAutoConfiguration.java): conditions for creating the Features endpoint and Spring Cloud Commons feature declarations.
- [FeaturesEndpointTests.java — Spring Cloud Commons tests](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/test/java/org/springframework/cloud/client/actuator/FeaturesEndpointTests.java): examples testing abstract features with beans, abstract features missing beans, and named features.
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint availability conditions, exposure, access control, and the beans/conditions/health endpoints.
- [NoUniqueBeanDefinitionException — Spring Framework API](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/beans/factory/NoUniqueBeanDefinitionException.html): exception when bean lookup by type has multiple candidates.

## Key Takeaways

The Features endpoint publishes features that modules declare via HasFeatures. Abstract features are checked by bean lookup by type in the ApplicationContext; named features are added to enabled from metadata without automatically verifying the corresponding bean. Therefore, guard named features with the conditions of the real capability, cross-check abstract features with the beans endpoint, use conditions to explain auto-configuration, and use health/integration tests to verify runtime behavior. Version/vendor metadata comes from the representative class's package and may be null when artifacts do not provide manifest fields.
