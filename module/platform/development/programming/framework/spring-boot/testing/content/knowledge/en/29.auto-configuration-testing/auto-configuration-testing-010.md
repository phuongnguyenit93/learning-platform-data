# Testing Binding, Validation, and Default Values of Configuration Properties

## 1. Problem: configuration is a contract of auto-configuration

In Spring Boot, a library can read settings from `application.properties`, YAML, environment variables, and other property sources and bind them into a Java object via `@ConfigurationProperties`. Beans created by `@AutoConfiguration` often use that object to set URLs, timeouts, retries, pool sizes, feature toggles, and operational choices.

If testing is incomplete, bugs may surface only after deployment: a typo causes a value to fall back to default; `500ms` accidentally binds as 500 seconds; a nested setting is never validated; a feature marked `enabled=true` in a JavaBean still fails to create its conditional bean; or auto-configuration overwrites a bean the application already defined itself.

**Three distinct questions must be tested:**

1. **Binding:** is the key mapped to the right Java property and converted to the right type?
2. **Validation:** do missing, blank, wrong-type, and out-of-range values fail the context per contract?
3. **Defaults/conditions:** when keys are missing, are defaults right, can they be overridden, and does the auto-config bean get created or back off properly?

A test like `assertThat(new ClientProperties().getTimeout()).isEqualTo(Duration.ofSeconds(3))` only proves the Java field initializer; it **does not** prove Spring Boot Binder, Jakarta Bean Validation, and auto-configuration work.

### Learning goals

After this lesson, you can use `ApplicationContextRunner` to test binding, validation, and defaults in a Spring Boot auto-configuration; distinguish `BindException` from `BindValidationException`; test JavaBean/record defaults, relaxed binding, nested properties, `@ConditionalOnProperty`, and `@ConditionalOnMissingBean`; understand limitations of ContextRunner versus `@SpringBootTest`; and work with a Java 17+ / Spring Boot 3.5.x example containing **18 JUnit Jupiter test methods**.

**Sample versions:** Java 17+, Spring Boot **3.5.16**, Spring Framework 6.x, Jakarta Bean Validation, JUnit Jupiter, and AssertJ. Spring Boot 4.x changes some test starters/packages, so match against your version rather than copying 3.5 imports blindly.

## 2. Configuration flow from source to bean

```text
 application.properties / application.yaml / OS environment
          / Java system properties / CLI arguments
                            |
                            v
                Spring Environment
                  PropertySources
                            |
                            v
                 Spring Boot Binder
                 relaxed key matching
                 + type conversion
                            |
                            v
               @ConfigurationProperties
              JavaBean / record / constructor
                            |
                            v
              @Validated + @Valid cascade
                            |
                   +--------+--------+
                   |                 |
                 invalid           valid
                   |                 |
             startup failure        v
                              @AutoConfiguration
                              @Conditional...
                                    |
                                    v
                             application bean
```

**Note the boundaries:**

- The Binder converts text into types such as `Duration`, `URI`, `int`, `boolean`, and collections.
- Validation enforces semantics declared by the developer (e.g., retry count between 1 and 8).
- Conditional annotations typically read `Environment` or bean definitions, not field initializers directly.
- Context startup succeeding **does not** prove a real HTTP client/network or database operates properly; it proves configuration/wiring within context scope.
- A full `SpringApplication` also performs ConfigData/profile loading that `ApplicationContextRunner` does not fully replicate automatically.

### 2.1. Minimum matrix

| Category | Input | Expected |
|---|---|---|
| Default | Supply only required key | Bean valid, defaults right |
| Override | `timeout=750ms` | `Duration.ofMillis(750)` |
| Relaxed binding | `maxAttempts=4` | Java field `maxAttempts=4` |
| Nested | `pool.size=12` | Nested object receives 12 |
| Validation | `max-attempts=0` | Startup fails |
| Conversion | `max-attempts=banana` | Startup fails because conversion fails |
| Required | Omit `service-name` | Startup fails with `@NotBlank` |
| Blank | `service-name=   ` | Startup fails with `@NotBlank` |
| Disabled | `enabled=false` | Properties still bind, conditional client absent |
| User override | User defines client bean | Auto-configuration backs off |
| Unknown key | Typo, strict mode | Startup fails instead of silently using default |

## 3. `@ConfigurationProperties`, `@Value`, and relaxed binding

`@ConfigurationProperties(prefix="demo.client")` registers a group of type-safe settings. It fits starters/libraries with multiple related keys. `@Value` works well for single values, yet lacks the nested type-safe binding, generated metadata, and relaxed binding of a properties type.

Example:

```properties
demo.client.service-name=orders
demo.client.timeout=750ms
demo.client.max-attempts=4
demo.client.pool.size=12
demo.client.tags=blue,green
```

The Spring Boot binder normally maps `max-attempts` to JavaBean `maxAttempts`. In properties sources, publish keys in **lowercase kebab-case**. CamelCase `demo.client.maxAttempts` can bind thanks to relaxed binding; however, environment variable naming has its own rules: typically replacing dots with underscores, stripping hyphens, and uppercasing. `demo.client.max-attempts` becomes `DEMO_CLIENT_MAXATTEMPTS`, **not automatically** equivalent to arbitrary underscored forms inside words.

A runner with `withPropertyValues("demo.client.maxAttempts=4")` tests a map-based property source; it is **not** an actual test of OS environment variables. When verifying env names/precedence, use a real environment/subprocess or a `SystemEnvironmentPropertySource` in a dedicated test.

### 3.1. Wrong type vs out-of-range value

- `max-attempts=banana`: Binder cannot convert String to `int`, typically producing `BindException` in the cause chain.
- `max-attempts=0`: converts to `int` cleanly yet `@Min(1)` rejects it; `BindValidationException` signals a validation failure.
- `timeout=not-a-duration`: conversion error.
- `timeout=PT0S`: converts cleanly to `Duration.ZERO`; `@NotNull` **does not** forbid 0. If business logic requires a positive timeout, add an appropriate constraint or custom validator.

Never combine multiple invalid inputs into a single test case, because when the context fails you will not know precisely which one was rejected.

## 4. Default values: JavaBean, `@DefaultValue`, and `Environment`

### 4.1. JavaBean initializer

```java
private Duration timeout = Duration.ofSeconds(3);
private int maxAttempts = 2;
private boolean enabled = true;
```

When a key is not provided, the JavaBean field initializer is preserved; when the key has a valid value, the Binder overrides it via the setter. Always test **both absent and explicit override**; testing `new Props()` measures only the initializer, not binding.

### 4.2. Record/constructor binding

For records in Spring Boot 3.x, `@DefaultValue` goes on record components/constructor parameters. This standalone snippet illustrates immutable binding (not a file in the main demo):

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties("demo.worker")
public record WorkerOptions(
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("3") int retries,
        @DefaultValue Pool pool
) {
    public record Pool(@DefaultValue("4") int size) {}
}
```

To use a constructor-bound type, register it with `@EnableConfigurationProperties` or configuration properties scanning. **Do not** annotate the record with `@Component` expecting Boot to treat it as binder-driven constructor binding. Records with a single canonical constructor generally need no `@ConstructorBinding` in Boot 3.x. With nested constructor binding, a no-arg `@DefaultValue` may be needed to instantiate the nested object when nested properties are absent.

### 4.3. Defaults in files vs defaults in beans

```properties
demo.client.timeout=3s
demo.client.enabled=true
```

A default in `application.properties` exists in `Environment`. Conversely, Spring Boot documentation confirms **defaults defined in `@ConfigurationProperties` are not automatically reflected back into `Environment`**.

Hence in a JavaBean:

```java
private boolean enabled = true;
```

when the user has not set `demo.client.enabled`:

- `properties.isEnabled()` is true;
- `environment.containsProperty("demo.client.enabled")` may be false;
- `@ConditionalOnProperty(havingValue="true")` **does not automatically read this Java default**.

That is why, if the client must be created by default, you use `matchIfMissing=true` or align the default configuration source with the condition.

### 4.4. Absent vs explicit empty/false/zero

| Configuration | Meaning |
|---|---|
| Key absent | Keeps JavaBean initializer / record `@DefaultValue` |
| `enabled=false` | Overrides true to false |
| `max-attempts=0` | Binds 0 then violates `@Min(1)` |
| `service-name=` | Blank string, rejected by `@NotBlank` |
| `timeout=` | Present empty key; conversion/null semantics must be tested |
| `tags=` | May produce an empty collection per converter; do not infer from absent |
| `pool.size=0` | Nested constraint rejects if `@Valid` cascades |
| Unknown key | Ignored by default or rejected in strict mode |

## 5. Jakarta Bean Validation with `@Validated` and `@Valid`

Spring Boot 3.5 requires a Jakarta Bean Validation provider on the classpath when using constraint annotations on `@ConfigurationProperties`. Typically add `spring-boot-starter-validation`, which brings Hibernate Validator. Imports in Boot 3.x start with `jakarta.validation`, not `javax.validation` as seen in older Boot 2 tutorials.

- `@NotBlank`: String is non-null and not whitespace-only.
- `@NotNull`: reference is non-null; does not validate URI scheme or positive `Duration`.
- `@NotEmpty`: collection/string must have at least one element/character.
- `@Min(1)`, `@Max(8)`: numeric boundaries.
- `@Size`, `@Pattern`: additional constraints.
- `@Valid`: required to **cascade validation into nested objects**.
- `@Validated`: enables validation for the configuration properties type per Spring Boot.

Example:

```java
@ConfigurationProperties(prefix = "demo.client")
@Validated
public class ExampleProperties {
    @NotBlank
    private String serviceName;
    @Min(1)
    private int retries = 2;
    @Valid
    private final Pool pool = new Pool();
    // JavaBean getters/setters and Pool class follow...
}
```

This snippet is not a standalone runnable Java file; the full implementation is in section 9.

### 5.1. Why does `@Valid` matter?

If an outer properties bean has `@Validated` and a nested object has `@Min(1)`, the validator **does not necessarily** validate the nested field unless the outer field carries `@Valid`. Happy-path tests like `pool.size=4` will not catch a missing cascade. Only a negative test like `pool.size=0` can catch a regression when `@Valid` is removed.

A pre-initialized nested POJO with a getter and JavaBean setters for child fields binds normally; `@NestedConfigurationProperty` primarily assists metadata generation when describing external nested types, and is not the switch that enables validation.

### 5.2. Failing context is expected behavior

Invalid configuration should fail-fast **before the app accepts traffic**. Testing with `ContextRunner` can assert context failure, inspect the cause chain, and confirm the right error branch. Do not add `ignoreInvalidFields=true` merely to keep startup succeeding when timeout/retry/security settings matter: it can mask broken config and leave the app running on unintended defaults.

## 6. Unknown keys: lenient or strict?

`@ConfigurationProperties` defaults to `ignoreUnknownFields=true`. A typo like `demo.client.max-attemps=5` (missing `t`) could be silently ignored, leaving `maxAttempts` at its default 2 without operators noticing.

The demo chooses **strict**:

```java
@ConfigurationProperties(
        prefix = "demo.client",
        ignoreUnknownFields = false
)
```

Testing `demo.client.max-attemps=4` must make the context fail. This is an intentional choice; for starters spanning multiple versions or complex property sources, strictness can introduce incompatibilities. Decide based on migration/versioning policy rather than assuming one setting fits every product.

Never confuse `ignoreUnknownFields` (an unmapped key) with `ignoreInvalidFields` (an unconvertible value). They are two separate flags.

## 7. When to use `ApplicationContextRunner`?

Spring Boot recommends `ApplicationContextRunner` when testing auto-configuration. The runner builds a small `ApplicationContext` per case, accepts property values and user configs, and lets you assert bean conditions and capture startup failures.

```java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    DemoClientAutoConfiguration.class));

@Test
void defaultCase() {
    runner.withPropertyValues(
            "demo.client.service-name=orders")
          .run(context -> {
              assertThat(context).hasNotFailed();
              assertThat(context)
                      .hasSingleBean(DemoClientProperties.class);
          });
}
```

This is a condensed excerpt from the full test class below.

**Advantages:** fast, no HTTP server needed, easy to vary individual properties, simulates user-defined beans with `withUserConfiguration`, and simulates missing classpaths with `FilteredClassLoader` when needed.

**Limitations:** `ApplicationContextRunner` does not automatically run the full `SpringApplication` ConfigData pipeline or read YAML profiles like a full Boot startup. For auto-configurations depending on Servlet/Reactive contexts, use `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner`. Boot docs note limitations of `ApplicationContextRunner` when running native image tests.

## 8. Demo design and versions

This lesson creates a starter-like auto-configuration for `DemoHttpClient` (a record holding values, **making no real HTTP calls**).

| Key | Type | Default | Constraint |
|---|---|---|---|
| `demo.client.service-name` | String | None | `@NotBlank` |
| `demo.client.endpoint` | URI | https://api.example.invalid | `@NotNull` |
| `demo.client.timeout` | Duration | 3s | `@NotNull` |
| `demo.client.max-attempts` | int | 2 | `@Min(1)`, `@Max(8)` |
| `demo.client.enabled` | boolean | true | type conversion |
| `demo.client.tags` | List String | ["default"] | `@NotEmpty` |
| `demo.client.pool.size` | nested int | 4 | `@Min(1)`, `@Max(32)` |

Auto-configuration policy:

- Properties bean is registered and validated via `@EnableConfigurationProperties`.
- Client bean is created when `enabled` is absent or true.
- When `enabled=false`, client bean is not created, while properties bean still binds/validates.
- When user defines their own client bean, default auto-config must back off.
- Unknown keys under the prefix are rejected due to `ignoreUnknownFields=false`.

### 8.1. Build file using Gradle Groovy DSL

`build.gradle` for Spring Boot 3.5.16 / Java 17:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    annotationProcessor(
            'org.springframework.boot:spring-boot-configuration-processor')

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Gradle Wrapper files are generated separately by Gradle or the IDE. If using Maven, the equivalent requires the Spring Boot 3.5 parent/BOM, `spring-boot-starter`, `spring-boot-starter-validation`, and `spring-boot-starter-test` in `test` scope, using Surefire/JUnit Platform appropriately. Never mix dependencies managed by different major Boot versions.

### 8.2. Project structure

```text
src/
├── main/
│   ├── java/com/example/autoconfig/
│   │   ├── DemoClientProperties.java
│   │   ├── DemoHttpClient.java
│   │   └── DemoClientAutoConfiguration.java
│   ├── java/com/example/demoapp/
│   │   └── DemoApplication.java
│   └── resources/
│       ├── application.properties
│       └── META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── test/java/com/example/autoconfig/
    └── DemoClientAutoConfigurationTest.java
```

Separating `com.example.autoconfig` from the component-scanning root `com.example.demoapp` ensures Boot loads auto-configuration via `AutoConfiguration.imports`, rather than scanning it like a regular `@Configuration` class.

## 9. Complete production code

### 9.1. Properties bean with defaults and validation

**File `src/main/java/com/example/autoconfig/DemoClientProperties.java`:**

```java
package com.example.autoconfig;

import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(
        prefix = "demo.client",
        ignoreUnknownFields = false
)
@Validated
public class DemoClientProperties {

    @NotBlank
    private String serviceName;

    @NotNull
    private URI endpoint =
            URI.create("https://api.example.invalid");

    @NotNull
    private Duration timeout = Duration.ofSeconds(3);

    @Min(1)
    @Max(8)
    private int maxAttempts = 2;

    private boolean enabled = true;

    @NotEmpty
    private List<String> tags =
            new ArrayList<>(List.of("default"));

    @Valid
    private final Pool pool = new Pool();

    public String getServiceName() {
        return serviceName;
    }

    public void setServiceName(String serviceName) {
        this.serviceName = serviceName;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public Pool getPool() {
        return pool;
    }

    public static class Pool {

        @Min(1)
        @Max(32)
        private int size = 4;

        public int getSize() {
            return size;
        }

        public void setSize(int size) {
            this.size = size;
        }
    }
}
```

**Technical notes:**

- `serviceName` is required with no initializer. `@NotBlank` catches missing and blank.
- `endpoint` defaults to a `.invalid` domain URI, never connecting to an external service. `@NotNull` does not verify an HTTPS scheme or valid hostname; add a custom constraint if required.
- `timeout` defaults to 3 seconds, though `@NotNull` does not prohibit `Duration.ZERO`.
- `maxAttempts` is constrained by `@Min`/`@Max`.
- `tags` uses a mutable `ArrayList` and setter so the binder can replace list values; it does not merge defaults `["default"]` with overrides `["blue","green"]`.
- `pool` is pre-initialized, has a getter, a `@Valid` field for nested validation, and `size` getter/setter.
- `ignoreUnknownFields=false` is this example's strict choice; the annotation default is true.
- Never use static fields to hold bound configuration.

### 9.2. Sample client bean

**File `src/main/java/com/example/autoconfig/DemoHttpClient.java`:**

```java
package com.example.autoconfig;

import java.net.URI;
import java.time.Duration;

public record DemoHttpClient(
        String serviceName,
        URI endpoint,
        Duration timeout,
        int maxAttempts,
        int poolSize
) {}
```

This is an immutable record used to observe values passed from properties to the auto-configured bean, **performing no network requests**. This test cannot prove actual HTTP timeouts, retry behavior, or connection pools work; test those against the real client implementation.

### 9.3. Auto-configuration and conditions

**File `src/main/java/com/example/autoconfig/DemoClientAutoConfiguration.java`:**

```java
package com.example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(DemoClientProperties.class)
public class DemoClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(DemoHttpClient.class)
    @ConditionalOnProperty(
            prefix = "demo.client",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    DemoHttpClient demoHttpClient(DemoClientProperties props) {
        return new DemoHttpClient(
                props.getServiceName(),
                props.getEndpoint(),
                props.getTimeout(),
                props.getMaxAttempts(),
                props.getPool().getSize());
    }
}
```

**Clear distinction:**

- `@EnableConfigurationProperties` registers/binds/validates the properties type whenever the auto-config class is loaded.
- `@ConditionalOnProperty` decides whether to create the client bean; it reads `Environment`. `matchIfMissing=true` matches default `enabled=true`.
- `@ConditionalOnMissingBean` prevents auto-config from overriding an application-defined bean.
- `enabled=false` **does not** prevent registering the properties bean in this design, so required fields still validate even when the client bean is suppressed.
- Classpath conditions can be added if real auto-configuration depends on optional libraries; write separate tests for `@ConditionalOnClass`.

### 9.4. `AutoConfiguration.imports` and `SpringBootApplication`

**File `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:**

```text
com.example.autoconfig.DemoClientAutoConfiguration
```

**File `src/main/java/com/example/demoapp/DemoApplication.java`:**

```java
package com.example.demoapp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**File `src/main/resources/application.properties`:**

```properties
demo.client.service-name=orders
```

Spring Boot's production boot path reads `AutoConfiguration.imports` and loads the class as an auto-config candidate. `ContextRunner` tests in section 10 **explicitly select that class** via `AutoConfigurations.of` and do not automatically read `application.properties` like `SpringApplication`.

## 10. JUnit suite testing binding, validation, defaults, and conditions

**File `src/test/java/com/example/autoconfig/DemoClientAutoConfigurationTest.java`:**

```java
package com.example.autoconfig;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.validation.BindValidationException;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DemoClientAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            DemoClientAutoConfiguration.class));

    private ApplicationContextRunner valid() {
        return runner.withPropertyValues(
                "demo.client.service-name=orders");
    }

    private static boolean containsCause(
            Throwable root, Class<? extends Throwable> kind) {
        for (Throwable e = root; e != null; e = e.getCause()) {
            if (kind.isInstance(e)) {
                return true;
            }
        }
        return false;
    }

    private static void validationFails(
            AssertableApplicationContext context) {
        assertThat(context).hasFailed();
        assertThat(containsCause(
                context.getStartupFailure(),
                BindValidationException.class)).isTrue();
    }

    private static void bindingFails(
            AssertableApplicationContext context) {
        assertThat(context).hasFailed();
        assertThat(containsCause(
                context.getStartupFailure(),
                BindException.class)).isTrue();
    }

    @Test
    void defaultsAreBoundWhenOptionalKeysAreMissing() {
        valid().run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .hasSingleBean(DemoClientProperties.class);
            assertThat(context)
                    .hasSingleBean(DemoHttpClient.class);

            DemoClientProperties p =
                    context.getBean(DemoClientProperties.class);
            assertThat(p.getServiceName()).isEqualTo("orders");
            assertThat(p.getEndpoint()).isEqualTo(
                    URI.create("https://api.example.invalid"));
            assertThat(p.getTimeout()).isEqualTo(
                    Duration.ofSeconds(3));
            assertThat(p.getMaxAttempts()).isEqualTo(2);
            assertThat(p.isEnabled()).isTrue();
            assertThat(p.getTags()).containsExactly("default");
            assertThat(p.getPool().getSize()).isEqualTo(4);

            DemoHttpClient client =
                    context.getBean(DemoHttpClient.class);
            assertThat(client.timeout())
                    .isEqualTo(Duration.ofSeconds(3));
            assertThat(client.maxAttempts()).isEqualTo(2);
            assertThat(client.poolSize()).isEqualTo(4);
        });
    }

    @Test
    void javaDefaultsAreNotAutomaticallyEnvironmentProperties() {
        valid().run(context -> {
            assertThat(context).hasNotFailed();
            DemoClientProperties p =
                    context.getBean(DemoClientProperties.class);

            assertThat(p.isEnabled()).isTrue();
            assertThat(p.getMaxAttempts()).isEqualTo(2);
            assertThat(context.getEnvironment()
                    .containsProperty("demo.client.enabled"))
                    .isFalse();
            assertThat(context.getEnvironment()
                    .containsProperty("demo.client.max-attempts"))
                    .isFalse();
            assertThat(context)
                    .hasSingleBean(DemoHttpClient.class);
        });
    }

    @Test
    void explicitOverridesConvertAndReachClient() {
        valid().withPropertyValues(
                "demo.client.endpoint=https://stage.example.invalid:8443",
                "demo.client.timeout=750ms",
                "demo.client.max-attempts=5",
                "demo.client.tags=blue,green",
                "demo.client.pool.size=12"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            DemoClientProperties p =
                    context.getBean(DemoClientProperties.class);

            assertThat(p.getEndpoint()).isEqualTo(
                    URI.create("https://stage.example.invalid:8443"));
            assertThat(p.getTimeout()).isEqualTo(
                    Duration.ofMillis(750));
            assertThat(p.getMaxAttempts()).isEqualTo(5);
            assertThat(p.getTags())
                    .containsExactly("blue", "green");
            assertThat(p.getPool().getSize()).isEqualTo(12);

            DemoHttpClient client =
                    context.getBean(DemoHttpClient.class);
            assertThat(client.endpoint()).isEqualTo(p.getEndpoint());
            assertThat(client.timeout()).isEqualTo(p.getTimeout());
            assertThat(client.maxAttempts()).isEqualTo(5);
            assertThat(client.poolSize()).isEqualTo(12);
        });
    }

    @Test
    void relaxedCamelCaseKeysBind() {
        runner.withPropertyValues(
                "demo.client.serviceName=billing",
                "demo.client.maxAttempts=4"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            DemoClientProperties p =
                    context.getBean(DemoClientProperties.class);
            assertThat(p.getServiceName()).isEqualTo("billing");
            assertThat(p.getMaxAttempts()).isEqualTo(4);
        });
    }

    @Test
    void minAndMaxBoundsAreInclusive() {
        for (int count : new int[] {1, 8}) {
            valid().withPropertyValues(
                    "demo.client.max-attempts=" + count,
                    "demo.client.pool.size=32"
            ).run(context -> {
                assertThat(context).hasNotFailed();
                DemoClientProperties p =
                        context.getBean(DemoClientProperties.class);
                assertThat(p.getMaxAttempts()).isEqualTo(count);
                assertThat(p.getPool().getSize()).isEqualTo(32);
            });
        }
    }

    @Test
    void missingRequiredServiceNameFails() {
        runner.run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void blankServiceNameFails() {
        runner.withPropertyValues(
                "demo.client.service-name=   "
        ).run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void maxAttemptsZeroFails() {
        valid().withPropertyValues(
                "demo.client.max-attempts=0"
        ).run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void maxAttemptsNineFails() {
        valid().withPropertyValues(
                "demo.client.max-attempts=9"
        ).run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void malformedIntegerFailsConversion() {
        valid().withPropertyValues(
                "demo.client.max-attempts=not-a-number"
        ).run(DemoClientAutoConfigurationTest
                ::bindingFails);
    }

    @Test
    void malformedDurationFailsConversion() {
        valid().withPropertyValues(
                "demo.client.timeout=not-a-duration"
        ).run(DemoClientAutoConfigurationTest
                ::bindingFails);
    }

    @Test
    void nestedPoolZeroFailsValidation() {
        valid().withPropertyValues(
                "demo.client.pool.size=0"
        ).run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void nestedPoolThirtyThreeFailsValidation() {
        valid().withPropertyValues(
                "demo.client.pool.size=33"
        ).run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void explicitFalseDisablesClientButNotProps() {
        valid().withPropertyValues(
                "demo.client.enabled=false"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .hasSingleBean(DemoClientProperties.class);
            assertThat(context)
                    .doesNotHaveBean(DemoHttpClient.class);
            assertThat(context.getBean(
                    DemoClientProperties.class).isEnabled())
                    .isFalse();
        });
    }

    @Test
    void malformedBooleanFailsConversion() {
        valid().withPropertyValues(
                "demo.client.enabled=not-a-boolean"
        ).run(DemoClientAutoConfigurationTest
                ::bindingFails);
    }

    @Test
    void unknownKeyFailsInStrictMode() {
        valid().withPropertyValues(
                "demo.client.max-attemps=4"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
    }

    @Test
    void requiredPropertiesValidateEvenWhenFeatureDisabled() {
        runner.withPropertyValues(
                "demo.client.enabled=false"
        ).run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void customClientMakesAutoConfigurationBackOff() {
        valid().withUserConfiguration(
                CustomClientConfiguration.class
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DemoHttpClient.class);
            assertThat(context.getBean(
                    DemoHttpClient.class).serviceName())
                    .isEqualTo("custom");
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {

        @Bean
        DemoHttpClient customClient() {
            return new DemoHttpClient(
                    "custom",
                    URI.create("https://custom.example.invalid"),
                    Duration.ofSeconds(7),
                    1,
                    5);
        }
    }
}
```

**Exactly 18 `@Test` methods**, excluding helpers and nested configuration. The suite uses no `@SpringBootTest`, opens no sockets, connects to no external APIs, and gives each runner invocation an independent context.

### 10.1. Test groupings

| Group | Test count | Coverage |
|---|---:|---|
| Default values and Environment | 2 | JavaBean defaults, `matchIfMissing`, keys do not auto-appear in `Environment` |
| Valid overrides and relaxed names | 3 | URI/Duration/List/nested, camelCase, inclusive min/max |
| Required fields and numeric constraint violations | 4 | Missing/blank `serviceName`, count 0/9 |
| Conversion errors | 3 | Unconvertible Integer, Duration, boolean |
| Nested Bean Validation | 2 | Pool size 0/33 |
| Conditional client | 1 | `enabled=false`, properties still exist |
| Strict unknown key | 1 | Typo rejected |
| Validation when disabled | 1 | Required config still fails since props register unconditionally |
| User override | 1 | `@ConditionalOnMissingBean` back-off |
| **Total** | **18** | Distinct context states |

### 10.2. Why does the helper walk the cause chain?

Spring may wrap failures in `BeanCreationException` or `ConfigurationPropertiesBindException`, while `BindValidationException` sits deeper down. Tests matching verbatim messages like `must be greater than or equal to 1` easily break if Hibernate Validator changes locale or phrasing, even though validation works. The `containsCause` helper finds the actual exception type along `Throwable.getCause()` and is more resilient.

For complex tests, inspect structured property paths/constraint violations too. In the demo each test intentionally changes **a single input**, keeping startup failure causes clear. In another environment, if the cause chain differs due to versions/custom validators, inspect the actual root cause rather than simply dropping the assertion.

### 10.3. What do the demo's conditions mean?

`@ConditionalOnProperty` reads `Environment`, not JavaBean defaults. `matchIfMissing=true` aligns with default `enabled=true`. `@EnableConfigurationProperties` sits on the auto-config class, so even when the client bean's condition is false, properties still bind and validate.

If a real design wants **a disabled feature not to require `service-name`**, place conditions on the properties bean registration scope as well, or use validation groups/conditional registration. When changing the design, **update tests** to match the new contract rather than assuming one policy is universal.

## 11. How to run and read reports

Linux/macOS:

```bash
./gradlew test --tests "com.example.autoconfig.DemoClientAutoConfigurationTest"

# Run the demo application (calls no external API):
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.autoconfig.DemoClientAutoConfigurationTest"
.\gradlew.bat bootRun
```

If using Maven, create a Maven project with Spring Boot parent/BOM, Java 17, and matching dependencies, then run `./mvnw -Dtest=DemoClientAutoConfigurationTest test` (Windows `mvnw.cmd`). Use whichever build tool actually exists in the project.

**Expected from code:** 18 JUnit methods pass if dependencies/versions and environment are complete. While authoring this lesson, the code was statically reviewed against Spring Boot 3.5 documentation, **not compiled or executed via JUnit**. A cached `BUILD SUCCESSFUL` log is insufficient either; check the test report for executed/passed/failed/skipped counts.

## 12. What `ApplicationContextRunner` does not prove yet

The tests above **target** binding/defaults/validation and conditional bean creation. They **do not verify**:

- That `SpringApplication`'s `ConfigData` parser loads YAML/profile documents properly.
- `spring.config.import` from Config Server/secrets managers.
- Actual OS env var naming or shell quoting.
- Property precedence across profile-specific jar files, external files, and CLI arguments.
- Real HTTP/TLS request paths, retry/circuit breakers, or network timeouts.
- Native-image AOT startup (`ContextRunner` has native-mode limitations per Boot docs).
- That a published starter jar includes `AutoConfiguration.imports` metadata properly in the final artifact.
- Safety of secrets/credentials or Actuator `configprops` exposure.

### 12.1. When a full application test is needed

Add `@SpringBootTest(properties = ...)` to boot `SpringApplication`/full context. Use `@ActiveProfiles("test")` and `application-test.yml` when verifying real profile loading. For dynamic Testcontainers endpoints, use `@DynamicPropertySource`. Tests across multiple property sources must compare precedence per Boot documentation rather than inferring from `ContextRunner.withPropertyValues`.

An **additional snippet** example, not counted among the sample project's 18 methods:

```java
@SpringBootTest(
    classes = DemoApplication.class,
    properties = {
        "demo.client.service-name=orders",
        "demo.client.timeout=500ms"
    }
)
class FullBootConfigTest {

    @Autowired DemoClientProperties props;

    @Test
    void timeoutIsLoadedBySpringApplication() {
        assertThat(props.getTimeout())
                .isEqualTo(Duration.ofMillis(500));
    }
}
```

The snippet requires proper imports and package; it is useful when verifying actual `Boot` app startup rather than replacing `ApplicationContextRunner`'s small cases.

### 12.2. Lists and property sources

Spring Boot overrides collection values: a list from a higher-priority property source normally **replaces** a lower-priority list rather than appending to it. Maps have key-merging behavior depending on the case. When configuration relies on lists/maps, test the actual final bound object across multiple sources instead of assuming concatenation.

### 12.3. `Duration` and `DataSize`

`Duration` accepts suffixes such as `ms`, `s`, and `m` per binding conventions; `DataSize` accepts `KB`, `MB`, and `GB`. For numeric-only inputs, default units and `@DurationUnit`/`@DataSizeUnit` matter. Always declare explicit units in docs and tests: `750ms` is not `750s`, and `4MB` is not 4 bytes.

### 12.4. Configuration metadata

`spring-boot-configuration-processor` generates metadata so IDEs can autocomplete property names/types/defaults when supported. It **does not replace** runtime Bean Validation or tests. A starter should document keys, defaults, constraints, deprecated aliases, and compatibility policies.

## 13. Common anti-patterns

| Anti-pattern | Why dangerous | Improvement |
|---|---|---|
| Testing `new Properties()` and calling it a binding test | Never runs the binder | `ContextRunner` + `withPropertyValues` |
| Having `@NotBlank` yet forgetting `@Validated` | Constraints may never run | `@Validated` + `starter-validation` |
| Nested `@Min` yet forgetting `@Valid` | Does not cascade | Negative nested test |
| Using `ignoreInvalidFields=true` so app starts | Hides mistyped input | Fail-fast, fix config |
| Using lenient unknown fields for critical keys without testing typos | Misspelled keys silently ignored | Strict mode or config lint |
| Having JavaBean default true yet condition lacks `matchIfMissing` | Auto bean missing | Align defaults and conditions |
| Testing only `enabled=true`, skipping disabled | Misses conditional failures | Include both missing and false cases |
| Not testing custom user beans | Auto-config may produce duplicates | Test `@ConditionalOnMissingBean` |
| Asserting full translated error messages | Locale/version flakiness | Check cause types and property paths |
| Putting multiple invalid inputs in one test | Unclear which violation fired | Valid baseline, vary one key |
| Assuming `ContextRunner` loads `application.yml` | Skips ConfigData loading | `SpringBootTest` profile test |
| Assuming `@NotNull URI` checks HTTPS | Relative URI is still non-null | Custom validator and scheme tests |
| Assuming `@NotNull Duration` bans 0 | `Duration.ZERO` is still an object | Domain-specific validation |
| Assuming property defaults live in `Environment` | Conditions see missing key | `matchIfMissing`/config defaults |
| Using global `System.setProperty` in parallel tests | State leaks | Scoped runner/`TestPropertySource` |
| Logging raw passwords/API keys in failure reports | Leaks secrets | Mask/redact config |

## 14. Workflow for debugging configuration startup failures

1. Record the exact canonical prefix/key and expected Java type.
2. Confirm the properties class is registered via `@EnableConfigurationProperties` or scanning.
3. Check current property source precedence, profiles, and ConfigData in full apps.
4. Check JavaBean setters/nested getters or record constructor binding.
5. Distinguish Binder conversion errors from Bean Validation constraints.
6. Check `@Validated`, `@Valid`, and the Jakarta Validator provider.
7. Read the root cause, field name, and rejected value **(redacted if secret)**.
8. Check the condition report if a bean was not created.
9. Reproduce in a small `ContextRunner` with a valid baseline and a single changed input.
10. Add a full `SpringApplication` test if the issue involves files/env profiles.
11. Keep a negative regression test so the same bug cannot return.
12. Never "fix" by removing validation, changing defaults against contract, or setting `ignoreInvalidFields`.

## 15. Exercises and solutions

### A. Missing required key

The class has `@NotBlank String serviceName`, the key is absent, and the context fails. Is this a conversion error or a validation error?

**Validation:** the property was omitted so the field stays null, violating `@NotBlank`. Tests should verify the cause chain contains `BindValidationException`.

### B. Malformed number format

`demo.client.max-attempts=banana`. `@Min` is never evaluated successfully because the binder cannot produce an `int`. **Conversion failure**; check for `BindException`.

### C. Nested size=0 does not fail

If `Pool.size` has `@Min(1)` yet the context still passes, check `@Valid` on the outer nested field and the Bean Validation provider. A negative `pool.size=0` test is required proof.

### D. `enabled` defaults true yet bean is absent

JavaBean `enabled=true` does not put the key into `Environment`. A condition with `matchIfMissing=false` will not match when the key is missing. **Fix the conditional policy** or explicit default source, and test the missing-key case.

### E. `enabled=false` while `serviceName` is missing

In the demo, the properties bean is always enabled on the auto-config class; hence validation still runs and startup fails. If business requirements differ, intentionally change the properties type's registration condition and write new tests.

### F. User-defined bean

Auto-config creates an extra client bean even though the app has a custom client. Add `@ConditionalOnMissingBean(DemoHttpClient.class)` and test `ContextRunner.withUserConfiguration` to prove back-off.

### G. JavaBean defaults and list overrides

Default `tags=["default"]`; user sets `tags=blue,green`. The demo test asserts `["blue","green"]`, not `["default","blue","green"]`. Collections use override semantics, not append-merge.

### H. Does required URI enforce HTTPS?

`@NotNull URI endpoint` does not guarantee `https` or a valid host. If policy requires HTTPS, add a custom Bean Validation constraint or validation method and test http/relative/wrong-host cases.

### I. Record `@DefaultValue` and `@Component`

A `@ConfigurationProperties` record uses `@DefaultValue` yet is registered as a `@Component`. Is Boot guaranteed to constructor-bind it? **Never assume so.** Use `EnableConfigurationProperties`/configuration properties scanning.

### J. `@SpringBootTest` or `ApplicationContextRunner`?

If the goal is a starter's conditional bean matrix, use `ContextRunner`. If the goal is YAML profile file loading, a full `SpringApplication` test fits better.

### K. English vs localized constraint messages

Tests comparing exact strings like `must be greater than or equal to 1` can fail across locales. Checking cause types and stable violation metadata is better.

### L. Secret properties

A configuration property is an API key, validation fails startup, and logs print the raw value. **Never store secrets in tests/reports.** Redact failure metadata logs and restrict Actuator config endpoints.

## 16. QA checklist for configuration properties and auto-configuration

- [ ] Canonical property prefix and names are consistent.
- [ ] Class is registered properly; auto-config class is not accidentally component-scanned.
- [ ] JavaBean fields have valid setters/getters or valid record constructor binding.
- [ ] Defaults are tested when keys are absent.
- [ ] Explicit overrides are tested, not only Java initializers.
- [ ] `Duration`/`URI`/`int`/`boolean`/`List`/nested conversions are accurate.
- [ ] Required fields have appropriate `@NotBlank`/`@NotNull`.
- [ ] Bean Validation provider is on the classpath.
- [ ] `@Validated` sits on the properties bean, with `@Valid` cascading to nested objects when needed.
- [ ] Min/max bounds are tested at both valid boundaries and invalid neighbors.
- [ ] Invalid numbers/durations/booleans fail binding.
- [ ] Unknown-key strict/lenient behavior is documented and tested.
- [ ] `ignoreInvalidFields=true` is not used to hide input errors.
- [ ] JavaBean defaults are not mistaken for `Environment` keys.
- [ ] `@ConditionalOnProperty` `matchIfMissing` matches the default contract.
- [ ] `@ConditionalOnMissingBean` backs off properly on user overrides.
- [ ] Disabled branch and validation scope are tested clearly.
- [ ] Test contexts are isolated with no global property leaks.
- [ ] Startup failures check exact cause types rather than matching full localized messages.
- [ ] List/map source precedence is tested when required.
- [ ] Profiles/YAML/ConfigData are tested via `SpringApplication` when needed.
- [ ] `AutoConfiguration.imports` holds exact class FQNs.
- [ ] Metadata processor is used when IDE completion is needed.
- [ ] Security/secret fields are masked in logs/Actuator.
- [ ] Test runner executes exact JUnit methods; skipped tests are reported clearly.
- [ ] Do not treat passing `ContextRunner` tests as proof of external HTTP client/network behavior.
- [ ] For Boot 4.x, update modules/imports and verify new behavior.

## 17. Conclusion

**Configuration properties form an interface driven by Spring Boot's Binder, Bean Validation, and auto-configuration conditions.** Good tests do more than call getters. They must verify:

- **Binding:** key names, relaxed matching, data types, nested objects, and explicit overrides.
- **Validation:** missing, blank, out-of-range, wrong types, and unknown keys per policy.
- **Defaults/conditions:** Java defaults, `@DefaultValue`, `Environment` visibility, enabled/disabled branches, and user bean overrides.

`ApplicationContextRunner` combined with `AutoConfigurations.of` is the right tool to test many combinations quickly and in isolation. When verifying YAML/profile/env sources or real external dependencies, add dedicated `SpringApplication`/full integration tests.

The accompanying Java 17+/Spring Boot 3.5.16 example provides **18 JUnit Jupiter methods** designed to verify those three risk groups. The tests use a `DemoHttpClient` record that opens no network connections; hence expected results establish **configuration/auto-configuration correctness**, not performance or real HTTP connectivity.

## 18. Official references

- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): type-safe properties, relaxed binding, validation, `@DefaultValue`, defaults, and `Environment`.
- [Spring Boot 3.5 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html): `ApplicationContextRunner`, `AutoConfigurations`, bean conditions, and `AutoConfiguration.imports`.
- [Spring Boot 3.5 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): context lifecycle and runner customization.
- [Spring Boot 3.5 — BindValidationException API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/bind/validation/BindValidationException.html): exception thrown when Bean Validation fails during binding.
- [Spring Boot 3.5 — ConfigurationProperties API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html): `prefix`, `ignoreUnknownFields`, `ignoreInvalidFields`.
- [Spring Boot 3.5 — ConditionalOnProperty API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): `havingValue`, `matchIfMissing`.
- [Spring Boot 3.5 — Gradle Plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html): plugin 3.5.16 and dependency management.
- [Jakarta Bean Validation 3.0](https://jakarta.ee/specifications/bean-validation/3.0/): `@NotBlank`, `@Min`/`@Max`, and `@Valid` cascade.