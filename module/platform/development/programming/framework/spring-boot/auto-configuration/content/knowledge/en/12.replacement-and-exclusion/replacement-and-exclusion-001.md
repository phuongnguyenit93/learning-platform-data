# Customization via properties, customizer, or user bean: choosing the right level of intervention

## 1. Context: when Spring Boot has already auto-configured a component

In Spring Boot, **auto-configuration** provides default beans and configuration based on the classpath, `Environment`, and the beans that the application has already registered. When you want to change behavior, there are three common levels of intervention:

1. **Properties:** adjust options exposed by Spring Boot or a library via `application.yml`, `application.properties`, environment variables, etc., while still using the bean created by auto-configuration.
2. **Customizer (bean callback):** add to or modify part of the bean-building process via a callback that auto-configuration **actively invokes**; most of the framework defaults remain intact.
3. **User-defined bean (`@Bean`):** create your own replacement component; if auto-configuration has a matching `@ConditionalOnMissingBean` condition, the default bean branch will **back off** (not register).

These are three different levels of **control**, not just three ways of writing the same value. Choosing the right level helps you preserve defaults for security, metrics, resource management, and version upgrades. The final section also distinguishes this from **completely excluding an auto-configuration**, a broader measure that should only be used when truly needed.

### Quick selection rules

| What needs to change | Usually appropriate option | Why |
| --- | --- | --- |
| Timeout, endpoint, pool size, logging level, or an on/off flag with an official key | **Properties** | Easy to configure per environment, minimal Java code, keeps the default path |
| Adding headers/interceptors, codecs, filters, serializers, or builder settings not supported by keys | **Customizer** | Modifies a specific part without losing the remaining settings |
| Need a completely different implementation, initialization algorithm, lifecycle, topology, or integration | **User bean** | Full control over object creation and dependencies |
| Do not want **an entire group** of auto-configurations applied | **Exclude auto-configuration** | Disables the configuration group, which may affect multiple beans |

This is a decision guide, **not a guarantee that every library provides all three mechanisms**. You must check the documentation and actual auto-configuration code: a property only takes effect if the code reads it, a customizer only takes effect if the code applies it, and a user bean only makes the default back off if the actual condition covers that bean type or name.

## 2. Understanding the order and boundaries of intervention

Picture a typical auto-configuration with the following flow:

```text
                Environment / PropertySources
                           |
                           v
               @ConfigurationProperties
                           |
                           v
               default configuration for Builder
                           |
                           v
       ObjectProvider<Customizer>.orderedStream()
                 apply each customizer
                           |
                           v
                       build()
                           |
                           v
          default auto-configuration bean
             (only when conditions match)
                           
If the user registers a bean of the matching type:
    @ConditionalOnMissingBean -> do not register the default bean.
    The build() path above does not run for that default bean.
```

This is **a sample design**, not a mandatory pipeline for every Spring Boot auto-configuration. Some components apply customizers before or inside a builder configurer, some use post-processors, and some do not have a builder. Check the actual invocation point and ordering.

Two phases must be distinguished:

- **Bean definition registration:** Spring evaluates `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, and other conditions. Bean conditions only see definitions that have been processed up to that point. Auto-configuration is processed after user configurations, making it the appropriate place for back-off conditions.
- **Bean instantiation:** when a `@Bean` method is called, the code receives properties, customizers, and dependencies, then builds the object. If a condition causes the method to be skipped, a callback located **inside that method** does not automatically run for a user-supplied bean.

`@Primary` and `@Qualifier` can affect **bean selection during injection**; they do not mean Spring has removed the default bean. Conversely, `@ConditionalOnMissingBean` can prevent the default bean from being registered at all, right before the injection step.

## 3. Level 1 — Customizing with properties

### 3.1. How it works

Spring Boot uses `Environment` and `@ConfigurationProperties` to map configuration into Java types; for example:

```properties
demo.client.base-url=https://api.example.test
demo.client.timeout=5s
demo.client.enabled=true
```

In a well-designed starter, `@ConfigurationProperties(prefix="demo.client")` holds settings such as `baseUrl` and `timeout`, while `@ConditionalOnProperty` can decide whether to create the bean. Equivalent keys can be placed in YAML:

```yaml
demo:
  client:
    base-url: https://api.example.test
    timeout: 5s
    enabled: true
```

Advantages:

- Configure per dev/test/prod, container, profile, or environment variable without changing code; `PropertySource` entries follow a precedence order.
- The binder supports type conversion such as `Duration`, `URI`, lists, enums, etc., and can validate configuration using Bean Validation when supported by the project.
- Well-suited for values that the starter **has publicly exposed** for users to control.

Limitations:

- You cannot assume that every setter on a library has a corresponding property key.
- A default value set on a field of `@ConfigurationProperties` **does not automatically appear in Environment**.
- If a condition should match when a key is missing, `matchIfMissing` must be configured appropriately; conditions do not automatically read post-binding values from properties beans.
- Changing properties does not guarantee updating already-instantiated beans in a running context; a context restart/recreation or an application-specific refresh mechanism is typically required.
- Properties can be overridden by a higher-precedence source. When results are unexpected, check the final resolved source rather than reading only one file.

**Illustrative example, not built-in Spring Boot properties:** the `demo.client.*` keys above are defined by the sample auto-configuration in Section 6 itself. They do not belong to Spring Boot's default namespace.

### 3.2. When not to escalate to a customizer

If the documentation already provides `spring.task.execution.pool.max-size` to configure an appropriate thread pool, writing a custom `Executor` just to change the pool size can alter how Boot selects the executor. Similarly, when you only need to change an HTTP timeout and the component has an official property/builder setting, using the supported configuration generally reduces maintenance effort.

There is no **global** precedence rule like "properties always beat customizers" or vice versa. The order is determined by the design of the code. In the Section 6 example, properties are applied to the builder **before** customizers, so a customizer writing the same field afterward wins.

## 4. Level 2 — Customizing with a customizer

### 4.1. A customizer is an extension contract, not a magic annotation

A customizer is a callback/interface supported by auto-configuration, such as `ClientCustomizer` with a `customize(Builder)` method. The application registers a bean implementing the interface; the auto-configuration collects and invokes it when creating its own bean.

Basic pattern:

```java
@FunctionalInterface
interface ClientCustomizer {
    void customize(Client.Builder builder);
}

// In auto-configuration:
@Bean
Client client(ClientProperties properties,
              ObjectProvider<ClientCustomizer> customizers) {
    Client.Builder builder = Client.builder()
        .timeout(properties.getTimeout());

    customizers.orderedStream()
        .forEach(customizer -> customizer.customize(builder));

    return builder.build();
}
```

The snippet above only illustrates the **idea**: `Client`, `ClientProperties`, and imports are hypothetical types, not a complete program. Section 6 provides a compilable Java file with `DemoClient` and `DemoClientCustomizer`.

The key point is the `customizers.orderedStream()...` call. If the auto-configuration does not read customizer beans, **merely declaring a callback bean will have no effect**. Even with built-in Spring Boot components, a customizer for a Boot-managed builder typically does not automatically apply to every builder you instantiate yourself with `new` or another factory method.

API examples in Spring Boot 3.5 include `org.springframework.boot.web.client.RestClientCustomizer` to customize `RestClient.Builder`; JSON components also have specific hooks. Names and packages may change between Spring Boot 3.x and 4.x: always check the API for the version you are using.

### 4.2. Ordering multiple customizers

When auto-configuration uses `ObjectProvider<T>.orderedStream()`, Spring sorts according to `Ordered`/`@Order` rules. Smaller order values are processed first. For example, if two customizers both modify the same `label`:

```java
@Bean
@Order(10)
DemoClientCustomizer first() {
    return builder -> builder.label("first");
}

@Bean
@Order(20)
DemoClientCustomizer second() {
    return builder -> builder.label("second");
}
```

Assuming these beans are invoked **via `orderedStream()` and no other callback overwrites `label`**, the final result is `"second"` because the second customizer is applied later. This snippet is an illustration inside a configuration class and requires imports and the types defined in the full example.

Do not assume "the customizer with `@Order(1)` always wins" when **overwriting the same field**: if the logic simply calls setters sequentially, the callback that runs **later** is the one that determines the final value. When orders are equal or undeclared, avoid relying on arbitrary ordering; specify an explicit order or separate customizer responsibilities.

### 4.3. When a customizer is appropriate

Use it when you need to add interceptors, header policies, serialization modules, mapper options, callbacks, connection customizations, etc., while still wanting auto-configuration to handle creating, registering, and closing the main bean.

Keep in mind:

- Customizers are sometimes invoked for **multiple builders or multiple beans**, so avoid unexpected side effects, especially I/O operations or mutating shared singletons inside the callback.
- If the callback runs before the bean is finalized, do not expect the target bean to already exist for injection back into that same customizer; this can cause a circular dependency.
- Prefer idempotent customizers when the API might invoke them repeatedly.
- Do not use a customizer to change structural aspects that the builder/API does not support; in that case, you need a user bean or another extension mechanism.
- Some hooks apply to the builder while others apply to the **post-build object**; their effect and ordering cannot be inferred from the interface name alone.

## 5. Level 3 — Creating a user bean and the back-off mechanism

### 5.1. The @ConditionalOnMissingBean condition

In auto-configuration, a common pattern is:

```java
@Bean
@ConditionalOnMissingBean(DemoClient.class)
DemoClient demoClient(...) {
    // Create the default bean.
}
```

When the application provides a matching `DemoClient` bean, Spring Boot **does not register** the default `demoClient` bean. This is *back-off*: the user bean runs as created; Boot does not automatically take the default bean's properties/customizers and apply them to the custom bean.

You can omit `value` on the annotation on a `@Bean` method: Spring Boot then infers the type to check from the method's **return type**. However, `@ConditionalOnMissingBean(DemoClient.class)` makes the intent explicit and avoids relying on inference from an overly broad return type.

The condition can match by **type**, **name**, or other criteria depending on the annotation attributes. Not all auto-configurations back off in the same way; for example, in some integrations a specific bean name such as `applicationTaskExecutor` is also an important contract. Check the actual conditions in the auto-configuration you are using.

### 5.2. @Primary, bean definition overriding, and back-off are different

- `@Primary`: selects one bean as the default candidate when multiple compatible beans are injected. **Does not by itself prevent registration** of the auto-configured bean.
- `@Qualifier`: specifies a bean at an injection point; does not create or remove an auto-configured bean.
- **Back-off**: if `@ConditionalOnMissingBean` does not match, the default bean is skipped during registration; this is the intentional auto-configuration mechanism.
- **Bean definition overriding**: two definitions with the same name can cause an error; enabling `spring.main.allow-bean-definition-overriding=true` is not the recommended way to perform normal replacement. Relying on proper type/name back-off expresses intent more clearly.
- **Exclude auto-configuration**: removes the entire auto-configuration from the candidate list, which is broader than backing off a single `@Bean`.

**Do not assume that simply giving a bean the same name as the default bean will make Boot replace it.** If the condition checks by **type**, a bean with a different type but the same name does not satisfy the condition and may cause a name collision error. Conversely, if the condition checks for type `DemoClient`, a bean of the same type named `manualClient` can also make the default bean back off.

### 5.3. Consequences of using a replacement bean

The user bean takes responsibility for the constructor, configuration, connections, timeouts, lifecycle, metrics/tracing, SSL, decorators, and compatibility with dependent code. Auto-configuration conveniences are **not automatically copied** to that bean.

You need to check other beans that depend on the default bean. Sometimes auto-configuration only backs off one bean while auxiliary beans are still created; sometimes a class-level condition can cause an entire group to be skipped. Read the exact annotation placement and run tests for the bean structure after replacement.

Especially for beans with a common interface, declare a sufficiently specific return type on `@Bean` so conditions have reliable metadata. If you register `@Bean Object manualClient()` and only return `DemoClient` at runtime, pre-instantiation type inference may fail to recognize the replacement bean.

## 6. Complete example with Java 17 and Spring Boot 3.5

Goal: create a sample client that performs no network I/O and only holds immutable configuration. The example verifies all three levels of intervention accurately:

1. No configuration: auto-configuration creates `DemoClient` with defaults.
2. Property set: the default client is created with values from `Environment`.
3. `DemoClientCustomizer` registered: the default client is still created, but the customizer modifies the builder after properties are assigned.
4. User registers `DemoClient`: auto-configuration backs off; the customizer used in the default branch **does not automatically modify** the user bean.
5. `demo.client.enabled=false` set: disables creation of the **default bean**.

The example uses `ApplicationContextRunner` so no web server or API server is needed. The code models a custom-written auto-configuration, **not a promise that Spring Boot includes `demo.client.*` or `DemoClientCustomizer` out of the box**.

### Directory structure

```text
customization-choice-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── CustomizationChoiceTest.java
```

### File pom.xml

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
    <artifactId>customization-choice-demo</artifactId>
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

### File src/test/java/example/CustomizationChoiceTest.java

```java
package example;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
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

class CustomizationChoiceTest {

    @ConfigurationProperties(prefix = "demo.client")
    public static class DemoClientProperties {
        private URI baseUrl = URI.create("https://api.example.test");
        private Duration timeout = Duration.ofSeconds(2);

        public URI getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(URI baseUrl) {
            this.baseUrl = baseUrl;
        }

        public Duration getTimeout() {
            return timeout;
        }

        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }
    }

    // Immutable object; does not make network connections in tests.
    record DemoClient(URI baseUrl, Duration timeout, String label) {

        static Builder builder() {
            return new Builder();
        }

        static final class Builder {
            private URI baseUrl;
            private Duration timeout;
            private String label = "auto";

            Builder baseUrl(URI value) {
                this.baseUrl = value;
                return this;
            }

            Builder timeout(Duration value) {
                this.timeout = value;
                return this;
            }

            Builder label(String value) {
                this.label = value;
                return this;
            }

            DemoClient build() {
                return new DemoClient(baseUrl, timeout, label);
            }
        }
    }

    @FunctionalInterface
    interface DemoClientCustomizer {
        void customize(DemoClient.Builder builder);
    }

    @AutoConfiguration
    @EnableConfigurationProperties(DemoClientProperties.class)
    static class DemoClientAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(DemoClient.class)
        @ConditionalOnProperty(
            prefix = "demo.client",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
        )
        DemoClient demoClient(
                DemoClientProperties properties,
                ObjectProvider<DemoClientCustomizer> customizers) {

            DemoClient.Builder builder = DemoClient.builder()
                .baseUrl(properties.getBaseUrl())
                .timeout(properties.getTimeout());

            customizers.orderedStream()
                .forEach(customizer -> customizer.customize(builder));

            return builder.build();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCustomizerConfiguration {
        @Bean
        DemoClientCustomizer tuneClient() {
            return builder -> builder
                .timeout(Duration.ofSeconds(8))
                .label("tuned");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserBeanConfiguration {
        @Bean
        DemoClient manualClient() {
            return new DemoClient(
                URI.create("https://manual.example.test"),
                Duration.ofSeconds(42),
                "manual"
            );
        }
    }

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(DemoClientAutoConfiguration.class)
            );

    @Test
    void defaultBeanUsesJavaDefaults() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(DemoClient.class);
            assertThat(context).hasBean("demoClient");

            DemoClient client = context.getBean(DemoClient.class);
            assertThat(client.baseUrl())
                .isEqualTo(URI.create("https://api.example.test"));
            assertThat(client.timeout())
                .isEqualTo(Duration.ofSeconds(2));
            assertThat(client.label()).isEqualTo("auto");
        });
    }

    @Test
    void propertiesChangeTheAutoConfiguredBean() {
        runner.withPropertyValues(
                "demo.client.base-url=https://configured.example.test",
                "demo.client.timeout=5s"
            )
            .run(context -> {
                DemoClient client = context.getBean(DemoClient.class);
                assertThat(client.baseUrl())
                    .isEqualTo(
                        URI.create("https://configured.example.test")
                    );
                assertThat(client.timeout())
                    .isEqualTo(Duration.ofSeconds(5));
                assertThat(client.label()).isEqualTo("auto");
            });
    }

    @Test
    void customizerChangesTheBuilderAfterPropertyBinding() {
        runner.withUserConfiguration(UserCustomizerConfiguration.class)
            .withPropertyValues("demo.client.timeout=5s")
            .run(context -> {
                assertThat(context).hasSingleBean(DemoClient.class);
                assertThat(context).hasBean("demoClient");

                DemoClient client = context.getBean(DemoClient.class);
                assertThat(client.timeout())
                    .isEqualTo(Duration.ofSeconds(8));
                assertThat(client.label()).isEqualTo("tuned");
            });
    }

    @Test
    void userBeanMakesDefaultBackOff() {
        runner.withUserConfiguration(
                UserBeanConfiguration.class,
                UserCustomizerConfiguration.class
            )
            .withPropertyValues("demo.client.timeout=5s")
            .run(context -> {
                assertThat(context).hasSingleBean(DemoClient.class);
                assertThat(context).hasBean("manualClient");
                assertThat(context).doesNotHaveBean("demoClient");

                DemoClient client = context.getBean(DemoClient.class);
                assertThat(client.baseUrl())
                    .isEqualTo(URI.create("https://manual.example.test"));
                assertThat(client.timeout())
                    .isEqualTo(Duration.ofSeconds(42));
                assertThat(client.label()).isEqualTo("manual");
            });
    }

    @Test
    void enabledFalseDisablesOnlyTheAutoConfiguredClient() {
        runner.withPropertyValues("demo.client.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(DemoClient.class);
                assertThat(context)
                    .hasSingleBean(DemoClientProperties.class);
            });
    }
}
```

### Running and interpreting

In the directory containing `pom.xml`, use JDK 17+ and Maven:

```bash
java -version
mvn -version
mvn test
```

**Expected result:** all **5 tests** in `CustomizationChoiceTest` pass and Maven reports `BUILD SUCCESS` (assuming dependencies download and the environment works normally). The code does not print fixed business stdout. Detailed results are usually found in `target/surefire-reports`. No calls to `example.test` URLs are needed because the demo only stores the `URI`.

How to read the 5 tests:

| Test | Intervention | Resulting primary bean |
| --- | --- | --- |
| `defaultBeanUsesJavaDefaults` | Nothing provided | `demoClient` with 2-second timeout and label `auto` |
| `propertiesChangeTheAutoConfiguredBean` | Base URL and timeout properties | `demoClient` with 5-second timeout and new URL |
| `customizerChangesTheBuilderAfterPropertyBinding` | 5-second timeout property and customizer | `demoClient` with 8-second timeout, label `tuned` |
| `userBeanMakesDefaultBackOff` | User-defined bean, plus property/customizer | Only `manualClient` with 42-second timeout, label `manual` |
| `enabledFalseDisablesOnlyTheAutoConfiguredClient` | Property `enabled=false` | No default `DemoClient`; `DemoClientProperties` still exists |

**Note on ordering in the example:** `DemoClientAutoConfiguration.demoClient(...)` itself assigns property values first, then calls `customizers.orderedStream()`. If you change the code so customizers run before properties, the result when both modify timeout may reverse. Do not generalize "customizer beats property" as a guarantee for every starter.

**Note on replacement:** in the `userBeanMakesDefaultBackOff` test, the user bean is named `manualClient`, different from `demoClient`. The bean still causes the auto-configured `demoClient` to back off because the condition checks **the `DemoClient` type**, not the same name. And the customizer is not automatically applied to `manualClient` because the default bean-creation method did not run.

`ApplicationContextRunner` is a testing tool for auto-configuration (used in unit/integration tests, not a production-running Spring Boot application). In an auto-configuration packaged as a real starter, the auto-configuration class must be declared in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; the test example explicitly loads it with `AutoConfigurations.of(...)`, so this imports file is not needed.

## 7. Scenarios for choosing an intervention level in projects

### Scenario A: changing the timeout of a component that already supports a key

**Choose properties.** Check the current configuration documentation, key, time units, and profile effects. Only move to a customizer when the key cannot express the requirement or when custom logic is needed instead of a fixed value.

### Scenario B: adding standard headers to a Boot-provided HTTP client

**Choose a customizer for that builder/HTTP client**, such as the callback type `RestClientCustomizer` in Spring Boot 3.5, if you are using the auto-configuration-managed bean/builder and the hook is invoked. Check ordering against framework-registered customizers so you do not accidentally overwrite settings that must be kept.

You do not need to define a new `RestClient.Builder` or `RestClient` just to add a header if an official hook already handles it. If the application calls `RestClient.builder()` itself and bypasses the Boot-provided builder, hooks that depend on Boot's builder may not be used.

### Scenario C: changing the protocol or integrating a specialized HTTP client

**Choose a user-created bean** when you need full control over the factory, lifecycle, and dependencies that a customizer cannot satisfy. Check `@ConditionalOnMissingBean`, type, bean name, other annotations, and auxiliary beans. If you still want to keep part of the defaults, check builders/configurers provided by Boot or other customization mechanisms before building everything yourself.

### Scenario D: a fallback bean exists in a starter, but the application wants its own implementation

**Choose a user bean** and let the starter use `@ConditionalOnMissingBean`. In starter code, ensure the condition only appears in auto-configuration and the `@Bean` return type is clear enough. Avoid asking users to toggle the application-wide bean-definition-overriding flag just to replace a single bean.

### Scenario E: wanting to completely disable the default datasource configuration

If you truly **do not want** Spring Boot to create a datasource from auto-configuration, you can exclude the corresponding auto-configuration class:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Or configure it on the application class (snippet, requires the corresponding Spring Boot dependency):

```java
@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

This is **excluding an actual auto-configuration**, not backing off a single `@Bean`. It may prevent features that depend on the datasource from initializing. Do not exclude `DataSourceAutoConfiguration` merely to change the JDBC URL, username, or pool properties; in that case, configure `spring.datasource.*` instead.

`spring.autoconfigure.exclude` takes **auto-configuration class** names recognized by Boot; do not use it arbitrarily to disable an application `@Configuration` class. When using the Java snippet, you must import `org.springframework.boot.autoconfigure.SpringBootApplication`, `org.springframework.boot.SpringApplication`, and `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`; this is not a file in the Section 6 test demo.

## 8. Ordering and precedence issues in practice

### 8.1. There is no universal precedence system across the three mechanisms

The sample example applies properties and then customizers. When a user bean appears, the default build path is skipped. However, other auto-configurations might use:

- Customizers to modify a builder **before** binding or applying framework configurers.
- Bean post-processors that run **after** the bean is created (different from builder customizers).
- A customizer that only registers if the classpath has a required class or a property is enabled.
- Conditions that back off only by name, only by type, or require multiple criteria.

Therefore, the accurate statement is not "bean > customizer > property always takes precedence" as a global formula; you must check **where each mechanism is applied and which conditions are evaluated**.

### 8.2. When multiple beans of the same type exist

If you create `@Primary DemoClient customClient()` while the default is still registered due to another condition, both beans may exist. `@Primary` only affects resolution at injection points without a qualifier; it does not guarantee that all code will pick that bean, especially with `@Qualifier` or lookup by name.

If an auto-configured bean already exists and you only want to change behavior within a narrow scope, using a customizer for that object or an explicitly named bean can be less risky. If you want back-off, verify whether the actual condition ignores `defaultCandidate=false` beans, non-autowire-candidate beans, or special generic types.

### 8.3. Implications for upgrades

Changing supported properties is generally easier to upgrade because framework code retains responsibility for constructing the bean. Customizers depend on specific hook APIs and require tracking across versions. Replacement beans carry most of the integration responsibility; you must re-test when Framework/Boot changes initialization, tracing, metrics, SSL, timeouts, thread models, or lifecycle.

That is a **maintenance trend**, not an absolute effectiveness ranking. If requirements genuinely demand a different implementation, a replacement bean remains the right choice.

## 9. Diagnosing when configuration has no effect

1. **Wrong key or configuration source:** check `@ConfigurationProperties` metadata, valid property logs, profiles, and `PropertySource` precedence. A misspelled property might be ignored depending on validation/binding; do not conclude "Boot ignored it" before verifying the exact name.
2. **Customizer is not invoked:** confirm the bean implements the right interface, is scanned/imported into the same `ApplicationContext`, is not filtered out by conditions, and that auto-configuration obtains it via a dependency or `ObjectProvider`.
3. **Customizer is invoked but values are overwritten:** check `@Order` order, builder/configurer ordering, other callbacks modifying the same setting, or creating a new instance without using the customized builder.
4. **Default bean still remains:** inspect what type or name `@ConditionalOnMissingBean` checks; check the declared type on the `@Bean` method and whether the bean qualifies as a candidate.
5. **Custom bean does not exist:** verify `@Configuration` is loaded, whether the bean was excluded by profile/condition, dependency initialization errors, or name collisions.
6. **Default bean is gone, but the system fails:** the replacement bean may lack capabilities, labels, or qualifiers expected by the rest of the system. Check Boot-managed integrations.
7. **Excluded too broadly:** look for classes in `spring.autoconfigure.exclude` or `@SpringBootApplication(exclude=...)`; a group of supporting auto-configurations might not have been registered.
8. **Misjudged evaluation timing:** `@ConditionalOnMissingBean` checks bean definitions processed up to the moment the condition is evaluated; Spring Boot recommends placing this kind of condition in auto-configuration, not in regular configurations without ordering guarantees.

To read the condition evaluation report of a Spring Boot application with an executable jar, you can run:

```bash
java -jar app.jar --debug
```

With Spring Boot Actuator installed and endpoints suitably configured, `/actuator/conditions` shows the condition report; `/actuator/configprops` helps inspect bound `@ConfigurationProperties` beans. Sensitive diagnostic endpoints should not be exposed publicly in production systems. For a custom-written auto-configuration, the `ApplicationContextRunner` tests in Section 6 provide clearer automated verification.

## 10. Common design mistakes and fixes

- **Writing a new bean for a simple setting:** easily loses defaults. Use documented properties first.
- **Assuming any bean suffixed with "Customizer" is applied automatically:** there must be a place calling the hook.
- **Using a builder customizer while instantiating a new builder yourself:** the hook applies inside the managed builder pipeline, not automatically to every object of the same type.
- **Confusing `@Primary` with back-off:** these are two independent mechanisms.
- **Using `spring.main.allow-bean-definition-overriding=true` as a general workaround:** hides name conflicts and creates hard-to-track dependencies; use proper bean types/conditions.
- **Placing `@ConditionalOnMissingBean` in early-processed user configuration:** may see fewer bean definitions than expected; place the condition in auto-configuration.
- **Writing `@Bean Object customClient()` for an instance whose actual type is `DemoClient`:** overly broad metadata can prevent conditions from recognizing it when needed.
- **Having multiple customizers modify one field without ordering:** results can become unpredictable.
- **Assuming a customizer still runs when the default bean backs off:** if the callback is only invoked inside the default bean-creation method, it does not run for the user bean.
- **Excluding an entire auto-configuration just to replace one bean:** may lose many auxiliary beans; usually a bean override via back-off is all that is needed.
- **Not testing across multiple scenarios:** test default, property-only, customizer, replacement, and disablement.

## 11. Decision checklist before intervening

Answer in order:

1. **What do I need to change?** A documented value, a builder step, or the entire implementation?
2. **Is there an official property?** Search the Spring Boot reference/metadata and starter documentation; determine type, default, units, and environment effects.
3. **Is there an official customizer hook?** Check the interface, where auto-configuration calls it, ordering, scope, and lifecycle.
4. **If registering a custom bean, what is the back-off condition?** Check `@ConditionalOnMissingBean` by type/name and accompanying conditions; avoid guessing.
5. **Which defaults will I have to bring myself?** Timeouts, headers, tracing, metrics, resources, SSL, thread management, shutdown, and related integrations.
6. **Is exclude truly necessary?** Reserved for disabling an entire auto-configuration; understand the impact on auxiliary beans.
7. **Which branches have been tested at minimum?** No customization; property; customizer; user bean; disabled via property; multiple customizers/multiple beans if applicable in practice.

## 12. Self-check questions

**Question 1.** To change a timeout for which the starter already has an official key, is it necessary to define a new `@Bean`?  
**Answer:** No. A property is sufficient when auto-configuration uses that key.

**Question 2.** A customizer bean is present, but auto-configuration does not inject or invoke it. Will builder values change automatically?  
**Answer:** No. Callback beans require an explicit invocation point in the configuration process.

**Question 3.** Will `@ConditionalOnMissingBean(DemoClient.class)` back off if the user defines a bean of the same type named `manualClient`?  
**Answer:** Yes, assuming the bean is a candidate considered at the time the condition is evaluated, because the condition here is type-based.

**Question 4.** If you manually create a `DemoClient` bean, will the customizer inside the `demoClient(...)` method automatically run on that bean?  
**Answer:** No, if the auto-configured method itself has backed off and nowhere else invokes the customizer.

**Question 5.** Does marking a user bean `@Primary` remove the auto-configured bean?  
**Answer:** No. `@Primary` only plays a role in dependency selection; back-off depends on the auto-configuration's bean conditions.

**Question 6.** If you want to drop an entire group of auto-configuration instead of just changing a timeout, what should you consider?  
**Answer:** You can exclude the appropriate auto-configuration class, but check which auxiliary beans are lost and why the entire group needs to be removed.

## Official references

- Spring Boot 3.5 Reference — **Creating Your Own Auto-configuration** (bean conditions, back-off, ordering, and `ApplicationContextRunner`): https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 Reference — **Externalized Configuration** (`Environment`, `@ConfigurationProperties`, conversion, precedence sources): https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Framework 6.2 Javadoc — `ObjectProvider.orderedStream()` and `@Order` rules: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/ObjectProvider.html
- Spring Boot 3.5 API — `RestClientCustomizer`, example hook for HTTP clients: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/client/RestClientCustomizer.html
- Spring Boot 3.5 Reference — **Task Execution and Scheduling** (properties, custom executor, and bean name rules): https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html

**Remember:** adjust **values** with properties when supported; adjust **part of the bean-building path** with customizers when the hook is actually invoked; **replace the object** with a user bean when full control and proper back-off conditions are needed. Exclude only when you want to remove auto-configuration at a broader scope. Before deciding, read the conditions and test the exact configuration branch being used.
