# Spring Boot Auto-Configuration and Bean Creation Conditions

When starting with **Spring Data Redis**, you often just add `spring-boot-starter-data-redis`, declare the Redis address, and inject `StringRedisTemplate` into a service. Spring Boot can create the required beans out of the box, but this **does not happen unconditionally**. Each bean is created or skipped based on specific conditions regarding libraries on the classpath, existing beans, configuration properties, and dependency resolution.

This lesson explains the path from dependencies to `RedisConnectionFactory` and Redis templates, how Spring Boot decides when to defer to application configuration, and how to read the condition evaluation report when beans do not appear as expected.

> **Version scope:** The class names, annotations, and configuration examples below follow **Spring Boot 3.3.x / Spring Data Redis 3.3.x**. On other versions, especially across major upgrades, verify the corresponding APIs, packages, and auto-configuration class names; the general mechanics of conditional auto-configuration remain the foundation for reading the documentation.

## 1. Understanding "Auto-Configuration" Correctly

**Auto-configuration** is the mechanism by which Spring Boot inspects the libraries on the classpath and the state of the `ApplicationContext`, then registers default beans when conditions are satisfied.

It is distinct from three commonly confused activities:

| Activity | What Does Spring Do? | Redis Example |
|---|---|---|
| Dependency management / starter | Brings required libraries onto the classpath | `spring-boot-starter-data-redis` adds Spring Data Redis and the default driver |
| Auto-configuration | Evaluates conditions and registers beans | Creates `RedisConnectionFactory`, `RedisTemplate`, and `StringRedisTemplate` if eligible |
| Dependency injection | Supplies an existing bean to a consumer | Constructor receives `StringRedisTemplate` |
| Actual Redis communication | Opens/uses a connection and sends commands | `redis.opsForValue().get("k")` |

**Having beans in the context does not mean Redis is running or authentication succeeds.** Connecting may occur during bean initialization or on an actual operation, depending on the driver, lifecycle settings, health checks, and execution path. Auto-configuration proves Spring assembled the bean graph; Redis availability must be verified separately.

Overview flow:

~~~mermaid
flowchart TD
    A["Add Redis starter"] --> B["Classpath has Spring Data Redis and driver"]
    B --> C["Spring Boot evaluates RedisAutoConfiguration"]
    C --> D{"Conditions satisfied?"}
    D -->|No| E["Skip auto-configuration"]
    D -->|Yes| F["Create RedisConnectionFactory if missing"]
    F --> G{"Single suitable factory candidate?"}
    G -->|Yes| H["Create default templates unless replaced by user beans"]
    G -->|No| I["Cannot auto-select a factory to create templates"]
    H --> J["Application injects template and calls Redis"]
    J --> K["Driver executes connection/command; network errors can still occur"]
~~~

Spring Boot loads the list of auto-configurations declared by libraries, evaluates `@Conditional...` annotations, and orders configurations so application-defined beans get a chance to override defaults. Therefore, auto-configuration can be viewed as **conditional default configuration**.

## 2. Bootstrapping a Minimal Redis Project

### 2.1. Adding the Starter

With Spring Boot using Gradle and Boot's dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

This starter bundles Spring Data Redis and the **Lettuce** driver by default. It is the standard way to get the classes checked by auto-configuration conditions. Adding an arbitrary library with "redis" in its name will not necessarily satisfy all conditions Boot checks.

An application can add `spring-boot-starter-data-redis-reactive` to explicitly signal intent to use Reactive APIs; Spring Boot 3.3 also supports Reactive APIs in the standard Redis starter when the required classpath and compatible connection factory are present.

### 2.2. Setting Connection Properties

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
~~~

In Boot 3.x, `spring.data.redis.*` binds to `RedisProperties`. Unless configured otherwise, Boot defaults to `localhost:6379`. These properties **do not launch a Redis server**; a real Redis instance must be reachable by the application.

You can also configure via a URL:

~~~yaml
spring:
  data:
    redis:
      url: redis://localhost:6379
~~~

When `url` is set, individual `host`, `port`, `username`, and `password` properties are no longer the primary connection source as in host/port configuration. Avoid declaring both styles simultaneously and guessing which wins.

In real deployment environments, credentials should come from proper secrets or environment configuration rather than placing passwords directly into documentation or source files.

### 2.3. Using Beans Provided by Boot

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ViewCounterService {

    private final StringRedisTemplate redis;

    public ViewCounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long increment(String articleId) {
        return redis.opsForValue().increment("views:" + articleId);
    }

    public String get(String articleId) {
        return redis.opsForValue().get("views:" + articleId);
    }
}
~~~

The application does not need to write `@Bean StringRedisTemplate` manually for simple cases when auto-configuration conditions hold. `StringRedisTemplate` uses string types and string serializers suitable for this use case.

If constructor injection succeeds, we only know the bean exists and Spring selected it. When calling `increment()`, the operation can still throw errors due to a disconnected Redis server, timeouts, invalid credentials, or a command rejected by Redis.

## 3. Conditional Annotations That Govern Bean Creation

The following annotations are key to reading auto-configuration classes:

| Annotation | Meaning | Common Consequence |
|---|---|---|
| `@ConditionalOnClass(X.class)` | Applies only when the required class is on the classpath | Without Spring Data Redis, Redis auto-configuration does not activate |
| `@ConditionalOnMissingBean` | Creates the default bean only if no matching bean already exists | A user-defined bean causes Boot to back off |
| `@ConditionalOnBean(X.class)` | Requires a bean of type `X` before configuring further | Repository configuration requires a connection factory |
| `@ConditionalOnSingleCandidate(X.class)` | Requires a single injectable candidate, or multiple candidates with one `@Primary` | Two Redis factories without a primary candidate prevent default templates from being created |
| `@ConditionalOnProperty` | Depends on a property configuration, value, and specified default | Can enable/disable Redis repositories |
| `@AutoConfiguration(after = ...)` | Orders related auto-configurations | Creates the connection factory before evaluating dependent beans |

A key distinction is **by bean name** versus **by bean type**. `@ConditionalOnMissingBean(name = "redisTemplate")` asks whether a bean with the *exact name* `redisTemplate` exists, whereas an unnamed `@ConditionalOnMissingBean` on a method returning `StringRedisTemplate` typically checks whether a bean of that related type already exists.

When reading annotations, check whether they are placed on **the entire configuration class** or on a **`@Bean` method**: class-level conditions can skip registering the entire group of beans; method-level conditions affect only that method's bean.

## 4. Which Redis Beans Does Boot 3.3 Create?

### 4.1. `RedisAutoConfiguration` as the Entry Point

In Spring Boot 3.3, `org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration` includes:

- `@AutoConfiguration`: allows Boot to load it as an auto-configuration.
- `@ConditionalOnClass(RedisOperations.class)`: requires the Spring Data Redis API to be present.
- `@EnableConfigurationProperties(RedisProperties.class)`: binds `spring.data.redis.*` properties.
- `@Import(...)`: brings **Lettuce** and **Jedis** factory configurations into evaluation.

The following snippet is **abbreviated pseudocode to illustrate conditions**, not a verbatim copy of Boot's source:

~~~java
@AutoConfiguration
@ConditionalOnClass(RedisOperations.class)
@EnableConfigurationProperties(RedisProperties.class)
@Import({
    LettuceConnectionConfiguration.class,
    JedisConnectionConfiguration.class
})
class RedisAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(name = "redisTemplate")
    @ConditionalOnSingleCandidate(RedisConnectionFactory.class)
    RedisTemplate<Object, Object> redisTemplate(
            RedisConnectionFactory connectionFactory) {
        // Initialize default template
        return /* template configured with connectionFactory */;
    }

    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnSingleCandidate(RedisConnectionFactory.class)
    StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory connectionFactory) {
        return new StringRedisTemplate(connectionFactory);
    }
}
~~~

This abbreviated snippet highlights the condition structure. The `return /* ... */` line is illustrative notation and is **not meant to compile**. For runnable code, use the `@Configuration` examples in later sections.

### 4.2. `RedisConnectionFactory`: The Foundation Bean

`RedisConnectionFactory` is the abstraction Spring Data Redis uses to obtain connections to Redis. Two common implementations:

- `LettuceConnectionFactory` for Lettuce, the default driver of Boot's starter.
- `JedisConnectionFactory` when selecting Jedis with its corresponding dependency.

Boot's Lettuce/Jedis configurations register the default factory only when classpath conditions, client selection, and the absence of an existing `RedisConnectionFactory` are all met. Thus, declaring your own factory tells Boot that the application has taken responsibility for connection configuration.

~~~text
Classpath has RedisOperations
         │
         ▼
RedisAutoConfiguration
         │
         ├── Lettuce available and selected?
         │        └── Yes, no factory yet → LettuceConnectionFactory
         │
         └── Jedis available and selected?
                  └── Yes, no factory yet → JedisConnectionFactory
                              │
                              ▼
                     RedisConnectionFactory
                              │
                   ┌──────────┴──────────┐
                   ▼                     ▼
             RedisTemplate       StringRedisTemplate
~~~

If using defaults, Lettuce is usually the simplest choice. When Jedis is needed, swap the Lettuce dependency for Jedis; when both drivers are on the classpath, explicitly set `spring.data.redis.client-type` rather than relying on guesswork.

Gradle example for switching drivers:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-data-redis') {
        exclude group: 'io.lettuce', module: 'lettuce-core'
    }
    implementation 'redis.clients:jedis'
}
~~~

This is an intentional choice: if reactive Redis APIs are needed, you cannot expect Jedis to provide a `ReactiveRedisConnectionFactory` equivalent to Lettuce.

### 4.3. `RedisTemplate` and `StringRedisTemplate` Have Different Conditions

The two primary synchronous (imperative) beans follow these rules:

| Default Bean | Prerequisite | Back-off Condition |
|---|---|---|
| `redisTemplate`, type `RedisTemplate<Object, Object>` | One identifiable `RedisConnectionFactory` candidate | **No** bean named `redisTemplate` |
| `stringRedisTemplate`, type `StringRedisTemplate` | One identifiable `RedisConnectionFactory` candidate | **No** matching bean of type `StringRedisTemplate` |

Consequences:

**Case 1 — Application declares no templates:** If Boot creates a single suitable `RedisConnectionFactory`, it typically creates both `redisTemplate` and `stringRedisTemplate`.

**Case 2 — Application declares `@Bean("redisTemplate")`:** That bean claims the standard name, so Boot does not create the default `redisTemplate`. This does not automatically disable `StringRedisTemplate`.

**Case 3 — Application declares `@Bean("customRedisTemplate")` of type `RedisTemplate`:** Because the name `redisTemplate` is still unclaimed, Boot can still create the default `redisTemplate` bean. Injecting directly by `RedisTemplate` type may then encounter multiple candidates; use `@Qualifier`, `@Primary`, or clearer bean design.

**Case 4 — Application already has a `StringRedisTemplate` even under a different name:** The missing-bean condition by type is no longer met, so the default `stringRedisTemplate` is normally not created.

**Case 5 — Two factories exist without a primary candidate:** `@ConditionalOnSingleCandidate(RedisConnectionFactory.class)` fails, so default templates may be absent. This prevents Boot from guessing which factory is right.

`RedisTemplate<Object, Object>` is a generic template; do not assume it serializes every object to JSON. Its default serializer aligns with Java serialization; for shared exchange protocols or readable formats, configure serializers intentionally.

### 4.4. When Do Reactive Templates Appear?

`RedisReactiveAutoConfiguration` in Boot 3.3 runs after `RedisAutoConfiguration` and checks that the classpath contains:

- `ReactiveRedisConnectionFactory`,
- `ReactiveRedisTemplate`,
- Reactor `Flux`.

Both reactive configuration methods additionally require a `ReactiveRedisConnectionFactory` bean:

| Bean | Specific Condition |
|---|---|
| `reactiveRedisTemplate` | Reactive factory present, no bean named `reactiveRedisTemplate` |
| `reactiveStringRedisTemplate` | Reactive factory present, no bean named `reactiveStringRedisTemplate` |

Lettuce provides the needed reactive capability via `LettuceConnectionFactory`. The presence of `ReactiveRedisTemplate` **does not require the entire application to be WebFlux**; it is a condition on APIs and factories, not strictly a "reactive web app" condition.

Example reactive service:

~~~java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCounterService {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveCounterService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> increment(String key) {
        return redis.opsForValue().increment("counter:" + key);
    }
}
~~~

`Mono<Long>` represents an asynchronous operation; execution occurs upon subscription in the reactive pipeline. Never call `block()` casually inside a non-blocking pipeline.

### 4.5. Redis Repositories Are a Separate Auto-Configuration Branch

Having `RedisTemplate` does not mean Boot always creates Redis repositories for every interface. `RedisRepositoriesAutoConfiguration` has its own conditions:

- `EnableRedisRepositories` is on the classpath.
- Context contains a `RedisConnectionFactory`.
- `spring.data.redis.repositories.enabled` is `true` or omitted (enabled by default).
- No `RedisRepositoryFactoryBean` already exists causing auto-configuration to back off.

When conditions hold, Boot imports the registrar to scan and configure Redis repositories per Spring Data scanning rules.

~~~yaml
spring:
  data:
    redis:
      repositories:
        enabled: false
~~~

This configuration only disables **Redis repository auto-configuration**. `RedisConnectionFactory`, `RedisTemplate`, or `StringRedisTemplate` can still exist for direct operations.

Example repository if the application chooses this model:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.repository.CrudRepository;

@RedisHash("session")
public class SessionRecord {
    @Id
    private String id;
    private String owner;

    // Appropriate constructors, getters, and setters
}

public interface SessionRepository
        extends CrudRepository<SessionRecord, String> {
}
~~~

The example focuses on bean types and mapping annotations; in practice you must define the complete entity and decide appropriate TTL and indexing policies. `@RedisHash` is not equivalent to enabling Hibernate/JPA for Redis.

### 4.6. Is the Redis Cache Manager Always Created?

**No.** Spring Cache is a separate layer. `RedisCacheManager` depends on enabling and satisfying Spring Cache auto-configuration conditions, such as adding `@EnableCaching` and having a `RedisConnectionFactory` so Redis is chosen as the cache provider.

Having the Redis starter **does not** mean every `@Cacheable` method automatically caches in Redis. Distinguish three things:

1. **Redis templates** for issuing direct Redis commands.
2. **Redis repositories** for manipulating entities through the repository abstraction.
3. **Redis cache manager** for backing the Spring Cache abstraction.

These three branches have distinct conditions and configuration rules. That is why seeing `RedisConnectionFactory` alone does not guarantee all Redis features in an application are ready.

## 5. Defining Custom Beans So Boot Backs Off Cleanly

### 5.1. Configuring a `RedisTemplate` with Explicit Serializers

If your application uses string keys/values and wants a strongly typed template:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class RedisTemplateConfiguration {

    @Bean("redisTemplate")
    RedisTemplate<String, String> redisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, String> template = new RedisTemplate<>();
        StringRedisSerializer serializer = new StringRedisSerializer();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(serializer);
        template.setValueSerializer(serializer);
        template.setHashKeySerializer(serializer);
        template.setHashValueSerializer(serializer);

        return template;
    }
}
~~~

This bean is named `redisTemplate`, so Boot does not create another generic bean of the same name. The factory can still be auto-configured by Boot. The default `StringRedisTemplate` bean can still be created because it has a different type.

Use the standard bean name if your genuine goal is replacing Boot's default bean. If you want an additional independent template, give it a distinct name and use `@Qualifier` at injection points.

**Note on generics:** `RedisTemplate<String, String>` gives a cleaner Java API, but it does not make Redis server aware of Java types. Serializers determine the bytes sent to Redis and must stay consistent with existing data and other clients.

### 5.2. Declaring `RedisConnectionFactory` Manually

When connection requirements cannot be met via properties or customizers, the application can own the factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration(proxyBeanMethods = false)
public class RedisConnectionConfiguration {

    @Bean
    RedisConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("localhost", 6379);

        return new LettuceConnectionFactory(server);
    }
}
~~~

Once this `RedisConnectionFactory` bean is detected, Boot's default factory configuration backs off; default templates can **still** be created from the custom factory if their own conditions hold.

This is a minimal example demonstrating the mechanism, not a recommendation to move host/port from YAML into Java source. Once you create the factory manually, **do not assume all `spring.data.redis.*` properties still apply to it automatically**: you become responsible for supplying configuration, credentials, timeouts, SSL, and other needed options.

If you only need to tune Lettuce while keeping Boot's configuration mechanism, prefer `LettuceClientConfigurationBuilderCustomizer` or `ClientResourcesBuilderCustomizer` beans where appropriate. For Jedis, there is `JedisClientConfigurationBuilderCustomizer`. These extension points let you customize behavior without replacing the entire factory.

### 5.3. Two `RedisConnectionFactory` Beans: What Happens?

Suppose an application accesses two distinct Redis instances, each with its own factory:

~~~java
@Configuration(proxyBeanMethods = false)
public class TwoRedisConnections {

    @Bean("cacheRedisConnectionFactory")
    RedisConnectionFactory cacheFactory() {
        return new LettuceConnectionFactory(
                new RedisStandaloneConfiguration("cache-redis", 6379));
    }

    @Bean("sessionRedisConnectionFactory")
    RedisConnectionFactory sessionFactory() {
        return new LettuceConnectionFactory(
                new RedisStandaloneConfiguration("session-redis", 6379));
    }
}
~~~

Both hostnames in this example are illustrative; a real environment must provide reachable DNS names/endpoints.

Both beans share the `RedisConnectionFactory` type. Without one selected as primary, `@ConditionalOnSingleCandidate` for the default templates will not match. Constructor injection of `StringRedisTemplate` may fail with a missing bean error.

Two design approaches depending on intent:

- If you want one shared default factory and another used only when explicitly requested, mark exactly one factory with `@Primary`. Auto-configuration can then use the primary factory.
- If you want two independent connections, declare dedicated templates with `@Qualifier` so nothing relies on implicit selection.

Example template wired specifically to the cache factory:

~~~java
@Bean("cacheStringRedisTemplate")
StringRedisTemplate cacheStringRedisTemplate(
        @Qualifier("cacheRedisConnectionFactory")
        RedisConnectionFactory factory) {
    return new StringRedisTemplate(factory);
}
~~~

This snippet is a method intended for a `@Configuration` class with appropriate imports for `@Bean`, `@Qualifier`, `StringRedisTemplate`, and `RedisConnectionFactory`. Each dedicated template should follow clear naming conventions so services receive the right connection.

If a user-defined `StringRedisTemplate` bean is created first, auto-configuration normally backs off for that type. Avoid relying on Boot creating a second `stringRedisTemplate` once you explicitly define one.

### 5.4. Do Not Use `@Primary` to Mask Unclear Configuration

`@Primary` resolves default candidate selection for dependency injection; it does not partition data, route requests to the right Redis automatically, or ensure repositories/caches use the intended template. When multiple Redis instances serve distinct roles, wire connections by explicit name per functional group and also review repository and cache configuration.

In large systems, "two `RedisConnectionFactory` beans + one implicit template" is usually far more error-prone than "each Redis has explicit template and repository wiring."

## 6. Reading Condition Evaluation Results Instead of Guessing

### 6.1. Starting with the Condition Evaluation Report

Run the Spring Boot application in debug mode:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot prints the **Condition Evaluation Report**, listing matched and unmatched condition groups. Search for these names:

~~~text
RedisAutoConfiguration
LettuceConnectionConfiguration
JedisConnectionConfiguration
RedisReactiveAutoConfiguration
RedisRepositoriesAutoConfiguration
~~~

Example log interpretation (illustrative, not fixed output):

~~~text
RedisAutoConfiguration matched:
  @ConditionalOnClass found RedisOperations

RedisAutoConfiguration#redisTemplate did not match:
  @ConditionalOnMissingBean found bean named 'redisTemplate'
~~~

Meaning: Spring Data Redis is present so the configuration class was evaluated, while the default `redisTemplate` factory method backed off because the application already defined a bean with that name. **"Did not match" is not necessarily an error**; it may be the exact desired outcome.

If Spring Boot Actuator is enabled and permitted, `/actuator/conditions` also exposes the report as JSON. Only enable exposure in appropriate administrative environments:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
~~~

The conditions endpoint can reveal internal application structure and must be protected by network and security controls. Never expose it publicly just for production debugging.

### 6.2. Inspecting Which Beans Actually Exist in the Context

You can write a small observer bean to check candidates at startup:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;

@Component
public class RedisBeanInspector implements ApplicationRunner {

    private final ApplicationContext context;

    public RedisBeanInspector(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        System.out.println("Factories: " + Arrays.toString(
                context.getBeanNamesForType(RedisConnectionFactory.class)));
        System.out.println("Redis templates: " + Arrays.toString(
                context.getBeanNamesForType(RedisTemplate.class)));
        System.out.println("String templates: " + Arrays.toString(
                context.getBeanNamesForType(StringRedisTemplate.class)));
    }
}
~~~

This is a temporary diagnostic snippet for learning/development; do not keep `System.out.println` in production code. This check answers **whether beans are registered**, not whether an actual Redis command succeeds.

To verify connectivity, execute a controlled operation and clearly separate network, authentication, and timeout failures from missing-bean errors. You can also inspect Actuator's Redis health indicator when configured.

### 6.3. Quick Lookup Flowchart When Injection Fails

~~~mermaid
flowchart TD
    A["StringRedisTemplate injection fails"] --> B{"Is RedisOperations on classpath?"}
    B -->|No| C["Check starter/dependencies"]
    B -->|Yes| D{"Is there a RedisConnectionFactory?"}
    D -->|No| E["Check driver, factory config, condition report"]
    D -->|Yes| F{"Multiple factories without a clear primary?"}
    F -->|Yes| G["Use @Primary or dedicated templates + @Qualifier"]
    F -->|No| H{"User-defined StringRedisTemplate already exists?"}
    H -->|Yes| I["Check name, type, qualifier, and context scope"]
    H -->|No| J["Read conditions of RedisAutoConfiguration#stringRedisTemplate"]
~~~

When tracing a failure, start from **the specific missing bean** and work backward through its dependencies. A message like "No qualifying bean of type StringRedisTemplate" is a context and condition issue; "RedisConnectionFailureException" or runtime timeouts are connectivity issues.

## 7. Common Configuration Errors

| Symptom | Likely Cause to Check | How to Reason About It |
|---|---|---|
| Cannot inject `StringRedisTemplate` | Missing starter, excluded auto-config, missing factory, multiple factories | Look up `RedisAutoConfiguration#stringRedisTemplate` in the condition report |
| Boot still creates `redisTemplate` despite custom template | Custom bean was given a name other than `redisTemplate` | The default `redisTemplate` condition checks **name** |
| No bean named `stringRedisTemplate`, yet another `StringRedisTemplate` exists | Application-provided bean of this type caused Boot to back off | Check `@ConditionalOnMissingBean` by type |
| Ambiguous `RedisConnectionFactory` injection | Two factories without a clear selection | Use `@Qualifier` or intentionally design `@Primary` |
| Redis repositories not registered | `repositories.enabled=false`, missing classpath, missing factory, or wrong scan scope | Check `RedisRepositoriesAutoConfiguration` and scan packages |
| Only synchronous templates present, no reactive templates | Missing reactive API/factory or using unsupported driver | Check `RedisReactiveAutoConfiguration` and `ReactiveRedisConnectionFactory` |
| App starts up, but Redis commands fail | Redis not running, wrong host, credentials, network, timeout | Test connectivity independently from bean registration |
| Changed YAML, yet connections still target the old address | Custom factory created manually without reading Boot properties | Inspect factory definitions in the application |
| Redis properties have no effect | Wrong prefix for the Spring Boot line or profile override | For Boot 3.x, check `spring.data.redis.*` and effective configuration |

One easily overlooked mistake is **misnaming a bean**. If you create an unrelated bean named `redisTemplate` with an incompatible type, Boot may still treat that name as taken, preventing the expected template from being created. Never reuse standard bean names for objects with a different meaning.

Another case involves applications using multiple `ApplicationContext` instances (parent/child) or custom auto-configuration imports/exclusions. Bean conditions are evaluated within each context and annotation matching rules; in complex setups, checking the condition report is far more reliable than just counting classes on the classpath.

## 8. Four Thought Experiments on Bean Creation Rules

To predict outcomes accurately, assume Spring Data Redis and Lettuce are on the classpath and Boot's Redis auto-configuration is not excluded.

**Experiment 1: Declare no Redis `@Bean` definitions at all.**

Boot can auto-configure a `LettuceConnectionFactory` and from it create `redisTemplate` and `stringRedisTemplate`. If reactive APIs/factories meet their conditions, reactive templates can also appear. Even then, the real Redis server may still not be ready.

**Experiment 2: Create a bean named `redisTemplate`.**

Boot keeps your bean and skips its default `redisTemplate` method. `StringRedisTemplate` is not disabled solely because a generic `RedisTemplate` exists, because its condition checks its own type.

**Experiment 3: Create two `RedisConnectionFactory` beans without `@Primary`.**

Boot cannot select a single factory for methods guarded by `@ConditionalOnSingleCandidate`, so default templates should not be expected. Mark one primary candidate or declare explicit templates using `@Qualifier` for each factory.

**Experiment 4: Set `spring.data.redis.repositories.enabled=false`.**

The repository auto-configuration branch stops, while the factory and templates can still be created normally by Boot. Disabling repositories does not mean disabling Redis.

These experiments clarify the three decision layers: **libraries present → foundation bean eligible → dependent beans permitted**.

## 9. Principles to Follow When Starting a Spring Data Redis Module

1. **Add only the starter and `spring.data.redis.*` settings before writing a custom factory.** This lets Spring Boot manage common setup and makes default beans easy to inspect.
2. **Choose the API for your use case:** `StringRedisTemplate` for string data, a `RedisTemplate` with explicit serializers for other types, and reactive templates for reactive pipelines.
3. **Read the annotations on each bean:** default `redisTemplate` checks *name*, `StringRedisTemplate` checks *type*, and both require a single factory candidate in Boot 3.3.
4. **Override only what you truly need:** customizers for driver tuning, custom template beans for different serializers, and a custom factory only when connection requirements exceed property support.
5. **With multiple factories, make wiring explicit:** bean names, `@Qualifier`, `@Primary`, and each repository/cache's target connection must be clear.
6. **Separate auto-configuration failures from runtime Redis errors:** having beans does not mean the server is connected; read `ConditionEvaluationReport` before changing dependencies blindly.
7. **Remember version effects:** property names, conditions, and packages can change across Spring Boot lines; consult documentation matching your application's version.

Spring Boot auto-configuration lets us bootstrap Redis with very little code, and its reliability comes from **inspectable conditions**. Understanding `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnSingleCandidate`, and the Redis auto-configuration branches allows you to predict which beans will appear, override defaults cleanly, and trace mismatches quickly.

## References

- [Spring Boot 3.3 — Working with NoSQL Technologies: Redis](https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html)
- [Spring Boot 3.3 API — RedisAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/data/redis/RedisAutoConfiguration.html)
- [Spring Boot 3.3 API — RedisReactiveAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/data/redis/RedisReactiveAutoConfiguration.html)
- [Spring Boot 3.3 API — RedisRepositoriesAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/data/redis/RedisRepositoriesAutoConfiguration.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 Actuator — Conditions Evaluation Report](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html)
