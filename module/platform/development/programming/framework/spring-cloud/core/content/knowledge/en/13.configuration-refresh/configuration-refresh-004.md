# The Role of ContextRefresher in the Refresh Process

> **Chapter:** Configuration Refresh  
> **Module:** SPRING_CLOUD_CORE

In a Spring Cloud application, changing a value in Config Server or an external configuration source does not cause running beans to automatically receive the new value. The application needs a workflow to re-read configuration sources, update `Environment`, determine which properties changed, and notify components that must react. **`ContextRefresher`** is the key coordinator in that workflow.

`ContextRefresher` belongs to Spring Cloud Context. It connects updating the configuration environment with configuration change events and the `RefreshScope` lifecycle. Understanding this role properly helps distinguish three actions often grouped together as "refresh": reloading configuration, notifying changed properties, and recreating targets of refresh-scoped beans.

## 1. Where Does ContextRefresher Fit in the Architecture?

A Spring Boot application can receive configuration from many sources: `application.yml`, profile-specific files, environment variables, command-line arguments, Spring Cloud Config, or custom configuration sources. Spring puts these sources into `Environment` as `PropertySource` instances.

When a refresh is needed, the application must perform a sequence of tasks:

1. Record the current configuration state as a comparison baseline.
2. Reload or update property sources according to the active configuration mechanism.
3. Compare before and after values to find changed keys.
4. Publish an event so interested components can process those keys.
5. Invalidate targets managed by refresh scope so they can be recreated with the new configuration.

`ContextRefresher` coordinates this sequence. It is **not Config Server**, not a scheduler watching files, and it does not decide on its own when operators need a refresh.

~~~mermaid
flowchart TB
    A["Configuration source changes"] --> B["Trigger refresh"]
    B --> C["ContextRefresher"]
    C --> D["Snapshot current Environment state"]
    D --> E["Update / reload property sources"]
    E --> F["Compare before and after"]
    F --> G["EnvironmentChangeEvent"]
    G --> H["Listeners handle changed keys"]
    F --> I["RefreshScope.refreshAll()"]
    I --> J["Invalidate targets in refresh scope"]
    J --> K["Next invocation creates new target"]
~~~

This diagram is a conceptual model. Remote sources are reloaded by the specific implementation of Spring Cloud Config Client or the active configuration mechanism; which listeners and beans get updated depends on dependencies, versions, and how the application registers them.

## 2. What Does ContextRefresher Do?

In Spring Cloud Context, `ContextRefresher` provides the main operations to refresh the configuration environment. Common APIs include:

| Operation | Role |
| --- | --- |
| `refresh()` | Coordinates refreshing the environment and refreshing refresh scope; returns the set of keys identified as changed |
| `refreshEnvironment()` | Updates Environment, compares before/after states, and publishes `EnvironmentChangeEvent`; does not call `RefreshScope.refreshAll()` itself |
| `updateEnvironment()` | Extension point in concrete implementations to load/update configuration sources |

In many versions, `ContextRefresher` is a base class whose environment-updating method is supplied by concrete implementations. Spring Cloud Config Client or an integrated configuration mechanism determines how data is fetched again. Therefore, when reading source code or debugging, distinguish the coordinating API from the implementation responsible for loading sources.

### 2.1. Capturing State Before Updating

Before reloading configuration, the refresher collects existing properties from the Environment. This state serves as a baseline to determine which values changed.

Example before refresh:

~~~yaml
catalog:
  client:
    base-url: "https://catalog-v1.internal"
    read-timeout: 3s
    max-attempts: 2
~~~

After the configuration source is updated:

~~~yaml
catalog:
  client:
    base-url: "https://catalog-v2.internal"
    read-timeout: 2s
    max-attempts: 2
~~~

The keys with different values are:

- `catalog.client.base-url`
- `catalog.client.read-timeout`

The key `catalog.client.max-attempts` did not change. The returned key set helps listeners or operational tools know which properties were identified as different.

### 2.2. Updating the Environment

After capturing the old state, `ContextRefresher` invokes the implementation's environment update logic. Depending on the integration, that logic may rebuild the necessary bootstrap/configuration context, re-read Config Server, or reload configuration sources according to the supported mechanism.

The critical point is that **Environment must actually receive the new values**. Calling `RefreshScope.refreshAll()` alone does not fetch remote configuration. If the property source has not changed, the newly created target can still receive the old values.

### 2.3. Comparing and Returning Changed Keys

After Environment is updated, the refresher compares the before and after snapshots. The changed key set is typically represented as `Set<String>`.

Example result:

~~~text
[
  "catalog.client.base-url",
  "catalog.client.read-timeout"
]
~~~

This information is useful to:

- Check whether the refresh changed any configuration.
- Determine which listeners need to act.
- Log/emit metrics about changed keys without printing sensitive values.
- Write tests verifying the right properties were updated.

This key set is not a full copy of the new configuration, nor does it indicate that every bean has been recreated. It only describes properties identified as changed according to the implementation's comparison.

## 3. EnvironmentChangeEvent Notifies Configuration Changes

After determining the changed keys, the refresh workflow publishes `EnvironmentChangeEvent` in the ApplicationContext. The event carries the changed key set so listeners can react.

~~~java
import java.util.Set;

import org.springframework.cloud.context.environment.EnvironmentChangeEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationChangeLogger {

    @EventListener
    public void onEnvironmentChange(EnvironmentChangeEvent event) {
        Set<String> changedKeys = event.getKeys();

        // Log only key names; do not log configuration values or secrets.
        changedKeys.forEach(key ->
                System.out.println("Configuration changed: " + key));
    }
}
~~~

This is an example listener observing changes. In real systems, use a logger/metrics instead of `System.out`, and filter sensitive keys if property names themselves reveal internal information.

### 3.1. What Are the Event and Listener Responsible For?

`EnvironmentChangeEvent` indicates that the Environment has been updated and which keys changed. Listeners decide what to do with that information.

Some Spring Cloud components can listen to the event to:

- Rebind configuration beans with supported mechanisms.
- Update logging configuration.
- Perform internal actions tailored to specific properties.

Do not assume every singleton or every bean in the ApplicationContext is automatically recreated. A singleton bean holding a value in a field can still keep its old snapshot unless there is a corresponding rebind or refresh mechanism.

### 3.2. Rebinding @ConfigurationProperties Differs from Refresh Scope

The two mechanisms serve different purposes:

| Mechanism | What gets updated | How it works |
| --- | --- | --- |
| Configuration rebind | Beans managed by the rebinding mechanism and supporting updates | Listener handles the event and rebinds matching properties |
| Refresh scope | Targets of beans annotated with `@RefreshScope` | Target cache is invalidated; proxy creates/obtains a new target on next call |
| Ordinary singleton | Not recreated by default | Fields assigned in constructor can still hold old values |

Rebindability depends on bean type, binding style, and Spring Cloud/Spring Boot version. Immutable or constructor-bound configurations should not be assumed updatable via field mutation; choose bean recreation or design a refresh-scoped bean if runtime updates are required.

## 4. ContextRefresher Working with RefreshScope

`RefreshScope` manages targets of beans marked with `@RefreshScope`. Consumers typically interact with the bean through a scoped proxy. When refresh scope is refreshed, cached targets are discarded; the next call through the proxy creates a new target.

In the `ContextRefresher.refresh()` workflow, refreshing the scope usually runs after the Environment has been updated and the configuration change event has been published.

~~~mermaid
sequenceDiagram
    participant Trigger as Refresh endpoint / Bus
    participant Refresher as ContextRefresher
    participant Env as Environment
    participant Event as Event listeners
    participant Scope as RefreshScope
    participant Proxy as Scoped proxy
    participant Target as Target bean

    Trigger->>Refresher: refresh()
    Refresher->>Env: Read old snapshot
    Refresher->>Env: Load new configuration
    Refresher->>Refresher: Compute changed key set
    Refresher->>Event: Publish EnvironmentChangeEvent
    Refresher->>Scope: refreshAll()
    Scope->>Target: Destroy/invalidate cached target
    Note over Proxy,Target: Proxy and consumer singletons still exist
    Proxy->>Scope: Next invocation
    Scope->>Target: Create new target when needed
    Target-->>Proxy: New configuration values
~~~

Note the distinctions:

- `ContextRefresher` coordinates updating the Environment.
- `EnvironmentChangeEvent` notifies changed keys.
- `RefreshScope` manages target invalidation.
- The scoped proxy forwards calls to the current target.

`ContextRefresher` does not replace every singleton bean itself. Nor does it guarantee that an HTTP client or connection pool created from old configuration will update automatically unless that object itself is recreated or designed to read configuration dynamically.

## 5. Distinguishing refreshEnvironment() and refresh()

These two methods are easily confused because of their similar names.

### 5.1. Updating Only the Environment

`refreshEnvironment()` focuses on updating configuration sources, computing changed keys, and publishing `EnvironmentChangeEvent`.

Use this operation alone when you need to update the Environment and let listeners react via their own mechanisms. It is not equivalent to invalidating all refresh-scoped targets.

### 5.2. Full Refresh

`refresh()` coordinates updating the Environment, publishing the event, and refreshing the refresh scope. This is the operation normally used when the goal is for refresh-scoped beans to recreate their targets from the new configuration.

You can compare them as follows:

| Step | `refreshEnvironment()` | `refresh()` |
| --- | --- | --- |
| Update sources/Environment | Yes | Yes |
| Compare before/after keys | Yes | Yes |
| Publish `EnvironmentChangeEvent` | Yes | Yes |
| Call `RefreshScope.refreshAll()` | No | Yes |
| Return changed key set | Yes | Yes |

When calling `refresh()`, do not call `refreshEnvironment()` beforehand "just to be sure," as doing so can load configuration and publish events twice. Use the right API for your intent.

## 6. Who Triggers ContextRefresher?

`ContextRefresher` does not watch Config Server on its own. Another component must request the refresh.

### 6.1. Actuator Refresh Endpoint

When an application has Spring Cloud Context and the corresponding Actuator integration, `RefreshEndpoint` can provide a management endpoint, typically accessed via:

~~~http
POST /actuator/refresh
~~~

Example endpoint exposure configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - refresh
~~~

This configuration only illustrates exposing the endpoint; dependencies, versions, endpoint enablement, and base path can affect the actual URL. Do not expose the refresh endpoint publicly. Require authentication, authorization, network restrictions, and audit who requested the refresh.

### 6.2. Spring Cloud Bus

In a multi-instance system, calling the refresh endpoint on one instance usually refreshes only the instance receiving that request. To propagate the event to multiple instances, you can integrate Spring Cloud Bus.

A typical flow:

1. The central configuration source is updated.
2. An administrative action or Config Monitor publishes an event over the Bus.
3. Instances receive the corresponding refresh event.
4. A listener on each instance invokes the local refresh workflow.
5. Each instance updates its Environment and refreshes its own targets.

The Bus distributes the event; `ContextRefresher` still performs the configuration update inside each application context. Do not treat a single local call as proof that all replicas received the new configuration.

### 6.3. Calling from Internal Code

A management bean can inject `ContextRefresher` if the application has an appropriate implementation:

~~~java
import java.util.Set;

import org.springframework.cloud.context.refresh.ContextRefresher;
import org.springframework.stereotype.Service;

@Service
public class ConfigurationRefreshService {

    private final ContextRefresher contextRefresher;

    public ConfigurationRefreshService(ContextRefresher contextRefresher) {
        this.contextRefresher = contextRefresher;
    }

    public Set<String> refreshConfiguration() {
        return contextRefresher.refresh();
    }
}
~~~

This is an example of calling the API from an internal component. Do not casually expose a custom endpoint wrapping this method without access control, rate limiting, and auditing. In many applications, the Actuator endpoint or Bus already serves as the centrally managed trigger path.

## 7. ContextRefresher Is Not ApplicationContext.refresh()

The two API names look similar, but their responsibilities differ.

| API/concept | Meaning |
| --- | --- |
| `ContextRefresher.refresh()` | Updates current configuration, publishes events, and invalidates refresh scope |
| `ConfigurableApplicationContext.refresh()` | Initializes or refreshes the ApplicationContext according to the Spring container lifecycle |
| `RefreshScope.refreshAll()` | Invalidates cached targets in refresh scope |
| `EnvironmentChangeEvent` | Event notifying the changed configuration key set |

Do not call `ApplicationContext.refresh()` as a substitute for runtime configuration refresh. ApplicationContext lifecycle refresh is a container-level operation that can involve initializing beans and managing resources across the entire context; it is not Spring Cloud's standard property source update mechanism.

## 8. What Updates and What Does Not Update Automatically?

A refresh does not mean the entire application restarts. Results depend on how each bean is managed.

| Component | Behavior after refresh |
| --- | --- |
| Environment/property sources | Updated by the configuration loading implementation |
| Returned keys | Reflect properties identified as changed |
| EnvironmentChangeEvent listeners | Can process/rebind keys according to their responsibilities |
| `@RefreshScope` beans | Target cache is invalidated; recreated when invoked |
| Scoped proxy | Typically remains the reference held by consumers |
| Ordinary singleton | Not recreated by default |
| Field that copied a config value | Does not change automatically without an update mechanism |
| Previously created HTTP client/pool | Does not update automatically unless recreated or update-capable |
| Static fields | Do not change automatically just because Environment was updated |

For example, if a singleton constructs a `WebClient` in its constructor from a base URL, refreshing a bean holding the URL string does not automatically change the already created `WebClient`. You can place an appropriate factory/client in refresh scope or design the client to resolve the endpoint via a proxy at request time.

## 9. Error Handling and Operational Limits

Refresh modifies a running configuration, so clear policies are required.

### 9.1. Configuration Source Unreachable

If Config Server or a custom source does not respond:

- Set finite timeouts for configuration fetch requests.
- Decide whether that source is required or optional.
- If required, report errors clearly and do not silently apply invalid configuration.
- If fallback is allowed, document fallback values and observability clearly.
- Do not assume Environment is always atomically rolled back to the old snapshot if the source-update implementation fails mid-way; test the actual behavior of your version and configuration source.

### 9.2. Concurrent Refreshes

Some implementations synchronize refresh operations within a single refresher instance, but that does not create a distributed lock across replicas. The system still needs coordination if multiple nodes may receive events closely together.

Avoid triggering refresh continuously per request. Batch configuration changes, apply rate limits, and monitor completion time. If multiple refreshes overlap, targets may be invalidated repeatedly and cause initialization load spikes.

### 9.3. Requests Currently Using an Old Target

Refresh scope does not mean all running requests stop immediately. A request may have obtained a target before invalidation occurred. The executing object must finish or handle errors according to its policy. For clients holding connections, schedulers, or pools, proper destruction callbacks and graceful shutdown mechanisms are needed.

### 9.4. Overly Broad Refresh Scope

If too many beans are marked `@RefreshScope`, a single refresh can invalidate many targets at once. The next access can recreate multiple clients, caches, or resources, causing connection and latency spikes.

Only mark beans that can be safely recreated. Do not store long-lived business state inside a refresh-scoped target if that state must survive a refresh.

## 10. Testing the Role of ContextRefresher

Tests should be separated into layers so you know where an error lies.

### 10.1. Testing the Changed Key Set

Create a test configuration with initial values, update the configuration source in the way supported by your test implementation, and assert the refresher returns the changed keys. Do not inspect secret values in assertions or logs.

Example result assertion:

~~~java
Set<String> changedKeys = contextRefresher.refresh();

assertThat(changedKeys)
        .contains("catalog.client.base-url")
        .doesNotContain("catalog.client.max-attempts");
~~~

This assertion assumes the test fixture only changed the base URL; how the new property source is supplied depends on the Config Data or legacy bootstrap implementation under test.

### 10.2. Testing the Event

Register a test listener or use Spring's test event-recording mechanism to confirm `EnvironmentChangeEvent` was published and contains the right keys. Distinguish whether the event was published from whether a business listener handled it successfully.

### 10.3. Testing Refresh-Scoped Targets

After the Environment has the new values, invoke `refresh()` or the appropriate scope operation, then invoke the proxy. Confirm the new target reads the new configuration and the consumer singleton still exists.

### 10.4. Testing Per Instance

In a multi-replica environment, verify each instance:

- Did the instance receive the refresh event?
- Has the instance's Environment updated?
- Does the changed key set match expectations?
- Is the refresh-scoped target recreated on the next invocation?
- Do logs/metrics show errors or latency spikes?

An endpoint returning an HTTP success on one node is not sufficient to prove the entire cluster has refreshed.

## 11. Symptom-Based Troubleshooting Examples

| Symptom | Points to check |
| --- | --- |
| Config Server changed, but `Environment.getProperty()` is still old | Did the trigger run; did the implementation reload remote sources; are profile/label correct |
| Environment is new, but refresh-scoped bean still returns old value | Did `RefreshScope` invalidate the target; is the consumer calling through the proxy |
| `ContextRefresher.refresh()` returns an empty key set | Did values actually differ; were property sources updated; did the diff see the keys |
| Singleton still holds old endpoint | Did the singleton copy the URI into a field or create an immutable client from old values |
| One replica updated, another did not | Which node received the refresh endpoint call; did Bus/event distribute to all nodes |
| Refresh succeeded, but HTTP client still calls old host | Was the client recreated; does the client read the endpoint via a proxy at call time |
| Refresh causes increased latency | Were too many targets invalidated; is client/pool recreation causing load spikes |
| Broken configuration after refresh | Check validation, schema, timeouts, and source fallback behavior |

When investigating, record the refresh timestamp, instance ID, application name, profile, changed key set, and processing result. Do not log secret values or the entire Environment.

## 12. Recommended Refresh Workflow

In a Spring Cloud application, you can structure the workflow as follows:

1. **Update source:** change configuration in Config Server or the managed configuration source.
2. **Trigger:** call the secured management endpoint or publish an event through Spring Cloud Bus.
3. **Reload:** the appropriate implementation updates property sources in Environment.
4. **Compare:** ContextRefresher identifies changed keys.
5. **Notify:** publish EnvironmentChangeEvent so appropriate listeners handle it.
6. **Invalidate targets:** refresh scope evicts cached targets.
7. **Recreate on demand:** the next call through the scoped proxy creates a new target.
8. **Verify:** check keys, beans, individual replicas, logs, and metrics.
9. **Recover:** if the new configuration is invalid, apply the rollback procedure or release a fix configuration; do not assume refresh rolls back automatically.

You should test this workflow in staging with at least one observable endpoint/timeout change. Also test behavior when Config Server is unreachable and when a replica misses an event.

## 13. Key Points to Remember

`ContextRefresher` is the **coordinator of the configuration refresh workflow** in Spring Cloud Context. It coordinates updating the Environment, comparing before/after properties, publishing `EnvironmentChangeEvent`, and refreshing `RefreshScope` when using `refresh()`. It does not watch Config Server itself, does not distribute events to every replica on its own, and does not restart the entire ApplicationContext.

For refresh to work properly, ensure configuration sources are reloaded, listeners handle changed keys properly, beans needing recreation are placed in refresh scope, and consumers continue calling through scoped proxies. Clearly distinguishing Environment refresh, event rebinding, and target invalidation is the foundation for designing runtime configuration that is observable, testable, and safe to operate in **SPRING_CLOUD_CORE**.
