# Designing for Missing Dependencies or User-Disabled Features

## 1. Goal: A Library Must Behave Gracefully When a Feature Is Unavailable

A Spring Boot library may integrate a vendor SDK, mail client, image processor, cloud adapter, or search module. Not every application needs these features. Some applications omit the corresponding dependency from the classpath; others include the dependency but intentionally disable the feature in a specific environment.

A well-designed auto-configuration must handle both cases:

1. **Optional dependency absent:** Spring Boot does not attempt to load classes that exist only in that SDK, does not fail the application with `NoClassDefFoundError`/`ClassNotFoundException`, and does not create the feature's beans.
2. **User disables the feature:** even when the SDK is present, the property condition prevents the feature configuration from applying; optional beans are not registered.
3. **Application provides a replacement bean:** if the library exposes an appropriate extension point, auto-configuration backs off via `@ConditionalOnMissingBean`.
4. **The rest of the application still starts:** code consuming the optional feature must not require injecting a bean that might be absent.

This lesson focuses on designing auto-configuration for an integration with an optional SDK. Examples use the `acme.catalog` namespace and the SDK class `demo.catalog.sdk.CatalogClient`. Illustrative types are defined inside the demo project; in a real library, `CatalogClient` comes from an external dependency.

After this lesson, you will be able to place classpath and property conditions properly, isolate references to optional classes, choose intentional opt-in/opt-out defaults, test a missing-dependency classpath with `FilteredClassLoader`, and let applications replace beans themselves.

## 2. Two Independent Questions: Is the Dependency Present, and Is the Feature Enabled?

Do not merge these two questions into one:

- **Classpath condition:** does the application have the required classes for the integration?
- **Feature condition:** does the application allow the feature to run in this environment?

Condition model:

```text
Is Catalog SDK on the classpath?
         |
       No  +------> Do not register integration
         |
        Yes
         |
Does acme.catalog.enabled allow it?
         |
       No  +------> Do not register integration
         |
        Yes
         |
Check for application replacement beans
         |
Register default beans if no matching bean exists
```

The classpath and property conditions combine with **AND**: the dependency must exist **and** the feature flag must allow it for the configuration branch to apply. Next, `@ConditionalOnMissingBean` decides whether the library needs to create a default implementation or yield to the application.

| SDK on classpath | `acme.catalog.enabled` | Desired outcome |
|---|---|---|
| No | Missing | No integration bean created; application still runs |
| No | `true` | Still no bean created; enabling the flag cannot replace a missing dependency |
| No | `false` | No bean created |
| Yes | Missing | Depends on the chosen default policy |
| Yes | `true` | Eligible to register default beans |
| Yes | `false` | Do not register integration branch |
| Yes | `true` and user already supplied service bean | Auto-configuration yields to the user bean |

**Properties do not install dependencies.** Setting `acme.catalog.enabled=true` cannot make the `CatalogClient` class appear on the classpath. Conversely, merely adding the SDK in Maven/Gradle does not force an application to turn the feature on.

## 3. `@ConditionalOnClass`: Register the Integration Only When the Dependency Exists

Spring Boot provides `@ConditionalOnClass` to check whether a class can be loaded from the classpath.

Example:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "demo.catalog.sdk.CatalogClient")
class CatalogSdkConfiguration {
    // Beans requiring CatalogClient are placed in this class
}
```

You can use the `value` attribute with a class reference when the dependency is always available at compile time:

```java
@ConditionalOnClass(CatalogClient.class)
```

For genuinely optional dependencies, the `name` attribute is usually better because it represents the class name as a string. More importantly, **method signatures, fields, constructors, and superclasses in the outer configuration class should not directly reference optional types**.

### 3.1. Why Use a Nested Configuration?

Suppose you write:

```java
@AutoConfiguration
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "demo.catalog.sdk.CatalogClient")
    CatalogService catalogService(CatalogClient client) {
        return client::findById;
    }
}
```

This looks plausible because the bean method has `@ConditionalOnClass`. However, the method still contains an optional type in its signature. Along certain introspection/metadata-reading paths, the JVM or Spring may need to resolve that type before the method condition can protect the configuration. The result can be a class-loading failure when the SDK is absent.

Spring Boot recommends isolating beans that depend on optional classes inside **a separate nested static configuration class**, then placing `@ConditionalOnClass` on that nested class itself:

```java
@AutoConfiguration
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "demo.catalog.sdk.CatalogClient")
    static class CatalogSdkConfiguration {

        // Only methods inside this branch reference CatalogClient.
    }
}
```

Spring reads the nested configuration's condition metadata before processing SDK-dependent contents. When the class is absent, the nested configuration is skipped and method signatures containing optional types do not need to be processed as an active bean branch.

**This is the critical boundary:** keep the outer auto-configuration safe when the SDK is absent; place all optional type references inside the guarded nested class.

### 3.2. Places Where Optional Types Must Not Leak Out

When a dependency may be absent, avoid placing that type in:

- Constructors or fields of the outer auto-configuration.
- Return types or parameters of `@Bean` methods on the outer class.
- Superclasses or interfaces that the outer class must load.
- Static field initializers or static blocks of the outer class.
- Annotation attributes using class literals of the optional dependency on the outer class.
- Component scans or direct imports that cause the nested class to be loaded independently outside the condition.

Keep optional types inside the classpath-guarded nested configuration. If a helper class also references the SDK, call or load that helper only from the guarded branch.

### 3.3. Using Class Names When Dependencies Are Absent at Runtime

For libraries with optional SDKs, the form:

```java
@ConditionalOnClass(name = "com.vendor.catalog.CatalogClient")
```

does not require the annotation to contain the `CatalogClient.class` literal. The library can still compile with the SDK on the compile classpath, while consuming applications do not necessarily receive that SDK at runtime.

In Maven, the library can mark the dependency as optional:

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>catalog-sdk</artifactId>
    <version>1.2.0</version>
    <optional>true</optional>
</dependency>
```

Optional dependencies affect dependency propagation: they are on the classpath when building the library itself, but Maven does not automatically propagate them to consuming projects. Applications needing the integration must add the SDK themselves. In Gradle, use dependency configurations matching the module's publishing goals, such as `compileOnly`/runtime dependencies based on actual packaging and distribution.

Another design is splitting the integration into a separate starter, such as `acme-catalog-spring-boot-starter`, depending on both the autoconfig library and the SDK. When an application adds that starter, the required classes appear together. Regardless of approach, `@ConditionalOnClass` remains a useful runtime guard if the dependency can be excluded or changed.

## 4. `@ConditionalOnProperty`: Letting Users Disable the Feature

Once the SDK is present, the feature flag decides whether to register the configuration branch.

Example:

```java
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
```

The full key is `acme.catalog.enabled`. The condition matches when the value exists and equals the string `true` case-insensitively. With `matchIfMissing=false`, omitting the key also means the feature is not enabled.

Configuration:

```yaml
acme:
  catalog:
    enabled: true
```

When the user wants to disable it in a specific environment:

```yaml
acme:
  catalog:
    enabled: false
```

Or via command line:

```bash
java -jar app.jar --acme.catalog.enabled=false
```

Values from higher-precedence configuration sources override YAML files. Therefore, when debugging, inspect the final value in the `Environment` rather than reading only one file.

### 4.1. Choosing the Default: Opt-In or Opt-Out?

Both contracts are valid; the library must pick one and document it clearly.

| Policy | Annotation | When property missing | When user sets `false` | Best suited when |
|---|---|---|---|---|
| **Opt-in** | `havingValue="true", matchIfMissing=false` | Disabled | Disabled | Features with cost, side effects, external calls, or explicit configuration needs |
| **Opt-out** | `havingValue="true", matchIfMissing=true` | Enabled if dependency is present | Disabled | Backward-compatible features expected to work automatically once integration is added |

This demo chooses **opt-in**: without the property, the feature stays off. This is a safe default for an external integration that may require endpoints, credentials, quotas, or networking. If a product requires backward compatibility and automatic activation whenever the SDK is present, `matchIfMissing=true` can be used, provided the missing-key case is tested.

Do not confuse `matchIfMissing=true` with "ignore `false`". It applies only when **the key is not found**. If the user sets `false`, `havingValue="true"` still does not match.

### 4.2. Why Avoid Relying Only on the Default `havingValue`?

If `havingValue` is omitted, its default is the empty string. The condition then matches any present value other than `false`. Strings such as `yes`, `1`, or typos can unintentionally turn the feature on.

For a boolean toggle, write it explicitly:

```java
havingValue = "true",
matchIfMissing = false
```

The behavior table then becomes straightforward:

| Value | Opt-in in demo | Opt-out if `matchIfMissing=true` |
|---|---|---|
| Key missing | Does not match | Matches |
| `true` | Matches | Matches |
| `TRUE` | Matches | Matches |
| `false` | Does not match | Does not match |
| Empty string | Does not match | Does not match |
| `yes` / `1` / `truue` | Does not match | Does not match |

### 4.3. Place the Property Condition at the Right Level

If every bean in the integration should turn off when the user sets `false`, put `@ConditionalOnProperty` on the nested configuration containing all related beans. That way all beans in the branch toggle together.

If only one bean is optional, the condition can sit on its `@Bean` method. However, check whether other beans still require injecting that type; if service A still requires bean B while B is disabled, the context can fail due to a missing dependency.

A feature branch should have clear boundaries: beans solely serving the feature live inside the conditional branch, or consumers handle the optional dependency gracefully.

## 5. `@ConditionalOnMissingBean`: Yielding Control to the Application

A library should not force users onto its default implementation. If the application wants to provide its own service or client, auto-configuration can use:

```java
@Bean
@ConditionalOnMissingBean(CatalogService.class)
CatalogService catalogService(CatalogClient client) {
    return client::findById;
}
```

When the application already has a matching `CatalogService` bean, the default bean is not registered. This is the standard **back-off behavior** in Spring Boot auto-configuration.

The three conditions in this design play distinct roles:

| Condition | Question |
|---|---|
| `@ConditionalOnClass` | Is the required SDK on the classpath? |
| `@ConditionalOnProperty` | Does the application allow the feature to run? |
| `@ConditionalOnMissingBean` | Has the application already provided a replacement implementation? |

The missing-bean condition does not replace the first two. If the SDK is absent, do not try to create the service merely because no service bean exists yet. If the feature is disabled, a user bean may still exist from the application's own configuration; whether the feature flag should also disable user beans or only default beans is **a contract that must be designed explicitly**.

### 5.1. Allowing Replacement of Either the SDK Client or the Service

For broader extension points, `@ConditionalOnMissingBean` can guard both client and service:

```java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient() {
    return new CatalogClient();
}

@Bean
@ConditionalOnMissingBean(CatalogService.class)
CatalogService catalogService(CatalogClient client) {
    return client::findById;
}
```

These methods must reside inside the nested configuration guarded by classpath and property conditions. Applications can replace the client to swap transports, or replace the service to change business logic.

Note on ordering: auto-configuration is designed so user beans are typically processed before default beans. If an auto-configuration depends on a bean created by another auto-configuration, declare appropriate ordering relationships and test them; do not rely on accidental method order.

## 6. Designing Consuming Applications: Inject Optional Beans Optionally

Even when auto-configuration handles missing dependencies properly, an application can still break itself if a component unconditionally injects an optional service:

```java
@Service
public class OrderService {
    private final CatalogService catalogService;

    public OrderService(CatalogService catalogService) {
        this.catalogService = catalogService;
    }
}
```

If `CatalogService` is not registered when the SDK is absent or the flag is off, Spring cannot construct `OrderService` with this constructor.

### 6.1. `ObjectProvider` When the Feature Is Truly Optional

```java
@Service
public class OrderService {
    private final ObjectProvider<CatalogService> catalogProvider;

    public OrderService(ObjectProvider<CatalogService> catalogProvider) {
        this.catalogProvider = catalogProvider;
    }

    public String describe(String id) {
        CatalogService service = catalogProvider.getIfAvailable();
        if (service == null) {
            return "Catalog integration is unavailable";
        }
        return service.findById(id);
    }
}
```

`ObjectProvider` lets you check whether the bean is available at the moment it is needed. The application still starts when the bean is absent. Clearly define business behavior when the service is missing: return an alternative result, skip the optional step, or report an error only when users invoke functionality depending on that integration.

### 6.2. `Optional` Injection

Another option is a constructor accepting `Optional<CatalogService>`:

```java
public OrderService(Optional<CatalogService> catalogService) {
    this.catalogService = catalogService;
}
```

This fits when the application only needs to know whether the service exists at initialization. When dynamic lookup at call time is needed, `ObjectProvider` is more flexible.

### 6.3. Splitting Modules or Components by Feature

If most code does not need to know the SDK exists, move the adapter/catalog integration into a separate module and register components only when the feature condition matches. Controllers or jobs depending on the integration should also carry matching conditions or call through an optional interface.

Do not create a dummy bean just to let the application start if that dummy implementation returns wrong data or hides that the feature is off. If a fallback is needed, define fallback behavior as part of the product contract.

## 7. Complete Example: Optional SDK and Feature Flag

The example below uses **Java 17+**, Spring Boot 3.3.13, and Maven. It demonstrates three states:

- SDK present and flag enabled: client and service are registered.
- SDK present but flag disabled: client and service are not registered.
- SDK absent: nested configuration is skipped, and the application does not fail due to missing SDK classes.

To run standalone, the project defines a simulated vendor SDK class in a separate package. In a real library, that class comes from an optional Maven dependency or dedicated integration starter.

### 7.1. Directory Structure

```text
optional-catalog-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/catalog/
    │   │   ├── api/CatalogService.java
    │   │   ├── sdk/CatalogClient.java
    │   │   ├── autoconfigure/CatalogAutoConfiguration.java
    │   │   └── app/CatalogDemoApplication.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/catalog/
        └── CatalogAutoConfigurationTest.java
```

### 7.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>optional-catalog-demo</artifactId>
    <version>1.0.0</version>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. Consumer-Facing API: `CatalogService.java`

```java
package demo.catalog.api;

public interface CatalogService {
    String findById(String id);
}
```

This interface does not depend on the vendor SDK. Business modules can compile with just the library API, even when the optional SDK is absent.

### 7.4. Simulated SDK: `CatalogClient.java`

```java
package demo.catalog.sdk;

public class CatalogClient {

    public String findById(String id) {
        return "catalog-item:" + id;
    }
}
```

In this demo project, this class simulates an external dependency. In a real library, the simulated class resides in a separate artifact; applications not needing the SDK do not add that artifact. Tests use `FilteredClassLoader` to simulate a context unable to load this class.

### 7.5. Auto-Configuration: `CatalogAutoConfiguration.java`

```java
package demo.catalog.autoconfigure;

import demo.catalog.api.CatalogService;
import demo.catalog.sdk.CatalogClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "demo.catalog.sdk.CatalogClient")
    @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    static class CatalogSdkConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient() {
            return new CatalogClient();
        }

        @Bean
        @ConditionalOnMissingBean(CatalogService.class)
        CatalogService catalogService(CatalogClient client) {
            return client::findById;
        }
    }
}
```

There are four design decisions:

1. The outer class uses only stable API types and has no methods or constructors needing SDK initialization.
2. The nested configuration holds all references to optional types.
3. `@ConditionalOnClass(name=...)` protects the branch when the SDK is absent from the classpath.
4. `@ConditionalOnProperty(... matchIfMissing=false)` requires explicit opt-in; `@ConditionalOnMissingBean` allows the application to replace the client or service.

If the user sets `acme.catalog.enabled=false`, neither bean in the nested configuration is registered. If the key is missing, the demo stays disabled under the opt-in policy.

### 7.6. Publishing Auto-Configuration

Create the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Single line content:

```text
demo.catalog.autoconfigure.CatalogAutoConfiguration
```

This is how Spring Boot 3.x discovers library auto-configurations. Place the auto-configuration class in a dedicated package not underneath the application's main component-scan package. Do not component-scan or manually `@Import` this auto-configuration again.

### 7.7. Consuming Application: `CatalogDemoApplication.java`

```java
package demo.catalog.app;

import demo.catalog.api.CatalogService;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogDemoApplication implements CommandLineRunner {

    private final ObjectProvider<CatalogService> catalogProvider;

    public CatalogDemoApplication(
            ObjectProvider<CatalogService> catalogProvider) {
        this.catalogProvider = catalogProvider;
    }

    public static void main(String[] args) {
        SpringApplication.run(CatalogDemoApplication.class, args);
    }

    @Override
    public void run(String... args) {
        CatalogService catalog = catalogProvider.getIfAvailable();

        if (catalog == null) {
            System.out.println("catalogFeature=unavailable");
            return;
        }

        System.out.println("catalogResult=" + catalog.findById("42"));
    }
}
```

The application uses `ObjectProvider` because the service may be absent. When enabling the feature:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--acme.catalog.enabled=true
```

Output line printed by the application:

```text
catalogResult=catalog-item:42
```

When disabling the feature:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--acme.catalog.enabled=false
```

Output:

```text
catalogFeature=unavailable
```

If `--acme.catalog.enabled=true` is omitted, the demo uses opt-in so it also prints `catalogFeature=unavailable`. Spring Boot startup logs may also appear; the lines above are the application's output.

### 7.8. Testing with `ApplicationContextRunner` and `FilteredClassLoader`

File `CatalogAutoConfigurationTest.java`:

```java
package demo.catalog;

import demo.catalog.api.CatalogService;
import demo.catalog.autoconfigure.CatalogAutoConfiguration;
import demo.catalog.sdk.CatalogClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class));

    @Test
    void featureIsDisabledWhenPropertyIsMissing() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean("catalogClient");
            assertThat(context).doesNotHaveBean("catalogService");
        });
    }

    @Test
    void featureIsEnabledWhenDependencyExistsAndFlagIsTrue() {
        runner.withPropertyValues("acme.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);
                    assertThat(context).hasSingleBean(CatalogService.class);
                    assertThat(context.getBean(CatalogService.class)
                            .findById("42"))
                            .isEqualTo("catalog-item:42");
                });
    }

    @Test
    void userCanDisableFeatureEvenWhenDependencyExists() {
        runner.withPropertyValues("acme.catalog.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("catalogClient");
                    assertThat(context).doesNotHaveBean("catalogService");
                });
    }

    @Test
    void missingOptionalSdkDoesNotFailContext() {
        runner.withClassLoader(
                new FilteredClassLoader(CatalogClient.class))
                .withPropertyValues("acme.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("catalogClient");
                    assertThat(context).doesNotHaveBean("catalogService");
                });
    }

    @Test
    void applicationServiceOverridesDefaultService() {
        runner.withPropertyValues("acme.catalog.enabled=true")
                .withUserConfiguration(UserCatalogConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogService.class);
                    assertThat(context.getBean(CatalogService.class)
                            .findById("42"))
                            .isEqualTo("custom-item:42");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {

        @Bean
        CatalogService customCatalogService() {
            return id -> "custom-item:" + id;
        }
    }
}
```

Run tests:

```bash
mvn test
```

With the exact five tests in the class above, the expected result is **5 tests, 0 failures, 0 errors**. This is the expected outcome; actual numbers must come from Maven Surefire when running the project.

### 7.9. Purpose of Each Test

| Test | Input | Expected result |
|---|---|---|
| `featureIsDisabledWhenPropertyIsMissing` | SDK present, property missing | Context succeeds; no client/service |
| `featureIsEnabledWhenDependencyExistsAndFlagIsTrue` | SDK present, `enabled=true` | `CatalogClient` and `CatalogService` present |
| `userCanDisableFeatureEvenWhenDependencyExists` | SDK present, `enabled=false` | Context succeeds; neither bean present |
| `missingOptionalSdkDoesNotFailContext` | SDK hidden by `FilteredClassLoader`, `enabled=true` | Context still succeeds; neither bean present |
| `applicationServiceOverridesDefaultService` | SDK present, `enabled=true`, user service registered | Only application-supplied service is used |

The `missingOptionalSdkDoesNotFailContext` test is the most important for proving the classpath condition. Merely asserting `doesNotHaveBean` while the dependency remains on the classpath does not prove the application tolerates a missing dependency. `FilteredClassLoader` prevents the SDK class from being loaded in the context under test.

## 8. Designing Dependencies in Maven/Gradle Libraries

### 8.1. Maven Optional Dependencies

A library can compile against an SDK without forcing every consuming application to receive it:

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>catalog-sdk</artifactId>
    <version>1.2.0</version>
    <optional>true</optional>
</dependency>
```

This is appropriate when:
- Auto-configuration can function without the integration.
- Only applications using the integration add the SDK.
- The library wants to ship one primary artifact without pulling multiple SDKs into every consumer.

When users need the feature, they add the dependency:

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>catalog-sdk</artifactId>
    <version>1.2.0</version>
</dependency>
```

Do not mark a dependency optional if the library cannot function or cannot compile/start without it. `optional` is an API and dependency-distribution decision, not a way to hide configuration bugs.

### 8.2. Splitting the Integration into a Module/Starter

A multi-module layout can look like:

```text
acme-catalog/
├── acme-catalog-core/
│   └── CatalogService API and vendor-independent business logic
├── acme-catalog-spring-boot-autoconfigure/
│   └── auto-configuration + conditions
└── acme-catalog-spring-boot-starter/
    └── dependencies on autoconfigure and vendor SDK
```

Applications using only the core API do not pull in the SDK. Applications wanting the integration add the starter. This is a clean option when the vendor SDK is large, carries a separate license, or is needed by only a subset of users.

You can also publish a starter without the vendor SDK alongside one with the vendor SDK if you want to support both integration models. Module names and dependency graphs should clearly communicate what users are adding.

### 8.3. Gradle and Optional Runtime Dependencies

In Gradle, dependency configurations should reflect the module's compile and runtime targets:

- `compileOnly`: present when compiling the module but not automatically added to consumers' runtime.
- `runtimeOnly`: present at runtime without exposing types during source compilation.
- `api`/`implementation`: controls which dependencies are exposed to consumers in Gradle.

Do not mechanically copy Maven `optional=true` rules into Gradle; verify the module's published metadata and actual consumer dependency graph. What must stay constant is: **if an SDK can be absent at runtime, auto-configuration must have a classpath guard and must not load optional types outside the guarded branch.**

## 9. Cases Requiring More Careful Design

### 9.1. Dependency Is Present, but Connection Configuration Is Incomplete

`@ConditionalOnClass` only confirms the class exists. It does not prove:

- The endpoint URL is valid.
- Credentials are present or still valid.
- Network connectivity to the vendor works.
- The SDK is compatible with the server.
- The account has access permissions.

If the client bean requires an endpoint, you can add `@ConditionalOnProperty` for the mandatory property, or use validated `@ConfigurationProperties` to fail fast with a clear error message when the user enabled the feature yet omitted required configuration.

Do not use `@ConditionalOnProperty` to silently ignore invalid configuration when the application explicitly enabled the feature expecting it to work. Decide: **missing endpoint disables the feature**, or **enabled feature with missing endpoint is a startup failure**. Those are two different policies.

### 9.2. User Disables the Feature but Still Provides a Custom Bean

If the feature condition sits on the entire nested configuration, that branch is not imported when the flag is `false`. An independently declared custom bean in the application can still exist. This can be the intended behavior: the flag disables only the library's default beans.

If the contract requires `false` to prohibit using even user-provided services, place a condition at the consumption boundary or use a clearer feature policy. Do not assume `@ConditionalOnProperty` on an auto-configuration deletes beans created by user configurations.

### 9.3. Separating Classpath Conditions and Property Conditions

Putting both conditions on the nested configuration keeps logic clear. If the dependency is absent, the feature flag does not matter; if the dependency is present, the property decides whether to apply it.

Some codebases put `@ConditionalOnClass` on the outer class and `@ConditionalOnProperty` on methods. That can work when every class in the outer class is safe to load. However, when method signatures contain optional types, a nested configuration is usually an easier isolation boundary to reason about.

### 9.4. Do Not Use `@ConditionalOnMissingClass` for Every Optional Design

You can use `@ConditionalOnMissingClass` to provide a fallback when the SDK is absent. Make sure the fallback is actually meaningful. For instance, a service returning empty data may hide that the integration is not installed. If the feature makes sense only when the SDK exists, omitting the bean and letting the application handle the optional dependency is usually more transparent.

### 9.5. Bean Conditions and Auto-Configuration Ordering

If the service bean needs a bean provided by another auto-configuration, `@ConditionalOnBean` sees only bean definitions already processed at evaluation time. When depending on another auto-configuration, use `@AutoConfiguration(after = OtherAutoConfiguration.class)` or the corresponding ordering attribute. Do not use classpath/property conditions to work around bean registration ordering bugs.

## 10. Design Decision Table

| Question | Mechanism to use | Notes |
|---|---|---|
| Might the SDK class be absent? | `@ConditionalOnClass(name=...)` | Place on nested config isolating optional types |
| Can users disable the feature? | `@ConditionalOnProperty` | Pick opt-in or opt-out and document the default |
| Do users want to replace the default service? | `@ConditionalOnMissingBean(Service.class)` | Place on the default bean |
| Can the application run without the service? | `ObjectProvider`/`Optional`/feature-specific config | Never inject a potentially absent bean as required |
| Should the SDK dependency not propagate to every consumer? | Maven optional or separate module/starter | Inspect published dependency graph |
| SDK present but missing endpoint/credentials? | Validation and property contract | Distinguish disabled feature from enabled-but-misconfigured |
| Want to disable only part of a nested config? | Condition on nested config/bean method | Do not exclude the entire outer auto-config if other branches are still needed |
| Need a fallback when SDK is missing? | `@ConditionalOnMissingClass` or alternative implementation | Use only if the fallback has valid semantics |
| Need a bean condition from another auto-config? | `@AutoConfiguration(after=...)` + `@ConditionalOnBean` | Handle dependency order at the proper layer |

## 11. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| App not using SDK fails at startup with `NoClassDefFoundError` | Optional type in outer config/method signature or scanned/imported separately | Isolate optional types in nested config with `@ConditionalOnClass` |
| Setting `enabled=false` yet bean still exists | Bean created by user config or another auto-config | Identify bean source; library feature flags do not delete independent beans |
| SDK present, flag missing, bean absent | Using opt-in with `matchIfMissing=false` | This is the chosen default; set `true` to enable or intentionally change policy |
| SDK missing yet `enabled=true`, bean still absent | Classpath condition did not match | Add proper dependency or accept integration is unavailable |
| App startup fails due to missing `CatalogService` | Consumer injects optional bean as required | Use `ObjectProvider`/`Optional` or guard consumer too |
| User already has `CatalogService` yet default still appears | `@ConditionalOnMissingBean` wrong type/name or user bean not processed earlier | Check bean type, qualifier, and auto-config ordering |
| SDK class present at compile time but missing at runtime | Incorrect dependency scope/publication | Check Maven/Gradle runtime graph and published metadata |
| Classpath condition true yet client creation fails | Class exists, but config/endpoint/credentials invalid | Validate config and inspect constructor/factory failure |
| Flag `false` yet custom service still exists | User bean registered outside the auto-config branch | Decide whether flag governs only default beans or the whole feature |
| Missing-SDK test passes even without hiding the class | Only skipped registering the bean while class remained on classpath | Use `FilteredClassLoader` to simulate missing dependency |

## 12. Pre-Release Starter Testing Workflow

An auto-configuration library should cover at least these cases:

1. **SDK present + flag `true`:** default bean appears.
2. **SDK present + flag `false`:** default bean does not appear.
3. **SDK present + flag missing:** outcome matches the documented opt-in/opt-out default policy.
4. **SDK missing + flag `true`:** context has no class-loading error and creates no integration bean.
5. **SDK present + custom service:** default bean backs off.
6. **SDK present + custom client:** default client backs off if the library supports that extension point.
7. **Consumer without service:** application still starts if the feature is genuinely optional.
8. **Enabled config with invalid endpoint/credentials:** matches the documented fail-fast or disabled contract.

Use `ApplicationContextRunner` to test auto-configuration quickly in isolated contexts. Use `FilteredClassLoader` for missing-dependency scenarios. For real applications, add at least one integration test booting with `@SpringBootTest` or running the packaged starter on a consuming classpath to catch imports registration and dependency propagation bugs.

When debugging, run with `--debug` to view the Condition Evaluation Report. Look for `OnClassCondition` and `OnPropertyCondition` on the nested configuration. If no entry appears, check whether the auto-configuration is published in `AutoConfiguration.imports` and whether it was excluded.

## 13. Self-Check Questions

**Question 1.** The `CatalogClient` SDK is absent from the runtime classpath, while the feature flag is `true`. Can `@ConditionalOnProperty` make the bean appear on its own?

**Answer:** No. The `@ConditionalOnClass` classpath condition still fails to match; properties do not install dependencies.

**Question 2.** Why put optional types inside a nested configuration with `@ConditionalOnClass`?

**Answer:** So Spring Boot reads and evaluates the classpath condition before processing SDK-dependent methods, constructors, or type references, preventing the outer auto-configuration from failing when the SDK is absent.

**Question 3.** With `havingValue="true", matchIfMissing=false`, if the user omits the property, is the feature enabled?

**Answer:** No. This is an opt-in policy; the user must explicitly set `true`.

**Question 4.** With `matchIfMissing=true`, if the user sets `false`, does the condition match?

**Answer:** No. `matchIfMissing` applies only when the key is absent; `false` still does not equal `true`.

**Question 5.** What scenario does `@ConditionalOnMissingBean(CatalogService.class)` solve?

**Answer:** It allows auto-configuration to yield the default service bean when the application has already supplied a matching bean.

**Question 6.** The SDK is present, the flag is `false`, and the application still defines a custom `CatalogService` in user config. Does the flag on the nested auto-configuration delete that bean?

**Answer:** No. The condition only prevents that auto-configuration branch from applying; it does not delete beans from independent user configurations.

**Question 7.** Why should consumers use `ObjectProvider` for `CatalogService`?

**Answer:** Because the service may be absent when the SDK is missing or the feature is disabled. `ObjectProvider` lets the application handle the missing-bean state and still start.

## 14. Takeaways

- **Dependency presence** and **feature enablement** are two independent conditions.
- Use `@ConditionalOnClass(name=...)` to check optional SDKs; place the condition on a nested static configuration to isolate references to optional types.
- Use `@ConditionalOnProperty(havingValue="true")` so users control the feature; choose `matchIfMissing=false` for opt-in or `true` for opt-out.
- Use `@ConditionalOnMissingBean` so applications can replace default implementations.
- Never inject a potentially absent bean as required; consider `ObjectProvider`, `Optional`, or conditions on the consuming component.
- Test a truly missing-dependency classpath with `FilteredClassLoader`; testing `false` properties alone is insufficient.
- Auto-configuration does not delete independent user beans. Define clearly whether the feature flag governs only default beans or the entire usage path.

### Official Documentation

- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — ConditionalOnClass API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3 — ConditionalOnProperty API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.3 — ConditionalOnMissingBean API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.3 — ApplicationContextRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.3 — FilteredClassLoader API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
