# Stability Scope Across Context Restarts and Limits Across Process Restarts

Spring Boot provides `RandomValuePropertySource` to generate random values in `Environment`. Spring Cloud Context adds `CachedRandomPropertySource`, allowing random results to be retained under a cache key. The two mechanisms solve different needs: generating a random value on demand, or reusing a generated value throughout the lifecycle of the same Java process.

The crucial point is that **stability across ApplicationContext restarts does not mean persistence across JVM restarts**. `CachedRandomPropertySource` keeps results in the process's cache. When the JVM/container terminates, the in-memory cache is lost; the next startup may generate a different value. If a value needs to survive multiple deployments or be shared across multiple replicas, it must be stored in a durable data source.

This lesson belongs to the **Random Values** chapter of the **SPRING_CLOUD_CORE** module. The content explains `random.*` and `cachedrandom.*`, the cache lifecycle, key selection, testing context restarts, process restart limits, and storage options when true durability is required.

## 1. Learning Objectives

After this lesson, learners will be able to:

- Distinguish Spring Boot's `RandomValuePropertySource` from Spring Cloud Context's `CachedRandomPropertySource`.
- Use `value`, `int`, `long`, `uuid`, and ranged random numbers.
- Write properties using the `cachedrandom.[yourkey].[type]` syntax.
- Explain why the same cache key returns the same value when the ApplicationContext is recreated in the same JVM.
- Distinguish context restart, context refresh, JVM restart, and container/pod recreation.
- Understand why `cachedrandom` does not provide persistence across process restarts or share values across multiple replicas.
- Design tests for the two different lifecycles.
- Choose a database, secret manager, or durable configuration source when the application needs to retain values across deployments.

## 2. Spring Boot's RandomValuePropertySource

Spring Boot adds a `RandomValuePropertySource` to `Environment`. Values can be referenced via placeholders:

```yaml
app:
  secret: "${random.value}"
  number: "${random.int}"
  big-number: "${random.long}"
  uuid: "${random.uuid}"
  number-less-than-ten: "${random.int(10)}"
  number-in-range: "${random.int[1024,65536]}"
```

Commonly used types:

| Placeholder | Result |
| --- | --- |
| `${random.value}` | String/byte-based random value per Spring Boot's implementation |
| `${random.int}` | Random integer |
| `${random.long}` | Random long integer |
| `${random.uuid}` | Random UUID |
| `${random.int(10)}` | Integer in the range from 0 to less than 10 |
| `${random.int[1024,65536]}` | Integer from 1024 to less than 65536 |

The range syntax for `random.int` and `random.long` has the form `OPEN value (,max) CLOSE`. The opening and closing characters can be `(`, `)`, `[`, or `]`; if only one bound is given, Spring Boot uses 0 as the lower bound and the given bound as the upper bound. If two bounds are given, the lower bound is inclusive and the upper bound is exclusive.

Example in `application.properties`:

```properties
app.port=${random.int[20000,30000]}
app.retry-limit=${random.int(5)}
app.instance-id=${random.uuid}
```

`RandomValuePropertySource` generates values when queried. It does not cache by property name. Therefore, do not use `random.*` expecting a later lookup to always receive the exact previously generated value. When you need to keep the same value by key within the same process, use Spring Cloud Context's cached random mechanism.

## 3. Spring Cloud Context's CachedRandomPropertySource

Spring Cloud Context adds a `PropertySource` named `CachedRandomPropertySource`. Aside from its caching behavior, it uses the same value types supported by Spring Boot.

To use this property source, ensure `spring-cloud-context` is on the classpath. If the project manages dependencies via the Spring Cloud BOM, there is no need to pin a separate version manually:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-context</artifactId>
</dependency>
```

Many Spring Cloud starters already pull in this module transitively. When an application has only Spring Boot without Spring Cloud Context, `random.*` still works, whereas `cachedrandom.*` is not provided.

Spring Cloud Context registers this property source during `Environment` processing via an `EnvironmentPostProcessor`. Typical applications only need the appropriate dependency on the classpath; there is no need to manually create a `CachedRandomPropertySource` bean.

Syntax:

```text
cachedrandom.[yourkey].[type]
```

Where:

- `cachedrandom` is the prefix to select the cached property source.
- `yourkey` is the cache entry name, used to identify the value to retain.
- `type` is a value type supported by `RandomValuePropertySource`.

Example:

```yaml
app:
  instance-id: "${cachedrandom.catalog-instance.uuid}"
  bootstrap-token: "${cachedrandom.catalog-token.value}"
  local-port: "${cachedrandom.catalog-port.int[20000,30000]}"
```

The first time a cache key is read, Spring Cloud generates a random value and stores the result in the cache. Subsequent reads with the same key receive the stored result. If a different key is used, the cache creates a separate entry.

`yourkey` is a cache label, not a cryptographic seed. Renaming the key does not reproduce the old value; it creates a new cache entry and may generate a new value. Two applications using the same key name in two separate JVMs do not share results automatically either.

### 3.1. Using the Same Key When the Same Value Is Needed

Suppose multiple properties need to reference the same identifier:

```yaml
app:
  node-id: "${cachedrandom.catalog-node.uuid}"
  node-id-for-metrics: "${cachedrandom.catalog-node.uuid}"
  node-id-for-log-context: "${cachedrandom.catalog-node.uuid}"
```

All three placeholders share the cache key `catalog-node` and type `uuid`, so they receive the same value within the current cache scope.

If different keys are used:

```yaml
app:
  node-id: "${cachedrandom.catalog-node.uuid}"
  worker-id: "${cachedrandom.catalog-worker.uuid}"
```

the two values are cached independently. Choose meaningful, stable key names; do not arbitrarily rename keys when you want to preserve an identifier across the process lifecycle.

## 4. Why Is cachedrandom Stable Across ApplicationContext Restarts?

`CachedRandomPropertySource` caches values by key at process scope. When Spring recreates the `ApplicationContext` within the same JVM/classloader, that cache remains intact. The new context can look up the same cache key and receive the previously generated value.

Example of an application creating contexts twice in the same process:

```java
String firstValue = firstContext.getEnvironment()
    .getProperty("app.instance-id");

firstContext.close();

try (ConfigurableApplicationContext secondContext =
         new SpringApplicationBuilder(Application.class).run()) {

    String secondValue = secondContext.getEnvironment()
        .getProperty("app.instance-id");

    // Same cache key in the same JVM keeps the cached value.
    assertEquals(firstValue, secondValue);
}
```

The example above illustrates context lifecycle, not process restart. The cache key must remain unchanged between the two context creations. If the application changes configuration to a different key, the result belongs to a new cache entry.

### 4.1. Context Refresh and Context Restart

Three operations should be distinguished:

- **Refresh Environment:** updates property sources and rebinds configuration in a running context.
- **Restart ApplicationContext:** closes the current context and creates a new context in the same JVM.
- **Restart process:** terminates the JVM and starts a new JVM.

With the same cache key, `CachedRandomPropertySource` is designed to return the cached value when the context is re-initialized in the same process. This mechanism does not turn random values into data written to disk or sent to another process.

## 5. Cache Boundary on JVM Restart

`CachedRandomPropertySource`'s cache resides in process memory. It is not a database, file store, distributed cache, or secret manager.

When the JVM stops:

1. Objects and static caches in the JVM's classloader are released.
2. The new process starts with fresh memory.
3. `CachedRandomPropertySource` begins with a cache containing no previous entries.
4. The first read of the cache key generates a new value.

Therefore, the following scenarios are not guaranteed to retain the same value:

- Re-running `java -jar` after the previous process terminates.
- Restarting or recreating a container.
- A Kubernetes Pod being replaced/rescheduled and starting a fresh JVM.
- A Deployment rolling update creating new replicas.
- Rebooting a server or node.

Stability across context restarts is only meaningful within the same JVM/classloader retaining the cache. Do not use it as a long-term identifier storage mechanism.

## 6. Lifecycle Comparison

| Event | `random.*` | `cachedrandom.*` |
| --- | --- | --- |
| First property read | Generates a random value | Generates and stores by cache key |
| Re-reading the same property source | May generate a new value when queried again | Returns the cached value by key |
| Recreating ApplicationContext in the same JVM | No guarantee of retaining value | Retains value by cache key |
| Refreshing configuration in the same process | No key-based caching | Existing cache keys continue returning the stored value |
| Restarting JVM/process | Generates value in the new process | New cache; may generate a different value |
| Creating a replica in another JVM | Independent values | Independent caches; values may differ |
| Requiring a value durable across deployments | Unsuitable | Unsuitable without external storage |

This table describes the lifecycle of the property source. A value already bound to a bean or stored in an object may continue to exist for that bean's own lifecycle; that does not mean the property source persisted the value durably.

## 7. A Cache Key Is Not a Multi-Instance Synchronization Mechanism

Suppose three replicas all declare:

```yaml
app:
  cluster-token: "${cachedrandom.shared-token.uuid}"
```

Each replica runs in its own JVM. Each JVM has its own cache, so all three can generate three different UUIDs. The string `shared-token` is only a local cache key name; it is not a sharing channel between replicas.

This remains true even when:

- Replicas share a Config Server.
- Replicas use the same `application.yml` file.
- Replicas have the same `spring.application.name`.
- Replicas are deployed in the same Kubernetes Deployment.

If every replica needs to receive the same value, generate the value once and store it in a shared durable source, then have the replicas read that value.

## 8. Choosing random vs. cachedrandom by Purpose

| Need | Mechanism to Use | Reason |
| --- | --- | --- |
| Generate a test number at startup | `random.int` | Fresh random value suits testing |
| Generate a local UUID for a process | `cachedrandom.node-id.uuid` | Keeps the same UUID when context is rebuilt in the JVM |
| Generate a temporary value for one run | `random.uuid` | Does not need retention across context restarts |
| Keep an identifier across context restarts | `cachedrandom.<key>.uuid` | Key-based caching within the process |
| Keep an ID across JVM restarts | Database or persistent store | In-JVM cache is insufficient |
| Share a token across multiple replicas | Secret manager or shared config store | Separate JVMs do not share caches |
| Create long-lived credentials | Secret manager/credential service | Requires lifecycle, distribution, rotation, and auditing |

Do not use `cachedrandom` to generate database passwords or long-lived API credentials if dependent systems need to reuse the credential after a process restart. When the new process generates a new value, the target service may still hold the old credential and authentication will fail.

## 9. Persisting Values Durably Across Process Restarts

When business requirements demand that a value stay unchanged after a JVM restart, use a storage source with an appropriate lifecycle.

Common options:

- **Database:** store an ID or token per application/environment; use transactions and unique constraints to prevent two replicas from creating two initial values simultaneously.
- **Secret manager:** store credentials or keys requiring secure distribution, versioning, and rotation.
- **Persistent volume:** store a local file or data if the identifier is tied to a node and the volume has a stable lifecycle.
- **Config Server or centralized configuration source:** store generated values and manage them by revision.
- **Kubernetes Secret/ConfigMap:** use when values must be distributed via Kubernetes; Secret is better suited for sensitive data and still requires proper RBAC and encryption-at-rest configuration.

A durable initialization pattern is:

1. Check whether the storage source already has a value for the application/environment.
2. If present, read and use that value.
3. If absent, generate a random value using an appropriate API.
4. Store the value via a transaction or create-if-absent operation.
5. Re-read the stored value so all replicas use the same one.
6. Never log plaintext secrets.

`cachedrandom` can be helpful for retaining a temporary value during context initialization, yet it does not replace a durable persistence step.

## 10. Complete Configuration Example

Suppose an application needs two kinds of values:

- An `instance-id` that stays stable when the context is recreated in the same JVM.
- A fresh `startup-marker` for every process startup.

Configuration:

```yaml
app:
  identity:
    instance-id: "${cachedrandom.catalog-instance.uuid}"
    startup-marker: "${random.uuid}"
```

Bean reading the values:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ApplicationIdentity {

    private final String instanceId;
    private final String startupMarker;

    public ApplicationIdentity(
            @Value("${app.identity.instance-id}") String instanceId,
            @Value("${app.identity.startup-marker}") String startupMarker) {
        this.instanceId = instanceId;
        this.startupMarker = startupMarker;
    }

    public String getInstanceId() {
        return instanceId;
    }

    public String getStartupMarker() {
        return startupMarker;
    }
}
```

Within the same JVM, when the context is rebuilt and the same cache key is still used, `instance-id` is retrieved from the cache. `startup-marker` is generated from `random.uuid` when configuration is resolved during the new context startup.

When a new JVM starts, both values may differ from the previous process. If `instance-id` must survive process restarts, replace `cachedrandom` with a value read from a persistent store.

## 11. Testing the Cache Lifecycle

A test suite should clearly distinguish three scenarios:

### 11.1. Same Cache Key in the Same JVM

- Initialize the first context.
- Read the `${cachedrandom.test-instance.uuid}` property.
- Close the context.
- Create the second context in the same JVM/classloader.
- Read the same property again.
- Assert the two values are equal.

When running multiple tests, isolate cache keys between tests. `CachedRandomPropertySource` provides a `clearCache()` API in versions that expose this method; verify the API of your project's release train before using it. Because this is a class-level global cache operation, do not call it arbitrarily while other contexts are active or when tests run in parallel.

### 11.2. Same Process but Different Keys

- Read `cachedrandom.test-a.uuid`.
- Read `cachedrandom.test-b.uuid`.
- Verify the two keys are separate cache entries.
- Re-read each key and confirm its corresponding value is preserved.

Do not write tests assuming two UUIDs will strictly differ on every run; collision probability is tiny yet mathematically non-zero. Focus on verifying that the same key returns the same value.

### 11.3. New Process

- Start the application in the first process and record the test UUID.
- Terminate that process completely.
- Start the second process with the same configuration and the same cache key.
- Observe that a new value is generated in the new JVM.

If the test objective is that a value must survive process restarts, the test must read from the actual persistence source and confirm the value is recovered from that source. `cachedrandom` cannot prove that requirement.

## 12. Common Issues and Diagnostics

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Value changes after container restart | New JVM has a fresh cache | Use a persistent store if retention across process restarts is needed |
| Two pods have the same cache key yet different values | Caches are isolated per JVM | Read a single value from a shared storage source |
| Value changes after renaming the key | New cache key has no value yet | Keep the key unchanged if you want to reuse the existing cache entry |
| Value does not change after recreating the context | Cache still exists in the same process | This is the expected behavior of `cachedrandom` |
| Test expects `random.*` to stay stable yet it changes | `RandomValuePropertySource` generates values on demand | Use `cachedrandom` or store the result yourself |
| Cached value fails to resolve | Missing Spring Cloud Context or wrong syntax | Check dependency, `cachedrandom.` prefix, and type |
| Two properties need the same value yet receive different ones | Using two different cache keys or one property uses `random.*` | Use the same cache key and type |
| Credential changes after redeploy causing service failures | Using cached random for long-lived credentials | Move credentials to a secret manager or database |
| Old value remains in a bean after refresh | Bean holds the bound value or was not recreated | Check bean rebind/lifecycle mechanisms; do not infer the cache was durably persisted |

## 13. Practice Exercise

A `catalog-service` has the following configuration:

```yaml
catalog:
  instance-id: "${cachedrandom.catalog-instance.uuid}"
  api-key: "${cachedrandom.catalog-api-key.value}"
```

The application runs two replicas. After a rollout, both replicas have different `instance-id`s from the previous run; the API key also changes, causing dependent services to reject requests.

Perform the following:

1. Explain why `cachedrandom` retains values across context restarts but not across process restarts.
2. Distinguish the caches of two replicas running in two JVMs.
3. Replace `instance-id` with an ID stored in a database or persistent source suitable for the deployment model.
4. Move `api-key` to a secret manager or shared credential source.
5. Test context restart in the same JVM and verify the cache key returns the old value.
6. Test process restart and verify the persisted value is recovered.
7. Rename the cache key and observe why the cache creates a new entry.
8. Design a multi-replica test to verify they all read the same value from the shared source.

**Completion criteria:** distinguish random values, cached random values, and persistent values; accurately identify the JVM scope of the cache; avoid using cached random as a secret store or cross-replica synchronization mechanism; and have tests for context restart and process restart.

## 14. Key Takeaways

- Spring Boot's `RandomValuePropertySource` generates `random.*` when queried; it is not a stable key-based cache.
- Spring Cloud Context's `CachedRandomPropertySource` caches values using `cachedrandom.[yourkey].[type]`.
- `yourkey` is a cache entry name, not a seed to reproduce values on another machine.
- The same cache key stays stable when `ApplicationContext` is recreated within the same JVM process.
- In-memory caches do not survive after the JVM/process exits.
- Replicas have separate caches; using the same cache key does not make them share the same value.
- `cachedrandom` fits temporary values that must stay stable within a process lifecycle, not persistence or secret distribution.
- To preserve values across process restarts, use a database, secret manager, persistent volume, or centralized configuration source.
- Test context restart, process restart, and multiple replicas separately to verify the exact lifecycle the application needs.

## 15. References

- [Spring Cloud Commons — CachedRandomPropertySource](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/cachedrandompropertysource.html): `cachedrandom.[yourkey].[type]` syntax and caching behavior across `ApplicationContext` restarts.
- [Spring Boot — Externalized Configuration, Configuring Random Values](https://docs.spring.io/spring-boot/reference/features/external-config.html): `random.value`, `random.int`, `random.long`, `random.uuid`, and range syntax.
- [Spring Boot — RandomValuePropertySource API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/env/RandomValuePropertySource.html): value types supported by the random property source.
- [Spring Cloud Context — CachedRandomPropertySource API](https://javadoc.io/doc/org.springframework.cloud/spring-cloud-context/3.1.9/org/springframework/cloud/util/random/CachedRandomPropertySource.html): caching API and `clearCache()` method in the documented version.
