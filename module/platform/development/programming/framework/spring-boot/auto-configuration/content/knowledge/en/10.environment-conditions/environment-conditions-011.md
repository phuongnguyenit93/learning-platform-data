# Combining Environment, Classpath, and Bean Conditions So Auto-Configuration Does Not Activate Unexpectedly

## 1. Problem: Having a Library Is Not Enough to Allow Bean Creation

An integration library may bring in the required classes, yet **not every application needs the feature turned on**. For example, a module providing `AuditReporter` for web systems should only create the default reporter when all of these requirements are met simultaneously:

1. **Application environment:** running as a **Servlet** web application, not CLI or WebFlux.
2. **Classpath:** the optional integration library (e.g. Audit SDK) is present.
3. **Operational configuration:** `demo.audit.enabled=true` is explicitly declared.
4. **Dependent bean:** the application already provides an `AuditTransport` to send data out.
5. **Customization rights:** no `AuditReporter` bean created by the application or another configuration exists yet.

Missing even one “gate” can cause unintended behavior: merely adding a starter auto-enables the reporter; the bean is created even though the user has not flipped the flag; a CLI app gets pulled into web logic; or the default bean competes with a business bean.

The desired design can be expressed as:

```text
CREATE_DEFAULT =
    SERVLET_WEB_CONTEXT
    AND OPTIONAL_SDK_ON_CLASSPATH
    AND demo.audit.enabled == "true"
    AND EXISTS(AuditTransport bean)
    AND NOT EXISTS(AuditReporter bean)
```

`@Conditional...` annotations placed on the same configuration or bean method act as conditions that **must all be satisfied**. Do not rely on a specific framework evaluation order to guard optional dependencies; class structure and condition placement are the critical design choices.

## 2. Four Distinct Layers of Checks

| Group | Spring Boot 3.3 annotation | Question actually answered | What the annotation does **not** prove |
|---|---|---|---|
| Environment type | `@ConditionalOnWebApplication(type = SERVLET)`, `@ConditionalOnNotWebApplication` | Is the context of the corresponding web type? | Whether any specific controller, route, or business bean exists? |
| Classpath | `@ConditionalOnClass`, `@ConditionalOnMissingClass` | Can the class be found on the classpath by the current class loader? | Whether a bean of that class is registered or the library is configured properly? |
| Environment property | `@ConditionalOnProperty` | Is a config key present and meeting the value rule? | Whether related classes exist, dependent beans are present, or complex config is valid? |
| BeanFactory | `@ConditionalOnBean`, `@ConditionalOnMissingBean` | At evaluation time, does a matching **bean definition** exist or not? | That no bean will be registered later, or that the bean has instantiated successfully? |

**Distinguishing “environment” here:** `Environment` stores properties from YAML, `.properties`, environment variables, launch args, profiles...; `@ConditionalOnWebApplication` inspects **the web application type**. These two meanings are related yet not identical. A project with `spring-webmvc` on the classpath can still launch a `WebApplicationType.NONE` application, and `@ConditionalOnClass` does not turn that context into a Servlet context.

For bean conditions, both `@ConditionalOnBean` and `@ConditionalOnMissingBean` inspect beans that the framework **has already processed**. They do not wait for beans declared in auto-configurations processed later. Spring Boot recommends using them inside auto-configurations, which are loaded after application-declared bean definitions.

## 3. Layering Conditions to Prevent Unwanted Activation and Class-Loading Errors

### 3.1. Placing shared gates on configuration, bean conditions near the bean factory method

A readable design pattern:

```java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
    @ConditionalOnClass(name = "com.example.optional.AuditClient")
    @ConditionalOnProperty(
            prefix = "demo.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    static class ServletAuditConfiguration {

        @Bean
        @ConditionalOnBean(AuditTransport.class)
        @ConditionalOnMissingBean(AuditReporter.class)
        DefaultAuditReporter defaultAuditReporter(AuditTransport transport) {
            return new DefaultAuditReporter(transport);
        }
    }
}
```

**This is a structural illustration snippet**, not a standalone Java file: `AuditTransport`, `AuditReporter`, `DefaultAuditReporter`, and the optional class `com.example.optional.AuditClient` are hypothetical application types. The runnable test example in section 6 declares the corresponding types itself.

Meaning of annotation placement:

- `@ConditionalOnWebApplication(type=SERVLET)` restricts the configuration to a **Servlet web context**. When both MVC and WebFlux are on the classpath, checking the specific web type avoids accidentally activating Servlet config on the wrong branch.
- `@ConditionalOnClass(name=...)` checks that the SDK is present. Use `name` when specifying a class name without forcing the auto-configuration source to reference the optional class directly.
- `@ConditionalOnProperty(... havingValue="true", matchIfMissing=false)` requires the **exact enable flag** under Spring Boot's value comparison; missing or `false` skips bean creation. Do not use `name="enabled"` alone assuming only `true` matches: by default, present strings other than `false` can also match.
- `@ConditionalOnBean(AuditTransport.class)` prevents creating the reporter when the application has no outbound transport yet.
- `@ConditionalOnMissingBean(AuditReporter.class)` backs off for any `AuditReporter` implementation already processed earlier, including user-supplied ones. If you only check `DefaultAuditReporter.class`, an application with `CustomAuditReporter` could still get an extra default reporter created.

**The same condition is not a self-sufficient configuration:** `@ConditionalOnBean` does not create `AuditTransport`; `@ConditionalOnClass` does not add dependencies; `@ConditionalOnWebApplication` does not supply a web server.

### 3.2. Why use a static nested `@Configuration` class inside auto-configuration?

Risky case:

```java
@Bean
@ConditionalOnClass(name = "com.example.optional.AuditClient")
com.example.optional.AuditClient auditClient() {
    return new com.example.optional.AuditClient();
}
```

This snippet **only illustrates a design flaw** (the actual constructor/API of `AuditClient` may differ). The JVM may need to load/inspect the `@Bean` method signature returning a library type **before** the condition placed on the method is applied. If the class is absent from the runtime classpath, the application risks `NoClassDefFoundError` or introspection errors.

Place the classpath check on a **separate configuration class** (usually a static nested `@Configuration`), and put bean methods using optional APIs **inside** that configuration. Spring Boot can inspect class-level annotation metadata before loading dependent components. For conditions on custom meta-annotations you create, the documentation also recommends declaring the class via `name` rather than `value`.

The key is not just “stacking many annotations”; you must isolate optional type references where they are only processed when the class is present.

### 3.3. Do not use component scan to discover auto-configuration

For Spring Boot 3.x starters/libraries, top-level auto-configurations are declared in:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Example file content in a published JAR:

```text
com.example.audit.autoconfigure.AuditAutoConfiguration
```

Spring Boot documentation requires auto-configurations to be loaded via the imports list, not accidentally picked up and activated by regular component scanning. The goal is to control loading timing and relative order with respect to user configurations. In the test below, `AutoConfigurations.of(...)` registers the simulated class directly, so no imports file is needed.

## 4. Truth Table: Any Failing Gate Must Block

Assuming `AuditTransport` and `AuditReporter` are two independent interfaces, the optional SDK is on the classpath unless stated otherwise, and “default reporter” means `DefaultAuditReporter` created by auto-configuration:

| Servlet context | SDK present | `enabled=true` | Has `AuditTransport` | Already has `AuditReporter` | Result |
|---|---|---|---|---|---|
| Yes | Yes | Yes | Yes | No | **Creates** default reporter |
| **No**, running CLI | Yes | Yes | Yes | No | Does not create |
| **No**, running Reactive | Yes | Yes | Yes | No | Does not create with `type=SERVLET` config |
| Yes | **No** | Yes | Yes | No | Does not create |
| Yes | Yes | **Not declared** | Yes | No | Does not create |
| Yes | Yes | **false** | Yes | No | Does not create |
| Yes | Yes | Yes | **No** | No | Does not create |
| Yes | Yes | Yes | Yes | **Yes** | Does not create default; keeps user reporter |

This table represents a **logical AND**. It does not imply Spring Boot evaluates the annotations in exact column order, or that having all SDKs and beans guarantees the app runs cleanly: bean instantiation and runtime logic checks are subsequent steps.

**A common logic mistake:** using `@ConditionalOnBean(AuditTransport.class)` while forgetting `@ConditionalOnMissingBean(AuditReporter.class)`. As a result, even if the user declared a custom reporter, the context may still end up with an extra default reporter. Conversely, if you use only `@ConditionalOnMissingBean` without `@ConditionalOnBean`, a bean method taking an `AuditTransport` parameter can be registered without its dependency; bean creation may then fail.

## 5. Explicit Configuration Conditions to Avoid Accidental Environment Activation

Default `application.yml` example:

```yaml
demo:
  audit:
    enabled: false
```

And in the environment where it should be enabled:

```yaml
demo:
  audit:
    enabled: true
```

To require operators to **explicitly opt in**, declare:

```java
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
```

Do not use `matchIfMissing=true` if the requirement is an off-by-default feature. Also do not check only `@ConditionalOnProperty(name="enabled")` and treat any value other than `false` as business-valid; `havingValue="true"` expresses intent much better.

Actual configuration can come from multiple `PropertySource`s with different precedence. A value in `application.yml` can be overridden by profiles, environment variables, or command-line arguments. Conditions always evaluate the `Environment` the application receives, so checking a single config file is not enough to conclude why it toggled on or off. Write tests for missing flag, `false`, `true`, and unexpected values.

If a real system needs activation by a specific profile, `@Profile("production")` can be an additional condition, provided you understand that **a profile name does not replace** an enable flag, web type, classpath condition, or bean presence. Avoid accidentally attaching `@Profile` to a shared starter that turns itself on at deployment merely because of a common profile name.

## 6. Testable Java 17+ Example Using Spring Boot 3.3

To verify all four condition layers and the application's override rights, put the following **`src/test/java/demo/CombinedAutoConfigurationConditionsTest.java`** file into a project using Spring Boot 3.3, Java 17+, and `spring-boot-starter-test`. Use `WebApplicationContextRunner` to simulate a Servlet context, `ApplicationContextRunner` for non-web, and `FilteredClassLoader` to hide the simulated SDK class.

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CombinedAutoConfigurationConditionsTest {

    // Represents an optional SDK. A nested class still has its own .class file.
    static final class OptionalSdkMarker {
    }

    interface AuditTransport {
        String destination();
    }

    interface AuditReporter {
        String mode();
    }

    static final class DefaultAuditReporter implements AuditReporter {
        private final AuditTransport transport;

        DefaultAuditReporter(AuditTransport transport) {
            this.transport = transport;
        }

        @Override
        public String mode() {
            return "default:" + transport.destination();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TransportConfiguration {
        @Bean
        AuditTransport auditTransport() {
            return () -> "user-transport";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomReporterConfiguration {
        @Bean
        AuditReporter customAuditReporter() {
            return () -> "custom";
        }
    }

    @AutoConfiguration
    static class AuditAutoConfiguration {
        @Configuration(proxyBeanMethods = false)
        @ConditionalOnClass(OptionalSdkMarker.class)
        @ConditionalOnWebApplication(
                type = ConditionalOnWebApplication.Type.SERVLET
        )
        @ConditionalOnProperty(
                prefix = "demo.audit",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = false
        )
        static class ServletAuditConfiguration {

            @Bean
            @ConditionalOnBean(AuditTransport.class)
            @ConditionalOnMissingBean(AuditReporter.class)
            DefaultAuditReporter defaultAuditReporter(
                    AuditTransport transport) {
                return new DefaultAuditReporter(transport);
            }
        }
    }

    private final WebApplicationContextRunner webRunner =
            new WebApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AuditAutoConfiguration.class));

    @Test
    void createsDefaultOnlyWhenAllGatesPass() {
        webRunner
                .withUserConfiguration(TransportConfiguration.class)
                .withPropertyValues("demo.audit.enabled=true")
                .run(context -> {
                    assertTrue(context.containsBean("defaultAuditReporter"));
                    assertEquals(
                            "default:user-transport",
                            context.getBean(AuditReporter.class).mode()
                    );
                });
    }

    @Test
    void missingFlagDoesNotEnableFeature() {
        webRunner
                .withUserConfiguration(TransportConfiguration.class)
                .run(context ->
                        assertFalse(context.containsBean("defaultAuditReporter"))
                );
    }

    @Test
    void falseFlagDoesNotEnableFeature() {
        webRunner
                .withUserConfiguration(TransportConfiguration.class)
                .withPropertyValues("demo.audit.enabled=false")
                .run(context ->
                        assertFalse(context.containsBean("defaultAuditReporter"))
                );
    }

    @Test
    void arbitraryStringIsNotTrue() {
        webRunner
                .withUserConfiguration(TransportConfiguration.class)
                .withPropertyValues("demo.audit.enabled=enabled")
                .run(context ->
                        assertFalse(context.containsBean("defaultAuditReporter"))
                );
    }

    @Test
    void noTransportMeansNoReporter() {
        webRunner
                .withPropertyValues("demo.audit.enabled=true")
                .run(context ->
                        assertFalse(context.containsBean("defaultAuditReporter"))
                );
    }

    @Test
    void customReporterMakesDefaultBackOff() {
        webRunner
                .withUserConfiguration(
                        TransportConfiguration.class,
                        CustomReporterConfiguration.class
                )
                .withPropertyValues("demo.audit.enabled=true")
                .run(context -> {
                    assertFalse(context.containsBean("defaultAuditReporter"));
                    assertTrue(context.containsBean("customAuditReporter"));
                    assertEquals(
                            "custom",
                            context.getBean(AuditReporter.class).mode()
                    );
                });
    }

    @Test
    void missingOptionalSdkDoesNotActivateAutoConfiguration() {
        webRunner
                .withUserConfiguration(TransportConfiguration.class)
                .withPropertyValues("demo.audit.enabled=true")
                .withClassLoader(new FilteredClassLoader(OptionalSdkMarker.class))
                .run(context ->
                        assertFalse(context.containsBean("defaultAuditReporter"))
                );
    }

    @Test
    void nonWebContextDoesNotActivateServletConfiguration() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(AuditAutoConfiguration.class)
                )
                .withUserConfiguration(TransportConfiguration.class)
                .withPropertyValues("demo.audit.enabled=true")
                .run(context ->
                        assertFalse(context.containsBean("defaultAuditReporter"))
                );
    }
}
```

### Why is this test meaningful?

- The first test satisfies **all** conditions and verifies `AuditReporter#mode()` actually uses the user-supplied `AuditTransport`.
- Three property tests distinguish **missing flag**, `false`, and an arbitrary string. They prevent unintended activation.
- The test without `AuditTransport` demonstrates the dependent bean check; having the SDK class and the flag is still not enough.
- The custom reporter test confirms **back-off** accurately against the **`AuditReporter` interface** and that the application-provided bean continues to be used.
- `FilteredClassLoader(OptionalSdkMarker.class)` simulates an absent SDK. The marker is a minimal test-only type to avoid external library dependencies.
- `ApplicationContextRunner` creates a **non-web context** even though the test class still has Spring Web libraries on the test classpath; accurate for testing environment conditions. `WebApplicationContextRunner` simulates a Servlet web context and does not require starting a real server.

### Dependencies and how to run

The test project needs Boot 3.3-compatible dependencies. Gradle Groovy DSL example, with the Spring Boot plugin/version already configured beforehand:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

From the project root directory:

```bash
./gradlew test --tests demo.CombinedAutoConfigurationConditionsTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.CombinedAutoConfigurationConditionsTest
```

**Expected:** all **8 tests pass**. The first test creates `defaultAuditReporter`; the remaining seven verify that each missing gate or user override prevents the default bean from appearing. This is the result **inferred from the code and Spring Boot 3.3 APIs**, not the log of an actual run. If the project applies additional dependencies/auto-configurations, check that project's actual test report.

## 7. Bean and Auto-Configuration Ordering: An Important Gate Often Forgotten

Both `@ConditionalOnBean` and `@ConditionalOnMissingBean` rely on bean definitions **already processed when the condition is evaluated**. Distinguish three kinds of ordering:

1. **User bean sources and auto-configuration:** Spring Boot is designed so user bean definitions are processed before auto-configurations. Therefore back-off conditions based on user beans work properly when placed in auto-configuration.
2. **Ordering across multiple auto-configurations:** if the reporter depends on an `AuditTransport` bean created by **another auto-configuration**, ensure the transport configuration is processed before the reporter. You can declare `@AutoConfiguration(after = TransportAutoConfiguration.class)` or `afterName` when avoiding direct references. Do not assume filename order or line order in `AutoConfiguration.imports` is a reliable solution.
3. **Object instantiation order:** auto-configuration `after`/`before` affects **bean definition registration order**, not directly guaranteeing object A is instantiated before object B. Instantiation still depends on bean injection and Spring's dependency mechanism.

Example guiding ordering between two auto-configurations (hypothetical class names):

```java
@AutoConfiguration(afterName =
        "com.example.transport.autoconfigure.TransportAutoConfiguration")
public class AuditAutoConfiguration {
    // Dedicated conditional configuration classes...
}
```

This is an **illustrative configuration snippet**, not a runnable file. This ordering is only needed if the reporter actually needs to detect an `AuditTransport` created by another auto-configuration. In the test example, `TransportConfiguration` is a user configuration registered beforehand, so `afterName` is unnecessary.

**Do not use:** arbitrarily placing `@ConditionalOnBean` on a user `@Configuration` and expecting it to always see unprocessed beans. Check the evaluation timing, or reorganize the condition into the proper auto-configuration.

## 8. Common Pitfalls and Fixes

### 8.1. Confusing classpath with beans

Having the `OptionalSdkMarker` class at runtime does not prove an `AuditTransport` bean exists. `@ConditionalOnClass` only checks classes. When a bean is needed, add `@ConditionalOnBean`; when avoiding duplicates, add `@ConditionalOnMissingBean`. If the dependent bean might live in a parent context, consider the bean condition's `search` attribute and clearly define the search scope.

### 8.2. Using `@ConditionalOnWebApplication` alone

This annotation checks the **context type**, without knowing whether the user wants the audit feature enabled. If production should not enable the feature by default, add an explicit flag in `Environment` and test the undeclared case. In particular, when both MVC and WebFlux dependencies are present, `type = SERVLET` or `type = REACTIVE` expresses intent more strictly than `ANY`.

### 8.3. Putting an optional class directly into a `@Bean` method's return type

A `@ConditionalOnClass` condition attached on **that method itself** may arrive too late to keep the JVM from loading the method signature. Isolate the method inside a `@Configuration` class with `@ConditionalOnClass` at the **class level**. Prefer `name` when writing meta-annotations or avoid referencing optional classes directly.

### 8.4. Using `@ConditionalOnMissingBean` with the wrong type

If there is an `AuditReporter` interface while the default bean returns `DefaultAuditReporter`, placing `@ConditionalOnMissingBean` without specifying a target may only check the method's **return type**. When wanting to respect all implementors, declare `@ConditionalOnMissingBean(AuditReporter.class)`. At the same time, keep the method signature's return type as specific as possible so Spring identifies the exact bean type.

### 8.5. Enabling by default when config is absent

`@ConditionalOnProperty(matchIfMissing = true)` makes a missing property still match. That is suitable behavior for some on-by-default features, yet contradicts an **opt-in** requirement. For features with side effects (writing audits, calling external services, initializing clients...), decide the default explicitly and use `havingValue="true", matchIfMissing=false` if you want it enabled only with user consent.

### 8.6. Referencing beans in SpEL expressions

`@ConditionalOnExpression` can evaluate SpEL expressions, yet directly referencing a bean inside an expression risks **instantiating the bean prematurely**, before it has passed through all post-processing and binding steps. For bean existence checks, use `@ConditionalOnBean`/`@ConditionalOnMissingBean`; for property values, use `@ConditionalOnProperty`. Avoid combining too much logic into a single hard-to-test expression.

### 8.7. Thinking changing properties at runtime automatically creates beans

The conditions above are evaluated during context construction, mainly when registering bean definitions. Changing environment variables or config files after the context has started **does not automatically** re-run all conditions to add or remove beans. If live toggling is needed, design a separate runtime mechanism; auto-configuration annotations solve **startup decisions**.

### 8.8. Assuming “right classpath” guarantees successful startup

Once conditions match, a bean can still fail during initialization due to invalid config, unresponsive external services, or dependency errors. Conditional annotations only decide **whether to register**, not replacing config validation, error handling, and integration tests.

## 9. Diagnosing When Beans Appear or Disappear Unexpectedly

Follow these questions in order:

1. **Environment:** what is the final value of `demo.audit.enabled`? Is any profile, environment variable, or CLI argument overriding it?
2. **Context type:** is the application actually Servlet, Reactive, or non-web? Do not conclude from finding MVC classes on the classpath.
3. **Classpath:** is the required SDK class on the runtime classpath? Was it declared `compileOnly` or stripped from dependencies during packaging?
4. **Bean definitions:** when the condition runs, is `AuditTransport` registered yet? Is the user's `AuditReporter` present yet? Is it searching current or parent contexts as well?
5. **Ordering:** if beans come from multiple auto-configurations, are `after`/`afterName` sufficient for the reporter's condition to see the related bean definition?
6. **Signatures and class loading:** does another `@Bean` method or class directly reference the optional type before the class-level guard is evaluated?
7. **Actual outcome:** does the bean definition exist yet fail instantiation, or did the condition truly not match?

Spring Boot provides the **Condition Evaluation Report**. On application startup, you can use `--debug` to view the condition report in logs; when Actuator is installed and configured, `/actuator/conditions` can also help inspect positive/negative matches. In tests, you can print the report via an initializer:

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
        )
        .withConfiguration(AutoConfigurations.of(AuditAutoConfiguration.class))
        .run(context -> {
            // Inspect conditions inside a real test.
        });
```

This snippet is a **diagnostic template**, which must be placed in a file importing `ConditionEvaluationReportLoggingListener`, `LogLevel`, and the other classes. Do not use it to replace assertions: the report tells **why** something matched, whereas tests verify **which beans were created**.

A test matrix should cover at least: all conditions met; each gate missing; `false`/missing flag; user override; non-web and, if the product supports it, Reactive; SDK class absent. For real integration, add a case where a second auto-configuration registers the dependency and verify ordering.

## 10. Design Principles to Remember

- Treat **environment, classpath, bean, and property** as independent gates. If all must be satisfied simultaneously, write multiple conditions explicitly to express AND.
- **Merely having a library does not mean enabling the feature**; merely having a bean does not mean enabling it against user intent.
- Use an explicit opt-in flag when a feature has side effects, along with `havingValue="true"` and `matchIfMissing=false`.
- Place `@ConditionalOnClass` on a **separate configuration class** when the code inside uses optional classes; avoid `@Bean` signatures that trigger early class loading.
- Use `@ConditionalOnBean` for mandatory dependencies and `@ConditionalOnMissingBean` on the **right abstraction type** to back off.
- Keep bean conditions inside auto-configuration and specify ordering if depending on beans from another auto-configuration.
- Test a **matrix of negative cases** to prove beans do not activate unexpectedly, rather than testing only a single positive case.
- Condition reports help diagnose **why** something matched; integration tests and runtime checks verify **the system works properly**.

### Official References

- Spring Boot 3.3 Reference, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 Javadoc, `ConditionalOnClass`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3 Javadoc, `ConditionalOnBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot 3.3 Javadoc, `ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.3 Javadoc, `ConditionalOnProperty`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.3 Javadoc, `ConditionalOnWebApplication`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html
