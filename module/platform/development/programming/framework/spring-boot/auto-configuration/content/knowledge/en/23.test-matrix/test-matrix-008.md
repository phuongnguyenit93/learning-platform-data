# Testing Standalone Features and Multi-Feature Integration in Spring Boot Auto Configuration

A custom starter can provide multiple features: shared infrastructure, metrics, audit, web adapters, or optional integrations. Each feature may work properly when tested in isolation, yet when appearing together in one application, they can still conflict over beans, conditions, properties, registration order, or coordination.

Therefore, an auto-configuration test suite needs two complementary perspectives:

- **Testing each feature independently:** isolating the auto-configuration and the inputs required for that specific feature. The goal is to know which conditions enable/disable it, which default beans are created, and which user beans cause the configuration to back off.
- **Testing multi-feature integration:** loading multiple auto-configurations into the same context, sharing infrastructure, and verifying that features coexist, coordinate properly, respect their individual properties, and do not create duplicate beans or missing dependencies.

`ApplicationContextRunner` fits both perspectives. Each test builds a context with deterministic inputs, allowing selection of auto-configurations, properties, user configurations, and classpath. When you need to test the full application, discovery from the JAR, environment configuration, component scanning, or an HTTP server, add integration tests with `@SpringBootTest`.

## 1. Why are both standalone tests and integration tests needed?

Suppose a custom starter provides three components:

- `EventBus`: shared event publishing infrastructure.
- `MetricsListener`: receives events to count activity.
- `AuditListener`: receives events to record history.

Each feature has its own conditions:

- The event bus has a default bean if the application has not provided its own `EventBus`.
- Metrics is enabled only when `demo.metrics.enabled=true`.
- Audit is enabled only when `demo.audit.enabled=true`.
- Both listeners require `EventBus`.

If you only test each feature in its own separate context, you do not know whether both listeners actually receive the same event. If you only test one context containing every feature, when a bean is missing or a condition is wrong, it is harder to isolate which feature caused the failure.

| Test type | Context scope | Key question | Example |
| --- | --- | --- | --- |
| Standalone feature | Required infrastructure + one auto-configuration | Does the feature enable properly, create the right beans, and handle its own dependencies? | EventBus + Metrics, without loading Audit. |
| Another standalone feature | Required infrastructure + another auto-configuration | Can the second feature run on its own? | EventBus + Audit, without loading Metrics. |
| Multi-feature integration | Multiple auto-configurations in the same context | Do the features share beans and coordinate properly? | EventBus + Metrics + Audit all receiving one event. |
| Property matrix | One set of auto-configurations, varying property combinations | Does turning off one feature accidentally disable another? | Metrics on, Audit off; then reversed. |
| Application integration | ApplicationContext close to a real app, possibly with a server | Is the starter discovered, configured, and operating properly in a consumer app? | `@SpringBootTest` with realistic configuration. |

The first two layers enable precise diagnosis. The integration layer catches interaction bugs. Application integration tests confirm components work the way a real application actually boots.

## 2. Building a deterministic context with `ApplicationContextRunner`

`ApplicationContextRunner` lets you construct a small context for each scenario. Instead of booting the entire application, the test loads only the auto-configurations under examination.

A base runner is usually declared as a field:

```java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        EventBusAutoConfiguration.class,
                        MetricsAutoConfiguration.class
                ));
```

Key points:

- `withConfiguration(AutoConfigurations.of(...))` selects which auto-configurations to load.
- `withPropertyValues(...)` controls Environment for each test.
- `withUserConfiguration(...)` adds bean configurations provided by the application.
- `withBean(...)` adds a bean directly to the runner when you only need to simulate one dependency.
- `withClassLoader(new FilteredClassLoader(...))` simulates a library or class being absent from the runtime classpath.
- `withInitializer(...)` adds context initialization hooks, such as enabling `ConditionEvaluationReportLoggingListener`.
- `run(context -> ...)` creates the context, runs assertions, and closes the context after the callback.

The runner has a builder-style API: each `with...` method returns a customized runner. Keep the returned value or chain calls; do not call a method and discard the new runner.

**Each `run` call is an isolated trial.** Do not rely on bean instances from an earlier test. Create dependencies inside the context/supplier or use immutable data to avoid state leakage between tests.

### 2.1. Loading multiple auto-configurations

Multiple classes can be passed to a single `AutoConfigurations.of`:

```java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
                EventBusAutoConfiguration.class,
                MetricsAutoConfiguration.class,
                AuditAutoConfiguration.class
        ));
```

Spring Boot applies the auto-configurations in the same order as when running an application; do not try to order the argument list to simulate runtime ordering. If one configuration truly depends on another, declare the relationship explicitly with `@AutoConfiguration(after = ...)`, `before`, or `@AutoConfigureAfter`/`@AutoConfigureBefore`.

Auto-configuration order affects **the order in which bean definitions are processed**. It does not dictate the instantiation order of every bean; instance creation depends on the dependency graph and `@DependsOn` relationships.

## 3. Defining boundaries between standalone and integration tests

A standalone test must still load the feature's **required infrastructure**. "Standalone" means not loading unrelated features, not intentionally omitting a dependency that the feature needs.

Example:

- Metrics test: load EventBus + Metrics.
- Audit test: load EventBus + Audit.
- Coordination test: load EventBus + Metrics + Audit.

Do not load every auto-configuration of the starter in all tests merely for the convenience of sharing one runner. Create base runners according to each test boundary:

```java
private final ApplicationContextRunner metricsRunner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        EventBusAutoConfiguration.class,
                        MetricsAutoConfiguration.class
                ));

private final ApplicationContextRunner auditRunner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        EventBusAutoConfiguration.class,
                        AuditAutoConfiguration.class
                ));

private final ApplicationContextRunner combinedRunner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        EventBusAutoConfiguration.class,
                        MetricsAutoConfiguration.class,
                        AuditAutoConfiguration.class
                ));
```

This split produces three kinds of evidence:

1. Each feature runs with minimal infrastructure.
2. Both features can share the infrastructure in one context.
3. Failures appearing only when combined are localized to the integration layer.

## 4. End-to-end example: EventBus, Metrics, and Audit

Let us build a Spring Boot 3.3.5 / Java 17 experiment. Two features have separate properties yet share a single `EventBus`. The goal is to prove:

- Metrics runs when enabled, even if Audit is not loaded.
- Audit runs when enabled, even if Metrics is not loaded.
- When both are enabled, each event is received once by both listeners.
- Disabling one property does not disable the other feature.
- If EventBus is absent, features depending on it back off.
- Infrastructure or listener beans provided by the application are respected.

### 4.1. Project structure

```text
feature-matrix-lab/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── FeatureMatrixTest.java
```

Content of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>feature-matrix-lab</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 4.2. Complete test file

Create `src/test/java/demo/FeatureMatrixTest.java`:

```java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureMatrixTest {

    static final class EventBus {
        private final String source;
        private final List<Consumer<String>> subscribers =
                new CopyOnWriteArrayList<>();

        EventBus(String source) {
            this.source = source;
        }

        String source() {
            return this.source;
        }

        void subscribe(Consumer<String> subscriber) {
            this.subscribers.add(subscriber);
        }

        void publish(String event) {
            this.subscribers.forEach(subscriber -> subscriber.accept(event));
        }
    }

    static final class MetricsListener implements Consumer<String> {
        private final String source;
        private final AtomicInteger received = new AtomicInteger();

        MetricsListener(String source) {
            this.source = source;
        }

        String source() {
            return this.source;
        }

        int count() {
            return this.received.get();
        }

        @Override
        public void accept(String event) {
            this.received.incrementAndGet();
        }
    }

    static final class AuditListener implements Consumer<String> {
        private final List<String> events = new CopyOnWriteArrayList<>();

        @Override
        public void accept(String event) {
            this.events.add(event);
        }

        List<String> events() {
            return List.copyOf(this.events);
        }
    }

    @AutoConfiguration
    static class EventBusAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(EventBus.class)
        EventBus eventBus() {
            return new EventBus("auto-configured");
        }
    }

    @AutoConfiguration(after = EventBusAutoConfiguration.class)
    @ConditionalOnBean(EventBus.class)
    @ConditionalOnProperty(
            prefix = "demo.metrics",
            name = "enabled",
            havingValue = "true"
    )
    static class MetricsAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(MetricsListener.class)
        MetricsListener metricsListener(EventBus eventBus) {
            MetricsListener listener = new MetricsListener("auto-configured");
            eventBus.subscribe(listener);
            return listener;
        }
    }

    @AutoConfiguration(after = EventBusAutoConfiguration.class)
    @ConditionalOnBean(EventBus.class)
    @ConditionalOnProperty(
            prefix = "demo.audit",
            name = "enabled",
            havingValue = "true"
    )
    static class AuditAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(AuditListener.class)
        AuditListener auditListener(EventBus eventBus) {
            AuditListener listener = new AuditListener();
            eventBus.subscribe(listener);
            return listener;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserEventBusConfiguration {

        @Bean
        EventBus eventBus() {
            return new EventBus("user");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserMetricsConfiguration {

        @Bean
        MetricsListener metricsListener(EventBus eventBus) {
            MetricsListener listener = new MetricsListener("user");
            eventBus.subscribe(listener);
            return listener;
        }
    }

    private final ApplicationContextRunner metricsRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            EventBusAutoConfiguration.class,
                            MetricsAutoConfiguration.class
                    ));

    private final ApplicationContextRunner auditRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            EventBusAutoConfiguration.class,
                            AuditAutoConfiguration.class
                    ));

    private final ApplicationContextRunner combinedRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            EventBusAutoConfiguration.class,
                            MetricsAutoConfiguration.class,
                            AuditAutoConfiguration.class
                    ));

    @Test
    void metricsWorksWithoutLoadingAuditFeature() {
        metricsRunner
                .withPropertyValues("demo.metrics.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(EventBus.class);
                    assertThat(context).hasSingleBean(MetricsListener.class);
                    assertThat(context).doesNotHaveBean(AuditListener.class);

                    EventBus bus = context.getBean(EventBus.class);
                    MetricsListener metrics =
                            context.getBean(MetricsListener.class);

                    bus.publish("order-created");

                    assertThat(metrics.count()).isEqualTo(1);
                });
    }

    @Test
    void auditWorksWithoutLoadingMetricsFeature() {
        auditRunner
                .withPropertyValues("demo.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(EventBus.class);
                    assertThat(context).hasSingleBean(AuditListener.class);
                    assertThat(context).doesNotHaveBean(MetricsListener.class);

                    EventBus bus = context.getBean(EventBus.class);
                    AuditListener audit = context.getBean(AuditListener.class);

                    bus.publish("payment-approved");

                    assertThat(audit.events())
                            .containsExactly("payment-approved");
                });
    }

    @Test
    void bothFeaturesReceiveTheSameEventThroughOneBus() {
        combinedRunner
                .withPropertyValues(
                        "demo.metrics.enabled=true",
                        "demo.audit.enabled=true"
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(EventBus.class);
                    assertThat(context).hasSingleBean(MetricsListener.class);
                    assertThat(context).hasSingleBean(AuditListener.class);

                    EventBus bus = context.getBean(EventBus.class);
                    MetricsListener metrics =
                            context.getBean(MetricsListener.class);
                    AuditListener audit = context.getBean(AuditListener.class);

                    bus.publish("invoice-issued");

                    assertThat(metrics.count()).isEqualTo(1);
                    assertThat(audit.events()).containsExactly("invoice-issued");
                });
    }

    @ParameterizedTest
    @CsvSource({
            "false, false, false, false",
            "true,  false, true,  false",
            "false, true,  false, true",
            "true,  true,  true,  true"
    })
    void featurePropertiesAreIndependent(
            boolean metricsEnabled,
            boolean auditEnabled,
            boolean expectMetrics,
            boolean expectAudit) {

        combinedRunner
                .withPropertyValues(
                        "demo.metrics.enabled=" + metricsEnabled,
                        "demo.audit.enabled=" + auditEnabled
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(EventBus.class);

                    assertThat(context.getBeansOfType(MetricsListener.class))
                            .hasSize(expectMetrics ? 1 : 0);

                    assertThat(context.getBeansOfType(AuditListener.class))
                            .hasSize(expectAudit ? 1 : 0);
                });
    }

    @Test
    void featureBacksOffWhenSharedInfrastructureIsNotImported() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        MetricsAutoConfiguration.class
                ))
                .withPropertyValues("demo.metrics.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(EventBus.class);
                    assertThat(context).doesNotHaveBean(MetricsListener.class);
                });
    }

    @Test
    void userInfrastructureIsSharedByBothFeatures() {
        combinedRunner
                .withUserConfiguration(UserEventBusConfiguration.class)
                .withPropertyValues(
                        "demo.metrics.enabled=true",
                        "demo.audit.enabled=true"
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(EventBus.class))
                            .containsOnlyKeys("eventBus");

                    EventBus bus = context.getBean(EventBus.class);
                    assertThat(bus.source()).isEqualTo("user");

                    bus.publish("shipment-dispatched");

                    assertThat(context.getBean(MetricsListener.class).count())
                            .isEqualTo(1);
                    assertThat(context.getBean(AuditListener.class).events())
                            .containsExactly("shipment-dispatched");
                });
    }

    @Test
    void userMetricsListenerOverridesOnlyTheMetricsDefault() {
        combinedRunner
                .withUserConfiguration(UserMetricsConfiguration.class)
                .withPropertyValues(
                        "demo.metrics.enabled=true",
                        "demo.audit.enabled=true"
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(MetricsListener.class);
                    assertThat(context).hasSingleBean(AuditListener.class);

                    MetricsListener metrics =
                            context.getBean(MetricsListener.class);
                    assertThat(metrics.source()).isEqualTo("user");

                    context.getBean(EventBus.class).publish("refund-created");

                    assertThat(metrics.count()).isEqualTo(1);
                    assertThat(context.getBean(AuditListener.class).events())
                            .containsExactly("refund-created");
                });
    }
}
```

Run from the `feature-matrix-lab` directory with JDK 17+ and Maven:

```bash
mvn test
```

**Expected result:** all tests succeed. There are seven test methods; `featurePropertiesAreIndependent` runs four property combinations via a JUnit parameterized test. In total, contexts are created ten times. The tests do not call `System.out.println`, so there is no fixed business stdout; Maven Surefire reports results by actual test invocation count.

## 5. Understanding what is being verified in the example

### 5.1. Standalone tests verify each feature's contract

`metricsWorksWithoutLoadingAuditFeature` loads only EventBus and Metrics. It verifies Metrics works when Audit is not in the context. The corresponding test for Audit proves the second feature does not depend on Metrics being enabled.

When a standalone test fails, the investigation scope is narrow:

- Was the property passed correctly?
- Does the condition on the feature class match?
- Did the infrastructure exist before `@ConditionalOnBean` was evaluated?
- Did the bean method back off because of a user bean or another bean of the same type?
- Can the listener's constructor/dependencies be instantiated?

There is no need to analyze interactions between two features before tests have even proven that each feature runs independently.

### 5.2. Integration tests verify behavior, not just presence

In `bothFeaturesReceiveTheSameEventThroughOneBus`, important assertions do not stop at having all three beans present. The test publishes an event through EventBus and verifies:

- Metrics receives the event exactly once.
- Audit records that exact event.
- Only one EventBus exists in the context.

If you only assert `hasSingleBean`, tests can miss bugs where a listener fails to subscribe, subscribes twice, or uses a different EventBus by mistake. Verify **coordinated behavior** across features.

### 5.3. Property matrix catches cross-toggle bugs

`featurePropertiesAreIndependent` checks all four combinations:

| `demo.metrics.enabled` | `demo.audit.enabled` | Metrics | Audit |
| --- | --- | --- | --- |
| `false` | `false` | Absent | Absent |
| `true` | `false` | Present | Absent |
| `false` | `true` | Absent | Present |
| `true` | `true` | Present | Present |

This is a two-feature Boolean matrix. With three Boolean features, all combinations are `2³ = 8`; with four features, `2⁴ = 16`. It is not strictly necessary to run every combination if certain conditions can be proven independent, yet you should test combinations likely to interact through shared dependencies or shared properties.

As the number of features grows, group by dependency graph and interaction risk. For example, if both Metrics and Audit depend on EventBus, prioritize:

- Each feature individually with EventBus.
- Both features together with EventBus.
- One feature on, the other off.
- Application-provided EventBus.
- EventBus absent or optional dependency missing.

### 5.4. Testing back-off at infrastructure level and feature level

`featureBacksOffWhenSharedInfrastructureIsNotImported` does not load EventBusAutoConfiguration. Even though the Metrics property is `true`, Metrics still does not appear because `@ConditionalOnBean(EventBus.class)` does not match.

`userInfrastructureIsSharedByBothFeatures` adds the application's EventBus. The starter's default bean yields; both features share the user-provided bean.

`userMetricsListenerOverridesOnlyTheMetricsDefault` proves a narrowly scoped override: the default Metrics listener backs off, while Audit is still created. Overriding one feature must not accidentally disable other features unless the contract requires it.

## 6. Auto-configuration order and cross-feature dependencies

A common integration bug occurs when feature B has `@ConditionalOnBean` depending on a bean provided by feature A, yet A and B lack a clear ordering relationship.

Example:

```java
@AutoConfiguration
class EventBusAutoConfiguration {
    // Registers EventBus.
}

@AutoConfiguration(after = EventBusAutoConfiguration.class)
@ConditionalOnBean(EventBus.class)
class MetricsAutoConfiguration {
    // Applies only when EventBus already has a bean definition.
}
```

`@AutoConfiguration(after = EventBusAutoConfiguration.class)` expresses the dependency relationship when processing bean definitions. It is useful when Metrics needs EventBus to already be registered before its condition runs.

Key rules:

- `@ConditionalOnBean` and `@ConditionalOnMissingBean` evaluate bean definitions processed up to the moment the condition runs.
- Boot auto-configurations are processed after user-defined bean definitions; this is why back-off conditions allow applications to replace defaults.
- If another auto-configuration provides infrastructure, declare `before`/`after` explicitly rather than relying on arbitrary list order.
- `@AutoConfigureOrder` fits when ordering is needed among auto-configurations that should not depend on each other directly.
- Bean definition order differs from instance initialization order; dependency injection and `@DependsOn` govern instance creation.

In integration tests, load the same set of auto-configurations that the application will use. `AutoConfigurations.of` applies Boot's ordering mechanism; there is no need to reorder arguments manually to simulate runtime.

## 7. Using Condition Evaluation Report when a feature does not appear

When a multi-feature integration test runs, the report helps identify which configuration class or bean method failed to match its conditions.

You can enable report logging in the runner:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

ApplicationContextRunner runner = new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO
                )
        )
        .withConfiguration(AutoConfigurations.of(
                EventBusAutoConfiguration.class,
                MetricsAutoConfiguration.class,
                AuditAutoConfiguration.class
        ));
```

Or read `ConditionEvaluationReport` directly from the context's BeanFactory. When investigating, focus on:

- `positiveMatches`: sources whose conditions matched.
- `negativeMatches`: sources with at least one unmatched condition; read the specific reason.
- `ClassName#beanMethod`: bean-method-level conditions, which can differ from class-level condition outcomes.
- Actual bean names/types in the context: verify that a matching condition resulted in the expected bean definition.

For instance, the Metrics class may match the property, while the method creating `MetricsListener` still backs off because the application supplied a custom listener. That is right if the contract allows replacement. Conversely, if class-level `@ConditionalOnBean(EventBus.class)` does not match, check whether EventBus was registered before Metrics.

## 8. When is `@SpringBootTest` needed instead of a runner?

`ApplicationContextRunner` explicitly loads selected auto-configurations and creates a small context. It is a great choice for testing condition logic, bean registration, and cross-feature interactions. However, it does not by itself prove the entire real application startup process.

Use `@SpringBootTest` or a consumer integration test when you need to check:

- Whether `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` inside the published JAR is discovered by Boot.
- Whether a consumer application pulls in the right starter via the dependency graph.
- Whether properties from `application.yml`, profiles, environment variables, or the command line produce expected results.
- Whether component scanning, user configuration, and Boot's default auto-configurations interact properly.
- Whether Servlet/Reactive servers, HTTP routes, filters, security chains, or real resources work properly.
- Whether database, broker, cache, or external service connections work in an integrated environment.

Example skeleton for a consumer application:

```java
@SpringBootTest(
        classes = ConsumerApplication.class,
        properties = {
                "demo.metrics.enabled=true",
                "demo.audit.enabled=true"
        }
)
class StarterConsumerIntegrationTest {

    @Autowired
    EventBus eventBus;

    @Autowired
    MetricsListener metrics;

    @Autowired
    AuditListener audit;

    @Test
    void bothFeaturesAreAvailableInConsumerApplication() {
        eventBus.publish("integration-event");

        assertThat(metrics.count()).isEqualTo(1);
        assertThat(audit.events()).containsExactly("integration-event");
    }
}
```

This is a skeleton for a consumer project with the starter and auto-configuration imports properly packaged. `ConsumerApplication` is a real Spring Boot application. If you need to test a web server, set the appropriate `webEnvironment` and call endpoints via an HTTP test client.

**Distinguish scopes:** the runner loads specified classes, making it well suited for proving the behavior of those auto-configurations. Consumer integration tests also verify artifact discovery and how a real application boots. The two tests answer different questions.

## 9. How should the test matrix be designed with multiple features?

There is no need to generate every permutation mechanically. Build the matrix around the **dependency graph**, **enable/disable conditions**, and **intersection points**.

| Scenario group | Question to answer | Priority examples |
| --- | --- | --- |
| Default behavior | Without user config, what does the starter provide? | Default infrastructure and each default feature. |
| Individual feature | Does each feature run independently with required dependencies? | Core + Metrics; Core + Audit. |
| Property isolation | Does disabling feature A affect feature B? | A=true/B=false and A=false/B=true. |
| Combined behavior | Do features coordinate through shared infrastructure? | One event received by both listeners. |
| User override | Does a user bean replace the right default while keeping other features? | Custom EventBus; custom MetricsListener. |
| Missing optional dependency | Does a missing external library break other features? | Use `FilteredClassLoader` to remove an adapter's dependency. |
| Ordering | Do conditions depending on beans from another auto-config run properly? | Feature after Core infrastructure. |
| Conflict/ambiguity | Are there multiple beans of the same type or name? | Two implementations, `@Primary`, qualifiers, and bean names. |
| Full application | Are the artifact and consumer configuration loaded properly? | `@SpringBootTest` with the published starter. |

If a feature works only in a Servlet or Reactive context, use `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner` respectively. If a feature depends on an optional library, use `FilteredClassLoader` to simulate absent classes/packages; assertions should confirm the expected bean/configuration backed off.

A practical workflow:

1. Draw the dependency graph: which feature needs which infrastructure, and which features can run independently.
2. Write default tests for each feature.
3. Write enable/disable property tests for each feature.
4. Write user override tests at each extension point.
5. Write combined tests for feature groups sharing beans or ordering.
6. Add full application tests only for risks that cannot be observed with a context runner.

For n completely independent features, there is no need to test every possible subset. For features sharing beans or cross-conditions, test combinations that touch the same dependencies.

## 10. Common mistakes in multi-feature tests

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Feature runs alone yet disappears when run with another feature | Bean condition, bean name/type, or ordering differs from expectations | Read the report for both class and method; check bean definitions existing when the condition runs. |
| Both features create two infrastructure beans | Auto-configurations do not share a contract type or lack `@ConditionalOnMissingBean` | Standardize the shared interface/type and back off by type. |
| Disabling A's property makes B disappear | B depends on A's class-level configuration or shared property | Separate conditions per feature; use a shared property only when that is an intentional contract. |
| Listener exists yet receives no events | Listener did not subscribe to the right EventBus or subscribed twice | Assert publish/receive behavior and verify beans share the same bus instance. |
| Tests pass alone yet fail when loaded together | Duplicate bean names, multiple candidates of the same type, unmatched conditions, or conflicting config | Assert the bean map, check ambiguity, and test user overrides. |
| Results change based on class order in test | Relying on import order instead of declaring ordering | Use `@AutoConfiguration(after/before = ...)` or `@AutoConfigureOrder`. |
| Test uses one huge context that is too hard to diagnose | Loading too many unrelated auto-configurations | Go back to standalone tests, then add related features one by one. |
| Runner tests pass yet consumer app does not load the feature | AutoConfiguration.imports, dependency artifact, or discovery was not checked | Add a consumer integration test with `@SpringBootTest` and inspect the JAR. |
| Tests depend on a real database/broker | Condition test pulls side effects or external connection beans into context | Replace dependencies with fake/in-memory test configuration; reserve real connections for a dedicated integration suite. |
| Condition report matches yet the bean is unusable | Bean definition was registered but initialization or runtime interaction failed | Inspect startup failures and test bean behavior after context refresh. |

## 11. Organizing the test suite for maintainability

A directory layout can be split by feature and integration:

```text
src/test/java/
└── com/example/starter/
    ├── autoconfigure/
    │   ├── EventBusAutoConfigurationTests.java
    │   ├── MetricsAutoConfigurationTests.java
    │   └── AuditAutoConfigurationTests.java
    ├── integration/
    │   ├── MetricsAndAuditIntegrationTests.java
    │   ├── CustomInfrastructureIntegrationTests.java
    │   └── StarterConsumerIntegrationTests.java
    └── support/
        ├── TestEventBus.java
        └── TestListeners.java
```

Suggested division:

- Feature test files contain property, classpath, missing-bean, and custom-bean cases for that feature.
- Integration files contain cooperating features, shared infrastructure, ordering, and conflict cases.
- Test support holds reusable fake or in-memory infrastructure.
- Consumer tests verify the artifact, imports resource, and near-production configuration.

Do not put all tests into one giant class. Test names should express behavior, such as `auditBacksOffWhenUserAuditListenerExists` or `metricsAndAuditShareOneEventBus`.

## 12. Checklist before concluding auto-configuration is thoroughly tested

- [ ] Each feature has at least one standalone test with minimal infrastructure.
- [ ] Enable/disable properties of each feature are tested.
- [ ] User bean overrides are tested against the exact type/name conditions.
- [ ] Features sharing infrastructure have tests inside the same context.
- [ ] Integration tests exercise actual behavior, not just bean presence.
- [ ] Important property combinations are tested to catch cross-toggle bugs.
- [ ] Conditions depending on beans from other auto-configurations have explicit ordering declarations.
- [ ] Missing optional dependencies and web contexts are tested with appropriate runners.
- [ ] No mutable bean state is shared across `run` calls.
- [ ] Condition Evaluation Report is used whenever an unmatched branch needs explanation.
- [ ] Consumer integration tests exist when verifying AutoConfiguration.imports, artifacts, and real startup.
- [ ] External services are faked in context tests and tested for real only in an intentional integration suite.

**Takeaway:** standalone testing proves each feature fulfills its own contract; integration testing proves features coexist and coordinate properly inside a single ApplicationContext. Use `ApplicationContextRunner` to precisely control configuration/property/bean combinations, then use `@SpringBootTest` when you need to verify consumer application startup and artifact discovery. Do not just verify that beans are created; publish events, invoke collaborators, and assert cross-feature behavior.

### Official References

- Spring Boot 3.3 — Testing Your Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Testing Spring Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-applications.html
- Spring Boot 3.3 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.3 API — `AutoConfigurations`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurations.html
- Spring Boot 3.3 API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html