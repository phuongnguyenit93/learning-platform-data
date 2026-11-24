# NoneNestedConditions for Negated Condition Groups

## 1. When Do You Need NoneNestedConditions?

A custom starter sometimes should create a fallback bean only when **none of the alternative options are enabled**.

For example, Acme provides a default local cache. The local cache should appear only when Redis is not enabled and Hazelcast is not enabled either. If either remote integration is selected, the local cache auto-configuration must be skipped.

Logical expression:

```text
LocalCacheEnabled = NOT (RedisEnabled OR HazelcastEnabled)
                 = NOT RedisEnabled AND NOT HazelcastEnabled
```

`NoneNestedConditions` represents the exact negation of an OR group of conditions. It is an abstract class in `org.springframework.boot.autoconfigure.condition`, extending `AbstractNestedCondition`. It matches when **none of the nested class conditions match**.

Each nested class is a marker class carrying its own condition annotation. That way, each excluding branch has an independent name and diagnostic message.

## 2. Distinguishing None, Any, and All

| Class | Match result | Logic |
| --- | --- | --- |
| `AnyNestedCondition` | At least one nested condition matches | `A OR B OR C` |
| `AllNestedConditions` | All nested conditions match | `A AND B AND C` |
| `NoneNestedConditions` | No nested condition matches | `NOT (A OR B OR C)` |

With two conditions A and B:

| A | B | Any | All | None |
| --- | --- | --- | --- | --- |
| false | false | false | false | true |
| true | false | true | false | false |
| false | true | true | false | false |
| true | true | true | true | false |

If even one member condition matches, `NoneNestedConditions` does not match. This is the easiest point to misread when seeing the word "none".

Examples:

- `AnyNestedCondition`: enable an integration if Redis **or** Hazelcast is chosen.
- `AllNestedConditions`: enable a feature when a property is enabled **and** the required class is on the classpath.
- `NoneNestedConditions`: enable the local fallback when **neither** Redis **nor** Hazelcast is chosen.

If you only need to negate a single condition, built-in annotations such as `@ConditionalOnMissingClass` or `@ConditionalOnProperty` may be simpler. `NoneNestedConditions` is useful when you need to negate **a group of multiple distinct conditions**.

## 3. Structure of a Custom NoneNestedConditions

A composite condition has three parts:

1. A Java class extending `NoneNestedConditions`.
2. A constructor calling `super(ConfigurationPhase...)` to choose the evaluation phase.
3. Nested marker classes declaring member conditions with annotations.

Example:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.NoneNestedConditions;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;

static class OnNeitherRedisNorHazelcast extends NoneNestedConditions {

    OnNeitherRedisNorHazelcast() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
            prefix = "acme.cache.redis",
            name = "enabled",
            havingValue = "true")
    static class RedisEnabled {
    }

    @ConditionalOnProperty(
            prefix = "acme.cache.hazelcast",
            name = "enabled",
            havingValue = "true")
    static class HazelcastEnabled {
    }
}
```

`RedisEnabled` matches when `acme.cache.redis.enabled=true`. `HazelcastEnabled` matches when `acme.cache.hazelcast.enabled=true`. The composite condition matches only when neither nested condition matches.

The nested classes are marker classes: they do not need bean methods or custom Java logic. Annotations on each class provide the criteria Spring Boot evaluates.

## 4. Choosing the Right ConfigurationPhase

The constructor of `NoneNestedConditions` requires a `ConfigurationPhase`. This value determines when the group of nested conditions is evaluated.

### 4.1. PARSE_CONFIGURATION

Use when nested conditions can be evaluated while parsing configuration, such as:

- `@ConditionalOnClass` / `@ConditionalOnMissingClass`.
- `@ConditionalOnProperty`.
- Conditions checking resources, JNDI, or the environment without reading the bean registry.

The cache example below uses property conditions, so choose:

```java
NoRemoteCacheEnabledCondition() {
    super(ConfigurationPhase.PARSE_CONFIGURATION);
}
```

`PARSE_CONFIGURATION` means the condition is evaluated while a configuration class is being parsed. If the condition does not match, the configuration class can be skipped before its bean methods are processed.

### 4.2. REGISTER_BEAN

Use when nested conditions need to inspect already-registered bean definitions, such as `@ConditionalOnBean` or `@ConditionalOnMissingBean`.

Another pattern: create a fallback `Clock` only when the context has neither a `DataSource` nor a `Clock`:

```java
import java.time.Clock;
import javax.sql.DataSource;

import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.NoneNestedConditions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;

class OnNeitherDataSourceNorClock extends NoneNestedConditions {

    OnNeitherDataSourceNorClock() {
        super(ConfigurationPhase.REGISTER_BEAN);
    }

    @ConditionalOnBean(DataSource.class)
    static class DataSourceExists {
    }

    @ConditionalOnBean(Clock.class)
    static class ClockExists {
    }
}

@Configuration(proxyBeanMethods = false)
class FallbackClockConfiguration {

    @Bean
    @Conditional(OnNeitherDataSourceNorClock.class)
    Clock fallbackClock() {
        return Clock.systemUTC();
    }
}
```

The condition is placed on the **`@Bean` method** so it is evaluated during the bean-registration phase. If a `DataSource` or `Clock` bean has already been processed, a nested condition matches and the composite condition does not match; the fallback is not registered.

`REGISTER_BEAN` does not mean waiting until every object is instantiated. This is the bean-definition registration phase; bean conditions check the definitions the container knows at that moment.

### 4.3. Do Not Mix Two Phases

Nested conditions in a group must be compatible with the composite condition's phase.

- Groups containing only property/classpath checks: choose `PARSE_CONFIGURATION`.
- Groups containing bean checks: choose `REGISTER_BEAN`.
- If both property checks and bean checks are needed, consider splitting into two condition classes or two configuration classes with separate phases rather than forcing members from different phases into one group.

Specifically, a `REGISTER_BEAN` phase condition is not used to prevent a `@Configuration` class from being parsed. When the goal is a bean-based condition, normally place the composite condition on the `@Bean` method as in `FallbackClockConfiguration`.

## 5. Practical Example: Creating Local Cache Only When No Remote Cache Is Selected

We build an auto-configuration that creates a default local `CacheStore`. If Redis or Hazelcast is enabled, the local configuration is not applied. The example uses Spring Boot 3.3.5 and Java 17+.

### 5.1. Project Structure

```text
none-nested-conditions-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/cache/CacheStore.java
    │   ├── java/demo/autoconfigure/
    │   │   ├── NoRemoteCacheEnabledCondition.java
    │   │   └── LocalCacheAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/autoconfigure/
        └── LocalCacheAutoConfigurationTests.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>none-nested-conditions-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`spring-boot-autoconfigure` provides `NoneNestedConditions`, `@AutoConfiguration`, and the condition annotations. `spring-boot-starter-test` is for testing only, providing JUnit, AssertJ, and `ApplicationContextRunner`.

### 5.3. Cache Contract: `CacheStore.java`

File `src/main/java/demo/cache/CacheStore.java`:

```java
package demo.cache;

public record CacheStore(String provider) {
}
```

In a real starter, the contract might be an interface with get/put/evict operations. The example uses a record to focus on condition results and make assertions simple.

### 5.4. Negated Condition Group: `NoRemoteCacheEnabledCondition.java`

File `src/main/java/demo/autoconfigure/NoRemoteCacheEnabledCondition.java`:

```java
package demo.autoconfigure;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.NoneNestedConditions;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;

class NoRemoteCacheEnabledCondition extends NoneNestedConditions {

    NoRemoteCacheEnabledCondition() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
            prefix = "acme.cache.redis",
            name = "enabled",
            havingValue = "true")
    static class RedisEnabled {
    }

    @ConditionalOnProperty(
            prefix = "acme.cache.hazelcast",
            name = "enabled",
            havingValue = "true")
    static class HazelcastEnabled {
    }
}
```

Each property has `matchIfMissing=false` by default. Therefore, when a property is absent or not `true`, its nested condition does not match.

| Redis enabled | Hazelcast enabled | Composite condition | Local fallback |
| --- | --- | --- | --- |
| missing/false | missing/false | Match | Allowed |
| true | missing/false | No match | Skipped |
| missing/false | true | No match | Skipped |
| true | true | No match | Skipped |

### 5.5. Local Auto-Configuration: `LocalCacheAutoConfiguration.java`

File `src/main/java/demo/autoconfigure/LocalCacheAutoConfiguration.java`:

```java
package demo.autoconfigure;

import demo.cache.CacheStore;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration
@Conditional(NoRemoteCacheEnabledCondition.class)
public class LocalCacheAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CacheStore.class)
    public CacheStore localCacheStore() {
        return new CacheStore("local");
    }
}
```

There are two independent decision layers:

1. `@Conditional(NoRemoteCacheEnabledCondition.class)` decides whether the entire local auto-configuration is applied.
2. `@ConditionalOnMissingBean(CacheStore.class)` lets the application provide a custom `CacheStore` to replace the default bean.

If Redis or Hazelcast is enabled, the local auto-configuration class is skipped. If no remote provider is chosen, the class is applied; the local bean is created only if no other `CacheStore` exists yet.

In a real system, Redis/Hazelcast integrations would have their own auto-configurations registering the corresponding providers. This example loads only the local auto-configuration to test the exclusion condition cleanly.

### 5.6. Registering Auto-Configuration

Create the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Contents:

```text
demo.autoconfigure.LocalCacheAutoConfiguration
```

Spring Boot 3.x uses `AutoConfiguration.imports` to discover auto-configurations in a JAR. Without registering this class, writing `@AutoConfiguration` and conditions correctly is still not enough for applications to load it automatically.

## 6. Testing Logic Branches with ApplicationContextRunner

Create file `src/test/java/demo/autoconfigure/LocalCacheAutoConfigurationTests.java`:

```java
package demo.autoconfigure;

import demo.cache.CacheStore;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class LocalCacheAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            LocalCacheAutoConfiguration.class));

    @Test
    void createsLocalCacheWhenNoRemoteProviderIsEnabled() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(CacheStore.class);
            assertThat(context.getBean(CacheStore.class).provider())
                    .isEqualTo("local");
        });
    }

    @Test
    void skipsLocalCacheWhenRedisIsEnabled() {
        this.runner
                .withPropertyValues("acme.cache.redis.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(CacheStore.class);
                });
    }

    @Test
    void skipsLocalCacheWhenHazelcastIsEnabled() {
        this.runner
                .withPropertyValues("acme.cache.hazelcast.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(CacheStore.class);
                });
    }

    @Test
    void skipsLocalCacheWhenBothRemoteProvidersAreEnabled() {
        this.runner
                .withPropertyValues(
                        "acme.cache.redis.enabled=true",
                        "acme.cache.hazelcast.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(CacheStore.class);
                });
    }

    @Test
    void userDefinedCacheStoreReplacesLocalDefault() {
        this.runner
                .withBean(CacheStore.class, () -> new CacheStore("custom"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CacheStore.class);
                    assertThat(context).doesNotHaveBean("localCacheStore");
                    assertThat(context.getBean(CacheStore.class).provider())
                            .isEqualTo("custom");
                });
    }
}
```

### 6.1. Running the Tests

From the project directory:

```bash
mvn -q test
```

The five tests verify:

- No remote chosen: local cache is created.
- Redis chosen: local cache is skipped.
- Hazelcast chosen: local cache is skipped.
- Both chosen: local cache is skipped.
- Custom cache present: local default backs off.

`ApplicationContextRunner` creates a small context for each scenario and closes it after assertions run. It is well suited for testing conditions without starting a web server or full application.

## 7. Reading the Condition Evaluation Report When a Negated Group Does Not Match

Each nested condition has its own outcome. When `--debug` is enabled on a real application, Spring Boot prints the Condition Evaluation Report. If the Actuator `conditions` endpoint is exposed, you can read the report as JSON.

When no remote cache is selected:

- `RedisEnabled` does not match.
- `HazelcastEnabled` does not match.
- `NoRemoteCacheEnabledCondition` matches because no member condition matched.
- `LocalCacheAutoConfiguration` is applied.
- `localCacheStore` is registered if no custom `CacheStore` bean exists yet.

When Redis is enabled:

- `RedisEnabled` matches.
- `HazelcastEnabled` does not match.
- `NoRemoteCacheEnabledCondition` does not match.
- `LocalCacheAutoConfiguration` is skipped.
- The local bean is not created from this auto-configuration.

Do not hard-code verbatim report messages into tests. Messages can change across Boot versions and nested members; check the source, match/no-match state, and bean registry.

If you need to expose the Actuator endpoint for diagnostics:

```properties
management.endpoints.web.exposure.include=health,conditions
```

The conditions endpoint can expose configuration names, bean names, and environment details. Only expose it in appropriate environments and restrict access to authorized operators.

## 8. When Should You Use NoneNestedConditions?

Use `NoneNestedConditions` when:

- A fallback should be created only if no integration or mode in a group is enabled.
- Multiple exclusion branches use different annotations, such as property, classpath, and JNDI.
- You want the Condition Evaluation Report to show each reason that excluded the fallback.
- You want to name a meaningful negated rule instead of repeating condition logic across multiple configuration classes.

| Fallback | Excluding conditions |
| --- | --- |
| Local cache | Redis enabled or Hazelcast enabled |
| Embedded database | PostgreSQL driver present or external database URL declared |
| Default HTTP client | Reactor Netty present or custom client configured |
| Local scheduler | Quartz enabled or cluster scheduler selected |
| Default metrics exporter | Prometheus exporter or OTLP exporter enabled |

These examples require choosing the right conditions for your actual requirements. If you only want the fallback to back off when a **custom bean already exists**, using `@ConditionalOnMissingBean` directly on the bean method is usually clearer than combining it into a parse-phase condition.

## 9. Common Pitfalls

1. **Confusing None with All.** None matches when no member matches; All requires every member to match.
2. **Reading "none" as "at least one condition is false".** With two conditions, just one member matching makes None not match. Use a truth table.
3. **Choosing the wrong phase.** Conditions inspecting the bean registry require `REGISTER_BEAN`; property/classpath checks usually fit `PARSE_CONFIGURATION`.
4. **Placing a REGISTER_BEAN condition on a configuration class.** This phase is for bean registration; it does not block configuration-class parsing like the parse phase. Place it on a `@Bean` method if needed.
5. **Mixing member conditions from different phases.** A nested condition group must use compatible phases; split groups if both parse-time and bean-time checks are needed.
6. **Forgetting `matchIfMissing`.** Missing properties usually make nested `@ConditionalOnProperty` not match. Inside a None group, that can cause the fallback to be enabled. Document property defaults clearly.
7. **Allowing invalid property values.** If a user mistypes a provider name or value, no nested condition matches and the fallback may be created. Validate allowed configurations instead of using None as an enum validator.
8. **Enabling multiple remote providers simultaneously.** None only excludes the local fallback; it does not choose between Redis and Hazelcast or guarantee two integrations will not both create beans. Add separate validation or policy if only one provider may be active.
9. **Overlooking user beans.** The group condition may match and the configuration class may apply, yet `@ConditionalOnMissingBean` must still yield to custom beans.
10. **Using a composite condition for overly simple logic.** If you only negate one class, use `@ConditionalOnMissingClass`. If you only check one property, use `@ConditionalOnProperty`.
11. **Not registering auto-configuration.** Forgetting `AutoConfiguration.imports` prevents the application from discovering the configuration even when conditions are written properly.
12. **Checking only the Condition Report.** Also assert bean types/names and implementation values to verify the final result.

## 10. Review Checklist for a Negated Condition Group

- [ ] Each member condition is clearly written with a meaningful name.
- [ ] The combined expression is confirmed to be NOT(A OR B OR ...).
- [ ] A truth table was written for key combinations.
- [ ] ConfigurationPhase fits the member conditions.
- [ ] If REGISTER_BEAN is used, the condition is placed on a bean method or appropriate bean registration point.
- [ ] Tested missing, false, true, and invalid property values.
- [ ] Tested when multiple members match simultaneously.
- [ ] Tested custom beans and fallback back-off.
- [ ] Auto-configuration is registered in `AutoConfiguration.imports`.
- [ ] Tested with `ApplicationContextRunner` on the target Spring Boot version.
- [ ] Read the report to understand each nested condition.
- [ ] Verified the bean registry to confirm the actual fallback.

## Official Documentation

- [Spring Boot 3.3 — `NoneNestedConditions` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/NoneNestedConditions.html): defines "matches when none of the nested class conditions match" and constructor accepting `ConfigurationPhase`.
- [Spring Boot 3.3 — `AnyNestedCondition` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AnyNestedCondition.html): groups conditions with OR.
- [Spring Boot 3.3 — `AllNestedConditions` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AllNestedConditions.html): groups conditions with AND.
- [Spring Framework 6.1 — `ConfigurationCondition.ConfigurationPhase` API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.ConfigurationPhase.html): differences between `PARSE_CONFIGURATION` and `REGISTER_BEAN`.
- [Spring Boot 3.3 — Developing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): registering auto-configuration and testing with `ApplicationContextRunner`.
- [Spring Boot 3.3 — Conditions Actuator API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): reading the Condition Evaluation Report via the conditions endpoint.
