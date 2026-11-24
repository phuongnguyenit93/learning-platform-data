# ApplicationContextRunner for Narrowly Scoped Configuration and Conditions

In a Spring Boot application, not every bug lives inside service logic or a REST controller. Many errors occur right when Spring builds the `ApplicationContext`: a bean fails to register even though a property is enabled, two beans compete for the same type, an auto-configuration fails to back off when the user defines a custom bean, or a `@ConditionalOnClass` condition behaves incorrectly when a dependency is absent.

Using `@SpringBootTest` for all those scenarios forces tests to spin up far too much: component scanning, `DataSource`, a mock web server, security configuration, and unrelated auto-configurations. Sometimes what you need to verify is a very narrow question:

> Given a specific set of beans, classpath, and properties, does Spring create this exact bean or not?

**`ApplicationContextRunner`** is a Spring Boot Test utility built for questions like that. It creates a small Spring context according to configurations explicitly declared by the test, runs a callback to assert the outcome, and closes the context. It is especially well suited for **narrowly scoped Spring configurations, bean registration conditions, and auto-configuration**, rather than replacing every style of integration test.

This lesson walks from the basic API through testing `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, `@ConditionalOnClass`, configuration ordering, simulated classpaths, context startup failures, debugging condition reports, and limitations compared to `@SpringBootTest`. Examples focus on Spring Boot with `ApplicationContextRunner` and `AutoConfigurations`; package imports and supporting APIs may vary slightly across framework generations.

## 1. Why test Spring configuration?

Suppose an application has an audit-logging library that wants to provide auto-configuration:

- When `demo.audit.enabled=true`, automatically create a default `AuditSink`.
- When the property is disabled or absent, do not create the default `AuditSink`.
- If the application has already declared a custom `AuditSink`, the auto-configuration must **back off** instead of creating a second bean.
- If an optional dependency is absent, the related configuration must not activate.
- If the user misconfigures something, the error should be clear and predictable.

These requirements are about **bean registration**, not HTTP responses or database rows.

A good test suite must verify both **present** and **absent** conditions:

| Scenario | Expected outcome |
|---|---|
| Audit enabled, no custom bean | Exactly one default `AuditSink` exists |
| Audit disabled | No default `AuditSink` created |
| Property missing, default disabled | No default `AuditSink` created |
| Audit enabled, user bean exists | User bean is used; no default bean created |
| Optional library missing | Auto-configuration depending on it does not activate |
| Required bean missing | Context reports startup failure per defined contract |

`ApplicationContextRunner` lets you construct each scenario individually without booting the whole application.

## 2. What is ApplicationContextRunner?

Main class:

~~~java
org.springframework.boot.test.context.runner.ApplicationContextRunner
~~~

Basic usage:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner();
~~~

The runner is a **builder-like test utility**. You supply desired configurations, properties, beans, or classloaders, then call `run(...)`.

~~~java
contextRunner
        .withUserConfiguration(MyConfiguration.class)
        .withPropertyValues("demo.feature.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(MyService.class);
        });
~~~

Inside the callback, `context` is an **assertable context** provided by Spring Boot Test. It lets you:

- Check whether a bean exists.
- Retrieve a specific bean to inspect state or behavior.
- Check whether context startup succeeded or failed.
- Inspect properties added to `Environment`.
- Verify the configuration produced the exact bean count or type expected.

Once the callback completes, the runner handles closing the test context. You generally do not need to call `context.close()` manually.

### The strength lies in explicit control

Unlike a full-application test, the runner does not automatically scan every configuration in the project just because the test sits in the same package. You explicitly specify the configuration classes or auto-configurations to place in the context.

This makes outcomes easy to explain: if a bean is missing, the suspects are limited to the configurations and dependencies you supplied.

## 3. Comparison with @SpringBootTest

| Criterion | `ApplicationContextRunner` | `@SpringBootTest` |
|---|---|---|
| Purpose | Testing narrowly scoped configs and conditions | Testing a Spring Boot application at broader scope |
| How configuration is chosen | Explicitly declared on the runner | Can locate main configuration and apply Boot bootstrap |
| Initialization cost | Usually lower | Usually higher depending on the app |
| Component scanning | Does not auto-scan the entire project | Can run per application configuration |
| Auto-configuration | Only configurations added explicitly | Typically the application's full set of auto-configurations |
| Database/web infrastructure | Not needed unless added | May be created or required |
| Property scenarios | Concise per-scenario overrides via `withPropertyValues` | Can use test properties/profiles and test context |
| Missing-class conditions | Convenient `FilteredClassLoader` | Hard to simulate different classpaths within tests |
| End-to-end HTTP/database | Not the primary goal | Better suited when paired with relevant test facilities |
| Catching app-wide wiring bugs | Only within declared subset | Broader coverage |

### The runner is not always better

If you need to know whether a REST controller is protected by security filters, whether JPA mappings boot against a real database, or whether the whole application starts cleanly, a broader test fits better.

If you only need to verify a `@ConditionalOnProperty` across three property values, booting the full context is usually unnecessary.

**Pick the tool based on the scope you need to prove**, not raw test speed alone.

## 4. Required dependencies and imports

Typically a Spring Boot test project includes:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

With Gradle Kotlin DSL:

~~~kotlin
dependencies {
    testImplementation(
        "org.springframework.boot:spring-boot-starter-test"
    )
}

tasks.test {
    useJUnitPlatform()
}
~~~

A test usually imports:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.autoconfigure.AutoConfigurations;

import static org.assertj.core.api.Assertions.assertThat;
~~~

Spring annotations depending on the example also include:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
~~~

`ApplicationContextRunner` is a **test utility**, so it belongs in the test source set/scope. There is no reason to add `spring-boot-test` to the production runtime dependencies just to use the runner in tests.

## 5. Minimal example: one @Configuration, one bean

Create the configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class ClockConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Test it:

~~~java
class ClockConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(ClockConfiguration.class);

    @Test
    void registersClock() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(Clock.class);

            Clock clock = context.getBean(Clock.class);
            assertThat(clock.getZone()).isEqualTo(ZoneOffset.UTC);
        });
    }
}
~~~

Meaning of each part:

1. `new ApplicationContextRunner()` creates the initial runner.
2. `withUserConfiguration(ClockConfiguration.class)` adds the user configuration class to the test context.
3. `run(context -> ...)` creates a fresh context, evaluates bean definitions, and runs assertions.
4. `hasSingleBean(Clock.class)` asserts there is exactly one bean of type `Clock` in the context.
5. `context.getBean(Clock.class)` lets you verify actual bean behavior/state.

The test requires neither a main Spring Boot application nor starting a web server.

### Why proxyBeanMethods=false?

In simple configuration classes, `@Configuration(proxyBeanMethods = false)` disables proxying meant to intercept calls between `@Bean` methods. It fits when bean methods do not directly invoke one another to obtain singleton dependencies.

This is a configuration class design/optimization choice; it is **not an on/off switch** for `ApplicationContextRunner`. The runner works with both regular and lite configurations.

## 6. The runner creates a new context for each run

A runner can be declared as a test field:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withUserConfiguration(ClockConfiguration.class);
~~~

Then reused multiple times:

~~~java
@Test
void firstScenario() {
    contextRunner.run(context -> {
        assertThat(context).hasSingleBean(Clock.class);
    });
}

@Test
void secondScenario() {
    contextRunner.run(context -> {
        assertThat(context).hasSingleBean(Clock.class);
    });
}
~~~

Each `run` invocation initializes an independent context and closes it after the callback completes. Do not store a bean retrieved inside the callback to use after the context has closed, especially if the bean holds connections, executors, or lifecycle-managed resources.

### Runners can be customized without mutating the base field

Example:

~~~java
private final ApplicationContextRunner baseRunner =
        new ApplicationContextRunner()
                .withUserConfiguration(ClockConfiguration.class);

@Test
void scenarioWithExtraProperty() {
    baseRunner
            .withPropertyValues("demo.mode=fast")
            .run(context -> {
                assertThat(context.getEnvironment()
                        .getProperty("demo.mode"))
                        .isEqualTo("fast");
            });
}
~~~

The `with...` methods produce derived runner configurations designed for reuse. This lets scenarios share the same baseline without properties from one test leaking into the next.

### Do not reuse ApplicationContext after the callback

The following snippet shows what to avoid:

~~~java
AtomicReference<MyService> ref = new AtomicReference<>();

contextRunner.run(context -> {
    ref.set(context.getBean(MyService.class));
});

// Bean may belong to an already-closed context:
ref.get().execute();
~~~

Place assertions and invocations inside the callback, or use a test context whose lifecycle is managed by the test framework if longer observation is required.

## 7. Testing @ConditionalOnProperty

This is one of the most common use cases for `ApplicationContextRunner`.

Suppose an application has an audit recording interface:

~~~java
public interface AuditSink {
    void record(String eventName);
}
~~~

Default implementation:

~~~java
public final class ConsoleAuditSink implements AuditSink {

    @Override
    public void record(String eventName) {
        System.out.println("AUDIT: " + eventName);
    }
}
~~~

Auto-configuration:

~~~java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    @ConditionalOnMissingBean(AuditSink.class)
    AuditSink auditSink() {
        return new ConsoleAuditSink();
    }
}
~~~

`@ConditionalOnProperty` decides whether to register the bean when the property holds the required value; `matchIfMissing = false` means missing the property causes the condition not to match.

### A dedicated runner for auto-configuration

~~~java
class AuditAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AuditAutoConfiguration.class
                            )
                    );

    @Test
    void registersAuditSinkWhenEnabled() {
        contextRunner
                .withPropertyValues("demo.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditSink.class);
                    assertThat(context.getBean(AuditSink.class))
                            .isInstanceOf(ConsoleAuditSink.class);
                });
    }

    @Test
    void doesNotRegisterAuditSinkWhenDisabled() {
        contextRunner
                .withPropertyValues("demo.audit.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AuditSink.class);
                });
    }

    @Test
    void doesNotRegisterAuditSinkWhenPropertyMissing() {
        contextRunner.run(context -> {
            assertThat(context).doesNotHaveBean(AuditSink.class);
        });
    }
}
~~~

The tests separate the three scenarios cleanly. There is no need to create three `@SpringBootTest` classes or three startup configurations for these simple conditions.

### Verify the exact contract, not just that the context starts

A test doing only:

~~~java
contextRunner.run(context ->
        assertThat(context).hasNotFailed()
);
~~~

can pass even when the target bean was never registered. With conditional configuration, verify **presence, absence, and the expected bean type**.

## 8. Understanding ConditionalOnProperty states accurately

With the configuration:

~~~java
@ConditionalOnProperty(
        prefix = "demo.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
~~~

general outcomes:

| `demo.audit.enabled` | Condition matches? |
|---|---|
| `true` | Yes |
| `false` | No |
| Undeclared | No |
| Another string, e.g. `enabled` | No when `havingValue="true"` |

If `havingValue` is omitted, `@ConditionalOnProperty` semantics should not be thought of as simple Java boolean parsing in all cases; the condition typically treats any present property not equal to `false` as matching. Thus, for boolean toggles, specifying `havingValue = "true"` makes the contract clearer.

### matchIfMissing=true

~~~java
@ConditionalOnProperty(
        prefix = "demo.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
~~~

When the property is absent, the condition matches. This fits features enabled by default and disabled only when explicitly set to `false`.

When testing, include a test for **missing property**; testing only `true`/`false` does not prove default semantics.

### Do not use a single test to claim full precedence

`withPropertyValues` sets properties on the context runner. It verifies the values supplied to the condition, but does not verify full precedence across command-line arguments, environment variables, and Config Data in a real `SpringApplication`. When multi-source precedence is the goal, test at a broader scope.

## 9. withPropertyValues accepts multiple key=value pairs

Example:

~~~java
contextRunner
        .withPropertyValues(
                "demo.audit.enabled=true",
                "demo.audit.prefix=ORDER",
                "demo.audit.batch-size=25"
        )
        .run(context -> {
            Environment environment = context.getEnvironment();

            assertThat(
                    environment.getProperty("demo.audit.prefix")
            ).isEqualTo("ORDER");

            assertThat(
                    environment.getProperty(
                            "demo.audit.batch-size",
                            Integer.class
                    )
            ).isEqualTo(25);
        });
~~~

The parameter format is property assignment strings. It is handy for testing a specific set of parameters tied to a bean.

### A property string does not configure everything automatically

If an auto-configuration reads `@ConfigurationProperties`, binding needs the appropriate infrastructure. If a bean reads `Environment` directly, properties can be accessed from `Environment`. Without a registered configuration class or binding, merely adding a property **does not create any bean**.

### Pick easily distinguishable values

When testing property binding, use a value distinct from the default to be sure the configuration actually took effect:

~~~java
.withPropertyValues("demo.audit.batch-size=37")
~~~

Then assert `37` instead of a value that happens to match the code's default.

## 10. Difference between withUserConfiguration and withConfiguration

Two easily confused APIs:

~~~java
.withUserConfiguration(UserProvidedConfiguration.class)
~~~

and:

~~~java
.withConfiguration(
        AutoConfigurations.of(MyAutoConfiguration.class)
)
~~~

Both add configuration to the context runner, yet they represent **different roles**.

| API | Typically used for |
|---|---|
| `withUserConfiguration(...)` | Configuration classes supplied by the application/user |
| `withConfiguration(AutoConfigurations.of(...))` | Auto-configuration classes under test |
| `withBean(...)` | Registering an individual bean for a scenario |
| `withInitializer(...)` | Adding custom initialization logic to the context |
| `withPropertyValues(...)` | Selecting `Environment` values for a scenario |

Spring Boot auto-configurations follow ordering and back-off rules relative to user beans. Using the API matching each role simulates how auto-configuration is actually consumed.

### Example with two configuration layers

~~~java
contextRunner
        .withUserConfiguration(CustomAuditConfiguration.class)
        .withConfiguration(
                AutoConfigurations.of(AuditAutoConfiguration.class)
        )
        .withPropertyValues("demo.audit.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(AuditSink.class);
        });
~~~

The goal is verifying that when the user already supplies a bean, auto-configuration does not create an extra default bean given a matching `@ConditionalOnMissingBean`.

### The runner does not automatically load every auto-configuration in the app

Merely writing:

~~~java
new ApplicationContextRunner()
~~~

is not equivalent to booting the whole app via `@SpringBootApplication`. You must explicitly supply the auto-configurations under test to the runner.

This is both an isolation advantage and a limitation: a narrow test can pass even if full-app integration fails because another configuration was omitted from the runner's context.

## 11. Testing @ConditionalOnMissingBean: back-off

A well-behaved Spring Boot starter supplies a default implementation while letting the host application provide a custom bean.

Suppose `AuditAutoConfiguration` declares:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "demo.audit",
        name = "enabled",
        havingValue = "true"
)
@ConditionalOnMissingBean(AuditSink.class)
AuditSink auditSink() {
    return new ConsoleAuditSink();
}
~~~

Create a custom bean:

~~~java
public final class InMemoryAuditSink implements AuditSink {

    private final List<String> records = new ArrayList<>();

    @Override
    public void record(String eventName) {
        records.add(eventName);
    }

    public List<String> records() {
        return List.copyOf(records);
    }
}
~~~

Test using `withBean`:

~~~java
@Test
void backsOffWhenCustomBeanExists() {
    contextRunner
            .withPropertyValues("demo.audit.enabled=true")
            .withBean(AuditSink.class, InMemoryAuditSink::new)
            .run(context -> {
                assertThat(context).hasSingleBean(AuditSink.class);

                assertThat(context.getBean(AuditSink.class))
                        .isInstanceOf(InMemoryAuditSink.class);
            });
}
~~~

This test verifies two things:

1. Only one bean of type `AuditSink` is registered.
2. That bean is the custom implementation, not the default `ConsoleAuditSink`.

Checking only that a bean exists would miss the case where auto-configuration wrongly creates a second bean and causes ambiguity in another service.

### Why does @ConditionalOnMissingBean care about ordering?

`@ConditionalOnMissingBean` evaluates bean definitions registered at that point in time. In auto-configurations, it is designed to run after user configurations in appropriate contexts.

If you arbitrarily place that condition on user configurations or organize processing order improperly, outcomes can diverge from expectations. `ApplicationContextRunner` paired with `AutoConfigurations.of(...)` tests this boundary properly.

### Test the reverse direction too

Do not only test back-off. Also verify that when no custom bean exists, the default is actually created:

~~~java
@Test
void usesDefaultWhenNoCustomBean() {
    contextRunner
            .withPropertyValues("demo.audit.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(AuditSink.class);
                assertThat(context.getBean(AuditSink.class))
                        .isInstanceOf(ConsoleAuditSink.class);
            });
}
~~~

## 12. Registering fake beans without full mocking infrastructure

`withBean` is useful for supplying a simple collaborator to the configuration under test.

Suppose a service requires `RemoteClient`:

~~~java
public interface RemoteClient {
    String fetchStatus();
}
~~~

A test implementation:

~~~java
public final class StubRemoteClient implements RemoteClient {

    @Override
    public String fetchStatus() {
        return "OK";
    }
}
~~~

Runner:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(StatusConfiguration.class)
        .withBean(RemoteClient.class, StubRemoteClient::new)
        .run(context -> {
            assertThat(context).hasSingleBean(StatusService.class);
            assertThat(context.getBean(StatusService.class).status())
                    .isEqualTo("OK");
        });
~~~

When you only need to verify wiring and conditions, a simple fake or stub is often clearer than adding Mockito annotations, Spring test mocks, or booting a remote service.

### A fake does not mean integration testing is complete

The stub only proves the configuration builds the service using the supplied dependency. It does not prove the real HTTP client handles endpoints, TLS, timeouts, or serialization. Those belong in a separate test.

## 13. Testing @ConditionalOnBean

An auto-configuration may activate only when a collaborator already exists:

~~~java
@AutoConfiguration
public class ReportingAutoConfiguration {

    @Bean
    @ConditionalOnBean(AuditSink.class)
    ReportingService reportingService(AuditSink auditSink) {
        return new ReportingService(auditSink);
    }
}
~~~

Two scenarios:

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                ReportingAutoConfiguration.class
                        )
                );

@Test
void doesNotCreateReportingServiceWithoutAuditSink() {
    runner.run(context -> {
        assertThat(context).doesNotHaveBean(
                ReportingService.class
        );
    });
}

@Test
void createsReportingServiceWhenAuditSinkExists() {
    runner.withBean(AuditSink.class, InMemoryAuditSink::new)
            .run(context -> {
                assertThat(context).hasSingleBean(
                        ReportingService.class
                );
            });
}
~~~

`ReportingService` is an illustrative business class whose constructor accepts `AuditSink`.

### Dependence on definition registration order

`@ConditionalOnBean` and `@ConditionalOnMissingBean` rely on bean definitions present when the condition is evaluated. For interdependent auto-configurations, `@AutoConfiguration(after = ...)` or explicit ordering metadata may be required.

If a test provides only one configuration class while the real app has several related auto-configurations, identify which ordering is part of the contract and pass all needed configurations into the runner together.

## 14. Testing multiple related auto-configurations

Example:

~~~java
@AutoConfiguration
public class CoreAuditAutoConfiguration {

    @Bean
    AuditSink auditSink() {
        return new ConsoleAuditSink();
    }
}
~~~

An additional configuration:

~~~java
@AutoConfiguration(after = CoreAuditAutoConfiguration.class)
public class ReportingAutoConfiguration {

    @Bean
    @ConditionalOnBean(AuditSink.class)
    ReportingService reportingService(AuditSink auditSink) {
        return new ReportingService(auditSink);
    }
}
~~~

Runner:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(
                        CoreAuditAutoConfiguration.class,
                        ReportingAutoConfiguration.class
                )
        )
        .run(context -> {
            assertThat(context).hasSingleBean(AuditSink.class);
            assertThat(context).hasSingleBean(ReportingService.class);
        });
~~~

This remains a **narrowly scoped test**: only two auto-configuration classes are loaded instead of the entire application.

### Do not rely on accidental declaration order

If auto-configuration B must run after A, express it with explicit ordering metadata. Tests should verify the final contract rather than relying on incidental classpath or reflection order.

## 15. @ConditionalOnClass and conditional classpaths

An auto-configuration often applies only when an optional library exists:

~~~java
@AutoConfiguration
@ConditionalOnClass(OptionalAuditLibrary.class)
public class OptionalAuditAutoConfiguration {

    @Bean
    AuditExtension auditExtension() {
        return new AuditExtension();
    }
}
~~~

`OptionalAuditLibrary` and `AuditExtension` are illustrative classes. Condition semantics: apply the configuration only when the dependency is detected on the matching classpath.

To test when the dependency **is present**, the class exists on the test runtime classpath. But how do you test when the dependency **is missing** without removing it from the entire project build?

Spring Boot Test provides `FilteredClassLoader`.

## 16. FilteredClassLoader: simulating a missing class

Import:

~~~java
import org.springframework.boot.test.context.FilteredClassLoader;
~~~

Runner:

~~~java
@Test
void doesNotCreateExtensionWhenOptionalLibraryMissing() {
    contextRunner
            .withClassLoader(
                    new FilteredClassLoader(
                            OptionalAuditLibrary.class
                    )
            )
            .run(context -> {
                assertThat(context).doesNotHaveBean(
                        AuditExtension.class
                );
            });
}
~~~

The example assumes `contextRunner` already includes `OptionalAuditAutoConfiguration` via `AutoConfigurations.of(...)`.

`FilteredClassLoader` hides specified classes or packages from the class-loading process used by conditions, letting you test the missing-dependency path without creating a separate project build.

### Also test the class-present branch

~~~java
@Test
void createsExtensionWhenOptionalLibraryAvailable() {
    contextRunner.run(context -> {
        assertThat(context).hasSingleBean(AuditExtension.class);
    });
}
~~~

Thus the tests verify both the positive path and the negative path.

### Mind the limits of classpath simulation

`FilteredClassLoader` is a classloading test utility, not physically removing a JAR from a packaged application. If a configuration directly references the optional class in method signatures or static initializers, linkage or class-resolution errors can still occur in certain scenarios.

A well-designed auto-configuration isolates optional dependency boundaries safely—for example, placing `@ConditionalOnClass` on an appropriate configuration class so absent types are not eagerly resolved by the JVM.

## 17. When a class is missing, should configuration skip the bean or fail?

Two distinct contracts:

**Optional integration:**

~~~text
Optional library absent
        |
        v
Do not register integration bean
        |
        v
Application can still start
~~~

**Required dependency:**

~~~text
Required collaborator absent
        |
        v
Service cannot be constructed
        |
        v
Context startup fails with clear cause
~~~

`ApplicationContextRunner` can test both.

Do not use `@ConditionalOnClass` to silently omit a **required** feature while letting the application appear to succeed incorrectly. Decide clearly which dependencies are optional and which are required.

## 18. Testing intentional context startup failure

A configuration with a required dependency:

~~~java
@Configuration(proxyBeanMethods = false)
class BrokenReportingConfiguration {

    @Bean
    ReportingService reportingService(
            AuditSink auditSink
    ) {
        return new ReportingService(auditSink);
    }
}
~~~

Without an `AuditSink`, Spring cannot create the bean from this method.

Test:

~~~java
@Test
void failsWhenRequiredAuditSinkMissing() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    BrokenReportingConfiguration.class
            )
            .run(context -> {
                assertThat(context).hasFailed();

                assertThat(context.getStartupFailure())
                        .hasRootCauseInstanceOf(
                                NoSuchBeanDefinitionException.class
                        );
            });
}
~~~

The runner lets the callback observe the **startup failure**. With a regular Spring Test context that fails setup, the test framework halts before running the test method, making intentional failure inspection much harder.

### When is testing failure reasonable?

- The configuration requires a collaborator that is not supplied.
- A required property is missing and the app must fail fast.
- Two beans collide in name or type under a strict policy.
- Constructor or configuration properties validation fails.
- An optional library is misconfigured and the system must catch it early.

Do not write a failure-expecting test for a situation where auto-configuration is supposed to back off. Define the configuration contract first.

### Do not assert overly strictly on verbatim exception messages

Exception messages can change across Spring or Java versions. Unless verifying a specific application-owned message, prefer asserting the exception type, root cause, or meaningful error components rather than the entire message string.

## 19. Testing @ConfigurationProperties in a small context

Many auto-configurations use typed properties instead of reading `Environment` directly.

Example:

~~~java
@ConfigurationProperties(prefix = "demo.audit")
public class AuditProperties {

    private boolean enabled;
    private int batchSize = 100;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }
}
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AuditProperties.class)
class AuditPropertiesConfiguration {
}
~~~

Test:

~~~java
@Test
void bindsAuditProperties() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    AuditPropertiesConfiguration.class
            )
            .withPropertyValues(
                    "demo.audit.enabled=true",
                    "demo.audit.batch-size=37"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(
                        AuditProperties.class
                );

                AuditProperties props =
                        context.getBean(AuditProperties.class);

                assertThat(props.isEnabled()).isTrue();
                assertThat(props.getBatchSize()).isEqualTo(37);
            });
}
~~~

### The Binder does not run just because a class has the annotation

`@ConfigurationProperties` describes how to bind, yet the class must still be registered appropriately, such as via `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`. In a small context, explicitly register what is needed.

### Test default values

Add a test without setting `demo.audit.batch-size`:

~~~java
@Test
void usesDefaultBatchSize() {
    runner.run(context -> {
        AuditProperties properties =
                context.getBean(AuditProperties.class);

        assertThat(properties.getBatchSize())
                .isEqualTo(100);
    });
}
~~~

`runner` in this example is an `ApplicationContextRunner` with `AuditPropertiesConfiguration` registered.

Default values are an important part of the contract. If a missing property still allows startup with an unexpected value, a test checking only "bean exists" will miss the bug.

## 20. Testing invalid configuration properties

You can place Bean Validation constraints on properties:

~~~java
@ConfigurationProperties(prefix = "demo.client")
@Validated
public class ClientProperties {

    @Min(1)
    private int poolSize = 4;

    public int getPoolSize() {
        return poolSize;
    }

    public void setPoolSize(int poolSize) {
        this.poolSize = poolSize;
    }
}
~~~

When a Bean Validation provider and matching binding/validation mechanism are present, `pool-size=0` must violate the constraint.

Runner:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(
                ClientPropertiesConfiguration.class
        )
        .withPropertyValues("demo.client.pool-size=0")
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .isNotNull();
        });
~~~

The example assumes `ClientPropertiesConfiguration` uses `@EnableConfigurationProperties(ClientProperties.class)` and the test runtime includes `spring-boot-starter-validation` or a compatible Bean Validation provider.

### Why mention the provider explicitly?

If the test classpath lacks a validation implementation, behavior may differ from production. A negative validation test is only meaningful when the underlying infrastructure matches what you intend to protect.

### Distinguish binding errors from constraint errors

- `demo.client.pool-size=abc` can cause a string-to-integer conversion failure.
- `demo.client.pool-size=0` converts to a number yet violates `@Min(1)`.
- Omitting `pool-size` uses the default `4`.

These three branches should be tested separately when they form a key configuration contract.

## 21. Testing @ConditionalOnSingleCandidate and @Primary

An auto-configuration may require a single candidate to inject by type:

~~~java
@AutoConfiguration
public class MailReportAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(MailSender.class)
    MailReportService mailReportService(
            MailSender mailSender
    ) {
        return new MailReportService(mailSender);
    }
}
~~~

`MailSender` and `MailReportService` are illustrative types.

Scenarios to consider:

| Context contains | Typical expectation |
|---|---|
| No `MailSender` | No `MailReportService` |
| One `MailSender` | `MailReportService` created |
| Two `MailSender` beans, no priority choice | Condition does not match |
| Two `MailSender` beans, one marked primary | Resolves to a single candidate per condition semantics |

You can use `withBean` or `withUserConfiguration` to set up each scenario.

### Why test ambiguity?

If an auto-configuration constructs a bean via a constructor taking an interface while an application supplies two implementations, the context can fail or behave unexpectedly. Narrow tests catch this boundary before the library integrates into a large application.

## 22. Does @ConditionalOnMissingBean check by type, name, or annotation?

`@ConditionalOnMissingBean` offers several ways to specify the bean that must be absent. For example, by type:

~~~java
@ConditionalOnMissingBean(AuditSink.class)
~~~

or by bean name when the contract truly defines it by name:

~~~java
@ConditionalOnMissingBean(name = "defaultAuditSink")
~~~

The two conditions are not equivalent.

Suppose there is a custom `AuditSink` named `customAuditSink`:

- A **type**-based condition detects the existing bean and backs off.
- A **name**-based condition checking `defaultAuditSink` still matches because no bean carries that name, creating a second `AuditSink`.

When testing, pick scenarios matching the starter's actual extension contract: does the library promise "users can override with any bean of type `AuditSink`" or "the bean must have a specific name"?

### Do not assert only by bean name if the contract is by type

~~~java
assertThat(context).hasSingleBean(AuditSink.class);
~~~

is generally more meaningful than:

~~~java
assertThat(context).hasBean("auditSink");
~~~

when the library lets users declare any bean name.

Conversely, when the name itself is part of the contract (such as an integration looking up a bean by a fixed name), asserting the specific name makes sense.

## 23. Using ConditionEvaluationReport to explain conditions

When an auto-configuration does not match, "bean absent" might be right or wrong. To investigate, Spring Boot provides a **condition evaluation report** recording condition evaluation outcomes.

One way to log the condition report in tests is via a suitable initializer:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO)
                )
                .withConfiguration(
                        AutoConfigurations.of(
                                AuditAutoConfiguration.class
                        )
                );
~~~

The example uses `ConditionEvaluationReportLoggingListener` and `LogLevel` from Spring Boot. When executed, condition evaluation details appear in test log output depending on logging configuration.

### What does the report help answer?

A condition report helps determine:

- Which auto-configurations matched?
- Did `@ConditionalOnClass` find the dependency?
- Which property value did `@ConditionalOnProperty` observe?
- Did `@ConditionalOnBean` see the collaborator?
- Why was a branch excluded from bean registration?

If you want to inspect the report programmatically, `ConditionEvaluationReport` has an API. However, avoid coupling tests tightly to the report's internal wording. When testing contracts, keep asserting bean existence/absence or startup failure.

### The report does not fix errors by itself

If the condition report shows a bean was skipped due to a missing class, you still need to decide whether that is expected optional-integration behavior or a misconfigured project dependency.

## 24. Testing custom @Conditional

Sometimes a project has a custom condition:

~~~java
public class LocalModeCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        String mode = context.getEnvironment()
                .getProperty("demo.processing.mode", "remote");

        return "local".equals(mode);
    }
}
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
public class LocalProcessingConfiguration {

    @Bean
    @Conditional(LocalModeCondition.class)
    ProcessingClient localClient() {
        return new LocalProcessingClient();
    }
}
~~~

Runner:

~~~java
@Test
void enablesLocalClientForLocalMode() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    LocalProcessingConfiguration.class
            )
            .withPropertyValues(
                    "demo.processing.mode=local"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(
                        ProcessingClient.class
                );
            });
}
~~~

Negative scenario:

~~~java
@Test
void omitsLocalClientForRemoteMode() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    LocalProcessingConfiguration.class
            )
            .withPropertyValues(
                    "demo.processing.mode=remote"
            )
            .run(context -> {
                assertThat(context).doesNotHaveBean(
                        ProcessingClient.class
                );
            });
}
~~~

### Do not turn Condition into a place for business work

`Condition.matches(...)` is invoked by Spring during configuration registration. It should decide configuration cheaply using metadata and `Environment`—never call external APIs, write to databases, or cause hard-to-control side effects.

A narrow test can catch wrong condition logic, yet cannot fix architectural problems if the condition performs excessive work.

## 25. Testing @Profile with ApplicationContextRunner

`@Profile` is another Spring condition:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("dev")
public class DeveloperToolsConfiguration {

    @Bean
    DeveloperTools developerTools() {
        return new DeveloperTools();
    }
}
~~~

For property-based conditions, `withPropertyValues` usually suffices. With `@Profile`, distinguish placing a property in `Environment` from **explicitly activating profiles in the context**.

A clear approach is setting active profiles via an initializer:

~~~java
new ApplicationContextRunner()
        .withInitializer(context ->
                context.getEnvironment()
                        .setActiveProfiles("dev")
        )
        .withUserConfiguration(
                DeveloperToolsConfiguration.class
        )
        .run(context -> {
            assertThat(context).hasSingleBean(
                    DeveloperTools.class
            );
        });
~~~

Setting profiles must occur before configuration classes are evaluated. `withInitializer` prepares the `Environment` during the context initialization phase.

### Do not assume withPropertyValues runs full SpringApplication bootstrap

The test runner builds a narrow context and does not simulate the full Config Data and profile activation flow of `SpringApplication.run`. If a test truly needs to check how `application-dev.yml` loads by precedence, how `spring.config.import` behaves, or how profile groups expand, choose a test scope aligned with `SpringApplication` bootstrap.

### Test default profiles separately

When no profile is active, Spring `Environment` falls back to default profiles when evaluating conditions. You can set a default profile via initializer and test `@Profile("local")`. Distinguish `getActiveProfiles()` from `getDefaultProfiles()` when making assertions.

## 26. Using ApplicationContextInitializer to customize Environment

`withInitializer(...)` lets you plug an `ApplicationContextInitializer` into context creation.

Example:

~~~java
new ApplicationContextRunner()
        .withInitializer(context -> {
            context.getEnvironment()
                    .setActiveProfiles("local");

            context.getEnvironment()
                    .setDefaultProfiles("default");
        })
        .withUserConfiguration(
                LocalOnlyConfiguration.class
        )
        .run(context -> {
            assertThat(context).hasSingleBean(
                    LocalService.class
            );
        });
~~~

In this example, `LocalOnlyConfiguration` registers `LocalService` when `local` is active.

You can use initializers to:

- Add custom property sources.
- Set active or default profiles.
- Configure bean factory settings.
- Prepare special environment pieces needed by a condition.
- Attach a condition evaluation logging listener.

Do not stuff the entire production bootstrap into an initializer just to test a simple condition. If test setup becomes more complex than the configuration under test, the chosen scope may be wrong.

## 27. Testing @ConditionalOnResource

Some auto-configurations activate only when a classpath resource exists:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(
        resources = "classpath:demo/schema.json"
)
public class SchemaSupportConfiguration {

    @Bean
    SchemaSupport schemaSupport() {
        return new SchemaSupport();
    }
}
~~~

A context runner can use the same configuration to verify behavior on a test classpath with or without the resource present.

When needing to simulate an absent resource without altering project structure, you can use a controlled test classloader or fixture arrangement depending on the capabilities of your Spring Boot Test version.

### Key points

- `classpath:demo/schema.json` differs from arbitrary filesystem paths.
- The file must reside on the classpath actually visible to the context runner.
- A resource placed in `src/test/resources` may exist at test runtime while being absent from the production artifact.
- Do not rely on tests passing with a test-only resource to prove the production image packages the file properly.

For artifact packaging and resource inclusion, test the actual released JAR or image.

## 28. Auto-configuration tests must verify missing-dependency paths

Picture an optional integration starter:

~~~text
AuditClient on classpath?
        |
   +----+----+
   |         |
  No        Yes
   |         |
   v         v
No audit    demo.audit.enabled?
bean             |
             +---+---+
             |       |
            No      Yes
             |       |
             v       v
          No bean   Custom AuditSink exists?
                         |
                    +----+----+
                    |         |
                   Yes        No
                    |         |
                    v         v
                 Back off   Create default
~~~

A meaningful test suite needs to exercise these branches:

1. Dependency absent.
2. Dependency present but feature disabled.
3. Dependency present and feature enabled.
4. Feature enabled and custom bean present.

You do not need to test every possible property permutation if they add no meaningful behavior. However, **each major conditional decision** needs at least one test proving its key branches.

## 29. Testing bean aliases/names and @Primary when needed

Some configurations create multiple beans for the same interface:

~~~java
@Configuration(proxyBeanMethods = false)
class GatewayConfiguration {

    @Bean
    @Primary
    Gateway primaryGateway() {
        return new MainGateway();
    }

    @Bean
    Gateway backupGateway() {
        return new BackupGateway();
    }
}
~~~

Runner:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(GatewayConfiguration.class)
        .run(context -> {
            assertThat(context).hasBean("primaryGateway");
            assertThat(context).hasBean("backupGateway");

            assertThat(context.getBean(Gateway.class))
                    .isInstanceOf(MainGateway.class);
        });
~~~

`Gateway`, `MainGateway`, and `BackupGateway` are illustrative types.

`hasSingleBean(Gateway.class)` **does not fit** here because the context holds two `Gateway` beans. The test should mirror the real contract: two beans exist, yet the `@Primary` bean is preferred on injection by type.

### Do not over-test implementation details

If a library only promises "a usable `Gateway` bean exists," asserting internal bean names makes tests brittle during refactoring. Conversely, if a bean name is a public extension point users rely on, it is part of the contract worth testing.

## 30. ApplicationContextRunner and bean lifecycles

The runner does more than parse bean definitions; it refreshes and closes the context so lifecycle callbacks can run.

Example:

~~~java
public final class ManagedClient implements AutoCloseable {

    private boolean closed;

    public boolean isClosed() {
        return closed;
    }

    @Override
    public void close() {
        closed = true;
    }
}
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class ManagedClientConfiguration {

    @Bean(destroyMethod = "close")
    ManagedClient managedClient() {
        return new ManagedClient();
    }
}
~~~

Inside the callback, the bean has not yet been closed by teardown:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(
                ManagedClientConfiguration.class
        )
        .run(context -> {
            ManagedClient client =
                    context.getBean(ManagedClient.class);

            assertThat(client.isClosed()).isFalse();
        });
~~~

After the callback, the runner closes the context per the test lifecycle. To observe a destruction callback, you can record state in an object outside the context in a controlled manner; never access a closed bean to do business work.

### Avoid resource leaks in test configurations

A configuration class that accidentally spawns an unclosed thread pool or a client holding sockets can hang the test suite or affect subsequent tests. Testing narrow configs reveals lifecycle ownership early, yet still requires proper `destroyMethod`, `@PreDestroy`, or resource cleanup.

## 31. Testing a failure scenario without running the entire app

A major advantage is verifying intentional failure paths. For instance, a configuration requiring a mandatory property:

~~~java
@Configuration(proxyBeanMethods = false)
class RequiredEndpointConfiguration {

    @Bean
    EndpointClient endpointClient(Environment environment) {
        String url = environment.getRequiredProperty(
                "demo.client.url"
        );
        return new EndpointClient(url);
    }
}
~~~

Test when the property is missing:

~~~java
@Test
void failsWhenUrlMissing() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    RequiredEndpointConfiguration.class
            )
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .isNotNull();
            });
}
~~~

Test when the property is provided:

~~~java
@Test
void createsClientWhenUrlProvided() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    RequiredEndpointConfiguration.class
            )
            .withPropertyValues(
                    "demo.client.url=https://example.test"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(
                        EndpointClient.class
                );
            });
}
~~~

`EndpointClient` is a hypothetical type with a constructor taking a URL string; the example only tests bean construction without making network calls.

### Never use a real URL to test configuration

A test verifying property binding and bean creation should use a valid dummy URL or a fake client. If a test accidentally calls a real endpoint, it becomes slow, flaky, and dependent on external environments without proving anything extra about the condition under test.

## 32. The runner and ApplicationContext types

`ApplicationContextRunner` suits **non-web application contexts** or configuration concerns that do not require simulating web infrastructure.

Spring Boot Test also supplies other runners when a web context is needed:

- `WebApplicationContextRunner` for servlet web context scenarios.
- `ReactiveWebApplicationContextRunner` for reactive web context scenarios.

Pick the matching runner when conditions depend on web application type:

~~~java
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET
)
~~~

or:

~~~java
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE
)
~~~

If you use the non-web `ApplicationContextRunner` to test a condition matching only servlet web applications, not matching is **correct for the context type**, not a bug in the condition.

### Web runners do not replace full HTTP integration tests

`WebApplicationContextRunner` builds the appropriate context type to check web-related bean configuration. It is not a request-level test with a real server, TLS, reverse proxy, or full security filter chain.

When you need to send real HTTP requests and check responses, use the appropriate web testing tool such as `MockMvc`, `WebTestClient`, or a server-based test depending on scope.

## 33. ApplicationContextRunner and auto-configuration imports

A Spring Boot auto-configuration is registered for application consumption through the auto-configuration imports mechanism. In modern Spring Boot generations, metadata typically lives in:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

That file lists the fully qualified names of auto-configuration classes.

When using the runner:

~~~java
.withConfiguration(
        AutoConfigurations.of(MyAutoConfiguration.class)
)
~~~

the test supplies the auto-configuration class directly into the context. This is great for verifying the auto-configuration's behavior, yet **does not prove that packaging metadata properly registered the class inside the JAR**.

### Two questions requiring tests at two layers

1. "If the auto-configuration is loaded, are its conditions and beans right?" → `ApplicationContextRunner` is ideal.
2. "When this library is added to a real application, is the auto-configuration discovered via imports metadata?" → requires testing packaging/auto-configuration import at an appropriate integration level.

A starter can have a completely valid auto-configuration class yet forget to list its name in the imports file; runner tests pointing directly at the class will still pass. Therefore do not rely on runner tests alone to conclude starter packaging is complete.

## 34. ApplicationContextRunner does not automatically read full application.yml

A common misconception: because the runner comes from Spring Boot Test, it automatically loads all `application.yml`, `application-dev.yml`, and `spring.config.import` files just like `SpringApplication.run`.

The runner is built for **narrow contexts**. When you write:

~~~java
new ApplicationContextRunner()
        .withPropertyValues("demo.mode=test")
~~~

you explicitly supply properties into the context. It does not by default run the full production-style Config Data bootstrap.

If a test needs to verify:

- Whether `spring.config.import` loads an external file properly.
- Whether profile-specific files merge/override as expected.
- Whether `SpringApplication` command-line/environment precedence is right.
- Whether configuration-tree secrets are read during bootstrap.

you need a test targeting **SpringApplication/Config Data loading** or a broader integration test.

### Narrow scope is a feature, not a pointless limitation

Not loading every config file from the project makes tests more deterministic, preventing results from depending on a development file the test author never meant to include.

## 35. Watch out when conditions touch web, databases, or external services

A conditional configuration might inspect the classpath or properties, yet the bean created inside opens a connection pool, hits the network, or spawns threads.

When the goal is strictly verifying the condition:

- Separate creation logic from remote-connection side effects.
- Supply fake collaborators via `withBean`.
- Keep bean creation safe for tests.
- Avoid expensive work inside conditional bean constructors.
- Do not pull the entire `DataSource` and JPA stack into tests if the condition does not require them.

If you need to verify that `DataSource` actually works, that is a separate integration testing problem rather than a narrow condition test.

### Narrow tests do not guarantee production performance

A three-bean context starting quickly does not prove a real application with hundreds of beans starts quickly. The runner measures local configuration behavior, not full startup benchmarks.

## 36. A pragmatic test matrix for auto-configuration

Suppose a Spring Boot starter library has the conditions:

~~~text
demo.audit.enabled=true
          AND
AuditClient class exists
          AND
No user-defined AuditSink
          |
          v
Register ConsoleAuditSink
~~~

Test matrix:

| Scenario | Enabled property | Optional class | Custom bean | Expected |
|---|---|---|---|---|
| A | False | Present | Absent | No sink created |
| B | True | Present | Absent | Default sink created |
| C | True | Absent | Absent | Default sink not created |
| D | True | Present | Present | Custom sink used, no default |
| E | Missing | Present | Absent | Per property condition default |
| F | True | Present | Two custom beans | Check ambiguity contract if needed |

Each scenario should clearly express its condition and assertion:

~~~java
@Test
void createsDefaultWhenEnabledAndDependencyAvailable() {
    runner.withPropertyValues("demo.audit.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(AuditSink.class);
            });
}
~~~

Name tests after the **cause**, not merely generic labels like `test1` or `test2`.

### Testing negative branches exposes overly broad conditions

If you only test B, an auto-configuration that unconditionally creates the bean even when the property is `false` would still pass. Branches A, C, and E enforce the boundaries of the conditions.

## 37. Common mistakes when using ApplicationContextRunner

| Symptom | Common cause | Resolution |
|---|---|---|
| Bean not created | Configuration class was not added to runner | Use `withUserConfiguration` or `withConfiguration` |
| Property condition fails to match | Wrong key/value or misunderstanding default semantics | Check `withPropertyValues` and `havingValue` |
| Context has unexpected multiple beans | Custom bean did not make auto-config back off | Check `@ConditionalOnMissingBean` and ordering |
| Context fails due to missing collaborator | Required bean not registered | Use `withBean` or fix configuration contract |
| Missing-class test does not work | Classloader not filtered properly | Use `FilteredClassLoader` and check real class |
| Test passes yet starter fails to auto-load in app | Missing auto-configuration imports metadata | Test packaging and discovery |
| Test passes yet real app fails | Test scope omitted interacting configurations | Add appropriate integration test |
| `@Profile` does not match | Only set property instead of activating profile on context | Use initializer to set active profiles |
| `@ConfigurationProperties` not bound | Properties type/binder not registered | Use `@EnableConfigurationProperties` appropriately |
| Negative validation does not fail | Missing Bean Validation provider | Check test dependencies and infrastructure |
| Assertion failure after callback | Bean/context already closed | Place assertions inside `run` |
| Web condition fails to match | Using non-web runner | Choose `WebApplicationContextRunner` or reactive equivalent |
| Exception caught losing root cause | Overly generic message assertion or wrong catch | Inspect `getStartupFailure()` |
| Failure test never reaches callback in broader test | Framework startup fails before test method | Use runner to inspect intentional startup failures |
| Order-dependent condition fails | Wrong auto-config ordering | Declare ordering metadata and test related configs together |
| Test runs too slowly | Pulling out-of-scope infrastructure beans | Trim configuration and use fake dependencies |

### Ask first: what are you testing?

If testing "is the bean registered when a property is enabled?", do not spin up a real database. If testing "can the database config connect?", a small runner is insufficient. Keep test boundaries consistent with the question being asked.

## 38. What to avoid: turning the runner into a full application test

An anti-pattern:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(
                StoreApplication.class,
                SecurityConfiguration.class,
                JpaConfiguration.class,
                WebConfiguration.class,
                MessagingConfiguration.class,
                SchedulerConfiguration.class
        )
        .run(context -> {
            assertThat(context).hasSingleBean(MyFeature.class);
        });
~~~

If `StoreApplication` carries `@SpringBootApplication`, broad component scanning and auto-configuration may activate, defeating isolation. Adding too many configuration classes makes the test slow and hard to reason about.

**Fix:** build a small configuration or properly scoped auto-configuration class, supply fake dependencies, and verify the target bean.

If you genuinely need the whole application, `@SpringBootTest` communicates that intent far more clearly.

## 39. What to avoid: using the runner to test pure business logic

If a service merely has a pricing method with no Spring configuration dependency:

~~~java
public final class DiscountCalculator {

    public BigDecimal apply(
            BigDecimal amount,
            BigDecimal discount
    ) {
        return amount.subtract(discount);
    }
}
~~~

then a plain Java test is simpler:

~~~java
@Test
void subtractsDiscount() {
    DiscountCalculator calculator =
            new DiscountCalculator();

    assertThat(
            calculator.apply(
                    new BigDecimal("100"),
                    new BigDecimal("15")
            )
    ).isEqualByComparingTo("85");
}
~~~

Do not spin up `ApplicationContextRunner` solely to call a method that has no DI or conditional configuration dependencies.

## 40. What to avoid: over-testing implementation details

A configuration test becomes brittle when asserting:

- Internal bean names that are not part of the public contract.
- Registration order that has no impact on behavior.
- Verbatim Spring Framework exception messages.
- Proxy class names rather than bean types or behavior.
- Total bean counts across the entire context rather than relevant beans.
- Exact log lines printed by condition reports.

Instead, focus on what the host application or other modules actually depend on:

- A bean implementing the contract exists when conditions are enabled.
- No default is created when the user provides an override.
- The right bean is chosen when multiple candidates exist.
- Startup fails fast when mandatory configuration is missing.
- Properties bind with the expected types and defaults.
- Integrations stay disabled when optional dependencies are absent.

### Tests can serve as documentation for a starter

When test names and assertions express these contracts clearly, they also help starter consumers understand how to customize the library without reading the entire auto-configuration source.

## 41. A complete example: mini starter with multiple conditions

Problem: a module provides a default audit sink only when:

1. Property `demo.audit.enabled=true`.
2. No custom `AuditSink` exists.

Definitions:

~~~java
public interface AuditSink {
    void record(String action);
}
~~~

~~~java
public final class ConsoleAuditSink implements AuditSink {

    @Override
    public void record(String action) {
        System.out.println("AUDIT: " + action);
    }
}
~~~

Auto-configuration:

~~~java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    @ConditionalOnMissingBean(AuditSink.class)
    AuditSink auditSink() {
        return new ConsoleAuditSink();
    }
}
~~~

Tests:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AuditAutoConfiguration.class
                            )
                    );

    @Test
    void enabledCreatesDefaultBean() {
        runner.withPropertyValues("demo.audit.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(AuditSink.class);

                    assertThat(context.getBean(AuditSink.class))
                            .isInstanceOf(ConsoleAuditSink.class);
                });
    }

    @Test
    void disabledDoesNotCreateBean() {
        runner.withPropertyValues("demo.audit.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(AuditSink.class);
                });
    }

    @Test
    void missingPropertyDoesNotCreateBean() {
        runner.run(context -> {
            assertThat(context)
                    .doesNotHaveBean(AuditSink.class);
        });
    }

    @Test
    void customBeanOverridesDefault() {
        runner.withPropertyValues("demo.audit.enabled=true")
                .withBean(
                        AuditSink.class,
                        InMemoryAuditSink::new
                )
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(AuditSink.class);

                    assertThat(context.getBean(AuditSink.class))
                            .isInstanceOf(InMemoryAuditSink.class);
                });
    }
}
~~~

`InMemoryAuditSink` is the test implementation introduced earlier.

These four tests cover the full core contract:

- Enabled: default created.
- Disabled: no default created.
- Missing property: no default created.
- Custom bean present: auto-configuration does not create an extra bean.

If the library also uses `@ConditionalOnClass`, add a `FilteredClassLoader` test for the missing-dependency branch. If the configuration binds properties, add tests for default values and invalid values.

### Why is this example narrow enough?

There are no REST controllers, `DataSource`, security filters, JPA repositories, or external services. The tests only instantiate beans affecting audit configuration. If one fails, maintainers can focus immediately on two conditions instead of wading through full application bootstrap logs.

## 42. Test naming and project organization

A common layout:

~~~text
src/
├── main/
│   └── java/com/example/audit/
│       ├── AuditAutoConfiguration.java
│       ├── AuditSink.java
│       └── ConsoleAuditSink.java
└── test/
    └── java/com/example/audit/
        └── AuditAutoConfigurationTests.java
~~~

If the module is a Spring Boot starter, auto-configuration and starter modules may be split. That does not change the testing principle: verify the configuration classes, bean contracts, and environment/classpath conditions directly.

Use clear test names:

~~~text
enabledCreatesDefaultBean
disabledDoesNotCreateBean
missingPropertyDoesNotCreateBean
customBeanOverridesDefault
missingOptionalLibraryDisablesIntegration
invalidPoolSizeFailsStartup
~~~

Test names expressing behavior under specific conditions help maintainers understand the goal immediately from test reports.

### Do not cram every condition into one callback

One giant callback does not automatically make a better test:

~~~java
runner.run(context -> {
    // Twenty assertions for unrelated features...
});
~~~

When conditions are independent, splitting scenarios makes failures pinpoint the broken branch and reduces investigation effort.

## 43. When should tests expand to the integration level?

Even after an auto-configuration is tested with the runner, gaps remain:

- Is the configuration actually discovered via imports metadata?
- Does it conflict with other auto-configurations in the application?
- Do the beans interact properly with a real `DataSource`?
- Do security and filter chains behave properly when running a web server?
- Does the app load production-like profiles and config files?
- Does the container image or native executable run properly?
- Do API requests/responses satisfy external contracts?

These questions are not answered by `ApplicationContextRunner` alone.

A balanced strategy:

~~~text
Unit tests (Java logic)
         |
         v
ApplicationContextRunner tests
  (conditions, bean wiring, property binding)
         |
         v
Focused integration tests
  (DB, web, messaging)
         |
         v
Full application / artifact smoke tests
         |
         v
Runtime deployment checks
~~~

Each layer has its own purpose and cost. Use the runner to catch configuration bugs early, not to eliminate necessary higher-layer tests.

## 44. A checklist for designing narrow configuration tests

When testing a configuration class or auto-configuration, ask:

1. **What is the target bean?** Define the type/name contract to protect.
2. **Which conditions govern its presence?** Properties, classpath, beans, resources, web type, or profiles?
3. **Is the unconfigured path clearly defined?** Enabled or disabled by default?
4. **Are custom bean overrides allowed?** How must `@ConditionalOnMissingBean` back off?
5. **Are there optional dependencies?** Simulate missing classes with `FilteredClassLoader`.
6. **Are property values bound?** Test both default and non-default values.
7. **Should invalid inputs fail fast?** Inspect `getStartupFailure()`.
8. **Is there ordering between auto-configurations?** Define ordering metadata explicitly.
9. **Are there web context dependencies?** Choose the matching web/reactive runner.
10. **Could the test hit real networks or databases?** Use fakes/stubs when only wiring is needed.
11. **Are unnecessary internal details asserted?** Focus on public behavior.
12. **Are both present and absent branches tested?** A single positive assertion is rarely enough.
13. **Is the test assuming the runner auto-loads `application.yml`?** Supply properties explicitly.
14. **Is the full application verified elsewhere?** The runner does not replace integration tests.
15. **Do callbacks hold resources after context close?** Keep assertions inside `run`.

This checklist serves as guidance when **designing tests**, not a requirement to write every possible case for every bean. For a simple configuration, two or three clear tests may be all you need.

## Conclusion

`ApplicationContextRunner` is the right Spring Boot Test tool for verifying **narrowly scoped configurations and bean registration conditions**. It builds a context from configurations, beans, properties, and classloaders supplied by the test, lets you directly assert bean presence, back-off behavior, and startup failures, and closes the context after the callback completes.

Core APIs include `withUserConfiguration(...)` for application configurations, `withConfiguration(AutoConfigurations.of(...))` for auto-configurations, `withPropertyValues(...)` to set `Environment` values, `withBean(...)` to supply custom collaborators, and `withClassLoader(new FilteredClassLoader(...))` to simulate missing optional dependencies. `withInitializer(...)` prepares special setup such as active profiles or condition reports.

The runner's greatest value is **scope control**: to find out whether an auto-configuration creates `AuditSink` when a property is enabled, you do not need to start a database, HTTP server, or full application. At the same time, respect its limits: the runner does not automatically verify packaging imports metadata, full Config Data bootstrap, HTTP behavior, or production artifacts. Combining narrow `ApplicationContextRunner` tests with targeted integration tests establishes a Spring Boot testing foundation that is fast, easy to diagnose, and reliable as your system grows.
