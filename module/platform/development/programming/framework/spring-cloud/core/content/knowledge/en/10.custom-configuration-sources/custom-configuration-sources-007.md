# Naming Sources Stably and Controlling Precedence

This lesson belongs to the **Custom Configuration Sources** chapter of the **SPRING_CLOUD_CORE** module. When an application needs to retrieve configuration from a source outside Spring Boot's default mechanisms—such as tenant settings, feature policies, an internal secret/configuration service, or data generated during startup—we can bring that data into Spring's `Environment` via a `PropertySource`.

Adding a configuration source is not merely placing a map into the Environment. Two decisions directly affect application behavior:

- **Source name (`PropertySource` name):** a stable identifier for managing, replacing, comparing, and diagnosing sources.
- **Position in the source list:** determines which source wins when multiple sources declare the same property.

Using unstable names or adding a source in an inappropriate position can cause configuration to be unexpectedly overridden, dropped during Environment merging, or unrecognized during refresh. This lesson focuses on designing and verifying these two decisions in Spring Framework, Spring Boot, and Spring Cloud Context.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the structure and role of `PropertySource` in `Environment`.
2. Give sources stable, unique, and scope-meaningful names.
3. Control precedence using `MutablePropertySources`.
4. Distinguish `addFirst`, `addLast`, `addBefore`, `addAfter`, `replace`, and `remove`.
5. Understand what happens when two sources share the same name and when a source contains keys overlapping with another source.
6. Choose the right registration timing using `EnvironmentPostProcessor`, `ApplicationContextInitializer`, or `@PropertySource`.
7. Update custom configuration sources safely while the application is running.
8. Test source order, name collisions, effective values, and refresh impact.
9. Avoid accidentally overriding system settings, leaking secrets, or calling remote sources excessively.

## 2. What Is a PropertySource?

Spring's `Environment` holds an ordered list of `PropertySource` instances. Each `PropertySource` represents a data source capable of returning a value for a given property name.

For example, sources may come from:

- Spring Boot configuration files such as `application.yml`.
- Environment variables and JVM system properties.
- Command-line arguments.
- A map created by the application.
- An external file loaded programmatically.
- Configuration from Spring Cloud Config or another configuration system.
- A dynamic source supplied by the application.

A `PropertySource` has two key attributes: **name** and **source**. Name is the source's identifier in the list. Source is the underlying data object that `PropertySource` uses for lookups.

~~~mermaid
flowchart TD
    APP["Application / @ConfigurationProperties / @Value"] --> ENV["Spring Environment"]
    ENV --> LIST["MutablePropertySources: ordered list"]
    LIST --> P1["commandLineArgs"]
    LIST --> P2["systemProperties"]
    LIST --> P3["custom-tenant-policy"]
    LIST --> P4["applicationConfig"]
    P1 --> RESOLVE["Property resolution: highest-precedence source with a value"]
    P2 --> RESOLVE
    P3 --> RESOLVE
    P4 --> RESOLVE
~~~

The diagram only illustrates an ordered list. The actual order of default sources depends on the Spring Boot version, application type, and how it is started.

### 2.1. Example with MapPropertySource

Spring provides `MapPropertySource` to wrap a map:

~~~java
Map<String, Object> values = Map.of(
    "app.region", "ap-southeast",
    "app.routing.timeout", "800ms"
);

PropertySource<?> source =
    new MapPropertySource("custom-routing-defaults", values);
~~~

- `custom-routing-defaults` is the source name.
- `values` is the data.
- `app.region` and `app.routing.timeout` are the property keys.

The source name is not a prefix for property keys. Renaming the source does not rename the properties inside the map.

### 2.2. A Key Can Exist in Multiple Sources

Suppose two differently named sources both contain `app.region`:

| Source | Value |
| --- | --- |
| `custom-routing-defaults` | `ap-southeast` |
| `applicationConfig: [classpath:/application.yml]` | `eu-west` |

Which value is chosen depends on the two sources' positions in the list. Spring searches from higher-precedence sources to lower-precedence ones; the first source returning a non-`null` value wins.

This is a rule based on **order**, not source name. The source name aids management and identification; source position determines precedence.

## 3. PropertySource Names Must Be Stable

### 3.1. Why Do Names Matter?

The `PropertySource` name identifies the source inside `MutablePropertySources`. Many source-management operations locate a source by name, such as `replace(name, source)`, `remove(name)`, `addBefore(relativeName, source)`, and `addAfter(relativeName, source)`.

A stable name helps:

- Replace the right source when reloading configuration.
- Avoid creating duplicate copies of the same source across repeated refreshes.
- Distinguish internal sources from sources created by Spring Boot/Spring Cloud.
- Diagnose ordering and which source supplies a value.
- Compare `PropertySource` entries across refreshes.
- Avoid name collisions when merging parent–child Environments.

Examples of meaningful names:

~~~text
platform-tenant-defaults
platform-tenant-overrides
company-feature-policy
remote-runtime-settings
secrets-from-vault
~~~

Names should describe the **owner and purpose** of the source. If a source holds per-tenant configuration, the tenant identifier can be included in the name when each tenant genuinely has its own source. Avoid embedding timestamps or random UUIDs into the name on every load.

### 3.2. Do Not Generate Random Names on Each Refresh

Anti-pattern to avoid:

~~~java
String name = "remote-config-" + UUID.randomUUID();
environment.getPropertySources().addFirst(
    new MapPropertySource(name, values)
);
~~~

Each execution of this code creates a new source. After several refreshes, the list accumulates multiple sources with the same purpose. Older sources may remain in the Environment and continue beating the newer source depending on position.

Use a stable constant instead:

~~~java
static final String SOURCE_NAME = "platform-remote-config";
~~~

When new data arrives, replace the source with that name or update a clearly managed data snapshot. Do not add a new source merely to represent a new data version.

### 3.3. Names Must Be Unique Within a MutablePropertySources

Within a `PropertySource` list, the name is the identifier. Two sources with the same name are not treated as two independent sources that can coexist in that list. Add/replace operations are designed to manage sources by name.

Specifically, when a child Environment merges a parent Environment, a source with the same name in the child is kept while the identically named source from the parent is omitted from the child's list. The two sources are **not merged key-by-key**.

Therefore, if two components do not share the same owner or semantics, do not give them the same source name just because both are custom configuration.

### 3.4. Name by Role, Not by Deployment Location

Names like `/etc/app/config.yml` or `classpath:/custom.yml` tie the source to a deployment location. Switching from a file to Config Server forces the source name to change even though the source retains the same meaning.

If the goal is a logical source whose delivery mechanism may change, use a role-based name such as `platform-routing-policy`. For diagnostics, log additional metadata about backend type or revision while keeping the source name stable.

## 4. MutablePropertySources and Precedence

`ConfigurableEnvironment.getPropertySources()` returns a `MutablePropertySources` object. This is an ordered list allowing adding, replacing, moving, and removing `PropertySource` instances.

### 4.1. Core Operations

| API | Behavior | When to use |
| --- | --- | --- |
| `addFirst(source)` | Places the source at the front of the list, highest precedence. | Intentional default override. |
| `addLast(source)` | Places the source at the end of the list, lowest precedence. | Intentional fallback/default. |
| `addBefore(name, source)` | Places the source immediately before the named source. | Need insertion at a clear relative position. |
| `addAfter(name, source)` | Places the source immediately after the named source. | Need the source below a specific source yet above subsequent ones. |
| `replace(name, source)` | Replaces the existing source with a new source at the same position. | Updating data without changing precedence. |
| `remove(name)` | Removes the source by name and returns the removed source if present. | Retiring an expired configuration source. |

APIs that add a source by name can remove an existing source with the same name before inserting the new one, so one name does not create duplicate entries in the list. `replace` requires that a source with the target name already exists; inspect the list or handle the absent-source case before calling it.

### 4.2. addFirst: Highest Precedence

~~~java
ConfigurableEnvironment environment = ...;

Map<String, Object> values = Map.of(
    "app.feature.enabled", true
);

environment.getPropertySources().addFirst(
    new MapPropertySource("platform-feature-override", values)
);
~~~

This source is searched before all remaining sources. If it contains `app.feature.enabled`, its value overrides lower sources.

Use `addFirst` only when you want the source to hold very high override authority. If the source contains default data, placing it at the front can unintentionally override system properties, environment variables, or command-line arguments.

### 4.3. addLast: Lowest Fallback

~~~java
environment.getPropertySources().addLast(
    new MapPropertySource(
        "platform-safe-defaults",
        Map.of("app.routing.timeout", "1s")
    )
);
~~~

A source at the end only supplies a value when no higher-priority source returns that property. This is the right position for platform-provided defaults, if application policy allows.

### 4.4. addBefore and addAfter: Relative Control

~~~java
MutablePropertySources sources = environment.getPropertySources();

sources.addAfter(
    StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME,
    new MapPropertySource("platform-runtime-settings", values)
);
~~~

This snippet places the source right after the environment variables source. As a result, system environment variables have higher precedence than the custom source, while the custom source takes precedence over sources following it.

`addBefore` works similarly but places the source before the reference source.

The reference name must exist. Otherwise, the operation may throw an exception. Do not hard-code Spring Boot source names without checking the version and Environment type; some web applications add specialized sources. When relying on a relative position, inspect the current list and write tests for the expected structure.

### 4.5. replace: Replace Content, Preserve Position

~~~java
MutablePropertySources sources = environment.getPropertySources();

PropertySource<?> replacement =
    new MapPropertySource("platform-runtime-settings", newValues);

sources.replace("platform-runtime-settings", replacement);
~~~

If the source exists, the new source is placed at the previous position. This is the right approach when updating data while preserving designed precedence.

Do not use `remove` followed by `addFirst` if the goal is merely updating content; doing so can accidentally alter precedence.

### 4.6. Inspecting Actual Order

You can print source names in order:

~~~java
environment.getPropertySources().forEach(source ->
    System.out.println(source.getName())
);
~~~

This output is useful in development environments. In production, avoid logging entire source contents since they may hold secrets. When observability is needed, log source names, types, order, and non-sensitive revisions.

## 5. Null, Empty Values, and Precedence

A `PropertySource` returns `null` when it does not supply a value for a key. In that case, the resolver continues searching lower-priority sources.

An empty string `""` is a non-null value. It can override a lower-priority value. Consequently, an empty-string override can cause the application to receive an empty string rather than falling back.

Example:

| Higher-priority source | Lower-priority source | Lookup result |
| --- | --- | --- |
| Key absent (null) | `ap-southeast` | `ap-southeast` |
| `""` | `ap-southeast` | Empty string |
| `eu-west` | `ap-southeast` | `eu-west` |

For boolean, numeric, or duration settings, type conversion happens after the resolver finds a value. An empty or malformed value can cause a binding/conversion error instead of automatically falling back to a lower source.

If a source intends to signify "not configured", return `null` for that key or omit the key from the map. Never use an empty string as a fallback marker unless the application explicitly defines that semantics.

## 6. Registering a Custom PropertySource at the Right Time

Position and registration timing matter equally. If a property is needed before the `ApplicationContext` is created, the source must be added to `Environment` early enough.

### 6.1. EnvironmentPostProcessor

`EnvironmentPostProcessor` is Spring Boot's extension point for customizing `Environment` during application preparation, before the context is refreshed. This is the right choice when a custom source must participate in early configuration.

Example:

~~~java
public final class PlatformDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    public static final String SOURCE_NAME = "platform-runtime-defaults";

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        Map<String, Object> values = new LinkedHashMap<>();
        values.put("app.routing.timeout", "800ms");
        values.put("app.routing.strategy", "round-robin");

        PropertySource<?> source =
                new MapPropertySource(SOURCE_NAME, values);

        MutablePropertySources sources = environment.getPropertySources();

        if (sources.contains(SOURCE_NAME)) {
            sources.replace(SOURCE_NAME, source);
        } else {
            sources.addAfter(
                StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME,
                source
            );
        }
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
~~~

The example places the source after system environment so system environment can still override it. The order of other `EnvironmentPostProcessor` implementations and available sources depends on the Boot version. If the application needs to insert after a specific source, verify that source exists in the real environment.

Register the processor in:

~~~text
META-INF/spring.factories
~~~

Contents:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.config.PlatformDefaultsEnvironmentPostProcessor
~~~

The class name must match the actual package. `EnvironmentPostProcessor` must be on the classpath when Spring Boot starts. Check the extension registration mechanism for the exact Boot version your project uses.

**Note on order:** `Ordered.LOWEST_PRECEDENCE` only controls processor execution order relative to other processors. It does not determine `PropertySource` precedence by itself. Precedence is still decided by `addAfter` or operations on `MutablePropertySources`.

### 6.2. ApplicationContextInitializer

`ApplicationContextInitializer` runs on the context before the context is refreshed. It fits when a source must be added before beans are instantiated, without necessarily participating in the earliest Config Data processing phase.

Example:

~~~java
public class PlatformContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        Map<String, Object> values = Map.of(
            "app.tenant.mode", "standard"
        );

        context.getEnvironment()
            .getPropertySources()
            .addLast(new MapPropertySource("platform-tenant-defaults", values));
    }
}
~~~

You can register the initializer via `SpringApplication.addInitializers` or an appropriate bootstrap configuration mechanism. Ensure the initializer is registered before the context refreshes.

If a property is required to determine Config Data locations, profiles, or early bootstrap steps, an initializer may run too late. In that case, use an `EnvironmentPostProcessor` or the appropriate Config Data extension point.

### 6.3. @PropertySource

`@PropertySource` can add properties files to `Environment` while processing configuration classes:

~~~java
@Configuration
@PropertySource(
    name = "platform-feature-defaults",
    value = "classpath:platform-feature-defaults.properties"
)
class PlatformFeatureConfiguration {
}
~~~

Example file:

~~~properties
app.feature.enabled=true
app.feature.rollout-percent=10
~~~

`@PropertySource` is convenient for static classpath file sources. However, it is processed during configuration registration—later than properties needed during early bootstrap, such as settings controlling Config Data loading. If multiple `@PropertySource` annotations are discovered via component scanning, ordering can become hard to predict; do not rely on it for complex precedence rules when order is critical.

By default, `@PropertySource` suits properties/XML supported by the default factory. To load YAML or custom formats, supply a matching `PropertySourceFactory` or use the appropriate Config Data mechanism.

### 6.4. Comparing Extension Points

| Mechanism | Timing | Suitable when |
| --- | --- | --- |
| `EnvironmentPostProcessor` | During Spring Boot Environment preparation. | Source is needed early, before ApplicationContext is refreshed. |
| `ApplicationContextInitializer` | After context is created, before refresh. | Source is needed before beans initialize, without needing early Config Data hooks. |
| `@PropertySource` | When configuration classes are processed. | Simple classpath configuration file tied to a Java configuration class. |
| Config Data resolver/loader | Inside Boot's Config Data pipeline. | Custom configuration format or protocol needing integration as a Config Data location. |

Choose the extension point based on when properties are needed, not simply by code brevity.

## 7. Integrating Dynamic Sources and Updating Configuration

A custom `PropertySource` can wrap data that changes over time. Two design patterns are common.

### 7.1. Source Holding an Immutable Snapshot

Whenever new configuration arrives, build a new map and replace the source:

~~~java
Map<String, Object> nextValues = loadValidatedValues();

PropertySource<?> replacement =
    new MapPropertySource(SOURCE_NAME, Map.copyOf(nextValues));

MutablePropertySources sources = environment.getPropertySources();

if (sources.contains(SOURCE_NAME)) {
    sources.replace(SOURCE_NAME, replacement);
} else {
    sources.addAfter(
        StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME,
        replacement
    );
}
~~~

Advantages:

- New data is validated before publication.
- The old source stays intact until the new source is ready.
- The stable source name preserves precedence position on `replace`.
- Revisions can easily be attached to logs or separate metadata.

`Map.copyOf` forbids null keys and null values. If data may contain nulls, validate it or use a suitable snapshot structure.

### 7.2. Dynamic Source Reading from a Provider

You can subclass `PropertySource` to query a provider:

~~~java
public final class RuntimePolicyPropertySource
        extends PropertySource<RuntimePolicyProvider> {

    public RuntimePolicyPropertySource(RuntimePolicyProvider provider) {
        super("platform-runtime-policy", provider);
    }

    @Override
    public Object getProperty(String name) {
        return getSource().find(name);
    }
}
~~~

`RuntimePolicyProvider` is an application-defined interface that can return data from a cache or internal snapshot.

Do not call HTTP/Config Server directly on every `getProperty` if that call has latency or can fail. Binders, placeholder resolution, and framework components may look up properties repeatedly during startup. A slow or network-dependent `PropertySource` makes startup unpredictable.

When using a remote source:

- Have explicit caching and timeouts.
- Maintain a last-known-good state if policy permits.
- Validate data before publishing.
- Track a revision/version for comparison.
- Have a refresh and error-handling mechanism.
- Never log sensitive contents.

### 7.3. Updating Multiple Keys Atomically as a Snapshot

Suppose a routing policy has three related properties:

~~~yaml
app:
  routing:
    mode: weighted
    primary-region: ap-southeast
    fallback-region: ap-northeast
~~~

Do not mutate individual keys in a shared map while concurrent requests may be reading. One request might observe the new `mode` alongside the old `region`.

Instead, build a complete snapshot, validate cross-key relationships, and then replace the source. If objects already consumed by beans need updating, define the appropriate rebinding or refresh scope mechanism. Replacing a `PropertySource` does not automatically update every singleton that already injected values earlier.

## 8. Relationship with Spring Cloud Context and Refresh

Spring Cloud Context provides mechanisms to update the `Environment` and beans when configuration changes. However, a custom `PropertySource` must integrate properly into that workflow.

### 8.1. Stable Names Help Compare Sources Across Refreshes

The refresh workflow typically needs to compare configuration values before and after reloading. A stable source name helps both the framework and operators match the corresponding source across two reads.

If a source gets a random name on every refresh:
- It is hard to identify which source is the new version of an older source.
- Duplicate-purpose sources accumulate easily.
- It is hard to diagnose whether a key changed because of data or source ordering.
- Comparing sources and values becomes confusing.

### 8.2. Replacing a PropertySource Does Not Automatically Refresh Beans

After replacing a source:

- `Environment.getProperty(key)` can return the new value.
- Singleton beans that received `@Value` via constructor may still hold the old value.
- `@ConfigurationProperties` needs the appropriate rebinding mechanism.
- `@RefreshScope` beans need their target cache invalidated so the next call creates a new target.

Therefore, clarify the update goal. Simply replacing a `PropertySource` does not mean the entire application is already using the new configuration.

### 8.3. Publishing Events and Refreshing

With Spring Cloud Context, the refresh workflow can publish `EnvironmentChangeEvent` to rebind `@ConfigurationProperties` beans and update logging levels. `@RefreshScope` manages its own target cache.

Do not publish events arbitrarily just to "refresh everything". When a custom source is updated, integrate into a controlled refresh workflow: replace the source, identify changed keys, publish events/refresh using the appropriate API, and then verify beans and business behavior.

With multiple instances, each instance maintains its own `Environment`. Refreshing one instance does not automatically update the others; a broadcast/rollout or distribution mechanism is required.

## 9. Practice: Adding a Source with Intentional Precedence

Suppose an application has three sources:

1. System environment: configuration supplied by the deployment platform.
2. Custom runtime defaults: default configuration supplied by the platform team.
3. Application config: configuration packaged inside the application.

Lab objectives:

- Environment variables are allowed to override the custom source.
- The custom source is allowed to override the default application file.
- Command-line/system properties still retain higher precedence than the custom source.
- The source has a stable name and appears only once.

### 9.1. Creating the Source

~~~java
public final class PlatformRuntimeDefaults {
    public static final String SOURCE_NAME = "platform-runtime-defaults";

    private PlatformRuntimeDefaults() {
    }

    public static PropertySource<?> create() {
        Map<String, Object> values = Map.of(
            "app.routing.timeout", "800ms",
            "app.routing.strategy", "round-robin"
        );

        return new MapPropertySource(SOURCE_NAME, values);
    }
}
~~~

### 9.2. Inserting the Source After System Environment

~~~java
MutablePropertySources sources = environment.getPropertySources();
PropertySource<?> source = PlatformRuntimeDefaults.create();

if (sources.contains(PlatformRuntimeDefaults.SOURCE_NAME)) {
    sources.replace(PlatformRuntimeDefaults.SOURCE_NAME, source);
} else {
    sources.addAfter(
        StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME,
        source
    );
}
~~~

Expected order in the relevant section:

~~~text
systemProperties / command-line sources (depending on Environment type)
systemEnvironment
platform-runtime-defaults
applicationConfig
lower-precedence sources
~~~

This is an illustrative diagram. A web application or another Spring Boot version may have additional sources and a different order; inspect the actual list before asserting.

### 9.3. Verifying with Marker Keys

In `application.yml`:

~~~yaml
app:
  routing:
    timeout: 2s
    strategy: random
~~~

When the custom source is added:

- `app.routing.timeout` is expected to be `800ms`.
- `app.routing.strategy` is expected to be `round-robin`.

If environment variable `APP_ROUTING_TIMEOUT=1500ms` is supplied, it has higher precedence than the custom source in the chosen layout and the expected result is `1500ms`.

If command-line argument `--app.routing.timeout=300ms` is supplied, the command-line value should win according to Spring Boot precedence.

Verify results using `Environment.getProperty` and bound bean behavior. Do not check only the custom source's map, because the map alone does not prove the source was inserted into `Environment` in the right order.

## 10. Testing Source Names and Precedence

### 10.1. Unit Test with StandardEnvironment

JUnit 5 example:

~~~java
@Test
void customSourceOverridesApplicationDefaultButNotSystemEnvironment() {
    ConfigurableEnvironment environment = new StandardEnvironment();

    environment.getPropertySources().addLast(
        new MapPropertySource("application-test", Map.of(
            "app.region", "default-region"
        ))
    );

    environment.getPropertySources().addAfter(
        StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME,
        new MapPropertySource("platform-runtime-defaults", Map.of(
            "app.region", "platform-region"
        ))
    );

    assertEquals("platform-region", environment.getProperty("app.region"));
}
~~~

The test above verifies that the custom source precedes the source added via `addLast`. It does not test the test machine's real environment variables; to test full precedence, create simulated `PropertySource` layers or run an integration test with a controlled environment.

### 10.2. Testing Duplicate Names

~~~java
@Test
void addingSourceWithSameNameDoesNotCreateDuplicateEntry() {
    ConfigurableEnvironment environment = new StandardEnvironment();

    environment.getPropertySources().addFirst(
        new MapPropertySource("platform-policy", Map.of("app.mode", "old"))
    );

    environment.getPropertySources().addFirst(
        new MapPropertySource("platform-policy", Map.of("app.mode", "new"))
    );

    long count = StreamSupport.stream(
        environment.getPropertySources().spliterator(), false
    ).filter(source -> source.getName().equals("platform-policy")).count();

    assertEquals(1, count);
    assertEquals("new", environment.getProperty("app.mode"));
}
~~~

This snippet illustrates the semantics of adding sources with the same name. When using `replace`, ensure the source already exists; test both the initial absent-source branch and the update-existing-source branch separately.

### 10.3. Testing Source Order Directly

You can assert relative ordering:

~~~java
List<String> names = StreamSupport.stream(
        environment.getPropertySources().spliterator(), false
    )
    .map(PropertySource::getName)
    .toList();

assertTrue(
    names.indexOf("platform-runtime-defaults")
        < names.indexOf("application-test")
);
~~~

Ordering is part of the configuration contract. When upgrading Spring Boot, re-check tests that rely on names or positions of framework-created sources.

### 10.4. Verification Matrix

| ID | Scenario | Outcome to verify |
| --- | --- | --- |
| P1 | Custom source at front of list. | Its values beat lower sources. |
| P2 | Custom source at end of list. | Values are only used when higher sources do not supply the key. |
| P3 | Custom source inserted after system environment. | Environment variables beat custom source; custom source can beat lower config files. |
| P4 | Two sources share a key, different names. | Earlier source wins. |
| P5 | Two sources with the same name are added. | List contains only one source with that name per API semantics. |
| P6 | Replace source with the same name. | New source sits at the exact old position and new values take effect. |
| P7 | Remove source. | Resolver pulls values from remaining lower sources. |
| P8 | Child merges parent with identically named source. | Child source is kept; identically named parent source is excluded from child. |
| P9 | Source replaced after singleton bean initialization. | Environment reflects new values while bean snapshot still holds old values. |
| P10 | Refresh configuration beans/refresh scope. | Beans update only via the corresponding rebinding/target invalidation mechanism. |

## 11. Troubleshooting Common Errors

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Custom property has no effect. | Source was not added, added too late, or sits below another source. | Inspect source list and Environment values. |
| Value is always custom despite setting environment variable. | Custom source used `addFirst` and overrides environment source. | Move to an appropriate relative position such as `addAfter` system environment if that is the desired policy. |
| A source appears multiple times after refresh. | Source name changes each time or code always adds a new source. | Use a stable name and replace/update instead of generating random names. |
| `replace` reports source not found. | Source not yet registered or passed name does not match. | Check `contains(name)`, add the first time, replace on subsequent updates. |
| `addBefore`/`addAfter` fails. | Reference source does not exist in that Environment. | Inspect actual source names; do not assume every Environment has identical sources. |
| Some parent keys disappear in child. | Parent and child sources share the same name, dropping parent source on merge. | Use distinct names or merge data intentionally. |
| Bean keeps using old value after source replacement. | Bean already snapshotted values; not rebound/refreshed yet. | Choose `@ConfigurationProperties` rebind or `@RefreshScope` as appropriate. |
| Slow startup with custom source. | `getProperty` calls remote backend synchronously or repeatedly. | Use caching/snapshots, timeouts, and controlled early loading. |
| Empty value overrides fallback. | Source returns empty string instead of null/missing key. | Define semantics for blank values and validate inputs. |
| Actuator `env` exposes configuration. | Endpoint is broadly exposed or displays sensitive properties. | Restrict endpoint exposure, access permissions, and observable data. |

## 12. Production Design Principles

1. **Stable source names:** use constants namespaced by owner and purpose.
2. **Intentional precedence:** clearly document which source is allowed to override which source.
3. **Do not override system settings unintentionally:** avoid `addFirst` for defaults or tenant policies if system properties/environment variables must take higher precedence.
4. **Update sources via snapshots:** validate the entire dataset before replacing the source.
5. **No network calls inside every `getProperty`:** use caching, timeouts, last-known-good, and a clear refresh mechanism.
6. **Control concurrency:** never mutate multi-key maps while requests are reading; consider immutable snapshots.
7. **Separate secrets from regular config:** use secret management, never log values, and never expose broadly via Actuator.
8. **Re-verify on version upgrades:** default source names and order may change across application types or framework versions.
9. **Test collisions:** test duplicate source names, overlapping keys, and parent–child merges.
10. **Observe metadata:** log source name, order, and non-sensitive revision when investigating issues.

## 13. Completion Checklist

- [ ] Can explain `PropertySource` and `Environment`.
- [ ] Distinguish source name from property key.
- [ ] Assign stable, unique, and namespaced source names.
- [ ] Understand that identically named sources are managed by name rather than accumulating as two independent entries.
- [ ] Can use `addFirst`/`addLast` and `addBefore`/`addAfter` operations.
- [ ] Know that `replace` preserves source position and how to handle when the source does not yet exist.
- [ ] Know how to `remove` a source and observe fallback values.
- [ ] Distinguish `null` from an empty string during property resolution.
- [ ] Can choose `EnvironmentPostProcessor`, `ApplicationContextInitializer`, or `@PropertySource` according to when configuration is needed.
- [ ] Know how to register `EnvironmentPostProcessor` per the Spring Boot version in use.
- [ ] Update custom sources using stable names and validated snapshots.
- [ ] Distinguish replacing a `PropertySource` from bean rebinding and refresh scope.
- [ ] Have tests verifying precedence, source-name collisions, and refresh.
- [ ] Have policies protecting secrets, Actuator, and remote configuration sources.

**Official documentation to cross-check against your project version:**

- [Spring Framework – PropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertySource.html): source names, data, and comparison semantics.
- [Spring Framework – MutablePropertySources](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/MutablePropertySources.html): adding, replacing, ordering, and removing sources.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): configuration sources, precedence order, and Config Data.
- [Spring Boot – EnvironmentPostProcessor](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html): extension point for customizing Environment during startup.
- [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): Environment changes, refresh scope, and configuration integration.

API names, default source order, and extension registration may vary by version. Check the exact Spring Boot/Spring Cloud release train and inspect the `PropertySource` list in your real application before putting a precedence policy into production.
