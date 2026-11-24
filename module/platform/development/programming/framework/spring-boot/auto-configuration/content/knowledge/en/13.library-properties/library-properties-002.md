# Registering Library Property Classes with @EnableConfigurationProperties in Spring Boot

## 1. The Problem: A Library Needs a Strongly Typed Configuration Bean

An integration library often needs to receive configuration from the application using it, such as an endpoint, timeouts, and a feature toggle flag:

~~~properties
acme.client.endpoint=https://orders.example/api
acme.client.connect-timeout=5s
acme.client.enabled=true
~~~

In Spring Boot, `@ConfigurationProperties` describes how to **bind** keys sharing a prefix into a Java object. However, placing `@ConfigurationProperties` on a class **is not enough to guarantee that the class is registered as a Spring bean** in every context. When building a starter or library auto-configuration, the explicit and reliable way to register it is:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {
    // Library @Bean methods using AcmeClientProperties
}
~~~

The desired outcome is:
- Spring Boot knows it must register `AcmeClientProperties` as a bean in the `ApplicationContext` when this configuration is applied.
- The binding system pulls corresponding values from the Spring `Environment` and maps them to the fields/constructor of the class.
- Business beans created later can receive `AcmeClientProperties` via constructor injection or `@Bean` method parameters.
- The consuming application does not have to manually declare `@Bean AcmeClientProperties` or scan the library's private package.

**Key takeaway:** `@ConfigurationProperties` describes **the data shape and prefix**, whereas `@EnableConfigurationProperties` on the configuration using the library specifies **which properties classes are registered**. It does not mean automatically scanning every properties class on the classpath.

## 2. Three Roles: Declaration, Registration, and Consumption

Distinguish three steps:

| Step | Mechanism | Responsibility |
| --- | --- | --- |
| **Declare configuration type** | `@ConfigurationProperties(prefix = "acme.client")` | Choose the namespace and map keys to typed Java properties. |
| **Register configuration bean** | `@EnableConfigurationProperties(AcmeClientProperties.class)` | Tell Spring Boot which specific properties class must be processed in the context. |
| **Consume bound bean** | Constructor injection or `@Bean` parameter | Read bound values to initialize business components. |

High-level example:

~~~text
application.yml / application.properties / environment variables
                         |
                         v
                 Spring Environment
                         |
                         v
           Configuration Properties Binder
                         |
                         v
           AcmeClientProperties (Spring bean)
                         |
                         v
          ClientAutoConfiguration @Bean
                         |
                         v
                     AcmeClient
~~~

This chain illustrates **the flow of values from source to consumer**. In reality, Spring Boot performs bean definition registration, binding, and bean instantiation according to the container lifecycle; the diagram does not mean every stage always executes sequentially like a runtime pipeline.

### The Two Annotations Do Not Replace Each Other

~~~java
@ConfigurationProperties(prefix = "acme.client")
public class AcmeClientProperties {
    // fields / getters / setters
}
~~~

This class has metadata for the binder to process, but merely writing the class and putting the JAR on the classpath is not enough for every application to create a bean automatically. To enable it for a specific class, write:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AcmeClientProperties.class)
class AcmeClientConfiguration {
}
~~~

For auto-configuration, using `@AutoConfiguration` instead of `@Configuration` is the right choice because Spring Boot has a dedicated discovery and conditionalization mechanism for auto-configuration.

## 3. Exact Syntax of @EnableConfigurationProperties

The annotation must be imported from:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
~~~

The `value` attribute is a `Class<?>[]` array, so it can register **one or more** classes annotated with `@ConfigurationProperties`:

~~~java
@AutoConfiguration
@EnableConfigurationProperties({
    AcmeClientProperties.class,
    AcmeRetryProperties.class
})
public class AcmeClientAutoConfiguration {
}
~~~

The `AcmeClientProperties` and `AcmeRetryProperties` classes above are library-provided classes; they need to be defined and annotated appropriately with `@ConfigurationProperties`. The single-class form can be written concisely:

~~~java
@EnableConfigurationProperties(AcmeClientProperties.class)
~~~

The form without passing any class:

~~~java
@EnableConfigurationProperties
~~~

still activates `@ConfigurationProperties` processing support under Spring Boot's mechanism, **but does not arbitrarily register every properties class the library has on the classpath**. If your intent is to register the library's type, pass the class in the `value` list.

### Where to Place the Annotation?

- On the library's `@AutoConfiguration`: the appropriate approach when the library is integrated via a starter.
- On a regular `@Configuration`: appropriate if the application explicitly imports the configuration.
- Do not place it on a `@Bean` method: `@EnableConfigurationProperties` has target **TYPE**, valid at the class/interface annotation level, not METHOD.

When an auto-configuration class is excluded by a class-level condition, the bean declarations and property registrations attached to that configuration are not applied through that class either. Conversely, when the class is applied and only **one `@Bean` method** is excluded by a method-level condition, class-level `@EnableConfigurationProperties` can still register the properties bean.

## 4. Realistic Library Structure Example (Java 17+, Spring Boot 3.3)

Suppose a library has a properties class, a client, and an auto-configuration. The following three files form a complete illustrative example of how to wire the parts together; packages and class names must match when applied to a project.

**File `src/main/java/com/acme/client/AcmeClientProperties.java`:**

~~~java
package com.acme.client;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.client")
public class AcmeClientProperties {

    private URI endpoint = URI.create("https://api.example.invalid");
    private Duration connectTimeout = Duration.ofSeconds(2);
    private boolean enabled;

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

The class has a default constructor generated by Java, standard JavaBean getters/setters, and default values. Spring Boot can convert `String` to `URI` and `Duration` during binding, for example `5s` to `Duration.ofSeconds(5)`.

**File `src/main/java/com/acme/client/AcmeClient.java`:**

~~~java
package com.acme.client;

import java.net.URI;
import java.time.Duration;

public class AcmeClient {

    private final URI endpoint;
    private final Duration connectTimeout;

    public AcmeClient(URI endpoint, Duration connectTimeout) {
        this.endpoint = endpoint;
        this.connectTimeout = connectTimeout;
    }

    public String description() {
        return endpoint.getHost() + " | " + connectTimeout.toSeconds() + "s";
    }
}
~~~

`AcmeClient` here is a simple Java object illustrating configuration consumption; it does not open HTTP connections. In a real library, the client could be an HTTP adapter, message producer, or business service.

**File `src/main/java/com/acme/client/AcmeClientAutoConfiguration.java`:**

~~~java
package com.acme.client;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.client",
            name = "enabled",
            havingValue = "true"
    )
    @ConditionalOnMissingBean(AcmeClient.class)
    AcmeClient acmeClient(AcmeClientProperties properties) {
        return new AcmeClient(
                properties.getEndpoint(),
                properties.getConnectTimeout()
        );
    }
}
~~~

There are two separate decisions in the code:

1. `@EnableConfigurationProperties(AcmeClientProperties.class)` registers the bean holding the library's configuration.
2. `@ConditionalOnProperty(... havingValue = "true")` on `@Bean` enables `AcmeClient` only when `acme.client.enabled=true`; `@ConditionalOnMissingBean` lets the application supply its own `AcmeClient`.

Therefore **`enabled=false` does not mean the properties bean disappears**. The auto-configuration class still participates, the properties bean is still registered, and only the `AcmeClient` created by the method above is skipped.

### Registering Auto-Configuration in the JAR

Create the file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

With a single line of content:

~~~text
com.acme.client.AcmeClientAutoConfiguration
~~~

This is the file Spring Boot 3.x uses to locate auto-configuration classes inside a JAR. Merely adding `@AutoConfiguration` and `@EnableConfigurationProperties` to a class without **registering the auto-configuration class properly** will not ensure the application automatically applies the configuration.

The consuming project adds the dependency containing the classes above to its classpath and configures:

~~~yaml
acme:
  client:
    enabled: true
    endpoint: https://orders.example/api
    connect-timeout: 5s
~~~

When the context starts successfully, `AcmeClientProperties` will be bound and the `AcmeClient` bean will use the endpoint/timeout above. For example, `description()` returns `orders.example | 5s`. This is the return value of the illustrative method, not a default startup log.

## 5. How Is the Bean Named and Injected?

When a `@ConfigurationProperties` class is registered via `@EnableConfigurationProperties` (or `@ConfigurationPropertiesScan`), Spring Boot uses the bean naming convention:

~~~text
<prefix>-<fully-qualified-class-name>
~~~

For example, for the class in section 4:

~~~text
acme.client-com.acme.client.AcmeClientProperties
~~~

If `@ConfigurationProperties` has no prefix, the name is usually the fully qualified class name. This naming mechanism differs from the default name of a bean created by a `@Bean` method, which typically comes from the method name.

However, when consuming properties in a bean method, **inject by type**:

~~~java
@Bean
AcmeClient acmeClient(AcmeClientProperties properties) {
    return new AcmeClient(
            properties.getEndpoint(),
            properties.getConnectTimeout()
    );
}
~~~

The snippet above only illustrates dependency injection, not a complete standalone configuration. Normally applications **do not need and should not hardcode** the prefix+FQN bean name to obtain the instance.

Having the type `AcmeClientProperties` appear in a `@Bean` parameter **does not automatically register** that bean. If the context does not yet have a properties bean, constructor/method injection may fail with a missing dependency error. The prerequisite is that the class has already been registered via an appropriate mechanism.

### Do Not Register Repeatedly via Multiple Uncontrolled Paths

Avoid simultaneously:
- Registering `AcmeClientProperties` via `@EnableConfigurationProperties(AcmeClientProperties.class)`.
- Annotating the same class with `@Component` so component scanning also detects it.
- Manually declaring an extra `@Bean AcmeClientProperties` without a clear reason.

Different registration paths can **produce multiple beans of the same type**, causing ambiguous injection, hard-to-control lifecycles, and surprises with binding/validation. Do not assume by default that each registration path produces the same name or excludes the others. In a starter, use a single clearly documented registration path.

## 6. Comparison with @ConfigurationPropertiesScan and @Component

| Registration method | How it works | When to use |
| --- | --- | --- |
| `@EnableConfigurationProperties(X.class)` | **Explicitly** registers class X | Libraries, auto-configuration, activating only needed property groups |
| `@ConfigurationPropertiesScan` | Finds `@ConfigurationProperties` classes in scanned packages | Applications owning their properties package and wanting to register multiple classes by convention |
| `@Component` on `@ConfigurationProperties` class | Component scan registers it as a normal Spring bean, then binding processes metadata | Mutable JavaBeans with normal bean lifecycle and scan needs; unsuitable for pure constructor binding |
| `@Bean` with `@ConfigurationProperties` on method | Registers an instance created by the method, then the binder attaches properties | Third-party library components whose source cannot be edited to annotate the class |

**Crucial distinction:** `@SpringBootApplication` includes component scanning for components, but that **does not automatically enable `@ConfigurationPropertiesScan`** for all plain properties classes. If a class is not a component and has no separate enable/scan mechanism, it may have no bean.

For **libraries**, avoid depending on another application scanning the `com.acme.client` package. The library's package may lie outside the application's scan root. Declaring `@EnableConfigurationProperties` on auto-configuration ensures the dependency is defined **where the library is responsible**.

Example scanning in an application (not a required strategy for starters):

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan("com.example.app.config")
public class ExampleApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExampleApplication.class, args);
    }
}
~~~

This snippet requires the corresponding `SpringBootApplication`, `ConfigurationPropertiesScan`, and `SpringApplication` imports, and assumes the `com.example.app.config` package contains valid properties classes. It illustrates the difference in **class discovery scope**, rather than replacing the starter registration in section 4.

## 7. Record, Constructor Binding, and JavaBean Binding

Spring Boot 3.3 supports two main styles:

**JavaBean binding:** a class with a no-arg constructor and getters/setters, matching the `AcmeClientProperties` example above. Default values can be set on fields and configured properties are bound into them.

**Constructor binding:** an immutable class/`record` receives values through its constructor instead of setters. With a suitable constructor (such as a record's single canonical constructor), Spring Boot 3.x infers constructor binding; there is no need to place `@ConstructorBinding` on the whole class just to use a record.

Example of a **standalone record**:

~~~java
package com.acme.client;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "acme.retry")
public record AcmeRetryProperties(
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("2s") Duration backoff
) {
}
~~~

To use the record:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(AcmeRetryProperties.class)
class AcmeRetryAutoConfiguration {
}
~~~

These two snippets are examples of record configuration; in a real project, `AutoConfiguration` and `EnableConfigurationProperties` imports are needed in the configuration file.

**Constraint of constructor binding:** properties classes created through enabling or configuration property scanning support this binding style. Constructor binding **is not intended for a bean created through ordinary Spring mechanisms** such as `@Component`, `@Bean` methods, or `@Import`. Do not annotate that same record as a component just to "register it quickly." When a bean must be created via a factory method, JavaBean binding and a suitable object design are normally used.

To capture constructor parameter names during binding, the project must be compiled with `-parameters`. The Spring Boot Gradle plugin and Boot's standard Maven configuration handle this. If you do not use those build conventions, check compiler flags.

### Do Not Inject Business Dependencies into Properties Classes

A `@ConfigurationProperties` class best represents **data from the Environment**. Do not constructor-inject a service/repository into it and confuse dependency beans with property values. Business beans should receive properties after they have been bound:

~~~text
Environment -> AcmeClientProperties -> AcmeClient
~~~

This organization allows testing the binder and business logic independently.

## 8. Validation and Limitations of @EnableConfigurationProperties

`@EnableConfigurationProperties` registers the bean, **which does not mean the data is automatically valid**. When input constraints are needed, Spring Boot supports validation of `@ConfigurationProperties`:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.credentials")
public record AcmeCredentialsProperties(
        @NotBlank String token,
        @Positive int poolSize
) {
}
~~~

This is an **illustrative snippet**; place it in a valid class/file and ensure a Jakarta Bean Validation provider is present, usually via the `spring-boot-starter-validation` dependency. Then register `AcmeCredentialsProperties.class` in `@EnableConfigurationProperties`. If a valid `token` or `pool-size` is not provided, binding/validation can fail application startup with a configuration error, helping catch issues early.

Do not confuse three distinct tasks:
1. **Registration:** `@EnableConfigurationProperties`.
2. **Data binding:** `@ConfigurationProperties`, binder, conversion.
3. **Validation:** `@Validated` + constraints and validation provider.

`@ConfigurationProperties` does not use Spring Expression Language (SpEL) by default like `@Value`. The enable annotation itself does not grant secret access or actively load new property files; values come from property sources already in the `Environment` by precedence order.

## 9. Runnable Spring Boot 3.3 Test

The following example is **a complete Java test file**, independent of the three illustrative files in section 4. It uses Java 17+, Spring Boot 3.3, JUnit 5, AssertJ, and `ApplicationContextRunner` to verify property registration, value binding, client enablement conditions, and the user's ability to replace the default bean.

Create the file `src/test/java/com/example/demo/EnableLibraryPropertiesTest.java`:

~~~java
package com.example.demo;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class EnableLibraryPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ClientAutoConfiguration.class));

    @ConfigurationProperties(prefix = "acme.client")
    public static class ClientProperties {
        private URI endpoint = URI.create("https://api.example.invalid");
        private Duration connectTimeout = Duration.ofSeconds(2);
        private boolean enabled;

        public URI getEndpoint() {
            return endpoint;
        }

        public void setEndpoint(URI endpoint) {
            this.endpoint = endpoint;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }

    static final class ClientFacade {
        private final URI endpoint;
        private final Duration timeout;

        ClientFacade(URI endpoint, Duration timeout) {
            this.endpoint = endpoint;
            this.timeout = timeout;
        }

        String description() {
            return endpoint.getHost() + " | " + timeout.toSeconds() + "s";
        }
    }

    @AutoConfiguration
    @EnableConfigurationProperties(ClientProperties.class)
    static class ClientAutoConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.client",
                name = "enabled",
                havingValue = "true"
        )
        @ConditionalOnMissingBean(ClientFacade.class)
        ClientFacade clientFacade(ClientProperties properties) {
            return new ClientFacade(
                    properties.getEndpoint(),
                    properties.getConnectTimeout()
            );
        }
    }

    @Test
    void annotationAloneDoesNotRegisterPropertiesBean() {
        new ApplicationContextRunner().run(context ->
                assertThat(context).doesNotHaveBean(ClientProperties.class));
    }

    @Test
    void enabledRegistrationCreatesPropertiesWithDefaults() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(ClientProperties.class);
            assertThat(context).doesNotHaveBean(ClientFacade.class);

            ClientProperties properties = context.getBean(ClientProperties.class);
            assertThat(properties.getEndpoint().toString())
                    .isEqualTo("https://api.example.invalid");
            assertThat(properties.getConnectTimeout())
                    .isEqualTo(Duration.ofSeconds(2));
            assertThat(properties.isEnabled()).isFalse();
        });
    }

    @Test
    void bindsValuesFromSpringEnvironment() {
        runner.withPropertyValues(
                "acme.client.endpoint=https://orders.example/api",
                "acme.client.connect-timeout=5s",
                "acme.client.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ClientProperties.class);
                    assertThat(context).hasSingleBean(ClientFacade.class);

                    ClientProperties properties =
                            context.getBean(ClientProperties.class);
                    assertThat(properties.getEndpoint().getHost())
                            .isEqualTo("orders.example");
                    assertThat(properties.getConnectTimeout())
                            .isEqualTo(Duration.ofSeconds(5));
                    assertThat(properties.isEnabled()).isTrue();
                    assertThat(context.getBean(ClientFacade.class).description())
                            .isEqualTo("orders.example | 5s");
                });
    }

    @Test
    void disabledClientDoesNotRemovePropertiesBean() {
        runner.withPropertyValues("acme.client.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(ClientProperties.class);
                    assertThat(context).doesNotHaveBean(ClientFacade.class);
                });
    }

    @Test
    void userClientBeanMakesAutoConfigurationBackOff() {
        runner.withPropertyValues("acme.client.enabled=true")
                .withBean(ClientFacade.class,
                        () -> new ClientFacade(
                                URI.create("https://user.example"),
                                Duration.ofSeconds(9)))
                .run(context -> {
                    assertThat(context).hasSingleBean(ClientProperties.class);
                    assertThat(context).hasSingleBean(ClientFacade.class);
                    assertThat(context.getBean(ClientFacade.class).description())
                            .isEqualTo("user.example | 9s");
                });
    }
}
~~~

Run in a project with the `org.springframework.boot:spring-boot-starter-test` dependency and Gradle wrapper:

~~~bash
./gradlew test --tests "com.example.demo.EnableLibraryPropertiesTest"
~~~

Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.EnableLibraryPropertiesTest"
~~~

**Expected result:** all **5 tests PASS**. They are assertions checking beans and values, not commands producing fixed stdout. `ApplicationContextRunner` uses `AutoConfigurations.of(...)` to provide the auto-configuration directly in the test; therefore this test fixture does not require `AutoConfiguration.imports`. Packaging the starter to run in a real application still needs the imports file as in section 4.

The tests prove:
- `@ConfigurationProperties` metadata alone on a class is not enough for the bean to appear in an empty context.
- `@EnableConfigurationProperties(ClientProperties.class)` registers the bean even when no properties are passed; Java default values still apply.
- The `connect-timeout` key is relaxed-bound to `connectTimeout`, and the string `5s` is converted to `Duration`.
- The condition on the client bean can fail to match while the properties bean still exists.
- A user-supplied bean takes precedence when auto-configuration has `@ConditionalOnMissingBean`.

## 10. Common Mistakes in Libraries

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` for `AcmeClientProperties` | Class has `@ConfigurationProperties` but was not registered via enable/scan/bean | Place `@EnableConfigurationProperties(AcmeClientProperties.class)` on a participating auto-configuration |
| Auto-configuration class is not applied | Missing entry in `AutoConfiguration.imports` or excluded by a condition/exclude | Check the imports file path and class-level conditions |
| YAML property has a value but Java field remains default | Wrong prefix/key, class not registered, missing setter, or incompatible mapping | Check prefix, relaxed binding, accessors/constructor, and effective value in `Environment` |
| Multiple beans of the same properties type | Both `@EnableConfigurationProperties` and another `@Bean`/component scan | Choose one primary registration method; inspect bean definitions before removing config |
| Record is not constructor-bound as expected | Registered via normal `@Component`/`@Bean` or missing compiler parameter metadata | Register via enable/scan and ensure the build supports `-parameters` |
| Client bean is absent while properties are present | Condition on `@Bean` method did not match | Check `@ConditionalOnProperty`/`@ConditionalOnClass` on the business bean |
| Project adds starter but IDE does not suggest keys | Missing metadata processor or property descriptions | Add `spring-boot-configuration-processor` and check built metadata |
| Validation does not trigger | Missing `@Validated`, constraints, or validator provider | Configure validation completely and test invalid input |
| Properties bean name differs from short class name | Bean name convention under enable/scan uses prefix + FQN | Inject by type; avoid hardcoding bean names |
| Library only works when the application scans the library's package | Relying on the consuming app's component scan | Register explicitly with `@EnableConfigurationProperties` in auto-configuration |

### Distinguishing the Two Annotation Processors

- `spring-boot-configuration-processor` generates **configuration metadata** so IDEs can offer autocomplete and property key descriptions.
- `spring-boot-autoconfigure-processor` generates **metadata supporting auto-configuration filtering** to optimize startup.

Neither processor is a replacement for `@EnableConfigurationProperties(AcmeClientProperties.class)` or for registering auto-configuration via the imports file.

## 11. Safe Diagnosis and Design Practices

When a library properties bean does not appear, inspect in order:

1. **Properties class:** does it have the right `@ConfigurationProperties(prefix = "...")` on the class and valid getters/setters or constructor binding?
2. **Registering configuration class:** does it have `@EnableConfigurationProperties(X.class)` with **the exact type X**, and does that class actually participate in the context?
3. **Auto-configuration discovery:** does `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` contain the exact class name and proper separator for nested classes if any?
4. **Class-level conditions:** do `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, or excludes prevent the class from participating?
5. **Configuration sources:** in which source does the key exist, what is the final value per `Environment` precedence, and are there typos in the prefix/spelling?
6. **Binding and validation:** can the Java type be converted from the property, is there a null/invalid value, and is Bean Validation enabled?
7. **Consumer bean:** do properties exist while the business `@Bean` has its own condition or backed off due to `@ConditionalOnMissingBean`?

Enable Spring Boot's `--debug` or `debug=true` to view the **Condition Evaluation Report** if you suspect auto-configuration was excluded. When Actuator is installed and the appropriate endpoints are exposed, `/actuator/configprops` helps inspect configuration beans (be careful with sensitive values and masking), and `/actuator/conditions` shows match/unmatch reasons. For automated tests, `ApplicationContextRunner` helps build each case using `withPropertyValues(...)` and `withBean(...)` to make conditions explicit.

In library design, keep a library-owned namespace like `acme.client`, pick clear defaults, manage validation for required values, and let auto-configuration handle registering concrete properties beans. Avoid forcing consuming applications to know the library's internal packages.

## 12. Self-Check Knowledge

1. Does merely writing `@ConfigurationProperties("acme.client")` on a POJO and putting the JAR on the classpath guarantee the bean is created? **No.** A registration mechanism is needed.
2. Does `@EnableConfigurationProperties(A.class)` automatically discover every class B and C in the same package? **No.** It specifies the exact class to register.
3. Why should `@EnableConfigurationProperties` be placed on the library's auto-configuration? **So the library itself decides which properties beans are needed, independent of the consuming application's scan root.**
4. Can the properties bean still exist when a client `@Bean` method annotated with `@ConditionalOnProperty` does not match? **Yes, it can**, because property registration happens at the auto-configuration class level, which is still applied.
5. Is `@ConfigurationPropertiesScan` automatically part of `@SpringBootApplication`? **No**; scanning must be enabled when choosing that mechanism.
6. What is the default bean name of a properties class registered via enable? **`<prefix>-<FQN>`**, for example `acme.client-com.acme.client.AcmeClientProperties`.
7. When using record constructor binding, should you also declare `@Component` to "make sure" the bean gets scanned? **No.** Use enable or configuration property scanning and ensure constructor parameters are preserved.
8. Does `@EnableConfigurationProperties` automatically validate a `@NotBlank` field when there is no validator provider? **Do not expect it to**; `@Validated` and properly configured Bean Validation are required.
9. If a config class is not yet in `AutoConfiguration.imports`, does merely adding `@EnableConfigurationProperties` to it make the starter run automatically? **No.** The auto-configuration loading mechanism is required.
10. Why can an `AcmeClientProperties` bean be missing even though `acme.client.enabled=true` is already in YAML? Because **a property source does not turn a properties class into a bean by itself**; it must be registered, bound, and its configuration must be applied.

## Official Documentation

- [Spring Boot 3.3 — Externalized Configuration, type-safe configuration properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): binding mechanism, `@EnableConfigurationProperties`, scanning, constructor binding, validation, and bean names.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): auto-configuration discovery via `AutoConfiguration.imports` and starter design.
- [Spring Boot 3.3 — JavaDoc `@EnableConfigurationProperties`](https://docs.spring.io/spring-boot/3.3.8/api/java/org/springframework/boot/context/properties/EnableConfigurationProperties.html): type-level annotation, `value`, and explicit bean registration.
- [Spring Boot 3.3 — Configuration Metadata Annotation Processor](https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata/annotation-processor.html): metadata for IDE support.
