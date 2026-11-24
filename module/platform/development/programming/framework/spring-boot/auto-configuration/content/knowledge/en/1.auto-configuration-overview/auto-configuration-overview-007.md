# Scope of auto-configuration when building an application and when developing a shared library

> Context: Spring Boot 3.3.x, Java 17+. Topic under the **Auto-configuration Overview** section. The example below uses Spring Boot 3.3.13 to illustrate the 3.3 branch APIs; when deploying a real system, choose a still-supported Spring Boot version and verify library compatibility.

## 1. Key takeaway

After this lesson, you need to distinguish two roles:
- **Application builder**: uses existing auto-configurations, supplies custom configurations and beans when needed, and controls which configurations are applied.
- **Shared library developer**: provides a conditional auto-configuration so consuming applications receive default configuration when adding the dependency, while still being able to tune or replace it.

The deciding point is **configuration ownership**. The application decides its own final beans and behavior; the library should only supply safe defaults when conditions are met.

## 2. What does auto-configuration actually do?

When starting an application with `@SpringBootApplication` (which includes `@EnableAutoConfiguration`), Spring Boot locates auto-configuration classes published in dependencies, evaluates their conditions, and registers eligible beans. Common conditions are based on the classpath, existing beans, configuration properties, and application type.

```text
Application declares dependencies + application.properties + custom @Bean
                              |
                              v
@SpringBootApplication -> selects auto-configuration candidates
                              |
                              v
         Evaluate conditions (class / bean / property / web)
                              |
                +-------------+-------------+
                |                           |
          condition matches           does not match
                |                           |
         register default bean       skip that configuration
                |
        Actual ApplicationContext
```

A familiar example: with `spring-boot-starter-jdbc` and a suitable JDBC driver, Boot can configure `DataSource` and related JDBC beans, depending on properties and existing beans. If the application declares a matching `DataSource` itself, the corresponding default configuration usually **backs off**. You cannot infer that merely having a dependency guarantees every related bean will appear: other conditions may still fail.

Three mechanisms must be separated:
- **Component scanning** finds `@Component`, `@Service`, `@Configuration`, etc. within the package scope scanned by the application.
- **Auto-configuration** imports declared candidate configurations and filters them using conditions; it does not randomly scan every class in every JAR.
- **`@ConfigurationProperties`** maps values from `Environment` into a configuration object; this annotation alone is not enough to register the properties bean without an appropriate activation mechanism.

## 3. Scope of responsibility when you build an application

The application is where business requirements, real connections, security policies, caching, operations, and final customizations are defined. Therefore, you normally:

1. **Choose starters/dependencies** for the features you need; understand which libraries a starter brings onto the classpath.
2. **Configure via properties** when Boot already exposes suitable parameters, such as `spring.datasource.url` or a key published by a library.
3. **Declare custom beans** when you need a different implementation or policy. Check the back-off condition of the relevant auto-configuration before expecting the default bean to disappear.
4. **Exclude specific auto-configurations** when intentionally not using that mechanism, instead of indiscriminately removing an entire starter.
5. **Inspect condition results** when startup behavior is unexpected; classpath, properties, multiple beans of the same type, and processing order can all have an effect.

For example, an application can exclude default JDBC configuration if it manages the connection layer completely on its own:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

This is a **separate illustrative snippet** for an application whose dependencies include `DataSourceAutoConfiguration`, not combined with the `DemoApplication` demo in section 5. You can also use `spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration` when controlling via configuration. Exclude only after confirming the impact on dependent beans.

**There is no need to write a custom starter for configuration used in only one application.** For internal configuration, `@Configuration` and `@Bean` are usually clearer and easier to control. A configuration can be reused across several modules in the same application without needing to become a public auto-configuration.

## 4. Scope of responsibility when you develop a shared library

A library serves multiple applications with different dependencies and policies. A sound design typically has three layers of responsibility:

| Component | What does it contain? | Scope of responsibility |
| --- | --- | --- |
| `greeter-core` | API, models, plain implementation | Provides functionality; does not need Spring Boot to run business logic |
| `greeter-autoconfigure` | `@AutoConfiguration`, conditions, default beans, configuration properties | Connects core to Spring Boot when conditions match |
| `greeter-spring-boot-starter` | Convenient dependency declarations for users | Pulls required components onto the classpath; usually contains no business logic |

This is **how modules are split for real packaging**, not a requirement that every small library must have three JARs. The demo in section 5 puts the components in a single project to make the flow clear; when publishing a library, move them into their corresponding separate artifacts.

A good auto-configuration must have the following traits:

- **Conditional activation**: for example, `@ConditionalOnClass` when an integration dependency is present, `@ConditionalOnProperty` to toggle a feature, `@ConditionalOnWebApplication` when running only in a web environment.
- **Does not usurp application configuration control**: use `@ConditionalOnMissingBean` for replaceable default beans; namespace keys/properties under the library's own prefix.
- **Does not arbitrarily scan application components**: register the auto-configuration class via `AutoConfiguration.imports`; use explicit `@Import` if internal supporting configurations are needed, rather than broad `@ComponentScan`.
- **Does not rely on accidental ordering**: if ordering between auto-configurations is needed, use `@AutoConfiguration`'s `before`/`after` attributes; note that bean definition registration order differs from bean instantiation order.
- **Isolates optional integrations**: if an external library type is truly optional, avoid letting potentially absent types appear in method signatures loaded too early by the JVM; isolate them in a nested `@Configuration(proxyBeanMethods = false)` class guarded by `@ConditionalOnClass`.
- **Discoverable packaging**: provide the imports file at the exact path and properties metadata so IDEs assist users; write tests for enabled, disabled, override, and missing-dependency scenarios.

## 5. End-to-end example: an application using a library's auto-configuration

The demo uses **a single Maven project** so you can learn the mechanism without publishing JARs first. The application's package `com.example.app` is intentionally different from `com.example.greeter.autoconfigure`; as a result, auto-configuration is loaded through imports rather than accidentally "picked up" by the application's component scanning.

### 5.1. File structure

```text
greeter-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/
    │   │       ├── app/DemoApplication.java
    │   │       └── greeter/
    │   │           ├── GreeterClient.java
    │   │           └── autoconfigure/
    │   │               ├── GreeterProperties.java
    │   │               └── GreeterAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/greeter/autoconfigure/
            └── GreeterAutoConfigurationTest.java
```

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>greeter-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

Requires JDK 17+ and Maven 3.x. The core starter provides Spring Boot runtime and auto-configuration needed for the demo; the test starter provides JUnit 5 and AssertJ.

### 5.3. Spring-independent core

`src/main/java/com/example/greeter/GreeterClient.java`

```java
package com.example.greeter;

import java.util.Objects;

public final class GreeterClient {
    private final String prefix;

    public GreeterClient(String prefix) {
        this.prefix = Objects.requireNonNull(prefix, "prefix");
    }

    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
```

`GreeterClient` only defines greeting behavior; it knows nothing about `@Bean`, `ApplicationContext`, or how properties are read. Therefore it can be used and tested independently outside Spring.

### 5.4. Namespaced library properties

`src/main/java/com/example/greeter/autoconfigure/GreeterProperties.java`

```java
package com.example.greeter.autoconfigure;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "acme.greeter")
public record GreeterProperties(
        @DefaultValue("Xin chào") String prefix
) {
}
```

This object receives `acme.greeter.prefix` from application configuration. `@DefaultValue` supplies a value when the key is not set. To turn it into a bound bean, the auto-configuration in the next step uses `@EnableConfigurationProperties`.

### 5.5. Auto-configuration providing conditional defaults

`src/main/java/com/example/greeter/autoconfigure/GreeterAutoConfiguration.java`

```java
package com.example.greeter.autoconfigure;

import com.example.greeter.GreeterClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreeterClient.class)
@ConditionalOnProperty(
        prefix = "acme.greeter",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
@EnableConfigurationProperties(GreeterProperties.class)
public class GreeterAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreeterClient.class)
    GreeterClient greeterClient(GreeterProperties properties) {
        return new GreeterClient(properties.prefix());
    }
}
```

Analyzing each boundary:
- `@AutoConfiguration` marks this as a default configuration managed by Boot.
- `@ConditionalOnClass` evaluates the configuration only when `GreeterClient` is on the classpath. In the demo, this class is always present because it is in the same project; in a separate-JAR library, the condition is useful when a dependency is optional.
- `@ConditionalOnProperty` allows `acme.greeter.enabled=false` to turn off this *entire* configuration; if the key is absent, `matchIfMissing=true` enables it by default.
- `@EnableConfigurationProperties` registers and binds `GreeterProperties`.
- `@ConditionalOnMissingBean(GreeterClient.class)` registers the default client only when the context does not already have a matching bean of the same type supplied by the application.

Subtle point: when `acme.greeter.enabled` is turned off, auto-configuration **does not create the default bean**. That does not forbid the application from declaring `GreeterClient` itself. Similarly, `@ConditionalOnMissingBean` is a condition on the default bean, not a mechanism that locks or overrides application beans.

### 5.6. Publishing auto-configuration via metadata resource

Create the file with the **exact spelling and exact path**:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.greeter.autoconfigure.GreeterAutoConfiguration
```

Each line contains the fully qualified name of an auto-configuration class. Spring Boot 3.x uses this file to discover candidates when the application starts. Placing `@AutoConfiguration` on the class without publishing it via imports will **not make the library load automatically** in a consuming application. Do not rely on `spring.factories` with the `EnableAutoConfiguration` key as the primary registration mechanism in Spring Boot 3.x.

### 5.7. Consuming application uses the bean without manual import

`src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.greeter.GreeterClient;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printGreeting(GreeterClient client) {
        return args -> System.out.println(client.greet("Lan"));
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

With default configuration and no other `GreeterClient` bean, the application run log **contains the line**:

```text
Xin chào, Lan!
```

Spring Boot also prints startup logs depending on the environment; this is the output line from `ApplicationRunner`, not the entire stdout.

Try adding `src/main/resources/application.properties`:

```properties
acme.greeter.prefix=Chào mừng
```

Run again, and the line from the runner becomes:

```text
Chào mừng, Lan!
```

If replaced with `acme.greeter.enabled=false` without declaring another bean, `ApplicationRunner` requiring `GreeterClient` will not be satisfied; the application **fails to start due to a missing bean**. This is an intentional result, showing that the consuming application must handle the case where the feature is disabled, such as declaring the runner conditionally, instead of assuming the bean always exists.

### 5.8. Application takes control with its own bean

Reset `application.properties` to empty or remove the `enabled` key, then add inside `DemoApplication`:

```java
@Bean
GreeterClient customGreeterClient() {
    return new GreeterClient("Chào từ ứng dụng");
}
```

This is an **addition to the class in section 5.7**, not a standalone Java file. Because the application already has a bean of the same type, `@ConditionalOnMissingBean` prevents the library's `greeterClient(...)` method from registering the default bean. The runner receives the application-created bean and prints:

```text
Chào từ ứng dụng, Lan!
```

Architectural lesson: **starters supply defaults, applications have the right to override**. If a library registers beans unconditionally, duplicate beans, order dependence, or unpredictable configuration easily arise.

## 6. Decision matrix: where should configuration live?

| Need | Appropriate place | Why? |
| --- | --- | --- |
| Endpoint URL, credentials, retry policy specific to one service | `application.properties` / secret store / `@Configuration` in the application | Values and policies depend on the application's operating environment |
| Choose a custom implementation for the application | `@Bean` in the application | The app owns the decision; the library should back off |
| Repeating default client setup across multiple apps when dependency is present | Library auto-configuration | Reduces boilerplate and shares conventions |
| Sharing algorithms, framework-independent APIs | Core library | Easy to test, easy to reuse outside Spring |
| Letting users add one dependency to enable an integration suite | Starter | Simplifies dependency management on the application side |
| Need to toggle or tune a library feature | `@ConfigurationProperties` + conditions in auto-configuration | Provides a stable configuration contract for applications |
| Completely replacing how Spring Boot auto-configures a subsystem | Custom bean or excluding the exact auto-configuration | Intentional control, avoids overlapping configurations |

**Important boundary:** a library's auto-configuration should not force business policies, production addresses, secrets, job schedules, database migrations, or specific security decisions onto every application. Those require explicit customization or appropriate opt-in.

## 7. Conditions and ordering: what to understand before writing your own starter

| Mechanism | Meaning | Caution |
| --- | --- | --- |
| `@ConditionalOnClass(X.class)` | Class `X` is present on the classpath | For truly optional classes, isolate code whose signatures depend on that class |
| `@ConditionalOnMissingBean(X.class)` | No matching bean exists by type/name/search scope | Result depends on already-processed bean definitions; appropriate inside auto-configuration |
| `@ConditionalOnBean(X.class)` | Corresponding bean already exists | Verify the bean creation source and configuration ordering |
| `@ConditionalOnProperty` | Matches key/value in `Environment` | Define the default when the key is missing; a typo in the key can prevent matching |
| `@ConditionalOnWebApplication` | Activates only in the matching web application | Distinguish servlet and reactive when needed |
| `@AutoConfiguration(after = ...)` | Specifies processing order among auto-configurations | **Does not** guarantee bean instantiation order; dependency injection governs bean creation lifecycle |

A common mistake is placing `@ConditionalOnMissingBean` on ordinary application configuration and expecting it to always see every bean appearing later. Conditions evaluate against bean definitions already processed at that time. In libraries, registering via auto-configuration ensures bean conditions run after application bean definitions, fitting the back-off mechanism.

For optional integrations, you can use the following isolation pattern instead of declaring methods directly on an always-loaded configuration:

```java
@AutoConfiguration
public class OptionalClientAutoConfiguration {
    @org.springframework.context.annotation.Configuration(proxyBeanMethods = false)
    @org.springframework.boot.autoconfigure.condition.ConditionalOnClass(
            name = "com.vendor.OptionalClient"
    )
    static class OptionalClientConfiguration {
        // Place @Bean methods typed with com.vendor.OptionalClient here
        // in a module compiled against the vendor API.
    }
}
```

This is a **non-runnable illustrative outline**: bean code is omitted because it requires a concrete `com.vendor.OptionalClient` API. The main point is keeping signatures that depend on optional libraries inside configurations guarded by class conditions. For complex libraries, verify both classpath and API version compatibility.

## 8. Testing the auto-configuration contract with ApplicationContextRunner

Instead of only running the whole application, test the condition combinations a library user might encounter. Create `src/test/java/com/example/greeter/autoconfigure/GreeterAutoConfigurationTest.java`:

```java
package com.example.greeter.autoconfigure;

import com.example.greeter.GreeterClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreeterAutoConfigurationTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(GreeterAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenEnabled() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(GreeterClient.class);
            assertThat(context.getBean(GreeterClient.class).greet("Lan"))
                    .isEqualTo("Xin chào, Lan!");
        });
    }

    @Test
    void usesConfiguredPrefix() {
        runner.withPropertyValues("acme.greeter.prefix=Hello")
                .run(context -> assertThat(
                        context.getBean(GreeterClient.class).greet("Lan"))
                        .isEqualTo("Hello, Lan!"));
    }

    @Test
    void skipsDefaultWhenDisabled() {
        runner.withPropertyValues("acme.greeter.enabled=false")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(GreeterClient.class));
    }

    @Test
    void backsOffWhenApplicationProvidesClient() {
        runner.withUserConfiguration(UserGreeterConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(GreeterClient.class);
                    assertThat(context.getBean(GreeterClient.class).greet("Lan"))
                            .isEqualTo("Tự chọn, Lan!");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGreeterConfiguration {

        @Bean
        GreeterClient userGreeterClient() {
            return new GreeterClient("Tự chọn");
        }
    }
}
```

Run `mvn test`. These tests verify **4 contracts**: default present, property customization, disabled via property, and backing off for a user bean. `ApplicationContextRunner` builds isolated contexts so there is no need to start the full app. If the library depends on optional classes, add tests with `FilteredClassLoader` to simulate absent dependencies. Additionally, JAR packaging or consumer project tests must verify that the `AutoConfiguration.imports` path is actually present in the artifact: the runner explicitly specifies the auto-configuration class, so it **cannot by itself prove discovery via the imports file**.

## 9. Diagnosing "added a starter, yet the bean does not appear"

Check in order:

1. **Is the dependency on the runtime classpath?** A dependency only in test scope, transitively excluded, or of a different version can cause `@ConditionalOnClass` to fail.
2. **Is the imports file in the right location?** For self-written libraries, verify the JAR contains `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` and the exact class name.
3. **Which condition did not match?** Run the application with `--debug` (for example `mvn spring-boot:run -Dspring-boot.run.arguments=--debug`) to inspect the condition evaluation report; distinguish positive/negative matches. Enable debug only during investigation because the output is long.
4. **Does the app already have its own bean?** `@ConditionalOnMissingBean` may have backed off, or more than one candidate of the same type may make injection ambiguous.
5. **Is the property name/value wrong?** `enabled=false`, a typo in the prefix, or an overriding profile/environment variable can change condition or binding behavior.
6. **Was it excluded?** Check `@SpringBootApplication(exclude=...)` and `spring.autoconfigure.exclude`.
7. **Were package scanning and imports mixed?** An auto-configuration class picked up by manual scanning can register outside its expected lifecycle and cause hard-to-explain results.

If the application has Actuator and permits access to the appropriate endpoint, `/actuator/conditions` can also provide the condition report. Do not publicly expose diagnostic endpoints containing system details in production without access control.

For libraries, you can add `spring-boot-configuration-processor` as an annotation processor to generate configuration key metadata for IDEs; check `META-INF/spring-configuration-metadata.json` in the JAR. IDE metadata aids property discovery; it **is not** a bean creation condition and does not replace the imports file.

## 10. Common design mistakes and how to avoid them

- **Putting `@Component` or broad `@ComponentScan` in a starter**: the library accidentally picks up application beans or depends on package structure. Replace with imports + `@AutoConfiguration` + controlled `@Bean`/`@Import`.
- **Creating default beans without `@ConditionalOnMissingBean`**: hard for applications to replace, risking duplicate/ambiguous beans. Define types and override policies upfront.
- **Mixing business policy into library defaults**: a single timeout/retry/security setting does not fit every consumer. Provide properties, documented defaults, override mechanisms, and tests.
- **Treating "class on classpath" as sufficient**: a class is only one condition; properties, beans, and environment can also block activation.
- **Misunderstanding `@AutoConfiguration(after=...)` as creating beans in order**: it only affects configuration application order; dependency relationships and Spring's lifecycle govern instantiation order.
- **Using `@ConditionalOnClass` directly on a `@Bean` returning an optional dependency's type**: the JVM may need to load the type before the condition is evaluated; isolate with a conditional configuration class.
- **Writing only happy-path tests without testing back-off/disabling**: the initial version runs, but the library conflicts with consumers' custom beans.
- **Ignoring version compatibility**: auto-configuration is an integration layer with Spring Boot/Spring APIs and third-party libraries. Maintain a version matrix, track API changes, and test real consumers.

## 11. Self-check exercises

1. If an application adds the starter but wants to create `GreeterClient` itself, where should the configuration live? **In the application** via `@Bean`; the auto-configuration supplying the default must back off.
2. If you want every application with the dependency to receive a default client driven by properties, where should the logic live? **In the library's auto-configuration**, published via `AutoConfiguration.imports` and guarded by conditions.
3. If `acme.greeter.enabled=false` yet the application still defines `GreeterClient` itself, does the bean exist? **Yes**, because the property condition only prevents the library's automatic configuration part.
4. If a JAR has `@AutoConfiguration` without an imports file, will Boot automatically discover it as a standard auto-configuration? **No**; candidates must be registered properly (unless the application explicitly imports/scans that class by other means).
5. If `ApplicationContextRunner` tests pass yet the consuming application does not see the bean, what should be investigated first? **Classpath, imports metadata inside the JAR, condition report, and current configuration**.

## 12. Scope takeaway

When **building an application**, you choose the final dependencies, configuration, and beans according to actual runtime needs. When **building a shared library**, you design a set of conditional, replaceable defaults with clear properties discovered via metadata. Both sides collaborate through the auto-configuration mechanism; the application retains control.

Official documentation for deeper reference:
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot — Using Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Boot API — `@AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
