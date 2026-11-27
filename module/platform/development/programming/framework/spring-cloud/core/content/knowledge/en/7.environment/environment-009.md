# Distinguishing Environment Changes from Initialized Bean Changes

This lesson belongs to the **Environment** chapter of the **SPRING_CLOUD_CORE** module. In a Spring application, configuration values are read from `Environment` and its `PropertySource` instances, and then passed into beans when beans are created or bound. When configuration changes while the application is running, these two things are **not synonymous**:

- **Environment changes:** the value the system resolves from configuration sources may now be different.
- **Initialized bean changes:** the object currently used by the application actually receives the new value or is recreated with the new value.

A single `Environment` update does not automatically mutate every field in every singleton bean. Spring Cloud Context provides mechanisms such as `EnvironmentChangeEvent`, rebinding for `@ConfigurationProperties`, and `@RefreshScope` to handle certain cases. Learners must understand precisely which mechanism applies to which kind of bean, their limitations, and how to verify after refresh.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Describe the roles of `Environment`, `PropertySource`, and precedence order when reading properties.
2. Distinguish values looked up dynamically from Environment from values injected into a bean at initialization time.
3. Explain why `@Value` in an ordinary singleton does not change automatically after a property source changes.
4. Distinguish initial binding, `@ConfigurationProperties` rebinding, and `@RefreshScope` target recreation.
5. Explain the role of `EnvironmentChangeEvent`, the refresh workflow, and related Actuator endpoints.
6. Identify limitations of mutable/immutable configuration beans, stateful beans, and dependent beans.
7. Design tests verifying Environment, beans, and individual instances after configuration changes.
8. Operate refresh safely in multi-instance systems, avoiding inconsistent configuration states.

## 2. Three Layers to Distinguish

You can view the configuration flow across three layers:

~~~mermaid
flowchart TD
    SRC["Config source: YAML, env, system property, Config Server..."] --> PS["PropertySource collection"]
    PS --> ENV["Environment: lookup current value"]
    ENV --> CREATE["Create bean / initial config binding"]
    CREATE --> BEAN["Initialized singleton bean"]
    ENV --> EVENT["EnvironmentChangeEvent / refresh workflow"]
    EVENT --> REBIND["@ConfigurationProperties rebind"]
    EVENT --> SCOPE["@RefreshScope target cache invalidation"]
    REBIND --> BOUND["Configuration bean updated"]
    SCOPE --> NEXT["Next call creates new target"]
~~~

The three layers should not be conflated:

| Layer | Question | Example |
| --- | --- | --- |
| **Configuration source** | Where does the raw data live? | YAML file, environment variable, system property, Config Server. |
| **Environment** | When looking up this key, what is the effective value? | `environment.getProperty("app.banner")`. |
| **Running bean** | Which object holds or uses the value? | Singleton with `banner` field, `@ConfigurationProperties` bean, `@RefreshScope` proxy. |

Suppose `app.banner=Welcome` when the application starts. A singleton bean receives this value via its constructor. Later, a configuration source is updated to `Hello again`.

- Environment may return `Hello again` on a fresh lookup.
- The field already assigned in an ordinary singleton may still be `Welcome`.
- A `@ConfigurationProperties` bean may be rebound when Spring Cloud processes `EnvironmentChangeEvent`.
- A `@RefreshScope` bean may have its target recreated on the next call after the target cache is evicted.

Therefore, the phrase "configuration has been refreshed" needs clarification: was the source updated, was Environment updated, was the event published, was the bean rebound, or was the target recreated?

## 3. How Do Environment and PropertySource Work?

### 3.1. Environment Is a Lookup Layer

In Spring, `Environment` provides the ability to query properties and active profiles. It aggregates multiple `PropertySource` instances, each with its own name and data. A key may appear in multiple sources; the value is chosen according to the precedence order of sources in that environment.

Example:

~~~java
@Component
class EnvironmentInspector {
    private final Environment environment;

    EnvironmentInspector(Environment environment) {
        this.environment = environment;
    }

    String currentBanner() {
        return environment.getProperty("app.banner", "default");
    }
}
~~~

Each time `currentBanner()` is called, the method looks up the property from Environment at call time. If a managed PropertySource has changed its value, the next lookup can see the new value.

That differs from reading a property once and storing it in a field:

~~~java
@Component
class BannerSnapshot {
    private final String banner;

    BannerSnapshot(@Value("${app.banner:default}") String banner) {
        this.banner = banner;
    }

    String currentBanner() {
        return banner;
    }
}
~~~

`BannerSnapshot`'s constructor runs when the bean is created. The value injected then is stored in the `banner` field; Spring does not re-invoke the constructor just because Environment changed. This is an example of a **startup-time snapshot**.

### 3.2. PropertySource and Precedence Order

Common sources:

- Packaged configuration files such as `application.yml`.
- External configuration files and profile-specific files.
- Environment variables.
- JVM system properties.
- Command-line arguments.
- Integrated configuration sources, such as Config Server or custom sources.

Exact ordering depends on the Spring Boot version, startup method, and integration mechanism. Do not guess precedence from source names; when multiple sources declare the same key, check documentation for your version and measure the actual value.

You can think of some sources taking higher precedence than others. If `app.banner` appears in both the default file and the command line, the effective value can come from the command line. When a higher-precedence source is removed, lookup can fall back to a lower-precedence source that remains.

### 3.3. Changing Source Contents Differs from Changing the PropertySource Set

There are two distinct operations:

1. **Updating data inside a mutable PropertySource:** e.g., a managed map is updated.
2. **Replacing/adding/removing a PropertySource:** e.g., adding an override source at the front of the list.

Modifying a file on disk does not by default cause Spring Boot to watch the file and update the running Environment. An actual reload/config refresh mechanism is required to re-read new data and update sources in the application.

When a source changes, lookup results also depend on the source's position in the precedence list. Adding a new source at an inappropriate position can let the old value keep winning.

## 4. Why Do Ordinary Singleton Beans Not Change Automatically?

### 4.1. Dependency Injection Occurs at Bean Creation

For singleton beans, Spring typically creates the object once during the ApplicationContext lifecycle. `@Value` values, constructor arguments, or bound configuration are supplied to the bean at creation time.

Example:

~~~java
@Component
class GreetingService {
    private final String greeting;

    GreetingService(@Value("${app.greeting:Hello}") String greeting) {
        this.greeting = greeting;
    }

    String greet() {
        return greeting;
    }
}
~~~

After initialization, the `greeting` field retains the received value. If Environment changes from `Hello` to `Hi there`, calling `greet()` on this singleton can still return `Hello`.

This is not a bug in Environment. The object received a value and has no mechanism to mutate that field on its own.

### 4.2. Reading Approaches Behave Differently

| Usage | When Is the Value Read? | Sees New Environment Automatically? |
| --- | --- | --- |
| `environment.getProperty(key)` on each call | Each time the lookup method runs. | Possibly, if Environment/PropertySource was actually updated. |
| `@Value` into singleton field/constructor | When the bean is created. | Not automatically. |
| Regular `@ConfigurationProperties` bean | When the bean is initially bound. | Only updated if an appropriate rebinding mechanism runs. |
| `@RefreshScope` bean | When target is initialized; target is cached. | After refresh scope invalidates the target, the next call creates a new target. |

You can inject `Environment` into a bean and look up on every call, yet this is not always the best choice. It couples configuration lookup directly into business logic, makes consistency across multiple reads harder to control, and is harder to test than a strongly typed configuration object.

### 4.3. When Should You Use a Snapshot?

Snapshots are useful when a value is considered immutable for the process's lifetime, such as an operational constant that only changes on deploy/restart. They also prevent a single business operation from reading two different configuration values partway through.

If runtime updates are genuinely required, choose an explicit update mechanism and define when changes take effect, rather than expecting singletons to re-read automatically.

## 5. @ConfigurationProperties and Rebinding

### 5.1. Initial Binding

`@ConfigurationProperties` groups related keys into a typed object. Example:

~~~yaml
app:
  routing:
    primary-region: ap-southeast
    fallback-enabled: true
~~~

Mutable bean:

~~~java
@ConfigurationProperties(prefix = "app.routing")
public class RoutingProperties {
    private String primaryRegion;
    private boolean fallbackEnabled;

    public String getPrimaryRegion() {
        return primaryRegion;
    }

    public void setPrimaryRegion(String primaryRegion) {
        this.primaryRegion = primaryRegion;
    }

    public boolean isFallbackEnabled() {
        return fallbackEnabled;
    }

    public void setFallbackEnabled(boolean fallbackEnabled) {
        this.fallbackEnabled = fallbackEnabled;
    }
}
~~~

Register the bean using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(RoutingProperties.class)`, depending on application structure. Spring Boot Binder takes values from Environment and assigns them to the bean during binding.

### 5.2. EnvironmentChangeEvent

Spring Cloud Context listens for `EnvironmentChangeEvent`. When the event is published with a set of changed keys, standard behaviors include:

- Rebinding `@ConfigurationProperties` beans in the context.
- Updating log levels for keys under `logging.level.*`.

Therefore, with mutable `@ConfigurationProperties`, updating Environment and publishing the appropriate event can make the bean receive new values without restarting the entire ApplicationContext.

However, rebinding does not mean every bean in the application is updated. Singleton beans that only take `@Value` are not automatically rebound by this mechanism. Custom objects need their own event handling if required.

### 5.3. Rebinding Has Limitations

Several characteristics to remember:

- Rebinding a mutable configuration bean can update fields on **the same instance** rather than creating a new object.
- During an update, another thread may read the object while some fields have changed and others have not finished updating. Consider consistency and thread safety.
- Values removed from Environment may be reset to class-level defaults during rebinding per Spring Cloud's mechanism; check your version and object structure.
- Constructor-bound immutable configuration, including Java Records using constructor binding, cannot be refreshed via this rebinding mechanism in current Spring Cloud documentation.
- Nested objects, collections, and complex data types may have specific binding behaviors; do not assume updates are always atomic to all readers.

If the application needs consistent configuration as a single snapshot, consider `@RefreshScope` or designing an immutable snapshot replaced in a synchronized manner. Do not rely on mutable beans to update multiple interrelated properties without synchronization.

### 5.4. Verifying Rebinding

In applications with Actuator installed and the appropriate endpoint exposed, you can use `/actuator/configprops` to inspect values bound into configuration properties. The endpoint can expose sensitive details if sanitization/protection is not properly configured; enable it only in controlled environments and access scopes.

When Environment returns the new value yet `@ConfigurationProperties` remains stale, it may indicate that the event/rebinding has not run, the bean was not properly registered, or the bean type does not support rebinding.

## 6. @RefreshScope: Recreating Target Beans When Needed

### 6.1. How It Works

`@RefreshScope` provides a scoped proxy and a cache of initialized target beans. When the bean is first used, the target is created and cached in the scope. When the scope is refreshed, the corresponding target cache is invalidated. The next call through the proxy creates a new target, at which point dependencies/configuration are injected from the current Environment state.

Example:

~~~java
@Component
@RefreshScope
class DynamicGreetingService {
    private final String greeting;

    DynamicGreetingService(@Value("${app.greeting:Hello}") String greeting) {
        this.greeting = greeting;
    }

    String greet() {
        return greeting;
    }
}
~~~

Callers typically inject the proxy of `DynamicGreetingService`. After the target cache is cleared, callers continue invoking through the proxy; a new target is initialized with current configuration values.

### 6.2. Refresh Does Not Equal Restarting the Whole Application

When refreshing the scope:

1. The scoped target cache is cleared.
2. The proxy remains the object callers hold.
3. The next method call creates a new target.
4. The new target reads dependencies and properties at initialization time.

Not every singleton bean is recreated. Not every resource automatically closes and reopens cleanly. Dependencies holding connections, threads, schedulers, or external state need clear lifecycles to avoid resource leaks or mixing old/new configuration.

### 6.3. Placing Annotations in the Right Spot

`@RefreshScope` on one bean does not automatically make every bean that depends on it refresh-scoped. If another bean copied a value from the dependency into its own field at initialization, that field does not change just because the underlying dependency is refreshed.

Example:

- `DynamicGreetingService` is in refresh scope.
- `NotificationFacade` is a singleton and stores the greeting string in its constructor.
- Refreshing `DynamicGreetingService`'s target does not update the snapshot field inside `NotificationFacade`.

If the facade calls the method through the proxy whenever it needs the value, it can receive results from the new target. If the facade needs to rebuild internal state, it also needs an appropriate lifecycle mechanism or must be redesigned to avoid storing snapshots.

### 6.4. Not Every Bean Is Refreshable

Some beans have complex internal state or are marked non-refreshable. Spring Cloud documentation lists `spring.cloud.refresh.never-refreshable` and `spring.cloud.refresh.extra-refreshable` to control special cases. For instance, `HikariDataSource` is non-refreshable by default in current documentation; check your exact release train before altering this setting.

Do not put `@RefreshScope` on every bean. Evaluate:
- Does the bean genuinely need to change configuration while the process is running?
- Would restarting/rolling out instances be safer?
- Can a new target be created while in-flight requests are still using the old target?
- How are old resources closed and new resources initialized?
- Do any downstream dependencies retain old state?

## 7. Configuration Update and Refresh Workflow

A conceptual workflow:

~~~mermaid
sequenceDiagram
    participant Source as Config Source
    participant Env as Environment
    participant Refresher as Context Refresher
    participant Event as EnvironmentChangeEvent
    participant Props as ConfigurationProperties
    participant Scope as RefreshScope
    participant Caller as Application Caller

    Source->>Refresher: New configuration available
    Refresher->>Env: Update property sources
    Refresher->>Event: Publish changed keys
    Event->>Props: Rebind mutable properties
    Refresher->>Scope: Invalidate refresh targets
    Caller->>Scope: Invoke method via proxy
    Scope-->>Caller: Create / use new target
~~~

Key steps:

1. **Source configuration:** file, Config Server, or configuration store is updated.
2. **Load into Environment:** reload/refresh mechanism actually re-reads or updates property sources.
3. **Detect changed keys:** the system identifies which properties have different values.
4. **Publish event/rebind:** `@ConfigurationProperties` beans and loggers are updated per Spring Cloud's mechanism.
5. **Invalidate refresh scope:** target caches for `@RefreshScope` beans are cleared.
6. **Recreate on use:** a new target is initialized when the proxy receives its next call.
7. **Verify:** re-read values and verify business behavior.

If you only edit a file on disk without a reload mechanism, step 2 has not happened. If you only add a new PropertySource without running the refresh/rebind workflow, already-initialized beans may still hold old values.

## 8. Triggering Refresh via Spring Cloud Context and Actuator

Spring Cloud Context provides APIs and endpoints supporting refresh. Exact triggering mechanisms depend on dependencies and application version.

### 8.1. Actuator Refresh Endpoint

In applications with Spring Boot Actuator and appropriate Spring Cloud Context, the refresh endpoint can be exposed:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
~~~

Then, if the endpoint is enabled, exposed, and properly secured:

~~~bash
curl -X POST http://localhost:8080/actuator/refresh
~~~

This endpoint runs Spring Cloud's refresh workflow on the instance receiving the request, including updating configuration via context refresher and refreshing targets in refresh scope. It is not a full JVM restart command.

Do not assume this endpoint exists or is exposed by default. Check dependencies, management settings, security, and release train documentation. Do not expose the refresh endpoint publicly to the Internet; it is an operation that modifies runtime configuration.

### 8.2. Environment Endpoint Differs from Refresh Endpoint

Some Spring Boot Actuator versions support `/actuator/env` for viewing Environment; POST operations updating Environment may require dedicated configuration and restrict allowed keys. When enabled, Spring Cloud can process `EnvironmentChangeEvent` and rebind configuration properties.

Distinguish:

| Endpoint | Primary Role | Things to Verify |
| --- | --- | --- |
| `/actuator/env` | View Environment; POST updates properties if enabled/configured. | Allowed keys, property sources, event/rebind, and access permissions. |
| `/actuator/refresh` | Runs Spring Cloud Context's refresh workflow. | Were config sources reloaded and was refresh scope invalidated? |
| `/actuator/restart` | Closes and restarts ApplicationContext when endpoint/capability is enabled. | This is a different lifecycle from refreshing targets; not enabled by default. |

The `env` POST endpoint is not a safe replacement for a centralized configuration management system. If used, require an allowlist of updatable properties, authentication/authorization, audit logging, and network restrictions.

### 8.3. Refresh via In-Application API

In Java code, Spring Cloud Context provides the `ContextRefresher` abstraction for the refresh workflow. An illustrative invocation example:

~~~java
@Component
class RefreshCoordinator {
    private final ContextRefresher contextRefresher;

    RefreshCoordinator(ContextRefresher contextRefresher) {
        this.contextRefresher = contextRefresher;
    }

    Set<String> refreshConfiguration() {
        return contextRefresher.refresh();
    }
}
~~~

Specific APIs and bean availability depend on the Spring Cloud Context module and version in use. Do not call refresh arbitrarily from every user request; control permissions, frequency, configuration sources, and concurrent behavior.

## 9. Refreshing One Instance Does Not Refresh the Entire Cluster

Each instance has its own ApplicationContext, Environment, beans, and refresh scope. If there are 5 instances and you only send `POST /actuator/refresh` to one instance, only that instance refreshes via that endpoint.

Spring Cloud Config Client does not continuously poll by default to detect every change in Environment. For scaled-out applications, a common approach is using a broadcast mechanism such as **Spring Cloud Bus** to deliver refresh events to multiple instances. Event delivery and broadcast scope must be configured, secured, and verified.

### 9.1. Example of Inconsistent State

Suppose `app.routing.mode` changes from `legacy` to `safe`:

| Instance | Environment | Ordinary Snapshotted Bean | Refresh Target After Next Call |
| --- | --- | --- | --- |
| `order-1` | `safe` | May still be `legacy` | New target can receive `safe` |
| `order-2` | `legacy` | `legacy` | Still receives `legacy` |
| `order-3` | `safe` | May still be `legacy` | New target can receive `safe` |

The table is an illustrative scenario. It shows that you must verify **per instance**:
- Environment revision/value.
- When the event was received.
- Rebinding status.
- Whether refresh targets have been invalidated and recreated.
- Which instance is serving requests.

If a configuration change affects inter-service contracts, an inconsistent cluster state can cause errors. Controlled rollouts, backward-compatible configuration, or a synchronized coordination process are required.

### 9.2. Do Not Poll Uncontrolledly from Every Instance

If every instance polls Config Server at high frequency, the system can generate unnecessary load and update timings will still be unaligned. At multi-instance scale, event broadcasting or deploying changes via controlled releases/rollouts is usually easier to manage. Choose based on acceptable latency, messaging reliability, and observability.

## 10. Testing the Difference Between Environment and Beans

A good test should separately verify:
- The value returned by Environment.
- The value held in a singleton snapshot.
- The value in a mutable `@ConfigurationProperties` bean.
- The value returned by a `@RefreshScope` proxy after the target is recreated.

### 10.1. Scenario Table

| Scenario | Environment | Singleton `@Value` | Mutable `@ConfigurationProperties` | `@RefreshScope` |
| --- | --- | --- | --- | --- |
| Initial startup | Value A | A | A | Initial target receives A |
| Add override B without refresh/rebind | Lookup can see B | Still A | Still A | Current cached target still A |
| Publish event/rebind per appropriate mechanism | B | Still A | Can be rebound to B | Target cache not necessarily cleared if only event published without full refresh workflow |
| Run full refresh workflow | B | Still A | Processed via event/rebind | Target cache invalidated; next call creates target B |

The table describes typical behavior of Spring Cloud Context mechanisms, not a guarantee for every bean type or every version. When writing tests, clearly identify which operations only update Environment, which publish events, and which invoke the full refresh workflow.

### 10.2. Thought-Experiment Test

Suppose `app.greeting` starts as `Hello`, and is later updated to `Hi there`.

| Step | Action | Expected Observation |
| --- | --- | --- |
| 1 | Start context with `app.greeting=Hello`. | Environment, singleton snapshot, and refresh bean all see Hello initially. |
| 2 | Add PropertySource override with `app.greeting=Hi there`. | Environment lookup sees new value; singleton still holds Hello. |
| 3 | Rebind mutable `@ConfigurationProperties` via event. | Properties object reflects new value per rebinder mechanism. |
| 4 | Run refresh scope. | Old target invalidated; next proxy call creates new target with new value. |
| 5 | Call singleton snapshot again. | Still Hello unless it has a custom update mechanism. |
| 6 | Call EnvironmentInspector again. | Returns Hi there if the new PropertySource still has high precedence. |

You can use `MapPropertySource` in tests to create an override source, ensuring the source is added to the right `MutablePropertySources` at the right precedence position. To test the end-to-end Spring Cloud workflow, prefer the appropriate refresh API or endpoint rather than manually simulating a partial event and assuming full refresh works.

### 10.3. Assertions to Include

- `Environment.getProperty(key)` returns the new value after the source is updated.
- Singletons using `@Value` do not change on their own without a special mechanism.
- Mutable `@ConfigurationProperties` are rebound when the event and rebinder actually run.
- Constructor-bound/record configs are not treated as refreshable.
- Scoped proxies continue to be used by callers, while targets are recreated after scope refresh.
- Beans depending on a refresh target do not automatically update their own snapshot state.
- After refresh, the new values are actually used in business behavior.
- With multiple instances, each instance is verified independently.

## 11. Designing Safe Configuration Updates

Refresh can directly impact resources and business behavior. It must be managed as an operational action.

### 11.1. Classifying Configuration

| Group | Examples | Typically Suitable Strategy |
| --- | --- | --- |
| **Startup configuration** | Port, SSL keystore, components built at startup. | Controlled restart/rollout. |
| **Simple runtime configuration** | Feature flags, threshold limits, display messages. | Environment update + rebind or refresh scope depending on usage. |
| **Resource configuration** | Database URL, pool, connection factory. | Evaluate lifecycle, closing/opening resources, request draining, and implementation refreshability. |
| **Sensitive configuration** | Credentials, signing keys, tokens. | Secret management, planned rotation, restricted logs and read permissions. |
| **Cross-service configuration** | Service names, endpoints, routing modes, protocols. | Backward compatibility, rollout/broadcast, cluster-wide verification. |

Not every property should change at runtime. For ports, listeners, security material, or configuration read during infrastructure setup, a restart can be safer and more predictable.

### 11.2. Avoiding Half-Old, Half-New State

If a business operation depends on three interrelated values, rebinding individual fields on a mutable bean can expose an intermediate state to concurrent readers. Ways to reduce risk:

- Use an immutable configuration snapshot and swap the entire snapshot via a synchronized mechanism.
- Use a refresh-scoped target to replace the cached target when object recreation is needed.
- Version/revision configuration changes and check the revision before executing business logic.
- Break rollouts into backward-compatible steps.
- Do not perform refresh while resources lack a clear lifecycle.

`@RefreshScope` manages the target cache for annotated beans, yet it does not turn system-wide changes into an atomic transaction. Different instances can still refresh at different times.

### 11.3. Securing Refresh Operations

- Expose the refresh endpoint only on necessary administrative networks.
- Enforce authentication and authorization.
- Log audit events: requester, timestamp, instance, configuration revision, and outcome.
- Rate-limit refreshes to avoid continuous refreshes recreating resources.
- Validate new configuration before broadcasting.
- Have a rollback plan if a new target fails to initialize.
- Do not log secret values when recording changes.

## 12. Common Pitfalls and Diagnostics

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Environment sees new value, yet bean method returns old value. | Bean stored a snapshot via `@Value` or constructor. | Check when the bean was created; use rebinding/refresh scope if appropriate. |
| Config file changed, yet Environment is still old. | Source not reloaded or Config Client did not fetch new config. | Check Config Server/source, reload mechanism, profiles, and property precedence. |
| `@ConfigurationProperties` did not update. | Bean not registered/bound, event not published, or binding style does not support refresh. | Check scan/enable, event, Actuator configprops, and constructor-binding type. |
| Record configuration unchanged after refresh. | Constructor-bound immutable beans do not support rebinding via this mechanism. | Use a suitable mutable bean or recreate bean/context by design. |
| `@RefreshScope` bean still returns old value. | Refresh endpoint not called, endpoint not exposed, target not in scope, or source unchanged. | Check dependencies, proxy, scope cache, and Environment before/after refresh. |
| A dependency still retains old configuration. | Dependency/facade snapshotted the value from another bean. | Identify which bean needs a proxy or needs to be recreated. |
| Some instances use new config, others use old config. | Refresh reached only one instance or broadcast did not complete. | Record revision and refresh timestamp on each instance. |
| Refresh causes temporary request errors. | New target fails to initialize or old/new resource lifecycles conflict. | Check refresh scope health, exceptions, pools, and dependency state. |
| Rebinding causes unexpected intermediate values. | Mutable bean fields updated while another thread reads them. | Check concurrency; consider immutable snapshot or refresh-scoped bean. |
| Calling `/actuator/refresh` returns 404/401/403. | Missing dependency, endpoint not exposed, or security denied access. | Check Actuator, Spring Cloud Context, endpoint exposure, and access permissions. |

## 13. Hands-On Lab: Environment, Singleton, and Refresh Scope

### 13.1. Preparation

Create a Spring Boot application with Spring Cloud Context compatible with your chosen release train. Add Actuator if you want to use management endpoints in the lab. Initial configuration:

~~~yaml
app:
  greeting: "Hello"
  routing:
    mode: "legacy"

management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
~~~

The exposure configuration above is for the lab only; production must restrict endpoints and secure access.

Create three beans:

1. `EnvironmentInspector`: calls `environment.getProperty("app.greeting")` on every request.
2. `GreetingSnapshot`: injects `@Value` in the constructor and stores it in a field.
3. `DynamicGreetingService`: `@RefreshScope`, injects the same property in the constructor.

A lab controller can call all three beans and return the results for comparison. Only expose this endpoint in a test environment; do not use it to display sensitive configuration.

### 13.2. Experimentation

1. Start the application with `app.greeting=Hello`.
2. Call the lab endpoint and record the three values.
3. Update the property source via the configuration management mechanism in use, such as Config Server or a controlled test operation.
4. Verify that Environment looks up the new value.
5. Before refreshing, call the endpoint again and observe the singleton snapshot and cached refresh target.
6. Trigger the supported refresh workflow for the lab instance.
7. Call the endpoint again; observe the singleton snapshot, Environment, and refresh target.
8. If using multiple instances, repeat the check on each instance and record revisions.
9. Try an invalid configuration value to observe binding/target initialization errors.
10. Restore the original configuration and confirm the application operates stably.

### 13.3. Results Table

| Milestone | Environment | Singleton snapshot | Refresh target | Result |
| --- | --- | --- | --- | --- |
| Startup | Hello | Hello | Hello | Self-recorded |
| Source changed, not refreshed yet | Hi there | Hello | May still be Hello | Self-recorded |
| After full refresh | Hi there | Hello | Hi there when new target is called | Self-recorded |
| Instance did not receive event | Old value | Old value | Old target | Self-recorded |

The table reflects expectations for the described bean structure. Actual results must be verified per version and source-update mechanism. If a singleton is designed to look up Environment on every call, that singleton's result will differ from the snapshot example.

## 14. Completion Checklist

- [ ] Distinguish configuration sources, Environment, and initialized beans.
- [ ] Explain PropertySource precedence order and how to verify the effective value.
- [ ] Explain why `@Value` in a singleton does not auto-update when Environment changes.
- [ ] Distinguish per-call Environment lookup from a snapshot stored in a field.
- [ ] Use `@ConfigurationProperties` and know the conditions for rebinding.
- [ ] Understand the role of `EnvironmentChangeEvent` for configuration properties and logging.
- [ ] Know the limitations of mutable rebinding and constructor-bound/Record types.
- [ ] Explain scoped proxies, target caches, and when `@RefreshScope` targets are recreated.
- [ ] Distinguish refreshing beans from restarting the entire ApplicationContext.
- [ ] Verify the refresh endpoint/`ContextRefresher` and secure refresh operations.
- [ ] Verify Environment/bean state on each instance in a cluster.
- [ ] Have tests proving values before/after source updates, events, and refreshes.
- [ ] Have rollback, audit, and sensitive-configuration handling strategies.

**References to cross-check during implementation:** Spring Cloud Commons Reference on Application Context Services, Environment Changes, Refresh Scope, and configuration properties; Spring Boot Reference on Environment, PropertySource, Actuator, and externalized configuration. APIs, endpoints, refreshable bean types, and rebinding behaviors can vary by release train, so check documentation for your application's exact version.
