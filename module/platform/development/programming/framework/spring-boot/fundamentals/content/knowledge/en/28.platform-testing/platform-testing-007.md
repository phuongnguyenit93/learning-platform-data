# Testing Profiles, Properties, and Selected Implementations

In Spring Boot, a single interface can have multiple implementations depending on the environment: a simulated implementation for local/test runs, an implementation connecting to real systems in production, or an implementation toggled by a feature flag. When selection conditions are wrong, the application can start with an **unintended bean**, miss a mandatory bean, or load multiple beans of the same type causing dependency injection failures.

Testing these cases needs to answer more than "is the profile active?":

- **Which profiles are actually active in the test context?**
- **Which properties are in effect and are they bound/converted properly?**
- **Which conditions evaluate to true or false?**
- **How many beans share a contract, and which implementation does Spring select?**
- **When a mandatory condition is missing, does the app fail fast or fall back as designed?**

This lesson uses Spring Boot Test, Spring Test, and `ApplicationContextRunner` to test **profiles, properties, and implementation selection** at a foundational level. Examples are written to make clear the boundary between *input configuration*, *bean creation decisions*, and *the behavior of the selected bean*.

## 1. Why must implementation selection be tested?

Suppose a system has a notification sending interface:

```java
public interface NotificationChannel {
    String channelName();
}
```

Two simulated implementations:

```java
public final class LocalNotificationChannel
        implements NotificationChannel {

    @Override
    public String channelName() {
        return "local";
    }
}
```

```java
public final class RemoteNotificationChannel
        implements NotificationChannel {

    @Override
    public String channelName() {
        return "remote";
    }
}
```

The names `local` and `remote` here simply serve as observable signals indicating which bean was chosen. The `channelName()` method makes no network calls; there is no real external system in these tests.

Operational requirements:

1. When the **`prod` profile is inactive**, use `LocalNotificationChannel`.
2. When **`prod` is active and `integration.notifications.enabled=true`**, use `RemoteNotificationChannel`.
3. When **`prod` is active but the property is not enabled**, **create no channel**. If a service requires a channel, the app should report a configuration error rather than silently falling back to local.

A decision table:

| Active profiles | `integration.notifications.enabled` | Expected bean |
|---|---|---|
| Unspecified | Absent | Local |
| `dev` | Absent | Local |
| `test` | `false` | Local |
| `prod` | `true` | Remote |
| `prod` | `false` | None |
| `prod` | Absent | None |
| `dev,prod` | `true` | Remote |

If a test only asserts that `Environment.getActiveProfiles()` returns `prod`, the test **has not proven** Spring registered `RemoteNotificationChannel`.

The real goal is verifying the container's final decision.

## 2. A foundational configuration example

Create the configuration:

```java
package com.example.notification;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean("localNotificationChannel")
    @Profile("!prod")
    public NotificationChannel localNotificationChannel() {
        return new LocalNotificationChannel();
    }

    @Bean("remoteNotificationChannel")
    @Profile("prod")
    @ConditionalOnProperty(
        prefix = "integration.notifications",
        name = "enabled",
        havingValue = "true"
    )
    public NotificationChannel remoteNotificationChannel() {
        return new RemoteNotificationChannel();
    }
}
```

This configuration **creates at most one of the two implementations—or neither**, depending on the profile/property combination.

Each mechanism has a specific role:

- `@Profile("!prod")`: registers the local bean only if `prod` is not active.
- `@Profile("prod")`: considers the remote bean only if `prod` is active.
- `@ConditionalOnProperty(...)`: registers the remote bean only when the flag matches the expected value.
- `@Bean("...")`: gives an explicit bean name so tests can verify both name and type.

Do not add `@Component` to the two implementations in this example, as the objects are created via `@Bean`. Component-scanning an implementation while also declaring a `@Bean` method can accidentally register duplicate beans.

## 3. Understanding the example's conditions accurately

We can write the logical conditions as:

```text
Local created  = NOT prod

Remote created = prod AND notifications.enabled=true
```

Because `prod` and `!prod` are mutually exclusive, both beans cannot be registered simultaneously from **these two methods** in the same context.

Yet a zero-bean state still exists:

```text
prod active
    │
    ▼
Local excluded
    │
    ▼
notifications.enabled=false or missing
    │
    ▼
Remote excluded
    │
    ▼
No NotificationChannel provided by this configuration
```

A "no bean" state is not automatically a bug if an intentional fail-fast policy requires it. Conversely, if production mandates a sender, tests should prove a missing flag causes dependent service creation to fail rather than letting the system run with a risky fallback.

**Design note:** `!prod` means "not prod," not "dev or test." When a `staging` or `demo` environment is added later, the local bean can appear there too. In real systems, consider positive expressions like `dev | test` if only those two environments are intended, and test every environment thoroughly.

## 4. Testing layers to distinguish

Three testing layers apply to this problem.

| Layer | Target | Relative cost | Best suited for |
|---|---|---|---|
| Plain Java unit test | Implementation/service methods | Low | Logic inside each implementation |
| Narrow context test with `ApplicationContextRunner` | Bean definitions, profile/property conditions, binding | Low to medium | Bean selection matrix |
| `@SpringBootTest` | Realistic test Spring Boot application context | Medium to high | Wiring/integration and overall behavior |

Unit test example:

```java
@Test
void localChannelReportsItsIdentity() {
    NotificationChannel channel =
            new LocalNotificationChannel();

    assertEquals("local", channel.channelName());
}
```

This test proves **the local class works as coded**. It **does not** prove Spring selects the local class under the `dev` profile.

To test container conditions, tests must boot a Spring context with matching profiles and properties.

## 5. Test dependencies

In standard Spring Boot projects, the test starter supplies Spring Test, JUnit Jupiter, AssertJ, and other needed libraries aligned with the project's version/BOM.

Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

The code snippets below assume the project uses JUnit Jupiter and appropriate Java/Spring imports. Exact versions are managed by the project build; avoid copying arbitrary versions from examples.

Across different Spring Boot releases, mock bean APIs or auxiliary test annotations may vary. The bean-selection tests below favor **real contexts and assertions**, avoiding masking selection behavior by mocking the very bean being selected.

## 6. @SpringBootTest: starting a context for testing

`@SpringBootTest` is the central annotation for Spring Boot integration tests.

Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    classes = NotificationConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("dev")
class LocalNotificationContextTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void selectsLocalChannel() {
        NotificationChannel channel =
                context.getBean(NotificationChannel.class);

        assertNotNull(channel);
        assertEquals("local", channel.channelName());
    }
}
```

This test specifies a minimal configuration class and chooses a non-web context to stay focused on bean selection.

Distinguish clearly:

- `classes = NotificationConfiguration.class`: specifies the configuration source for the test.
- `webEnvironment = NONE`: skips starting an embedded web server for this test.
- `@ActiveProfiles("dev")`: sets the active profile for the Spring Test context.
- `ApplicationContext.getBean(...)`: retrieves the bean selected by the container.

If you omit `classes`, Spring Boot Test locates a startup configuration via test bootstrap rules. That can pull in unrelated auto-configurations or beans, making tests heavier.

## 7. What is @ActiveProfiles?

`@ActiveProfiles` comes from Spring Test and sets the **active profile names** for the application context during testing.

```java
@ActiveProfiles("dev")
```

or:

```java
@ActiveProfiles({"prod", "cloud"})
```

The second form activates **two independent profile names**. Do not confuse it with a profile expression:

```java
@Profile("prod & cloud")
```

`@Profile` is an expression checking a bean condition; `@ActiveProfiles` is the list of profile names activated by the test.

Example:

```java
@Component
@Profile("dev & cloud")
class CloudDeveloperTool {
}
```

Correct test:

```java
@SpringBootTest
@ActiveProfiles({"dev", "cloud"})
class CloudDeveloperToolTest {
}
```

Do not write `@ActiveProfiles("dev & cloud")` expecting Spring to treat it as an AND expression. It declares profile names for the test, not a pointcut or `@Profile` expression parser.

## 8. Testing that the local implementation is selected

Using `NotificationConfiguration` from Section 2:

```java
@SpringBootTest(
    classes = NotificationConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("dev")
class DevNotificationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void createsExactlyOneLocalChannel() {
        String[] names =
                context.getBeanNamesForType(NotificationChannel.class);

        assertEquals(1, names.length);
        assertEquals("localNotificationChannel", names[0]);

        NotificationChannel channel =
                context.getBean(NotificationChannel.class);

        assertInstanceOf(LocalNotificationChannel.class, channel);
        assertEquals("local", channel.channelName());
    }
}
```

This test checks three layers:

1. **Count:** only one bean for the interface.
2. **Name/type:** the selected bean is the local implementation.
3. **Behavior:** the method returns the expected identity.

`assertInstanceOf` comes from compatible JUnit Jupiter versions; on older versions, use `assertTrue(LocalNotificationChannel.class.isInstance(channel))`.

**Do not assert only that the local bean exists.** If the remote bean was also accidentally registered, a test checking only local presence can still pass. An "exactly one" assertion catches overlapping configurations.

## 9. Passing properties into @SpringBootTest

`@SpringBootTest` lets you declare properties scoped to the test context:

```java
@SpringBootTest(
    classes = NotificationConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "integration.notifications.enabled=true"
    }
)
@ActiveProfiles("prod")
class ProductionNotificationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void selectsRemoteChannel() {
        NotificationChannel channel =
                context.getBean(NotificationChannel.class);

        assertInstanceOf(RemoteNotificationChannel.class, channel);
        assertEquals("remote", channel.channelName());
        assertEquals(
                1,
                context.getBeanNamesForType(
                        NotificationChannel.class
                ).length
        );
    }
}
```

This explicitly configures a test scenario:

- `prod` profile active.
- Flag `integration.notifications.enabled=true`.
- Remote implementation must be chosen.
- Local implementation must not be registered per profile condition.

Properties from `@SpringBootTest(properties = ...)` form a test property source that typically overrides standard config files. If multiple property override mechanisms are used simultaneously, understand their precedence and avoid creating unnecessary conflicts.

## 10. Flag absent in prod: testing the zero-bean state

In this example, when production does not enable notifications, no `NotificationChannel` exists.

```java
@SpringBootTest(
    classes = NotificationConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "integration.notifications.enabled=false"
    }
)
@ActiveProfiles("prod")
class DisabledProductionNotificationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void doesNotCreateAnyNotificationChannel() {
        assertEquals(
                0,
                context.getBeanNamesForType(
                        NotificationChannel.class
                ).length
        );
    }
}
```

This test starts cleanly because it loads only `NotificationConfiguration`, with no service requiring injection of `NotificationChannel`.

If the real application has:

```java
@Service
public class NotificationService {

    private final NotificationChannel channel;

    public NotificationService(NotificationChannel channel) {
        this.channel = channel;
    }
}
```

and that service bean is loaded, `prod` without a channel causes context startup to fail due to a missing dependency. That behavior is worth testing at the integration level.

**Two distinct test requirements:**

- *Configuration does not register the channel when the flag is false.*
- *Application fails fast if a required feature depends on the channel when it is unconfigured.*

Do not conflate them. The same property can be valid in an optional subsystem yet be a critical error in a mandatory subsystem.

## 11. Writing a case matrix before writing code

A test matrix helps prevent missing branches:

| ID | Profiles | Property | Expected channel | Expected count |
|---|---|---|---|---:|
| P1 | Unspecified | Absent | Local | 1 |
| P2 | `dev` | Absent | Local | 1 |
| P3 | `test` | false | Local | 1 |
| P4 | `prod` | true | Remote | 1 |
| P5 | `prod` | false | None | 0 |
| P6 | `prod` | missing | None | 0 |
| P7 | `dev,prod` | true | Remote | 1 |

P7 is especially important: Spring permits multiple active profiles at once. `@Profile("!prod")` does not match if `prod` is active, even if `dev` is also active.

A matrix covering **positive**, **negative**, **missing**, and **mixed-profile** cases is far more valuable than testing only the `dev` profile.

## 12. ApplicationContextRunner for fast configuration testing

`ApplicationContextRunner` belongs to Spring Boot Test and builds small contexts under controlled conditions, passing each context to an assertion callback.

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class NotificationConfigurationRunnerTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(
                    NotificationConfiguration.class
                );

    @Test
    void selectsLocalWhenNoProdProfile() {
        runner.run(context -> {
            assertThat(context)
                    .hasSingleBean(NotificationChannel.class);

            NotificationChannel channel =
                    context.getBean(NotificationChannel.class);

            assertThat(channel)
                    .isInstanceOf(LocalNotificationChannel.class);

            assertThat(channel.channelName())
                    .isEqualTo("local");
        });
    }
}
```

Useful characteristics:

- No need to run the full Spring Boot application.
- Easy to add/remove properties and user configurations.
- Easy to check bean count, bean type, and startup failures.
- Each `run(...)` call gets its own runner-managed context lifecycle.
- Well suited for unit/integration-style tests of auto-configuration.

However, a small context does not necessarily load all beans, filters, and auto-configurations of the production app. Results hold for the configurations registered in the runner; to verify full-app wiring, include some `@SpringBootTest` checks.

## 13. Using ApplicationContextRunner with properties

Example where `false` prevents creating the remote bean in `prod`:

```java
@Test
void prodWithDisabledFlagHasNoChannel() {
    runner
        .withInitializer(context ->
            context.getEnvironment().setActiveProfiles("prod")
        )
        .withPropertyValues(
            "integration.notifications.enabled=false"
        )
        .run(context -> {
            assertThat(context)
                    .doesNotHaveBean(NotificationChannel.class);
        });
}
```

Example with `true`:

```java
@Test
void prodWithEnabledFlagSelectsRemote() {
    runner
        .withInitializer(context ->
            context.getEnvironment().setActiveProfiles("prod")
        )
        .withPropertyValues(
            "integration.notifications.enabled=true"
        )
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(NotificationChannel.class);

            NotificationChannel channel =
                    context.getBean(NotificationChannel.class);

            assertThat(channel)
                    .isInstanceOf(RemoteNotificationChannel.class);

            assertThat(channel.channelName())
                    .isEqualTo("remote");
        });
}
```

In these snippets, `runner` is the field declared in `NotificationConfigurationRunnerTest` earlier.

**Why use `setActiveProfiles("prod")`?** `ApplicationContextRunner` builds a small context and does not automatically emulate the full Spring Boot startup/config-data pipeline for every app behavior. Setting active profiles directly on the context's `Environment` makes test intent explicit. Do not assume merely adding `spring.profiles.active=prod` via `withPropertyValues(...)` is always equivalent to real application bootstrap profile activation.

## 14. Testing multiple profiles with ApplicationContextRunner

To test `prod` and `dev` active together:

```java
@Test
void prodWinsTheExplicitSelectionEvenWithDevActive() {
    runner
        .withInitializer(context ->
            context.getEnvironment()
                .setActiveProfiles("dev", "prod")
        )
        .withPropertyValues(
            "integration.notifications.enabled=true"
        )
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(NotificationChannel.class);

            assertThat(
                context.getBean(NotificationChannel.class)
                       .channelName()
            ).isEqualTo("remote");
        });
}
```

There is no automatic "prod beats dev" rule in this example. Remote is chosen because:

1. `prod` is active, so `@Profile("prod")` matches.
2. `!prod` is false, so the local bean is excluded.
3. `integration.notifications.enabled=true`, so the remote bean's condition matches.

The outcome follows from **the conditional expressions**, not an implicit profile-name priority.

## 15. Testing that an implementation was excluded

When verifying the wrong bean does not exist, use direct assertions:

```java
@Test
void devDoesNotRegisterRemoteImplementation() {
    runner
        .withInitializer(context ->
            context.getEnvironment().setActiveProfiles("dev")
        )
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(NotificationChannel.class);

            assertThat(context)
                    .doesNotHaveBean(RemoteNotificationChannel.class);
        });
}
```

**Note:** if the `@Bean` method declares its return type as the interface, Spring bean-type resolution in tests can depend on metadata and when the bean is actually instantiated. Another reliable approach is fetching the contract bean and checking the actual object's class:

```java
NotificationChannel actual =
        context.getBean(NotificationChannel.class);

assertThat(actual)
        .isInstanceOf(LocalNotificationChannel.class);
```

When you want to check bean names explicitly:

```java
assertThat(context.containsBean("localNotificationChannel"))
        .isTrue();

assertThat(context.containsBean("remoteNotificationChannel"))
        .isFalse();
```

Type, name, and behavior checks complement one another. Avoid relying solely on a bean name if that name is not part of the module's contract.

## 16. Testing expected failure when a dependency is missing

A pure configuration only creates candidate channels. To test that an invalid configuration causes the app to fail, register a consumer requiring the channel:

```java
public class NotificationCoordinator {

    private final NotificationChannel channel;

    public NotificationCoordinator(NotificationChannel channel) {
        this.channel = channel;
    }

    public String currentMode() {
        return channel.channelName();
    }
}
```

Factory configuration:

```java
@Configuration(proxyBeanMethods = false)
public class NotificationCoordinatorConfiguration {

    @Bean
    NotificationCoordinator notificationCoordinator(
            NotificationChannel channel) {
        return new NotificationCoordinator(channel);
    }
}
```

Test:

```java
@Test
void prodWithoutEnabledFlagFailsFast() {
    runner
        .withUserConfiguration(
            NotificationCoordinatorConfiguration.class
        )
        .withInitializer(context ->
            context.getEnvironment().setActiveProfiles("prod")
        )
        .withPropertyValues(
            "integration.notifications.enabled=false"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .isNotNull();
        });
}
```

When Spring tries to build `NotificationCoordinator` and finds no `NotificationChannel`, startup fails because the dependency cannot be satisfied.

This test brings two benefits:

- Verifies *there is no silent fallback*.
- Protects the policy that "production must be explicitly configured."

When asserting detailed error info, inspect the exception cause chain for your version instead of matching brittle full exception text.

## 17. What is @TestPropertySource?

`@TestPropertySource` comes from Spring Test and supplies properties or property files dedicated to the test context.

Example:

```java
import org.springframework.test.context.TestPropertySource;

@SpringBootTest(
    classes = NotificationConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("prod")
@TestPropertySource(properties = {
    "integration.notifications.enabled=true"
})
class NotificationWithTestPropertySourceTest {
}
```

You can also reference a properties resource file:

```java
@TestPropertySource(
    locations = "classpath:notification-test.properties"
)
```

and create `src/test/resources/notification-test.properties`:

```properties
integration.notifications.enabled=true
```

**Format note:** `@TestPropertySource(locations=...)` by default in Spring Test reads property resources per its supported contract, commonly `.properties`. Do not assume every `.yml` file in `locations` will be parsed like Spring Boot config data without a custom factory configuration.

## 18. @SpringBootTest(properties) or @TestPropertySource?

Both add test properties. Pick one primary style per test group to minimize conflicts.

| Need | Convenient choice |
|---|---|
| One or a few keys specific to one integration test | `@SpringBootTest(properties=...)` |
| A `.properties` file shared across a test suite | `@TestPropertySource(locations=...)` |
| Pure conditional config tests across many combinations | `ApplicationContextRunner.withPropertyValues(...)` |
| Values generated by a database/container started in test | `@DynamicPropertySource` |
| Loading `application-dev.yml` by profile | `@ActiveProfiles("dev")` in Spring Boot test |

Avoid mixing multiple sources setting the same key unless **intentionally testing precedence**. A test relying on a tangled override chain is hard to understand and maintain.

To verify the effective value, inject `Environment` and check `getProperty(...)`, remembering that a property being present does not by itself prove the right bean was selected.

## 19. Testing property defaults and missing properties

`@ConditionalOnProperty` has important semantics. With:

```java
@ConditionalOnProperty(
    prefix = "integration.notifications",
    name = "enabled",
    havingValue = "true"
)
```

`matchIfMissing` defaults to `false`. Consequently, when the key is completely absent, the condition does not match.

Write a test:

```java
@Test
void missingFlagDoesNotSelectRemote() {
    runner
        .withInitializer(context ->
            context.getEnvironment().setActiveProfiles("prod")
        )
        .run(context -> {
            assertThat(context)
                    .doesNotHaveBean(NotificationChannel.class);
        });
}
```

Another configuration might use `matchIfMissing=true`:

```java
@ConditionalOnProperty(
    prefix = "feature.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
```

Here, **missing** and **explicit false** behave differently. Test both.

General behavior table for `havingValue="true"`:

| Property | `matchIfMissing=false` | `matchIfMissing=true` |
|---|---:|---:|
| Missing | Does not match | Matches |
| `true` | Matches | Matches |
| `false` | Does not match | Does not match |
| Value other than `true` | Does not match | Does not match |

If `havingValue` is omitted, `@ConditionalOnProperty` semantics differ: typically the property only needs to exist and not equal `false`. Do not assume all property conditions behave identically as simple boolean checks.

## 20. Reading the property actually used in tests

To inspect the effective configuration, inject `Environment`:

```java
@SpringBootTest(
    classes = NotificationConfiguration.class,
    properties = "integration.notifications.enabled=true",
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("prod")
class NotificationEnvironmentTest {

    @Autowired
    Environment environment;

    @Test
    void propertyIsEffective() {
        assertEquals(
                "true",
                environment.getProperty(
                        "integration.notifications.enabled"
                )
        );
    }
}
```

This test is useful for distinguishing an unloaded property from a broken bean condition. However, it **does not replace** testing bean selection:

```java
assertEquals(
    "remote",
    context.getBean(NotificationChannel.class)
           .channelName()
);
```

Reading `Environment` verifies **input configuration**. Inspecting `ApplicationContext` verifies **the output of bean registration**.

## 21. Testing @ConfigurationProperties and typed binding

A property might exist as a String yet bind to the wrong type, or the properties object might not be registered at all.

Example:

```yaml
app:
  client:
    timeout: 5s
    max-attempts: 3
```

Typed properties:

```java
package com.example.notification;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        Duration timeout,
        int maxAttempts
) {
}
```

Register the properties object in the test context:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
class ClientPropertiesConfiguration {
}
```

Test with `ApplicationContextRunner`:

```java
@Test
void bindsClientProperties() {
    new ApplicationContextRunner()
        .withUserConfiguration(
            ClientPropertiesConfiguration.class
        )
        .withPropertyValues(
            "app.client.timeout=5s",
            "app.client.max-attempts=3"
        )
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(ClientProperties.class);

            ClientProperties properties =
                    context.getBean(ClientProperties.class);

            assertThat(properties.timeout())
                    .isEqualTo(Duration.ofSeconds(5));

            assertThat(properties.maxAttempts())
                    .isEqualTo(3);
        });
}
```

Here, the test proves Spring Boot **converted `"5s"` into a `Duration`** and bound `max-attempts` into the Java property `maxAttempts`.

If the properties class is not registered, merely placing `app.client.timeout` in `Environment` does not create a `ClientProperties` bean.

## 22. Testing binding and validation failures

Consider invalid configuration:

```properties
app.client.timeout=not-a-duration
```

With the properties object bound during initialization, Spring throws an error because the string cannot be converted to `Duration`.

Test:

```java
@Test
void invalidDurationFailsContextStartup() {
    new ApplicationContextRunner()
        .withUserConfiguration(
            ClientPropertiesConfiguration.class
        )
        .withPropertyValues(
            "app.client.timeout=not-a-duration",
            "app.client.max-attempts=3"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .isNotNull();
        });
}
```

This tests a **conversion failure**.

**Validation failure** is a separate case: the value converts to the target type yet violates business constraints, such as `max-attempts=-1`. When requiring constraints like `@Min(0)` or a positive timeout, define validation annotations on the properties object and ensure validation infrastructure is enabled. Do not assume Spring automatically rejects negative numbers simply because a field is named `maxAttempts`.

## 23. Testing @Value for a single property

`@Value` can be used instead of `@ConfigurationProperties` when a bean only needs a single value.

Example:

```java
@Component
public class WelcomeMessage {

    private final String prefix;

    public WelcomeMessage(
            @Value("${app.welcome.prefix:Hello}") String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + " " + name;
    }
}
```

Context test with property:

```java
@SpringBootTest(
    classes = WelcomeMessage.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "app.welcome.prefix=Hi"
)
class WelcomeMessageTest {

    @Autowired
    WelcomeMessage message;

    @Test
    void usesConfiguredPrefix() {
        assertEquals("Hi Linh", message.greet("Linh"));
    }
}
```

To test the default `Hello`, use a separate context without supplying the property. Never mutate environment variables between two test methods expecting a cached context to rebind automatically.

## 24. @DynamicPropertySource for values generated at test time

Many integration tests require dynamic ports/URLs from a database, message broker, or HTTP test server. Hardcoding URLs in YAML invites collisions across developer machines and CI.

Spring Test provides `@DynamicPropertySource` to add properties generated by test code.

Minimal example without needing a real container:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class DynamicPortExampleTest {

    @DynamicPropertySource
    static void dynamicProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "integration.remote.port",
            () -> 18081
        );
    }

    @Autowired
    Environment environment;

    @Test
    void dynamicPropertyIsVisible() {
        assertEquals(
                18081,
                environment.getProperty(
                    "integration.remote.port",
                    Integer.class
                )
        );
    }
}
```

In real use cases, the supplier typically reads the port from a started container or server. Dynamic properties carry high precedence in Spring Test; avoid setting the same key across multiple sources unintentionally.

Note that `@DynamicPropertySource` runs when Spring Test prepares the context. It is not an API for changing bean configuration between test methods after the context has already refreshed.

## 25. Testing with a real database or container

When an application picks an implementation based on the presence of an integration, tests may need Testcontainers or an isolated real service.

Target example:

- Profile `integration` active.
- Database container running on a random port.
- Dynamic properties providing datasource URL/credentials.
- Real repository bean created and accessible.

This kind of test verifies end-to-end wiring and behavior far better than an `ApplicationContextRunner` building isolated bean definitions.

However, **never spin up an external integration solely to prove `@ConditionalOnProperty` works**. Narrow tests suffice for bean selection logic; external-resource integration tests should target behavior that actually depends on those resources.

To keep tests deterministic:

1. Manage external resource lifecycles inside fixtures.
2. Never share a production database.
3. Seed isolated data and clean up explicitly.
4. Avoid hardcoded fixed ports whenever possible.
5. Pass dynamic properties from fixtures rather than hardcoding them.
6. Mind CI speed and resource consumption.

## 26. Profile-specific YAML and @ActiveProfiles

Spring Boot can load files such as:

```text
application.yml
application-dev.yml
application-prod.yml
```

when running with matching active profiles.

Example:

```yaml
# src/main/resources/application.yml
app:
  client:
    timeout: 10s
```

```yaml
# src/main/resources/application-dev.yml
app:
  client:
    timeout: 2s
```

Test:

```java
@SpringBootTest
@ActiveProfiles("dev")
class DevTimeoutConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void usesDevTimeout() {
        assertEquals(
                "2s",
                environment.getProperty("app.client.timeout")
        );
    }
}
```

In a Spring Boot test with config-data loading, the `dev` profile causes `application-dev.yml` to be applied according to Boot rules.

If the test adds `@SpringBootTest(properties = "app.client.timeout=5s")`, the runtime value becomes `5s` rather than the profile YAML value. Clarify whether the test verifies **profile-specific config loading** or **test overrides**; do not mix the two goals.

## 27. Default profile differs from active profile

When no active profiles are specified, Spring uses **default profiles** according to `Environment` rules.

Example bean:

```java
@Bean
@Profile("default")
public NotificationChannel defaultChannel() {
    return new LocalNotificationChannel();
}
```

It can be registered when no active profile is set and the effective default profile is `default`.

Meanwhile:

```java
@Profile("!prod")
```

matches in many other situations, such as `dev` or `test`, as long as `prod` is not active.

These are two distinct conditions, so test:

- No active profile.
- `dev` active.
- `prod` active.
- Custom default profile if the application uses one.

In particular, a test omitting `@ActiveProfiles` does not necessarily mirror production: some test environments still apply test properties, startup arguments, or active profiles inherited from base classes or meta-annotations.

## 28. Profile expressions AND, OR, NOT in tests

Spring `@Profile` supports expressions:

```java
@Profile("(dev | staging) & cloud & !maintenance")
```

With `@ActiveProfiles({"dev", "cloud"})`, the expression above evaluates to true.

If `{"dev", "cloud", "maintenance"}` are active, the expression evaluates to false.

Example:

```java
@Test
void profileExpressionCanBeCheckedDirectly() {
    MockEnvironment environment = new MockEnvironment();
    environment.setActiveProfiles("dev", "cloud");

    assertTrue(
        environment.acceptsProfiles(
            Profiles.of("(dev | staging) & cloud & !maintenance")
        )
    );
}
```

Import `MockEnvironment` from Spring Test and `Profiles` from Spring Core.

Testing `Profiles.of(...)` is fast, yet verifies only **expression logic**. To prove beans are selected inside a real context, add a context configuration test with the corresponding `@Profile`.

## 29. @Profile taking an array is not AND

These two declarations are **not equivalent**:

```java
@Profile({"dev", "cloud"})
```

and:

```java
@Profile("dev & cloud")
```

The first means **dev OR cloud**; the second means **dev AND cloud**.

A helpful test check:

```text
Active: dev only

@Profile({"dev", "cloud"}) -> matches
@Profile("dev & cloud")  -> does not match
```

When using `@ActiveProfiles({"dev", "cloud"})`, **both profiles are active**, so both conditions match. That can mask a design mistake if you only test the case where both are active together.

Add at least one "dev only" test and one "cloud only" test whenever AND/OR semantics matter.

## 30. Checking @Primary and @Qualifier

Sometimes an application intentionally registers **multiple beans of the same type** and selects one via `@Primary` or `@Qualifier`.

Example:

```java
@Configuration(proxyBeanMethods = false)
public class GatewayConfiguration {

    @Bean("primaryGateway")
    @Primary
    NotificationChannel primaryGateway() {
        return new LocalNotificationChannel();
    }

    @Bean("backupGateway")
    NotificationChannel backupGateway() {
        return new RemoteNotificationChannel();
    }
}
```

When injecting by type:

```java
@Service
public class ChannelConsumer {

    private final NotificationChannel channel;

    public ChannelConsumer(NotificationChannel channel) {
        this.channel = channel;
    }

    public String mode() {
        return channel.channelName();
    }
}
```

`@Primary` gives preference to one bean when multiple eligible candidates exist at single-value injection points.

Keep in mind:

- Both `primaryGateway` and `backupGateway` **exist**.
- `getBeansOfType(NotificationChannel.class)` returns two beans.
- `@Primary` does not stop Spring from creating the backup bean.
- `@Qualifier("backupGateway")` can explicitly choose the other implementation.

Tests should distinguish **registered beans** from **the bean injected into the consumer**.

## 31. Test the injected bean, not just the count

Example verifying the consumer receives the primary bean:

```java
@Test
void consumerUsesPrimaryGateway() {
    new ApplicationContextRunner()
        .withUserConfiguration(
            GatewayConfiguration.class,
            ChannelConsumerConfiguration.class
        )
        .run(context -> {
            assertThat(
                context.getBeansOfType(NotificationChannel.class)
            ).hasSize(2);

            ChannelConsumer consumer =
                    context.getBean(ChannelConsumer.class);

            assertThat(consumer.mode())
                    .isEqualTo("local");
        });
}
```

Configuration creating the consumer:

```java
@Configuration(proxyBeanMethods = false)
class ChannelConsumerConfiguration {

    @Bean
    ChannelConsumer channelConsumer(NotificationChannel channel) {
        return new ChannelConsumer(channel);
    }
}
```

This example shows:

- Both beans are created.
- Constructor injection picks the primary bean.
- Post-injection behavior reflects the selected implementation.

If someone swaps an implementation and the test checks only that two beans exist, the test misses a regression in injection-point resolution.

## 32. Testing @ConditionalOnMissingBean and fallback

A common auto-configuration pattern: create a default bean **when the user has not provided** an implementation.

```java
@Configuration(proxyBeanMethods = false)
public class DefaultChannelAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationChannel.class)
    NotificationChannel defaultChannel() {
        return new LocalNotificationChannel();
    }
}
```

Fallback test:

```java
@Test
void createsDefaultWhenNoUserBean() {
    new ApplicationContextRunner()
        .withUserConfiguration(
            DefaultChannelAutoConfiguration.class
        )
        .run(context ->
            assertThat(context)
                .hasSingleBean(NotificationChannel.class)
        );
}
```

User override test:

```java
@Configuration(proxyBeanMethods = false)
class CustomChannelConfiguration {

    @Bean
    NotificationChannel customChannel() {
        return new RemoteNotificationChannel();
    }
}
```

```java
@Test
void backsOffWhenUserDefinesChannel() {
    new ApplicationContextRunner()
        .withUserConfiguration(
            CustomChannelConfiguration.class,
            DefaultChannelAutoConfiguration.class
        )
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(NotificationChannel.class);

            assertThat(
                context.getBean(NotificationChannel.class)
            ).isInstanceOf(RemoteNotificationChannel.class);
        });
}
```

In real auto-configuration, bean definition processing order and `@ConditionalOnMissingBean` matter. Default configurations must be structured so conditions evaluate after relevant user configurations have been registered. In tests, use proper ordering or auto-configuration registration matching the module design rather than relying on lucky scan order.

**Note:** `@ConditionalOnMissingBean` is not `@Profile`. It inspects bean candidates, not environment names.

## 33. @TestConfiguration and test-only beans

Some integration tests need test-only beans such as a fake external clock, fake service, or fixture provider.

Spring Boot's `@TestConfiguration` marks configuration intended for tests:

```java
@TestConfiguration(proxyBeanMethods = false)
class FixedClockTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Import it into a test:

```java
@SpringBootTest
@Import(FixedClockTestConfiguration.class)
class ClockIntegrationTest {
    // Test beans using the fixed Clock.
}
```

However, adding a test-only bean can **alter** outcomes of `@ConditionalOnMissingBean`, `@Primary`, or auto-configurations, meaning you are no longer testing the original production configuration's behavior.

If the goal is testing whether Boot auto-creates Bean A, do not inadvertently replace A with a fake and conclude auto-configuration worked. Document clearly which bean overrides are active in the test context.

## 34. Mock beans can hide implementation-selection bugs

When testing controllers, developers often replace the real service with a mock to isolate the web layer. This is a sound approach for unit and slice testing, yet **is unsuitable as proof that Spring selected the right service implementation**.

Conceptual example:

```java
@MockitoBean
NotificationChannel notificationChannel;
```

`@MockitoBean` is Spring Test's bean override mechanism in compatible modern Spring Framework releases. Older Spring Boot projects may use `@MockBean`, though annotations and lifecycle support differ across versions.

If a mock replaces `NotificationChannel`, tests can pass even when local/remote selection is completely wrong for actual deployment.

Choose appropriately:

- **Testing controller contracts:** mock service dependencies when isolation is needed.
- **Testing profile/condition selection:** keep real configurations and bean candidates, asserting types, names, and counts.
- **Testing end-to-end integration:** use suitable test fixtures or external resources.

No single mocking technique replaces every testing layer.

## 35. Test slices do not necessarily load all beans

`@WebMvcTest`, `@DataJpaTest`, and other test slices focus on a subset of the application context.

For example, `@WebMvcTest(OrderController.class)` does not automatically load every `@Service`, `@ConfigurationProperties`, or configuration condition in the application.

If a slice test lacks a bean, it may be because the slice intentionally restricts components rather than a faulty profile or condition.

When testing **which implementation Spring selects in the application**, prefer:

- `ApplicationContextRunner` with explicitly declared configurations.
- `@SpringBootTest` with matching classes, profiles, and properties.

When testing only HTTP mapping, serialization, or controller validation, slice tests are usually leaner.

**Never conclude from a slice test that a bean is missing from the full application context.**

## 36. How does context caching affect tests?

Spring Test includes **ApplicationContext caching** to reuse contexts across tests sharing compatible configurations.

A context cache key can depend on:

- Loaded configuration classes.
- Active profiles.
- Inline test properties and property sources.
- Context initializers.
- Test customizers, mock/bean overrides, or dynamic property setups.
- Other bootstrap/context hierarchy attributes.

Practical consequence: calling `System.setProperty(...)` between two test methods **does not cause** an already-initialized context to recreate beans and re-evaluate `@ConditionalOnProperty`.

Error-prone example:

```java
@Test
void first() {
    System.setProperty("integration.notifications.enabled", "true");
    // Expecting the context to rebuild automatically: incorrect.
}
```

Bean definitions were already decided when the context was built. For profile/property selection, prefer **separate test classes with dedicated configurations** or `ApplicationContextRunner` creating an independent context per case.

## 37. @DirtiesContext: when is it needed?

`@DirtiesContext` marks the cached context as no longer suitable for reuse.

Example:

```java
@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
class MutatingContextTest {
}
```

This may be necessary when a test genuinely alters context state in a way that affects subsequent tests.

However, do not treat `@DirtiesContext` as a default fix for every profile/property case:

- It slows down the test suite.
- It does not replace declaring proper property sources before the context builds.
- It can mask leaking test state.
- It does not automatically reset external resources like databases unless managed separately.

When testing multiple flag combinations, `ApplicationContextRunner` is usually cheaper and clearer.

## 38. Unit testing with MockEnvironment

When you only want to verify a profile expression, you can use `MockEnvironment` without booting a Spring Boot context:

```java
@Test
void prodAndCloudExpressionMatches() {
    MockEnvironment env = new MockEnvironment();

    env.setActiveProfiles("prod", "cloud");

    assertTrue(
        env.acceptsProfiles(
            Profiles.of("prod & cloud")
        )
    );

    assertFalse(
        env.acceptsProfiles(
            Profiles.of("dev & !prod")
        )
    );
}
```

With named properties:

```java
@Test
void exposesPropertyForSimpleLogic() {
    MockEnvironment env = new MockEnvironment()
        .withProperty("feature.audit.enabled", "true");

    assertEquals(
        "true",
        env.getProperty("feature.audit.enabled")
    );
}
```

`MockEnvironment` tests logic at the `Environment` level. It does not instantiate configuration beans or evaluate `@ConditionalOnProperty` without a Spring context.

Use it as an auxiliary test for expression logic, not a replacement for container wiring tests.

## 39. Property precedence matrix in tests

When the same key appears in multiple places, Spring Boot applies property-source precedence rules. In tests, additional sources such as inline properties or dynamic properties typically take precedence over standard application files.

A test design table:

| Source | Example | Test goal |
|---|---|---|
| `application.yml` | `mode=local` | Default configuration |
| `application-prod.yml` | `mode=remote` | Profile-specific configuration |
| `@SpringBootTest(properties=...)` | `mode=test-remote` | Test-level override |
| `@TestPropertySource` | `mode=simulated` | Test-specific property source |
| `@DynamicPropertySource` | URL/port from fixture | Dynamic runtime values |

Do not memorize a rigid absolute order for every pair without knowing the app's version and bootstrap setup; what matters is **verifying the effective property** via `Environment` and then **verifying bean selection** via `ApplicationContext`.

If explicitly testing precedence, write a dedicated test whose name states the hypothesis clearly: e.g., "inline test property overrides config data." Avoid having business-logic tests depend on obscure multi-source override chains.

## 40. Checking why multiple beans share the same type

Suppose you have:

```java
@Bean
@Profile("dev | test")
NotificationChannel localChannel() { /* ... */ }

@Bean
@Profile("test | staging")
NotificationChannel anotherChannel() { /* ... */ }
```

When `test` is active, **both** expressions evaluate to true. If a service injects a single `NotificationChannel` by type without `@Primary` or `@Qualifier`, `NoUniqueBeanDefinitionException` can occur.

A helpful test:

```java
@Test
void testProfileDetectsAmbiguousConfiguration() {
    new ApplicationContextRunner()
        .withUserConfiguration(
            OverlappingChannelConfiguration.class,
            NotificationCoordinatorConfiguration.class
        )
        .withInitializer(context ->
            context.getEnvironment().setActiveProfiles("test")
        )
        .run(context -> {
            assertThat(context).hasFailed();
        });
}
```

`OverlappingChannelConfiguration` is an illustrative configuration declaring the beans above; the test verifies the missing selection rule when both implementations coexist.

If the design intends both beans to be present, instead of failing, inject `List<NotificationChannel>` or `Map<String, NotificationChannel>`, or use `@Qualifier` to select a specific bean.

Tests must mirror the consumer's **selection contract**, rather than assuming multiple beans are always a bug.

## 41. Verifying the selected bean by type, name, and behavior

There are three distinct checks:

**By type:**

```java
NotificationChannel channel =
        context.getBean(NotificationChannel.class);

assertThat(channel)
        .isInstanceOf(RemoteNotificationChannel.class);
```

**By bean name:**

```java
assertThat(context.containsBean("remoteNotificationChannel"))
        .isTrue();

assertThat(context.containsBean("localNotificationChannel"))
        .isFalse();
```

**By behavior:**

```java
assertThat(channel.channelName())
        .isEqualTo("remote");
```

Combined with count:

```java
assertThat(context)
        .hasSingleBean(NotificationChannel.class);
```

Combine these assertions when bean selection is a contract worth protecting. Checking only bean names couples tightly to implementation details; checking only behavior may miss duplicate type registrations if both implementations return similar values.

## 42. Testing fail-fast vs. fallback

Both policies are valid, but you must choose explicitly:

### Policy A — Fail-fast

In production, if remote configuration is missing, the application cannot finish starting.

Strengths:

- Catches deployment errors early.
- Avoids silently running an unsafe implementation.
- Makes deployment failures easy to monitor.

Risks:

- Temporarily missing config makes the service unavailable.
- Requires clear error messages and thorough configuration procedures.

### Policy B — Fallback

When remote is disabled, use a local or no-op implementation.

Strengths:

- Keeps the application running when secondary features are optional.
- Convenient for offline or dev/test modes.

Risks:

- Can mask production errors if the fallback fails to meet requirements.
- Can cause the system to report success without performing the intended side effect.

Tests must state the policy clearly. For example, use a `NoOpNotificationChannel` for optional notifications, rather than falling back to a local fake sender in a system that strictly requires sending notifications.

A configuration should never "just pick something automatically" without knowing what the business rules require.

## 43. Testing with @ConditionalOnExpression and compound conditions

Some projects use compound conditions:

```java
@Bean
@Profile("prod & cloud")
@ConditionalOnProperty(
    prefix = "integration.notifications",
    name = "enabled",
    havingValue = "true"
)
NotificationChannel remoteChannel() {
    return new RemoteNotificationChannel();
}
```

For the bean to register, **both** the profile expression and the property condition must match.

Build a matrix:

| Active profiles | enabled | Remote expected |
|---|---|---|
| `prod,cloud` | true | Yes |
| `prod` | true | No |
| `cloud` | true | No |
| `prod,cloud` | false | No |
| `prod,cloud` | missing | No |
| `prod,cloud,maintenance` | true | Yes unless a condition negates maintenance |

Do not mistake `@Profile("prod & cloud")` for SpEL. It uses Spring's profile-expression grammar (`&`, `|`, `!`). `@ConditionalOnExpression` is a different, expression-based condition with its own semantics and pitfalls.

With many branches, test combinations prioritized by risk rather than testing only the happy path.

## 44. When a bean is missing due to package scanning

Not every absent bean stems from profiles or properties.

For instance, the main application class sits in:

```text
com.example.orders.OrdersApplication
```

while the service sits in:

```text
com.another.team.NotificationService
```

If default component scanning covers only the main class's package and subpackages, services in external packages will not be discovered.

When testing with `ApplicationContextRunner.withUserConfiguration(...)`, you pass the configuration manually so the test passes, yet the full application still fails to scan it.

Check:

1. Is the bean created via `@Bean` or `@Component`?
2. Is the configuration imported or scanned?
3. Are there `@Profile` or `@Conditional...` annotations?
4. Which classes does the test context load?
5. Which packages does the production application scan?

Add a `@SpringBootTest` integration check loading the main application configuration to verify the bean truly exists when booted as deployed.

## 45. When the property exists yet the bean is still wrong

A logical debugging pipeline:

```text
Property source
       │
       ▼
Spring Environment
       │
       ├── Profile conditions
       │
       ├── ConditionalOnProperty
       │
       └── ConfigurationProperties binder
       │
       ▼
Bean definitions
       │
       ▼
Dependency injection
       │
       ▼
Implementation used by consumer
```

When outcomes are wrong, ask in order:

- Is the property named accurately and placed in the right source?
- Is a higher-precedence source overriding it?
- Is the profile actually active in the context?
- Do `havingValue` and `matchIfMissing` match the contract?
- Is the configuration class registered?
- Are multiple candidate beans present with `@Primary`/`@Qualifier` influencing selection?
- Is the consumer receiving a real bean or a mock/test override?
- Is the test running on a production-like context or a narrow slice?

Tracing from input to output is usually faster than guessing Spring "picked wrong" from a single exception.

## 46. Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Test confirms profile is active yet bean is missing | Configuration not scanned/imported, or another condition failed | Inspect `ApplicationContext` and bean definitions |
| Dev test passes yet prod picks local | Profile expression too broad or prod config not loaded | Test `prod` with realistic properties |
| Both implementations created | Overlapping expressions | Design mutually exclusive conditions or use qualifier/primary |
| `NoUniqueBeanDefinitionException` | Multiple beans of same type, consumer needs one | Check count and injection resolution |
| `NoSuchBeanDefinitionException` in prod | No condition matched | Decide whether fail-fast or fallback is required |
| Bean created even when property is false | Misunderstood `havingValue`/condition defaults | Test true, false, and missing separately |
| `@ActiveProfiles("prod & cloud")` does not behave as expected | Not how two profile names are activated | Use `@ActiveProfiles({"prod", "cloud"})` |
| `@Profile({"dev","test"})` does not require both | Array has OR semantics | Use `@Profile("dev & test")` for AND |
| Tests using `System.setProperty` do not update beans | Context already cached and built | Separate contexts/test classes or use `ContextRunner` |
| Test slice cannot see service | Slice omits unrelated components | Use `@SpringBootTest` or explicit context runner |
| Mock hides real implementation | Bean override masks selection | Do not mock the bean whose selection is under test |
| `@Value` property exists, yet configprops is empty | `configprops` reflects registered properties beans | Check injection point or `Environment` |
| Profile YAML not loaded | Wrong active profiles, filename, or config-data loading context | Check Boot startup context and property sources |
| Duration conversion failure | Invalid property format or missing converter | Test binding failure and format |
| Local tests pass, production fails | Differences in dependencies, classpath, profiles, env, scanned modules | Add main-app integration test |
| Unusually slow tests | Too many `@SpringBootTest`/`@DirtiesContext` | Use `ApplicationContextRunner` for configuration matrices |

## 47. Practical workflow for designing the test suite

A repeatable workflow when adding a configuration with multiple implementations:

1. Write the **contract**: which service needs which interface and when an implementation must exist.
2. Draw the profile/property matrix, including missing and mixed-profile rows.
3. Design mutually exclusive conditions or clear resolution rules when multiple beans coexist.
4. Write `ApplicationContextRunner` tests for each row of the matrix.
5. Assert **bean count**, concrete type/name, and behavior where appropriate.
6. Add expected startup-failure tests if a missing bean is a deployment error.
7. Add `@ConfigurationProperties` binding/validation tests if selection depends on typed config.
8. Add a few `@SpringBootTest` checks for main-application integration wiring.
9. Avoid mocking the exact bean whose selection you are trying to verify.
10. Verify profile-specific YAML and test property precedence where they matter in practice.
11. Keep tests deterministic; avoid external system dependencies when testing pure conditions.
12. On failure, narrow down using `Environment`, `ConditionEvaluationReport`, and bean inventory rather than randomly tweaking annotations.

## 48. Hands-on exercises

### Exercise A — Two profile-based implementations

Create `PaymentGateway` with `FakePaymentGateway` and `RemotePaymentGateway`. Use `@Profile("!prod")` and `@Profile("prod")`. Write two `@SpringBootTest` classes with `@ActiveProfiles("dev")` and `@ActiveProfiles("prod")`, then assert the concrete bean type.

### Exercise B — Add a property gate

Create the remote gateway only if `payment.remote.enabled=true`. Test `true`, `false`, and missing when the `prod` profile is active. Assert fail-fast or no-bean per contract.

### Exercise C — Test matrix with ApplicationContextRunner

Create a shared `ApplicationContextRunner` for the configuration, using `withInitializer(...)` to vary active profiles and `withPropertyValues(...)` to vary flags. Assert count and type for every row in the decision table.

### Exercise D — Profile expression

Create a bean active only under `@Profile("(dev | staging) & cloud")`. Test with `dev`, `dev,cloud`, `staging,cloud`, and `prod,cloud`. Explain why `@ActiveProfiles({"dev","cloud"})` differs from passing a single string `"dev & cloud"`.

### Exercise E — @Primary and @Qualifier

Register two beans for the same interface and mark one `@Primary`. Test that both exist while the default consumer receives the primary. Then add `@Qualifier` to another consumer and verify it receives the alternate implementation.

### Exercise F — @ConditionalOnMissingBean

Create an auto-configuration providing a default `Clock` if the app has none. Test both the missing-bean state and the user-defined clock state. Confirm the default configuration backs off when a user bean is present.

### Exercise G — @ConfigurationProperties

Bind `integration.client.timeout=5s` into `Duration` and `max-attempts=3` into `int`. Test valid values, missing properties, malformed `Duration`, and negative attempts when validation is enabled.

### Exercise H — Dynamic properties

Start a test server or container on a dynamic port; use `@DynamicPropertySource` to supply the endpoint URL to the Spring test context. Explain why you should not hardcode the port and why the supplier needs a compatible lifecycle.

### Exercise I — Context caching

Write two test methods sharing a `@SpringBootTest` context and try changing a Java system property between methods. Observe why bean configuration does not rebuild automatically, and fix the suite using independent contexts.

### Exercise J — Test slice

Create a `@WebMvcTest` for a controller depending on a service. Observe that the slice does not load the service automatically. Propose an appropriate test for the HTTP contract and a separate test for profile/property selection.

### Exercise K — Fallback vs. fail-fast

In production when the remote flag is missing, compare two choices: local fallback versus fail-fast. Pick the reasonable behavior for a critical transaction and write a test enforcing that decision.

### Exercise L — Debugging a wrong selection

Suppose the remote bean appears when `dev` is active. Form hypotheses around `@Profile`, property conditions, scanning, duplicate bean declarations, and mock overrides. Build checks tracing from `Environment` to `ApplicationContext` to pinpoint the cause.

## 49. Summary

1. **Testing profiles** goes beyond reading active profile names: you must prove the right bean is registered or excluded.
2. **`@ActiveProfiles`** activates profile names in a Spring Test context; it is not a profile-expression parser.
3. **`@Profile("dev & cloud")`** uses AND, whereas **`@Profile({"dev","cloud"})`** uses OR.
4. **`@SpringBootTest(properties=...)`** and `@TestPropertySource` supply test-specific properties.
5. **`ApplicationContextRunner`** excels at quickly testing many profile/property combinations and bean registration conditions.
6. With context runners, setting active profiles directly via an initializer expresses test scenarios clearly.
7. **`@ConditionalOnProperty`** should be tested at least for `true`, `false`, and missing cases, especially when `havingValue` and `matchIfMissing` are significant.
8. **Bean selection** should be verified by count, name, type, and behavior—not merely checking that `Environment` holds a key.
9. When **`@Primary`** or **`@Qualifier`** is involved, verify which bean the consumer actually receives rather than just counting beans.
10. **`@ConditionalOnMissingBean`** lets default configurations step aside when a user implementation exists; configuration ordering must be understood and tested.
11. **`@ConfigurationProperties`** should be tested for both typed field binding and validation where applicable.
12. **`@DynamicPropertySource`** supplies values generated by test resources, yet does not cause a context to rebind after refresh.
13. **Context caching** speeds up suites, but makes mutating `System.setProperty` between methods unreliable for testing bean registration.
14. **Mocks and test slices** are helpful, yet can mask the very implementation-selection logic you need to test.
15. **Fail-fast and fallback** are distinct policies; tests must reflect business requirements.
16. Spring conditions are evaluated during context construction; changing runtime properties does not automatically swap injected implementations.
17. A strong test suite pairs **narrow tests across many combinations** with **a few real integration tests** proving the main app loads configurations properly.
18. When outcomes are wrong, investigate in order: profile/property sources → conditions → bean definitions → dependency injection → behavior.

**Core mindset:** reliable configuration tests must answer **"Given this set of profiles and properties, exactly how many beans will Spring create, which implementation will the consumer receive, and what happens when conditions are invalid?"** Answering these three questions catches configuration bugs before they ever reach real deployments.
