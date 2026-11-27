# Distinguishing cachedrandom from Spring Boot's random

Both Spring Boot and Spring Cloud can provide random values via placeholders in configuration, yet the two mechanisms serve different purposes. Spring Boot uses the `random.` prefix to generate a random value when a property is looked up. Spring Cloud Context adds the `cachedrandom.` prefix to store the generated value under a key, so the same key returns the same value on subsequent lookups, even when the ApplicationContext is restarted within the same process.

The critical difference is **whether there is key-based caching or not**. `random.uuid` is suitable when you need a fresh value; `cachedrandom.instance-id.uuid` is suitable when you need a value that stays stable within the process's cache lifecycle. Neither replaces a persistent configuration store or a secret management system.

This lesson belongs to the **Random Values** chapter of the **SPRING_CLOUD_CORE** module. The content explains Spring Boot's `RandomValuePropertySource`, Spring Cloud's `CachedRandomPropertySource`, placeholder syntax, value lifetime, how to choose a mechanism by scenario, and how to test.

## 1. Two Property Sources, Two Behaviors

Spring Boot provides `RandomValuePropertySource`, which recognizes properties starting with `random.`. Spring Cloud Context provides `CachedRandomPropertySource`, which recognizes properties of the form `cachedrandom.[yourkey].[type]`.

| Criterion | Spring Boot `random.*` | Spring Cloud `cachedrandom.*` |
| --- | --- | --- |
| Property source | `RandomValuePropertySource` | `CachedRandomPropertySource` |
| Prefix | `random.` | `cachedrandom.` |
| Value generation | Generates a random value when the property is looked up | Generates on first lookup, then caches by key |
| Repeated lookup of the same property | May receive a new value | Receives the cached value for that key |
| ApplicationContext restart in the same JVM | No guarantee of retaining the old value | Spring Cloud documentation describes retaining the value across context restarts |
| JVM/process restart | Value is regenerated | In-memory cache is lost; value may differ |
| Scope across replicas | Each process generates values independently | Each process has its own cache |
| Providing library | Spring Boot | Spring Cloud Context |

Both mechanisms share the same interpretation of the `type` part: the value types supported by Spring Boot's `RandomValuePropertySource`. `cachedrandom` adds the `yourkey` part to identify which cache entry will be used.

~~~mermaid
flowchart TD
    A["Placeholder in configuration"] --> B{"Prefix"}
    B -->|"random.*"| C["Spring Boot RandomValuePropertySource"]
    B -->|"cachedrandom.*"| D["Spring Cloud CachedRandomPropertySource"]
    C --> E["Generate value per lookup"]
    D --> F{"Key already in cache?"}
    F -->|"No"| G["Generate value and store by key"]
    F -->|"Yes"| H["Read stored value"]
    G --> I["Return value"]
    H --> I
    E --> J["Return random value"]
~~~

Do not treat `cachedrandom` as merely another name for `random`. They have different stability contracts.

## 2. Spring Boot's random

Spring Boot automatically adds `RandomValuePropertySource` to `Environment` during startup. You can use placeholders in `application.yml` or `application.properties` without writing a custom random-generation bean.

YAML example:

~~~yaml
app:
  random:
    token-fragment: "${random.value}"
    instance-uuid: "${random.uuid}"
    worker-number: "${random.int}"
    delay-millis: "${random.int[100,1000]}"
    port-candidate: "${random.int[1024,65536]}"
    sequence-number: "${random.long}"
~~~

Properties example:

~~~properties
app.random.token-fragment=${random.value}
app.random.instance-uuid=${random.uuid}
app.random.worker-number=${random.int}
app.random.delay-millis=${random.int[100,1000]}
app.random.port-candidate=${random.int[1024,65536]}
app.random.sequence-number=${random.long}
~~~

Values are resolved like normal properties. They can be injected via `@Value`, read through `Environment`, or bound to `@ConfigurationProperties`.

### 2.1. Supported Value Types

| Placeholder | Result |
| --- | --- |
| `${random.value}` | Random byte/value-based string provided by RandomValuePropertySource |
| `${random.int}` | Random integer |
| `${random.long}` | Random long integer |
| `${random.uuid}` | Random UUID |
| `${random.int(10)}` | Integer from 0 to less than 10 |
| `${random.int[1024,65536]}` | Integer from 1024 to less than 65536 |
| `${random.long[1000,5000]}` | Long from 1000 to less than 5000 |

With the two-bound syntax, the first value is min (inclusive) and the second value is max (exclusive). Therefore, `random.int[1024,65536]` does not generate 65536.

The opening and closing characters of the range portion can use parentheses or square brackets according to the syntax described by Spring Boot. Standardize on one style across the project to keep configuration readable.

### 2.2. random Does Not Cache by Property Name

`RandomValuePropertySource` provides no caching contract by property name. When `Environment` looks up `random.uuid` multiple times, the property source can generate different UUIDs.

Direct check example:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RandomValueReader {

    private final Environment environment;

    public RandomValueReader(Environment environment) {
        this.environment = environment;
    }

    public String nextUuid() {
        return environment.getProperty("random.uuid");
    }
}
~~~

Each call to `nextUuid()` performs a read from `Environment`. With `random.uuid`, a new read can return a different UUID from the previous one.

However, distinguish `Environment` lookups from injecting a placeholder into a bean. If `@Value("${random.uuid}")` is resolved when the bean is initialized, the bean's field retains that injected value. The field does not automatically change whenever another method calls `Environment.getProperty("random.uuid")`.

### 2.3. @Value and ConfigurationProperties Examples

Direct injection:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class WorkerIdentity {

    private final String startupId;

    public WorkerIdentity(
            @Value("${random.uuid}") String startupId) {
        this.startupId = startupId;
    }

    public String getStartupId() {
        return startupId;
    }
}
~~~

Binding into a configuration group:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.random")
public class RandomSettings {

    private String instanceUuid;
    private int workerNumber;

    public String getInstanceUuid() {
        return instanceUuid;
    }

    public void setInstanceUuid(String instanceUuid) {
        this.instanceUuid = instanceUuid;
    }

    public int getWorkerNumber() {
        return workerNumber;
    }

    public void setWorkerNumber(int workerNumber) {
        this.workerNumber = workerNumber;
    }
}
~~~

Register `RandomSettings` using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(RandomSettings.class)`. Values are bound when configuration is loaded. If you want to read a fresh random value on each operation, do not rely solely on a field bound at startup.

## 3. Spring Cloud Context's cachedrandom

Spring Cloud Context provides `CachedRandomPropertySource`. This mechanism works similarly to Spring Boot's `RandomValuePropertySource`, except it stores values by key.

Syntax:

~~~text
cachedrandom.[yourkey].[type]
~~~

Where:
- `cachedrandom` is the property source prefix.
- `yourkey` is the key used to look up the value in the cache.
- `type` is a random type supported by Spring Boot, such as `value`, `int`, `long`, `uuid`, or a ranged type.

Example:

~~~yaml
app:
  identity:
    instance-id: "${cachedrandom.catalog-service.instance-id.uuid}"
    worker-port: "${cachedrandom.catalog-service.worker-port.int[20000,30000]}"
    opaque-value: "${cachedrandom.catalog-service.opaque-value.value}"
~~~

When `catalog-service.instance-id.uuid` is looked up for the first time, Spring Cloud generates a UUID and stores it in the cache under the key. Subsequent lookups with the same key return the stored value.

### 3.1. The Cache Key Determines Which Value Is Reused

Suppose two properties reference the same cache key:

~~~yaml
app:
  primary-id: "${cachedrandom.orders.instance-id.uuid}"
  diagnostic-id: "${cachedrandom.orders.instance-id.uuid}"
~~~

Both placeholders use the same key and type, so they receive the same cached value.

If two independent values are needed, use two different keys:

~~~yaml
app:
  instance-id: "${cachedrandom.orders.instance-id.uuid}"
  correlation-seed: "${cachedrandom.orders.correlation-seed.uuid}"
~~~

Key names should:
- Be meaningful for their intended purpose.
- Remain stable across context initializations.
- Contain no secrets or personal data.
- Differ between values that need to be independent.
- Stay consistent when renaming configuration properties.

Do not change keys on every deployment if the goal is to reuse cached values within the same process. Changing the key requests a different cache entry and may generate a new value.

### 3.2. Example Sharing the Same Value Across Multiple Beans

~~~java
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class InstanceIdentity {

    private final UUID instanceId;

    public InstanceIdentity(
            @Value("${cachedrandom.orders.instance-id.uuid}")
            UUID instanceId) {
        this.instanceId = instanceId;
    }

    public UUID getInstanceId() {
        return instanceId;
    }
}
~~~

Another bean can use the same placeholder:

~~~java
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DiagnosticIdentity {

    private final UUID instanceId;

    public DiagnosticIdentity(
            @Value("${cachedrandom.orders.instance-id.uuid}")
            UUID instanceId) {
        this.instanceId = instanceId;
    }

    public UUID getInstanceId() {
        return instanceId;
    }
}
~~~

Both beans receive the same UUID because the placeholders use the same cache key. This differs from generating a new UUID in a constructor with `UUID.randomUUID()`.

## 4. How Long Does cachedrandom Live?

The Spring Cloud documentation states that cached random values can maintain consistency when the Spring ApplicationContext is restarted. This is useful when an application closes and recreates its context within the same JVM process.

Distinguish the scopes:

| Event | `random.*` | `cachedrandom.*` |
| --- | --- | --- |
| Reading a property multiple times | Generates a new value per lookup | Reuses the value by key |
| Creating another bean in the same context | Placeholder resolved at bean creation time | Same key receives the cached value |
| Closing and recreating ApplicationContext in the same JVM | No guarantee of keeping the old value | Cache can retain the old value per documentation |
| JVM/process restart | New value when process restarts | In-memory cache is recreated; old value is not guaranteed |
| Running two independent replicas | Each process generates values independently | Each process has its own cache and may produce two different values |

**cachedrandom is not a persistent cache.** It does not write values to a database, file, Config Server, or secret manager. When the JVM terminates, the process's in-memory cache is gone.

Therefore:
- Use `cachedrandom` if you need stability across ApplicationContext recreations within the same process.
- Do not use it as a durable identifier across deployments or process restarts.
- Do not use it to share the same secret across multiple replicas.
- Do not use it to replace an ID issued by a database or centralized identity system.

If you need to keep the same value across multiple deployments, generate the value once and store it in a durable source such as Config Server, Vault, a Kubernetes Secret, or a database following appropriate governance procedures.

### 4.1. Context Restart Differs from Process Restart

Some applications can close and recreate the ApplicationContext to apply a restart mechanism within the same JVM. This is the scenario `cachedrandom` targets.

Conversely, when a container is deleted and recreated, a Pod is rescheduled, a JVM is killed, or a server reboots, the new process has fresh memory. You cannot rely on the old process's cache.

~~~mermaid
flowchart TD
    A["JVM process starts"] --> B["CachedRandomPropertySource"]
    B --> C["Create key instance-id for the first time"]
    C --> D["Cache UUID value"]
    D --> E["ApplicationContext runs"]
    E --> F["Context closed and recreated in the same JVM"]
    F --> G["Same cache key"]
    G --> H["Receives cached UUID again"]
    H --> I["JVM terminates"]
    I --> J["New process, new cache"]
    J --> K["Same key may generate a different UUID"]
~~~

## 5. Property Sources and Precedence Order

Spring Boot loads configuration sources into `Environment`. `RandomValuePropertySource` is a dedicated property source for `random.*` keys; Spring Boot documentation places it after config data and before sources like OS environment variables in the default order.

Spring Cloud Context adds a property source for `cachedrandom.*`. When diagnosing actual precedence order, inspect the `Environment` of your exact application and version rather than assuming every setup has the same order after adding other `EnvironmentPostProcessor`s or libraries.

Points to remember:
- `random.*` and `cachedrandom.*` are two separate namespaces.
- A regular property such as `app.instance-id` can use a placeholder to reference either namespace.
- The final value of a property depends on property sources and placeholder resolution.
- If another configuration source overrides the target property, check the effective value rather than only reading YAML files.
- Do not expose random values or secrets on public management endpoints.

Example:

~~~yaml
app:
  instance-id: "${cachedrandom.orders.instance-id.uuid}"
~~~

Components in the application read `app.instance-id` without needing to know where the UUID was generated. This allows changing the ID generation policy without modifying every consumer.

## 6. When to Choose random vs. cachedrandom?

| Need | Suitable Choice | Reason |
| --- | --- | --- |
| New UUID for every lookup | `random.uuid` | No key-based caching required |
| Random number for tests or temporary config | `random.int`, `random.long` | Concise configuration, supported by Spring Boot |
| One value shared across multiple beans | `cachedrandom.<key>.<type>` | Same key returns the same value |
| Preserve value when ApplicationContext restarts in the same JVM | `cachedrandom.<key>.<type>` | Cache outlives a single context lifecycle |
| Preserve ID across JVM/container restarts | Persistent storage source | In-memory cache does not survive process exit |
| Secret used for production authentication | Secret manager/KMS/Vault | Requires lifecycle management, access control, and rotation |
| Unique ID across multiple replicas | ID service/database/distributed UUID design | Per-JVM caches are not shared |
| Random test port | `random.int[...]` or test port-selection utility | Does not need stability after restart |

### 6.1. Example for Test Configuration

You can use `random.int` to produce a bounded test value:

~~~yaml
test:
  retry:
    delay-millis: "${random.int[50,250]}"
~~~

Each time the configuration is resolved in the test process, the value falls between 50 and less than 250. Do not use this value to pick a real port without checking whether the port is already in use by the operating system.

### 6.2. Example for a Stable Identifier Within One Process

~~~yaml
app:
  diagnostics:
    process-id: "${cachedrandom.orders.process-id.uuid}"
~~~

Beans in the same process can share the same process ID. When the context is recreated in the same JVM, the same key can return the old value. When the process restarts, the ID may change.

If the goal is to identify a deployment across multiple restarts, store the ID in a durable source or obtain the ID from the deployment platform.

## 7. Do Not Use Random Properties as Cryptographic Secrets

Property names might suggest that `random.value` is an option for generating passwords, tokens, or encryption keys. However, `RandomValuePropertySource` is designed to provide random values for configuration and tests; you should not assume it is a secret management system or a dedicated cryptographic key generator.

Do not use `random.*` or `cachedrandom.*` as a source of cryptographic secrets for production. For sensitive data:
- Use Vault, KMS, a secret manager, or an equivalent mechanism.
- Use `java.security.SecureRandom` when the application genuinely needs to generate random data with cryptographic requirements. `RandomValuePropertySource` is a configuration utility, not a cryptographic RNG guarantee.
- Store and distribute secrets according to system policy.
- Plan for rotation, revocation, and auditing.
- Do not write secret values to logs, metrics, traces, or Actuator endpoints.
- Do not use `cachedrandom` to share secrets across replicas or across process restarts.

A stable cached value is not equivalent to a secure secret. Caching only solves value consistency within managed memory scope.

## 8. Impact of Configuration Refresh

Spring Cloud Context supports updating `Environment` and refreshing beans in an application. However, a refresh operation does not clear `CachedRandomPropertySource`'s cache.

If a property uses:

~~~yaml
app:
  node:
    id: "${cachedrandom.orders.node-id.uuid}"
~~~

then invoking a configuration refresh and re-resolving the same cache key can still return the cached value. To generate a different value, use a different key or a value-management mechanism with its own lifecycle.

With `random.uuid`, each new lookup can produce a new value. However, if the value was already bound to a singleton or stored in a field, re-reading `Environment` does not automatically update that field. Understand clearly when properties are resolved.

### 8.1. Changing the Cache Key Is One Way to Produce a New Value

Example:

~~~yaml
app:
  node:
    current-id: "${cachedrandom.orders.node-id-v2.uuid}"
~~~

The key `orders.node-id-v2` differs from the previous key, so it requests a new cache entry. This is a way to generate a new value through configuration, though key changes must be managed intentionally to avoid unintended ID changes.

Do not append a timestamp or a new UUID to a key on every refresh if your goal is stable caching; doing so turns every lookup into a separate entry and defeats the purpose of the cache key.

## 9. Testing Both Behaviors

Test the two property sources separately so you do not confuse results already resolved into a bean with the behavior of the property source itself.

### 9.1. Unit Test for RandomValuePropertySource

Example testing the same property looked up twice:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.env.RandomValuePropertySource;

class RandomValuePropertySourceTests {

    @Test
    void generatesNewUuidForRepeatedLookups() {
        RandomValuePropertySource source =
                new RandomValuePropertySource();

        Object first = source.getProperty("random.uuid");
        Object second = source.getProperty("random.uuid");

        assertThat(first).isNotEqualTo(second);
    }
}
~~~

This test checks the property source directly. In a real application, `@Value` typically resolves placeholders only at bean creation time, so you should not use an injected field to conclude whether a property source caches values.

### 9.2. Unit Test for CachedRandomPropertySource

Spring Cloud provides `CachedRandomPropertySource`. You can verify that the same key returns the same value:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.env.RandomValuePropertySource;
import org.springframework.cloud.util.random.CachedRandomPropertySource;

class CachedRandomPropertySourceTests {

    @AfterEach
    void clearCache() {
        CachedRandomPropertySource.clearCache();
    }

    @Test
    void reusesValueForTheSameCacheKey() {
        CachedRandomPropertySource source =
                new CachedRandomPropertySource(
                        new RandomValuePropertySource()
                );

        Object first =
                source.getProperty("cachedrandom.orders.instance-id.uuid");

        Object second =
                source.getProperty("cachedrandom.orders.instance-id.uuid");

        assertThat(first).isEqualTo(second);
    }

    @Test
    void usesIndependentValuesForDifferentKeys() {
        CachedRandomPropertySource source =
                new CachedRandomPropertySource(
                        new RandomValuePropertySource()
                );

        Object primaryFirst =
                source.getProperty("cachedrandom.orders.primary-id.uuid");
        Object primaryAgain =
                source.getProperty("cachedrandom.orders.primary-id.uuid");

        Object secondaryFirst =
                source.getProperty("cachedrandom.orders.secondary-id.uuid");
        Object secondaryAgain =
                source.getProperty("cachedrandom.orders.secondary-id.uuid");

        assertThat(primaryAgain).isEqualTo(primaryFirst);
        assertThat(secondaryAgain).isEqualTo(secondaryFirst);
    }
}
~~~

The test calls `clearCache()` to isolate state between runs. This is an API of `CachedRandomPropertySource`; verify the package/API against the Spring Cloud release train used by your project.

Two independent keys are tested separately. Do not write an assertion requiring two random values from two different keys to be strictly unequal, because two independent values still have a theoretical probability of colliding, however small.

### 9.3. Integration Test for ApplicationContext Restart

The unit tests above confirm key-based caching within a single property source instance. If you want to test behavior across an `ApplicationContext` restart, run the application with `SpringApplication` with Spring Cloud Context on the classpath so the `EnvironmentPostProcessor` is registered.

An integration test scenario:
1. Start the first context in the test JVM.
2. Read `cachedrandom.test.instance-id.uuid` from `Environment`.
3. Close the first context.
4. Start the second context in the same JVM.
5. Read the same cache key again.
6. Verify the values are equal.
7. Use a different key to verify independent cache entries.

Do not use two separate processes/JVMs for this test if the goal is to verify caching across a context restart. Two JVMs have two independent memory spaces.

## 10. Diagnosing When cachedrandom Does Not Work

If a `cachedrandom.*` placeholder is not resolved as expected, check in order:

1. Is Spring Cloud Context/Commons on the classpath?
2. Is the Spring Cloud BOM version compatible with Spring Boot?
3. Is `CachedRandomPropertySource`'s `EnvironmentPostProcessor` registered?
4. Does the `cachedrandom` property source appear in `Environment`?
5. Does the placeholder match the `cachedrandom.[key].[type]` format?
6. Are the reads genuinely using the same key?
7. Is another property source overriding the target property?
8. Is any test calling `clearCache()` or modifying the cache during execution?
9. Did the application restart the process rather than only restarting the context?

You can use the Actuator `env` endpoint in a test environment or protected management network to inspect property sources. Do not expose endpoints or random/secret values in production merely for debugging.

### 10.1. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `cachedrandom.*` fails to resolve | Missing Spring Cloud Context or processor not registered | Check dependencies, BOM, and EnvironmentPostProcessor |
| Same `random.uuid` property yields different results | Random property source does not cache by key | Use `cachedrandom` if the value needs to be reused |
| Same `cachedrandom` changes after deploy | New JVM/process creates a fresh cache | Use durable storage if persistence across process restarts is needed |
| Two replicas share the same cache key yet differ | Each JVM has its own cache | Use Config Server, Vault, or a shared ID service |
| Two beans have different IDs | Using different keys or resolved via separate random mechanisms | Use the same cache key and type if the same value is needed |
| Field value does not change after refresh | Field retained the previously injected value | Check resolution/binding timing and bean lifecycle |
| `cachedrandom` value changes after editing key | New key creates a different cache entry | Keep key stable or manage key changes intentionally |
| Random value exposed via Actuator | Endpoint exposed or show-values configured too broadly | Restrict exposure, masking, and access permissions |

## 11. Mechanism Selection Checklist

Before adding a random placeholder to configuration, determine:

- [ ] Does the value need to be new on each lookup or stable per key?
- [ ] Does the value need to survive `ApplicationContext` recreation?
- [ ] Does it need to survive JVM/container restarts?
- [ ] Does the same value need to be shared across multiple replicas?
- [ ] Is the value a secret or cryptographic key?
- [ ] Does the cache key have a stable name that does not collide with another purpose?
- [ ] Are Spring Cloud Context and BOM dependencies compatible?
- [ ] Do tests distinguish property source lookup from values already injected into beans?
- [ ] Could logs, Actuator, or telemetry accidentally expose sensitive values?

## Remember

Spring Boot's `random.*` generates a random value when a property is looked up and does not cache by key. Spring Cloud Context's `cachedrandom.[yourkey].[type]` adds key-based caching, allowing the same key to receive the retained value when the `ApplicationContext` is recreated within the same JVM. This cache lives in process memory, is not durable storage, and is not shared across replicas. Choose `random` for values that should change, `cachedrandom` for values that must stay stable within a process's cache scope, and a secret manager or durable storage source when values must survive restarts or deployments.

## References

- Spring Cloud Commons – CachedRandomPropertySource: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/cachedrandompropertysource.html
- Spring Boot – Externalized Configuration / Configuring Random Values: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot – RandomValuePropertySource API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/env/RandomValuePropertySource.html
