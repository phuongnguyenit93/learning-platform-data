# Changes to Auto-Configuration Registration Across Spring Boot Lines

Spring Boot auto-configuration lets a library automatically configure needed beans when an application has the right dependencies on the classpath. Instead of requiring every application to import a configuration class manually, Spring Boot discovers auto-configuration classes published by libraries, evaluates their conditions, and registers beans when those conditions are satisfied.

The **auto-configuration registration mechanism has changed across Spring Boot lines**. If you maintain a starter or upgrade an application from Boot 2.x to 3.x/4.x, you need to know which files the framework reads, which annotations apply, and how to preserve compatibility.

Key transition milestones:

- **Spring Boot 1.x through 2.6:** auto-configurations registered under the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key in `META-INF/spring.factories`.
- **Spring Boot 2.7:** introduced `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` and the `@AutoConfiguration` annotation. The old mechanism remained supported for transition, though deprecated.
- **Spring Boot 3.0 and later:** dropped auto-configuration registration via the `EnableAutoConfiguration` key in `spring.factories`. `AutoConfiguration.imports` is the mechanism to use. Other SPIs may continue using `spring.factories`.
- **Spring Boot 4.x:** continues using `AutoConfiguration.imports`. When upgrading starters, pay attention to modularization and package/module changes in Boot 4; there is no return to the old registration mechanism.

This lesson covers the history, file format, an auto-configuration creation example, multi-version compatibility migration, testing, JAR packaging, and diagnosing when auto-configuration fails to load.

## 1. What does auto-configuration do?

A library may need to provide a default client, converter, template, or service. For example, an Acme library supplies an SDK to call a catalog service. When an application adds the SDK to its classpath, the starter can automatically register:

- `AcmeClient` to call the service.
- `AcmeClientProperties` to bind URL and timeout.
- `AcmeHealthIndicator` if health integration exists.
- Related converters or customizers.

Auto-configuration is a configuration class provided by the library. Spring Boot discovers this class, then evaluates conditions such as:

- Whether the required library is on the classpath.
- Whether the application has already declared a corresponding bean.
- What value a feature toggle property has.
- Whether the application is a web application.
- Whether a specific resource or class exists.

For example, the library wants to create a client only when the SDK is present and the application has not provided its own client:

```java
@AutoConfiguration
@ConditionalOnClass(AcmeSdk.class)
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient(AcmeClientProperties properties) {
        return new AcmeClient(
                properties.baseUrl(),
                properties.timeout()
        );
    }
}
```

When auto-configuration loads, conditions are evaluated. If satisfied, bean definitions are registered. Registering an auto-configuration class **does not mean every bean inside it will always be created**; conditions still decide whether each configuration or bean method applies.

## 2. Spring Boot 1.x through 2.6: spring.factories

In older Boot lines, auto-configuration was registered via the file:

```text
META-INF/spring.factories
```

Inside the file, use the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key with a list of fully qualified class names.

Example:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.autoconfigure.AcmeClientAutoConfiguration,\
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
```

Listed classes become auto-configuration candidates when an application enables `@EnableAutoConfiguration` or uses `@SpringBootApplication`.

### 2.1. Why is the file named spring.factories?

`spring.factories` is a registration mechanism for many Spring Boot and Spring Framework extension points, not just auto-configuration. One file can contain multiple keys, each mapping to one or more implementation classes.

Illustrative example of several SPIs registered through this file:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.autoconfigure.AcmeClientAutoConfiguration

org.springframework.boot.env.EnvironmentPostProcessor=\
com.acme.bootstrap.AcmeEnvironmentPostProcessor

org.springframework.boot.diagnostics.FailureAnalyzer=\
com.acme.diagnostics.AcmeFailureAnalyzer
```

Do not assume that because Boot 3 removed the auto-configuration key, the entire `spring.factories` file was eliminated. The change focuses on **the auto-configuration registration key**.

### 2.2. @EnableAutoConfiguration triggers candidate discovery

`@SpringBootApplication` includes `@EnableAutoConfiguration`. This annotation triggers the selector mechanism that gathers the list of auto-configuration candidates from libraries on the classpath.

In older lines, the candidate list was read from the `EnableAutoConfiguration` key in `spring.factories`. Spring Boot then processes exclusions, conditions, and configuration ordering.

Regular applications do not need to list every auto-configuration class manually. Starters or libraries are responsible for publishing them.

## 3. Spring Boot 2.7: the transition phase

Spring Boot 2.7 introduced a new file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line contains one fully qualified class name:

```text
com.acme.autoconfigure.AcmeClientAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
```

Notable points about the new file:

- It does not use one long Properties key like `spring.factories`.
- Each auto-configuration class sits on its own line.
- Comments can be added using the `#` character.
- The framework reads files from JARs on the classpath.
- Boot 2.7 still reads legacy registrations to support unmigrated libraries.
- If the same class appears in both places, Boot 2.7 deduplicates candidates.

### 3.1. The path must be exact

The new path is:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

This is a resource packaged inside the auto-configuration module's JAR. Some early milestone docs mentioned a different experimental path; when migrating to Boot 2.7 stable and newer lines, use the exact `META-INF/spring/...` path above.

### 3.2. Introduction of the @AutoConfiguration annotation

Boot 2.7 introduced `@AutoConfiguration` for top-level auto-configuration classes:

```java
@AutoConfiguration
public class AcmeClientAutoConfiguration {
}
```

This annotation is meta-annotated with `@Configuration(proxyBeanMethods = false)`, and also provides attributes to declare auto-configuration ordering.

Therefore, top-level classes generally use `@AutoConfiguration` instead of `@Configuration` when the baseline supports Boot 2.7 or higher.

Configuration classes imported or nested inside an auto-configuration can continue using `@Configuration` in their usual role.

### 3.3. Boot 2.7 still supports spring.factories for compatibility

During the 2.7 phase, a library can publish the same auto-configuration class in both files:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

This is a useful bridge when a library must support both Boot 2.6 and Boot 2.7:

- Boot 2.6 understands only the legacy registration.
- Boot 2.7 understands both legacy and new registrations.
- Boot 2.7 deduplicates classes appearing in both sources.

However, maintaining both files should only serve an actually needed compatibility matrix. Once the library's baseline is Boot 2.7+, you can use the new imports file and drop the legacy auto-configuration registration.

## 4. Spring Boot 3.0: removing EnableAutoConfiguration from spring.factories

Boot 3.0 removed support for registering auto-configurations via the key:

```text
org.springframework.boot.autoconfigure.EnableAutoConfiguration
```

in `META-INF/spring.factories`.

Instead, the framework uses:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Example registration for Boot 3:

```text
com.acme.autoconfigure.AcmeClientAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
```

### 4.1. spring.factories did not disappear completely

Other entries in `spring.factories` remain active for their corresponding SPIs. For example, a library may still register a `FailureAnalyzer` or `EnvironmentPostProcessor` under the appropriate key.

Thus, proper migration means:

- Removing the old **auto-configuration entry** from `spring.factories` when Boot 2.6 compatibility is no longer required.
- Keeping other SPI entries if they remain supported by the target version.
- Moving the auto-configuration class list to `AutoConfiguration.imports`.

Do not delete the entire `spring.factories` file mechanically if the library still uses other extension points.

### 4.2. A library supporting both Boot 2.x and Boot 3.x

If a single artifact must support Boot 2.6 and Boot 3.x, both registration resources can be packaged:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

In `spring.factories`, keep the `EnableAutoConfiguration` entry so Boot 2.6 finds the class. In the imports file, publish the class so Boot 2.7/3.x finds it.

Boot 2.7 supports both sources and deduplicates candidates. Boot 3.x ignores the old auto-configuration key and reads the imports file.

Beyond resource registration, verify **binary/API compatibility** of the class. If the class uses annotations or APIs introduced in Boot 2.7, it will fail on a Boot 2.6 runtime even if the old registration file is present. Choose an appropriate compile baseline or release separate artifacts/variants.

### 4.3. @AutoConfiguration and Boot 2.6 compatibility

`@AutoConfiguration` was introduced in Boot 2.7. If a binary must run on Boot 2.6, do not assume a class referencing this annotation will work on a 2.6 runtime.

Options:

- If the minimum baseline is Boot 2.7, use `@AutoConfiguration`.
- If the same binary must run on both Boot 2.6 and Boot 3, consider `@Configuration` with ordering annotations available in the baseline, registered via both old and new files.
- If Boot 3-specific APIs are needed, publish separate artifacts/variants rather than forcing one binary across every generation.

Boot 3 does not require deleting configuration classes just because they use `@Configuration`; what matters is that the class is registered and configured properly. However, for new code supporting only Boot 2.7+, `@AutoConfiguration` is recommended.

## 5. Spring Boot 4.x line

Spring Boot 4 continues using the `AutoConfiguration.imports` mechanism for auto-configuration. There is no return to registering auto-configurations via the `EnableAutoConfiguration` key in `spring.factories`.

When upgrading a library/starter to Boot 4, pay additional attention to:

- Boot 4 modularizes parts of the framework; packages and modules containing certain APIs/auto-configurations may change.
- Starter artifacts and dependencies may be reorganized around the new modules.
- Classes referenced in `before`/`after`, exclusions, and replacements must be updated if their packages changed.
- Some SPIs still using `spring.factories` may change package/class keys; for instance, `EnvironmentPostProcessor` moved packages in Boot 4, so both code imports and registration keys must match the new API.
- Boot 4 migration guidance recommends not trying to support Boot 3 and Boot 4 in the same starter artifact when separate compatible lines can be published.

This does not alter the core registration principle: auto-configurations remain published via the imports resource. What needs auditing in Boot 4 are the modules, packages, dependencies, and SPIs your auto-configuration uses.

## 6. Comparison across Spring Boot lines

| Spring Boot line | Auto-configuration registration | Recommended top-level annotation | Notes |
|---|---|---|---|
| 1.x | `spring.factories` with `EnableAutoConfiguration` key | `@Configuration` | Traditional mechanism |
| 2.0–2.6 | `spring.factories` with `EnableAutoConfiguration` key | `@Configuration` | Continues legacy mechanism |
| 2.7 | `AutoConfiguration.imports`; `spring.factories` still supported for compatibility | `@AutoConfiguration` | Migration starts; deduplicated |
| 3.x | `AutoConfiguration.imports` | `@AutoConfiguration` | `EnableAutoConfiguration` key dropped from `spring.factories` |
| 4.x | `AutoConfiguration.imports` | `@AutoConfiguration` | Continues imports; watch modularization and package migration |

Remember that this table covers **auto-configuration registration**. Other SPIs have their own mechanisms or keys; do not infer that every entry in `spring.factories` was removed.

## 7. Modern starter module structure

A library can split modules as follows:

```text
acme-spring-boot/
├── acme-spring-boot-autoconfigure/
│   ├── src/main/java/com/acme/autoconfigure/
│   │   ├── AcmeClientAutoConfiguration.java
│   │   └── AcmeClientProperties.java
│   └── src/main/resources/
│       └── META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-spring-boot-starter/
    └── build configuration / dependency declarations
```

Roles:

- **autoconfigure module:** contains auto-configuration classes, properties classes, and library integration code.
- **starter module:** aggregates the required dependencies so applications only need to add one starter dependency.

If the library is simple, both can be combined into one module. Splitting modules helps when users want to pick dependencies manually while still using auto-configuration.

### 7.1. Do not name modules like official Spring starters

Third-party starters should use their own namespace, such as `acme-spring-boot-starter`. Never name a module starting with `spring-boot-` if it does not belong to the official Spring Boot project.

Configuration keys should also use their own namespace, such as `acme.client`, avoiding core namespaces like `spring`, `server`, or `management`.

## 8. Building a complete auto-configuration

Suppose the Acme library provides a client:

```java
package com.acme.client;

public class AcmeClient {

    private final String baseUrl;
    private final Duration timeout;

    public AcmeClient(String baseUrl, Duration timeout) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
    }

    public String baseUrl() {
        return baseUrl;
    }

    public Duration timeout() {
        return timeout;
    }
}
```

Properties:

```java
package com.acme.autoconfigure;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.client")
public record AcmeClientProperties(
        String baseUrl,
        Duration timeout
) {
}
```

Auto-configuration:

```java
package com.acme.autoconfigure;

import com.acme.client.AcmeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.client",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    @ConditionalOnMissingBean(AcmeClient.class)
    AcmeClient acmeClient(AcmeClientProperties properties) {
        return new AcmeClient(
                properties.baseUrl(),
                properties.timeout()
        );
    }
}
```

The example assumes the SDK dependency is present when auto-configuration is used. Real applications should define clear defaults and validation for required properties.

### 8.1. Registering in AutoConfiguration.imports

Create the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Contents:

```text
com.acme.autoconfigure.AcmeClientAutoConfiguration
```

When building the JAR, the resource must reside at the exact path inside the archive. If the source file is right yet the resource is not packaged, Spring Boot will not find the auto-configuration.

### 8.2. Configuring an application using the starter

Example `application.yml`:

```yaml
acme:
  client:
    enabled: true
    base-url: https://api.acme.example
    timeout: 3s
```

The application only needs to add the starter dependency. When the SDK class is on the classpath, the property permits it, and no custom bean replaces it, auto-configuration creates `AcmeClient`.

## 9. Important conditions in auto-configuration

Registering a class only makes it a candidate. Conditions decide whether the configuration applies.

### 9.1. @ConditionalOnClass

Use when a feature works only if a specific dependency/class is on the classpath:

```java
@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
public class AcmeClientAutoConfiguration {
}
```

Placing the condition at the configuration class level lets Boot evaluate metadata before processing configurations depending on that class.

Be careful if using an optional class in the return type of a `@Bean` method: the JVM may need to load the method signature before method-level conditions are evaluated. When a dependency is truly optional, isolate the configuration depending on that class into a separate configuration class with `@ConditionalOnClass` at the class level.

### 9.2. @ConditionalOnMissingBean

Allows the application to provide its own bean:

```java
@Bean
@ConditionalOnMissingBean(AcmeClient.class)
AcmeClient acmeClient(AcmeClientProperties properties) {
    return new AcmeClient(
            properties.baseUrl(),
            properties.timeout()
    );
}
```

If the user has already declared an `AcmeClient` bean, auto-configuration does not create the default bean.

Bean conditions belong in auto-configuration because auto-configuration is processed after application-declared bean definitions. Avoid relying on accidental ordering between ordinary configurations.

### 9.3. @ConditionalOnProperty

Used to toggle a feature on or off:

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme.client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
AcmeClient acmeClient(AcmeClientProperties properties) {
    return new AcmeClient(
            properties.baseUrl(),
            properties.timeout()
    );
}
```

If you want it disabled by default, omit `matchIfMissing = true` and require the property to be enabled explicitly.

### 9.4. Other conditions

Spring Boot also provides conditions for:

- Class presence/absence on the classpath.
- Bean type or bean name.
- Property values.
- Resource existence.
- Web applications or web application types.
- SpEL expressions.

Use conditions that accurately express integration prerequisites instead of creating a bean and checking manually inside its constructor.

## 10. Auto-configuration ordering

Some auto-configurations must be processed before or after others. For example, a web extension configuration may need to apply after MVC auto-configuration.

With `@AutoConfiguration`:

```java
@AutoConfiguration(after = WebMvcAutoConfiguration.class)
public class AcmeWebAutoConfiguration {
}
```

Or using a class name:

```java
@AutoConfiguration(afterName =
        "org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration")
public class AcmeWebAutoConfiguration {
}
```

Dedicated ordering annotations are also supported:

```java
@AutoConfigureAfter(WebMvcAutoConfiguration.class)
@AutoConfigureBefore(SomeOtherAutoConfiguration.class)
@AutoConfigureOrder(100)
```

### 10.1. Registration order is not bean instantiation order

Ordering determines the order in which auto-configuration classes/bean definitions are processed. It does **not** mean every bean in those classes runs its constructor in that exact order.

Bean instantiation still depends on the dependency graph, scopes, lazy initialization, `@DependsOn`, and other lifecycle rules.

Do not use ordering to fix an undeclared dependency. If bean B needs bean A, express the dependency via constructor injection or an appropriate mechanism.

## 11. Auto-configurations should not be component scanned

Auto-configurations should be loaded through the imports file. Do not place them in a package accidentally discovered by application component scanning, and do not use component scanning inside auto-configuration to pick up more classes.

Instead of:

```java
@AutoConfiguration
@ComponentScan("com.acme")
public class AcmeAutoConfiguration {
}
```

import the needed configurations explicitly:

```java
@AutoConfiguration
@Import({
        AcmeClientConfiguration.class,
        AcmeMetricsConfiguration.class
})
public class AcmeAutoConfiguration {
}
```

Benefits:

- Clear scope of registered classes.
- Avoids accidentally pulling in unrelated components.
- Easier to verify conditions and ordering.
- Reduces the risk of configurations being loaded twice via imports and component scanning.

Place auto-configurations in a dedicated package like `com.acme.autoconfigure`, outside typical application component scan scopes whenever possible.

## 12. Excluding auto-configuration when an application does not need it

An application can exclude an auto-configuration by class:

```java
@SpringBootApplication(
        exclude = AcmeClientAutoConfiguration.class
)
public class Application {
}
```

Or by class name:

```java
@SpringBootApplication(
        excludeName = "com.acme.autoconfigure.AcmeClientAutoConfiguration"
)
public class Application {
}
```

Or via property:

```properties
spring.autoconfigure.exclude=com.acme.autoconfigure.AcmeClientAutoConfiguration
```

This mechanism is for applications wanting to disable an auto-configuration. When authoring a starter, design conditions and properties so users can customize behavior without excluding the whole class just to swap one bean.

## 13. AutoConfiguration.replacements when renaming classes

When a library moves packages or renames an auto-configuration class, the old class name may already be referenced by other configurations in `before`/`after` or exclusions.

Current Spring Boot documentation supports a replacements file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
```

Example content:

```properties
com.acme.autoconfigure.AcmeClientAutoConfiguration=com.acme.autoconfigure.client.AcmeClientAutoConfiguration
```

Once a replacement is declared:

- `AutoConfiguration.imports` should list only the replacement class.
- The mapping tells Spring Boot the old class name was replaced by the new class in relevant auto-configuration metadata.
- Ordering/exclusion configurations referencing the old name can be resolved via the replacement mapping.

This feature is helpful when refactoring a public auto-configuration class already referenced by other modules. If merely renaming an unpublished internal class, a replacements file is usually unnecessary.

## 14. Testing auto-configuration with ApplicationContextRunner

Do not check only that the JAR contains the imports file. Verify conditions and bean behavior.

`ApplicationContextRunner` creates lightweight contexts, adds specific auto-configurations, and asserts outcomes.

Example:

```java
class AcmeClientAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeClientAutoConfiguration.class
                            )
                    )
                    .withPropertyValues(
                            "acme.client.enabled=true",
                            "acme.client.base-url=https://api.test",
                            "acme.client.timeout=2s"
                    );

    @Test
    void createsClientWhenEnabled() {
        contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AcmeClient.class);
        });
    }
}
```

The test above assumes the SDK dependency is present on the test classpath.

### 14.1. Testing that a user bean takes precedence

```java
@Configuration(proxyBeanMethods = false)
static class UserConfiguration {

    @Bean
    AcmeClient customAcmeClient() {
        return new AcmeClient(
                "https://custom.test",
                Duration.ofSeconds(7)
        );
    }
}
```

Add the user configuration:

```java
contextRunner
        .withUserConfiguration(UserConfiguration.class)
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AcmeClient.class);
            assertThat(context.getBean(AcmeClient.class).baseUrl())
                    .isEqualTo("https://custom.test");
        });
```

This test proves `@ConditionalOnMissingBean` backs off when the application supplies its own bean.

### 14.2. Testing the disabling property

```java
contextRunner
        .withPropertyValues("acme.client.enabled=false")
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(AcmeClient.class);
        });
```

### 14.3. Testing when a dependency is absent from the classpath

Use `FilteredClassLoader` in tests to simulate a classpath missing the SDK:

```java
contextRunner
        .withClassLoader(new FilteredClassLoader(AcmeSdk.class))
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(AcmeClient.class);
        });
```

If the auto-configuration class has method signatures directly referencing optional types, isolate the configuration properly so the class is not loaded before the class condition is evaluated.

### 14.4. Testing a full application context

`ApplicationContextRunner` is great for unit testing individual auto-configurations. Alongside it, an integration test with a full application context confirms:

- The imports resource is actually packaged and discovered.
- Component scanning does not accidentally load the auto-configuration.
- Other auto-configurations collaborate properly.
- Application exclusions and properties apply as expected.

## 15. JAR packaging and resource merging

A common post-migration bug: `AutoConfiguration.imports` exists in source yet disappears or ends up partial inside an executable/uber JAR.

The cause is often a build tool packaging multiple dependency JARs into one archive and **overwriting resources with the same path** instead of appending their contents.

Example:

```text
dependency-a.jar:
  META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
    com.acme.autoconfigure.AcmeAutoConfiguration

dependency-b.jar:
  META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
    com.example.metrics.MetricsAutoConfiguration
```

If shading keeps only one resource, an entire set of auto-configurations vanishes.

### 15.1. Maven Shade Plugin

Configure a transformer to append the resource:

```xml
<transformer implementation=
    "org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>
        META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
    </resource>
</transformer>
```

The complete configuration sits inside the `transformers` section of the Maven Shade Plugin.

### 15.2. Gradle Shadow Plugin

With the Shadow plugin, append the imports resource:

```kotlin
tasks.shadowJar {
    append(
        "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports"
    )
}
```

Exact syntax can vary across plugin versions; check the DSL for the plugin version you use.

### 15.3. Inspecting resources inside the artifact

After building, inspect the JAR contents:

```bash
jar tf build/libs/acme-app.jar
```

Extract the imports file to verify:

```bash
jar xf build/libs/acme-app.jar \
  META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

For standard executable Spring Boot JARs, resources from dependencies live inside nested JARs under `BOOT-INF/lib` rather than being merged at root. Inspect the right artifact type and build style.

For shaded/uber JARs, verify the final resource includes every candidate from all required dependencies.

## 16. Diagnosing when auto-configuration fails to load

Common symptoms:

- Starter added to build, yet beans never appear.
- Application throws no errors, yet the client is not created.
- Property is configured, yet the condition fails to match.
- Auto-configuration class exists in source, yet is missing from the JAR.
- Works in the IDE, yet shaded JAR lacks certain beans.

Check in order:

1. Is the starter/autoconfigure dependency actually on the runtime classpath?
2. Is the imports resource at the exact path and packaged?
3. Are the class names in the file exact fully qualified names?
4. Was the class unintentionally component scanned or manually imported?
5. Which condition failed to match?
6. Are the property prefix, name, and value exact?
7. Is an optional dependency actually present?
8. Is there an exclusion via annotation or property?
9. Was the resource overwritten in a shaded JAR?
10. Does the Boot version support the registration mechanism the artifact uses?

### 16.1. Enabling the debug condition report

Run:

```bash
java -jar app.jar --debug
```

Spring Boot prints the condition evaluation report, showing which auto-configurations matched and which conditions failed.

This is a reliable way to distinguish:

- Class was never discovered.
- Class was discovered yet excluded by a condition.
- Another bean caused `@ConditionalOnMissingBean` to back off.
- A property condition was not satisfied.

If the auto-configuration class does not appear in the report at all, check resource registration and the classpath first.

### 16.2. Inspecting the imports file inside a dependency

With Maven, inspect a dependency JAR using:

```bash
jar tf ~/.m2/repository/com/acme/acme-spring-boot-autoconfigure/1.0.0/acme-spring-boot-autoconfigure-1.0.0.jar
```

With Gradle, locate the artifact in the corresponding dependency cache. Do not inspect only source files in the IDE; resources can be omitted during module publishing.

## 17. Common migration mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Boot 3 creates no beans from legacy library | Registered only under `EnableAutoConfiguration` in `spring.factories` | Switch to `AutoConfiguration.imports` |
| Boot 2.6 fails to discover new auto-config | Only the imports file exists | Keep `spring.factories` while still supporting 2.6 |
| Boot 2.7 loads duplicate candidate? | Same class listed in both files | Boot 2.7 deduplicates; check actual resources and classes |
| `@AutoConfiguration` annotation missing | Runtime/baseline older than Boot 2.7 | Use compatible `@Configuration` or raise baseline |
| Auto-config registered yet bean missing | Condition unmatched | Enable `--debug` and inspect properties/classpath |
| Auto-config loaded twice | Loaded via both imports and component scan/`@Import` | Remove redundant component scan or manual import |
| Shaded JAR missing some auto-configs | Resources at same path overwritten | Configure resource appending/merging |
| Boot 4 fails to compile packages | Modules/APIs modularized or relocated | Update dependencies and imports for Boot 4 |
| `EnvironmentPostProcessor` not discovered after upgrade | SPI key/package mismatches Boot line | Update class and `spring.factories` entry |
| Custom auto-config does not back off for app bean | Missing or misplaced `@ConditionalOnMissingBean` | Place condition appropriately in auto-configuration |

## 18. Migration strategy by target version

### 18.1. Projects supporting Boot 2.6 or earlier only

- Use `META-INF/spring.factories`.
- Register classes under the `EnableAutoConfiguration` key.
- Use `@Configuration` and ordering annotations present in the baseline version.
- Do not reference `@AutoConfiguration` if the minimum runtime is Boot 2.6.

### 18.2. Projects supporting Boot 2.7

- Create `AutoConfiguration.imports`.
- Switch top-level classes to `@AutoConfiguration`.
- Optionally keep the `spring.factories` entry to support Boot 2.6.
- Boot 2.7 supports both and deduplicates.
- Test on the exact lowest version declared supported.

### 18.3. Projects supporting Boot 3.x only

- Use `AutoConfiguration.imports`.
- Use `@AutoConfiguration`.
- Remove the `EnableAutoConfiguration` key from `spring.factories`.
- Retain any other SPI entries still needed.
- Update Jakarta namespaces, Java baseline, and compatible dependencies when upgrading from Boot 2.x.

### 18.4. Projects supporting Boot 4.x

- Continue using `AutoConfiguration.imports`.
- Audit Boot 4 module dependencies and packages.
- Check classes referenced in conditions, ordering, and exclusions.
- Check remaining `spring.factories` SPIs and their matching keys/packages.
- Consider releasing separate starter lines for Boot 3 and Boot 4 per migration guidance.

## 19. Practical migration workflow

When upgrading a starter from Boot 2.6 to 3.x, follow these steps:

### Step 1. List existing auto-configurations

Find the entry:

```text
org.springframework.boot.autoconfigure.EnableAutoConfiguration
```

in every `META-INF/spring.factories` in the module.

Record every listed class, including classes from submodules.

### Step 2. Create the new imports file

Create the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Place each auto-configuration class on its own line.

### Step 3. Update annotations

If the baseline is Boot 2.7+, use `@AutoConfiguration` on top-level classes. Keep `@Configuration` for ordinary nested/imported configurations.

If binary compatibility with Boot 2.6 must be maintained, verify which annotations/APIs actually exist in the lowest runtime.

### Step 4. Keep or drop legacy registration per support matrix

- Still supporting 2.6: keep the old key in `spring.factories`.
- Supporting 2.7+ only: drop the old key.
- Supporting 2.6 and 3.x: keep both resources while verifying binary compatibility.
- Supporting Boot 3/4: use imports and verify packages/modules separately per line.

### Step 5. Check other SPIs

Do not delete `spring.factories` if `FailureAnalyzer`, `EnvironmentPostProcessor`, or other extension points remain registered there.

### Step 6. Inspect the final artifact

Open the published/built JAR and confirm the imports resource is present with accurate contents. For shaded/uber JARs, verify the resource is appended.

### Step 7. Test across the version matrix

Run context tests on both the lowest and highest versions the library claims to support. Test registration, conditions, custom bean back-off, and optional dependencies.

## 20. Common misconceptions

| Statement | True or false? | Explanation |
|---|---|---|
| Boot 3 removed `spring.factories` completely | **False** | Only the auto-configuration registration key was removed; other SPIs may still use it |
| Boot 2.7 already dropped support for `spring.factories` | **False** | Still supported for transition, though deprecated |
| `AutoConfiguration.imports` is a properties file | **False** | Each line is a class name; no `key=value` format |
| One line holds a comma-separated list | **False** | Each class name sits on its own line |
| `@AutoConfiguration` existed in Boot 2.6 | **False** | The annotation was introduced in Boot 2.7 |
| Registering a class guarantees its beans are created | **False** | Conditions can still skip the configuration or beans |
| `@AutoConfiguration` replaces every `@Configuration` | **False** | It targets top-level auto-configs; regular configurations still use `@Configuration` |
| `@AutoConfigureAfter` dictates which bean constructor runs first | **False** | It controls auto-configuration definition processing order |
| You can component scan auto-configs instead of using imports | **Not recommended** | Auto-configs should load via imports and stay out of component scans |
| `@ConditionalOnMissingBean` is the same as `@Primary` | **False** | Conditionals decide bean registration; `@Primary` picks among candidates |
| Boot 2.7 deduplicates the two files automatically | **True** | When the same class appears in both old and new registrations |
| Boot 4 returned to `spring.factories` for auto-configs | **False** | Imports remains the auto-configuration registration mechanism |

## 21. Practical exercises

### Exercise 1. Migrating registration from Boot 2.6 to 2.7

A library contains:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.autoconfigure.AcmeAutoConfiguration
```

**Tasks:**

1. Create `AutoConfiguration.imports`.
2. Add the class FQCN on one line.
3. Switch the top-level class to `@AutoConfiguration` if baseline is 2.7+.
4. Run on Boot 2.7.
5. Verify the bean appears exactly once.

**Question:** Why can both files be kept during the transition period?

**Answer:** Boot 2.7 supports both legacy and new registrations while deduplicating duplicate candidates.

### Exercise 2. Moving to Boot 3

**Tasks:**

1. Remove the `EnableAutoConfiguration` key from `spring.factories`.
2. Keep `AutoConfiguration.imports`.
3. Retain other SPI keys if still used.
4. Run application context tests on Boot 3.

**Pass criteria:** auto-configuration is still discovered without relying on legacy registration.

### Exercise 3. Verifying @ConditionalOnMissingBean

Create an auto-configuration providing a default `AcmeClient`. Create user configuration supplying a custom client.

**Tasks:** test two cases:

- No user bean: default client is created.
- User bean present: default client backs off and the custom bean is used.

### Exercise 4. Checking shaded JARs

Create two modules, each with its own imports resource. Package them into one uber JAR.

**Question:** Why does only one auto-configuration appear?

**Answer:** The build tool may overwrite resources with identical paths. Configure appending/merging for the imports file.

### Exercise 5. Boot 4 migration

Take a Boot 3 starter and inspect:

- Packages of auto-configuration classes.
- Modules containing condition and properties APIs.
- Starter dependencies.
- SPI keys in `spring.factories`.
- The imports resource.
- Version matrix tests.

Do not change only parent/plugin versions; audit the modules and APIs the starter depends on.

## 22. Key takeaways

- Boot 1.x–2.6 registered auto-configurations via `META-INF/spring.factories` under the `EnableAutoConfiguration` key.
- Boot 2.7 introduced `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, supporting both old and new mechanisms while deduplicating candidates.
- `@AutoConfiguration` was introduced in Boot 2.7 to mark top-level auto-configurations.
- Boot 3 dropped the `EnableAutoConfiguration` key from `spring.factories`; other SPI keys were not automatically removed.
- Boot 4 continues using imports; watch for module/package migrations and starter dependencies.
- Each line in `AutoConfiguration.imports` is a fully qualified class name.
- Auto-configurations should be loaded via imports, not component scanning.
- `@ConditionalOnClass`, `@ConditionalOnMissingBean`, and `@ConditionalOnProperty` decide when configurations apply.
- `@AutoConfiguration(before/after)` and ordering annotations control auto-configuration processing order, not constructor execution order.
- When renaming referenced auto-configuration classes, consider `AutoConfiguration.replacements`.
- If building uber/shaded JARs, merge imports resources from dependencies.
- Use `ApplicationContextRunner` to test auto-configuration, conditions, user overrides, and optional classpaths.
- During migration, keep `spring.factories` for needed SPIs; do not delete the file merely because auto-configuration registration moved.
- Test against both the lowest and highest versions your starter claims to support.

When upgrading auto-configuration, clearly verify **the lowest Boot version to support, the registration file read by that version, the annotations/APIs available at runtime, and whether the resource is actually packaged inside the final artifact**. Those four checks determine whether Spring Boot discovers and configures your starter properly across each release line.

## 23. Official references

- [Spring Boot 2.7 Release Notes — Auto-configuration Registration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes)
- [Spring Boot 3.0 Migration Guide — Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
