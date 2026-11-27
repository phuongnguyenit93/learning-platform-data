# Merging Multiple Sources with `CompositePropertySource`

In a Spring application, a property can be provided from many places: configuration files, environment variables, startup arguments, per-tenant settings, a central configuration store, or a secret management service. When an integration needs to group several sources together and control precedence among them, Spring Framework provides **`CompositePropertySource`**.

`CompositePropertySource` is an aggregating `PropertySource`. It holds multiple child `PropertySource` instances and looks up keys sequentially according to their ordered sequence. For a given key, **the first child source that returns a non-`null` value determines the result**. Consequently, an application can represent a group of configuration sources as a single source when adding it to `Environment`.

This lesson belongs to the **Custom Configuration Sources** chapter of the **SPRING_CLOUD_CORE** module. Learners will practice merging configuration sources using the Spring Framework API, controlling internal and global precedence, integrating into `ConfigurableEnvironment`, testing, and understanding limitations when used alongside Spring Cloud Config or refresh mechanisms.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain the role of `CompositePropertySource` and its relationship to `PropertySource`.
2. Create a composite containing multiple configuration sources and determine the winning source on key collisions.
3. Distinguish precedence **inside the composite** from the composite's position in `MutablePropertySources`.
4. Combine default sources, per-tenant sources, and controlled override sources.
5. Analyze property name enumeration when a child source does not support enumeration.
6. Register a composite into `Environment` at the right initialization stage.
7. Test precedence, missing keys, and behavior when multiple sources share the same name.
8. Distinguish source aggregation from remote data fetching, caching, refresh, and configuration synchronization.

## 2. What Is `CompositePropertySource`?

`PropertySource<T>` is the abstraction representing a source supplying properties. A source typically has a name and an underlying backing object. For example:

- `MapPropertySource`: reads from a `Map<String, Object>`.
- `PropertiesPropertySource`: reads from `Properties`.
- `SystemEnvironmentPropertySource`: reads from environment variables.
- `ResourcePropertySource`: reads from a resource.
- A custom `PropertySource`: reads from an API or data store integrated by the application.

`CompositePropertySource` extends `EnumerablePropertySource<Object>` and holds a collection of child `PropertySource` instances. It provides one name for the entire group while performing lookups across each child source.

~~~mermaid
flowchart TD
    E[Environment] --> M[CompositePropertySource: applicationSources]
    M --> A[tenantOverrides]
    M --> B[centralConfig]
    M --> C[platformDefaults]
    A --> V1[Key present in tenant?]
    B --> V2[Key present in central config?]
    C --> V3[Key present in platform defaults?]
~~~

In the diagram, sources are checked from top to bottom. If `tenantOverrides` has the key, its value is returned; otherwise, the composite proceeds to check `centralConfig`, and then `platformDefaults`.

### 2.1. Composites Do Not Copy Data

When adding a `PropertySource` to a composite, the composite holds a reference to that source. It does not eagerly read every key, copy the entire map, or create an immutable snapshot of values.

Consequences:

- The child source remains responsible for supplying data.
- Values are looked up when `getProperty` is called.
- If a child source relies on changing data, results may change depending on how that source is implemented.
- The composite does not automatically reload files or call remote services.

Therefore, `CompositePropertySource` is a **lookup aggregation** mechanism, not a config server, cache, or synchronization system.

### 2.2. Composite Name and Child Source Names

The composite has its own name, such as `tenantAndPlatformConfig`. Each child source should also have a unique, meaningful name:

~~~text
tenantAndPlatformConfig
  ├── tenantOverrides
  ├── centralConfig
  └── platformDefaults
~~~

Clear names help with debugging, reading logs, and inspecting configuration sources. `PropertySource` compares equality by name; therefore, when adding child sources to the collection, duplicate names can prevent a new source from being added as expected. Assign distinct names to each source, even when two sources read from the same backend type.

## 3. Lookup Behavior and Internal Precedence Rules

### 3.1. First Non-Null Wins

Suppose the composite contains three sources:

| Child source | `service.timeout` | `service.region` |
| --- | ---: | --- |
| `tenantOverrides` | `900ms` | Absent |
| `platformDefaults` | `500ms` | `global` |
| `centralConfig` | `700ms` | `ap-southeast-1` |

Result:

| Key | Value returned by composite | Winning source |
| --- | --- | --- |
| `service.timeout` | `900ms` | `tenantOverrides` |
| `service.region` | `global` | `platformDefaults` |
| `service.name` | `null` if no source has the key | None |

The composite checks each source in order. The first source returning a non-`null` value stops the lookup for that key.

**An empty string `""` is not `null`.** If the first source returns an empty string, that still counts as a value and blocks values in subsequent sources. If the application wants to treat an empty string as "unconfigured", normalize or validate values at an appropriate layer; do not assume the composite automatically skips empty strings.

### 3.2. Order of Adding Sources Affects Results

Commonly used API methods:

- `addPropertySource(source)`: appends the source to the end of the internal order.
- `addFirstPropertySource(source)`: places the source at the front, giving it highest priority inside the composite.
- `getPropertySources()`: inspects the current child sources.
- `containsPropertySource(name)`: checks for a child source by name.

Example:

~~~java
CompositePropertySource composite =
        new CompositePropertySource("serviceConfig");

composite.addPropertySource(platformDefaults);
composite.addPropertySource(centralConfig);
composite.addFirstPropertySource(tenantOverrides);
~~~

Lookup order after adding:

~~~text
1. tenantOverrides
2. platformDefaults
3. centralConfig
~~~

If you want `centralConfig` above `platformDefaults`, add them in the proper order or intentionally call `addFirstPropertySource`:

~~~java
composite.addFirstPropertySource(centralConfig);
~~~

After this operation, the order becomes:

~~~text
1. centralConfig
2. tenantOverrides
3. platformDefaults
~~~

Note: `addFirstPropertySource` moves the specified source to the front of the composite's collection. It does not change the order of external `PropertySource` entries in `Environment`.

### 3.3. Missing Keys vs. Sources Returning Null

If a child source does not contain a key, `getProperty` returns `null` and the composite continues to the next source. A custom source might return `null` when the backend has no data, when access to a key is forbidden, or when the backend is unavailable; those cases carry very different operational meanings.

Do not silently convert backend connection errors into `null` if the application needs to distinguish:

- Key does not exist.
- Key exists but access was denied.
- Backend is temporarily unavailable.
- Backend returned invalid data.

For required configuration, backend errors should be handled explicitly in the loading layer or bootstrap rather than pretending the key simply does not exist.

## 4. Creating a CompositePropertySource from Multiple MapPropertySources

A small example makes precedence visible without an external backend.

### 4.1. Declaring Child Sources

~~~java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;

PropertySource<?> tenantOverrides = new MapPropertySource(
        "tenantOverrides",
        Map.of(
                "service.timeout", "900ms",
                "service.display-name", "Tenant A"
        )
);

PropertySource<?> centralConfig = new MapPropertySource(
        "centralConfig",
        Map.of(
                "service.timeout", "700ms",
                "service.region", "ap-southeast-1"
        )
);

PropertySource<?> platformDefaults = new MapPropertySource(
        "platformDefaults",
        Map.of(
                "service.timeout", "500ms",
                "service.region", "global",
                "service.retry-enabled", true
        )
);
~~~

The sources share several overlapping keys. This is intentional to test precedence.

### 4.2. Merging Sources

~~~java
import org.springframework.core.env.CompositePropertySource;

CompositePropertySource composite =
        new CompositePropertySource("serviceConfig");

composite.addPropertySource(platformDefaults);
composite.addPropertySource(centralConfig);
composite.addFirstPropertySource(tenantOverrides);
~~~

The internal order is:

1. `tenantOverrides`.
2. `platformDefaults`.
3. `centralConfig`.

For `service.timeout`, tenant wins and the result is `900ms`. For `service.region`, tenant lacks the key so platform defaults is checked before central config; the result is `global`.

If you want central config to take higher priority than platform defaults, change the addition order:

~~~java
CompositePropertySource composite =
        new CompositePropertySource("serviceConfig");

composite.addPropertySource(platformDefaults);
composite.addFirstPropertySource(centralConfig);
composite.addFirstPropertySource(tenantOverrides);
~~~

The internal order becomes tenant, central, platform.

### 4.3. Reading Values from the Composite

~~~java
Object timeout = composite.getProperty("service.timeout");
Object region = composite.getProperty("service.region");
Object retryEnabled = composite.getProperty("service.retry-enabled");

System.out.println(timeout);       // 900ms
System.out.println(region);        // ap-southeast-1 if central comes before platform
System.out.println(retryEnabled);  // true
~~~

The snippet above assumes the order configured in the second example. In real applications, document the source order clearly with a table or test so maintainers do not have to infer it from `addPropertySource` calls.

## 5. Adding the Composite to the Environment

A `CompositePropertySource` only participates in application configuration resolution when attached to `Environment` or registered by an integration.

### 5.1. Using MutablePropertySources

`ConfigurableEnvironment` exposes `getPropertySources()`, which returns `MutablePropertySources`. You can add a composite as a top-level source:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.CompositePropertySource;

void registerComposite(
        ConfigurableEnvironment environment,
        CompositePropertySource composite
) {
    environment.getPropertySources().addFirst(composite);
}
~~~

Once added, you can read via `Environment`:

~~~java
String timeout = environment.getProperty("service.timeout");
~~~

Here there are **two layers of precedence**:

1. **Inside the composite:** child source order determines which source wins within the group.
2. **Among Environment PropertySources:** the composite's position in `MutablePropertySources` determines whether the composite comes before or after sources outside the group.

For example, if `commandLineArgs` sits ahead of the composite and contains `service.timeout`, the command line wins. If the composite is added via `addFirst`, it sits ahead of existing sources and can override even command-line values. This is a high-impact decision; do not use `addFirst` blindly in production.

### 5.2. Choosing Position Intentionally

| Method | Effect |
| --- | --- |
| `addFirst(composite)` | Composite has highest priority in the current list |
| `addLast(composite)` | Composite has lowest priority |
| `addBefore(name, composite)` | Places composite before a known named source |
| `addAfter(name, composite)` | Places composite after a known named source |
| `replace(name, composite)` | Replaces an existing source with the same name in the Environment list |

When using `addBefore` or `addAfter`, verify that the target source name exists. Default source names can vary by Environment type, version, or startup method. Inspect `environment.getPropertySources()` before doing relative placement.

### 5.3. Adding a Composite in ApplicationContextInitializer

One way to register before regular beans are created is `ApplicationContextInitializer`:

~~~java
import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.CompositePropertySource;
import org.springframework.core.env.MapPropertySource;

public class ServiceSourcesInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        CompositePropertySource composite =
                new CompositePropertySource("serviceConfig");

        composite.addFirstPropertySource(
                new MapPropertySource(
                        "tenantOverrides",
                        Map.of("service.timeout", "900ms")
                )
        );

        composite.addPropertySource(
                new MapPropertySource(
                        "platformDefaults",
                        Map.of(
                                "service.timeout", "500ms",
                                "service.retry-enabled", true
                        )
                )
        );

        context.getEnvironment()
                .getPropertySources()
                .addLast(composite);
    }
}
~~~

Register the initializer with `SpringApplication`:

~~~java
SpringApplication application =
        new SpringApplication(OrdersApplication.class);

application.addInitializers(new ServiceSourcesInitializer());
application.run(args);
~~~

The example uses `addLast` so the composite acts as a low-priority fallback source. If requirements demand that tenant overrides win over existing sources, choose a different position and test the order explicitly.

`ApplicationContextInitializer` runs during context preparation. This is the right time to add configuration sources needed before beans are created. Do not wait until `ApplicationRunner` to add a source if beans have already bound values earlier.

## 6. CompositePropertySource with Remote Configuration Sources

In distributed systems, child sources may come from multiple backends:

- Platform default configuration.
- Application-specific configuration.
- Environment-specific configuration.
- Per-tenant configuration.
- Secret or credential sources.
- Operations-managed override sources.

A composite can express precedence across those sources.

### 6.1. Multi-Layered Configuration Model

For example, an `orders-service` receives three layers:

| Layer | Example | Purpose |
| --- | --- | --- |
| Platform defaults | Default timeout `500ms` | Baseline values for all services |
| Central application config | Timeout `700ms`, region `ap-southeast-1` | Application/environment settings |
| Tenant overrides | Timeout `900ms`, custom display name | Permitted per-tenant adjustments |

If tenant overrides have the highest priority, the composite selects timeout `900ms`. If the tenant does not declare a region, lookup falls through to the next source containing that key.

This is a **key-based fallback** model. It is not automatic deep merging of JSON/YAML objects. The composite only looks up values by flattened property keys. Merging lists or complex objects must be defined in the binding layer or a dedicated configuration processing layer.

### 6.2. Remote Sources Must Be Loaded Before Registration

If a child source reads from HTTP, Vault, or a database, a component must load the data and turn it into a `PropertySource`. The composite itself has no knowledge of URLs, credentials, retries, timeouts, or backend protocols.

One possible flow:

~~~mermaid
flowchart TD
    A[Bootstrap / Config Data integration] --> B[Fetch platform config]
    A --> C[Fetch application config]
    A --> D[Fetch tenant overrides]
    B --> E[Build PropertySource objects]
    C --> E
    D --> E
    E --> F[Build CompositePropertySource]
    F --> G[Register into Environment]
    G --> H[Create and bind application beans]
~~~

This flow needs a clear error policy:

- Platform defaults can be mandatory or have a packaged fallback.
- Config Server can be mandatory or optional depending on business requirements.
- Tenant overrides can be optional if a tenant has no custom configuration.
- Secret sources typically must not fall back to empty or insecure default values.
- If a backend fails, distinguish that failure from the backend returning "key not found".

### 6.3. Separating Data Loading from Composition

A maintainable design usually separates two responsibilities:

1. **Loader/adapter:** connects to the backend, authenticates, handles timeouts, retries, caches, and converts data into a `PropertySource`.
2. **Composer:** accepts prepared `PropertySource` instances, names them, orders them, and builds the `CompositePropertySource`.

This keeps precedence logic decoupled from HTTP clients or secret store SDKs. You can test the composer using `MapPropertySource` without spinning up real backends.

## 7. Integrating with Spring Cloud

### 7.1. Relationship with PropertySourceLocator in Legacy Bootstrap

In Spring Cloud integrations using the legacy bootstrap context, `PropertySourceLocator` is an extension point for locating or creating property sources based on the Environment. An implementation can fetch configuration from backends and return a `CompositePropertySource` when multiple child sources need to be grouped.

Conceptual idea:

~~~java
// Pseudocode: package/API names must be checked against your release train.
PropertySource<?> locate(Environment environment) {
    PropertySource<?> platform = loadPlatformProperties(environment);
    PropertySource<?> application = loadApplicationProperties(environment);
    PropertySource<?> tenant = loadTenantProperties(environment);

    CompositePropertySource composite =
            new CompositePropertySource("remoteConfiguration");

    if (tenant != null) {
        composite.addFirstPropertySource(tenant);
    }
    if (application != null) {
        composite.addPropertySource(application);
    }
    if (platform != null) {
        composite.addPropertySource(platform);
    }

    return composite;
}
~~~

This is pseudocode illustrating the concept, not a copy-pasteable class: `PropertySourceLocator`'s package, registration, and lifecycle depend on the Spring Cloud version and bootstrap mode. Do not assume this legacy extension point is automatically invoked in modern Config Data projects.

### 7.2. Modern Config Data Import

With modern Spring Cloud Config Client, applications typically declare:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:configserver:http://localhost:8888
~~~

Config Client is responsible for fetching remote configuration and contributing property sources into the Config Data process. Users do not need to manually build a `CompositePropertySource` just to call Config Server once.

If there are multiple sources beyond Config Server, a custom integration may be needed. With Spring Boot Config Data, the extension points for custom sources can be `ConfigDataLocationResolver` and `ConfigDataLoader`, depending on requirements and version. Choose the extension point matching the configuration loading mechanism in use; do not drop legacy bootstrap code into Config Data simply because it worked in an older version.

### 7.3. Composites Do Not Replace Config Server

| Component | Responsibility |
| --- | --- |
| `CompositePropertySource` | Groups existing property sources and determines lookup order |
| Config Client | Connects to Config Server and loads remote configuration |
| Config Server | Serves centralized configuration |
| `Environment` | Lets the application read values after sources are registered |
| Spring Cloud Context refresh | Supports updating/rebinding or recreating beans via the appropriate refresh mechanism |

A composite does not store configuration version history, distribute changes to instances, or authenticate users. Those responsibilities belong to the corresponding integration systems.

## 8. Enumeration: Listing Key Names in a Composite

`CompositePropertySource` is an `EnumerablePropertySource`. When `getPropertyNames()` is called, it collects key names from child sources that support enumeration.

### 8.1. EnumerablePropertySource vs. Non-Enumerable Sources

A source like `MapPropertySource` can list its key names. However, a custom source that can only answer `getProperty(key)` might not know all keys upfront or might not support enumeration.

Consequences:

- `composite.getProperty("secret.token")` can still retrieve the value from a non-enumerable child source.
- `composite.getPropertyNames()` can only aggregate key names from child sources that support enumeration.
- A key may be readable even though it does not appear in the key name list.

Never use the `getPropertyNames()` list as absolute proof that every queryable key has been listed.

### 8.2. containsProperty and Empty Keys

`containsProperty(key)` checks child sources according to each source's capabilities. A key that exists with a `null` value may not be treated as a resolvable value; an empty string is still a non-`null` value.

If the backend distinguishes "key absent", "key has empty value", and "access forbidden", the adapter should surface those distinctions via explicit error/validation policies. Do not overload `null` for multiple states if the application needs to tell them apart.

## 9. Testing CompositePropertySource

Testing the composer should verify internal ordering, interaction with Environment, and missing-key cases. The tests below use `MapPropertySource` and require no Config Server or registry.

### 9.1. Checking First Source Wins

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.CompositePropertySource;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class CompositePropertySourceTest {

    @Test
    void firstSourceWinsForDuplicateKey() {
        var defaults = new MapPropertySource(
                "defaults",
                Map.of("service.timeout", "500ms")
        );

        var tenant = new MapPropertySource(
                "tenant",
                Map.of("service.timeout", "900ms")
        );

        var composite = new CompositePropertySource("serviceConfig");
        composite.addPropertySource(defaults);
        composite.addFirstPropertySource(tenant);

        assertThat(composite.getProperty("service.timeout"))
                .isEqualTo("900ms");
    }
}
~~~

The test proves the tenant source is placed first and beats the default source for the overlapping key.

### 9.2. Checking Fallback When the First Source Lacks a Key

~~~java
@Test
void fallsBackToNextSourceWhenKeyIsAbsent() {
    var tenant = new MapPropertySource(
            "tenant",
            Map.of("service.display-name", "Tenant A")
    );

    var defaults = new MapPropertySource(
            "defaults",
            Map.of("service.timeout", "500ms")
    );

    var composite = new CompositePropertySource("serviceConfig");
    composite.addPropertySource(tenant);
    composite.addPropertySource(defaults);

    assertThat(composite.getProperty("service.timeout"))
            .isEqualTo("500ms");
}
~~~

Because `tenant` does not declare `service.timeout`, the composite continues looking in `defaults`.

### 9.3. Checking Precedence Between Environment and Composite

~~~java
import org.springframework.mock.env.MockEnvironment;
import org.springframework.core.env.MapPropertySource;

@Test
void environmentSourceCanOverrideComposite() {
    var environment = new MockEnvironment();

    var composite = new CompositePropertySource("serviceConfig");
    composite.addPropertySource(
            new MapPropertySource(
                    "compositeDefaults",
                    Map.of("service.timeout", "700ms")
            )
    );

    environment.getPropertySources().addLast(composite);
    environment.getPropertySources().addFirst(
            new MapPropertySource(
                    "commandLineLike",
                    Map.of("service.timeout", "1200ms")
            )
    );

    assertThat(environment.getProperty("service.timeout"))
            .isEqualTo("1200ms");
}
~~~

This test proves there are two layers of ordering: regardless of child ordering inside the composite, an external property source placed ahead of the composite can still win.

### 9.4. Checking Source Names and Enumeration

Consider adding tests for:

- Child sources with unique names.
- Adding a child source with a duplicate name.
- A composite containing both an enumerable source and a non-enumerable source.
- Keys with empty string values.
- Keys missing from all sources.
- Child sources throwing errors during lookup.

Not every application needs to write every test above. Pick cases that reflect your system's actual precedence and backend error policies.

## 10. Common Mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Value retrieved from unexpected source | Wrong child source order | Inspect `getPropertySources()` order and use `addFirstPropertySource` intentionally |
| Composite has value but Environment does not see it | Composite was not added to Environment or was overridden by a preceding source | Inspect `MutablePropertySources` and the composite's position |
| Key does not appear in `getPropertyNames()` | Child source does not support enumeration | Query `getProperty(key)` directly or provide an enumerable source |
| Adding a source has no effect | `PropertySource` name collides with an existing source in the set | Use unique child source names and check `containsPropertySource` |
| Empty string blocks default value | `""` is not `null`, so the first source still counts as having a value | Validate/normalize values in the loader or binder |
| Config Server fails yet composite returns fallback | Adapter converted backend errors into `null` | Distinguish connection failures from missing keys |
| Map changes yet bean keeps using old value | Bean already bound/cached the value earlier | Check lifecycle, rebinding, and refresh scope |
| Source order shifts between environments | Sources added in a different phase or by another integration | Verify startup order and actual property sources |
| Sibling/other context does not see the same config | Composite was registered in a separate Environment/context | Clarify context ownership and Environment sharing |

### 10.1. Duplicate Child Source Names

`PropertySource` uses its name as its identifier in equality comparisons. Adding two sources with the same name to the internal collection may prevent the second source from being added as a separate entry. Do not name two different sources `remoteConfig` and expect both to be present.

Name sources by backend and scope, for example:

~~~text
tenantConfig:tenant-42
centralConfig:orders-service:prod
platformDefaults:region-ap-southeast-1
~~~

Do not include secrets or sensitive data in source names.

### 10.2. Mutating a Composite After the Application Is Running

`CompositePropertySource` and its child source collection are not a thread-safe configuration store for arbitrary runtime mutations. Adding or removing sources while multiple threads are reading can produce unpredictable behavior.

Recommendations:

- Build the composite completely before registering it into `Environment`.
- Avoid mutating the child source collection on the request-handling path.
- If configuration updates are needed, use a controlled refresh/replacement mechanism.
- Identify which beans need rebinding or recreation after an update.
- Test concurrency if the integration is required to support runtime updates.

### 10.3. Merging Sources Does Not Mean Deep Object Merging

A composite answers the question: "Which source does this key come from?". It does not merge two JSON objects, YAML lists, or map structures by domain rules.

For example, if two sources both define `clients.inventory.zones` with different lists: the composite selects the value from the winning source for that key; it does not concatenate elements from both lists. If deep merging is needed, implement dedicated merge logic before building the `PropertySource` or use an appropriate configuration model.

## 11. Security and Operations

When a composite holds secret sources or per-tenant configuration, design clear access boundaries.

- **Tenant isolation:** only place the identified tenant's overrides into the matching context/request scope. Never put a shared JVM-wide tenant map where requests might read each other's configuration.
- **Access control:** adapters must authenticate and check permissions before loading data; never treat `PropertySource` names as a security boundary.
- **Secrets:** never log values, put tokens/passwords into source names, or expose Actuator `env` publicly.
- **Timeouts and retries:** remote loaders need bounded timeouts, controlled retries, and separation between backend failures and missing keys.
- **Fallback:** only fall back when business rules allow; mandatory secrets should never fall back to dummy values.
- **Observability:** record which backend was loaded, load duration, key count, or source status at a safe metadata level; never log sensitive contents.
- **Refresh:** when sources change, update the composite via a controlled mechanism and verify beans receive the updated configuration.
- **Versioning:** Spring Framework APIs and Spring Cloud extension points must match the project's release train/Boot version.

For per-tenant configuration, specifically avoid stuffing all tenant overrides into one global `CompositePropertySource` and switching the "current tenant" per request. `Environment` normally belongs to application/context scope, not request scope. If configuration varies per tenant on each request, use a properly scoped resolver, tenant-isolated caching, and dedicated access control.

## 12. Practice Exercises

**Exercise 1 — Internal order.** Create three `MapPropertySource` instances: `platformDefaults`, `centralConfig`, `tenantOverrides`. Declare the `service.timeout` key in all three with different values. Use `addPropertySource` and `addFirstPropertySource` so tenant wins; prove the result with a test.

**Exercise 2 — Key-based fallback.** Tenant declares only `service.display-name`, central declares `service.region`, and platform declares `service.timeout`. Call `getProperty` for all three keys and explain which source is chosen.

**Exercise 3 — Two layers of precedence.** Add a composite to `MockEnvironment` using `addLast`, then add a `MapPropertySource` using `addFirst`. Prove that an external source ahead of the composite can override child sources regardless of the composite's internal ordering.

**Exercise 4 — Enumeration.** Create a custom source that can read keys but cannot enumerate key names. Compare `getProperty("secret.token")` with the composite's `getPropertyNames()` and explain the difference.

**Exercise 5 — Duplicate names.** Add two `MapPropertySource` instances with the same name to a composite. Observe the source collection and lookup results; then rename them to ensure both sources are managed clearly.

**Exercise 6 — Remote sources.** Design an adapter reading platform config and tenant config from two mock backends. Separate the loader from the composer; write tests for timeouts, backend errors, missing keys, and precedence.

**Exercise 7 — Refresh.** Update the data of a child source after application startup. Determine whether the new value is read by `Environment` and whether beans that bound the old value need to be refreshed or recreated.

## 13. Key Takeaways and Reference Sources

- `CompositePropertySource` is an aggregating `PropertySource` containing multiple child sources.
- A composite looks up keys in internal order; **the first source returning a non-`null` value wins**.
- `addFirstPropertySource` places a source at the front; `addPropertySource` appends a source to the end.
- Child source names should be unique because `PropertySource` uses names in equality checks.
- `getPropertyNames()` only lists keys from child sources that support enumeration; a non-enumerable source can still answer `getProperty(key)`.
- When adding a composite to `Environment`, consider both internal order and the composite's position in `MutablePropertySources`.
- A composite only aggregates lookups; it does not fetch remote config, cache, deep-merge objects, or refresh beans.
- With Spring Cloud, choose the right extension point: legacy bootstrap and modern Config Data have different lifecycles.
- Per-tenant configuration and secrets require controlled access scopes, fallbacks, and logging.

Official sources for verifying APIs against your project's Spring Framework/Spring Cloud versions:

1. [Spring Framework Javadoc – `CompositePropertySource`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/CompositePropertySource.html)
2. [Spring Framework Javadoc – `PropertySource`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertySource.html)
3. [Spring Framework Javadoc – `MutablePropertySources`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/MutablePropertySources.html)
4. [Spring Framework Reference – Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
5. [Spring Cloud Config – Client Side Usage](https://docs.spring.io/spring-cloud-config/reference/client.html)
6. [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
