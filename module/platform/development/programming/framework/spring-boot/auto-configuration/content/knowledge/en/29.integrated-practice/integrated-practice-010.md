# Intentionally Creating Registration, Condition, and Bean Conflict Errors and Diagnosing by Evidence

## Lab Objectives

When a bean provided by Spring Boot auto-configuration does not appear or the ApplicationContext fails to start, tweaking annotations by guesswork usually makes the issue harder to understand. The reliable approach is creating a reproducible error, gathering evidence from Spring, identifying the failing stage, and fixing the exact root cause.

This lab intentionally creates three common categories of errors:

1. **Registration error:** an auto-configuration class is not discovered due to a missing or misspelled entry in `AutoConfiguration.imports`.
2. **Condition error:** the class is discovered, yet excluded because a property or classpath condition does not match.
3. **Bean conflict:** two beans share the same name when overriding is disabled, or multiple beans share the same type so dependency injection cannot pick a candidate.

We will use a small Acme library, Spring Boot 3.3, Java 17+, JUnit 5, and `ApplicationContextRunner`. Each error includes a reproduction method, observable symptoms, a fix, and a regression test.

After this lesson, you can:

- Distinguish an unregistered auto-configuration from a registered auto-configuration whose conditions did not match.
- Use `--debug`, the Condition Evaluation Report, and Actuator `/actuator/conditions` to gather evidence.
- Inspect bean names and bean types in the ApplicationContext.
- Distinguish `BeanDefinitionOverrideException`, `NoUniqueBeanDefinitionException`, and `NoSuchBeanDefinitionException`.
- Use `@ConditionalOnMissingBean` so default beans yield to application implementations.
- Use `@Primary` and `@Qualifier` to resolve multiple candidates of the same type.
- Write separate tests for discovery, property conditions, classpath conditions, and bean conflicts.
- Build an evidence-driven diagnostic workflow instead of changing multiple settings at once.

## 1. Investigation Workflow: Pinpointing Which Stage Failed

A missing bean can stem from several causes. Break the process down into stages:

~~~text
1. Candidate discovery
   Does AutoConfiguration.imports list the class?
             |
             v
2. Condition evaluation
   Do class/property/bean/web/resource conditions match?
             |
             v
3. Bean definition registration
   Is the bean name duplicated? Was the bean definition registered?
             |
             v
4. Dependency resolution
   Does the dependency have a matching bean? One or multiple candidates?
             |
             v
5. Bean creation
   Can the constructor/factory method instantiate the object?
~~~

Each stage leaves behind different types of evidence:

| Symptom | Stage to inspect first |
| --- | --- |
| No bean and auto-configuration does not appear in report | Candidate discovery or imports resource |
| Auto-configuration appears in report as a negative match | Condition evaluation |
| `BeanDefinitionOverrideException` error | Bean definition registration, usually duplicate bean name |
| `NoUniqueBeanDefinitionException` error | Dependency resolution, multiple beans of the same type |
| `NoSuchBeanDefinitionException` error | Required dependency not registered or excluded by condition |
| Bean definition exists yet instance creation fails | Constructor, factory method, dependencies, or lifecycle |

Do not start by adding `@Primary`, enabling bean overriding, or changing properties randomly. First identify which stage the failure belongs to.

## 2. Preparing a Minimal Acme Application

We create an API, properties class, default implementation, and auto-configuration. The example is kept simple to focus on bean registration.

### 2.1. Source structure

~~~text
acme-autoconfigure/
  build.gradle
  src/
    main/
      java/
        com/acme/api/AcmeClient.java
        com/acme/autoconfigure/AcmeClientProperties.java
        com/acme/autoconfigure/DefaultAcmeClient.java
        com/acme/autoconfigure/AcmeClientHealth.java
        com/acme/autoconfigure/AcmeClientAutoConfiguration.java
        com/acme/autoconfigure/AcmeCodecAdapter.java
        com/acme/autoconfigure/AcmeCodecAutoConfiguration.java
      resources/
        META-INF/spring/
          org.springframework.boot.autoconfigure.AutoConfiguration.imports
    test/
      java/
        com/acme/autoconfigure/AcmeAutoConfigurationTests.java
        com/acme/autoconfigure/AutoConfigurationDiscoveryTests.java
        com/acme/vendor/OptionalCodec.java
~~~

### 2.2. Public API

**File:** `src/main/java/com/acme/api/AcmeClient.java`

~~~java
package com.acme.api;

public interface AcmeClient {

    String send(String payload);
}
~~~

This is the contract that applications can inject or replace. The API contains no Spring Boot details.

### 2.3. Properties

**File:** `src/main/java/com/acme/autoconfigure/AcmeClientProperties.java`

~~~java
package com.acme.autoconfigure;

import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "acme.client")
public record AcmeClientProperties(
        @DefaultValue("https://api.acme.example") URI endpoint
) {
}
~~~

### 2.4. Default implementation and dependent bean

**File:** `src/main/java/com/acme/autoconfigure/DefaultAcmeClient.java`

~~~java
package com.acme.autoconfigure;

import java.net.URI;

import com.acme.api.AcmeClient;

public final class DefaultAcmeClient implements AcmeClient {

    private final URI endpoint;

    public DefaultAcmeClient(URI endpoint) {
        this.endpoint = endpoint;
    }

    @Override
    public String send(String payload) {
        // Deterministic stub for wiring tests; sends no real HTTP requests.
        return endpoint + "|" + payload;
    }
}
~~~

**File:** `src/main/java/com/acme/autoconfigure/AcmeClientHealth.java`

~~~java
package com.acme.autoconfigure;

import com.acme.api.AcmeClient;

public record AcmeClientHealth(AcmeClient client) {
}
~~~

`AcmeClientHealth` represents a bean depending on AcmeClient. When multiple AcmeClient beans of the same type exist without an appropriate primary/qualifier, this bean is where injection errors surface.

### 2.5. Auto-configuration

**File:** `src/main/java/com/acme/autoconfigure/AcmeClientAutoConfiguration.java`

~~~java
package com.acme.autoconfigure;

import com.acme.api.AcmeClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AcmeClient.class)
    public DefaultAcmeClient acmeClient(AcmeClientProperties properties) {
        return new DefaultAcmeClient(properties.endpoint());
    }

    @Bean
    @ConditionalOnMissingBean(AcmeClientHealth.class)
    public AcmeClientHealth acmeClientHealth(AcmeClient client) {
        return new AcmeClientHealth(client);
    }
}
~~~

We have two conditions at two scopes:

- Class-level condition: applies the entire configuration only when `acme.client.enabled=true`, or when the property is omitted because `matchIfMissing=true`.
- Bean-method condition: creates the default AcmeClient only if no bean compatible with AcmeClient exists yet; likewise for AcmeClientHealth.

When the user provides an AcmeClient, the default client backs off. The health bean can still be created and injected with the custom client.

### 2.6. Auto-configuration using an optional dependency

Optional integration example:

**File:** `src/main/java/com/acme/autoconfigure/AcmeCodecAdapter.java`

~~~java
package com.acme.autoconfigure;

public class AcmeCodecAdapter {
}
~~~

**File:** `src/main/java/com/acme/autoconfigure/AcmeCodecAutoConfiguration.java`

~~~java
package com.acme.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "com.acme.vendor.OptionalCodec")
public class AcmeCodecAutoConfiguration {

    @Bean
    public AcmeCodecAdapter acmeCodecAdapter() {
        return new AcmeCodecAdapter();
    }
}
~~~

The optional type is referenced only by name in the class condition; the method signature does not directly reference the vendor type. This keeps the configuration class guarded when the optional dependency is absent.

## 3. Error 1 — Auto-Configuration Is Not Registered

### 3.1. Intentionally creating the error

Spring Boot 3 uses the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each line is the FQCN of an auto-configuration class.

**Correct content:**

~~~text
com.acme.autoconfigure.AcmeClientAutoConfiguration
com.acme.autoconfigure.AcmeCodecAutoConfiguration
~~~

Intentionally delete the `AcmeClientAutoConfiguration` line:

~~~text
com.acme.autoconfigure.AcmeCodecAutoConfiguration
~~~

Then launch an application with `@EnableAutoConfiguration`. AcmeClient does not appear even though the class has `@AutoConfiguration` and its conditions would match.

### 3.2. Evidence to gather

Inspect the exact resource in source:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Inspect the built artifact:

~~~bash
jar tf build/libs/acme-autoconfigure-1.0.0.jar
~~~

Find the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Extract and read its content:

~~~bash
jar xf build/libs/acme-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

If a class is not in the candidate list, it is not evaluated as an auto-configuration candidate. Hence, there may be no negative condition entry for that class in the Condition Evaluation Report.

**The strongest evidence** combines:
- The imports resource lacks the required FQCN.
- The bean does not exist.
- A test going through `@EnableAutoConfiguration` also fails to find the bean.

Do not draw conclusions solely from not seeing a line in the report; verify the resource and candidate discovery.

### 3.3. Testing discovery properly

A test using `AutoConfigurations.of(AcmeClientAutoConfiguration.class)` loads the class directly. That verifies conditions and bean behavior, yet **skips discovering candidates from the imports resource**.

To test discovery, use `@EnableAutoConfiguration`:

**File:** `src/test/java/com/acme/autoconfigure/AutoConfigurationDiscoveryTests.java`

~~~java
package com.acme.autoconfigure;

import com.acme.api.AcmeClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationDiscoveryTests {

    @Test
    void clientAutoConfigurationIsDiscoveredFromImportsResource() {
        new ApplicationContextRunner()
                .withUserConfiguration(ImportsDrivenApplication.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context).hasSingleBean(AcmeClientHealth.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class ImportsDrivenApplication {
    }
}
~~~

Intentionally remove the AcmeClient line from the imports file and run the test:
- The test will fail because there is no AcmeClient.
- Restore the FQCN in the resource.
- Re-run and verify the test passes.

This is a regression test for resource discovery. It is distinct from direct auto-configuration tests in later sections.

### 3.4. How to fix

Restore the exact FQCN, ensuring:
- The file is at the exact path.
- Each candidate is one FQCN on one line.
- Package/class name matches the compiled class.
- The resource is packaged inside the JAR.
- You do not rely on component scan to discover auto-configurations.

Spring Boot 3 uses `AutoConfiguration.imports`. Do not mechanically apply older-version `spring.factories` instructions for registering new auto-configurations.

## 4. Error 2 — Auto-Configuration Discovered Yet Condition Does Not Match

Once a candidate is registered, Spring Boot evaluates conditions on the class and bean methods. If a condition fails to match, the corresponding configuration or bean is not created.

### 4.1. Intentionally making a property condition fail

The auto-configuration uses:

~~~java
@ConditionalOnProperty(
        prefix = "acme.client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
~~~

Intentionally configure:

~~~yaml
acme:
  client:
    enabled: false
~~~

Result:
- The candidate is still discovered from the imports file.
- The property condition does not match.
- Neither AcmeClient nor AcmeClientHealth is registered through this configuration.

This is an intentional condition failure, not a registration error.

### 4.2. Evidence from the Condition Evaluation Report

Run the application with:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot prints the Condition Evaluation Report. Search for `AcmeClientAutoConfiguration` and inspect the negative match. Exact wording depends on condition and version, but identify:
- Which property is checked.
- What its current value is.
- What value is required.
- Whether `matchIfMissing` allows the property to be absent.

Actuator can also be used:
1. Add `spring-boot-starter-actuator`.
2. Expose the conditions endpoint in a diagnostic environment.
3. Call `GET /actuator/conditions`.
4. Locate `AcmeClientAutoConfiguration` under `positiveMatches` or `negativeMatches`.

Example configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,conditions
~~~

The conditions endpoint can reveal internal configuration details. Expose it only per your environment's security policy; never expose it publicly by accident.

### 4.3. Testing the property condition

**File:** `src/test/java/com/acme/autoconfigure/AcmeAutoConfigurationTests.java`

~~~java
package com.acme.autoconfigure;

import java.net.URI;

import com.acme.api.AcmeClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AcmeClientAutoConfiguration.class));

    @Test
    void defaultConfigurationCreatesClient() {
        this.runner.run(context -> {
            assertThat(context).hasSingleBean(AcmeClient.class);
            assertThat(context).hasSingleBean(AcmeClientHealth.class);
            assertThat(context.getBean(AcmeClientProperties.class).endpoint())
                    .isEqualTo(URI.create("https://api.acme.example"));
        });
    }

    @Test
    void falsePropertyDisablesTheWholeAutoConfiguration() {
        this.runner
                .withPropertyValues("acme.client.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AcmeClient.class);
                    assertThat(context).doesNotHaveBean(AcmeClientHealth.class);
                    assertThat(context).doesNotHaveBean(AcmeClientProperties.class);
                });
    }
}
~~~

Here `AutoConfigurations.of(...)` intentionally loads the candidate directly to isolate the property condition. The discovery test using the imports resource was placed separately in the previous section.

### 4.4. Intentionally making a classpath condition fail

The optional codec configuration uses:

~~~java
@ConditionalOnClass(name = "com.acme.vendor.OptionalCodec")
~~~

If the vendor JAR is not on the runtime classpath, the codec configuration is not applied. This can be reproduced in tests using `FilteredClassLoader`.

Create the test fixture:

**File:** `src/test/java/com/acme/vendor/OptionalCodec.java`

~~~java
package com.acme.vendor;

public class OptionalCodec {
}
~~~

Test:

~~~java
@Test
void optionalCodecConfigurationIsSkippedWhenClassIsMissing() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(AcmeCodecAutoConfiguration.class))
            .withClassLoader(new FilteredClassLoader(OptionalCodec.class))
            .run(context ->
                    assertThat(context).doesNotHaveBean(AcmeCodecAdapter.class));
}
~~~

And test with the class present:

~~~java
@Test
void optionalCodecConfigurationMatchesWhenClassIsPresent() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(AcmeCodecAutoConfiguration.class))
            .run(context ->
                    assertThat(context).hasSingleBean(AcmeCodecAdapter.class));
}
~~~

The two tests show that the classpath condition changes with the classloader. If an optional type appears in a method signature or field of a configuration class, place the class condition at the configuration-class level and isolate the integration separately to avoid resolving the optional type before the condition can guard it.

### 4.5. Other reasons conditions fail to match

| Condition | Intentional error | Evidence to read |
| --- | --- | --- |
| `@ConditionalOnProperty` | Wrong prefix/name or value false | Property sources and negative match message |
| `@ConditionalOnClass` | Missing dependency or classloader filters out class | Classpath/dependency tree and negative match |
| `@ConditionalOnBean` | Dependent bean not yet registered | Processed bean definitions and ordering |
| `@ConditionalOnMissingBean` | User bean already exists | Candidate type/name and positive/negative match |
| `@ConditionalOnWebApplication` | Context is not Servlet/Reactive as expected | ApplicationContext class and web condition message |
| `@ConditionalOnResource` | Missing resource or wrong path | JAR contents and resource condition |

Do not modify conditions until you have identified exactly which condition failed to match and why.

## 5. Error 3 — Two Beans Sharing the Same Name Cause BeanDefinitionOverrideException

Spring distinguishes **bean name** from **bean type**. Two beans can share the same type yet have different names; or two bean definitions can share the same name whether their types match or differ.

Name collision errors typically happen when two configurations register the same bean name.

### 5.1. Intentionally creating two beans with the same name

~~~java
@Configuration(proxyBeanMethods = false)
class FirstClientConfiguration {

    @Bean("sharedClient")
    AcmeClient firstClient() {
        return payload -> "first:" + payload;
    }
}

@Configuration(proxyBeanMethods = false)
class SecondClientConfiguration {

    @Bean("sharedClient")
    AcmeClient secondClient() {
        return payload -> "second:" + payload;
    }
}
~~~

Both methods register the name `sharedClient`. When bean definition overriding is disabled, the context cannot register the second definition.

Typical error:

~~~text
BeanDefinitionOverrideException:
Invalid bean definition with name 'sharedClient'
...
Cannot register bean definition ...
There is already ... bound.
~~~

This is a **duplicate bean definition name** error, not yet a multiple-beans-of-the-same-type error.

### 5.2. Test to reproduce

~~~java
import org.springframework.beans.factory.support.BeanDefinitionOverrideException;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;

@Test
void duplicateBeanNamesFailWhenOverridingIsDisabled() {
    new ApplicationContextRunner()
            .withInitializer(context ->
                    ((DefaultListableBeanFactory) context.getBeanFactory())
                            .setAllowBeanDefinitionOverriding(false))
            .withUserConfiguration(
                    FirstClientConfiguration.class,
                    SecondClientConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasRootCauseInstanceOf(
                                BeanDefinitionOverrideException.class);
            });
}
~~~

The initializer explicitly sets `allowBeanDefinitionOverriding=false` so the test does not depend on context factory defaults. This is an intentional failure test; it must fail with the exact expected exception.

### 5.3. How to fix

Choose one of the following based on design intent:

- Rename one bean if these are two independent implementations.
- Keep only one owner of the bean if two configurations accidentally register the same responsibility.
- Use `@ConditionalOnMissingBean` for default beans in auto-configurations.
- Separate beans by qualifier if consumers need both implementations.
- If one bean is an application customization, publish a clear override interface and contract.

Do not enable `spring.main.allow-bean-definition-overriding=true` just to make the application start. That can mask duplicate configurations and make behavior depend on registration order. Allow overriding only when it is intentionally designed, documented, and tested.

## 6. Error 4 — Multiple Beans of the Same Type Cause NoUniqueBeanDefinitionException

This differs from duplicate bean names. Two differently named beans can both implement `AcmeClient`. Spring finds multiple candidates for a typed dependency and cannot tell which bean to pick.

### 6.1. Intentionally creating two AcmeClient beans

~~~java
@Configuration(proxyBeanMethods = false)
class AmbiguousClientsConfiguration {

    @Bean
    AcmeClient firstClient() {
        return payload -> "first:" + payload;
    }

    @Bean
    AcmeClient secondClient() {
        return payload -> "second:" + payload;
    }
}
~~~

Default auto-configuration has:

~~~java
@Bean
@ConditionalOnMissingBean(AcmeClient.class)
public DefaultAcmeClient acmeClient(AcmeClientProperties properties) {
    return new DefaultAcmeClient(properties.endpoint());
}
~~~

When two user beans exist, the default client backs off. However, the `AcmeClientHealth` bean requires an `AcmeClient` via its constructor/factory method. Spring sees two candidates and cannot pick one.

Typical error:

~~~text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'com.acme.api.AcmeClient' available:
expected single matching bean but found 2: firstClient,secondClient
~~~

### 6.2. Test to reproduce

~~~java
@Test
void twoClientsWithoutPrimaryCauseAmbiguousInjection() {
    this.runner
            .withUserConfiguration(AmbiguousClientsConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasRootCauseInstanceOf(
                                NoUniqueBeanDefinitionException.class);
            });
}
~~~

Key evidence is the exception naming the dependency type and candidate names. This shows:
- Auto-configuration reached the stage of creating the dependent bean.
- Multiple AcmeClient beans match.
- This is not a missing classpath or missing imports resource error.

### 6.3. Fixing with @Primary

If one implementation is the default choice for by-type injection, mark it:

~~~java
@Configuration(proxyBeanMethods = false)
class PrimaryClientsConfiguration {

    @Bean
    @Primary
    AcmeClient primaryClient() {
        return payload -> "primary:" + payload;
    }

    @Bean
    AcmeClient secondaryClient() {
        return payload -> "secondary:" + payload;
    }
}
~~~

Spring then picks the primary candidate for unqualified dependencies.

Test:

~~~java
@Test
void primaryClientResolvesAmbiguousInjection() {
    this.runner
            .withUserConfiguration(PrimaryClientsConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(AcmeClientHealth.class);
                assertThat(context.getBeanNamesForType(AcmeClient.class))
                        .containsExactlyInAnyOrder(
                                "primaryClient", "secondaryClient");

                assertThat(context.getBean(AcmeClientHealth.class).client())
                        .isSameAs(context.getBean("primaryClient"));
            });
}
~~~

Both AcmeClient beans still exist. `@Primary` only resolves candidate selection for injection points that do not specify a qualifier.

### 6.4. Fixing with @Qualifier

If consumers need to choose explicitly among multiple implementations, use a qualifier:

~~~java
@Component
class SecondaryClientJob {

    private final AcmeClient client;

    SecondaryClientJob(
            @Qualifier("secondaryClient") AcmeClient client) {
        this.client = client;
    }
}
~~~

Qualifier specifies the concrete bean for that dependency. `@Primary` is unnecessary if every consumer knows explicitly which implementation it needs.

### 6.5. Distinguishing the three mechanisms

| Mechanism | Effect | What it does not do |
| --- | --- | --- |
| `@ConditionalOnMissingBean(AcmeClient.class)` | Prevents default AcmeClient creation when a matching bean already exists | Does not choose between two user beans |
| `@Primary` | Selects preferred candidate for by-type autowiring | Does not delete the other bean, nor prevent default beans by itself |
| `@Qualifier` | Selects bean by qualifier/name at the injection point | Does not prevent other beans from being registered |

When multiple beans of the same type exist, decide clearly whether the application wants a single implementation or multiple implementations with distinct roles.

## 7. Using ConditionEvaluationReport as Evidence

Spring Boot maintains a Condition Evaluation Report inside the ApplicationContext. It is the primary tool for distinguishing applied candidates, matched conditions, and non-matched conditions.

### 7.1. Enabling the report when running the application

~~~bash
java -jar app.jar --debug
~~~

Or using a system property:

~~~bash
java -Ddebug -jar app.jar
~~~

Look for:
- `AcmeClientAutoConfiguration` under positive/negative matches.
- `OnPropertyCondition` and the message about `acme.client.enabled`.
- `OnBeanCondition` for the default AcmeClient.
- Other conditions on classes or bean methods.

### 7.2. Using the report in ApplicationContextRunner

You can print the report in tests:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))
        .withConfiguration(
                AutoConfigurations.of(AcmeClientAutoConfiguration.class))
        .withPropertyValues("acme.client.enabled=false")
        .run(context -> {
            assertThat(context).doesNotHaveBean(AcmeClient.class);
        });
~~~

This lets you observe condition reasons in tests without running the entire application.

### 7.3. Actuator conditions endpoint

If the application has Spring Boot Actuator, expose the `conditions` endpoint in a protected environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,conditions
~~~

Call:

~~~bash
curl http://localhost:8080/actuator/conditions
~~~

The response includes:
- `positiveMatches`: matched conditions.
- `negativeMatches`: excluded configurations and non-matching conditions.
- `unconditionalClasses`: auto-configurations requiring no conditions to be applied.

The endpoint lets you view the report as JSON. Protect the endpoint under the application's security policy; never expose internal configuration details to the public Internet.

### 7.4. What the report does not prove

If an auto-configuration is not listed in the imports candidates, it may not appear in the report at all. Therefore:
- A negative match in the report proves the condition was evaluated and did not match.
- A positive match in the report proves the corresponding conditions matched.
- Missing the class from the report requires checking the imports resource and candidate discovery.
- The report does not replace exception stack traces when bean creation or dependency injection fails.

## 8. Inspecting Bean Names and Bean Types in the Context

Once the context has started, inspect beans by type:

~~~java
String[] names = applicationContext.getBeanNamesForType(AcmeClient.class);
~~~

To inspect bean definitions, use `ConfigurableApplicationContext`:

~~~java
ConfigurableApplicationContext configurable =
        (ConfigurableApplicationContext) applicationContext;

for (String name : configurable.getBeanFactory()
        .getBeanNamesForType(AcmeClient.class)) {

    var definition =
            configurable.getBeanFactory().getBeanDefinition(name);

    System.out.println("name=" + name
            + ", class=" + definition.getBeanClassName()
            + ", primary=" + definition.isPrimary());
}
~~~

Illustrative output with two beans:

~~~text
name=primaryClient, class=null, primary=true
name=secondaryClient, class=null, primary=false
~~~

`class=null` can appear for factory method definitions because the implementation type comes from the factory method/return type rather than a direct bean class. To see the actual runtime type, use:

~~~java
Object bean = configurable.getBean(name);
System.out.println(bean.getClass().getName());
~~~

Do not call `getBean` inside conditions. This inspection snippet is for diagnostics after context refresh succeeds or inside test callbacks; it can initialize lazy beans if they have not yet been created.

## 9. Reading Exceptions According to Their Meaning

| Exception | Common meaning | Action needed |
| --- | --- | --- |
| `BeanDefinitionOverrideException` | Two definitions share a bean name and overriding is forbidden | Find both registration sources; rename or unify ownership |
| `NoUniqueBeanDefinitionException` | Multiple candidates of the same type for one injection point | Use `@Primary`, `@Qualifier`, or collection injection |
| `NoSuchBeanDefinitionException` | No matching candidate for a dependency | Check imports, conditions, types, and scopes |
| `BeanCreationException` | Factory/constructor failed to create the bean | Read nested causes and bean name; trace dependencies |
| `ClassNotFoundException` / `NoClassDefFoundError` | Class missing or resolved outside expected classpath | Check dependency scope, optional modules, and class-level conditions |
| `UnsatisfiedDependencyException` | Cannot supply dependency to constructor/factory method | Read nested cause: missing, ambiguous, or bean creation failure |

Do not stop at the first line of the stack trace. Find the deepest meaningful cause and the bean name being created. An `UnsatisfiedDependencyException` is often just a wrapper; the root cause may be `NoUniqueBeanDefinitionException` or `NoSuchBeanDefinitionException`.

## 10. A Comprehensive Regression Test Suite

After fixing the errors, the test suite should retain key scenarios:

~~~java
@Test
void defaultClientIsCreatedWhenEnabled() {
    runner.run(context ->
            assertThat(context).hasSingleBean(AcmeClient.class));
}

@Test
void propertyCanDisableClient() {
    runner.withPropertyValues("acme.client.enabled=false")
            .run(context ->
                    assertThat(context).doesNotHaveBean(AcmeClient.class));
}

@Test
void userClientMakesDefaultBackOff() {
    runner.withUserConfiguration(CustomClientConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(AcmeClient.class);
                assertThat(context.getBean(AcmeClient.class))
                        .isSameAs(context.getBean("customAcmeClient"));
            });
}

@Test
void primaryResolvesMultipleCandidates() {
    runner.withUserConfiguration(PrimaryClientsConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(AcmeClientHealth.class);
                assertThat(context.getBean(AcmeClientHealth.class).client())
                        .isSameAs(context.getBean("primaryClient"));
            });
}
~~~

These are illustrative test methods using the same `ApplicationContextRunner` and configurations defined above. Also keep registration tests via `@EnableAutoConfiguration` and classpath tests via `FilteredClassLoader` so the other two error classes are not missed.

### 10.1. Required test matrix

| Scenario | Setup | Primary assertion |
| --- | --- | --- |
| Discovery succeeds | `@EnableAutoConfiguration` | Auto-config bean appears |
| Missing imports | Remove FQCN from resource in experiment test | Auto-config bean does not appear |
| Property false | `withPropertyValues(...=false)` | Configuration bean absent |
| Optional class missing | `FilteredClassLoader` | Optional adapter absent |
| Custom bean | `withUserConfiguration` | Default bean backs off |
| Two beans with same name | Two `@Bean` with same name, override false | `BeanDefinitionOverrideException` |
| Two beans with same type | Two AcmeClients, no primary | `NoUniqueBeanDefinitionException` |
| With primary | One AcmeClient with `@Primary` | Dependency injected with right bean |

Each test should isolate a single cause. Avoid simultaneously introducing a bad property, a missing class, and duplicate beans, as you will not know which condition decided the result.

## 11. Dependencies and Test Execution Commands

Requires Java 17+, Spring Boot 3.3.x, JUnit 5, and AssertJ. Gradle Groovy DSL example:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run all tests:

~~~bash
# Linux/macOS
./gradlew test

# Windows
gradlew.bat test
~~~

Run a specific test class:

~~~bash
./gradlew test --tests "com.acme.autoconfigure.AcmeAutoConfigurationTests"
~~~

**Expected results after fixing:**
- Discovery test passes when the imports file contains the exact FQCN.
- Default/property tests pass.
- Custom bean test proves default back-off.
- Duplicate name test intentionally fails with `BeanDefinitionOverrideException` and is counted as passing when the assertion catches the expected exception.
- Two-beans-same-type-without-primary test intentionally fails with `NoUniqueBeanDefinitionException`.
- Primary test passes and injects the right bean.

Failure-injection tests must assert the specific exception. Do not treat a test as passing merely because the context failed for any reason.

## 12. Evidence-Driven Diagnostic Workflow

When encountering errors in a real application, follow this order:

1. **Confirm the symptom.** Is a bean missing or does the context fail to start?
2. **Check candidate registration.** Open the exact JAR and read `AutoConfiguration.imports`; verify the FQCN is in the resource.
3. **Check the condition report.** Run `--debug` or inspect `/actuator/conditions`; locate positive/negative matches.
4. **Check Environment.** Confirm effective properties, profiles, command-line args, and environment variables.
5. **Check classpath.** Use dependency tree and FilteredClassLoader tests for optional classes.
6. **Check bean names/types.** Use `getBeanNamesForType` and bean definition metadata.
7. **Read the root cause.** Classify `BeanDefinitionOverrideException`, `NoUniqueBeanDefinitionException`, `NoSuchBeanDefinitionException`, or bean creation failure.
8. **Fix one cause.** Do not simultaneously change resources, properties, and bean names.
9. **Add a regression test.** Reproduce the old error and verify the fix.
10. **Inspect the artifact.** Rebuild the JAR, verify the imports resource, and run a sample consumer.

### 12.1. Quick decision table

| Observed evidence | Priority conclusion | Next action |
| --- | --- | --- |
| FQCN missing from imports file | Missing registration | Add the right line, rebuild JAR |
| FQCN in imports, negative match in report | Condition failed to match | Read message, fix property/class/bean condition |
| Positive match in report, bean method creates no bean | Method-level condition or registration method | Check method conditions and bean name/type |
| Same bean name registered from two sources | Bean name conflict | Find both definitions and unify naming/ownership |
| Two beans of same type, injection reports 2 candidates | Ambiguous dependency | Primary, qualifier, or collection |
| Dependency has no bean | Missing dependency | Check conditions and bean definition processing order |
| Class cannot be resolved | Dependency/classpath issue | Check runtime scope and optional class protection |

## 13. Design Principles to Prevent Errors

### 13.1. Auto-configurations must have explicit resource registration

- Use `@AutoConfiguration`.
- List FQCNs in `AutoConfiguration.imports`.
- Inspect the resource in the JAR.
- Do not rely on component scan.

### 13.2. Conditions must have predictable contracts

- Use `@ConditionalOnProperty` with clear prefix/name/havingValue.
- Choose `matchIfMissing` deliberately.
- Guard optional dependencies with class-level conditions.
- Place bean conditions in auto-configurations.
- Use `@ConditionalOnMissingBean` for replaceable default implementations.

### 13.3. Bean types and names must be intentional

- Bean names describe roles; never reuse one name for two distinct responsibilities.
- Public bean return types must supply sufficient type information for conditions.
- If multiple implementations exist, document qualifiers or primary.
- Do not use bean overriding as a default conflict-resolution mechanism.

### 13.4. Test each layer independently

- Discovery test via `@EnableAutoConfiguration`.
- Condition test via `ApplicationContextRunner`.
- Optional class test via `FilteredClassLoader`.
- Bean conflict tests for both name and type.
- Artifact test for packaged resources.

## 14. Common Mistakes When Diagnosing

1. **Seeing a missing bean and immediately adding @Primary.** Primary only resolves multiple candidates; it does not register a missing auto-configuration.
2. **Seeing a condition fail to match and immediately adding a dependency.** If a property is false, adding a JAR will not fix the property condition.
3. **Using only AutoConfigurations.of to test the imports file.** That loads the class directly; use `@EnableAutoConfiguration` to test discovery.
4. **Skipping JAR inspection.** A resource present in the IDE yet missing from the published artifact still prevents consumers from discovering auto-configuration.
5. **Assuming no report entry means the condition was false.** The candidate might not have been registered; check the imports resource.
6. **Confusing BeanDefinitionOverrideException with NoUniqueBeanDefinitionException.** One is a duplicate definition name, the other is multiple candidates of the same type.
7. **Enabling allow-bean-definition-overriding to hide errors.** It can mask ownership conflicts and make behavior depend on registration order.
8. **Using @Primary to replace a default bean.** The default may still exist; use `@ConditionalOnMissingBean` to back off.
9. **Using @Qualifier to delete a bean.** Qualifier only selects a candidate at the injection point.
10. **Placing @ConditionalOnMissingBean in regular user configuration.** The condition might run before expected bean definitions are processed; put it in auto-configuration.
11. **Omitting a concrete return type on @Bean methods.** Bean conditions may lack type information to evaluate accurately.
12. **Using a classpath condition while method signatures still expose optional types.** Separate configuration classes and guard at class level.
13. **Reading only the first exception.** The root cause may pinpoint missing vs. ambiguous dependencies accurately.
14. **Changing multiple things at once.** Makes it impossible to tell which fix solved the error; change one factor and re-run tests.
15. **Dropping failure-injection tests.** Bugs can regress when changing imports, properties, or adding new implementations.

## 15. Lab Completion Checklist

- [ ] Intentionally remove an FQCN from `AutoConfiguration.imports` and observe the bean is not discovered.
- [ ] Use a test via `@EnableAutoConfiguration` to verify registration.
- [ ] Intentionally set property enabled=false and read the negative match.
- [ ] Intentionally exclude an optional class with `FilteredClassLoader`.
- [ ] Create two beans with the same name when overriding is disabled and identify `BeanDefinitionOverrideException`.
- [ ] Create two beans of the same type without primary and identify `NoUniqueBeanDefinitionException`.
- [ ] Add `@Primary` or `@Qualifier` and verify injection.
- [ ] Use `@ConditionalOnMissingBean` so a custom bean replaces the default.
- [ ] Read the Condition Evaluation Report or Actuator conditions endpoint.
- [ ] Inspect bean names/types in the ApplicationContext.
- [ ] Restore the imports resource and run all regression tests.
- [ ] Verify the final JAR contains the right resource.

## 16. Self-Check Questions

**Question 1.** A class has `@AutoConfiguration` yet is absent from `AutoConfiguration.imports`. What happens?

**Answer:** It is not discovered as a candidate through the auto-configuration imports mechanism. The annotation on the class does not register the candidate by itself.

**Question 2.** Why does `AutoConfigurations.of(AcmeClientAutoConfiguration.class)` not prove the imports file is correct?

**Answer:** Because the runner loads the class directly. To verify discovery, use `@EnableAutoConfiguration` or `@SpringBootApplication` so Boot reads the candidate resource.

**Question 3.** `acme.client.enabled=false` yet the imports file is right. What error is this?

**Answer:** The candidate was registered, yet the property condition did not match. Inspect the Condition Evaluation Report to confirm values and messages.

**Question 4.** Two configurations declare the same bean name with overriding disabled. Which exception typically appears?

**Answer:** `BeanDefinitionOverrideException`.

**Question 5.** Two beans have different names yet both implement AcmeClient, and a constructor takes AcmeClient. Which exception can occur?

**Answer:** `NoUniqueBeanDefinitionException`, because Spring cannot pick a single unique candidate.

**Question 6.** Does `@Primary` prevent the default bean from being created?

**Answer:** No. `@Primary` only prioritizes a candidate during autowiring; `@ConditionalOnMissingBean` is what makes the default bean back off when a matching bean already exists.

**Question 7.** When do you use `FilteredClassLoader`?

**Answer:** When simulating a class or package absent from the runtime classpath to test classpath conditions and optional integrations.

**Question 8.** Is not seeing an auto-configuration in the Condition Evaluation Report enough to conclude the condition failed to match?

**Answer:** No. The candidate might not have been registered. Check the imports resource and artifact first.

## 17. Key Takeaways

Auto-configuration diagnostics should follow evidence and the right stage. First verify the candidate is discovered from `AutoConfiguration.imports`. If it is, read the Condition Evaluation Report to see which condition failed to match. Once bean definitions are registered, distinguish name conflicts from type conflicts using exceptions and the bean candidate list.

`BeanDefinitionOverrideException` usually indicates two definitions with the same name. `NoUniqueBeanDefinitionException` indicates multiple beans of the same type for one injection point. `@ConditionalOnMissingBean` lets default implementations back off for custom beans; `@Primary` and `@Qualifier` choose among multiple implementations. These mechanisms solve distinct problems.

Maintain three separate test layers: discovery via `@EnableAutoConfiguration`, conditions via `ApplicationContextRunner`, and bean conflicts via contexts with intentionally conflicting configurations. After fixing, inspect the built JAR and retain regression tests so bugs do not return.

### Official Spring Boot 3.3 Documentation

- [Creating Your Own Auto-configuration — Conditions and Testing](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Troubleshooting Auto-configuration — Condition Evaluation Report](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Conditions Actuator Endpoint — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html)
- [@ConditionalOnMissingBean Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [ApplicationContextRunner Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [FilteredClassLoader Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html)
