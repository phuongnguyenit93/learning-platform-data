# Inspecting Auto-Configuration Conditions in Spring Boot gRPC

## 1. Why Inspect Auto-Configuration?

In **SPRING_GRPC**, a Spring Boot starter can automatically register beans for the gRPC server or client based on dependencies, configuration, and existing beans in the `ApplicationContext`. This avoids manually wiring every component, yet introduces subtle failure modes: the starter is in the build but configuration does not run, client beans never appear, or a default configuration backs off because the application supplied a replacement bean.

**Inspecting auto-configuration conditions** means determining why an auto-configuration was applied or skipped, then cross-checking the result against the runtime classpath, properties, and actual beans.

This lesson focuses on:

- Common Spring Boot condition groups: classpath, property, bean, and resource.
- How a gRPC starter is discovered and its conditions evaluated.
- The back-off mechanism when the application provides custom beans.
- Reading the Condition Evaluation Report and Actuator's `conditions` endpoint.
- Writing condition tests using `ApplicationContextRunner`.
- Distinguishing auto-configuration errors from service registration, channel, or network connectivity errors.

gRPC examples use **`net.devh`** starters for illustration. Official Spring gRPC has its own version-specific auto-configuration registration and settings. Custom example properties defined in this lesson are not default properties of every gRPC starter.

## 2. Which Conditions Govern Auto-Configuration?

An auto-configuration class is typically applied when multiple conditions match simultaneously. Common conditions include:

| Condition | Annotation | Question to Answer |
| --- | --- | --- |
| Classpath | `@ConditionalOnClass` | Are the required classes/libraries on the runtime classpath? |
| Property | `@ConditionalOnProperty` | Does the property exist with a matching value? |
| Bean present | `@ConditionalOnBean` | Are the required dependent beans already in the context? |
| Bean missing | `@ConditionalOnMissingBean` | Has the application already declared a replacement bean? |
| Resource | `@ConditionalOnResource` | Does the required file/resource exist? |
| Web application type | `@ConditionalOnWebApplication` | Does the app use the expected web context type? |
| Profile | `@Profile` | Is the corresponding profile active? |

Conditions can be combined at the class level or on individual `@Bean` methods. If any condition fails to match, the corresponding configuration is skipped.

### 2.1. Classpath Conditions

`@ConditionalOnClass` checks whether a class can be loaded from the classpath. This prevents starters from creating configurations that depend on uninstalled libraries.

For example, a gRPC client configuration might require `io.grpc.ManagedChannel`. If the runtime includes only the gRPC server artifact without the required client library, client auto-configuration may not activate.

Always inspect the **runtime classpath**, not just the declared dependency list. A dependency might be excluded, assigned the wrong scope, or altered by version conflict resolution.

### 2.2. Property Conditions

`@ConditionalOnProperty` inspects properties in the Spring `Environment`. For instance, an optional configuration activates only when `app.grpc.metrics.enabled=true`.

This condition is commonly used to toggle features per profile or environment. Note:

- `havingValue` defines the expected match value.
- `matchIfMissing` determines behavior when the property is absent.
- Properties can originate from YAML, environment variables, command-line arguments, or test overrides.
- A typo in the property name or an override from a higher-precedence source can cause the condition not to match.

Never assume a property exists just because you wrote it in a YAML file; verify that the file/profile was actually loaded.

### 2.3. Bean Conditions and Back-Off

`@ConditionalOnBean` applies configuration only when a matching bean is already registered. `@ConditionalOnMissingBean` typically provides a default bean unless the application already supplied one.

For example, a starter may provide a default channel factory; if the application registers a custom factory of the expected type, the default configuration backs off. This is intentional extensibility, not necessarily an error.

Distinguish these cases:

- Bean absent because a condition failed to match.
- Bean absent because auto-configuration was never discovered.
- Default bean absent because a replacement bean already exists.
- Context fails because multiple beans of the same type exist or a required dependency is missing.

### 2.4. Resource and Web Context Conditions

A configuration may require a resource file such as a trust store or a specific application context type. If the resource is missing or the context type mismatches, that configuration may be skipped.

However, for TLS, not every starter checks file existence with a conditional annotation; some libraries only read resources when building the server or channel. Thus, a certificate path error may surface during bean creation or transport startup even without a matching `@ConditionalOnResource` entry in the condition report.

## 3. How Is gRPC Starter Auto-Configuration Discovered?

In modern Spring Boot, auto-configuration classes are typically annotated with `@AutoConfiguration` and registered via the resource:

`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Each line in this file lists the fully qualified name of an auto-configuration class. Spring Boot reads the list and evaluates conditions on each class and its bean methods.

A starter can group multiple configurations, such as:

- Shared configuration for gRPC Java.
- Server configuration when the server artifact is on the classpath.
- Client configuration when the client artifact is on the classpath.
- TLS, interceptor, or health integration configuration when corresponding dependencies/properties are present.

This is a common structural pattern, not a guarantee of exact class names across all starters. Spring Boot 2.7 and newer use `AutoConfiguration.imports` for new auto-configurations; older projects may still use legacy registration files such as `spring.factories`.

### Configuration Ordering Also Matters

Auto-configurations can declare before/after relationships so conditional beans are registered at the right time. `@AutoConfiguration(after = ...)` or `before = ...` orders configuration processing; it does not by itself guarantee a dependent bean will exist.

`@ConditionalOnMissingBean` is particularly sensitive to ordering: the condition is evaluated against bean definitions already known at processing time. Therefore, when writing custom auto-configurations, use Spring Boot's ordering contracts rather than relying on incidental scan order.

## 4. Example of a Conditional Auto-Configuration

Suppose an application has a feature that records metrics for gRPC client calls. This feature should be registered only when:

1. The gRPC Java client API is on the classpath.
2. The application enables `app.grpc.observability.enabled=true`.
3. The application has not provided its own metrics implementation.

Example custom configuration:

```java
@AutoConfiguration
@ConditionalOnClass(name = "io.grpc.ManagedChannel")
@ConditionalOnProperty(
    prefix = "app.grpc.observability",
    name = "enabled",
    havingValue = "true"
)
public class GrpcClientObservabilityAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GrpcClientMetrics.class)
    GrpcClientMetrics grpcClientMetrics() {
        return new GrpcClientMetrics();
    }
}
```

`GrpcClientMetrics` is an application-defined type in this example. This configuration illustrates condition mechanics; it does not instrument RPCs by itself. To collect actual metrics, wire the bean to an appropriate interceptor or instrumentation.

Register the class in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
dev.example.grpc.GrpcClientObservabilityAutoConfiguration
```

And enable the feature:

```yaml
app:
  grpc:
    observability:
      enabled: true
```

Four scenarios:

| Classpath | Property | Custom Bean Present | Outcome |
| --- | --- | --- | --- |
| `ManagedChannel` present | `true` | No | Auto-configuration creates default bean |
| `ManagedChannel` present | Missing / `false` | No | Property condition fails; no bean created |
| `ManagedChannel` present | `true` | Yes | `@ConditionalOnMissingBean` backs off; app bean is used |
| `ManagedChannel` missing | `true` | No | Classpath condition fails |

If the auto-configuration class is not listed in the imports file, its internal conditions are never evaluated as a discovered auto-configuration. In that case, enabling the property will still not produce the bean.

## 5. Reading the Condition Evaluation Report

A quick way to see why configurations were applied or skipped is enabling Spring Boot's debug report:

```bash
java -jar app.jar --debug
```

Or when running from an IDE, add `--debug` as a program argument. Spring Boot prints the **Condition Evaluation Report**, typically containing:

- **Positive matches:** configurations whose required conditions were satisfied.
- **Negative matches:** excluded configurations and the exact reason a condition failed.
- **Exclusions:** auto-configurations explicitly excluded.
- **Unconditional classes:** configurations without standard conditions.

When inspecting a gRPC starter, locate server/client auto-configurations in the report. If a class appears under negative matches, read the detailed reason instead of stopping at "did not match."

### Workflow for Reading the Report

1. Identify the server or client auto-configuration class.
2. Check classpath conditions: were required gRPC APIs found?
3. Check property conditions: prefix, property name, and effective value.
4. Check bean conditions: were dependent beans created, or did an app bean replace the default?
5. Check exclusions and configuration ordering.
6. Cross-reference findings against actual beans in the `ApplicationContext`.

`--debug` does not fix configuration by itself. It provides the evidence needed to pinpoint the first unsatisfied condition or back-off.

## 6. Using the Actuator Conditions Endpoint

If the application includes Spring Boot Actuator, the `conditions` endpoint exposes auto-configuration evaluation results over HTTP.

Example exposing the endpoint in an administrative environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
```

Once the application starts, the endpoint is typically available at:

`/actuator/conditions`

This endpoint helps inspect a running application without digging through full startup logs. Protect it with authentication and network policies and expose it only on an appropriate management interface; condition details can reveal library structure and internal configuration.

Actuator `conditions` shows condition evaluation results. It does not prove a remote gRPC server is healthy, a channel is connected, or RPCs can succeed. Those require health checks or test RPC calls.

## 7. Testing Conditions with ApplicationContextRunner

Do not test auto-configuration solely by booting the entire application. `ApplicationContextRunner` builds a lightweight context, applies specific auto-configurations, sets properties, and asserts resulting beans.

Example test for the configuration in Section 4:

```java
class GrpcClientObservabilityAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    GrpcClientObservabilityAutoConfiguration.class
                )
            );

    @Test
    void createsMetricsBeanWhenEnabled() {
        contextRunner
            .withPropertyValues(
                "app.grpc.observability.enabled=true"
            )
            .run(context ->
                assertThat(context)
                    .hasSingleBean(GrpcClientMetrics.class)
            );
    }

    @Test
    void doesNotCreateMetricsBeanWhenDisabled() {
        contextRunner
            .withPropertyValues(
                "app.grpc.observability.enabled=false"
            )
            .run(context ->
                assertThat(context)
                    .doesNotHaveBean(GrpcClientMetrics.class)
            );
    }

    @Test
    void backsOffWhenApplicationProvidesBean() {
        contextRunner
            .withPropertyValues(
                "app.grpc.observability.enabled=true"
            )
            .withBean(
                GrpcClientMetrics.class,
                GrpcClientMetrics::new
            )
            .run(context ->
                assertThat(context)
                    .hasSingleBean(GrpcClientMetrics.class)
            );
    }
}
```

These tests require the appropriate Spring Boot test dependencies (`spring-boot-test`, JUnit 5, and AssertJ; typically supplied by `spring-boot-starter-test`). The example tests three behaviors: property enabled, property disabled, and back-off when the application provides its own bean.

To test classpath conditions, use `FilteredClassLoader` with `ApplicationContextRunner` to simulate a missing class, then assert the bean is not created. That is much cleaner than stripping real dependencies from the build just to test one condition branch.

`ApplicationContextRunner` verifies context/bean conditions. It does not replace integration tests invoking RPCs over real channels and servers.

## 8. Diagnosing When gRPC Auto-Configuration Does Not Run

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| No server bean | Missing server starter or classpath condition mismatch | Runtime dependency tree and negative matches |
| No client/channel bean | Missing client starter, wrong artifact, or property condition | Condition report and effective properties |
| Auto-configuration absent from report | Class not imported/discovered or excluded | Check imports metadata and exclusions |
| Default bean not created | `@ConditionalOnMissingBean` backed off | Inspect beans of the same type in context |
| Property condition mismatch | Wrong prefix/name, different value, or inactive profile | Inspect `Environment` and property sources |
| Context reports missing dependency | `@ConditionalOnBean` unsatisfied or business bean not scanned | Check bean definitions and component scan |
| Bean exists yet RPC returns `UNAVAILABLE` | Conditions passed, but target/network/server has issues | Check DNS, port, TLS, and server readiness |
| RPC returns `UNIMPLEMENTED` | Service method unregistered or contract mismatch | Check `BindableService`, service name, and `.proto` |

### Separating Errors Across Layers

An auto-configuration appearing as a positive match only means its activation conditions were met. It does not guarantee every bean it creates initializes cleanly; bean instantiation can still fail due to constructors, resources, or dependencies.

Similarly, having a `ManagedChannel` bean does not mean the channel reached `READY`. Having a service bean does not mean the service was bound to the server if the starter does not recognize that bean type. Investigate sequentially from condition report, bean context, and server lifecycle to actual RPC calls.

## 9. Pre-Fix Checklist Before Changing Configuration

1. Confirm the right server/client starter and version are on the runtime classpath.
2. Check whether the relevant auto-configuration class was discovered or excluded.
3. Read positive/negative matches and exact reasons in the Condition Evaluation Report.
4. Check properties after Spring merges YAML, profiles, environment variables, and command-line arguments.
5. Check bean conditions and back-offs; search for custom beans of the same type.
6. Check ordering when auto-configuration depends on beans provided by another configuration.
7. Use `ApplicationContextRunner` to reproduce minimal condition behavior.
8. Once beans appear, continue verifying service registration, channels, and RPCs separately.
9. Disable or secure debug/Actuator endpoints appropriately before deploying to production.

In **SPRING_GRPC**, inspecting auto-configuration confirms whether Spring Boot recognized the right dependencies and conditions to build gRPC components. The condition report explains why configurations were applied or backed off; bean checks and RPC tests verify subsequent stages. Separating these steps lets you fix the true root cause rather than guessing at dependencies or properties.
