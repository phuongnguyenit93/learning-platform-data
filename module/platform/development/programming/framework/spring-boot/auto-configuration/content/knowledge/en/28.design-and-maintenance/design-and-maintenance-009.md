# Use regression tests to protect back-off and compatibility contracts

> **Goal:** Build a regression test suite proving that auto-configuration upholds its public contracts: providing default beans when appropriate, backing off for application-declared beans, honoring property/classpath/context conditions, and continuing to work across all Spring Boot versions the library commits to supporting.

This lesson belongs to **Design and Maintenance**, using Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+, JUnit Jupiter, and AssertJ. The focus is turning back-off rules into repeatable tests in CI. A single successful startup test is not enough to protect a starter; you must verify defaults, overrides, boundary conditions, JAR discovery, and a version matrix.

## 1. The back-off contract is part of the starter API

Auto-configuration provides convenient setup so applications can start using a library without manually declaring every bean. However, users need the ability to replace defaults with implementations tailored to their application.

Example:

~~~java
@AutoConfiguration
public class PaymentGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    DefaultPaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

Contracts the starter must uphold:

1. If no bean of type PaymentGateway is supplied by the application or another configuration, the starter registers the default.
2. If the application supplies a PaymentGateway bean, the default method backs off.
3. The application's bean is still injected and used through the PaymentGateway abstraction.
4. Property and classpath conditions decide whether the configuration is enabled per the published contract.
5. When upgrading Spring Boot, these public behaviors remain intact across all supported versions.

`@ConditionalOnMissingBean` matches only when the BeanFactory does not yet contain a bean matching the declared criteria. If placed on a `@Bean` method without specifying value, type, or name, the target type defaults to the method's return type. The condition sees only bean definitions processed up to evaluation time, so ordering between auto-configurations is also part of the contract to test. [Official API documentation](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).

## 2. Turn contracts into a test matrix

Before writing tests, list the scenarios starter users can encounter. Each row in the matrix must map to an observable behavior.

| Scenario | Setup | Contract that must hold |
| --- | --- | --- |
| No custom bean | Load auto-configuration only | Default bean exists |
| Custom bean of same type | Add user bean implementing the abstraction | Default backs off; custom bean is used |
| Multiple custom beans of same type | Register two implementations | Default still does not appear; do not assume only one candidate |
| Property enabled | Set property to true | Auto-configuration and default bean are allowed to activate |
| Property disabled | Set property to false | Beans guarded by property condition do not appear |
| Property missing | Omit property | Outcome matches published matchIfMissing |
| Optional class present | Class is on classpath | Optional integration configuration is allowed to apply |
| Optional class absent | Filter class off classpath | Configuration depending on that class is not registered |
| Provider runs before fallback | Two auto-configurations with ordering relationship | Provider exists; fallback backs off |
| Discovery from JAR | Load via EnableAutoConfiguration | Boot finds the class in the imports resource |
| Different Boot versions | Run the same contract suite across baselines | Public behavior does not change |

Not every starter needs every case. Choose the rows matching the annotations, properties, optional dependencies, context types, and versions your starter actually publishes. Do not add tests for capabilities the library does not support.

## 3. Choose the right testing tools

`ApplicationContextRunner` is the right tool for most auto-configuration tests. Each test builds a small context with a defined combination of auto-configuration, user configuration, Environment, and classpath. A callback receives the created context for assertions; the runner closes the context after the callback.

A base runner is commonly declared as a field:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                PaymentGatewayAutoConfiguration.class));
~~~

Runner fluent methods let each test add its own conditions:

| API | Used to test |
| --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Load one or more auto-configurations |
| `withUserConfiguration(...)` | Simulate application-declared configuration |
| `withBean(...)` | Register test beans directly |
| `withPropertyValues(...)` | Customize Environment for a test case |
| `withClassLoader(...)` | Simulate classes or packages missing from the classpath |
| `withInitializer(...)` | Add initializers, such as a condition report listener |
| `run(...)` | Start context, run assertions in callback, then close context |

The runner creates a fresh context for each `run`. You can share a base runner field to avoid repeating baseline configuration; each test should still clearly express its own setup and assertions.

Use `WebApplicationContextRunner` if the configuration applies only to Servlet web contexts, or `ReactiveWebApplicationContextRunner` if it applies only to Reactive web contexts. `ApplicationContextRunner` is non-web by default. These runners are JVM testing tools; they do not execute inside native image tests. [Testing auto-configuration guide](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).

## 4. Write contract tests for defaults and custom overrides

The following example is a small starter. Tests verify behavior through the public interface without depending on internal implementation details beyond what the starter promises.

### 4.1. Contract and implementation

**`src/main/java/com/acme/payment/PaymentGateway.java`**

~~~java
package com.acme.payment;

public interface PaymentGateway {
    String provider();
}
~~~

**`src/main/java/com/acme/payment/DefaultPaymentGateway.java`**

~~~java
package com.acme.payment;

public final class DefaultPaymentGateway implements PaymentGateway {

    @Override
    public String provider() {
        return "default";
    }
}
~~~

**`src/main/java/com/acme/payment/autoconfigure/PaymentGatewayAutoConfiguration.java`**

~~~java
package com.acme.payment.autoconfigure;

import com.acme.payment.DefaultPaymentGateway;
import com.acme.payment.PaymentGateway;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.payment",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class PaymentGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    DefaultPaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

In this example, a missing property or true allows auto-configuration to run; false disables it. The bean method checks the PaymentGateway abstraction, while its return type exposes the concrete default implementation to provide clear type metadata.

### 4.2. Test defaults, overrides, and properties

**`src/test/java/com/acme/payment/autoconfigure/PaymentGatewayAutoConfigurationTests.java`**

~~~java
package com.acme.payment.autoconfigure;

import com.acme.payment.PaymentGateway;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentGatewayAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    PaymentGatewayAutoConfiguration.class));

    @Test
    void suppliesDefaultWhenNoUserGatewayExists() {
        contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(PaymentGateway.class);
            assertThat(context).hasBean("paymentGateway");

            assertThat(context.getBean(PaymentGateway.class).provider())
                    .isEqualTo("default");
        });
    }

    @Test
    void backsOffAndKeepsUserGateway() {
        contextRunner.withUserConfiguration(UserGatewayConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(PaymentGateway.class);
                    assertThat(context).hasBean("customPaymentGateway");
                    assertThat(context).doesNotHaveBean("paymentGateway");

                    assertThat(context.getBean(PaymentGateway.class).provider())
                            .isEqualTo("custom");
                });
    }

    @Test
    void disablesGatewayWhenPropertyIsFalse() {
        contextRunner.withPropertyValues("acme.payment.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(PaymentGateway.class);
                });
    }

    @Test
    void explicitlyEnabledPropertyStillSuppliesDefault() {
        contextRunner.withPropertyValues("acme.payment.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(PaymentGateway.class);
                    assertThat(context.getBean(PaymentGateway.class).provider())
                            .isEqualTo("default");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGatewayConfiguration {

        @Bean
        CustomPaymentGateway customPaymentGateway() {
            return new CustomPaymentGateway();
        }
    }

    static final class CustomPaymentGateway implements PaymentGateway {

        @Override
        public String provider() {
            return "custom";
        }
    }
}
~~~

These tests protect four parts of the contract: the default appears when there is no override, the default backs off for a user bean, property false disables the feature, and property true enables it.

If the bean name paymentGateway is not an API committed by the starter, you can omit the name assertion and check only type/behavior. If the starter's docs publish the bean name so users can inject by qualifier or name, keep that assertion because renaming during refactoring would be a breaking change.

### 4.3. Test multiple custom beans

`@ConditionalOnMissingBean` does not mean "create default only when exactly one implementation exists". It checks only for the absence of a matching bean. When two implementations exist, the default must still back off.

You can add a test:

~~~java
@Test
void doesNotAddDefaultWhenMultipleUserGatewaysExist() {
    contextRunner.withUserConfiguration(MultipleGatewayConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBeansOfType(PaymentGateway.class))
                        .hasSize(2);
                assertThat(context).doesNotHaveBean("paymentGateway");
            });
}
~~~

`MultipleGatewayConfiguration` declares two distinct beans implementing PaymentGateway. This test prevents accidental changes from a missing-bean condition to logic that checks bean count or Primary only.

## 5. Protect ordering between providers and fallbacks

If a default bean depends on a bean supplied by another auto-configuration, tests must protect bean definition processing order.

Provider:

~~~java
@AutoConfiguration
public class PrimaryTransportAutoConfiguration {

    @Bean
    PrimaryTransport primaryTransport() {
        return new PrimaryTransport();
    }
}
~~~

Fallback:

~~~java
@AutoConfiguration(after = PrimaryTransportAutoConfiguration.class)
public class FallbackTransportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Transport.class)
    FallbackTransport fallbackTransport() {
        return new FallbackTransport();
    }
}
~~~

Test:

~~~java
@Test
void fallbackBacksOffWhenPrimaryProviderIsConfigured() {
    new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    FallbackTransportAutoConfiguration.class,
                    PrimaryTransportAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(Transport.class);
                assertThat(context).hasBean("primaryTransport");
                assertThat(context).doesNotHaveBean("fallbackTransport");
            });
}
~~~

Both PrimaryTransport and FallbackTransport in the example implement Transport. The `after` ordering controls when bean definitions are registered; it does not control when instances are instantiated. Bean creation dependencies remain governed by the dependency graph and `@DependsOn`.

`AutoConfigurations.of` applies ordering using the same rules as a running application. Therefore, tests should pass the required auto-configurations into the runner and assert the final outcome rather than relying on class listing order in the test. [Ordering and bean conditions documentation](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).

## 6. Test optional dependencies and classpath

Starters often integrate with optional libraries. If the dependency is absent, the corresponding auto-configuration must be skipped without breaking context creation.

Spring Boot provides `FilteredClassLoader` to simulate missing classes or packages:

~~~java
contextRunner
        .withClassLoader(new FilteredClassLoader(OptionalClient.class))
        .withConfiguration(
                AutoConfigurations.of(OptionalClientAutoConfiguration.class))
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean("optionalClient");
        });
~~~

For configurations whose method signatures reference optional classes, isolate those beans inside a nested configuration guarded by `@ConditionalOnClass`. If the optional class is missing, Spring can skip the nested configuration before processing methods needing that class. Do not place an optional dependency's return type directly on a method that the JVM must load before class conditions are evaluated.

Regression tests for optional integrations should cover both branches:

- Class present: the integration bean is registered if other conditions are satisfied.
- Class absent: the context still starts and the integration bean does not appear.

Do not check only `doesNotHaveBean`; verify the context did not fail with `NoClassDefFoundError` or `ClassNotFoundException`.

## 7. Test discovery from the packaged artifact

A test loading a class directly via `AutoConfigurations.of(...)` verifies the class's behavior, but does not verify whether Boot finds the class from the registration file inside the JAR.

For Boot 2.7+/3.x, auto-configuration must be listed in:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example:

~~~text
com.acme.payment.autoconfigure.PaymentGatewayAutoConfiguration
~~~

To test discovery, create a test fixture using `@EnableAutoConfiguration`:

~~~java
@SpringBootConfiguration(proxyBeanMethods = false)
@EnableAutoConfiguration
static class DiscoveryApplication {
}
~~~

Run the test against the module's real classpath:

~~~java
@Test
void discoversAutoConfigurationFromImportsResource() {
    new ApplicationContextRunner()
            .withUserConfiguration(DiscoveryApplication.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(PaymentGateway.class);
            });
~~~

This test must run in a module that has the real registration resource on the classpath. Do not add `AutoConfigurations.of(PaymentGatewayAutoConfiguration.class)` to the discovery test, because doing so loads the class directly and stops testing the imports file.

After building the artifact, inspect the actual resource in the JAR:

~~~bash
mvn -B -DskipTests package
jar tf target/acme-payment-autoconfigure-1.0.0.jar
~~~

Confirm the imports file is inside the artifact and contains all exact FQCNs. If using Maven Shade or Gradle Shadow to build an uber-JAR, verify identically named resources are merged properly instead of one dependency overwriting another's contents.

## 8. Inspect the Condition Evaluation Report when regression tests fail

When a test reports a missing default bean, the Condition Evaluation Report identifies which condition failed to match and why.

You can enable the listener in tests:

~~~java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))
        .withConfiguration(
                AutoConfigurations.of(PaymentGatewayAutoConfiguration.class))
        .run(context -> {
            // Assertions.
        });
~~~

Details to inspect:

- The auto-configuration class and bean method being evaluated.
- The type, name, or annotation the condition is searching for.
- Existing beans causing `@ConditionalOnMissingBean` not to match.
- Which property or classpath condition is excluding the configuration.
- Whether ordering prevented a provider definition from being processed yet.

You can use `--debug` when running the application to print the condition report. If Actuator is used and the endpoint is exposed/permitted, `/actuator/conditions` provides positive and negative matches. Expose endpoints only per the application's security policy; never open diagnostic endpoints broadly just for test convenience.

## 9. Distinguish regression test layers

Not every auto-configuration bug should be tested with the same kind of test.

| Test layer | Scope | Appropriate tool |
| --- | --- | --- |
| Contract test | Defaults, overrides, properties, types/names, bean count | `ApplicationContextRunner` |
| Condition test | Classpath, resources, profiles, web conditions | Runner + `FilteredClassLoader` |
| Ordering test | Provider and fallback auto-configurations | `AutoConfigurations.of(...)` |
| Discovery test | Imports file, classpath, and auto-configuration registration | `@EnableAutoConfiguration` on artifact |
| Web context test | Servlet or Reactive conditions | `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner` |
| Compatibility test | Supported Boot/JDK versions | CI version matrix |
| Integration test | Real communication with external systems | Testcontainers or dedicated integration environment |

Keep contract tests fast and independent. Use real databases, brokers, or HTTP servers in integration tests only when that behavior is genuinely part of the contract being protected. A bean back-off test should never depend on an external network service.

## 10. Protect compatibility across Spring Boot versions

A library must clearly publish the Boot versions it supports. CI can only protect contracts if it runs against the baselines actually committed to.

For example, a library supporting Boot 2.7 and Boot 3.3 can run the same contract test suite on these two lines:

| Runtime | Test JDK | Goal |
| --- | --- | --- |
| Spring Boot 2.7.18 | 17 | Maintain compatibility with the 2.7 baseline |
| Spring Boot 3.3.13 | 17 | Protect behavior on the Boot 3 line |

Boot 2.7 already has `@AutoConfiguration` and `AutoConfiguration.imports`, so a source set using those APIs can be tested on both lines. If the library also supports Boot 2.6 or earlier, the `@AutoConfiguration` API did not exist in that baseline; you must maintain separate compatible source/artifacts, such as `@Configuration` and `spring.factories` registration, and run the corresponding contract suite. Do not include an uncompilable baseline in the same matrix simply by swapping dependency versions.

### 10.1. Use a Maven property to select the Boot BOM

A POM can declare the Boot version via a property:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-boot.version>3.3.13</spring-boot.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

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
~~~

`spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and required test utilities. In real projects, compiler and Surefire plugins must be managed via an appropriate parent or plugin management.

You can manually run the same suite against each baseline:

~~~bash
mvn -B -Dspring-boot.version=2.7.18 verify
mvn -B -Dspring-boot.version=3.3.13 verify
~~~

### 10.2. CI matrix example

A minimal GitHub Actions workflow:

~~~yaml
name: Auto-configuration compatibility

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        boot-version: ['2.7.18', '3.3.13']
        java-version: ['17']

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java-version }}
          cache: maven

      - name: Run regression suite
        run: mvn -B -Dspring-boot.version=${{ matrix.boot-version }} verify
~~~

In a real workflow, the two placeholders above correspond to GitHub Actions expressions for matrix.java-version and matrix.boot-version. When adding a supported Boot baseline, add it to the matrix and ensure corresponding dependencies/plugins are actually compatible.

Do not run tests only on the latest version. A dependency change can accidentally drop support for an older baseline while still compiling and passing on the newest version.

## 11. Test what belongs to the public contract

Useful regression tests protect behavior observable by starter users. Common contracts:

- **Bean type:** the application can inject the published abstraction.
- **Back-off:** a user bean of the same type prevents the default from being registered.
- **Bean name:** check only if the starter documents the name or qualifier.
- **Property keys:** prefix, property name, default value, havingValue, and matchIfMissing.
- **Optional dependencies:** missing libraries do not break the context.
- **Ordering:** provider/fallback are processed in the right order.
- **Registration:** imports resource exists in the artifact and discovery works.
- **Supported versions:** all committed baselines run the same contract suite.

Avoid locking tests to internal non-API details. For example, if the contract promises only a PaymentGateway, not every test needs to insist the exact class is DefaultPaymentGateway. When implementation changes without altering the contract, tests should not fail over a valid refactor.

Conversely, if a bean name or qualifier is published in documentation and users rely on it, test it as part of the API.

## 12. Mistakes that leave a regression suite unable to protect a starter

| Weak testing practice | Why bugs slip through | How to improve |
| --- | --- | --- |
| Checking only that context starts successfully | Unknown whether default exists or backs off properly | Assert bean type, count, and custom implementation |
| Testing only without custom beans | Fails to protect the back-off contract | Add user configuration with a bean of the same abstraction |
| Asserting only bean name | Bean may exist with wrong type or behavior | Assert public type and behavior |
| Loading classes only via `AutoConfigurations.of` | Misses a missing imports resource | Add discovery test via `@EnableAutoConfiguration` |
| Testing only the newest Boot version | Older baselines can suffer breaking changes | Run a version matrix per support policy |
| Using one large `@SpringBootTest` for everything | Slow tests and hard to pinpoint failing conditions | Use `ApplicationContextRunner` for small combinations |
| Skipping missing-property tests | matchIfMissing can be changed by accident | Test missing, true, and false |
| Not simulating missing classpath | Optional integrations can crash contexts | Use `FilteredClassLoader` |
| Not testing ordering | Fallback can register before provider | Add both auto-configurations to runner and assert outcome |
| Tests depend on real databases/brokers | Environment errors mask condition bugs | Keep contract tests local; separate integration tests |

## 13. Workflow for updating the regression suite when changing a starter

When modifying auto-configuration, follow this workflow:

1. Identify impacted contracts: bean type/name, properties, classpath, ordering, or registration.
2. Locate existing tests protecting those contracts.
3. If behavior changes intentionally, update contract docs before updating assertions.
4. Add reproducing tests before or alongside implementation changes.
5. Run the relevant test classes for fast feedback.
6. Run the full contract suite and discovery tests.
7. Run the CI matrix across all supported baselines.
8. Inspect the packaged JAR and imports resource if packaging changed.
9. Review the diff to ensure no older baseline tests were accidentally dropped.

A change is compatible when all published contracts still hold. If a change breaks user overrides, changes default properties, or drops a committed baseline, treat it as a breaking change and announce it clearly in release notes.

## 14. Pre-release checklist

- [ ] Test default bean when no custom bean exists.
- [ ] Test user bean of the same type causing default back-off.
- [ ] Test multiple user beans if the starter allows multiple implementations.
- [ ] Test missing, enabled, and disabled property states.
- [ ] Test optional dependencies present and absent.
- [ ] Test provider/fallback ordering.
- [ ] Test bean type and bean name when they are public contracts.
- [ ] Test discovery via EnableAutoConfiguration on the artifact.
- [ ] Verify imports resource inside the JAR after package/shade/shadow.
- [ ] Run contract suite on every supported Boot version.
- [ ] Check the corresponding JDK baseline.
- [ ] Keep contract tests independent of external systems.
- [ ] Inspect the Condition Evaluation Report on unexpected test no-matches.
- [ ] Update documentation and release notes when contracts change.

## 15. Self-check questions

1. Why is testing only that the default bean appears not enough?  
   **Answer:** Because that test does not prove the starter backs off when the application provides its own implementation.

2. Which test proves the back-off contract?  
   **Answer:** Build a context with a user bean of the same type, verify the user bean is used, and confirm the default bean is not registered.

3. Why should ApplicationContextRunner be used?  
   **Answer:** It creates a lightweight context where user configuration, properties, and classpath can be controlled per case, keeping condition tests fast and isolated.

4. Does AutoConfigurations.of verify the imports file?  
   **Answer:** No. It loads classes directly; a discovery test via EnableAutoConfiguration is required to verify the registration resource.

5. When should FilteredClassLoader be used?  
   **Answer:** When simulating optional classes or packages absent from the classpath.

6. Why must missing properties be tested?  
   **Answer:** Because matchIfMissing and default property values are part of the contract; changing them can flip feature activation.

7. Why test against the oldest supported Boot baseline?  
   **Answer:** Because APIs, registration, and behavior can change across release lines; testing only on the newest version does not protect promised compatibility.

8. Should internal implementation classes be asserted in every test?  
   **Answer:** No. Prefer public types and behavior; assert concrete implementations only when that is a documented contract.

9. If a provider is created by another auto-configuration, what must be tested?  
   **Answer:** Ordering of the two auto-configurations and fallback back-off after the provider definition is processed.

10. Does the regression suite replace integration tests with external systems?  
    **Answer:** No. Contract tests verify conditions and bean registration; integration tests are still needed for real communication with databases, brokers, or external services.

## Official documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): ordering, bean conditions, ApplicationContextRunner, condition report, web runners, and FilteredClassLoader.
- [Spring Boot 3.3.13 — ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): type/name/annotation criteria, default return type, search strategy, and ignored types.
- [Spring Boot 3.3.13 — AutoConfigurations API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurations.html): utility for loading and ordering auto-configurations in tests.
- [Spring Boot 3.3.13 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): runner for non-web test contexts.
- [Spring Boot 3.3.13 — Conditions Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): positive/negative condition match results.
- [Spring Boot 2.7 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes): `@AutoConfiguration` milestone and new resource registration in 2.7.

**Takeaway:** A regression suite must prove both sides of the contract: the default appears when no override exists, and backs off when a user bean is present. Then expand tests to cover properties, classpath, ordering, discovery, and every supported Boot version. When these contracts run automatically in CI, internal refactoring can proceed while starter users continue receiving the published behavior.
