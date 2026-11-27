# New Bean Does Not Appear After Changing ConditionalOnProperty

## 1. Identifying the Right Problem

A common situation in Spring Boot/Spring Cloud development is adding or changing a property, yet a bean annotated with `@ConditionalOnProperty` still does not appear in `ApplicationContext`. For example, the application sets `inventory.remote.enabled=true` to enable a remote service client, but injecting `InventoryClient` fails with `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException`.

Before editing the annotation, distinguish three situations:

1. **Bean definition is not registered:** the condition does not match, so Spring skips the configuration or `@Bean` method.
2. **Bean definition exists, but the instance is not yet created:** the bean may be lazy, belong to an inactive scope, or have nothing requesting it yet.
3. **Bean exists, but injection fails:** a dependency may be missing, the type may be wrong, multiple beans of the same type may exist, or another condition excluded the bean from the context.

Specifically, `@ConditionalOnProperty` is evaluated when Spring processes configurations to create bean definitions. Changing a property in `Environment` after the application has started does not cause Spring to automatically re-evaluate that condition. `@RefreshScope` only refreshes targets of beans in that scope; it does not re-register bean definitions or re-run the entire auto-configuration process.

After this lesson, readers can:

- Inspect the exact property read by the condition.
- Understand `prefix`, `name`, `havingValue`, and `matchIfMissing`.
- Read `ConditionEvaluationReport` to find why a condition did not match.
- Distinguish a skipped bean definition from an uninitialized bean or an injection failure.
- Write tests for individual property values using `ApplicationContextRunner`.
- Design feature flags that change at runtime without expecting `@ConditionalOnProperty` to re-register beans automatically.

## 2. What Does @ConditionalOnProperty Check?

`@ConditionalOnProperty` reads values from the Spring `Environment`. It can be placed on a `@Configuration` class or on a `@Bean` method.

Example:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
class RemoteInventoryConfiguration {

    @Bean
    InventoryClient inventoryClient() {
        return new InventoryClient();
    }
}
```

The condition above checks the full property `inventory.remote.enabled`. Only when the value equals `true` does Spring include this configuration in bean registration.

### 2.1. prefix and name

- `prefix` is the leading part of the property key. A trailing dot is added automatically if needed.
- `name` is one or more remaining segments of the property name.
- Use kebab-case for property names, e.g., `client-enabled`.
- If multiple elements are declared in `name`, all properties must satisfy the condition for the condition to match.

Example:

```java
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = {"enabled", "client-enabled"},
        havingValue = "true"
)
```

This condition requires both `inventory.remote.enabled=true` and `inventory.remote.client-enabled=true`.

### 2.2. Default havingValue Does Not Mean True Only

This is a frequent reason a bean unexpectedly appears or disappears. If `havingValue` is omitted, Spring only requires that the property exists and is not the string `false`; it does not require the value to be `true`.

| Value in Environment | `havingValue` omitted | `havingValue="true"` | `havingValue="false"` |
| --- | --- | --- | --- |
| `true` | Match | Match | No match |
| `false` | No match | No match | Match |
| `yes` or `on` | Match | No match | No match |
| `custom` | Match | No match | No match |
| Property absent | No match by default | No match by default | No match by default |

If the property is a boolean feature flag, explicitly declare `havingValue = "true"` to prevent any arbitrary non-`false` value from accidentally enabling the bean.

### 2.3. matchIfMissing

`matchIfMissing` determines whether the condition matches when the property is completely absent from `Environment`. The default is `false`.

```java
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
```

With this setup, the bean is registered when the property is `true` or undeclared. If the property is present with the value `false`, the condition does not match.

Choose the default according to product semantics:

- `matchIfMissing = false`: feature is only enabled when explicitly configured.
- `matchIfMissing = true`: feature is enabled by default unless overridden by configuration.

Do not change `matchIfMissing` merely to make `NoSuchBeanDefinitionException` disappear; doing so may activate an integration unwanted in the current environment.

### 2.4. Do Not Use @ConditionalOnProperty to Check Collections

`@ConditionalOnProperty` is unreliable for checking collection/indexed properties. For example, `inventory.targets[0]` may exist yet a condition checking `inventory.targets` may not match as expected.

If you need to decide based on a list, use a custom `Condition` that reads and checks the property structure, or use a dedicated boolean property such as `inventory.targets.enabled`.

Starting with Spring Boot 3.5, `@ConditionalOnBooleanProperty` is a clearer option for boolean properties: by default it requires `true` and still supports `matchIfMissing`. For older baselines, use `@ConditionalOnProperty(havingValue = "true")`.

### 2.5. Placing the Condition on the Class vs. on a @Bean Method

- Placed on a `@Configuration` class: if the condition does not match, that configuration is not processed and `@Bean` methods inside do not register beans.
- Placed on a `@Bean` method: only the bean provided by that method is skipped; other beans in the same configuration class can still be registered.

If a configuration class contains multiple independent integrations, placing the condition on individual `@Bean` methods keeps unrelated beans active. If the entire configuration only makes sense when the feature is enabled, a class-level condition is clearer to express.

## 3. When Is the Condition Evaluated?

Spring processes configurations, evaluates conditions, and registers bean definitions when creating the `ApplicationContext`. With this configuration:

```java
@Configuration(proxyBeanMethods = false)
class InventoryConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "inventory.remote",
            name = "enabled",
            havingValue = "true"
    )
    InventoryClient inventoryClient() {
        return new InventoryClient();
    }
}
```

If `inventory.remote.enabled=false` at context startup, the `inventoryClient` bean definition is not registered. When the property changes to `true` later, the bean definition still does not appear automatically.

### 3.1. Context Refresh Does Not Re-Run Conditions

In Spring Cloud, `ContextRefresher.refresh()` updates Environment from property sources and triggers supported refresh/rebind mechanisms. `@RefreshScope` uses proxies and a target cache; on refresh, the target cache is cleared so a new target is created on the next invocation.

That flow is not equivalent to destroying and recreating the entire `ApplicationContext`. Configuration classes have already been processed, and `@ConditionalOnProperty` conditions are not automatically re-evaluated to add or remove bean definitions.

Hence, the following example does not turn a condition into a dynamic feature toggle:

```java
@Configuration
@RefreshScope
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = "enabled",
        havingValue = "true"
)
class RemoteInventoryConfiguration {

    @Bean
    RemoteInventoryClient remoteInventoryClient() {
        return new RemoteInventoryClient();
    }
}
```

Placing `@RefreshScope` on a `@Configuration` class does not mean every bean declared inside becomes refresh-scoped, nor does it cause Spring to re-register `@Bean` methods when a property changes.

### 3.2. When Is a Restart Needed?

If a feature is selected via `@ConditionalOnProperty` and the set of beans in the context must change, the simple, predictable choice is restarting the process/context with the new configuration. This is typically suitable for:

- Selecting an implementation per deployment environment.
- Enabling/disabling an adapter to an external system.
- Choosing a database driver or messaging provider.
- Configuring integrations requiring dedicated dependencies or lifecycles.

If state must switch immediately while the application is running, use a stable bean acting as a router/policy and have that bean read an updatable feature flag. Do not use conditions to alter bean topology dynamically.

## 4. Ordered Diagnostic Procedure

### Step 1: Confirm the Bean Is Truly Absent

Check beans by name and type in `ApplicationContext`:

```java
String[] names = applicationContext.getBeanNamesForType(InventoryClient.class);
log.info("InventoryClient bean names: {}", Arrays.toString(names));
```

If the array is empty, no bean definition was found for that type. If a bean name exists yet `getBean()` fails, the condition may have matched while instance creation or dependency injection is failing.

You can distinguish further:

| Symptom | What to Check |
| --- | --- |
| `NoSuchBeanDefinitionException` | Bean definition not registered or lookup uses wrong name/type |
| `NoUniqueBeanDefinitionException` | Multiple beans of same type exist; needs qualifier or primary |
| `UnsatisfiedDependencyException` | Bean to inject is absent or an inner dependency failed to build |
| Bean name exists in context yet no instance created | Check `@Lazy`, scope, and usage sites |
| ApplicationContext fails to start | Read root cause and condition report; error may happen before context is ready |

`getBeansOfType()` can initialize lazy singletons depending on the case. When you only want to confirm bean names, prefer `getBeanNamesForType()` and inspect bean definitions instead of accidentally triggering all beans.

### Step 2: Read the Actual Value in Environment

Do not look solely at `application.yml`. The value may be overridden by:

- Active profiles.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Config Data imports or remote configuration.
- Test property sources.
- `@TestPropertySource` or `@DynamicPropertySource`.

You can log the resolved value while diagnosing:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class InventoryFeatureDiagnostics implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(InventoryFeatureDiagnostics.class);
    private final Environment environment;

    InventoryFeatureDiagnostics(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("inventory.remote.enabled={}",
                environment.getProperty("inventory.remote.enabled"));
    }
}
```

Log only non-sensitive feature flags. Never dump the entire `Environment` or print secrets, passwords, tokens, or connection strings to logs.

If Actuator is available, the `env` endpoint helps inspect property sources and value origins. This endpoint can expose sensitive information; expose it only in administrative environments, restrict roles, and enable proper sanitization.

### Step 3: Match the Key Against the Annotation

Cross-check each segment:

```java
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = "enabled",
        havingValue = "true"
)
```

With YAML:

```yaml
inventory:
  remote:
    enabled: true
```

The full property is `inventory.remote.enabled`. Common mistakes:

- Wrong prefix, e.g., `inventory.remotes` instead of `inventory.remote`.
- Wrong property name, e.g., `enable` instead of `enabled`.
- Placing the property at the wrong YAML nesting level.
- Setting `inventory.remote.enabled` while the annotation checks `inventory.client.enabled`.
- Declaring multiple `name` entries while only one property is set.

### Step 4: Check havingValue and matchIfMissing

Record three facts: does the property exist, what is its actual value, and what value does the annotation expect. Specifically check missing-property cases and default values.

If boolean true is desired, prefer:

```java
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
```

Avoid relying on the default `havingValue` if the property can take values other than `true`/`false`.

### Step 5: Check Profiles and Configuration Load Order

Confirm active profiles with `Environment.getActiveProfiles()` and inspect corresponding files such as `application-dev.yml`, `application-test.yml`, or profiles activated by deployment.

With Config Data or Config Server, confirm the configuration source was loaded before bean definitions were created. A property that appears only after a refresh event cannot travel back in time to make an earlier condition match.

### Step 6: Check Configuration Location and Component Scan

A condition is only evaluated if Spring actually discovers the configuration or `@Bean` method:

- Is the `@Configuration` class within component scan?
- Is it imported via `@Import` or registered via auto-configuration?
- Does the main application class's package cover the configuration package?
- Is there another profile or condition on a parent/enclosing class?
- Is the `@Bean` method placed in a configuration that is not imported?

If the configuration is never discovered, tweaking `havingValue` will not fix the root cause.

### Step 7: Check Other Conditions and Bean Conflicts

A bean may be governed by multiple conditions: `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@Profile`, `@ConditionalOnWebApplication`, or a custom `Condition`. If any one condition does not match, the bean is still not registered even when `@ConditionalOnProperty` matches.

Additionally, `@ConditionalOnMissingBean` can cause auto-configuration to back off when a user-supplied bean already exists. Check beans of the same type, bean names, `@Primary`, and `@Qualifier` before concluding the property condition is wrong.

## 5. Using ConditionEvaluationReport to Find Unmatched Conditions

Spring Boot generates a `ConditionEvaluationReport` to explain auto-configuration decisions. This is the right tool when a bean comes from a starter or auto-configuration.

### 5.1. Enable Debug at Startup

Run the application with `--debug`:

```bash
java -jar inventory-service.jar --debug
```

Or:

```bash
java -Ddebug=true -jar inventory-service.jar
```

Locate the condition report section and the relevant configuration name. Negative match entries usually indicate which property is missing or lacks the expected value.

### 5.2. Use the Actuator Conditions Endpoint

If the application includes Actuator, the `conditions` endpoint displays the report as JSON. Default path:

```text
/actuator/conditions
```

Actuator endpoints are not exposed over HTTP just because the dependency is present. You can explicitly configure exposure in a diagnostic environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - conditions
```

This endpoint is useful for checking why an auto-configuration was applied or skipped. Protect it with authentication/authorization and expose it only on an appropriate management network; the condition report can reveal class names, packages, and internal structure.

### 5.3. Read the Report Properly

Once you find the relevant configuration, inspect:

1. Name of the auto-configuration or configuration class.
2. Which conditions matched and which did not.
3. The property key being evaluated.
4. Expected value versus found value.
5. Whether other conditions exist on the same configuration or bean method.

If the bean is in user configuration not belonging to the auto-configuration report, inspect `ApplicationContext`, package scan, `@Import`, and properties directly. Not every application-written configuration class appears in the report the same way auto-configurations do.

## 6. Complete Example: Conditional Bean Configuration

Suppose the application creates an Inventory API client only when a feature flag is enabled.

### 6.1. Property

```yaml
inventory:
  remote:
    enabled: true
    base-url: https://inventory.internal
```

### 6.2. Configuration

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InventoryProperties.class)
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class RemoteInventoryConfiguration {

    @Bean
    InventoryClient inventoryClient(InventoryProperties properties) {
        return new InventoryClient(properties.getBaseUrl());
    }
}
```

If the property is missing or `false`, `InventoryClient` is not registered. When the feature flag has value `true` from the start, the bean appears in the context.

### 6.3. Do Not Confuse Binding with Conditions

`@ConfigurationProperties` binds properties into a Java object. `@ConditionalOnProperty` checks `Environment` to decide whether to register configuration. Both mechanisms relate to the same property source but perform different jobs.

Example properties class:

```java
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "inventory.remote")
public class InventoryProperties {

    private boolean enabled;
    private URI baseUrl;

    // getters and setters
}
```

If `InventoryProperties` holds `enabled=true` after binding, that does not mean a bean excluded by a condition at startup will appear on its own. Binding an object does not re-run bean definition registration.

## 7. Testing Condition Branches with ApplicationContextRunner

`ApplicationContextRunner` creates a small context per test. This is a great way to confirm which property causes the bean to register, while inspecting `ConditionEvaluationReport` without running the whole application.

Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class RemoteInventoryConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(RemoteInventoryConfiguration.class);

    @Test
    void registersClientWhenPropertyIsTrue() {
        contextRunner
                .withPropertyValues("inventory.remote.enabled=true")
                .run(context -> assertThat(context)
                        .hasSingleBean(InventoryClient.class));
    }

    @Test
    void skipsClientWhenPropertyIsFalse() {
        contextRunner
                .withPropertyValues("inventory.remote.enabled=false")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(InventoryClient.class));
    }

    @Test
    void skipsClientWhenPropertyIsMissing() {
        contextRunner
                .run(context -> assertThat(context)
                        .doesNotHaveBean(InventoryClient.class));
    }
}
```

In a real project, provide the appropriate `InventoryProperties` bean or enable `@EnableConfigurationProperties(InventoryProperties.class)` in the test configuration. If running as an auto-configuration test, use `withConfiguration(AutoConfigurations.of(...))` to register auto-configuration following Spring Boot's mechanism.

### 7.1. Testing matchIfMissing

If the annotation sets `matchIfMissing = true`, add a test confirming the bean appears when the property is absent:

```java
@Test
void registersClientWhenPropertyIsMissingAndMatchIfMissingIsTrue() {
    new ApplicationContextRunner()
            .withUserConfiguration(DefaultEnabledInventoryConfiguration.class)
            .run(context -> assertThat(context)
                    .hasSingleBean(InventoryClient.class));
}
```

The test must use a configuration with `matchIfMissing = true`. Do not reuse the same context for multiple property values and expect the condition to re-run; each `run` creates a fresh context.

### 7.2. Testing Non-True Values

If the annotation requires `havingValue = "true"`, add tests with `yes`, `on`, or an arbitrary string to prove those values do not enable the bean.

```java
@Test
void doesNotTreatArbitraryValueAsTrue() {
    contextRunner
            .withPropertyValues("inventory.remote.enabled=yes")
            .run(context -> assertThat(context)
                    .doesNotHaveBean(InventoryClient.class));
}
```

## 8. When a Feature Flag Must Change While the Application Is Running

If the business requirement is toggling behavior while the process is running, keep the bean definitions stable and switch the decision inside a bean. `@ConditionalOnProperty` is meant for deciding whether to create an integration at startup; it is not a runtime feature switch.

### 8.1. Using a Refreshable Policy Bean

Example policy reading the property whenever the target is created:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class InventoryRoutingPolicy {

    @Value("${inventory.remote.enabled:false}")
    private boolean remoteEnabled;

    public boolean useRemoteClient() {
        return remoteEnabled;
    }
}
```

The service injects the policy proxy and chooses the implementation:

```java
@Service
public class InventoryService {

    private final InventoryRoutingPolicy routingPolicy;
    private final RemoteInventoryClient remoteClient;
    private final LocalInventoryClient localClient;

    public InventoryService(
            InventoryRoutingPolicy routingPolicy,
            RemoteInventoryClient remoteClient,
            LocalInventoryClient localClient) {
        this.routingPolicy = routingPolicy;
        this.remoteClient = remoteClient;
        this.localClient = localClient;
    }

    public Inventory find(String id) {
        if (routingPolicy.useRemoteClient()) {
            return remoteClient.find(id);
        }
        return localClient.find(id);
    }
}
```

Both clients are created stably in the context. When the property changes and refresh succeeds, the target of `InventoryRoutingPolicy` is recreated; the next call reads the new value. No bean definitions are added or removed.

This pattern is only suitable when both implementations can safely coexist simultaneously. If an integration cannot initialize while the feature is disabled, keep the integration behind a stable abstraction, or use restart/redeploy to change bean topology.

### 8.2. Prerequisites to Refresh the Policy

For Spring Cloud Context:

1. `spring.cloud.refresh.enabled` must be enabled in a runtime mode supporting refresh.
2. The property source must receive the new value.
3. The application must invoke `ContextRefresher.refresh()` or an exposed and secured refresh endpoint.
4. `InventoryRoutingPolicy` must be Spring-managed and injected via proxy.

Refresh Scope does not support Spring AOT transformations and native images. In those modes, use restart/redeploy or a dedicated dynamic configuration mechanism suited to the runtime.

### 8.3. When the Actual Set of Beans Must Change

If a feature requires adding or removing beans, changing datasources, message listener containers, or connections with dedicated lifecycles, consider:

- Restarting/redeploying the instance with the new configuration.
- Creating a stable abstraction/router and managing resource lifecycles inside it.
- Using a plugin/module architecture with explicitly designed registration and deregistration APIs.

Do not use `@ConditionalOnProperty` as a dynamic module toggle. Registering or removing bean definitions at runtime requires managing dependencies, destruction callbacks, threads, connections, and concurrency; only do so with a specific lifecycle architecture.

## 9. Other Causes Preventing a Bean from Being Injected

Even after a condition matches, errors can still arise due to:

| Cause | Symptom | How to Check |
| --- | --- | --- |
| Configuration outside component scan | Neither configuration nor bean is seen | Check package of `@SpringBootApplication`, `@Import` |
| Profile not active | `@Profile` on configuration does not match | Check `spring.profiles.active` |
| Missing dependency | Bean method cannot run or auto-configuration skipped | Check runtime classpath and `@ConditionalOnClass` |
| Bean excluded by `@ConditionalOnMissingBean` | A bean of the same type was registered earlier | Find beans of same type/name and auto-configuration order |
| Multiple beans for same interface | `NoUniqueBeanDefinitionException` | Use `@Qualifier` or `@Primary` |
| Lazy bean | Definition exists yet instance not created | Check `@Lazy` and call sites |
| Incompatible scope | Bean exists only in request/session or custom scope | Check scope and proxy |
| Dependency in bean method fails | Context fails while creating bean | Read root exception and constructor dependencies |
| `@Bean` method not called as expected | Configuration proxy mode or direct method call mistake | Inject bean from context; avoid calling factory methods directly |

## 10. Quick Diagnostic Table

| Symptom | First Cause to Check | Action |
| --- | --- | --- |
| Property is `true` in YAML yet condition fails | Value in Environment overridden or wrong key | Check property source and full key |
| Property absent yet bean is expected to appear | `matchIfMissing` defaults to false | Decide whether to set `matchIfMissing=true` |
| Property has value `yes` and bean gets created | `havingValue` omitted | Use `havingValue="true"` or `@ConditionalOnBooleanProperty` |
| Property changed via Config Server yet bean does not appear | Condition only evaluated at context creation | Restart or switch to a runtime policy bean |
| `@RefreshScope` refreshed yet conditional bean still missing | Refresh Scope only clears target cache | Do not expect refresh to re-register bean definitions |
| Condition matches yet bean still cannot be injected | Component scan, another condition, or dependency error | Read condition report and root exception |
| Bean name exists yet no instance yet | Lazy initialization or scope | Check `@Lazy`, scope, and call sites |
| Test passes for true, yet false still retains bean | Same context reused across tests | Use a fresh context for each case |
| Condition checking a list fails to match | Collection/indexed property | Use a custom `Condition` or separate boolean flag |

## 11. Troubleshooting Checklist

1. Confirm whether the missing bean is an unregistered bean definition or merely an uninitialized instance.
2. Read the root exception instead of only looking at the final injection failure.
3. Print the exact property key from `Environment`, not just YAML files.
4. Check active profiles and higher-precedence property sources.
5. Cross-check `prefix`, `name`, `havingValue`, and `matchIfMissing`.
6. If boolean true is desired, explicitly declare `havingValue="true"`.
7. Check every property in `name` when multiple names are listed.
8. Do not use `@ConditionalOnProperty` to match collection/indexed properties.
9. Enable `--debug` or inspect `/actuator/conditions` to read `ConditionEvaluationReport`.
10. Check component scan, `@Import`, `@Profile`, classpath, and other conditions.
11. Write `ApplicationContextRunner` tests for true, false, missing, and unusual values.
12. If runtime behavior switching is required, use a stable policy/strategy bean instead of a condition.
13. If the bean set itself must change, plan a restart/redeploy or explicit module lifecycle.

## 12. References

- [Spring Boot 4.1 — ConditionalOnProperty API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): semantics of `prefix`, `name`, `havingValue`, `matchIfMissing`, and collection limitations.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): property conditions, condition annotations, and testing with `ApplicationContextRunner`.
- [Spring Boot — Troubleshoot Auto-configuration](https://docs.spring.io/spring-boot/how-to/application.html): `ConditionEvaluationReport`, `--debug`, and Actuator `conditions` endpoint.
- [Spring Cloud Context — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): Refresh Scope, target cache, and Context Refresh limits.

`@ConditionalOnProperty` decides bean definitions when the context is created. If a bean fails to appear, check the actual property and condition report before changing annotations. If the requirement is to switch behavior at runtime, keep beans stable and update a policy; if the requirement is to change bean structure, create a new context or redeploy with the new configuration.
