# @ConditionalOnProperty and the Impact of matchIfMissing

In Spring Boot and Spring Cloud, many beans should only be created when a feature is enabled via configuration. For example, an application should only create a cache when `catalog.cache.enabled=true`, only initialize an external integration client when an appropriate endpoint is configured, or only enable an adapter in specific deployment environments. The **`@ConditionalOnProperty`** annotation lets you make configurations and beans conditional on values in the `Environment`.

The **`matchIfMissing`** attribute determines what happens when the checked key does not exist. By default, a missing key causes the condition not to match. Setting `matchIfMissing=true` allows the condition to match even when the key is absent, though the outcome still depends on `havingValue` and any other property names in the annotation. Choosing the wrong value here can accidentally enable a feature, disable a bean, or alter default behavior during an application upgrade.

This lesson belongs to the **Auto-Configuration Customization** chapter of the `SPRING_CLOUD_CORE` module. It explains how `@ConditionalOnProperty` checks keys and values, the role of `havingValue`, the specific impact of `matchIfMissing`, usage at the configuration and bean levels, interactions with property sources, and how to test missing-property cases.

## 1. Why Make Configuration Conditional?

Suppose an application has a catalog caching feature. In local environments, developers want the cache disabled to inspect data easily; production may enable the cache to reduce database load.

If you only check a flag inside each method, the cache bean still has to exist and be initialized:

```java
@Service
public class CatalogService {
    private final CatalogCache cache;
    private final Environment environment;

    public CatalogService(
            CatalogCache cache,
            Environment environment) {
        this.cache = cache;
        this.environment = environment;
    }

    public CatalogItem find(String id) {
        if (environment.getProperty(
                "catalog.cache.enabled", Boolean.class, false)) {
            return cache.get(id);
        }
        return loadFromDatabase(id);
    }
}
```

If the cache needs to connect to Redis, allocate thread pools, or initialize expensive resources, the application still pays that cost even when the feature is off. A conditional configuration lets Spring register the bean only when the condition matches:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true"
)
public class CatalogCacheConfiguration {

    @Bean
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

With this configuration, the `CatalogCache` bean is only created when the `catalog.cache.enabled` property has the matching value. Because `matchIfMissing` defaults to `false`, if the key is absent from the `Environment`, the configuration does not match and the bean is not registered.

## 2. What Does @ConditionalOnProperty Check?

`@ConditionalOnProperty` is a Spring Boot condition annotation in the `org.springframework.boot.autoconfigure.condition` package. It can be placed on a configuration class or a `@Bean` method.

| Attribute | Meaning |
| --- | --- |
| `prefix` | Common prefix for the checked properties |
| `name` | One or more property names to check after the prefix |
| `havingValue` | The value the property must have for the condition to match |
| `matchIfMissing` | Whether a missing property should be treated as a match |
| `value` | Alias for `name`; `name` is usually preferred for clarity |

Example:

```java
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
```

The annotation checks the property whose full name is `catalog.cache.enabled`. Using `prefix` groups keys under the same namespace and avoids repeating strings.

Declare property names in kebab-case:

```java
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "refresh-after-write",
        havingValue = "true"
)
```

Corresponding property:

```yaml
catalog:
  cache:
    refresh-after-write: true
```

Using consistent canonical names avoids discrepancies across YAML, properties files, environment variables, and relaxed binding.

### 2.1. The Condition Reads the Effective Value in Environment

Values can come from `application.yml`, profile-specific config, environment variables, system properties, command-line arguments, Config Server, or other sources. When multiple sources declare the same key, Spring Boot's precedence rules determine which value the condition sees.

For example, if Config Server sets `true` while a container environment variable sets `false`, the condition may see `false` according to the active precedence. When a condition does not match as expected, inspect the effective value in `Environment`, not just a single YAML file.

## 3. The Role of havingValue

`havingValue` specifies the value the property must have for the condition to match. This is the clearest approach when a property represents a boolean or a specific mode.

### 3.1. Omitting havingValue

If `havingValue` is omitted, Spring Boot applies the default rule: the property must exist and its value must not equal the string `"false"` (case-insensitive comparison).

Example:

```java
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled"
)
```

| Value of `catalog.cache.enabled` | Does condition match? |
| --- | --- |
| Missing | No, unless `matchIfMissing=true` |
| `true` | Yes |
| `false` | No |
| `TRUE` | Yes |
| `yes` | Yes under the default rule because it differs from `"false"` |
| Empty string | Yes because the property exists and does not equal `"false"` |

This is an easy source of surprises: if the intent is to enable only when the boolean value is genuinely `true`, do not omit `havingValue`. Typos like `treu` or `enabled` can also be treated as matches under the default rule.

### 3.2. Specifying havingValue = "true"

```java
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true"
)
```

The condition only matches when the property has the value `true` according to the condition's comparison. Values such as `false`, `yes`, `on`, an empty string, or invalid values do not match.

This is usually the clearest choice for boolean feature flags:

```yaml
catalog:
  cache:
    enabled: true
```

### 3.3. Specifying havingValue = "false"

You can create a configuration that only activates when a feature is explicitly disabled:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "false"
)
public class CatalogCacheDisabledConfiguration {
    // Beans dedicated to the cache-disabled mode.
}
```

If the key is missing, this condition does not match when `matchIfMissing` keeps its default `false`. To treat a missing key as equivalent to false, you must explicitly set `matchIfMissing=true`.

### 3.4. havingValue Is Not a Parser for Every Data Type

`@ConditionalOnProperty` matches property values by name and required string; it does not replace validation for the entire configuration. For modes with multiple choices such as `simple`, `redis`, or `caffeine`, set `havingValue` accordingly or write a custom condition if the logic is complex.

Example selecting Redis:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "type",
        havingValue = "redis"
)
public class RedisCatalogCacheConfiguration {
    // Redis-backed cache beans.
}
```

If `catalog.cache.type=redsi` due to a typo, the configuration does not match. The application should have validation or an explicit fallback configuration so mistakes are caught early.

## 4. matchIfMissing Determines Default Behavior

`matchIfMissing` is a boolean and defaults to `false`.

- `matchIfMissing=false`: if the property does not exist, the condition does not match.
- `matchIfMissing=true`: if the property does not exist, the condition is considered matched, provided the other properties in the annotation also match.

This is the policy for **when the key is absent**, not a policy for overriding a declared value.

### 4.1. matchIfMissing=false: Disabled by Default

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class CatalogCacheConfiguration {

    @Bean
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

| Property | Outcome |
| --- | --- |
| Key missing | `CatalogCache` not created |
| `enabled=false` | `CatalogCache` not created |
| `enabled=true` | `CatalogCache` created |

This is an **opt-in** style: the feature only turns on when configuration explicitly sets `true`. It fits new features, external integrations, or expensive resources that an application should not enable automatically when configuration is missing.

### 4.2. matchIfMissing=true: Matches by Default When Key Is Missing

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class CatalogCacheConfiguration {

    @Bean
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

| Property | Outcome |
| --- | --- |
| Key missing | `CatalogCache` created |
| `enabled=false` | `CatalogCache` not created |
| `enabled=true` | `CatalogCache` created |

This is a **default-on, opt-out** style: when no configuration is present, the feature is enabled; operators must set `false` to disable it. It fits when default behavior must be preserved for existing applications or when a feature is considered a module default.

However, default-on can allocate unintended resources when a module is added to an application that has never declared the property. Use it only when this is an intentional compatibility decision.

### 4.3. matchIfMissing=true Does Not Mean Always Matching

With `havingValue="true"`:

- Key missing: matches because `matchIfMissing=true`.
- Key equals `true`: matches.
- Key equals `false`: does not match.
- Key has any other value: does not match.

`matchIfMissing` only handles the branch where the property is not found. When the property exists, `havingValue` still applies.

### 4.4. Omitting havingValue Changes the Impact

Example:

```java
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        matchIfMissing = true
)
```

| Property | Outcome |
| --- | --- |
| Key missing | Matches |
| `enabled=false` | Does not match |
| `enabled=true` | Matches |
| `enabled=yes` | Matches |
| Empty string | Matches |

If the property is boolean, this style is usually less clear than `havingValue="true"`. Specify the exact expected value to avoid accidentally enabling a feature on an invalid value.

## 5. Matrix of havingValue and matchIfMissing Combinations

Assume we are checking a single property `catalog.cache.enabled`:

| `havingValue` | `matchIfMissing` | Key missing | Value `true` | Value `false` | Value `other` |
| --- | --- | --- | --- | --- | --- |
| Not specified | `false` | Does not match | Matches | Does not match | Matches |
| Not specified | `true` | Matches | Matches | Does not match | Matches |
| `"true"` | `false` | Does not match | Matches | Does not match | Does not match |
| `"true"` | `true` | Matches | Matches | Does not match | Does not match |
| `"false"` | `false` | Does not match | Does not match | Matches | Does not match |
| `"false"` | `true` | Matches | Does not match | Matches | Does not match |

Define up front the desired behavior when the key is missing, when it is true/false, and when an operator enters an invalid value.

## 6. Multiple Properties in One Annotation

`name` can contain multiple properties. When multiple names are declared, **all** properties must satisfy the condition for the annotation to match.

Example:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog",
        name = {"cache.enabled", "cache.remote"},
        havingValue = "true"
)
public class RemoteCatalogCacheConfiguration {
    // Enabled only when both properties are true.
}
```

Corresponding configuration:

```yaml
catalog:
  cache:
    enabled: true
    remote: true
```

If `catalog.cache.enabled=true` but `catalog.cache.remote=false`, the configuration does not match. If one of the keys is missing, the result depends on `matchIfMissing`. With `matchIfMissing=true`, each missing key follows that policy; present keys must still satisfy `havingValue`.

Do not treat the `name` list as an OR condition. If the logic is “A and B, or C and not D,” split configurations or write a clearly named custom `Condition`.

## 7. Class-Level vs. Bean-Level Usage

### 7.1. On a Configuration Class

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.search",
        name = "enabled",
        havingValue = "true"
)
public class CatalogSearchConfiguration {

    @Bean
    CatalogSearchClient catalogSearchClient() {
        return new CatalogSearchClient();
    }

    @Bean
    CatalogSearchHealthIndicator catalogSearchHealthIndicator(
            CatalogSearchClient client) {
        return new CatalogSearchHealthIndicator(client);
    }
}
```

When the class-level condition does not match, that configuration is not applied; the bean methods in the class are not registered from this configuration. This is appropriate when multiple beans form one feature that should be enabled or disabled together.

### 7.2. On a @Bean Method

```java
@Configuration(proxyBeanMethods = false)
public class CatalogConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "catalog.cache",
            name = "enabled",
            havingValue = "true"
    )
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

The condition applies only to the bean declared by that method. Other beans in the class can still be registered.

Use method-level conditions when only a single optional implementation or adapter depends on the property. If multiple beans must appear together, placing the condition on the class is usually cleaner and avoids repeating annotations.

### 7.3. Combining with Other Conditions

You can combine `@ConditionalOnProperty` with classpath or bean conditions:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.redis.RedisClient")
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "type",
        havingValue = "redis"
)
public class RedisCatalogCacheConfiguration {
    // Enabled only when the Redis library is present and type=redis.
}
```

This avoids creating Redis configuration when the library is not on the classpath. For auto-configurations, review the ordering and conditions of related configurations so two competing beans are not created at the same time.

## 8. Property Defaults in @ConfigurationProperties

A default value in a `@ConfigurationProperties` object is not necessarily equivalent to a property being present in `Environment`.

Example:

```java
@ConfigurationProperties(prefix = "catalog.cache")
public class CatalogCacheProperties {

    private boolean enabled = true;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

If `catalog.cache.enabled` is not in the property sources, the bound object can hold `enabled=true` from the field initializer. However, `@ConditionalOnProperty` checks properties in `Environment`; it does not read Java object field defaults to evaluate the condition.

As a result, the following can happen:

- `CatalogCacheProperties.isEnabled()` returns `true`.
- `@ConditionalOnProperty(prefix="catalog.cache", name="enabled", havingValue="true")` does not match because the key does not exist and `matchIfMissing=false`.

To avoid two conflicting sources of defaults, pick one strategy:

1. Declare the default in a property source visible to the condition if you want the condition to rely on that default.
2. Use `matchIfMissing=true` if the intent is that a missing key enables the configuration.
3. Design a custom condition or auto-configuration around a single source of truth if the logic is complex.
4. Write tests verifying both the bean condition and the `@ConfigurationProperties` values together.

Do not assume Java field initializers are automatically written back into `Environment`.

## 9. Property Sources and Spring Cloud Config

In Spring Cloud applications, properties can come from Config Server or external configuration sources. `@ConditionalOnProperty` still checks the effective value in `Environment`; it does not care whether the property comes from local YAML, environment variables, or a remote Config Server.

Remote config example:

```yaml
catalog:
  cache:
    enabled: true
```

If Config Client loads this property before auto-configuration is evaluated, the condition can match and the bean is registered at startup.

### 9.1. Property Precedence Can Change the Outcome

Suppose Config Server sets `true` while the container environment sets `CATALOG_CACHE_ENABLED=false`. The effective value depends on property source precedence in the application. The condition uses the effective value, so the bean may not be created even though the remote file contains `true`.

When debugging, check which property source is winning and avoid logging the entire configuration if secrets are present.

### 9.2. Refreshing Properties Does Not Automatically Register or Remove Beans

`@ConditionalOnProperty` is a configuration condition evaluated while building the application context. It is not a listener continuously watching properties.

For example, the application starts with:

```yaml
catalog:
  cache:
    enabled: false
```

Later Config Server changes it to `true` and the application calls `/actuator/refresh`. The property value may update in Environment, but Spring does not re-run the entire configuration-class evaluation to add the `CatalogCache` bean.

Similarly, if the bean was created when the property was `true`, refreshing the property to `false` does not automatically remove the bean or destroy its resources.

If you need to toggle behavior at runtime, design a permanently registered bean that reads refreshable configuration, use a state/strategy bean with an explicit lifecycle, or manage resource creation/destruction explicitly. If the set of beans in the context must change, you generally need a safe instance restart or rollout.

`@RefreshScope` can recreate the target of a bean placed in that scope, but it does not turn `@ConditionalOnProperty` into a dynamic condition that adds or removes bean definitions.

## 10. Limitations When Checking Collection Properties

`@ConditionalOnProperty` works well for scalar properties such as booleans, strings, or modes. It is not a reliable choice for checking the presence of collections based on indexed keys.

Example:

```yaml
catalog:
  nodes:
    - http://catalog-a:8080
    - http://catalog-b:8080
```

The bound keys can appear as:

```text
catalog.nodes[0]
catalog.nodes[1]
```

A condition checking `catalog.nodes` will not necessarily match just because indexed properties exist. Spring Boot documentation warns that `@ConditionalOnProperty` cannot reliably predict the presence of collection properties this way.

If you need to check a collection, use `@Conditional` with a custom `Condition` or bind the collection into a configuration object and validate it via an appropriate mechanism. Do not rely on an indexed key happening to make `containsProperty` return the desired result in one specific property source.

## 11. Designing Safe Default-On and Default-Off Behavior

Choose `matchIfMissing` based on the feature's impact:

| Feature | Usually appropriate default | Reason |
| --- | --- | --- |
| Paid external service integration adapter | Off (`false`) | Avoids external connections when unconfigured |
| New optional cache | Off or decided by compatibility | Avoids allocating unexpected resources |
| Default behavior existing from older versions | Can be on (`true`) | Preserves compatibility when users have not declared the new property |
| Resource-heavy extra telemetry | Off (`false`) | Enable only intentionally |
| Mandatory security configuration | Should not rely solely on `matchIfMissing` | Requires explicit fail-fast/validation |

### 11.1. Opt-In

```java
@ConditionalOnProperty(
        prefix = "catalog.experimental",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
```

The feature only activates when an operator explicitly sets `true`. This is a good choice for experimental features, integrations with side effects, or external resources.

### 11.2. Opt-Out

```java
@ConditionalOnProperty(
        prefix = "catalog.compatibility",
        name = "legacy-mode",
        havingValue = "true",
        matchIfMissing = true
)
```

Compatibility mode is enabled when the property is absent; operators can set `false` to disable it. This is useful when introducing a new property while preserving old behavior for applications that have not updated their configuration.

If this is only a transitional default, plan to remove it in a future release. Document the default clearly in configuration docs so operators know the feature is active even when the key is omitted.

## 12. Testing with ApplicationContextRunner

Spring Boot provides `ApplicationContextRunner` to test auto-configuration and conditions in a small context without starting the full application.

Example configuration:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
class CatalogCacheAutoConfiguration {

    @Bean
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class CatalogCacheAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            CatalogCacheAutoConfiguration.class);

    @Test
    void missingPropertyDoesNotCreateCache() {
        contextRunner.run(context ->
                assertThat(context).doesNotHaveBean(CatalogCache.class));
    }

    @Test
    void trueCreatesCache() {
        contextRunner
                .withPropertyValues("catalog.cache.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(CatalogCache.class));
    }

    @Test
    void falseDoesNotCreateCache() {
        contextRunner
                .withPropertyValues("catalog.cache.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(CatalogCache.class));
    }
}
```

`CatalogCache` is an example application class. The test covers three key states: key missing, key `true`, and key `false`. If you change to `matchIfMissing=true`, the first test must update its expectation to assert that the bean is created when the key is missing.

### 12.1. Required Test Matrix

| Case | Test property | `havingValue` | `matchIfMissing` | Expectation |
| --- | --- | --- | --- | --- |
| Not declared | None | `true` | `false` | No bean |
| Explicitly enabled | `true` | `true` | `false` | Bean exists |
| Explicitly disabled | `false` | `true` | `false` | No bean |
| Enabled by default | None | `true` | `true` | Bean exists |
| Enabled with wrong value | `yes` | `true` | `false` | No bean |
| Enabled by default but operator disables | `false` | `true` | `true` | No bean |

Add tests for property precedence if the application uses Config Server, environment variables, or command-line arguments to override the same key.

## 13. Troubleshooting Common Issues

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Bean is not created when property is omitted | `matchIfMissing` defaults to `false` | Verify whether the key exists and choose an intentional default |
| Bean is created even though value is not `true` | `havingValue` was omitted | Set `havingValue="true"` for boolean flags |
| Bean is not created even though YAML has `true` | Higher-precedence property source sets `false`, wrong prefix/name, or profile not loaded | Check the effective value in Environment |
| Bean is unexpectedly created when key is missing | `matchIfMissing=true` | Revisit the default-on/opt-out decision |
| Multiple properties but condition fails to match | One key in the list is missing or does not satisfy the value | Remember that all `name` entries must match |
| Collection condition does not work | Checking base key when only indexed properties exist | Use a custom `Condition` or post-binding validation |
| `@ConfigurationProperties` has `enabled=true` but bean condition fails | Java object default is not a property in Environment | Align default and condition strategies |
| Config Server refreshes property but bean does not appear | Conditions are not re-evaluated after startup | Restart/rollout or design a dedicated runtime toggle |
| Property disabled after refresh but bean remains | Conditions do not automatically remove bean definitions at runtime | Manage lifecycle or restart instances |
| Two configurations both create the same bean | Overlapping conditions or missing exclusion condition | Design mutually exclusive branches and test the context |

Investigation sequence:

1. Confirm the full property key after combining `prefix` and `name`.
2. Check which profile and property source provide the value.
3. Confirm the effective value in `Environment`.
4. Read the actual `havingValue` and `matchIfMissing` on the annotation.
5. Check all property names if multiple keys are listed.
6. Check whether the condition is class-level or method-level.
7. Inspect the condition evaluation report when diagnosing auto-configuration.
8. Confirm whether the application is checking a startup condition or expecting a runtime change.
9. Write an `ApplicationContextRunner` test reproducing the exact property values.

Spring Boot Actuator includes a `conditions` endpoint in appropriate setups to inspect whether auto-configuration conditions matched. Expose this administrative endpoint strictly according to your application's security policy; do not open all Actuator endpoints just for debugging.

## 14. Practice: Enabling Cache via Configuration

Suppose the catalog module provides an optional cache. Requirements:

- Cache is off by default.
- Enable only when `catalog.cache.enabled=true`.
- If the property is missing, do not create a Redis client bean.
- If the property has an invalid value, do not silently enable the cache.

Configuration:

```yaml
catalog:
  cache:
    enabled: false
    type: redis
    ttl: 5m
```

Auto-configuration:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.cache",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class CatalogCacheAutoConfiguration {

    @Bean
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

If the cache requires a Redis library, you can add `@ConditionalOnClass` and a condition for `catalog.cache.type=redis`. Then Redis-specific beans are created only when both the library and the matching property are present.

Verification steps:

1. Omit `catalog.cache.enabled` completely: bean is not created.
2. Set `false`: bean is not created.
3. Set `true`: bean is created.
4. Set `yes`: bean is not created because `havingValue="true"`.
5. Set a higher-precedence property source to `false`: bean is not created even if another file sets `true`.
6. Change the property after startup: confirm the condition does not automatically register or remove beans; use restart or design a runtime toggle if business requirements need immediate changes.

### Self-Check Questions

1. Where does `@ConditionalOnProperty` read its data from?
2. What is the default value of `matchIfMissing`?
3. When `havingValue` is omitted, can the value `yes` make the condition match?
4. Why should you set `havingValue="true"` for boolean feature flags?
5. Does `matchIfMissing=true` make the condition match when the property is present with value `false`?
6. If multiple properties are declared in `name`, how many must match?
7. How does a class-level condition differ from a condition on a `@Bean` method?
8. Why does a default field in `@ConfigurationProperties` not automatically make `@ConditionalOnProperty` match?
9. Why is `@ConditionalOnProperty` unsuitable for checking collection indexed properties?
10. When Config Server refreshes a property, does Spring automatically register or remove beans according to conditions?
11. When should `matchIfMissing=true` be used?
12. Which tool should you use to test missing/true/false property cases?

**Answer Key:** (1) From `Environment` and effective property sources; (2) `false`; (3) Yes, because it differs from the string `false` under the default rule; (4) To enable only on an explicit `true` value; (5) No, `havingValue` still applies; (6) All of them; (7) A class condition applies to the whole configuration, while a method condition applies only to that bean method; (8) Field defaults are not properties in Environment; (9) Indexed keys do not guarantee the base collection key exists; (10) No, conditions are evaluated when creating the context; (11) When a missing key should mean enabled under an explicit compatibility policy; (12) `ApplicationContextRunner`.

## 15. Principles to Remember

- `@ConditionalOnProperty` makes configurations or beans conditional on properties in `Environment`.
- `havingValue` specifies the value to match; for boolean flags, explicitly declare `havingValue="true"` or `havingValue="false"`.
- If `havingValue` is omitted, any existing property value other than the string `false` can match, including invalid non-boolean values.
- `matchIfMissing` defaults to `false`; missing keys do not match.
- `matchIfMissing=true` only changes how missing keys are handled; it does not bypass `havingValue` when the key is present.
- Multiple properties in `name` form an AND condition: all must be satisfied.
- A class-level condition applies to the entire configuration; a `@Bean` condition applies only to that bean.
- Defaults in `@ConfigurationProperties` do not automatically become properties in `Environment`.
- Do not use `@ConditionalOnProperty` to check collection indexed properties; consider a custom `Condition`.
- Property refreshes do not re-evaluate conditions or add/remove bean definitions; runtime toggles need dedicated lifecycle design.
- Test missing keys, `true`, `false`, invalid values, property precedence, and the condition report using `ApplicationContextRunner`.

Choosing `havingValue` and `matchIfMissing` properly gives auto-configuration predictable default behavior, preserves compatibility when new properties are introduced, and prevents unintentionally initializing features. Treat the missing-property case as an explicit design decision, then test both present and absent values before releasing.

## References

- [Spring Boot Reference — ConditionalOnProperty](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot API — ConditionalOnProperty](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot API — ApplicationContextRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Cloud Commons Reference](https://docs.spring.io/spring-cloud-commons/reference/)