# Testing Default Configuration and Custom Replacement Beans

This lesson belongs to the **Testing** chapter of the **SPRING_CLOUD_CORE** module. Spring Boot and Spring Cloud often create default beans via auto-configuration. When the application provides its own bean, auto-configuration can back off thanks to `@ConditionalOnMissingBean`. You must test both branches: without a custom bean, the default appears; with a custom bean matching the contract, the default is not created and consumers receive the application's implementation.

`ApplicationContextRunner` is the right tool to test these conditions in a small, fast, and independent Spring ApplicationContext. It lets you load auto-configuration, add user configuration, change properties, simulate missing classpath dependencies, and inspect actual beans. Afterwards, `@SpringBootTest` can verify that the configuration works in the full application. This lesson also distinguishes production custom beans from mocks or test-only bean overrides, because they verify different behaviors.

## 1. Learning Objectives

After this lesson, you can:

1. Explain why both default beans and custom beans must be tested.
2. Distinguish auto-configuration from user configuration in a test context.
3. Test `@ConditionalOnMissingBean` using `ApplicationContextRunner`.
4. Verify the default is created when no custom bean exists.
5. Verify a custom bean matching the contract makes the default back off.
6. Check bean types, bean names, bean counts, and concrete implementations.
7. Test property and optional-class conditions.
8. Read `ConditionEvaluationReport` when results differ from expectations.
9. Use `@TestConfiguration` and `@Import` to add beans in `@SpringBootTest`.
10. Distinguish `@MockitoBean` from custom replacement beans in the application.
11. Understand the role of `@Primary`, `@Qualifier`, and bean overriding in tests.
12. Test Spring Cloud LoadBalancer customizations inside the proper service-specific context.
13. Build a test matrix for default, custom, disabled condition, and missing dependency cases.
14. Avoid tests that only assert context startup without verifying the actual implementation.

## 2. Why Test Both Branches?

An auto-configuration typically provides defaults so an application works out of the box after adding a starter. When users need different behavior, they can supply their own bean via an extension point published by the library.

Example:

~~~java
@AutoConfiguration
public class InventoryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(InventoryClient.class)
    DefaultInventoryClient inventoryClient() {
        return new DefaultInventoryClient();
    }
}
~~~

The default bean is created only when the context does not yet have a bean matching `InventoryClient`. Therefore, two behaviors need verification:

- **No custom bean:** Spring creates a `DefaultInventoryClient` and consumers can inject it via the `InventoryClient` contract.
- **Custom bean present:** Spring uses the implementation supplied by the application; the default bean is not registered.

If you only test the first case, tests miss condition bugs where the default still appears even after the application supplies its own implementation. If you only test the custom case, tests miss regressions where the library accidentally drops the default in standard setups.

~~~mermaid
flowchart TD
    A["Initialize test ApplicationContext"] --> B["Load auto-configuration"]
    B --> C{"User-provided InventoryClient bean exists?"}
    C -->|No| D["@ConditionalOnMissingBean matches"]
    D --> E["Create DefaultInventoryClient"]
    C -->|Yes| F["Condition does not match"]
    F --> G["Default backs off"]
    E --> H["Verify bean and behavior"]
    G --> H
    H --> I["Test PASSES when right implementation is used"]
~~~

## 3. Creating a Testable Auto-Configuration Example

To illustrate, create a contract for a client calling an inventory service:

~~~java
public interface InventoryClient {

    InventoryItem findById(String itemId);
}
~~~

The return model in the examples is a simple record:

~~~java
public record InventoryItem(String id, String source) {
}
~~~

Default implementation:

~~~java
public class DefaultInventoryClient implements InventoryClient {

    @Override
    public InventoryItem findById(String itemId) {
        return new InventoryItem(itemId, "default");
    }
}
~~~

Application's custom implementation:

~~~java
public class CustomInventoryClient implements InventoryClient {

    @Override
    public InventoryItem findById(String itemId) {
        return new InventoryItem(itemId, "custom");
    }
}
~~~

Auto-configuration:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class InventoryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(InventoryClient.class)
    DefaultInventoryClient inventoryClient() {
        return new DefaultInventoryClient();
    }
}
~~~

Note three points:

1. The bean method returns the concrete type `DefaultInventoryClient` so Spring has complete type metadata.
2. The condition checks the `InventoryClient` contract, not the bean name.
3. A custom implementation must implement `InventoryClient` to satisfy the condition.

In real projects, auto-configuration often includes classpath, property, or discovery provider conditions as well. Keep test examples synchronized with the conditions in production code.

## 4. Preparing ApplicationContextRunner

### 4.1. Testing Dependencies

With Maven, the test dependency is typically:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

`spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and Spring Boot test utilities. If your tests use Mockito or Spring TestContext integrations, verify they are on the test classpath.

Auto-configuration tests usually do not need to start a web server or the whole application. Using a context runner keeps tests fast and loads only the configuration under test.

### 4.2. Declaring a Shared Runner

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class InventoryAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    InventoryAutoConfiguration.class
                            )
                    );
}
~~~

`AutoConfigurations.of(...)` tells the runner to load the auto-configuration under test. This is crucial: if you only create a regular context without loading the auto-configuration, the test may never execute the bean method you want to verify.

Each call to `run(...)` creates a context for that test case and closes it once the callback completes. You can add per-test user configuration or properties without polluting state across cases.

## 5. Testing Default Bean Creation

When no `InventoryClient` bean is provided by the application, `@ConditionalOnMissingBean` must match.

~~~java
@Test
void createsDefaultClientWhenNoCustomBeanExists() {
    contextRunner.run(context -> {
        assertThat(context).hasSingleBean(InventoryClient.class);
        assertThat(context).hasSingleBean(DefaultInventoryClient.class);

        InventoryClient client = context.getBean(InventoryClient.class);
        assertThat(client).isInstanceOf(DefaultInventoryClient.class);

        assertThat(client.findById("item-42").source())
                .isEqualTo("default");
    });
}
~~~

The test verifies multiple layers:

- The `InventoryClient` contract has exactly one bean.
- The default implementation is present.
- The bean injected via the contract is indeed `DefaultInventoryClient`.
- The implementation's behavior matches the default.

Do not only assert `hasBean("inventoryClient")`. Bean names can change during refactoring; contract and behavior are far stronger evidence.

If the `InventoryItem` record in your project does not have a `source()` accessor, replace the assertion with the actual field or method on your model. The goal is to prove the result comes from the default implementation.

## 6. Testing That a Custom Bean Makes the Default Back Off

### 6.1. Declaring User Configuration

In the test, create a configuration providing the custom implementation:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
static class CustomInventoryConfiguration {

    @Bean
    CustomInventoryClient customInventoryClient() {
        return new CustomInventoryClient();
    }
}
~~~

The method returns the concrete type `CustomInventoryClient`, while the bean remains assignable to the `InventoryClient` contract.

### 6.2. Loading Custom Configuration Alongside Auto-Configuration

~~~java
@Test
void customClientReplacesDefaultClient() {
    contextRunner
            .withUserConfiguration(CustomInventoryConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(InventoryClient.class);
                assertThat(context).hasSingleBean(CustomInventoryClient.class);
                assertThat(context).doesNotHaveBean(DefaultInventoryClient.class);

                InventoryClient client = context.getBean(InventoryClient.class);
                assertThat(client).isInstanceOf(CustomInventoryClient.class);

                assertThat(client.findById("item-42").source())
                        .isEqualTo("custom");
            });
}
~~~

This test proves:
1. User configuration was loaded.
2. A custom bean matching the contract is in the context.
3. The condition on the default bean no longer matches.
4. The default implementation is not created.
5. Consumers injecting the contract receive the custom implementation.

Spring Boot designs auto-configurations to load after user-defined bean definitions. Therefore, `ApplicationContextRunner` combined with `withUserConfiguration` is ideal for testing back-off behavior.

### 6.3. Asserting Bean Count by Contract

The `hasSingleBean(InventoryClient.class)` assertion is very valuable. If both the default and custom beans appear, the test fails even if `@Primary` causes one implementation to be injected.

This is a critical distinction: the goal of backing off is that the default is not registered when a qualifying custom bean exists. Checking only the injected bean can overlook a lingering default bean in the context.

## 7. Testing Beans That Do Not Match the Contract

A custom bean that does not implement the contract checked by the condition will not make the default back off.

For example, a bean of a different type:

~~~java
public class InventoryClientAdapter {
    // Does not implement InventoryClient.
}
~~~

The test can register this bean:

~~~java
@Test
void unrelatedBeanDoesNotReplaceDefault() {
    contextRunner
            .withBean(InventoryClientAdapter.class, InventoryClientAdapter::new)
            .run(context -> {
                assertThat(context).hasSingleBean(InventoryClient.class);
                assertThat(context).hasSingleBean(DefaultInventoryClient.class);
                assertThat(context.getBean(InventoryClient.class))
                        .isInstanceOf(DefaultInventoryClient.class);
            });
}
~~~

The expected result is that the default is still created because the condition checks `InventoryClient`, and `InventoryClientAdapter` does not implement that contract.

This scenario catches a common mistake: the application declares a bean with a similar name or purpose that does not match the exact type expected by auto-configuration.

## 8. Testing by Property

Auto-configurations often combine property conditions with missing-bean conditions.

Example:

~~~java
@AutoConfiguration
public class InventoryPropertyAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.inventory",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    @ConditionalOnMissingBean(InventoryClient.class)
    DefaultInventoryClient inventoryClient() {
        return new DefaultInventoryClient();
    }
}
~~~

Because this is an auto-configuration variant with an added property condition, create a dedicated runner so subsequent tests load the exact class:

~~~java
private final ApplicationContextRunner propertyContextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                InventoryPropertyAutoConfiguration.class
                        )
                );
~~~

With this configuration, the default is created when:
- `app.inventory.enabled` equals `true`; or the property is omitted since `matchIfMissing=true`.
- No matching `InventoryClient` bean already exists.

Testing property disabled:

~~~java
@Test
void doesNotCreateDefaultWhenInventoryIsDisabled() {
    propertyContextRunner
            .withPropertyValues("app.inventory.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(InventoryClient.class);
                assertThat(context).doesNotHaveBean(DefaultInventoryClient.class);
            });
}
~~~

Testing property enabled:

~~~java
@Test
void createsDefaultWhenInventoryIsEnabled() {
    propertyContextRunner
            .withPropertyValues("app.inventory.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(InventoryClient.class);
                assertThat(context).hasSingleBean(DefaultInventoryClient.class);
            });
}
~~~

Testing custom bean when property is disabled:

~~~java
@Test
void customBeanCanExistWhenDefaultFeatureIsDisabled() {
    propertyContextRunner
            .withPropertyValues("app.inventory.enabled=false")
            .withUserConfiguration(CustomInventoryConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(InventoryClient.class);
                assertThat(context).hasSingleBean(CustomInventoryClient.class);
                assertThat(context).doesNotHaveBean(DefaultInventoryClient.class);
            });
}
~~~

The latter test verifies two independent mechanisms: the property stops the default auto-configuration from creating a bean, while user configuration can still supply the application's bean. If business requirements demand that disabling the property forbid any implementation, add corresponding conditions or validation; `@ConditionalOnProperty` on the default bean alone does not forbid user configuration.

## 9. Testing Optional Dependencies and Classpath Conditions

Some auto-configurations activate only when a library/provider is on the classpath. For example, configuration requiring an optional SDK:

~~~java
@AutoConfiguration
public class OptionalInventoryAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(InventorySdk.class)
    static class SdkConfiguration {

        @Bean
        @ConditionalOnMissingBean(InventoryClient.class)
        DefaultInventoryClient inventoryClient() {
            return new DefaultInventoryClient();
        }
    }
}
~~~

Putting classes that reference the SDK inside a nested configuration isolates the optional dependency. When the SDK is absent from the classpath, the nested configuration is not applied.

Use `FilteredClassLoader` to simulate a missing SDK:

~~~java
import org.springframework.boot.test.context.FilteredClassLoader;

@Test
void skipsSdkConfigurationWhenSdkIsMissing() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(
                            OptionalInventoryAutoConfiguration.class
                    )
            )
            .withClassLoader(
                    new FilteredClassLoader(InventorySdk.class)
            )
            .run(context -> {
                assertThat(context)
                        .doesNotHaveBean(InventoryClient.class);
            });
}
~~~

This test is especially valuable for starters with multiple integrations such as Eureka, Consul, or Zookeeper. Each provider should activate only when its class is on the classpath and all other conditions are satisfied.

## 10. Reading ConditionEvaluationReport in Tests

When a test fails to create the default or a custom bean fails to make the default back off, read the condition report instead of guessing.

You can attach a listener to the runner:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO)
                )
                .withConfiguration(
                        AutoConfigurations.of(
                                InventoryAutoConfiguration.class
                        )
                );
~~~

The report helps identify:
- Whether classpath conditions matched.
- Which beans a bean condition found.
- What values a property condition read.
- Which auto-configurations were applied.
- Which bean methods were skipped.

For example, if the report says the condition found an `InventoryClient` bean, the default backed off as designed. If the report says `InventorySdk` is missing, check test classpath dependencies instead of changing the condition.

In a full application, you can use Actuator `/actuator/conditions` if the endpoint is exposed and secured. However, for auto-configuration unit/context tests, the direct report from the runner is usually faster and more precise.

## 11. Testing with @SpringBootTest and @TestConfiguration

`ApplicationContextRunner` focuses on testing auto-configuration. Once those tests pass, you can add integration tests to verify that the custom configuration is used in the full application.

### 11.1. Importing Test Configuration

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(InventoryOverrideIntegrationTest.CustomConfiguration.class)
class InventoryOverrideIntegrationTest {

    @Autowired
    InventoryClient inventoryClient;

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void applicationUsesCustomInventoryClient() {
        assertThat(inventoryClient)
                .isInstanceOf(CustomInventoryClient.class);

        assertThat(applicationContext.getBeansOfType(InventoryClient.class))
                .hasSize(1);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class CustomConfiguration {

        @Bean
        CustomInventoryClient customInventoryClient() {
            return new CustomInventoryClient();
        }
    }
}
~~~

`@TestConfiguration` declares extra beans for the test without replacing the main application configuration. Use `@Import` to load the test configuration explicitly.

### 11.2. When Do You Need This Test?

Use `@SpringBootTest` when you want to verify:
- Real components inject the right custom bean.
- Other auto-configurations in the application do not create additional implementations of the same contract.
- Application profiles and properties do not alter the expected outcome.
- The custom bean works with real dependencies, proxies, and lifecycle callbacks.

You do not need `@SpringBootTest` for every condition combination. The full context starts slower and couples tests to configurations outside the scope under verification.

## 12. Distinguishing Custom Beans from Mock Beans in Tests

A common mistake is using a mock to replace a dependency in a test and then concluding that auto-configuration backed off properly.

### 12.1. @MockitoBean Replaces a Dependency for Testing

In modern Spring Framework, `@MockitoBean` can replace a bean in the test ApplicationContext with a Mockito mock:

~~~java
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class InventoryServiceTests {

    @MockitoBean
    InventoryRepository inventoryRepository;

    @Autowired
    InventoryService inventoryService;

    @Test
    void returnsItemFromRepository() {
        given(inventoryRepository.findById("item-42"))
                .willReturn(Optional.of(new InventoryItem("item-42", "test")));

        InventoryItem item = inventoryService.findById("item-42");

        assertThat(item.id()).isEqualTo("item-42");
        then(inventoryRepository).should().findById("item-42");
    }
}
~~~

Mockito imports used in the example:

~~~java
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
~~~

This test verifies `InventoryService` logic when the repository is replaced with a mock. It does not prove that `InventoryClient` auto-configuration backed off for a production custom bean.

`@MockitoBean` typically uses a replace-or-create strategy: if a matching bean exists, it replaces it; if none exists, it creates the mock. You can use `enforceOverride=true` when you want the test to fail if the target bean does not exist.

A replacement mock is registered directly in the test context and bypasses part of normal bean post-processing. If the original bean was wrapped by AOP such as transactions, retry, or method security, the mock does not automatically preserve that advice. When verifying proxies/AOP, test the real bean or consider spy/wrap semantics per Spring TestContext documentation.

### 12.2. A Production Custom Bean Is a Real Implementation

When testing auto-configuration back-off, provide a real implementation in user configuration:

~~~java
@Bean
CustomInventoryClient customInventoryClient() {
    return new CustomInventoryClient();
}
~~~

This implementation must implement the contract checked by the condition. When the context starts, the default auto-configuration must not create the default bean.

### 12.3. Comparison

| Tool | Purpose | Proves default backs off? |
| --- | --- | --- |
| `ApplicationContextRunner` + user configuration | Tests conditions and bean graph independently. | Yes, when asserting both the custom bean and the absence of the default. |
| `@TestConfiguration` | Adds real beans to a test context. | Possible, when testing auto-configuration alongside this configuration. |
| `@MockitoBean` | Replaces dependency with a mock to test consumer logic. | Does not by itself prove production auto-configuration back-off. |
| `@Primary` | Selects preferred bean when multiple candidates exist. | No; the default may still exist. |
| Bean-definition overriding | Replaces definitions sharing an identifier in the container/test. | No; does not test the extension-point contract properly. |

Older versions may use Spring Boot's `@MockBean`. Choose the bean-override annotation matching your project's Spring Boot/Spring Framework version. Do not migrate tests from `@MockBean` to `@MockitoBean` without checking dependency compatibility.

## 13. @Primary Does Not Replace the Default

Suppose the context has two beans:

- `DefaultInventoryClient` created by auto-configuration.
- `CustomInventoryClient` created by the application.

If the custom bean is marked `@Primary`, type-based injection may select the custom bean. However, the default still exists in the context.

This can make a naive test pass:

~~~java
@Autowired
InventoryClient inventoryClient;

@Test
void injectsPrimaryBean() {
    assertThat(inventoryClient)
            .isInstanceOf(CustomInventoryClient.class);
}
~~~

But this test does not verify back-off. Add:

~~~java
assertThat(applicationContext)
        .hasSingleBean(InventoryClient.class);

assertThat(applicationContext)
        .doesNotHaveBean(DefaultInventoryClient.class);
~~~

Use `@Primary` when you genuinely want multiple beans implementing the same contract and want to pick a default injection candidate. Use a custom bean matching the extension point when you want auto-configuration to skip creating the default.

## 14. Testing Spring Cloud LoadBalancer

Spring Cloud LoadBalancer is a real-world example of default beans and custom replacement beans. Each service ID has its own child ApplicationContext. Therefore, a custom `ReactorLoadBalancer` or `ServiceInstanceListSupplier` must be registered in the context of the service being customized.

### 14.1. Behaviors to Test

For a service ID like `inventory-service`, tests should verify:

1. Without a custom supplier, LoadBalancer uses the default DiscoveryClient-based supplier if providers and conditions match.
2. When dedicated configuration via `@LoadBalancerClient` supplies a custom supplier, the corresponding default supplier backs off.
3. Configuration for `inventory-service` does not accidentally apply to other service IDs.
4. Requests via WebClient/RestClient actually route to an instance returned by the supplier.
5. Empty instance lists and discovery errors are handled properly.

### 14.2. Configuring by Service ID

Example dedicated client declaration:

~~~java
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerTestConfiguration.class
)
class InventoryLoadBalancerTestSetup {
}
~~~

Custom supplier configuration:

~~~java
public class InventoryLoadBalancerTestConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

This example builds a supplier backed by DiscoveryClient and zone preference. For tests requiring deterministic data, replace the discovery source with a fixture or test provider returning a static instance list.

Do not place LoadBalancer client-specific configuration into global component scanning if doing so causes the custom bean to appear in every service's child context.

### 14.3. Testing the Child Context Instead of Only the Root Context

Per-service-ID LoadBalancer beans are created inside a child context. A test that only calls `applicationContext.getBeansOfType(...)` on the root context may not see that custom bean.

In integration tests, initialize the client for the target service ID, trigger creation of the corresponding LoadBalancer context, and verify:
- The Supplier/LoadBalancer is resolved from the right child context.
- Other service IDs still use their own configuration.
- Actual requests reach one of the instances supplied by the supplier.

Spring Cloud LoadBalancer documentation describes separate child contexts per service ID and configuration via `@LoadBalancerClient`. Tests must reflect this context boundary.

## 15. Recommended Test Matrix

| ID | Scenario | Expected verification |
| --- | --- | --- |
| T1 | No custom bean. | Default is created and implements the contract. |
| T2 | One custom bean matching contract. | Custom bean is used; default does not exist. |
| T3 | Bean of a different type. | Default is still created. |
| T4 | Two custom beans matching contract. | Default backs off; injection needs qualifier/primary if consumer expects a single candidate. |
| T5 | Property enabled. | Bean is created per condition. |
| T6 | Property disabled. | Default bean is excluded per condition. |
| T7 | Property disabled but custom user bean exists. | Custom bean still exists if condition applies only to default bean. |
| T8 | Optional class on classpath. | Nested auto-configuration is applied. |
| T9 | Optional class removed by FilteredClassLoader. | Configuration depending on class is not loaded. |
| T10 | Custom bean declared in @TestConfiguration. | Test context uses custom bean and default backs off. |
| T11 | Dependency replaced with @MockitoBean. | Consumer tested with mock; do not infer back-off from this test. |
| T12 | Custom bean only marked @Primary. | Injection picks primary, yet default still exists unless condition backs off. |
| T13 | LoadBalancer custom supplier per service ID. | Bean resolved in child context for the right service. |
| T14 | Other service ID without custom configuration. | Default configuration of other service is unaffected. |
| T15 | Condition report with logging listener. | Match/back-off reasons can be read when test fails. |

Not every test class has to contain all cases. Group tests by auto-configuration, property, and integration boundary for readability and speed.

## 16. Common Pitfalls and Fixes

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Default still created despite custom bean. | Custom bean does not implement the contract checked by condition. | Check bean type and target type in `@ConditionalOnMissingBean`. |
| Custom bean does not appear in test. | User configuration not loaded or missing condition dependency. | Use `withUserConfiguration` and read the report. |
| Test sees injected bean yet default still exists. | Custom bean marked `@Primary`. | Assert `hasSingleBean` and `doesNotHaveBean(DefaultType.class)`. |
| Condition does not recognize custom bean. | Method return type too broad or bean definition registered at wrong phase. | Declare concrete return type and use user configuration with runner. |
| Test runner does not create default. | Auto-configuration not loaded or class condition failed. | Check `AutoConfigurations.of`, classpath, and report. |
| Optional dependency test still initializes SDK class. | Optional class referenced from configuration outside condition guard. | Isolate in nested configuration with `@ConditionalOnClass`. |
| Custom bean test fails with multiple candidates. | Multiple beans share contract without clear injection target. | Use qualifier/primary when multiple beans are intended; for back-off tests, assert default absence. |
| @MockitoBean does not replace right bean. | Multiple candidates or qualifier/name mismatch. | Specify qualifier or bean name; use enforceOverride to verify target exists. |
| @SpringBootTest starts too slowly. | Full context used for every condition combination. | Move condition matrix to `ApplicationContextRunner`. |
| LoadBalancer test cannot find custom supplier. | Inspecting root context instead of per-service-ID child context. | Create client context and verify bean in child context. |
| LoadBalancer test passes yet requests hit wrong instance. | Only checked bean existence, not actual request routing. | Use test servers/fixtures and assert destination/response. |
| Test depends on run order. | Sharing mutable singletons, mocks, or external registries across tests. | Create isolated contexts, reset mocks, and use separate fixtures. |
| Test passes yet production uses default. | Test configuration has custom bean while production config is not imported/scanned. | Add integration test with real app configuration and verify wiring. |

## 17. Principles for Building Sustainable Tests

1. **Test both default and custom paths.** Both branches are public behavior of the auto-configuration.
2. **Assert by contract and implementation.** Check type, bean count, default absence, and behavioral output.
3. **Use ApplicationContextRunner for the condition matrix.** Keep each test small with explicit input configuration.
4. **Load auto-configuration explicitly.** Never let tests silently skip the class under verification.
5. **Use user configuration for custom beans.** This tests back-off using the production mechanism.
6. **Separate mocks from custom implementations.** Mocks isolate consumers; custom beans test extension points.
7. **Do not rely on @Primary to prove back-off.** Primary only determines which candidate gets injected.
8. **Read the condition report on failures.** Inspect type/name, property, and classpath conditions.
9. **Test child contexts at the right scope.** For LoadBalancer, clearly identify the service ID and child context.
10. **Keep test dependencies minimal.** Add providers or test servers only when the test actually needs that behavior.
11. **Avoid asserting unstable details.** Do not rely on bean ordering or generated names unless part of the contract.
12. **Check versions.** Bean override annotations and test APIs can differ across Spring Boot/Spring Framework release trains.

## 18. Completion Checklist

- [ ] Explain why both default and custom beans must be tested.
- [ ] Build an auto-configuration using `@ConditionalOnMissingBean`.
- [ ] Initialize `ApplicationContextRunner` and load auto-configuration.
- [ ] Verify the default is created when no custom bean exists.
- [ ] Verify a contract-matching custom bean makes the default back off.
- [ ] Assert bean count by contract and concrete implementation.
- [ ] Test that an unrelated bean does not make the default back off.
- [ ] Test enabled/disabled properties.
- [ ] Test optional dependencies using `FilteredClassLoader`.
- [ ] Read ConditionEvaluationReport when tests fail.
- [ ] Use `@TestConfiguration` and `@Import` in integration tests when needed.
- [ ] Distinguish `@MockitoBean` from production custom beans.
- [ ] Understand that `@Primary` does not eliminate the default bean.
- [ ] Test LoadBalancer in the per-service-ID child context.
- [ ] Maintain a test matrix covering default, custom, property, classpath, and context scope.
- [ ] Verify real behavior rather than only context startup.

**Official documentation to cross-check against your project version:**

- [Spring Boot – Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): `@ConditionalOnMissingBean`, bean definition ordering, and Testing your Auto-configuration with `ApplicationContextRunner`.
- [Spring Framework – Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html): `@TestBean`, `@MockitoBean`, `@MockitoSpyBean`, and replace/wrap strategies.
- [Spring Framework – @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring/reference/testing/annotations/integration-spring/annotation-mockitobean.html): selecting beans by type/name, qualifiers, and AOP proxy notes.
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): per-service-ID child contexts, custom LoadBalancer, and ServiceInstanceListSupplier.
- [Spring – Client-Side Load-Balancing with Spring Cloud LoadBalancer](https://spring.io/guides/gs/spring-cloud-loadbalancer/): example providing a custom ServiceInstanceListSupplier to test instance selection.

Test APIs and bean overrides vary across Spring Boot/Spring Framework versions. Check your project's BOM, run tests against the exact dependency set, and verify both default and custom paths before upgrading or releasing a starter.
