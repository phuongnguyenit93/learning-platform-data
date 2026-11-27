# Context Refresh Limitations in AOT and Native Image

Spring Cloud Context provides a mechanism to update configuration and refresh beans while the application is running. In a standard JVM application, the `@RefreshScope` annotation (written as @RefreshScope in prose below) can create a proxy for a bean, clear the cached target, and reinitialize the target the next time the bean is invoked. The /actuator/refresh endpoint can trigger this workflow after the Environment is updated.

That mechanism is incompatible with the Spring AOT and GraalVM native image models. AOT analyzes the application at build time, generating initialization code and the required hints based on the classpath, Environment, and bean definitions at build time. Spring Cloud Context does not support Context Refresh in AOT transformations and native images. Therefore, applications running under these two models must set:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

This limitation does not mean Spring Cloud Config Client cannot run in a native image. Config Client supports AOT/native image starting from Spring Cloud Config 4.0.0, with specific conditions regarding Config Data and configuration sources at build time. The application can still fetch configuration at startup; what is unsupported is relying on Spring Cloud Context to refresh the context and refresh-scoped beans while the process is running.

This lesson belongs to the **AOT and checkpoint** chapter of the **SPRING_CLOUD_CORE** module. Learners will distinguish AOT processing from runtime refresh, understand why the bean graph must remain stable, properly configure spring.cloud.refresh.enabled, design ways to apply configuration changes without Context Refresh, and distinguish native image from JVM checkpoint/restore using Project CRaC.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish AOT processing, native image, Spring ApplicationContext refresh, and Spring Cloud Context Refresh.
2. Explain how AOT generates initialization code from the classpath, Environment, and bean definitions at build time.
3. Describe the role of @RefreshScope, proxies, and target caches in standard JVM applications.
4. Explain why Spring Cloud Context Refresh is not supported in AOT transformations and native images.
5. Configure spring.cloud.refresh.enabled=false at the right time during build and runtime.
6. Identify limitations related to @Profile, @Conditional, and properties that affect bean creation.
7. Distinguish Config Client's AOT/native image support from runtime refresh capability.
8. Build configuration update strategies using rolling restarts or dedicated dynamic data mechanisms.
9. Distinguish native image from Project CRaC JVM checkpoint/restore.
10. Test startup, configuration, endpoints, and post-restore behavior across each deployment model.

## 2. Clarifying the Concepts

### 2.1. Spring ApplicationContext

ApplicationContext is the container managing beans, dependency injection, events, resources, and lifecycle of a Spring application. During standard startup, Spring reads configuration, creates bean definitions, initializes beans, and completes the context refresh process before the application is ready to serve requests.

The word "refresh" in ApplicationContext.refresh() refers to the process of initializing or refreshing the container according to Spring's lifecycle. It does not mean a running Spring Cloud application receives new configuration via /actuator/refresh.

### 2.2. Spring Cloud Context Refresh

Spring Cloud Context adds a mechanism to mutate the Environment and refresh certain beans without restarting the entire process.

Related components include:

- ContextRefresher: coordinates reloading property sources and detecting configuration changes.
- EnvironmentChangeEvent: notifies listeners of changed keys.
- Rebinding: rebinds certain ConfigurationProperties beans.
- RefreshScope: a scope managing target beans that can be reinitialized.
- @RefreshScope: marks a bean to use refresh scope.
- /actuator/refresh: an endpoint that can trigger a refresh when configured and exposed.

In the standard JVM model, this is a runtime mechanism. It is not part of the AOT build process.

### 2.3. Spring AOT

AOT stands for Ahead-of-Time. Spring analyzes the application at build time to generate artifacts that support more efficient runtime initialization, such as:

- Generated Java source code.
- Bytecode, for example for certain proxies.
- RuntimeHints for reflection, resource loading, serialization, and JDK proxies.
- Code to restore the analyzed bean definitions.

AOT helps Spring reduce dynamic discovery and processing work at startup. Decisions related to bean structure are made early based on the classpath and Environment of the build.

### 2.4. GraalVM Native Image

A native image is an executable compiled from the application and required runtime components. Spring Boot's native image uses AOT output as a mandatory input.

When running a native image, the application does not behave like a standard JVM capable of arbitrarily loading classes and creating dynamic bean structures. Many decisions about classpath, bean definitions, reflection, and configuration conditions have already been determined during the build.

### 2.5. Project CRaC Checkpoint/Restore

CRaC (Coordinated Restore at Checkpoint) creates a checkpoint from a running JVM and then restores a process from the saved image. After restore, the JVM resumes from the checkpoint image with its warmed-up state.

CRaC is still a JVM model. It differs from native image:

| Concept | Primary Decision Time | Runtime |
| --- | --- | --- |
| Standard JVM | Mainly at startup | JVM initializes beans and can use Spring Cloud refresh |
| Spring AOT on JVM | Part of bean structure at build time | JVM runs generated AOT code |
| GraalVM native image | Classpath, bean graph, and native compilation at build time | Native executable |
| JVM CRaC | Process state captured at checkpoint | Restores JVM from checkpoint |

CRaC has lifecycle callbacks before checkpoint and after restore. Spring Cloud has RefreshScopeLifecycle to refresh configuration and beans after restore when appropriate. This is a feature tied to JVM checkpoint/restore, not a way to enable Context Refresh in a native image.

## 3. RefreshScope Mechanism in Standard JVM Applications

### 3.1. RefreshScope Uses a Proxy and Target Cache

A bean with @RefreshScope is typically accessed through a proxy. The proxy routes calls to the current target bean. The target is lazily initialized when needed and stored in the scope's cache.

When refresh scope is invalidated, the current target is evicted from the cache. The next call through the proxy creates a new target from the current Environment and dependencies.

~~~mermaid
flowchart TD
    A[Caller] --> B[RefreshScope proxy]
    B --> C{Target already in cache?}
    C -->|Yes| D[Current target]
    C -->|No| E[Create new target]
    E --> F[Read current configuration]
    F --> G[Store target in cache]
    G --> D
    H[Refresh event] --> I[Invalidate target cache]
    I --> C
~~~

This mechanism is useful for clients or components that can be safely reinitialized when configuration changes. It does not automatically guarantee that every object depending on that bean is replaced.

### 3.2. Example of a Refresh-Scoped Bean

~~~java
@Component
@RefreshScope
public class PartnerClientSettings {

    private final String baseUrl;

    public PartnerClientSettings(Environment environment) {
        this.baseUrl = environment.getProperty("partner.api.base-url");
    }

    public String baseUrl() {
        return baseUrl;
    }
}
~~~

In a standard JVM application, after the Environment is updated and refresh scope is refreshed, the target bean can be recreated and read the new value.

This example only illustrates the mechanism. HTTP clients or connection pools created from old configuration may need their own lifecycle to close and recreate safely.

### 3.3. RefreshScope Does Not Replace Process Restart

Refresh scope refreshes certain target beans in the context. It does not:

- Change the running classpath.
- Load new dependency JARs.
- Change JVM arguments.
- Change heap size or GC.
- Automatically update every singleton.
- Automatically reinitialize every connection pool.
- Replace a new deployment.

Changes involving application structure or runtime processes still require an appropriate build/deploy/restart.

### 3.4. Other Limitations of Refresh Scope

Even in a standard JVM, refresh scope has limitations:

- @RefreshScope on a @Configuration class does not mean every bean declared in that class automatically belongs to refresh scope.
- A bean depending on a refreshable bean is not automatically recreated unless that dependency is also designed appropriately.
- Completely removing a property from configuration and refreshing does not necessarily alter the property's presence as expected.
- Certain bean types, such as HikariDataSource, are non-refreshable by default.
- @ConfigurationProperties using constructor binding, including Java records, cannot be refreshed through standard rebinding.

When designing a JVM application, inspect the lifecycle of each dependency instead of assuming every bean updates simultaneously.

## 4. How Does AOT Produce a Stable Bean Graph?

### 4.1. AOT Analyzes ApplicationContext at Build Time

Spring AOT creates a context for analysis. This process evaluates configuration classes, component scans, import selectors, and conditions to determine bean definitions.

During AOT processing, Spring does not perform the full bean instantiation process like a normal startup. It primarily creates and analyzes bean definitions, then generates the code needed to restore the bean factory state at runtime.

~~~mermaid
flowchart TD
    A[Application classes and dependencies] --> B[Build-time Environment]
    B --> C[AOT ApplicationContext processing]
    C --> D[Evaluate configuration and conditions]
    D --> E[Collect bean definitions]
    E --> F[Generate code and RuntimeHints]
    F --> G[Compile application]
    G --> H[JVM AOT runtime or native image]
~~~

Bean definitions that match the conditions at build time are included in the AOT output. Beans that do not match are excluded from the generated structure.

### 4.2. The Classpath Is Fixed

AOT assumes the classpath is fully determined at build time. The application cannot arbitrarily add a new library at runtime and expect Spring to rescan the classpath and create beans automatically like a standard JVM application.

For example, if a provider is only on the classpath in production but absent during AOT processing, the auto-configuration beans of that provider may not appear in the generated output.

### 4.3. @Profile and Profile-Specific Configuration

Profiles affect bean definitions. In AOT, profiles must be selected at build time. The profiles used during AOT processing will be baked into the corresponding AOT runtime configuration.

Example:

~~~java
@Configuration
@Profile("production")
class ProductionConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new ProductionPaymentGateway();
    }
}
~~~

If AOT processing runs with the test profile, the production configuration may not be included in the generated bean graph. Merely setting SPRING_PROFILES_ACTIVE=production after the native image has been built cannot add bean definitions that were excluded during the build.

For multiple environments, choose one of these strategies:

- Build separate AOT artifacts for each profile that has a different bean graph.
- Keep the bean graph stable and vary runtime data values.
- Use a factory/strategy registered since build time to select behavior within a designed scope.

Do not use runtime profiles to try to alter a bean structure that has been fixed by AOT.

### 4.4. @Conditional and `.enabled` Properties

Conditions such as @ConditionalOnProperty decide whether a bean is created. AOT evaluates conditions affecting bean presence at build time.

Example:

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "feature.payment",
        name = "enabled",
        havingValue = "true"
)
class PaymentConfiguration {

    @Bean
    PaymentProcessor paymentProcessor() {
        return new PaymentProcessor();
    }
}
~~~

If feature.payment.enabled=false during AOT processing, the PaymentProcessor bean is not included in the AOT output. Changing the property to true at runtime does not recreate the missing bean definition.

This is especially important when a system plans to use Config Server to toggle integrations via .enabled after a native image is already running.

### 4.5. RuntimeHints Do Not Make the Bean Graph Dynamic

RuntimeHints provide the native runtime with information about required reflection, resources, serialization, and proxies. Hints help the native image access anticipated components, but they do not turn a bean definition excluded at build time into a bean that can appear dynamically at runtime.

Do not confuse adding reflection hints with supporting dynamic bean creation or refreshing the entire ApplicationContext.

## 5. Why Is Spring Cloud Context Refresh Unsupported?

### 5.1. Runtime Refresh Requires Changing Bean State

Spring Cloud Context Refresh can update the Environment, rebind certain configuration properties, and invalidate the RefreshScope target cache. When the target is next invoked, it is recreated using the new configuration.

This is dynamic runtime behavior. Some components are reinitialized and their dependencies may be re-resolved from the container.

### 5.2. AOT Relies on Decisions Made at Build Time

AOT has already determined the bean structure based on the classpath and Environment at build time. Conditions deciding bean presence have also been evaluated.

A runtime mechanism attempting to refresh the context structure or recreate components based on new decisions can go beyond what AOT analyzed and generated supporting code for.

Spring Cloud Commons documentation explicitly states that **Context Refresh is not supported for Spring AOT transformations and native images**. This is a feature support limitation, not merely a performance warning.

### 5.3. Disable Refresh Autoconfiguration

For AOT or native image applications, set:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

The spring.cloud.refresh.enabled property controls the auto-configuration of refresh scope and related features. The default value in standard Spring Cloud applications is true; for AOT/native image, it must be set to false.

### 5.4. The Property Must Be Set When AOT Processing Occurs

This is a critical point: do not wait until the native executable is running to pass:

~~~bash
SPRING_CLOUD_REFRESH_ENABLED=false
~~~

If AOT processing already evaluated conditions with a different value, the generated code may reflect an inappropriate bean structure. Ensure the property is false in the Environment used during AOT build and keep that same decision when running.

Example shared configuration for the AOT/native variant:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

If using a dedicated profile for the AOT variant, that profile must be active during both AOT processing and runtime. Check the actual Maven/Gradle plugin build configuration to ensure the property is loaded at the right phase.

### 5.5. Do Not Re-enable Refresh via Runtime Override

After building with refresh disabled, do not try to re-enable it using:

~~~bash
SPRING_CLOUD_REFRESH_ENABLED=true
~~~

Changing a runtime property cannot make an unsupported feature safe. Nor should you expose /actuator/refresh expecting that endpoint to work in a native image.

### 5.6. Audit Remaining Beans Annotated with @RefreshScope

When disabling refresh auto-configuration, audit classes still annotated with @RefreshScope.

Do not assume the annotation turns into a normal singleton when the scope is disabled. If a bean still declares refresh scope while that scope is not registered, the context may fail to start.

For the AOT/native variant:

1. Identify which beans are using @RefreshScope.
2. Remove the annotation if the bean does not need refresh.
3. If there is variant-specific configuration, use appropriate configurations/bean definitions right from build time.
4. Verify no remaining dependencies require refresh scope.
5. Run AOT processing and startup tests to catch scope errors early.

Do not simply set spring.cloud.refresh.enabled=false and ignore beans that previously used refresh scope.

## 6. Configuration by Deployment Type

### 6.1. Standard JVM

Non-AOT JVM applications can use refresh scope if needed:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: true
~~~

You can expose /actuator/refresh if the application genuinely needs it and the endpoint is secured.

### 6.2. JVM Running AOT Code

Spring Boot allows running AOT-generated initialization code on the JVM via spring.aot.enabled=true, provided the artifact already contains AOT code.

~~~bash
java -Dspring.aot.enabled=true -jar orders-service.jar
~~~

This is still a JVM, but the constraints on bean structure and build-time conditions still apply. Therefore, do not use Spring Cloud Context Refresh as a mechanism to change the bean graph in this case.

### 6.3. GraalVM Native Image

Native image requires AOT. Required configuration:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

The application can load initial configuration at startup, but does not use Spring Cloud Context to refresh scopes at runtime.

### 6.4. Decision Table

| Model | spring.cloud.refresh.enabled | Context Refresh |
| --- | --- | --- |
| Standard JVM, no AOT | Can be true | Supported as configured |
| JVM running AOT-generated code | false | Unsupported |
| GraalVM native image | false | Unsupported |
| JVM with CRaC checkpoint/restore | Depends on design and compatibility | Can use refresh-on-restart via lifecycle |
| Native image and CRaC | Do not treat as the same model | Do not use CRaC lifecycle as a substitute for native refresh |

## 7. Config Client in AOT and Native Image

### 7.1. Config Client Can Still Fetch Configuration

Spring Cloud Config Client supports Spring AOT transformations and GraalVM native images starting from version 4.0.0. Therefore, disabling refresh scope does not mean abandoning Spring Cloud Config.

An application can use:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: configserver:https://config.internal
  cloud:
    refresh:
      enabled: false
~~~

At startup, Config Client can fetch configuration from Config Server and populate the Environment before beans are initialized.

### 7.2. Config Data Source Must Be Available During Build

When building an application with Config Client and AOT processing, Spring Cloud Config documentation requires that the Config Data source the client connects to be reachable during the build.

For example, if the client fetches configuration from Config Server, the server needs to be running and reachable at the configured URL when AOT processing executes.

The source can be:

- Spring Cloud Config Server.
- Consul.
- ZooKeeper.
- Vault.
- Another supported Config Data source.

This is a build-time requirement for AOT. Do not run a build on a machine without connectivity to the configuration source and assume the output will match a build environment that has Config Server.

### 7.3. Values Affecting Bean Creation Must Be Consistent

Properties affecting bean creation, such as:

- @Profile.
- @ConditionalOnProperty.
- Provider enablement.
- Types of integrations auto-configured.
- Bootstrap/configuration flags.

must have consistent values at build time and runtime. If they differ, the generated bean graph may not match the runtime configuration.

For example, if AOT builds with feature.payment.enabled=false, but at runtime Config Server returns true, you cannot expect the payment bean to appear automatically.

### 7.4. Legacy Config-First Bootstrap

Spring Cloud Config documentation explicitly states that AOT/native image support is not available for legacy config-first bootstrap when setting:

~~~properties
spring.config.use-legacy-processing=true
~~~

For applications needing AOT/native, prefer Config Data import:

~~~yaml
spring:
  config:
    import: configserver:
~~~

Verify the exact Spring Cloud Config version and how the project bootstraps. Do not mix legacy bootstrap with Config Data mode under the same lifecycle assumptions.

### 7.5. Native Startup Still Needs to Connect to the Config Source

A native executable can start quickly, but if Config Client has to call Config Server or Vault at startup, network time is still counted toward startup time.

AOT does not eliminate the cost of accessing remote configuration sources. Configure timeouts, retries, and fail-fast policies appropriate for the application's requirements.

### 7.6. Do Not Confuse Config Server with Config Client

AOT/native capabilities of Config Client and Config Server are documented separately:

- Config Client supports AOT/native from 4.0.0, under the stated conditions.
- Config Server supports AOT transformations from 4.0.0 and native image from 4.1.0 with GraalVM 21 and later, while requiring some workarounds per the release documentation.

The fact that Config Server can run natively does not alter the limitations of Spring Cloud Context Refresh on clients or servers that use refresh scope.

## 8. Alternatives to Context Refresh in Native Image

When ApplicationContext cannot be refreshed, choose a configuration update strategy tailored to the type of change.

### 8.1. Rolling Restart When Configuration Changes

This is the easiest option to operate and verify when changes affect bean creation or resource lifecycle.

Workflow:

1. Update configuration in a versioned source.
2. Validate configuration before deploying.
3. Create a new deployment revision or trigger a rollout.
4. Start new instances with the current configuration.
5. Wait for readiness and health checks to pass.
6. Shift traffic to the new instances.
7. Drain and stop old instances.
8. Monitor for errors after rollout.
9. Roll back to a tested revision if necessary.

~~~mermaid
flowchart TD
    A[Config revision changes] --> B[Validate configuration]
    B --> C[Start new instance]
    C --> D[Load config at startup]
    D --> E[Readiness checks]
    E --> F{Healthy?}
    F -->|No| G[Stop new instance and rollback]
    F -->|Yes| H[Shift traffic]
    H --> I[Drain old instance]
    I --> J[Stop old instance]
~~~

Rolling restarts create new instances with a consistently initialized bean graph and configuration. This fits native image because it does not require mutating bean definitions inside an existing process.

### 8.2. Use Configuration Versions or Revisions

Each deployment should record:

- Native image digest.
- Config label or commit.
- Profile.
- Secret version or credential reference.
- Startup timestamp.
- Readiness results.

When rolling back, restore a compatible, tested version set. Do not just swap a configuration file while keeping a binary that was AOT-compiled under different conditions.

### 8.3. Move Frequently Changing Data Out of the Bean Graph

Some values do not need to alter the bean structure. They can be modeled as runtime data:

- Feature flags.
- Tenant lists.
- Routing tables.
- Business thresholds.
- Enabled partner lists.
- Display rules.

A service can read this data from a database, remote API, or a dynamic configuration client. If immediate updates are needed, design a dedicated component to fetch data and publish a new snapshot.

### 8.4. Use Immutable Snapshots and Atomic Swaps

Example of a service managing a policy snapshot itself:

~~~java
@Component
public class RuntimePolicyProvider {

    private final AtomicReference<RuntimePolicy> current =
            new AtomicReference<>(RuntimePolicy.defaults());

    public RuntimePolicy current() {
        return current.get();
    }

    public void replace(RuntimePolicy next) {
        current.set(Objects.requireNonNull(next));
    }
}
~~~

Another component can fetch the new policy from a data source, validate it, and call replace(...). In-flight requests consistently read either the old or new snapshot.

This is application runtime data design, not Spring Cloud Context Refresh. It does not create new beans, change @Conditional evaluations, or modify the ApplicationContext structure.

### 8.5. Explicitly Update Clients or Resources

If a change requires recreating an HTTP client or connection pool, you can design a factory managing resource versions:

1. Read the new configuration.
2. Validate URLs, credentials, and timeouts.
3. Create the new client/pool.
4. Test connectivity.
5. Swap the active reference to the new client.
6. Drain requests using the old client.
7. Close the old client.

This approach requires managing concurrency, resource disposal, timeouts, and initialization failures. Not every library supports safe resource replacement.

### 8.6. Feature Flag Service

If features need to be toggled quickly, use a feature flag service or a runtime policy component. Feature flags should control business behavior within an existing bean graph.

Do not use a runtime property to enable an auto-configuration bean that was excluded during AOT. All required implementations must exist in the pre-built structure.

## 9. CRaC Checkpoint/Restore and RefreshScopeLifecycle

### 9.1. CRaC Is a Checkpoint of a Running JVM

CRaC allows capturing the state of a JVM at a point in time, saving the checkpoint image, and restoring a process from that image. It can reduce startup time and preserve warmed-up state.

Checkpoint/restore is not native image. The restored process is still a JVM with the captured classes, heap, and runtime state.

### 9.2. Spring Cloud Refreshes Configuration After Restore

Spring Cloud Context provides RefreshScopeLifecycle to trigger Context Refresh when an application restarts after a JVM checkpoint/restore.

This behavior can:

- Rebind ConfigurationProperties beans.
- Refresh @RefreshScope beans.
- Clear the target cache so new targets are initialized from the current configuration.

Controlling property:

~~~properties
spring.cloud.refresh.on-restart.enabled=true
~~~

According to current configuration properties, the default value is true. It can be disabled:

~~~properties
spring.cloud.refresh.on-restart.enabled=false
~~~

### 9.3. This Is Not an Exception for Native Image

Do not infer that because CRaC can trigger Context Refresh after restore, a native image can also refresh. The two models have different runtimes.

- CRaC: JVM is restored and Spring lifecycle handles callbacks after restore.
- Native image: executable produced from AOT/native compilation; Spring Cloud Context Refresh is unsupported.

Do not use spring.cloud.refresh.on-restart.enabled=true to override the spring.cloud.refresh.enabled=false requirement in native images.

### 9.4. Refresh-on-Restart Does Not Automatically Fetch All New Configuration

After restore, Spring Cloud can trigger the refresh lifecycle, but that does not mean all remote configuration sources are always reloaded the same way across every architecture.

Verify:

- Is the configuration source reachable after restore?
- Is the Environment updated by the deployment mechanism?
- Which property sources are retained?
- Are credentials or tokens still valid?
- Can beans be safely reinitialized?
- Were network connections, sockets, and file handles properly handled before checkpoint?

CRaC requires coordinating resource lifecycles. A checkpoint containing stale connections or expired credentials can cause errors after restore if not handled properly.

### 9.5. Protecting Checkpoint Images

A CRaC image contains JVM memory state. Values the JVM has read, including properties or secrets, may appear in checkpoint files.

Therefore:

- Protect read permissions on checkpoint files.
- Do not store checkpoints in public artifact repositories.
- Apply encryption at rest where appropriate.
- Control backups and retention.
- Rotate credentials if old checkpoints are no longer permitted for use.
- Do not place checkpoint images in environments with broader access privileges than the environment that created them.

## 10. Sample Configuration for AOT/Native Applications

### 10.1. Refresh Disabled Configuration

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    refresh:
      enabled: false
~~~

This configuration must be loaded during AOT processing. Do not merely pass an environment variable at runtime after the image has already been built.

### 10.2. Separate Build Profile for Native Variant

If the application has both standard JVM mode and a native variant, you can use a dedicated configuration profile:

application-native.yml:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

The native profile must be selected during AOT processing and at runtime of the native executable. If the profile alters the bean graph, verify the exact beans included in the AOT output.

Do not use the same native image for profiles with different bean graphs and expect runtime profiles to automatically add excluded beans.

### 10.3. Verifying the Property Was Loaded

In the build or test environment, you can assert:

~~~java
assertThat(environment.getProperty("spring.cloud.refresh.enabled"))
        .isEqualTo("false");
~~~

This only checks the Environment value. Additional AOT/native startup tests are needed to confirm no beans or dependencies require refresh scope.

### 10.4. Checking for Remaining Annotations

Search for classes with:

~~~java
@RefreshScope
~~~

Evaluate each bean:

- Can refresh scope be removed and the bean initialized once at startup?
- Can the configuration be converted to runtime data?
- Does the resource need to be replaced via a custom factory?
- Can a rolling restart be used?

If a bean genuinely requires refresh scope, native image is currently not a suitable deployment mode for that requirement.

## 11. Testing Across the Deployment Matrix

### 11.1. Matrix to Verify

| Test Model | Refresh Setting | Result to Verify |
| --- | --- | --- |
| Standard JVM | true | Refresh scope works as configured |
| JVM AOT | false | AOT startup succeeds without relying on Context Refresh |
| Native image | false | Native executable startup succeeds |
| Native image | true | Unsupported configuration; do not use for deployment |
| JVM CRaC | As designed | Verify post-restore lifecycle and refresh-on-restart |
| Config Client AOT/native | false | Config source available at build; client fetches config at startup |

### 11.2. Testing Startup with Refresh Disabled

Create an integration test starting the context with:

~~~properties
spring.cloud.refresh.enabled=false
~~~

Verify:

- ApplicationContext starts up.
- No errors occur due to an unregistered refresh scope.
- Required beans are created according to AOT configuration.
- No code paths invoke /actuator/refresh.
- ConfigurationProperties receive the expected startup values.

### 11.3. Testing AOT on the JVM

Spring Boot can run a JAR containing AOT-generated initialization code:

~~~bash
java -Dspring.aot.enabled=true -jar orders-service.jar
~~~

Run smoke tests for critical beans, profiles, and conditions. Do not test only on a standard JVM and conclude the native image will work as well.

### 11.4. Testing Native Image

Check:

1. Native compilation completes.
2. The image runs in the target runtime.
3. Required Config Data is read.
4. The bean graph matches the build profile.
5. No dependencies require refresh scope.
6. Health/readiness pass.
7. External resources are reachable.
8. Logs have no reflection/resource hint errors.
9. The refresh endpoint is not relied upon as an operational feature.
10. Config changes trigger restarts/rollouts or the designed dynamic data path.

### 11.5. Testing Config Client

For Config Client:

- Ensure Config Server or a test config source is available when AOT processing runs.
- Use a fixed application name, profile, and label.
- Verify Config Data import is processed.
- Verify properties affecting bean creation have consistent values between build and runtime.
- Test startup when the config source is unreachable per optional/fail-fast policy.
- Verify the runtime native client still fetches configuration as expected.

Do not use a production Config Server as a fixture source for automated builds if pipelines are not permitted to access it or should not depend on production data.

### 11.6. Testing CRaC Separately

For a JVM with CRaC:

1. Start the application on a CRaC-supported JDK.
2. Warm up necessary code paths.
3. Check resources before checkpoint.
4. Create the checkpoint.
5. Restore the process.
6. Observe Spring-managed lifecycle restart.
7. Verify RefreshScopeLifecycle if enabled.
8. Check config, credentials, and connections after restore.
9. Verify the application serves requests.
10. Verify checkpoint files are protected.

This is a JVM checkpoint/restore test, not a replacement for native image testing.

## 12. Common Errors and Resolutions

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Native image fails due to refresh scope | spring.cloud.refresh.enabled was not set to false during AOT processing | Put the property into the build-time Environment |
| Runtime sets refresh false but native still fails | AOT processed conditions with a different value | Rebuild with the correct configuration |
| Bean reports no scope named refresh | Bean still carries @RefreshScope while refresh auto-configuration is disabled | Remove the annotation or redesign the bean for the native variant |
| Config Server returns new config but bean does not change | No Context Refresh in native | Use restart/rollout or a dynamic data component |
| Native image is missing a bean | @Profile or @Conditional did not match at build time | Check AOT profile and build-time properties |
| Changing runtime profile does not create new bean | Bean graph was fixed at build time | Build the corresponding variant or keep the bean graph stable |
| Config Client AOT build cannot reach server | Config Data source unavailable during build | Provide an available test/build config source |
| Runtime config differs from build config causing strange behavior | Properties affecting bean creation are inconsistent | Synchronize build/runtime values |
| Using legacy bootstrap with AOT | spring.config.use-legacy-processing=true | Switch to Config Data import as documented |
| /actuator/refresh missing or not working | Refresh auto-configuration disabled or endpoint unsupported | Do not rely on the endpoint in AOT/native |
| CRaC restore uses stale connections | Resources not properly coordinated in lifecycle | Handle before-checkpoint and after-restore |
| Refresh-on-restart does not run | spring.cloud.refresh.on-restart.enabled=false or refresh lifecycle not created | Check properties and Spring Cloud Context |
| Checkpoint image contains secrets | JVM read secrets before checkpoint | Protect the image, restrict distribution, and control retention |
| AOT build used wrong profile | Build profile did not match intended runtime | Set profile before AOT processing and verify output |

## 13. Migrating an Application Using RefreshScope to Native Image

Suppose orders-service uses Config Server and multiple @RefreshScope beans. The engineering team wants to migrate the application to a native image.

### Step 1 — Inventory Refresh Use Cases

List:

- Classes with @RefreshScope.
- /actuator/refresh endpoints.
- Event listeners for EnvironmentChangeEvent.
- ConfigurationProperties beans that get rebound.
- Resources created from configuration.
- Integrations toggled via @ConditionalOnProperty.

Categorize each case as startup-only, dynamic-data, or resource-recreation.

### Step 2 — Choose a Policy for Each Change Type

| Change | Strategy for Native Image |
| --- | --- |
| Service endpoint | Load at startup; change via restart/rollout |
| Database credentials | Load at startup; rollout or dedicated resource replacement |
| Feature flag | Dynamic feature service or runtime policy snapshot |
| Provider bean .enabled | Decided at build time |
| Log level | Use supported runtime logging mechanism, tested separately |
| Classpath integration | Build a new image |
| Routing list | Runtime data in a dedicated component |

### Step 3 — Disable Refresh Auto-Configuration

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Ensure the property is present during AOT processing.

### Step 4 — Remove Refresh-Scope Dependencies

Remove @RefreshScope on beans that no longer need it. For beans requiring data updates, switch to a runtime data model. For beans requiring resource recreation, design an explicit factory and lifecycle.

### Step 5 — Check Config Client

If using Config Server, migrate to Config Data import if still using legacy bootstrap. Ensure Config Server or the config source is reachable during the AOT build and properties affecting bean creation are consistent.

### Step 6 — Build AOT/Native and Test

Run AOT processing, native compilation, and smoke tests. Confirm the bean graph, config, and resources match the intended profile.

### Step 7 — Update Operational Procedures

Replace "refresh all instances" actions with controlled rollouts. Record artifact digests, config labels, and secret versions. Monitor readiness and maintain rollback capability.

## 14. Pre-Release Checklist for AOT/Native

### Build-Time Environment

- [ ] Classpath is fixed and complete.
- [ ] Profile is selected before AOT processing.
- [ ] Properties affecting bean presence have correct values.
- [ ] spring.cloud.refresh.enabled=false.
- [ ] Required Config Data source is reachable during build.
- [ ] Config Client does not use legacy config-first bootstrap.
- [ ] Build and runtime agree on properties affecting bean creation.

### Bean Graph

- [ ] No remaining beans require @RefreshScope.
- [ ] No remaining code depends on /actuator/refresh.
- [ ] @ConditionalOnProperty is verified in build-time config.
- [ ] Required beans are present in AOT output.
- [ ] RuntimeHints for reflection/resources/proxies are sufficient.
- [ ] Resource factories have clear lifecycles.

### Runtime and Operations

- [ ] Native executable starts in the target environment.
- [ ] Config Client fetches configuration properly at startup.
- [ ] Readiness checks essential dependencies.
- [ ] Configuration changes have a restart/rollout process.
- [ ] Artifact digests and config revisions are recorded.
- [ ] Rollback has been tested.
- [ ] Logs and Actuator do not assume refresh scope is active.

### CRaC If Used

- [ ] Distinguish JVM checkpoint/restore from native image.
- [ ] Check RefreshScopeLifecycle and spring.cloud.refresh.on-restart.enabled.
- [ ] Resources are handled before checkpoint and after restore.
- [ ] Checkpoint files are protected as data that may contain secrets.
- [ ] Restore is tested on supported JDK and OS.

## 15. Practice Exercises

**Exercise 1 — Distinguish Types of Refresh.** Describe the differences between ApplicationContext.refresh(), AOT refreshForAotProcessing, and Spring Cloud /actuator/refresh. State when each runs and its purpose.

**Exercise 2 — Observe AOT Conditions.** Create a bean with @ConditionalOnProperty. Run AOT processing with the property set to true and then false. Observe which bean definitions are included in the output.

**Exercise 3 — Disable RefreshScope.** Create an application with a @RefreshScope bean. Set spring.cloud.refresh.enabled=false, then identify errors or leftover dependencies when the context starts. Remove the annotation and retest.

**Exercise 4 — Config Client AOT.** Create a test Config Server and Config Client. Run AOT processing while the server is available. Try changing a property affecting bean creation between build and runtime and record the result.

**Exercise 5 — Native Image Startup.** Build a native executable with refresh disabled. Verify the application fetches configuration at startup and does not depend on /actuator/refresh.

**Exercise 6 — Rolling Restart.** Change a downstream endpoint in Config Server. Perform a native image rollout, verify new instances use the new configuration, and then drain old instances.

**Exercise 7 — Runtime Policy Snapshot.** Write a RuntimePolicyProvider using AtomicReference. Create a test swapping the snapshot while multiple requests read data and verify there are no partial update states.

**Exercise 8 — CRaC Restore.** On a CRaC-enabled JVM, create a checkpoint and restore it. Observe lifecycle callbacks and RefreshScopeLifecycle. Compare with native image and explain why the two mechanisms are not equivalent.

**Exercise 9 — Build-Time Profiles.** Create two profiles with different bean definitions. Run AOT with each profile and verify that profiles cannot arbitrarily alter the bean graph after the build.

**Exercise 10 — Checkpoint Security Check.** Run an application with a test secret, create a checkpoint, and audit the storage procedure, read permissions, backup, and retention of checkpoint files.

## 16. Key Takeaways and Reference Sources

- Spring AOT analyzes ApplicationContext at build time and generates code/hints to restore the bean factory.
- AOT fixes the classpath and bean presence decisions; @Profile and @Conditional are evaluated against the build-time Environment.
- Spring Cloud Context Refresh is not supported for Spring AOT transformations and native images.
- AOT/native images require spring.cloud.refresh.enabled=false during AOT processing.
- Context Refresh cannot be re-enabled via a runtime property after a native image is built.
- Audit beans still annotated with @RefreshScope; disabling auto-configuration can leave the scope unregistered.
- Spring Cloud Config Client supports AOT/native from 4.0.0, but the Config Data source must be available during build and properties affecting bean creation must remain consistent between build and runtime.
- Legacy config-first bootstrap with spring.config.use-legacy-processing=true is not supported in AOT/native.
- Config Client can still fetch configuration at startup; that does not mean the bean graph can be refreshed while running.
- Changes affecting beans or resources in a native image typically require a restart/rolling deployment.
- Frequently changing business data can be modeled as a runtime snapshot or feature policy independent of the bean graph.
- CRaC is JVM checkpoint/restore. RefreshScopeLifecycle can trigger refresh after restore; this is not a solution for native images.
- Checkpoint files may contain sensitive data read by the JVM, so they must be protected.

Official sources to cross-reference for your project's Spring Boot/Spring Cloud versions:

1. [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
2. [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
3. [Spring Framework – Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
4. [Spring Boot – Ahead-of-Time Processing With the JVM](https://docs.spring.io/spring-boot/reference/packaging/aot.html)
5. [Spring Cloud Config – Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
6. [Spring Cloud Config – AOT and Native Image Support](https://docs.spring.io/spring-cloud-config/reference/server/aot-and-native-image-support.html)
7. [Spring Boot – Checkpoint and Restore With the JVM](https://docs.spring.io/spring-boot/reference/packaging/checkpoint-restore.html)
8. [Spring Framework – JVM Checkpoint Restore](https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html)
9. [Project CRaC – Checkpoint and Restore](https://crac.org/use/checkpoint-and-restore/)
10. [Spring Cloud – Release train and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
