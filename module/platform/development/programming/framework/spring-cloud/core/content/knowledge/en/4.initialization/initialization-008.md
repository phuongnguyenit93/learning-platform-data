# Inspecting Beans, Configuration Sources, and Auto-Configuration Conditions

When a Spring Boot or Spring Cloud application starts up, the process running successfully does not prove that **the needed beans were created**, **the right configuration values were loaded**, or **the intended auto-configuration was applied**. An application can open an HTTP port while still missing `DiscoveryClient`, loading the wrong profile, using default timeout values, or failing to create a bean because a classpath condition was not met.

A systematic diagnostic approach follows three questions:

1. **Which beans exist?** Was a bean registered via component scanning, manual configuration, or a specific auto-configuration?
2. **Where did a configuration value come from?** Which property wins when multiple sources declare the same key, which profiles are active, and is Config Server involved?
3. **Why was an auto-configuration enabled or skipped?** Which conditions matched, which did not match, and which dependency, bean, or property is missing?

This lesson belongs to the **Initialization** chapter of the **SPRING_CLOUD_CORE** module, focusing on Spring Cloud's core abstractions inside a Spring Boot application: `ApplicationContext`, `Environment`, externalized configuration, discovery, service registry, refresh scope, and how to test and operate initialization.

## 1. Learning Objectives

After this lesson, learners can:

- Distinguish between `BeanDefinition`, bean instance, and auto-configuration.
- Inspect beans by name, type, registration source, and state in `ApplicationContext`.
- Read `PropertySource` entries in `Environment`, determine the effective value, and identify higher-precedence configuration sources.
- Understand when Config Data, profiles, and Spring Cloud Config properties are loaded.
- Read the condition evaluation report to explain why an auto-configuration or bean was enabled or skipped.
- Write isolated initialization tests with `ApplicationContextRunner` alongside appropriate integration tests.
- Diagnose common issues such as missing beans, wrong profiles, overridden properties, missing discovery implementations, or unmet auto-configuration conditions.

## 2. The Initialization Picture: From Configuration to Beans

Spring Boot organizes initialization around `SpringApplication` and the Spring `ApplicationContext`. At a high level, the flow typically includes:

~~~mermaid
flowchart TD
    A[SpringApplication.run] --> B[Prepare Environment]
    B --> C[Load Config Data and profiles]
    C --> D[Create ApplicationContext]
    D --> E[Register BeanDefinitions]
    E --> F[Refresh ApplicationContext]
    F --> G[Evaluate conditions and instantiate singletons]
    G --> H[Run ApplicationRunner / CommandLineRunner]
    H --> I[ApplicationReady]
~~~

The diagram illustrates the main phases; internal details can vary by Boot version and application type.

### 2.1. Environment Is Prepared Before Regular Beans Are Created

`Environment` is Spring's abstraction for accessing profiles and property sources. In Spring Boot, convention-based configuration files such as `application.properties` or `application.yaml` are loaded during environment preparation via the Config Data mechanism. Properties that affect configuration discovery—such as `spring.config.name`, `spring.config.location`, `spring.config.additional-location`, and active profiles—must be supplied early enough for configuration loading to use them.

This explains why adding `@PropertySource` on a `@Configuration` class is not suitable for every startup property: that annotation is processed during context creation, which may be too late for settings needed to determine Config Data or bootstrap behavior.

### 2.2. BeanDefinition and Bean Instance Are Two Different States

The Spring container normally registers metadata as a `BeanDefinition` before instantiating the actual object.

- **BeanDefinition** describes a bean: name, expected type, factory method, scope, dependencies, and related metadata.
- **Bean instance** is the object created and managed by the container.
- **Singleton scope** normally creates one shared instance per `ApplicationContext`; singleton does not mean unique across the entire JVM if multiple contexts exist.
- **Lazy initialization** can defer bean creation until first access.
- **Prototype** creates a new instance on demand; its full lifecycle is not managed like a singleton.

Therefore, seeing a bean definition does not necessarily prove the object has been instantiated. Conversely, inspecting a bean via `getBean()` can trigger instantiation and surface dependency errors; when diagnosing metadata only, start by listing names/definitions.

### 2.3. Where Do Beans Come From?

A bean in an application may be registered by:

1. **Component scanning:** classes annotated with `@Component`, `@Service`, `@Repository`, `@Controller`, or corresponding stereotypes.
2. **Java configuration:** `@Bean` methods in a `@Configuration` class or compatible configuration.
3. **Auto-configuration:** library-provided configurations evaluated conditionally by Spring Boot.
4. **Direct import:** `@Import`, registrars, or specialized bean registration mechanisms.
5. **Framework integration mechanisms:** e.g., Spring Cloud creating beans for discovery, Config Client, or refresh when dependencies and conditions match.

A bean with the same name can originate from different sources across environments. Thus, when investigating, identify **the registration source and creation conditions**, not just the bean name.

## 3. Inspecting Beans in ApplicationContext

`ApplicationContext` acts as both the bean-managing container and a lookup API. When debugging, inspect from narrow to broad scope to avoid inadvertently instantiating heavy beans.

### 3.1. Looking Up by Name and Type

~~~java
import java.util.Arrays;

import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
class BeanInventory {
    private final ApplicationContext context;

    BeanInventory(ApplicationContext context) {
        this.context = context;
    }

    void inspect() {
        System.out.println("inventoryGateway exists: "
                + context.containsBean("inventoryGateway"));

        String[] names = context.getBeanNamesForType(InventoryGateway.class);
        System.out.println("InventoryGateway beans: "
                + Arrays.toString(names));
    }
}
~~~

`containsBean(name)` checks for a bean name in the context and its parent context according to container rules. `getBeanNamesForType(type)` returns beans assignable to the requested type. If only metadata inspection is needed, `ListableBeanFactory` and `ConfigurableListableBeanFactory` APIs offer options to control eager initialization of `FactoryBean`; pick the overload suited to your goal and Spring version.

Notes:

- `getBean(InventoryGateway.class)` requests an object instance, which may trigger lazy bean initialization.
- If multiple beans share the same type, lookup by type can throw `NoUniqueBeanDefinitionException`; check bean names, `@Primary`, `@Qualifier`, and context hierarchy.
- `getBeanNamesForType` does not prove a bean's dependencies were successfully injected into a specific consumer.
- A bean may live in a parent context; be clear about which context you are inspecting.

### 3.2. Listing Bean Definitions

When you need to see which names the container has registered:

~~~java
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.ConfigurableApplicationContext;

void listDefinitions(ConfigurableApplicationContext context) {
    ConfigurableListableBeanFactory factory = context.getBeanFactory();

    for (String name : factory.getBeanDefinitionNames()) {
        var definition = factory.getBeanDefinition(name);
        System.out.printf(
                "%s | class=%s | scope=%s | resource=%s%n",
                name,
                definition.getBeanClassName(),
                definition.getScope(),
                definition.getResourceDescription()
        );
    }
}
~~~

`getBeanClassName()` can be `null` if the bean is created via a factory method or the class cannot yet be inferred from the definition. For `@Bean`-declared beans, also inspect the factory bean name and factory method name. `resourceDescription` helps locate metadata, though it does not always contain an explicit source path.

Do not dump the full bean list into production logs on every startup: the output can be large and expose class names or internal details. Use temporary logging in test environments or controlled management tools.

### 3.3. Using Spring Boot Actuator for Observation

If the application includes Actuator, useful endpoints include:

| Endpoint ID | Purpose |
| --- | --- |
| `beans` | View bean definitions per context |
| `conditions` | View which auto-configuration conditions matched or did not match |
| `env` | Observe properties and property sources in `Environment` |
| `configprops` | Observe beans bound via `@ConfigurationProperties` |
| `health` | Check application health and configured health contributors |

Endpoints operate only when dependencies, endpoint conditions, web exposure, and access permissions allow. For example, in a local environment you might expose:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,beans,conditions,env,configprops
~~~

This is an example for development environments. **Do not expose management endpoints en masse to the Internet or untrusted networks.** `env` and `configprops` sanitize sensitive values, but masking does not replace authentication, authorization, and network restrictions. Open only truly necessary endpoints; consider a separate management port protected by Spring Security or equivalent controls.

## 4. Inspecting Configuration Sources via Environment

Spring `Environment` maintains a list of `PropertySource` entries. When the same key appears in multiple sources, precedence order determines which value is read.

### 4.1. PropertySource and Effective Value

For instance, `server.port` might be set in YAML, an environment variable, and a command-line argument. When multiple values exist, Spring Boot applies property source precedence rules. Typically, command-line arguments take precedence over configuration files; external files can override files packaged inside the JAR; profile-specific files can override common files.

Do not memorize a simplified list and apply it blindly across all versions: Spring Boot has many property sources and exact ordering is documented per version. When in doubt, inspect the live `Environment` and the Externalized Configuration docs for your exact version.

You can inspect property sources programmatically:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

void inspectPropertySources(ConfigurableEnvironment environment) {
    for (PropertySource<?> source : environment.getPropertySources()) {
        System.out.println("PropertySource: " + source.getName());
    }

    System.out.println("server.port = "
            + environment.getProperty("server.port"));
    System.out.println("spring.application.name = "
            + environment.getProperty("spring.application.name"));
}
~~~

The list is normally iterated in the precedence order maintained by `MutablePropertySources`. This snippet prints source names and final resolved values; it does not directly reveal which source supplied the winning value. To inspect exact origins, use Actuator's `env` endpoint in a secured environment or Spring Boot's origin tracking mechanisms.

Never dump all keys and values to logs: doing so can leak passwords, tokens, connection strings, or identifying metadata.

### 4.2. Common Configuration Sources

| Source | Example | Role |
| --- | --- | --- |
| Packaged config file | `classpath:/application.yaml` | Default values bundled with the application |
| External config file | `./application.yaml`, `./config/application.yaml` | Deployment environment-specific configuration |
| Profile-specific file | `application-prod.yaml` | Overrides or adds settings when the `prod` profile is active |
| Environment variables | `SPRING_DATASOURCE_URL` | Passes runtime environment settings into the application |
| JVM system properties | `-Dserver.port=9090` | JVM launch-time configuration |
| Command-line arguments | `--server.port=9091` | Convenient per-run overrides |
| Spring Cloud Config | Properties from Config Server | Centralized configuration by application/profile/label |
| Test property sources | `@TestPropertySource`, test `properties` | Test-scoped configuration overrides |

Exact ordering depends on source type and declaration. For example, `@TestPropertySource` or `@DynamicPropertySource` in tests follows specific precedence rules; do not extrapolate this table to every context.

### 4.3. Checking Active Profiles

Profiles determine which bean groups and configuration files are activated. Profiles can be declared via:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Or passed at runtime:

~~~bash
java -jar orders-service.jar --spring.profiles.active=prod
~~~

Inspecting actual profiles:

~~~java
import java.util.Arrays;
import org.springframework.core.env.Environment;

void inspectProfiles(Environment environment) {
    System.out.println("active="
            + Arrays.toString(environment.getActiveProfiles()));
    System.out.println("default="
            + Arrays.toString(environment.getDefaultProfiles()));
}
~~~

When no active profile is set, Spring may fall back to default profiles (commonly `default`). Distinguish **active profiles** from **default profiles**. Additionally, `spring.profiles.include` and profile groups can activate extra profiles; inspect the result after Environment preparation.

A common error is placing `spring.profiles.active` inside a configuration document activated only by that very profile. Profile declarations must obey Spring Boot Config Data rules; never put profile activation inside a document gated by the profile being activated.

### 4.4. External Config Files and Config Data

Spring Boot searches default locations for config files and lets you add or replace locations via:

- `spring.config.name`: base filename of the configuration file.
- `spring.config.location`: specifies locations to search and can replace default locations.
- `spring.config.additional-location`: adds search locations alongside defaults.
- `spring.config.import`: imports additional configuration sources, such as Config Server or extra files.

Properties controlling file discovery must be available early enough, typically via environment variables, system properties, or command-line arguments. When an external file fails to load, check the working directory, absolute/relative paths, filenames, profiles, and whether `location` or `additional-location` was used.

## 5. Spring Cloud Config and Configuration Loading Timing

In Spring Cloud, configuration can come from a Config Server. Under modern Config Data integration, the application declares an import:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:configserver:http://localhost:8888
~~~

A compatible **Config Client starter** for the release train in use is required. `spring.application.name`, profiles, and labels are used to request the corresponding configuration set from the server.

### 5.1. `optional:` vs. Mandatory Config Server Connection

- `optional:configserver:...` allows the application to proceed when the import source is unavailable under Config Data policies.
- Omitting `optional:` marks the source as mandatory; connection failures can cause application startup to fail.
- Fail-fast/retry configuration can differ across versions and bootstrap setups; consult the exact release train documentation.

Choosing optional vs. mandatory is an operational decision. If the application requires mandatory secrets or endpoints from Config Server, starting with fallback defaults can cause subtle failures or unsafe behavior.

### 5.2. Config Data and Bootstrap Context

Modern Spring Cloud releases use Config Data with `spring.config.import` for Config Client. Older projects may rely on the **bootstrap context** and corresponding bootstrap dependencies/configuration. Do not assume every Spring Cloud project creates a bootstrap context or that every `bootstrap.yml` property retains identical behavior in modern setups.

When upgrading, check:

1. Spring Cloud release train compatibility with Spring Boot.
2. Config Client starter and the active import mechanism.
3. Profile, application name, label, and Config Server endpoint.
4. Whether any legacy bootstrap dependency or setting is still enabled.
5. Whether the final resolved values in `Environment` match expectations.

### 5.3. Initial Config Loading Differs from Runtime Refresh

Reading Config Server at startup does not mean the application automatically picks up subsequent changes. Distinguish:

- **Load:** loading property sources during Environment preparation.
- **Refresh:** triggering updates/rebinding or recreating `@RefreshScope` beans via a configured mechanism.
- **Propagate:** notifying other instances, e.g., via messaging/bus if deployed.
- **Observe:** verifying each instance received the new values.

`@RefreshScope` belongs to Spring Cloud Context; it does not poll Config Server periodically, does not broadcast changes across a cluster, and does not guarantee every bean refreshes.

## 6. Auto-Configuration: Why Are Beans Created or Skipped?

Spring Boot auto-configuration is a set of candidate configurations packaged with libraries that apply only when conditions are satisfied. This is how starters integrate libraries without requiring users to declare every bean manually.

### 6.1. Common Condition Types

| Annotation / condition | Meaning | Diagnostic example |
| --- | --- | --- |
| `@ConditionalOnClass` | Applies only if required classes are on the classpath | Missing HTTP client or provider library |
| `@ConditionalOnMissingBean` | Creates a default bean only when no matching bean exists | User already declared a custom bean |
| `@ConditionalOnBean` | Applies only when another bean exists | Missing prerequisite configuration |
| `@ConditionalOnProperty` | Checks if a property has an expected value | Feature flag disabled or wrong property key |
| `@ConditionalOnResource` | Checks if a resource exists | Missing file or schema |
| `@ConditionalOnWebApplication` | Checks web application type | Web auto-configuration skipped in non-web app |
| `@ConditionalOnNotWebApplication` | Applies only when not a web application | Configuration dedicated to batch/CLI processes |

A single configuration may depend on multiple conditions. For instance, a discovery auto-configuration may require an implementation class on the classpath, an enabled property, and no custom replacement bean.

### 6.2. Custom Auto-Configuration Example

Suppose a library provides `InventoryClient` when the application has a compatible HTTP transport and `inventory.client.enabled=true`:

~~~java
@AutoConfiguration
@ConditionalOnClass(InventoryClient.class)
@ConditionalOnProperty(
        prefix = "inventory.client",
        name = "enabled",
        havingValue = "true"
)
public class InventoryClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    InventoryClient inventoryClient(InventoryTransport transport) {
        return new InventoryClient(transport);
    }
}
~~~

In this example:

- `@ConditionalOnClass` checks that the class is on the classpath.
- `@ConditionalOnProperty` checks the feature flag.
- `@ConditionalOnMissingBean` lets the application provide its own `InventoryClient`.
- A matching `InventoryTransport` bean must still exist; otherwise the bean method cannot succeed.

With Spring Boot 3, library auto-configurations are typically registered in:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The file lists fully qualified auto-configuration class names, one per line. Older Boot projects may use `spring.factories`; when upgrading, follow the registration rules of the target Boot version.

### 6.3. Auto-Configuration Ordering

When multiple configurations depend on each other, ordering can affect `@ConditionalOnBean` or `@ConditionalOnMissingBean` evaluations. Annotations like `@AutoConfigureBefore`, `@AutoConfigureAfter`, or the `before`/`after` attributes on `@AutoConfiguration` control relative ordering.

However, do not rely on ordering to mask a flawed dependency design. If a custom bean must exist beforehand, declare configurations and dependencies explicitly; use the condition report to verify actual order and conditions.

## 7. Reading the Condition Evaluation Report

The condition evaluation report is vital evidence when a feature fails to appear. It shows which auto-configurations matched, which conditions did not match, and the recorded reason.

### 7.1. Enabling Debug at Startup

You can launch the application with:

~~~bash
java -jar orders-service.jar --debug
~~~

Or enable debug logging for the auto-configuration package appropriate to your version. Spring Boot prints the **Condition Evaluation Report** grouped into positive and negative matches. Search for the auto-configuration class related to the feature under investigation, such as Config Client, LoadBalancer, or a discovery provider.

A "did not match" entry typically explains that a class was absent, a property was unset, or a prerequisite bean did not exist. Read the exact reason before adding dependencies or editing configuration.

### 7.2. Using Actuator `conditions`

If Actuator is present and the endpoint is properly exposed/secured, you can query:

~~~http
GET /actuator/conditions
~~~

This endpoint returns condition evaluation results per context. It is especially helpful when comparing local, staging, and production: the same auto-configuration may match locally yet fail in production due to classpath or property differences.

The `conditions` endpoint is for diagnostics; never expose it publicly. Use debug logs in test environments instead if you prefer not to open management endpoints.

### 7.3. Classifying Root Causes from Evidence

| Evidence in report | Likely cause | Resolution |
| --- | --- | --- |
| `@ConditionalOnClass` did not match | Missing JAR or version lacks that class | Check runtime dependency tree and BOM |
| `@ConditionalOnProperty` did not match | Wrong key, different value, profile inactive | Check `Environment`, property sources, and profiles |
| `@ConditionalOnMissingBean` did not match | Custom bean or bean from another config already exists | Find existing bean and verify if override is intentional |
| `@ConditionalOnBean` did not match | Missing prerequisite bean | Inspect the auto-configuration creating that bean and its conditions |
| Configuration excluded | Excluded via annotation or property | Check `exclude`, `excludeName`, `spring.autoconfigure.exclude` |
| Auto-configuration absent from report | Not imported, missing metadata, or wrong version | Check starter, imports file, and Boot version |

A non-matching condition is not always a bug. A default auto-configuration may intentionally back off in favor of an application-supplied bean. Evaluate against application intent rather than trying to make every condition match.

## 8. Diagnosing Real-World Scenarios

### 8.1. Missing `DiscoveryClient`

A Spring Cloud application needs to look up `inventory-service`, yet injecting `DiscoveryClient` fails or yields the wrong implementation.

Check in order:

1. **Class and bean:** Is the `DiscoveryClient` API on the runtime classpath? Does any bean of that type exist?
2. **Provider:** Was an appropriate discovery starter added (e.g., Eureka Client), or are you intentionally using `SimpleDiscoveryClient`?
3. **Auto-configuration:** Does the condition report show the provider's configuration matching or skipped?
4. **Properties:** Are the application name, registry URL, profile, and discovery properties accurate?
5. **Runtime:** Can the provider reach the registry and return instances?

`spring-cloud-commons` supplies the shared abstractions, not every registry implementation. Having a `DiscoveryClient` bean also does not prove an external registry connected successfully; it could be simple/static discovery or another implementation.

### 8.2. Timeout Value Does Not Match Configuration

Suppose `application-prod.yaml` sets a 400 ms timeout, yet runtime still uses 1,000 ms. Steps:

- Confirm `prod` is among the active profiles.
- Verify the file is in the right location with the right filename.
- Check whether environment variables, system properties, CLI arguments, or Config Server override it.
- Inspect property sources and effective values via `Environment`/Actuator.
- Check whether the client bean was instantiated before the new value appeared or cached the old value inside an already constructed object.

If a client bean captures the timeout in its constructor, changing a property in `Environment` will not automatically update the running instance. Explicit lifecycle/refresh design is required.

### 8.3. Bean Exists Locally but Not in Production

Compare verifiable differences:

- Runtime dependency tree and artifact versions.
- Active profiles, environment variables, and Config Data locations.
- Auto-configuration exclusions.
- Conditional properties and classpath.
- Component scan base packages, `@Import`, and enabled configurations.
- Differences between web application and non-web application types.
- Custom beans, `@Primary`, `@Qualifier`, and context hierarchy.

Do not patch the symptom by adding `@Component` or duplicating a bean declaration before understanding why the original configuration did not apply. Doing so can mask the root cause and cause conflicts when another environment starts.

### 8.4. Config Server Has the Setting, but the Application Does Not Receive It

Check `spring.config.import`, Config Client starter, Config Server URL, application name, profile, and label. Then inspect Config Data startup logs, property sources in `Environment`, and the optional/fail-fast policy.

If a setting appears on one instance but not another, compare startup timestamps, profiles, application versions, labels, and refresh/propagation mechanisms. Never assume that because the server holds data, every client has received that same data.

## 9. Testing Beans and Auto-Configuration

Initialization testing validates specific conditions without launching an entire external dependency stack.

### 9.1. ApplicationContextRunner

Spring Boot provides `ApplicationContextRunner` to run a lightweight context with specified configurations and properties. Illustrative example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class InventoryClientAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            InventoryClientAutoConfiguration.class
                    ))
                    .withBean(InventoryTransport.class,
                            () -> request -> "ok");

    @Test
    void createsClientWhenEnabled() {
        runner.withPropertyValues("inventory.client.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(InventoryClient.class);
                });
    }

    @Test
    void backsOffWhenDisabled() {
        runner.withPropertyValues("inventory.client.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(InventoryClient.class);
                });
    }
}
~~~

This is an example test for the hypothetical auto-configuration shown earlier. `InventoryTransport` and `InventoryClient`'s constructor are example application APIs, not built-in Spring classes.

Benefits of `ApplicationContextRunner`:

- Runs a minimal context with no web server required.
- Easily varies properties across test cases.
- Can register prerequisite beans or custom override beans.
- Verifies that auto-configuration creates beans, backs off, or fails when conditions are missing.

### 9.2. Testing Configuration Sources

For `@ConfigurationProperties` configurations, test both binding and expected values:

~~~java
@ConfigurationProperties(prefix = "inventory.client")
public record InventoryClientProperties(
        boolean enabled,
        Duration connectTimeout,
        Duration readTimeout
) {}
~~~

Tests can spin up contexts with different properties and assert bound values. When multiple property sources exist, add each source in tests to prove higher-precedence sources truly override lower-precedence ones.

### 9.3. When Are Integration Tests Needed?

`ApplicationContextRunner` does not replace all integration tests. Integration tests are needed when behavior depends on:

- A real Config Server or containerized mock.
- Eureka/Consul or a discovery provider.
- Networking, HTTP clients, and service registries.
- Spring Security protecting management endpoints.
- Refresh events, messaging/bus, or bean lifecycles.
- How the application is packaged and run in a production-like environment.

Separate tests for **bean creation conditions** from tests for **dependency connectivity** so failures point to clear root causes.

## 10. Operations and Security Checklist

When a Spring Cloud application starts in production, observe signals that establish its state:

| Signal | Question to answer |
| --- | --- |
| Startup logs | Did the context refresh cleanly? Are there warnings about config imports or critical conditions? |
| Condition report | Did expected auto-configurations match? Why were any skipped? |
| Bean inventory | Are critical beans present in the right context? |
| Active profiles | Which profiles is the instance running with? |
| Property sources | Which source supplied the final value? Were there unexpected overrides? |
| Config Client logs | Which server, application name, profile, and label were used? |
| Discovery/registry health | Did the client register and look up services successfully? |
| Readiness | Is the application capable of serving requests, or merely alive? |

Key guidelines:

- Do not leave framework-wide debug/trace logging enabled long-term if logs grow excessive or risk capturing sensitive information.
- Do not expose `/actuator/env`, `/actuator/configprops`, `/actuator/beans`, or `/actuator/conditions` publicly just for debugging convenience.
- Protect management endpoints with authentication, authorization, and network policies.
- Never log secrets, tokens, passwords, or full resolved configurations.
- Decouple application health from optional dependency status; a recommendation service failing should not necessarily fail readiness for the entire API.
- Use the same observability practices across local/staging/production while tailoring access controls and detail levels to each environment.

## 11. Version Compatibility and Key Differences to Note

Spring Boot and Spring Cloud evolve initialization mechanisms, auto-configuration metadata, and config loading across releases. When reviewing examples or logs from another project, identify its versions before applying them.

Key points to watch:

- Spring Boot 3 uses `AutoConfiguration.imports` to register auto-configurations; older libraries may still use `spring.factories` metadata from earlier Boot generations.
- Modern Spring Cloud Config supports Config Data via `spring.config.import`; legacy projects may rely on a bootstrap context.
- APIs, property names, conditions, and Actuator endpoints can differ across versions.
- Choose a Spring Cloud release train compatible with Spring Boot per the official matrix, manage versions with the `spring-cloud-dependencies` BOM, and inspect the dependency tree after upgrades.
- Do not copy a `bootstrap.yml` snippet, auto-configuration example, or endpoint from an old article without confirming it matches your running version.

When hitting `NoSuchMethodError`, `ClassNotFoundException`, or unexpected bean conditions after an upgrade, check **the actually resolved versions**, not just what is declared in `pom.xml` or `build.gradle`.

## 12. Practice Exercises

**Exercise 1 — Missing Bean.** A controller injects `DiscoveryClient`, yet the application throws `NoSuchBeanDefinitionException`. Lay out the inspection sequence across classpath, provider starter, auto-configuration conditions, profiles, and bean inventory. Explain why adding Commons alone may not suffice.

**Exercise 2 — Overridden Property.** `application-prod.yaml` sets `inventory.client.read-timeout=400ms`, yet Actuator reports the effective value as `1s`. Identify which configuration sources to check and how to prove which source has higher precedence.

**Exercise 3 — Unmatched Auto-Configuration.** The condition report shows `@ConditionalOnProperty` did not match. List possible causes: wrong key, wrong value, inactive profile, unloaded property source, or overridden config. Write an `ApplicationContextRunner` test covering both enabled and disabled cases.

**Exercise 4 — Config Client.** An application has `spring-cloud-context` yet fails to read configuration from Config Server. Explain the difference between Context and Config Client, and list the dependencies, `spring.config.import`, and runtime evidence to check.

**Exercise 5 — Environment Comparison.** A bean exists locally but is missing in production. Build a comparison table covering runtime classpath, active profiles, property sources, exclusions, and the condition report; indicate what evidence is sufficient to conclude the root cause.

## 13. Key Takeaways and Reference Resources

When a Spring Cloud feature fails to work, follow the verification chain:

**Environment → BeanDefinition/bean → auto-configuration conditions → dependency/provider → runtime behavior.**

- `ApplicationContext` shows which beans the container manages.
- `Environment` shows active profiles and configuration sources; higher-precedence property sources can override file values.
- The condition evaluation report explains why auto-configurations were enabled or skipped.
- A starter puts dependencies on the classpath, but does not by itself prove the provider connected or the behavior works.
- Spring Cloud Context supports refresh; Config Client handles loading configuration from Config Server. Both responsibilities must be verified separately.

Official references to consult for your project's version:

1. [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
2. [Spring Boot Reference – Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
3. [Spring Boot Reference – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
4. [Spring Boot API – ApplicationContextRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
5. [Spring Cloud Config – Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
6. [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
7. [Spring Cloud – release train and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
