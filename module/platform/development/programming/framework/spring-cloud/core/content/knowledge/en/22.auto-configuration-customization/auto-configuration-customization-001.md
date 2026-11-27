# Reading Bean Creation Conditions Before Replacing Defaults

This lesson belongs to the **Auto-Configuration Customization** chapter of the **SPRING_CLOUD_CORE** module. Spring Boot and Spring Cloud use auto-configuration to create default beans based on the classpath, existing beans, properties, and application type. When you want to replace a default implementation, the first step is to read the conditions that created that bean. Conditions typically indicate that the bean only appears when a library is present, when a property is enabled, when another dependency already exists, or when the application has not yet provided a replacement bean.

The most common extension mechanism is `@ConditionalOnMissingBean`. Auto-configuration declares a default bean with the condition “no matching bean exists yet”; if the application provides a bean matching the contract checked by the condition, auto-configuration backs off. This is an intentional and controllable way to replace defaults. To apply it properly, you need to inspect the condition evaluation report, read the bean factory method, and identify the exact type/name the condition looks for.

In the Spring Cloud ecosystem, this pattern appears in modules such as LoadBalancer, discovery, and service registry. For example, LoadBalancer can create a default `ReactorLoadBalancer` or `ServiceInstanceListSupplier` if the service's context does not yet have a custom bean. This lesson uses those examples to build a workflow for reading conditions before changing configuration.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the role of Spring Boot auto-configuration in Spring Cloud.
2. Distinguish auto-configuration from component scanning and application-declared configuration.
3. Read classpath, bean, property, resource, and web application conditions.
4. Use `--debug` or Actuator `/conditions` to inspect the ConditionEvaluationReport.
5. Locate the auto-configuration class and bean method that created a default bean.
6. Determine whether `@ConditionalOnMissingBean` checks by type or by name.
7. Replace a default with a custom bean matching the exact contract so auto-configuration backs off.
8. Distinguish conditional back-off from bean-definition overriding and `@Primary`.
9. Understand how auto-configuration ordering affects condition evaluation.
10. Use `ApplicationContextRunner` to test both the default case and the custom bean replacement case.
11. Customize Spring Cloud LoadBalancer per service ID without accidentally applying the configuration to every service.
12. Diagnose why a default bean does not appear or why a custom bean is not being used.

## 2. How Does Auto-Configuration Create Default Beans?

### 2.1. Auto-Configuration Is Conditional Configuration

Spring Boot auto-configuration consists of configuration classes that are discovered and applied automatically. Since Spring Boot 2.7, modern auto-configurations are typically listed in the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each line in the file is the name of an auto-configuration class. These classes usually use `@AutoConfiguration`, which is a form of Spring configuration with `proxyBeanMethods=false`, and rely on conditions to decide whether to create beans. Before Spring Boot 2.7, auto-configuration candidates were typically registered under the `EnableAutoConfiguration` key in `META-INF/spring.factories`; when reading older projects, check the discovery mechanism corresponding to that version.

General example:

~~~java
@AutoConfiguration
@ConditionalOnClass(CatalogSdk.class)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    DefaultCatalogClient catalogClient() {
        return new DefaultCatalogClient();
    }
}
~~~

The auto-configuration above is only applied when the `CatalogSdk` class is on the classpath. The default `CatalogClient` bean is only created when the ApplicationContext does not yet have a bean matching the `CatalogClient` contract.

### 2.2. Why Have Defaults?

A library needs to provide sensible behavior right after a user adds a starter. For example:
- A discovery starter creates a DiscoveryClient implementation.
- Spring Cloud LoadBalancer provides a default instance selection algorithm.
- Spring Cloud Context provides beans supporting refresh.
- Actuator auto-configuration registers endpoints when dependencies and conditions match.

Users can start with the defaults. When requirements change, they can supply their own implementation or adjust properties supported by the library.

### 2.3. Three Layers to Distinguish

| Layer | Responsibility | Example |
| --- | --- | --- |
| Dependency/classpath | Provides classes and modules that can be activated. | LoadBalancer starter, Eureka client. |
| Auto-configuration | Evaluates conditions and declares default beans. | LoadBalancerClientConfiguration. |
| Application configuration | Provides application beans, properties, or customizations. | Custom ServiceInstanceListSupplier. |

Adding a dependency only puts classes on the classpath. It does not guarantee that every bean in the module will be created; the conditions still have to match.

## 3. Reading Conditions in Order

When you want to replace a default bean, follow this flow:

~~~mermaid
flowchart TD
    A["Default bean does not fit requirements"] --> B["Find bean type and declaration site"]
    B --> C["Read class-level conditions"]
    C --> D["Read bean-method conditions"]
    D --> E["Inspect ConditionEvaluationReport"]
    E --> F{"Why was the bean created?"}
    F -->|"Classpath/property/bean condition"| G["Adjust the appropriate dependency or property"]
    F -->|"ConditionalOnMissingBean"| H["Provide custom bean matching the checked type/name"]
    F -->|"Condition did not match"| I["Fix the missing condition or dependency"]
    G --> J["Verify actual beans in context"]
    H --> J
    I --> J
    J --> K["Write context tests for default and custom"]
~~~

A practical workflow:

1. Identify the bean being injected and the behavior you need to change.
2. Record the bean type, bean name, qualifier, and injection point.
3. Locate the `*AutoConfiguration` class or provider configuration that creates that bean.
4. Read every condition at both the class level and the method level.
5. Inspect the ConditionEvaluationReport to see which conditions matched or did not match.
6. Choose the appropriate extension point: property, custom bean, customizer, strategy, or exclude.
7. Start the context and verify the actual bean present.
8. Write tests proving both the default and custom behaviors.

Do not start by renaming beans or enabling bean-definition overriding. First, understand the existing bean creation mechanism.

## 4. Common Condition Types

Spring Boot provides condition annotations that can be applied to configuration classes or individual `@Bean` methods.

### 4.1. Classpath Conditions

| Annotation | Meaning |
| --- | --- |
| `@ConditionalOnClass` | Applies only when the required class is on the classpath. |
| `@ConditionalOnMissingClass` | Applies only when the required class is not on the classpath. |

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.vendor.CatalogSdk")
class CatalogSdkConfiguration {
    // Configuration that requires this SDK.
}
~~~

Using `name` is useful when the class is an optional dependency. If the class is absent, the application can still start without loading that type.

### 4.2. Bean Conditions

| Annotation | Meaning |
| --- | --- |
| `@ConditionalOnBean` | Applies when a matching bean already exists. |
| `@ConditionalOnMissingBean` | Applies when no matching bean exists yet. |
| `@ConditionalOnSingleCandidate` | Applies when there is a single candidate or one candidate marked as primary. |

Example:

~~~java
@Bean
@ConditionalOnBean(DiscoveryClient.class)
InventoryLocator inventoryLocator(DiscoveryClient discoveryClient) {
    return new DiscoveryInventoryLocator(discoveryClient);
}
~~~

The `InventoryLocator` bean is only created when a `DiscoveryClient` exists. If the discovery provider has not created the bean, the locator is not created either.

### 4.3. Property Conditions

`@ConditionalOnProperty` checks values in the Environment:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
CatalogClient catalogClient() {
    return new HttpCatalogClient();
}
~~~

By default, the condition matches when the property exists and its value is not the string `false`. Use `havingValue` to require a specific value. Use `matchIfMissing=true` when you want the capability enabled if the property is not declared.

If multiple properties are declared in `name`, all of them must satisfy the condition. For boolean properties, state the intended semantics explicitly so readers do not have to infer from defaults.

### 4.4. Resource Conditions

`@ConditionalOnResource` checks whether a resource exists:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:catalog/schema.json")
class CatalogSchemaConfiguration {
}
~~~

This is appropriate when the configuration only makes sense if a required file, schema, or resource is present.

### 4.5. Web Application Type Conditions

`@ConditionalOnWebApplication` and `@ConditionalOnNotWebApplication` restrict configuration by application type:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE
)
class ReactiveCatalogConfiguration {
}
~~~

These conditions are useful when a starter supports both Servlet MVC and Reactive WebFlux, while each stack needs different beans.

### 4.6. Expression Conditions

`@ConditionalOnExpression` allows using SpEL:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("${app.catalog.enabled:false}")
class CatalogExpressionConfiguration {
}
~~~

Use this only when standard conditions cannot express the requirement. Referencing beans inside an expression can trigger very early bean initialization, before certain post-processing steps such as configuration properties binding; therefore, avoid using SpEL to query arbitrary bean state.

### 4.7. Combined Conditions

When a class or bean method has multiple conditions, all applied conditions must match for the configuration/bean to be registered. For instance, if a class has `@ConditionalOnClass` and a method has `@ConditionalOnMissingBean`, both layers of conditions participate in the decision.

Read both the conditions on the enclosing class and the conditions on the method. Looking only at method annotations can miss a class-level condition that prevents the entire configuration from loading.

## 5. What Does ConditionEvaluationReport Tell You?

### 5.1. Enabling Debug at Startup

Spring Boot can print the ConditionEvaluationReport to logs when debug is enabled:

~~~bash
java -jar app.jar --debug
~~~

Or:

~~~bash
java -Ddebug -jar app.jar
~~~

The report helps determine:
- Which auto-configurations were applied.
- Which conditions matched.
- Which conditions did not match.
- Why a condition did not match, such as a missing class, missing bean, or mismatched property.

Search for the relevant auto-configuration class name or bean method, then read the condition message rather than only looking at the overall verdict.

### 5.2. Using the Actuator Conditions Endpoint

If the application includes Spring Boot Actuator, the `conditions` endpoint provides a JSON report:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
~~~

Query:

~~~bash
curl http://localhost:8080/actuator/conditions
~~~

The endpoint can contain sections such as:
- `contexts`: the ApplicationContexts, typically the main context and possibly child contexts.
- `positiveMatches`: classes/methods whose conditions matched.
- `negativeMatches`: classes/methods that did not match, along with the list of conditions and messages.
- `unconditionalClasses`: auto-configurations that have no conditions.

Abbreviated example:

~~~json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "CatalogAutoConfiguration#catalogClient": [
          {
            "condition": "OnBeanCondition",
            "message": "@ConditionalOnMissingBean found no beans of type CatalogClient"
          }
        ]
      },
      "negativeMatches": {
        "ReactiveCatalogConfiguration": {
          "notMatched": [
            {
              "condition": "OnClassCondition",
              "message": "Required class was not found"
            }
          ]
        }
      }
    }
  }
}
~~~

The exact response format depends on the Spring Boot version. The example only illustrates how to read the main sections.

### 5.3. Exposing Conditions Safely

The conditions endpoint can reveal internal classes, dependencies, and why a capability is enabled or disabled. Expose it only on an appropriate management interface, protected by authentication/authorization and network policies. Do not publicly expose all Actuator endpoints just to inspect conditions.

### 5.4. Combining with the Beans Endpoint

`/actuator/conditions` explains condition decisions. `/actuator/beans` lists actual bean definitions. These two endpoints answer different questions:

| Endpoint | Question |
| --- | --- |
| `/actuator/conditions` | Why was an auto-configuration or bean method applied or not applied? |
| `/actuator/beans` | Which beans actually exist in the ApplicationContext? |
| `/actuator/configprops` | Which configuration values are configuration properties beans receiving? |

If the condition report states that a default bean backed off, check the beans endpoint to confirm that your custom bean is present in the context.

## 6. Reading @ConditionalOnMissingBean Before Replacing

### 6.1. The Back-Off Mechanism

`@ConditionalOnMissingBean` lets auto-configuration create a default when no bean satisfying the condition exists yet.

~~~java
@AutoConfiguration
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    DefaultCatalogClient catalogClient() {
        return new DefaultCatalogClient();
    }
}
~~~

When the application has a bean implementing `CatalogClient`, the default method is not applied. Auto-configuration backs off so the application-provided bean is used.

This is the built-in replacement mechanism for defaults. You do not need to register a bean with the exact same name as the default bean.

### 6.2. Replacing a Default with a Custom Bean

Suppose the application needs custom headers and timeouts for the Catalog client:

~~~java
@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean
    CatalogClient catalogClient() {
        return new AuthenticatedCatalogClient(
                URI.create("https://catalog.internal"),
                Duration.ofSeconds(2)
        );
    }
}
~~~

If auto-configuration uses `@ConditionalOnMissingBean(CatalogClient.class)`, the custom bean above causes the condition not to match and the default is not created.

To verify:
1. Run the application with the custom configuration.
2. Check the report: the default method no longer matches because a bean was found.
3. Verify the ApplicationContext has exactly one bean matching the expected contract.
4. Invoke the service client and verify the custom behavior.

### 6.3. Checking by Type or by Name

The condition can check by type:

~~~java
@ConditionalOnMissingBean(CatalogClient.class)
~~~

Or by bean name:

~~~java
@ConditionalOnMissingBean(name = "catalogClient")
~~~

Checking by type is usually more resilient when the goal is to replace an implementation by contract. Checking by name is only appropriate when the bean name is an intentional part of the extension point.

If the condition checks by name and the custom bean uses a different name, the default may still be created. Conversely, if the condition checks by type, the custom bean must actually be assignable to the checked type.

### 6.4. Multiple Beans with the Same Contract

If the application creates multiple beans of the same type:
- `@ConditionalOnMissingBean` may consider a matching bean to already exist and back off the default.
- Injection by type may become ambiguous.
- `@Primary` or `@Qualifier` may be needed to select a candidate.

Do not assume that “the default backed off” means “all injections are unambiguous.” Check both the bean count and how consumers inject them.

## 7. How @Bean Return Types Affect Conditions

When `@ConditionalOnMissingBean` is placed on a `@Bean` method without explicitly specifying a type or name, Spring Boot defaults to using the method's return type as the target type.

Example:

~~~java
@Bean
@ConditionalOnMissingBean
DefaultCatalogClient catalogClient() {
    return new DefaultCatalogClient();
}
~~~

The method returns `DefaultCatalogClient`. Bean conditions can rely on the method's type metadata.

If the condition is meant to check the `CatalogClient` contract, declare it explicitly:

~~~java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
DefaultCatalogClient catalogClient() {
    return new DefaultCatalogClient();
}
~~~

This approach both checks the right contract and exposes a concrete return type so Spring has fuller implementation type information.

Spring Boot recommends providing as much type information as possible in the return type of `@Bean` methods. This is especially important when conditions need to evaluate types from bean definitions before beans are instantiated.

## 8. Condition Evaluation Timing and Configuration Ordering

### 8.1. Conditions Only See Processed Bean Definitions

`@ConditionalOnBean` and `@ConditionalOnMissingBean` evaluate bean definitions that have already been processed at the time the condition runs. If a custom bean is registered after the condition has already been evaluated, it cannot retroactively change the earlier condition's result.

This is why Spring Boot recommends using these two conditions primarily on auto-configuration classes. Auto-configurations are loaded after user-defined bean definitions, so they can see beans declared by the application.

Avoid placing `@ConditionalOnMissingBean` on a regular component-scanned configuration if the goal is to wait for auto-configuration or another configuration to create a bean first.

### 8.2. Class-Level vs. Method-Level Conditions

| Placement | Impact |
| --- | --- |
| On `@Configuration` / `@AutoConfiguration` class | If the condition does not match, that configuration is not registered as a bean configuration. |
| On `@Bean` method | Only the bean created by that method is skipped; other bean methods in the class can still be processed. |

Choose placement based on the scope you need to control. If a configuration defines multiple independent beans, method-level conditions usually allow finer-grained customization per bean.

### 8.3. Auto-Configuration Ordering

Spring Boot supports:
- `@AutoConfigureBefore`
- `@AutoConfigureAfter`
- `@AutoConfigureOrder`
- The `before`, `after`, `beforeName`, and `afterName` attributes on `@AutoConfiguration`.

Example:

~~~java
@AutoConfiguration(after = WebClientAutoConfiguration.class)
public class CatalogWebClientAutoConfiguration {
}
~~~

Auto-configuration ordering affects the order in which bean definitions are registered and therefore can influence conditions based on already-processed beans. It does not directly dictate bean instance initialization order; dependencies and `@DependsOn` govern initialization lifecycle.

Do not use ordering to fix a custom bean of the wrong type or an incorrect condition. Check the contract and registration timing first; only declare ordering when two auto-configurations genuinely need to coordinate.

## 9. Class Conditions and Optional Dependencies

### 9.1. Why Separate Nested Configurations?

`@ConditionalOnClass` on a configuration class can inspect class metadata without loading every optional class. However, on a `@Bean` method, the JVM may need to load the return type or types referenced by the method before the method condition is evaluated.

For optional dependencies, isolate the code depending on that class inside a nested configuration:

~~~java
@AutoConfiguration
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(CatalogSdk.class)
    static class SdkConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient() {
            return new SdkCatalogClient();
        }
    }
}
~~~

When the SDK is not on the classpath, the nested configuration is not applied. The application can still run without loading the SDK classes.

### 9.2. Meta-Annotations and the name Attribute

If you create a composed annotation containing `@ConditionalOnClass` or `@ConditionalOnMissingClass`, use the `name` attribute to reference classes by name. Using the Class-typed `value` attribute is not handled in the same way inside meta-annotations.

## 10. Customization Options Before Excluding Auto-Configuration

Once you understand the conditions, choose the least invasive extension point that meets your requirements.

| Approach | Use when | Impact |
| --- | --- | --- |
| External property | The library already provides properties for the behavior you want to change. | Preserves the bean graph, changes configuration values. |
| Custom bean | Auto-configuration has `@ConditionalOnMissingBean` for that contract. | Custom bean is used, default backs off. |
| Customizer/strategy | The module provides a dedicated extension point. | Changes part of the behavior while keeping the rest of the default. |
| `@Primary` / `@Qualifier` | You need to select among multiple beans of the same type. | Selects injection candidate; does not remove the default. |
| Exclude auto-configuration | The module's entire auto-configuration is unsuitable. | Removes the whole group of beans provided by that auto-configuration; you must supply any needed parts yourself. |

### 10.1. Prefer Built-In Properties

For example, LoadBalancer provides properties to configure retry, caching, health-check suppliers, or per-service settings. If properties satisfy the requirement, use properties instead of recreating an entire supplier or load balancer.

Check property metadata and documentation for the exact release train. A property may be renamed, change defaults, or be absent in the version you are using.

### 10.2. Use a Custom Bean at the Extension Point

If the module guards a default bean with `@ConditionalOnMissingBean`, create a custom bean matching the checked contract. Do not create a class that fails to implement the expected interface and expect auto-configuration to recognize it.

### 10.3. Use a Customizer or Strategy

Many modules provide customizers to adjust part of the configuration:
- WebClientCustomizer.
- RestClientCustomizer.
- LoadBalancer request transformer.
- ServiceInstanceListSupplier.
- ReactorLoadBalancer.
- Spring Cloud strategy/provider interfaces.

This is usually a narrow change with minimal impact on other default configurations.

### 10.4. @Primary Does Not Replace a Bean

`@Primary` only prioritizes one bean when multiple candidates exist for injection by type. The default bean still exists in the ApplicationContext. If your goal is for auto-configuration to back off, check `@ConditionalOnMissingBean` and provide a bean matching the contract.

## 11. Bean Overriding Is Not a Back-Off Mechanism

Bean overriding happens when a new bean definition uses an identifier that has already been registered. It is different from auto-configuration skipping a default because of `@ConditionalOnMissingBean`.

For example, two configurations declaring the same bean name `catalogClient` can collide. Spring Boot generally disables bean-definition overriding by default; the `spring.main.allow-bean-definition-overriding` property can change this behavior depending on the version/configuration.

Do not enable overriding just to replace a default. Overriding by the same name creates fragility around bean names and registration order, making configuration harder to read and test. Spring Framework also warns that bean overriding makes configuration hard to understand and is moving toward deprecating/removing it in the future.

| Mechanism | Result |
| --- | --- |
| `@ConditionalOnMissingBean` | Auto-configuration does not register the default if a matching bean already exists. |
| `@Primary` | Picks a preferred bean when injecting among multiple candidates. |
| `@Qualifier` | Explicitly specifies which bean to inject. |
| Bean-definition overriding | A definition with the same identifier replaces the previous definition if the container allows it. |

## 12. Practical Example: Customizing Spring Cloud LoadBalancer

Spring Cloud LoadBalancer is a clear example of conditional auto-configuration.

### 12.1. Default ReactorLoadBalancer

In LoadBalancer configuration, Spring Cloud can create a default `ReactorLoadBalancer<ServiceInstance>` when no bean with that contract exists yet. The common default implementation is `RoundRobinLoadBalancer`.

Example structure in auto-configuration:

~~~java
@Bean
@ConditionalOnMissingBean
public ReactorLoadBalancer<ServiceInstance> reactorServiceInstanceLoadBalancer(
        Environment environment,
        LoadBalancerClientFactory clientFactory) {

    String serviceId = environment.getProperty(
            LoadBalancerClientFactory.PROPERTY_NAME);

    return new RoundRobinLoadBalancer(
            clientFactory.getLazyProvider(
                    serviceId,
                    ServiceInstanceListSupplier.class),
            serviceId);
}
~~~

How to read it:
1. The bean has the type contract `ReactorLoadBalancer<ServiceInstance>`.
2. The `@ConditionalOnMissingBean` condition checks whether the LoadBalancer child context already has a matching implementation.
3. If not, the factory creates the Round Robin default.
4. If service-specific configuration provides a matching bean earlier, the default can back off.

Exact class names, methods, and conditions should be cross-checked against the Spring Cloud LoadBalancer version in use.

### 12.2. Default ServiceInstanceListSupplier

LoadBalancer also creates a `ServiceInstanceListSupplier` when a matching DiscoveryClient is present and no custom supplier exists yet. Example conditions may include:

~~~java
@Bean
@ConditionalOnBean(DiscoveryClient.class)
@ConditionalOnMissingBean
ServiceInstanceListSupplier discoveryClientServiceInstanceListSupplier(
        ConfigurableApplicationContext context) {

    return ServiceInstanceListSupplier.builder()
            .withBlockingDiscoveryClient()
            .withCaching()
            .build(context);
}
~~~

This is a default supplier using blocking discovery and caching. For reactive providers, the corresponding configuration can use ReactiveDiscoveryClient. Discovery mode conditions and service-specific configuration also affect which bean is created.

### 12.3. Replacing the Supplier for One Service

If only the `inventory-service` needs a custom supplier, use `@LoadBalancerClient` to declare configuration by service ID:

~~~java
@Configuration
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class
)
public class InventoryClientRegistration {
}
~~~

The configuration is loaded inside the LoadBalancer child context for that service. Example supplier configuration:

~~~java
public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withBlockingDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

Notes:
- Configuration classes dedicated to a LoadBalancer client should not be component-scanned into the main context if doing so would apply the custom bean globally.
- The custom bean must match the contract checked by the default condition.
- The configuration only affects the declared service ID.
- If the application uses reactive discovery, choose the corresponding reactive supplier instead of the blocking supplier.
- Check the actual conditions in the source code of your release train.

### 12.4. Read the Source Code Before Replacing

When opening the source of `LoadBalancerClientConfiguration`, look for:
- `@ConditionalOnDiscoveryEnabled`.
- `@ConditionalOnBlockingDiscoveryEnabled` or its reactive counterpart.
- `@ConditionalOnBean(DiscoveryClient.class)`.
- `@ConditionalOnMissingBean`.
- Property conditions selecting defaults, zone preference, health checks, or retries.
- `@AutoConfigureAfter` when one configuration depends on beans from another configuration.

Only after understanding those conditions should you decide to add a supplier, load balancer, or property. If the custom bean does not appear, the condition report and child context will help pinpoint the cause.

## 13. Excluding Auto-Configuration Only When Truly Needed

You can exclude a specific auto-configuration via annotation:

~~~java
@SpringBootApplication(
        exclude = CatalogAutoConfiguration.class
)
public class OrdersApplication {
}
~~~

Or via property:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.example.catalog.autoconfigure.CatalogAutoConfiguration
~~~

Excluding an entire auto-configuration can remove many related beans at once. Before using it, read the entire class and its nested configurations, then identify which beans the application must supply itself after exclusion.

Do not exclude an auto-configuration merely because one default bean does not fit if the module already provides a custom bean or customizer for the specific part you need to change.

## 14. Testing Conditions with ApplicationContextRunner

`ApplicationContextRunner` lets you test auto-configuration in a small, isolated context without starting the full application.

### 14.1. Example Configuration

~~~java
@AutoConfiguration
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    DefaultCatalogClient catalogClient() {
        return new DefaultCatalogClient();
    }
}
~~~

### 14.2. Testing That the Default Is Created

~~~java
class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class
                            )
                    );

    @Test
    void createsDefaultWhenNoCustomBeanExists() {
        contextRunner.run(context ->
                assertThat(context)
                        .hasSingleBean(CatalogClient.class)
                        .hasSingleBean(DefaultCatalogClient.class)
        );
    }
}
~~~

The test confirms that when no custom bean exists, the default is created.

### 14.3. Testing That a Custom Bean Makes the Default Back Off

~~~java
@Test
void backsOffWhenCustomBeanExists() {
    contextRunner
            .withBean(
                    CatalogClient.class,
                    CustomCatalogClient::new
            )
            .run(context -> {
                assertThat(context)
                        .hasSingleBean(CatalogClient.class)
                        .hasSingleBean(CustomCatalogClient.class)
                        .doesNotHaveBean(DefaultCatalogClient.class);
            });
}
~~~

This test verifies that a custom bean matching the contract prevents the default from being registered.

### 14.4. Testing Property Conditions

~~~java
@Test
void doesNotCreateCatalogClientWhenDisabled() {
    contextRunner
            .withPropertyValues("app.catalog.enabled=false")
            .run(context ->
                    assertThat(context)
                            .doesNotHaveBean(CatalogClient.class)
            );
}
~~~

The test requires the auto-configuration to have the corresponding `@ConditionalOnProperty`. It proves that the disabled property prevents the bean from being created.

### 14.5. Testing Optional Classes

You can use `FilteredClassLoader` to simulate an optional library being absent from the classpath:

~~~java
@Test
void skipsSdkConfigurationWhenSdkIsMissing() {
    contextRunner
            .withClassLoader(
                    new FilteredClassLoader(CatalogSdk.class)
            )
            .run(context ->
                    assertThat(context)
                            .doesNotHaveBean(CatalogClient.class)
            );
}
~~~

This test is useful when a starter supports multiple providers or optional dependencies. Ensure that the filtered class is not referenced from a method or class outside the isolated conditional region.

### 14.6. What to Test?

| Test case | What to verify |
| --- | --- |
| No custom bean | Default is created. |
| Custom bean matching contract | Default backs off. |
| Custom bean with wrong type | Default is still created if the condition does not recognize that bean. |
| Property disabled | Bean method/class is excluded by the condition. |
| Optional class absent | Configuration depending on the class is not loaded. |
| Multiple beans of same type | Injection is unambiguous using qualifier/primary as designed. |
| LoadBalancer child context | Custom bean resides in the right service-specific context. |

Do not just assert that the context starts successfully. Verify bean types, bean counts, qualifiers, and actual behavior.

## 15. Troubleshooting Workflow When a Custom Bean Fails to Replace a Default

| Observation | Question to check | Action to take |
| --- | --- | --- |
| Default still appears | Does the condition check by type or by name? | Provide the right contract or bean name. |
| Custom bean is not created | Which class/method condition failed to match? | Read positive/negative matches and properties. |
| Custom bean exists but wrong one injected | Are there multiple candidates of the same type? | Use qualifier or primary appropriately. |
| Optional provider does not work | Is the class on the classpath and does the class condition match? | Inspect dependency tree and nested configurations. |
| Condition does not see custom bean | Was the custom bean registered before the auto-config condition ran? | Place missing-bean conditions in properly ordered auto-configuration. |
| Unintended global custom configuration | Is the child configuration being component-scanned? | Separate per-service configuration from component scanning. |
| Exclusion removes too many beans | Which nested configs does the auto-configuration class contain? | Exclude only when ready to supply related beans yourself. |
| Same-name bean conflict | Are two definitions using the same identifier? | Use type-based back-off or rename beans; avoid unnecessary overriding. |
| Report does not show auto-configuration | Is there an issue with imports, dependencies, or excludes? | Check AutoConfiguration.imports and the condition report. |

## 16. Implementation Principles

1. **Read source before replacing.** Find the auto-configuration class, bean method, and all related conditions.
2. **Use reports to verify.** ConditionEvaluationReport shows why something matched or did not match; do not infer solely from the dependency list.
3. **Replace by contract.** A custom bean must implement the exact type or name that `@ConditionalOnMissingBean` checks.
4. **Keep type metadata clear.** Declare concrete return types on `@Bean` methods.
5. **Prefer properties/customizers.** Use narrow extension points before replacing an entire implementation.
6. **Understand registration order.** Missing-bean conditions only see bean definitions already processed.
7. **Use ordering purposefully.** Before/after controls auto-configuration order, not a substitute for checking types and conditions.
8. **Distinguish back-off from overriding.** Avoid relying on duplicate bean names to replace defaults.
9. **Check child contexts.** For per-service LoadBalancer, the bean must be registered in the corresponding child context.
10. **Test both branches.** Have tests for defaults and custom beans, along with property/class conditions.
11. **Protect diagnostic endpoints.** Conditions and beans can expose internal application structure.
12. **Verify against your release train.** Conditions, class names, and properties can change across Spring Boot/Spring Cloud versions.

## 17. Completion Checklist

- [ ] Can explain how auto-configuration creates default beans based on conditions.
- [ ] Know that modern auto-configurations are listed in AutoConfiguration.imports.
- [ ] Distinguish classpath, bean, property, resource, and web conditions.
- [ ] Can read conditions at both class level and bean method level.
- [ ] Can enable --debug to inspect ConditionEvaluationReport.
- [ ] Can query /actuator/conditions in a secured environment.
- [ ] Distinguish positiveMatches and negativeMatches.
- [ ] Know that @ConditionalOnMissingBean checks by type/name.
- [ ] Understand that defaults back off when a matching custom bean is registered.
- [ ] Know that @Bean method return types affect type metadata.
- [ ] Understand that conditions only see processed bean definitions.
- [ ] Distinguish class-level and method-level conditions.
- [ ] Understand @AutoConfigureBefore, @AutoConfigureAfter, and @AutoConfigureOrder.
- [ ] Distinguish back-off, @Primary, @Qualifier, and bean-definition overriding.
- [ ] Can read conditions in Spring Cloud LoadBalancer configuration.
- [ ] Know how to replace ReactorLoadBalancer or ServiceInstanceListSupplier per service ID.
- [ ] Have ApplicationContextRunner tests for default, custom bean, and property conditions.
- [ ] Exclude auto-configuration only after identifying the beans you must supply yourself.

**Official documentation to cross-check for your project version:**

- [Spring Boot – Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): auto-configuration discovery, condition annotations, bean back-off, type metadata, and ordering.
- [Spring Boot – Troubleshoot Auto-configuration](https://docs.spring.io/spring-boot/4.0/how-to/application.html): ConditionEvaluationReport, --debug, and reading auto-configuration source.
- [Spring Boot Actuator – Conditions Endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/conditions.html): positiveMatches, negativeMatches responses, and condition messages.
- [Spring Boot – ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): how the condition resolves bean candidates and processing-time limitations.
- [Spring Framework – Bean Definition and Overriding](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): bean identity, overriding, and caveats around duplicate bean names.
- [Spring Cloud LoadBalancer – LoadBalancerClientConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/annotation/LoadBalancerClientConfiguration.java): real-world example of default ReactorLoadBalancer, ServiceInstanceListSupplier, and back-off conditions.

APIs and auto-configuration may change across release trains. Verify against your running version's Spring Boot/Spring Cloud BOM, condition report, and source code before replacing a default bean.