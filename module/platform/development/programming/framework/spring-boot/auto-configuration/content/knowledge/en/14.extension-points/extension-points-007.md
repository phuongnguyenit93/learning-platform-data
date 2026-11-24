# Separating core configuration from optional integrations using multiple auto-configuration classes

## Learning objectives

A Spring Boot library may provide core functionality used by every application, while also supporting integrations that only some applications need: a vendor SDK, cloud client, broker, database driver, or a specific web framework. If everything is placed in a single auto-configuration class, that class easily ends up depending on the optional libraries. When an application does not install an SDK, startup can fail with `NoClassDefFoundError` even though the user never enabled the integration feature.

This lesson demonstrates how to split into **multiple auto-configuration classes along functional and dependency boundaries**. The core configuration only knows about the core API; each optional integration has its own configuration guarded by a classpath condition. As a result, applications can use the core functionality without pulling in every partner library.

After this lesson, you will be able to:

- Design boundaries between the core API, core auto-configuration, and optional integrations.
- Split a large auto-configuration into smaller classes with clear conditions.
- Use `@ConditionalOnClass` in the right place to avoid loading types absent from the runtime classpath.
- Register multiple auto-configurations via `AutoConfiguration.imports`.
- Coordinate configuration ordering, `@ConditionalOnBean`, and `@ConditionalOnMissingBean`.
- Test scenarios: core only, optional SDK present, SDK present without a client bean, and user overrides.

## 1. Problem: one library, multiple integration levels

Suppose the `acme-notification` library provides a notification API. Every application may need the core API, whereas only some applications use a Vendor's SMS SDK.

If everything is bundled into one class:

~~~java
@AutoConfiguration
class NotificationAutoConfiguration {

    @Bean
    NotificationRegistry notificationRegistry() {
        return new DefaultNotificationRegistry();
    }

    @Bean
    SmsSender smsSender(com.vendor.sms.SmsClient client) {
        return new VendorSmsSender(client);
    }
}
~~~

An application using only the core part still has to resolve the `com.vendor.sms.SmsClient` type appearing in the method signature. If the SDK is not on the runtime classpath, the JVM or configuration processing can fail before the user even gets a chance to use the core functionality.

A `@ConditionalOnClass` placed **only on the `@Bean` method** is not always sufficient protection. Before the method-level condition is evaluated, the JVM may already load the method's return type or parameter types. That is why Spring Boot recommends isolating references to optional classes inside a separate configuration class with a class-level condition.

A cleaner design:

~~~text
Spring Boot Application
       |
       +---- Core Auto-configuration
       |       |
       |       +---- Core API / Core beans
       |
       +---- Optional Vendor Auto-configuration
               |
               +---- Evaluated only when Vendor SDK is present
                       |
                       +---- Vendor client / adapter
~~~

Core and optional integrations can be packaged in the same artifact or in separate artifacts/modules. Either way, **dependency boundaries in source code** must remain clear.

## 2. Dividing responsibilities into layers

A library design can have the following parts:

| Component | Responsibility | Expected dependencies |
| --- | --- | --- |
| Core API | Shared interfaces, models, exceptions, and contracts | Required Java/Jakarta APIs |
| Core implementation | Default implementation without partner SDKs | Core API |
| Core auto-configuration | Registers core beans | Spring Boot and core implementation |
| Optional integration API/adapter | Adapts between the core API and the vendor API | Core API + corresponding SDK |
| Optional auto-configuration | Only registers the adapter when matching SDK/client is present | Core API + optional SDK + Spring Boot |
| Optional starter | Aggregates dependencies so applications can easily enable the integration | Core starter + selected optional integration |

Example module structure:

~~~text
acme-notification/
  acme-notification-api/
    NotificationRegistry.java
    SmsSender.java

  acme-notification-autoconfigure/
    CoreNotificationAutoConfiguration.java
    META-INF/spring/
      org.springframework.boot.autoconfigure.AutoConfiguration.imports

  acme-notification-vendor-sms/
    VendorSmsAutoConfiguration.java
    VendorSmsSender.java
    META-INF/spring/
      org.springframework.boot.autoconfigure.AutoConfiguration.imports

  acme-notification-spring-boot-starter/
    build.gradle
~~~

This is an illustrative layout; artifact names and module count depend on scale. You do not have to create one module per class. Only split when dependency boundaries, lifecycles, or feature ownership genuinely differ.

**Key takeaway:** the core module does not import, extend, or expose Vendor SDK types in its method signatures. Optional integration modules may depend on the core API and the required SDK.

## 3. Core auto-configuration: use only core types

Example library API:

~~~java
package example.notification;

public interface NotificationRegistry {
    String implementation();
}
~~~

Core auto-configuration:

~~~java
package example.notification.autoconfigure;

import example.notification.NotificationRegistry;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class CoreNotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationRegistry.class)
    NotificationRegistry notificationRegistry() {
        return () -> "core-default";
    }
}
~~~

This is a **complete production Java file** once the corresponding package/file is created and Spring Boot dependencies are present. The core configuration only registers a default implementation. Users can supply their own `NotificationRegistry`; `@ConditionalOnMissingBean` lets the default configuration back off.

There is no reference to `com.vendor.sms.SmsClient`. Therefore, this class can still be loaded and applied when the SMS SDK is completely absent.

### Why keep the core API independent of the SDK?

If the core interface declares a parameter of type `SmsClient`, then every user of the core API must also have the SDK. The boundary is broken right at the API layer.

Keep the core contract using library-owned types:

~~~java
public interface NotificationSender {
    SendResult send(NotificationMessage message);
}
~~~

The optional adapter can accept the Vendor SDK type inside its implementation without letting that type leak into the core API. That allows applications to switch to a different integration without modifying core code.

## 4. Optional auto-configuration: class-level condition guards dependencies

Suppose the Vendor SDK provides:

- `com.vendor.sms.SmsClient`: the client provided by the SDK.
- `com.vendor.sms.autoconfigure.SmsClientAutoConfiguration`: the SDK's auto-configuration registering the client bean.

The library's optional auto-configuration:

~~~java
package example.notification.vendor;

import com.vendor.sms.SmsClient;
import example.notification.NotificationRegistry;
import example.notification.SmsSender;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(
        afterName = "com.vendor.sms.autoconfigure.SmsClientAutoConfiguration"
)
@ConditionalOnClass(name = "com.vendor.sms.SmsClient")
public class VendorSmsAutoConfiguration {

    @Bean
    @ConditionalOnBean(type = "com.vendor.sms.SmsClient")
    @ConditionalOnMissingBean(SmsSender.class)
    SmsSender vendorSmsSender(
            SmsClient client,
            NotificationRegistry registry) {
        return new VendorSmsSender(client, registry);
    }
}
~~~

This is an **illustrative production snippet**; `SmsSender` and `VendorSmsSender` are API/adapter types owned by the library, while `SmsClient` is from the Vendor SDK. The SDK dependency is required on the **integration module's compile classpath** to compile this code.

The three conditions serve distinct roles:

1. `@ConditionalOnClass(name = "com.vendor.sms.SmsClient")` at the **class** level guards the entire configuration if the SDK is missing from the runtime classpath.
2. `@ConditionalOnBean(type = "com.vendor.sms.SmsClient")` requires the client bean to actually exist in the context; having the SDK on the classpath does not guarantee a client bean was created.
3. `@ConditionalOnMissingBean(SmsSender.class)` allows the application to supply its own `SmsSender` and replace the default adapter.

`afterName` orders the integration configuration after the SDK's auto-configuration. The fully qualified name is given as a string so **declaring the order** does not require importing the SDK's auto-configuration class. It does not register the SDK configuration or create `SmsClient` on its own; the SDK must be included in the application and its configuration must be selected.

### Can you use `value = SmsClient.class`?

If the integration module already has the SDK on its compile classpath, the class-level condition can also be written as:

~~~java
@ConditionalOnClass(SmsClient.class)
~~~

The `name = "..."` form is useful when expressing the condition by name and avoiding another class literal in annotation metadata. However, if the `@Bean` signature still uses `SmsClient`, the integration module must still compile against the SDK. Using `name` **does not remove the compile-time dependency from a Java file that directly references that type**.

## 5. Why is a class-level condition safer than a method-level condition?

Consider an unsafe example when the SDK might be absent:

~~~java
@AutoConfiguration
class VendorSmsAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.vendor.sms.SmsClient")
    SmsSender smsSender(com.vendor.sms.SmsClient client) {
        return new VendorSmsSender(client);
    }
}
~~~

The condition is on the method, but to process method metadata, the JVM may need to resolve the `SmsClient` type in the parameter or return type before the condition is evaluated. When the SDK is absent, the guard can come too late.

The fix is to move the condition to a **separate configuration class**:

~~~java
@AutoConfiguration
class NotificationAutoConfiguration {

    // Core beans do not reference the optional SDK.

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sms.SmsClient")
    static class VendorSmsConfiguration {

        @Bean
        SmsSender smsSender(com.vendor.sms.SmsClient client) {
            return new VendorSmsSender(client);
        }
    }
}
~~~

Spring Boot reads configuration metadata and class-level conditions before loading the optional configuration part. Nested configurations must be `static` so they do not require an instance of the enclosing class.

In larger projects, a **separate top-level auto-configuration class** is usually easier to organize, test, and distribute. Nested configurations are useful when the integration is small and clearly owned by the parent configuration.

**Practical rule:** when a class or method signature contains a type that might not exist, place the classpath condition at the level of a configuration class that can be skipped entirely. Do not rely on a method-level condition to shield an absent return type or parameter type.

## 6. Two packaging approaches: same artifact or separate artifacts?

### Same auto-configuration artifact

You can put both core config and optional config in one artifact:

~~~text
acme-notification-autoconfigure/
  CoreNotificationAutoConfiguration.java
  VendorSmsAutoConfiguration.java
  AutoConfiguration.imports
~~~

The artifact is compiled with the dependencies needed to build the integration part. At runtime, if an application does not include the Vendor SDK on the classpath, the class-level condition excludes the optional configuration; core config still works.

This fits when:
- Integrations are small and released in lockstep with core.
- Compile-time knowledge of the SDK in that module is acceptable.
- Users only need to choose whether to add the SDK at runtime.

### Separate optional module/artifact

If you need to **isolate dependencies at the build graph level**, split the integration into a separate artifact:

~~~text
acme-notification-autoconfigure
    -> acme-notification-api
    -> spring-boot-autoconfigure

acme-notification-vendor-sms
    -> acme-notification-api
    -> vendor-sms-sdk
    -> spring-boot-autoconfigure
~~~

Applications using only core do not add `acme-notification-vendor-sms`. Applications wanting the SMS integration add that artifact and the corresponding SDK.

This helps when:
- The SDK is large or has its own license/versioning.
- Another team owns the integration.
- You do not want the core module build to depend on the SDK.
- Independent release/versioning of the integration is needed.

If the integration artifact is added yet the SDK is excluded from the runtime classpath, `@ConditionalOnClass` still protects the optional configuration. If the integration artifact is not added at all, its auto-configuration is not even a candidate.

**Note:** dependency scopes and publishing setup (Gradle/Maven) must be configured properly. A dependency present only on the integration module's compile classpath does not automatically guarantee it is packaged or provided at runtime to applications; inspect the actual dependency graph and runtime classpath of the starter.

## 7. Registering multiple auto-configurations via AutoConfiguration.imports

Spring Boot 3.x discovers a library's auto-configurations via the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

If core and optional config live in the same artifact, the file can list:

~~~text
example.notification.autoconfigure.CoreNotificationAutoConfiguration
example.notification.vendor.VendorSmsAutoConfiguration
~~~

Each line is the fully qualified name of an auto-configuration. Spring Boot evaluates classpath conditions to decide which configurations apply.

If split into two artifacts:
- The imports file in the core artifact lists only `CoreNotificationAutoConfiguration`.
- The imports file in the integration artifact lists `VendorSmsAutoConfiguration`.

Core config does not need `@Import(VendorSmsAutoConfiguration.class)`. Direct importing creates coupling between the two classes and defeats the benefit of independent boundaries. Each artifact publishes its own auto-configurations through the standard resource.

**Do not component-scan the auto-configuration package** to find these classes. Register them via the imports file; use `@Import` intentionally for specific supporting configurations, not to replace auto-configuration discovery.

When building an uber/fat JAR where multiple dependencies contain imports resources at the same path, make sure the packaging tool **merges resource contents** instead of overwriting another artifact's file. If overwritten, a library's auto-configurations can vanish even though the classes remain in the JAR.

## 8. Coordinating ordering and bean conditions

Three kinds of conditions often appear together while answering three different questions:

| Annotation | Question |
| --- | --- |
| `@ConditionalOnClass` | Is the required type/API on the classpath? |
| `@ConditionalOnBean` | Has the required bean already been registered in the context? |
| `@ConditionalOnMissingBean` | Is a suitable replacement bean already absent? |

Auto-configuration ordering can be necessary if optional config depends on a bean registered by the SDK's auto-configuration. For example:

~~~java
@AutoConfiguration(
    afterName = "com.vendor.sms.autoconfigure.SmsClientAutoConfiguration"
)
@ConditionalOnClass(name = "com.vendor.sms.SmsClient")
class VendorSmsAutoConfiguration {
}
~~~

`afterName` only orders the auto-configuration if the SDK configuration is selected as a candidate. It does not add the SDK or guarantee that the client bean exists. Hence `@ConditionalOnBean(type = "com.vendor.sms.SmsClient")` may still be needed on the bean method.

When an optional integration needs a core bean, you can write:

~~~java
@AutoConfiguration(after = CoreNotificationAutoConfiguration.class)
class VendorSmsAutoConfiguration {
}
~~~

This expresses that core auto-configuration is applied before the integration. Application order affects **bean definition registration order**, not the constructor invocation order of bean instances. Spring creates beans according to the dependency graph; if one bean needs another, declare the dependency as a constructor/method parameter.

## 9. Verification example: core runs when SDK is missing, integration activates only when conditions are met

The following test simulates an optional SDK with `OptionalSmsClient`. `FilteredClassLoader` tests the case where the SDK class is absent from the application context's classpath.

**File:** `src/test/java/example/notification/OptionalIntegrationAutoConfigurationTest.java`

~~~java
package example.notification;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class OptionalIntegrationAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            CoreAutoConfiguration.class,
                            OptionalSmsAutoConfiguration.class));

    @Test
    void coreWorksWhenOptionalSdkIsMissing() {
        runner.withClassLoader(new FilteredClassLoader(OptionalSmsClient.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(NotificationRegistry.class);
                    assertThat(context).doesNotHaveBean(SmsSender.class);
                    assertThat(context.getBean(NotificationRegistry.class).name())
                            .isEqualTo("core");
                });
    }

    @Test
    void optionalIntegrationLoadsWhenSdkAndClientBeanExist() {
        runner.withUserConfiguration(OptionalSdkConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(NotificationRegistry.class);
                    assertThat(context).hasSingleBean(SmsSender.class);
                    assertThat(context.getBean(SmsSender.class).provider())
                            .isEqualTo("vendor");
                });
    }

    @Test
    void sdkClassAloneDoesNotCreateIntegrationWithoutClientBean() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(NotificationRegistry.class);
            assertThat(context).doesNotHaveBean(SmsSender.class);
        });
    }

    @Test
    void userImplementationOverridesOptionalAdapter() {
        runner.withUserConfiguration(
                        OptionalSdkConfiguration.class,
                        CustomSmsSenderConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(SmsSender.class);
                    assertThat(context.getBean(SmsSender.class).provider())
                            .isEqualTo("custom");
                });
    }

    interface NotificationRegistry {
        String name();
    }

    interface SmsSender {
        String provider();
    }

    // Represents the SDK type; in production this type comes from the vendor artifact.
    static class OptionalSmsClient {
        String provider() {
            return "vendor";
        }
    }

    @AutoConfiguration
    static class CoreAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(NotificationRegistry.class)
        NotificationRegistry notificationRegistry() {
            return () -> "core";
        }
    }

    @AutoConfiguration(after = CoreAutoConfiguration.class)
    @ConditionalOnClass(OptionalSmsClient.class)
    static class OptionalSmsAutoConfiguration {

        @Bean
        @ConditionalOnBean(OptionalSmsClient.class)
        @ConditionalOnMissingBean(SmsSender.class)
        SmsSender vendorSmsSender(
                OptionalSmsClient client,
                NotificationRegistry registry) {
            return () -> client.provider();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class OptionalSdkConfiguration {

        @Bean
        OptionalSmsClient optionalSmsClient() {
            return new OptionalSmsClient();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomSmsSenderConfiguration {

        @Bean
        SmsSender customSmsSender() {
            return () -> "custom";
        }
    }
}
~~~

In the test harness, configurations are nested inside one class to keep the example compact. In production, use top-level classes and separate packages as described in the architecture section. `OptionalSmsClient` in the test is a simulated class; it is not a real SDK.

### Dependencies and run commands

The test project needs Java 17+ and Spring Boot 3.3.x. With Gradle Groovy DSL (version managed by the Spring Boot plugin/BOM):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run the test in the module containing the file:

~~~bash
# Linux/macOS
./gradlew test --tests "example.notification.OptionalIntegrationAutoConfigurationTest"

# Windows
gradlew.bat test --tests "example.notification.OptionalIntegrationAutoConfigurationTest"
~~~

**Expected result:** four tests PASS.

| Test | Result to verify |
| --- | --- |
| `coreWorksWhenOptionalSdkIsMissing` | Core bean exists, `SmsSender` does not exist |
| `optionalIntegrationLoadsWhenSdkAndClientBeanExist` | Both core and optional integration exist |
| `sdkClassAloneDoesNotCreateIntegrationWithoutClientBean` | SDK class is present without a client bean, integration is not registered |
| `userImplementationOverridesOptionalAdapter` | Application-declared bean wins over the default adapter |

The tests use assertions and do not call `System.out.println`, so there is no fixed application stdout. Console output depends on Gradle/JUnit logging settings. These are the expected results based on the code; run the command in a real project to verify your specific build, version, and classpath.

## 10. Common mistakes when splitting configurations

1. **Core class still references the optional SDK in a method signature.** Even with a classpath condition elsewhere, the JVM may resolve types upfront. Move the method to a separate optional configuration.
2. **Putting `@ConditionalOnClass` only on a `@Bean` method with an optional return type.** The condition may be evaluated too late; place it at the class level of a separate configuration.
3. **Using `@ConditionalOnClass` but forgetting the SDK client bean.** Having the SDK on the classpath does not mean a client bean exists; consider `@ConditionalOnBean` or explicitly depending on the auto-configuration providing the client.
4. **Optional config imported directly from core config.** That creates hard coupling; publish each auto-configuration via `AutoConfiguration.imports`.
5. **Splitting classes without splitting the dependency graph.** If the core module still declares `implementation vendor-sdk`, core applications may still receive the SDK transitively. Put the dependency in the integration module.
6. **Putting optional APIs inside core interfaces.** Then every core consumer must know about the SDK. Keep APIs neutral and write adapters in the integration module.
7. **Confusing `@ConditionalOnClass` with `@ConditionalOnBean`.** Classpath presence and bean registration are two distinct conditions.
8. **Assuming `after = CoreAutoConfiguration.class` creates core beans.** Ordering does not create beans; the core class must be selected and its conditions must match.
9. **Using component scan to discover all configurations.** Auto-configurations must be registered via the imports file; do not broaden component scanning across the entire library package.
10. **Imports resource overwritten during packaging.** Inspect the resource contents in the final JAR, especially when building fat JARs or shading multiple dependencies.
11. **Not testing all four states.** Only testing "SDK present" does not prove core works when the SDK is missing, the client bean is absent, or the user overrides it.
12. **Creating too many tiny classes without real boundaries.** Split only along dependency/lifecycle/ownership lines; do not turn every single bean into its own auto-configuration.

## 11. Diagnosing when an application still fails with the SDK absent

If a user adds only the core starter yet hits `NoClassDefFoundError`, check in order:

1. Identify the missing class in the stack trace.
2. Search for that class in fields, superclasses, interfaces, annotations, return types, and parameter types of the core auto-configuration.
3. Verify the class-level condition sits on **the exact class containing all optional references**.
4. Check whether the optional config is directly imported by core config or picked up by component scan.
5. Inspect the dependency tree to see if the SDK is pulled in by the core artifact or another starter.
6. Enable `--debug` to inspect the Condition Evaluation Report; check `OnClassCondition` and why configurations were excluded or selected.
7. Inspect the `AutoConfiguration.imports` file inside the published JAR, not only in the source tree.

To verify classpath conditions, write tests using `FilteredClassLoader` as shown in the example. Such tests are valuable because they genuinely make the class invisible through the application context's classloader.

## 12. Inspecting the artifact after building

When releasing a library, inspect the **actual JAR**:

~~~bash
# List auto-configuration imports in the artifact
jar tf build/libs/acme-notification-autoconfigure.jar

# Inspect the imports file contents (depending on environment, you may extract the JAR first)
jar xf build/libs/acme-notification-autoconfigure.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

On Windows you can also use PowerShell `jar tf ...` and `jar xf ...` if the JDK is in `PATH`. After extracting, open the imports file to verify core/optional classes are listed as designed.

For a separate integration artifact, confirm:
- The integration JAR contains the optional auto-configuration.
- The core JAR contains no direct references to the optional SDK.
- The core dependency graph does not pull in the Vendor SDK when the user does not choose the integration.
- Imports resources from all artifacts are merged properly when building the final application.
- A smoke test booting the context with a core-only classpath still succeeds.

You do not need to start external systems to verify classpath conditions; use small context tests first, then add integration tests with the real SDK as needed.

## 13. Self-check questions

**Question 1.** Core auto-configuration has a method accepting `com.vendor.sdk.Client`. Is placing `@ConditionalOnClass(name="com.vendor.sdk.Client")` on that method safe enough when the SDK might be missing?

**Answer:** You should not rely on that. The JVM may need to resolve the method signature before the method-level condition is applied. Move the method into a separate configuration with a class-level condition.

**Question 2.** The SDK is on the classpath, but no client bean exists yet. Does `@ConditionalOnClass` guarantee the adapter will be created?

**Answer:** No. It only checks the classpath. An actual client bean is needed; use `@ConditionalOnBean` or an explicit required dependency.

**Question 3.** If core config has `@Import(VendorSmsAutoConfiguration.class)`, has splitting into multiple classes eliminated the dependency?

**Answer:** Not necessarily. Core still directly references the optional class. Let each auto-configuration be registered independently via `AutoConfiguration.imports`.

**Question 4.** Should `SmsClient` be placed in the core `SmsSender` interface?

**Answer:** No, if you want core to stay independent of the SDK. Keep the contract neutral; only implementations in the integration module should know vendor types.

**Question 5.** When the SDK is absent, what must keep working?

**Answer:** Core beans that do not reference the SDK must be registered and the context must start normally; the optional adapter must not be created.

## 14. Takeaways when designing a library

Split auto-configurations along **dependency boundaries**:

- Core auto-configuration only references core APIs and implementations.
- Each optional integration has its own configuration, guarded by `@ConditionalOnClass` at the **class level**.
- If a class is on the classpath yet a client bean might not be created, use `@ConditionalOnBean` to check for the bean.
- Use `@ConditionalOnMissingBean` so applications can replace the default adapter.
- Use `@AutoConfiguration(after = ...)` or `afterName = ...` when definition registration order is genuinely needed.
- Register each auto-configuration via `AutoConfiguration.imports`; do not let core hard-import optional classes.
- When build-graph dependency isolation is needed, split into separate artifacts/modules. Classpath conditions remain useful when the SDK may be absent at runtime.

A well-designed library lets users add only what they need. Module boundaries, neutral API types, and class-level conditions help keep the core independent as optional integrations change or are omitted.

### Official Spring Boot documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration: Class Conditions and Bean Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 Javadoc — @ConditionalOnClass](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Spring Boot 3.3 Javadoc — @AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3 Javadoc — @ConditionalOnBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html)
- [Spring Boot 3.3 Javadoc — @ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
