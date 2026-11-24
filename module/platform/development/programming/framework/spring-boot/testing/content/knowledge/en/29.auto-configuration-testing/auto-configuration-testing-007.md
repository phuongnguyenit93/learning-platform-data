# Checking Bean Type, Bean Count, and Configuration Properties

## Objectives

In the **Auto-Configuration Testing** group of **Spring Boot - testing**, a test should not merely confirm that `ApplicationContext` starts. It must answer precisely: **what type is the bean, how many beans exist for an interface, did auto-configuration create the default bean under the right conditions, can users override it, and were configuration properties bound, validated, and passed into the actual bean?** A context can still start while accidentally creating two email clients, a `DataSource` with the wrong endpoint, or a service using a default limit instead of the value configured by the operator.

This lesson uses **Java 17, Spring Boot 3.4.5, Spring Framework 6.2, JUnit Jupiter, AssertJ, and Bean Validation**. The complete example builds **`AlertAutoConfiguration`** for `AlertSender`. When the feature is enabled and the application has not supplied its own sender, Spring Boot creates `ConsoleAlertSender`; when the feature is disabled, there is no default sender; when the user already supplied one or two senders, the default bean must **back off**. Config **`acme.alert`** includes `enabled`, `prefix`, and `max-message-length` with defaults/overrides and validation. Fast checks use **`ApplicationContextRunner`**, while Boot discovery checks use **`@SpringBootTest`**.

**Scope of evidence:** `ApplicationContextRunner` verifies the behavior of an explicitly imported auto-configuration. It **does not prove** Spring Boot discovered the auto-configuration from the **`AutoConfiguration.imports`** resource. Therefore, a separate discovery test is needed. Expected outcomes are derived from the source code; **no claim is made of having actually executed Gradle**.

## 1. Three distinct contracts

### Bean type: contract, implementation, and proxy

- **Contract type**: the interface or superclass consumers ask to inject, e.g., **`AlertSender`**.
- **Concrete type**: the default implementation, e.g., **`ConsoleAlertSender`**, which can be asserted when it is part of the starter's contract.
- **Bean name**: a name like **`consoleAlertSender`**, useful to distinguish default beans from user beans; avoid asserting names when they are mere internal details subject to refactoring.
- **Runtime class**: if a bean is AOP-proxied, runtime `getClass()` may be a JDK proxy/CGLIB subclass, unlike the implementation class. Assert the **assignable contract** and behavior rather than arbitrary exact `getClass()`.
- **Definition type**: the type Spring knows from `@Bean` return type, `BeanDefinition`, or factory metadata; it may not know the implementation subtype prior to instantiation.

When the feature is enabled, verify **there is one `AlertSender`**, **the bean is actually `ConsoleAlertSender`** in a non-proxied context, and **the `send` method uses the right properties**. All three together provide stronger evidence than `assertNotNull`.

### Bean count: 0, 1, or 2?

| Scenario | Expected AlertSender count | Meaning |
| --- | --- | --- |
| enabled=false, no user sender | 0 | Default feature is not registered |
| enabled=true, no user sender | 1 | One ConsoleAlertSender |
| enabled not declared, no user sender | 1 | matchIfMissing=true provides default |
| User supplies customSender | 1 | `@ConditionalOnMissingBean` makes default back off |
| User supplies two senders | 2 | Two user beans exist, no default |
| enabled=false yet user defines sender | 1 | Default bean's condition does not delete user beans |

**`getBean(AlertSender.class)`** is insufficient to prove only one bean exists: with **`@Primary`**, Spring can pick one bean even when two candidates exist. Use **`getBeanNamesForType(AlertSender.class).length`** or **`getBeansOfType(AlertSender.class).size()`** when the contract requires a count. If two beans lack `@Primary`/`@Qualifier`, `getBean(type)` throws **`NoUniqueBeanDefinitionException`**.

### Configuration properties

Check all of the following simultaneously:
1. **Default** when no property is provided.
2. **Override** from `Environment` via `withPropertyValues`.
3. Values on the **`@ConfigurationProperties`** bean.
4. Values passed into the **actual implementation**, not merely present in `Environment`.
5. **`@ConditionalOnProperty`** match/no-match.
6. Whether invalid configuration validation makes startup **fail intentionally**.
7. Whether a misspelled property key is caught by assertions on the actual bound value.

A property appearing in `application.yml` does not prove the client used it. If `AlertProperties.prefix` is `OPS` yet `ConsoleAlertSender` still uses `NOTICE`, config tests must fail.

## 2. Auto-configuration annotations and mechanisms

**`@AutoConfiguration`** marks a configuration considered by Spring Boot as an auto-configuration candidate, registered in **`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`** in Spring Boot 3.x.

**`@ConditionalOnClass`** requires a library/class on the classpath; **`@ConditionalOnProperty`** checks `Environment`; **`@ConditionalOnMissingBean`** creates a default bean when the user lacks a suitable bean; **`@ConditionalOnBean`** requires a dependency bean to be present; **`@ConditionalOnWebApplication`** depends on web application type; **`@EnableConfigurationProperties`** registers the target for type-safe binding; **`@ConfigurationProperties`** declares the prefix; **`@Validated`** enables Bean Validation on bound properties when a validation provider is present.

Conditions are evaluated while processing configuration/bean definitions, unlike `if/else` inside business services. When **`@ConditionalOnProperty(enabled=false)`** sits on a `@Bean` method, that method creates no bean; other beans in the auto-config class can still exist. When the condition sits on the `@AutoConfiguration` class itself, the entire class may be skipped. Never equate **0 `AlertSender`** with **0 `AlertProperties`**.

### Why does `@ConditionalOnMissingBean` matter?

A starter should defer to applications providing custom implementations. If auto-config always creates a default for the same interface, the application hits duplicate beans and injection errors, or silently picks the wrong bean via `@Primary`. In the standard flow, user-defined configurations are processed before auto-configurations so **`@ConditionalOnMissingBean`** sees the user's choice. Putting this condition in component-scanned `@Configuration` classes with uncontrolled order can behave differently.

**Proper test scenario:** application has an `AlertSender` bean named `customSender`; auto-config must not create `consoleAlertSender`; count stays one. If the application has two user senders, auto-config also adds no default; a count of two reflects user configuration, not an auto-config bug.

## 3. ApplicationContextRunner isolates each condition combination

Spring Boot provides **`org.springframework.boot.test.context.runner.ApplicationContextRunner`**. It builds an isolated context per callback, evaluates conditions for the property/user-configuration combination you specify, and closes the context after the callback. No full `@SpringBootTest`, web server, database, or network is needed.

~~~java
private final ApplicationContextRunner runner =
    new ApplicationContextRunner()
        .withConfiguration(
            AutoConfigurations.of(AlertAutoConfiguration.class));

@Test
void disabledFeatureHasNoSender() {
    runner.withPropertyValues("acme.alert.enabled=false")
        .run(context -> {
            assertNull(context.getStartupFailure());
            assertEquals(0, context
                .getBeanNamesForType(AlertSender.class).length);
        });
}
~~~

**`withConfiguration(AutoConfigurations.of(...))`** loads one or several auto-configuration classes; **`withUserConfiguration(...)`** injects user beans in the proper order; **`withPropertyValues(...)`** supplies a test `Environment`; **`run(...)`** yields an `AssertableApplicationContext` to assert types/counts/values.

**Never test multiple cases by mutating properties on an already-refreshed context** expecting conditions to re-evaluate. Each combination must use a **fresh context**. Avoid JVM-wide `System.setProperty` when runner properties suffice; static/global mutations easily interfere with parallel tests.

Spring Boot documentation notes **`ApplicationContextRunner` cannot be used when the test itself runs inside a native image**. When native/AOT compatibility is required, add a native-specific test strategy.

## 4. Runnable project with Spring Boot 3.4.5

### File tree

~~~text
settings.gradle
build.gradle
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
src/main/java/com/example/alertlib/AlertSender.java
src/main/java/com/example/alertlib/ConsoleAlertSender.java
src/main/java/com/example/alertlib/AlertProperties.java
src/main/java/com/example/alertlib/AlertAutoConfiguration.java
src/main/java/com/example/alertdemo/AlertDemoApplication.java
src/test/java/com/example/alertlib/AlertAutoConfigurationTest.java
src/test/java/com/example/alertdemo/AutoConfigurationDiscoveryTest.java
~~~

The application resides in **`com.example.alertdemo`**, while auto-config resides in sibling package **`com.example.alertlib`**. This helps prove auto-config must be discovered via the imports resource rather than accidentally component-scanned by `@SpringBootApplication`.

### settings.gradle

~~~groovy
rootProject.name = 'autoconfiguration-bean-contracts'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
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

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**`spring-boot-starter-validation`** supplies the Bean Validation provider so `@NotBlank`/`@Min`/`@Max` are enforced. **`spring-boot-configuration-processor`** generates IDE metadata; it **is not the Binder** and is not required for runtime binding. **`spring-boot-starter-test`** provides JUnit Jupiter, AssertJ, `ApplicationContextRunner`, and test utilities. Dependency management via the Spring Boot BOM prevents mixing incompatible versions.

### Contract interface: AlertSender.java

~~~java
package com.example.alertlib;

public interface AlertSender {
    String send(String recipient, String message);
}
~~~

**`AlertSender`** is the interface clients will inject. The example intentionally avoids network requests: `send` returns a deterministic string so behavior can be tested without an external email/SMS service. Production implementations must have their own delivery/error contracts.

### Default implementation: ConsoleAlertSender.java

~~~java
package com.example.alertlib;

import java.util.Objects;

public final class ConsoleAlertSender implements AlertSender {
    private final String prefix;
    private final int maxMessageLength;

    public ConsoleAlertSender(
            String prefix, int maxMessageLength) {
        this.prefix = Objects.requireNonNull(prefix);
        this.maxMessageLength = maxMessageLength;
    }

    public String getPrefix() {
        return prefix;
    }

    public int getMaxMessageLength() {
        return maxMessageLength;
    }

    @Override
    public String send(String recipient, String message) {
        Objects.requireNonNull(recipient, "recipient");
        Objects.requireNonNull(message, "message");

        if (message.length() > maxMessageLength) {
            throw new IllegalArgumentException(
                "message too long");
        }
        return prefix + ":" + recipient + ":" + message;
    }
}
~~~

In default tests, message `hello` outputs **`NOTICE:anna:hello`**. With prefix `OPS` and `maxMessageLength=5`, **`OPS:bob:hello`** is valid, whereas `abcdef` (length 6) must throw `IllegalArgumentException`. Thus property values are asserted via both the properties bean and **implementation behavior**.

### Configuration with defaults + validation: AlertProperties.java

~~~java
package com.example.alertlib;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.alert")
public class AlertProperties {
    private boolean enabled = true;

    @NotBlank
    private String prefix = "NOTICE";

    @Min(1)
    @Max(500)
    private int maxMessageLength = 80;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }

    public int getMaxMessageLength() {
        return maxMessageLength;
    }

    public void setMaxMessageLength(int maxMessageLength) {
        this.maxMessageLength = maxMessageLength;
    }
}
~~~

**Defaults:** `enabled=true`, `prefix=NOTICE`, `maxMessageLength=80`.

**Overrides:** `acme.alert.enabled=false` or `acme.alert.prefix=OPS`, `acme.alert.max-message-length=5`.

**Invalid:** `acme.alert.max-message-length=0` fails `@Min(1)`; whitespace-only prefix fails `@NotBlank`; `enabled=not-a-boolean` cannot convert to boolean. Spring Boot Binder and Bean Validation must fail context startup.

**Relaxed binding:** `@ConfigurationProperties` understands valid naming variants such as kebab-case and camelCase, but does not fix random typos. In documentation and config files use canonical kebab-case, avoiding typos like **`max-message-lenght`** being ignored and silently falling back to default 80.

### Auto-config: AlertAutoConfiguration.java

~~~java
package com.example.alertlib;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(AlertProperties.class)
public class AlertAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AlertSender.class)
    @ConditionalOnProperty(
        prefix = "acme.alert",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
    ConsoleAlertSender consoleAlertSender(
            AlertProperties properties) {
        return new ConsoleAlertSender(
            properties.getPrefix(),
            properties.getMaxMessageLength());
    }
}
~~~

**Default conditions:** feature is enabled if `enabled=true` or the key is missing (`matchIfMissing=true`), **yet creates the sender only when no other `AlertSender` exists**. The `@Bean` method returns the **concrete type `ConsoleAlertSender`**, providing clear type metadata. Clients should still inject **`AlertSender`** rather than the implementation type.

**Subtlety:** `@EnableConfigurationProperties` sits on the auto-config class, while `@ConditionalOnProperty` sits on the `@Bean` method. Hence **`enabled=false`** still yields an **`AlertProperties` bean**, while creating **no default `AlertSender` bean**. Tests must count by specific type, not the entire `ApplicationContext`.

### Registration resource: AutoConfiguration.imports

Create **`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`** at the exact path:

~~~text
com.example.alertlib.AlertAutoConfiguration
~~~

Spring Boot 3.x finds auto-configuration candidates from the imports file. Each line is a fully-qualified class name. Do not use `spring.factories` to register `EnableAutoConfiguration` in the Spring Boot 2.x style. Do not annotate `ConsoleAlertSender` with `@Component` outside `@Bean`, otherwise unexpected duplicates/back-off failures can occur.

### Boot app: AlertDemoApplication.java

~~~java
package com.example.alertdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AlertDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AlertDemoApplication.class, args);
    }
}
~~~

Because the app is in `com.example.alertdemo` and auto-config is in `com.example.alertlib`, **component scanning does not directly find `AlertAutoConfiguration`**. The integration test in section 6 proves the imports resource is used by Spring Boot.

## 5. Complete auto-configuration test suite

**src/test/java/com/example/alertlib/AlertAutoConfigurationTest.java**

~~~java
package com.example.alertlib;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AlertAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(AlertAutoConfiguration.class));

    @Test
    void defaultHasExactlyOneSenderOfCorrectType() {
        runner.run(context -> {
            assertNull(context.getStartupFailure());

            assertEquals(1, context
                .getBeanNamesForType(AlertSender.class).length);
            assertEquals(1, context
                .getBeansOfType(AlertSender.class).size());
            assertEquals(1, context
                .getBeanNamesForType(
                    ConsoleAlertSender.class).length);
            assertTrue(context.containsBean("consoleAlertSender"));

            ConsoleAlertSender sender = assertInstanceOf(
                ConsoleAlertSender.class,
                context.getBean(AlertSender.class));

            assertEquals("NOTICE", sender.getPrefix());
            assertEquals(80, sender.getMaxMessageLength());
            assertEquals("NOTICE:anna:hello",
                sender.send("anna", "hello"));
        });
    }

    @Test
    void defaultConfigurationPropertiesAreBoundOnce() {
        runner.run(context -> {
            assertNull(context.getStartupFailure());
            assertEquals(1, context
                .getBeanNamesForType(AlertProperties.class).length);

            AlertProperties properties =
                context.getBean(AlertProperties.class);
            assertTrue(properties.isEnabled());
            assertEquals("NOTICE", properties.getPrefix());
            assertEquals(80, properties.getMaxMessageLength());
        });
    }

    @Test
    void disabledFeatureHasZeroSenderButRetainsProperties() {
        runner.withPropertyValues("acme.alert.enabled=false")
            .run(context -> {
                assertNull(context.getStartupFailure());
                assertEquals(0, context
                    .getBeanNamesForType(AlertSender.class).length);
                assertFalse(
                    context.containsBean("consoleAlertSender"));

                AlertProperties properties =
                    context.getBean(AlertProperties.class);
                assertFalse(properties.isEnabled());
                assertEquals("NOTICE", properties.getPrefix());
            });
    }

    @Test
    void explicitEnabledTrueCreatesDefaultSender() {
        runner.withPropertyValues("acme.alert.enabled=true")
            .run(context -> {
                assertNull(context.getStartupFailure());
                assertEquals(1, context
                    .getBeanNamesForType(AlertSender.class).length);
                assertInstanceOf(
                    ConsoleAlertSender.class,
                    context.getBean(AlertSender.class));
            });
    }

    @Test
    void overriddenPropertiesAffectRealImplementation() {
        runner.withPropertyValues(
            "acme.alert.prefix=OPS",
            "acme.alert.max-message-length=5")
            .run(context -> {
                assertNull(context.getStartupFailure());

                AlertProperties properties =
                    context.getBean(AlertProperties.class);
                assertEquals("OPS", properties.getPrefix());
                assertEquals(5, properties.getMaxMessageLength());

                ConsoleAlertSender sender =
                    context.getBean(ConsoleAlertSender.class);
                assertEquals("OPS", sender.getPrefix());
                assertEquals(5, sender.getMaxMessageLength());
                assertEquals("OPS:bob:hello",
                    sender.send("bob", "hello"));

                assertThrows(IllegalArgumentException.class,
                    () -> sender.send("bob", "abcdef"));
            });
    }

    @Test
    void userSenderMakesDefaultAutoConfigurationBackOff() {
        runner.withUserConfiguration(UserSenderConfig.class)
            .run(context -> {
                assertNull(context.getStartupFailure());

                assertEquals(1, context
                    .getBeanNamesForType(AlertSender.class).length);
                assertTrue(context.containsBean("customSender"));
                assertFalse(
                    context.containsBean("consoleAlertSender"));

                assertEquals("CUSTOM:anna:hello",
                    context.getBean(AlertSender.class)
                        .send("anna", "hello"));
                assertNotNull(
                    context.getBean(AlertProperties.class));
            });
    }

    @Test
    void disablingDefaultDoesNotRemoveUserBean() {
        runner.withUserConfiguration(UserSenderConfig.class)
            .withPropertyValues("acme.alert.enabled=false")
            .run(context -> {
                assertNull(context.getStartupFailure());

                assertEquals(1, context
                    .getBeanNamesForType(AlertSender.class).length);
                assertTrue(context.containsBean("customSender"));
                assertFalse(
                    context.containsBean("consoleAlertSender"));
            });
    }

    @Test
    void twoUserSendersStayTwoWithoutExtraDefault() {
        runner.withUserConfiguration(TwoSendersConfig.class)
            .run(context -> {
                assertNull(context.getStartupFailure());

                assertEquals(2, context
                    .getBeanNamesForType(AlertSender.class).length);
                assertEquals(2, context
                    .getBeansOfType(AlertSender.class).size());
                assertFalse(
                    context.containsBean("consoleAlertSender"));

                assertThrows(
                    NoUniqueBeanDefinitionException.class,
                    () -> context.getBean(AlertSender.class));
            });
    }

    @Test
    void numericConfigBelowMinimumFailsStartup() {
        runner.withPropertyValues(
            "acme.alert.max-message-length=0")
            .run(context -> {
                assertNotNull(context.getStartupFailure());
            });
    }

    @Test
    void blankPrefixFailsBeanValidation() {
        runner.withPropertyValues("acme.alert.prefix= ")
            .run(context -> {
                assertNotNull(context.getStartupFailure());
            });
    }

    @Test
    void invalidBooleanFailsConfigBinding() {
        runner.withPropertyValues(
            "acme.alert.enabled=not-a-boolean")
            .run(context -> {
                assertNotNull(context.getStartupFailure());
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserSenderConfig {
        @Bean
        AlertSender customSender() {
            return (recipient, message) ->
                "CUSTOM:" + recipient + ":" + message;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoSendersConfig {
        @Bean
        AlertSender alphaSender() {
            return (recipient, message) -> "ALPHA";
        }

        @Bean
        AlertSender betaSender() {
            return (recipient, message) -> "BETA";
        }
    }
}
~~~

### What the tests verify

**`defaultHasExactlyOneSenderOfCorrectType`:** count=1 by interface, count=1 by concrete type, default bean name exists, behavior uses `NOTICE`. Not merely asserting the context started.

**`defaultConfigurationPropertiesAreBoundOnce`:** proves the properties bean exists exactly once with defaults `enabled=true`, `prefix=NOTICE`, `maxMessageLength=80`.

**`disabledFeatureHasZeroSenderButRetainsProperties`:** `enabled=false` removes the default sender yet keeps the properties bean. This is very easy to assert wrongly when `@ConditionalOnProperty` is at method level.

**`explicitEnabledTrueCreatesDefaultSender`:** property `true` exhibits the same behavior as default enabled due to `matchIfMissing=true`.

**`overriddenPropertiesAffectRealImplementation`:** checks values bound in `AlertProperties` **and** passed into `ConsoleAlertSender`; sending an over-length string throws an exception. If a key has a typo, the test fails.

**`userSenderMakesDefaultAutoConfigurationBackOff`:** `@ConditionalOnMissingBean` works; `customSender` is kept, `consoleAlertSender` is absent, count stays 1.

**`disablingDefaultDoesNotRemoveUserBean`:** the `enabled` condition governs only the auto bean, without deleting user beans.

**`twoUserSendersStayTwoWithoutExtraDefault`:** when the user has two senders, auto-config still backs off. Unqualified lookup by interface throws `NoUniqueBeanDefinitionException`, avoiding assuming `getBean` picks randomly.

**Three invalid-config tests:** `max-message-length=0`, blank prefix, and invalid boolean cause context startup failures instead of silently using wrong values. Positive tests sit alongside to avoid false positives where "every configuration fails".

**Isolation:** each test method uses the shared `runner` with `withConfiguration` yet builds **a fresh context inside the `run` callback**. No System property mutations, no `@TestMethodOrder`, no leaked state from earlier methods.

### Improving startup-failure assertions

Merely calling `assertNotNull(context.getStartupFailure())` can PASS due to an unrelated error. In production code, when testing invalid properties, inspect the **cause chain** down to Bean Validation/`BindException` or the failing property name per the pinned Spring Boot version; avoid asserting verbatim full stack traces or log messages that vary easily.

For all other tests, asserting `assertNull(context.getStartupFailure())` before type/count verifies the context did not fail for an unexpected reason.

## 6. Independent Spring Boot discovery test

`ApplicationContextRunner` specified **`AlertAutoConfiguration.class`** directly. If you accidentally delete the **`AutoConfiguration.imports`** resource, the 11 runner tests can still PASS. To prove Boot discovers the class automatically when running an app, add this test:

**src/test/java/com/example/alertdemo/AutoConfigurationDiscoveryTest.java**

~~~java
package com.example.alertdemo;

import com.example.alertlib.AlertSender;
import com.example.alertlib.ConsoleAlertSender;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

@SpringBootTest(
    classes = AlertDemoApplication.class,
    properties = {
        "acme.alert.enabled=true",
        "acme.alert.prefix=DISCOVERED"
    })
class AutoConfigurationDiscoveryTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void importsFileRegistersAlertAutoConfiguration() {
        assertEquals(1, context
            .getBeanNamesForType(AlertSender.class).length);

        ConsoleAlertSender sender =
            assertInstanceOf(
                ConsoleAlertSender.class,
                context.getBean(AlertSender.class));

        assertEquals("DISCOVERED", sender.getPrefix());
        assertEquals("DISCOVERED:client:ok",
            sender.send("client", "ok"));
    }
}
~~~

If the auto-configuration class is not in the imports file and not scanned by the app package, **there is no `AlertSender`**; the test fails. **Do not fix this test with `@Import(AlertAutoConfiguration.class)`**, as that bypasses the discovery mechanism again.

**`@SpringBootTest` does not automatically need an HTTP server:** the project has only the core starter, without `starter-web`. It still creates a full application context and auto-configurations; slower than `ApplicationContextRunner`, yet supplies the required integration proof.

## 7. Bean types: `getBean()`, `getBeansOfType()`, and bean definitions

| Question | Tool | Thing to watch |
| --- | --- | --- |
| Is there exactly one bean for interface? | getBeanNamesForType(T).length | Counts candidate names by type |
| How many instances of type? | getBeansOfType(T).size() | Can instantiate/affect lazy FactoryBeans |
| Can consumer inject type? | getBean(T.class) | `@Primary` can mask multiple beans |
| Does default bean name exist? | containsBean("consoleAlertSender") | Naming is a contract when needed |
| Is concrete implementation right? | assertInstanceOf(ConsoleAlertSender.class, bean) | Proxies can alter runtime class |
| Does properties bean exist? | getBean(AlertProperties.class) | No need to assert generated bean name |
| Total definitions? | getBeanDefinitionCount() | Not the AlertSender count |
| Are there 2 user beans? | getBeansOfType(AlertSender.class) | Auto-config must not add a default |
| Context startup error? | getStartupFailure() | Do not count beans amid startup failure |

### `getBeanNamesForType` vs `getBeansOfType`

**`getBeanNamesForType`** typically uses metadata to return names matching a type, avoiding instantiation in many cases. **`getBeansOfType`** returns a map of **name -> bean instance** and can trigger creation of singletons/factories. With lazy beans, `FactoryBean`s, or proxies, type query semantics depend on metadata and initialization timing; test **bean contracts after the context starts**, rather than guessing from class files.

**`@Bean` return type matters:** if a method declares return type `AlertSender` yet creates `ConsoleAlertSender` at runtime, metadata does not always know the concrete implementation before instantiation. In the example, `@Bean` returns **`ConsoleAlertSender`** so Spring has clear concrete return-type metadata.

### `@Primary` and `@Qualifier` do not reduce bean count

`@Primary` chooses a default injection candidate, yet **two bean definitions still exist**. `@Qualifier` helps inject the matching named/qualified bean, yet also removes no other bean. If the contract requires exactly one bean, assert **count**, not merely that `getBean(type)` works.

### Singleton, prototype, and parent contexts

A singleton bean definition typically has one instance in the context. A prototype bean definition can create many instances across `getBean` calls, yet `getBeanNamesForType` count remains **the number of definitions**, not instances ever created. With parent/child contexts, local bean lists can differ from lists including ancestor beans; when testing hierarchies, use APIs with appropriate `SearchStrategy`/`BeanFactoryUtils`. Never assert a global count without knowing scope.

## 8. `@ConditionalOnProperty` and `ConfigProperties`: exact scope

In the project:

~~~java
@ConditionalOnProperty(
    prefix = "acme.alert",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
~~~

| Value | Default sender | AlertProperties |
| --- | --- | --- |
| Not declared | Present, if no other AlertSender | enabled=true |
| true | Present, if no other AlertSender | enabled=true |
| false | Absent | enabled=false |
| not-a-boolean | Condition disallows default; Binder fails | Startup failure |
| customSender present, enabled=true | Absent (back-off) | Present |
| customSender present, enabled=false | Absent | Present |

**Conditions are not validators.** They only govern registration when properties match. Binder and Bean Validation check types and `@ConfigurationProperties` constraints. In this design, the properties bean is registered by `@EnableConfigurationProperties` **at class level**, so it still binds when the sender is disabled; if `@ConditionalOnProperty` were placed at class level too, the properties bean could also be excluded.

When adding nested properties, use **`@Valid`** to cascade Bean Validation. For enums/`Duration`/`DataSize`, test conversion and invalid values. Even with relaxed binding, canonical kebab-case in config docs remains recommended.

### Which configuration source wins?

`ApplicationContextRunner.withPropertyValues` appends test `Environment` values. A full Spring Boot application also has default config, profile-specific config, environment variables, command-line properties, `@TestPropertySource`, and test annotation properties following defined precedence. A runner test does not necessarily prove a production profile picks up the right source; when precedence/profiles are requirements, add **`@SpringBootTest(properties=...)`** or `ConfigDataApplicationContextInitializer`, and assert bound bean values under realistic conditions.

## 9. Classpath, web contexts, and auto-config ordering

Other conditions can also affect type/count. For example, **`@ConditionalOnClass(name="com.vendor.FastClient")`** when an optional dependency is absent must **not create the client bean**, without throwing `ClassNotFoundException`.

Spring Boot test's **`FilteredClassLoader`** can simulate an absent class:

~~~java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(OptionalClientAutoConfiguration.class))
    .withClassLoader(
        new FilteredClassLoader("com.vendor.FastClient"))
    .run(context -> {
        // Assert optional client bean is absent.
    });
~~~

This is an **excerpt**, outside the runnable tree; it requires a real `OptionalClientAutoConfiguration` class, `@ConditionalOnClass` annotation, and imports. For optional classes, avoid referencing the class directly in method signatures if it could be loaded before the condition applies; use separate configuration structures or name-based conditions appropriately.

**`@ConditionalOnWebApplication`**: testing a web auto-config inside a plain `ApplicationContextRunner` will not match because the context is not web. Choose **`WebApplicationContextRunner`** for servlet, **`ReactiveWebApplicationContextRunner`** for reactive. When `@ConditionalOnBean` spans multiple auto-configurations, **definition processing order** can affect conditions; use `@AutoConfiguration(before/after)` per real dependencies and test both with and without prerequisite beans.

## 10. `ConditionEvaluationReport` aids debugging

When no sender is created, it could be because the feature is disabled, a user bean already exists, an optional class is absent, the imports file is missing, or a property bound wrongly. Do not guess by deleting conditions. Spring Boot provides **`ConditionEvaluationReport`** to view positive/negative matches.

In a runner you can enable logging:

~~~java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(AlertAutoConfiguration.class))
    .withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(
            LogLevel.INFO))
    .withPropertyValues("acme.alert.enabled=false")
    .run(context -> {
        assertEquals(0, context
            .getBeanNamesForType(AlertSender.class).length);
    });
~~~

This is an **illustrative excerpt**, adding imports:
- `org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener`
- `org.springframework.boot.logging.LogLevel`
- `org.springframework.boot.test.context.runner.ApplicationContextRunner`
- `org.springframework.boot.autoconfigure.AutoConfigurations`
- JUnit Assertions and demo code.

**`ConditionEvaluationReport` does not replace assertions.** It explains why conditions matched or did not match; bean creation can still fail due to dependency resolution/binding/validation. When enabling debug or Actuator `conditions`/`configprops` in real environments, secure endpoints and avoid leaking secrets into public CI logs.

## 11. Common testing mistakes

| Anti-pattern | Risk | Fix |
| --- | --- | --- |
| Asserting only `context != null` | Unknown if bean types/counts are right | Assert specific types/counts/config |
| Only `getBean(T.class)` | `@Primary` can hide duplicate beans | `getBeanNamesForType(T).length` |
| Asserting total 17 bean definitions | Coupled to framework version | Count beans by contract |
| Testing only `enabled=true` | Misses disabled/default branches | Default/true/false tests |
| Not testing user overrides | Unexpected duplicate beans | `withUserConfiguration` and back-off |
| Mocking `AlertProperties` in binding tests | Hides property binder bugs | Use real `AlertProperties` bean |
| Checking property only in `Environment` | Does not prove implementation uses value | Assert sender behavior |
| Missing validation provider | `@Min`/`@NotBlank` silently inactive | `starter-validation` |
| Runner passes -> assuming imports file works | Class was imported directly | `@SpringBootTest` discovery |
| Putting auto-config in app scan package | Does not prove auto-config registration | Sibling package and imports |
| `@Component` on implementation + `@Bean` | Can create unexpected duplicates/back-off bugs | Register from a single source |
| Using `allow-bean-definition-overriding` to mask duplicates | Runtime picks bean unclearly | Proper `@ConditionalOnMissingBean` |
| Testing servlet condition in plain runner | Context type mismatch | `WebApplicationContextRunner` |
| Asserting concrete `getClass()` on proxied beans | Breaks easily under AOP | Contract type/behavior assertions |
| Wrong property name yet default stays green | Relaxed binding does not fix typos | Explicit overrides + assert values |
| Startup-failure test only checks non-null | Can pass due to unrelated error | Inspect root cause for strict QA |
| Using `@DirtiesContext` to fix duplicates | Slow without fixing conditions | Independent runner contexts |
| Mutating System properties across parallel tests | Global state leaks | `withPropertyValues` |
| Testing everything with `@SpringBootTest` | Heavy and hard to diagnose | Runner for conditions, full context for discovery |

## 12. Running Gradle and expected results

With a JDK 17-compatible Gradle Wrapper:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.alertlib.AlertAutoConfigurationTest
./gradlew test --tests com.example.alertdemo.AutoConfigurationDiscoveryTest
./gradlew test --tests com.example.alertlib.AlertAutoConfigurationTest.defaultHasExactlyOneSenderOfCorrectType
./gradlew test --tests com.example.alertlib.AlertAutoConfigurationTest.userSenderMakesDefaultAutoConfigurationBackOff
~~~

On Windows use **`gradlew.bat`**. If Gradle Wrapper files have not been generated yet, use an installed Gradle or run the `wrapper` task; do not pretend `./gradlew` exists before creating it. No `BUILD SUCCESSFUL` stdout was observed while authoring this lesson.

| Test | Expected |
| --- | --- |
| `defaultHasExactlyOneSenderOfCorrectType` | 1 AlertSender, 1 ConsoleAlertSender, output NOTICE |
| `defaultConfigurationPropertiesAreBoundOnce` | 1 AlertProperties, true/NOTICE/80 |
| `disabledFeatureHasZeroSenderButRetainsProperties` | 0 AlertSender, AlertProperties enabled=false |
| `explicitEnabledTrueCreatesDefaultSender` | 1 default sender |
| `overriddenPropertiesAffectRealImplementation` | OPS/5 and rejects length-6 message |
| `userSenderMakesDefaultAutoConfigurationBackOff` | 1 customSender, default absent |
| `disablingDefaultDoesNotRemoveUserBean` | 1 user sender |
| `twoUserSendersStayTwoWithoutExtraDefault` | 2 user beans, unqualified lookup ambiguous |
| `numericConfigBelowMinimumFailsStartup` | Startup failure via `@Min` |
| `blankPrefixFailsBeanValidation` | Startup failure via `@NotBlank` |
| `invalidBooleanFailsConfigBinding` | Startup failure via type conversion |
| `importsFileRegistersAlertAutoConfiguration` | `@SpringBootTest` finds imports, 1 sender with prefix DISCOVERED |

**Debugging when tests fail:**
- Default 0 beans: inspect `@ConditionalOnProperty`, `@EnableConfigurationProperties`, `AutoConfigurations.of`.
- User override has 2 beans: inspect `@ConditionalOnMissingBean` and user configuration timing.
- Property override has no effect: inspect keys, setters, nested binding, and factory method value passing.
- Invalid properties fail to fail: check `@Validated` and validation implementation.
- Runner PASSES yet discovery FAILS: inspect `META-INF/spring/...imports` path, package names, and component scanning.
- Full context has unexpected extra beans: inspect `@Primary`, `@Qualifier`, `@Component` scan, `@ConditionalOnBean`, and active profiles.

## 13. QA process applicable to a real starter

**Step 1 — List contract types**: `DataSource`, `HttpClient`, `MeterRegistry`, `AlertSender`, or any bean the module provides. Define the expected 0/1/N count.

**Step 2 — Define conditions**: classpath, properties, missing user beans, web environment, cloud platform. Build a minimal matrix so no branch is missed.

**Step 3 — Define configuration**: prefix, defaults, type conversion, validation, required/optional fields, nested objects; avoid ambiguous property keys.

**Step 4 — Write runner tests**: defaults, enabled/disabled, overrides, user beans, missing prerequisites, and startup failures. Count by contract type and test behavior.

**Step 5 — Add integration discovery test**: catch missing/misnamed FQN in `AutoConfiguration.imports` or accidental component scanning.

**Step 6 — Test across injection points**: if applications inject with `@Qualifier`, `@Primary`, `List<T>`, `Map<String,T>`, or parent-child contexts, simple count/type assertions may not suffice.

**Step 7 — Avoid brittle assertions**: never assert global `beanDefinitionCount` or full stack traces. Never ignore root causes of invalid configs.

**Step 8 — Test realistic classpaths/environments**: for optional vendor libraries, test `FilteredClassLoader`; for servlet/reactive conditions pick the right runner. For real datasources/message brokers, add Testcontainers/integration tests rather than calling runner tests end-to-end.

**Step 9 — Review regressions**: when changing `@Bean` return types, conditions, prefixes, Bean Validation, or imports resources, update tests based on the contract rather than merely tweaking expected counts to stay green.

### Checklist

- Did you check 0/1/2 beans by interface?
- Did you check appropriate implementation types without brittle dependence on exact proxy classes?
- Did you assert bean names only when they are part of the contract?
- Did you verify property defaults, overrides, and real usage in behavior?
- Did you verify invalid configs and startup failures for the exact root cause?
- Do you have `@ConditionalOnMissingBean` user-override tests?
- Do you understand `@Primary`/`@Qualifier` do not reduce bean counts?
- Did you separate the `@ConfigurationProperties` bean from the default feature bean when disabled?
- Did you use `ApplicationContextRunner` for conditions and `@SpringBootTest` for discovery?
- Is `AutoConfiguration.imports` at the right path with exact FQNs?
- Did you avoid component-scanning the auto-config class?
- Did you test optional classpaths/web contexts when features depend on them?
- Do you understand how singleton/prototype/`FactoryBean`/hierarchy differ?
- Did you use `ConditionEvaluationReport` to debug instead of deleting conditions?
- Did you avoid global property sources or static mutable state across tests?
- Did you distinguish startup checks from functional behavior and production integration?
- Did you state clearly that code is designed to be runnable without fabricating runtime output?

## 14. Self-check questions

**1.** Context has `AlertSender` via `getBean(type)` — is exactly-one proven? **Not yet**, `@Primary` can pick one of multiple beans.

**2.** Which API counts beans by interface? **`getBeanNamesForType(T).length`** or `getBeansOfType(T).size()`.

**3.** Does `enabled=false` in the demo still have `AlertProperties`? **Yes**, because `@EnableConfigurationProperties` is class-level and the condition sits only on the sender `@Bean`.

**4.** What if `enabled` is not declared? **Default sender is created if no user sender exists**, thanks to `matchIfMissing=true`.

**5.** User has `customSender` yet auto-config still creates `consoleAlertSender` — what is wrong? **Broken back-off**, causing duplicates.

**6.** Two `AlertSender` beans without primary — what does `getBean(AlertSender.class)` do? **`NoUniqueBeanDefinitionException`**.

**7.** Does `@Primary` reduce bean count? **No**; it only affects candidate selection.

**8.** Prefix set to `OPS`, yet test only reads `Environment` — enough? **No**, must read `AlertProperties` and verify `ConsoleAlertSender` actually uses `OPS`.

**9.** Does `@ConfigurationProperties` support relaxed binding? **Yes**, though it does not fix key typos.

**10.** Do `@Validated` + `@Min` need a validation provider? **Yes**; `starter-validation` is the common choice.

**11.** What is expected for `max-message-length=0`? **Startup failure**.

**12.** Does runner `AutoConfigurations.of` prove imports discovery? **No**, it specifies the class directly.

**13.** Which test proves imports? **`@SpringBootTest`** on an app that does not component-scan auto-config, counting loaded beans.

**14.** Is `@ConditionalOnWebApplication` tested well in plain `ApplicationContextRunner`? **No**, pick `WebApplicationContextRunner`.

**15.** What simulates an absent optional class? **`FilteredClassLoader`**.

**16.** Does `ConditionEvaluationReport` replace assertions? **No**, it is for diagnostics.

**17.** Does prototype bean definition count=1 mean only one instance across the JVM? **No**.

**18.** When `@Bean` return type is an interface, does Spring always know the concrete implementation before instantiation? **Not always**.

**19.** Why not assert total `beanDefinitionCount`? **Infrastructure definitions vary across versions and dependencies**.

**20.** Most important takeaway? **Auto-config must create the right count and type of beans, back off for user-defined beans, and bind/validate/apply properties according to contract.**

**Conclusion:** Testing Spring Boot auto-configuration is more than confirming the context starts; you must **count beans per contract, check types, check names when needed, verify conditional back-off, test binding defaults/overrides, validation, and behavior**. **`ApplicationContextRunner`** makes these combinations fast, isolated, and easy to debug. **`@SpringBootTest`** adds real discovery proof via **`AutoConfiguration.imports`**. With classpath/web conditions or multiple beans, adjust the context runner and assertions to match the contract rather than forcing everything to be a single bean.

## Official documentation

- Spring Boot 3.4 — Creating Your Own Auto-configuration and Testing Your Auto-configuration: https://docs.spring.io/spring-boot/3.4/reference/features/developing-auto-configuration.html
- Spring Boot 3.4 — Externalized Configuration and ConfigurationProperties Validation: https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — ConditionalOnMissingBean Javadoc: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.4 — ConditionalOnProperty Javadoc: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Framework 6.2 — BeanFactory/ApplicationContext: https://docs.spring.io/spring-framework/reference/6.2/core/beans/introduction.html