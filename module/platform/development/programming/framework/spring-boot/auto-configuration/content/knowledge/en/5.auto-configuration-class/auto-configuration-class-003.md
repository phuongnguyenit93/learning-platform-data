# Splitting Configuration by Feature Instead of Bundling Every Integration into One Class

> **Context:** Spring Boot 3.3.x, Java 17+, in the **Auto-Configuration Class** section. This lesson explains how to design multiple narrowly scoped, independent auto-configurations with clear conditions. Examples use Spring Boot 3.3.13 with Maven so you can run and observe each feature yourself.

## 1. The Problem: One Configuration Class That Does Everything

When starting to build a library for multiple Spring Boot applications, it is tempting to write a single class:

```java
// Illustrative snippet of a design needing improvement; types are not declared here.
@AutoConfiguration
class EverythingAutoConfiguration {
    @Bean AuditService auditService() { /* ... */ }
    @Bean NotificationService notificationService() { /* ... */ }
    @Bean MetricsBridge metricsBridge() { /* ... */ }
    @Bean VendorClient vendorClient() { /* ... */ }
}
```

At first, bundling everything together seems convenient: fewer files, one place to look. However, once audit, notification, metrics, and vendor integration have different lifecycles, classpaths, and activation conditions, that class gradually introduces **unnecessary coupling**.

For example, you place a condition on the entire class:

```java
// Illustrative snippet: vendor condition applies to the ENTIRE class.
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.OptionalClient")
class EverythingAutoConfiguration {
    // All @Bean methods, even pure-Java audit,
    // are only evaluated when OptionalClient is present.
}
```

Result: applications that do not use the vendor also lose the audit feature. That is a mistake in setting condition boundaries, not a flaw of `@ConditionalOnClass`.

**Goal of splitting configuration:** if one feature is disabled, missing a dependency, or replaced by the application, other independent features can still operate normally.

## 2. Principle of Splitting by Feature

Instead of splitting by line count, ask: **"Can this feature be activated, configured, tested, and replaced independently?"**

Suppose a shared library has two features:
- **Audit:** produces business record entries when an event occurs.
- **Notification:** produces notifications for an event.

The two features have separate APIs, properties, and enable/disable policies; therefore, it makes more sense to write:

```text
AuditAutoConfiguration
  -> @ConditionalOnProperty(demo.audit.enabled)
  -> @Bean @ConditionalOnMissingBean(AuditService)

NotificationAutoConfiguration
  -> @ConditionalOnProperty(demo.notification.enabled)
  -> @Bean @ConditionalOnMissingBean(NotificationService)
```

Later, if there is a genuinely optional metrics integration, you can add a `MetricsAutoConfiguration` with its own `@ConditionalOnClass` without forcing Audit and Notification to require the metrics library as well.

### 2.1. Signs You Should Split

| Sign | Why split |
| --- | --- |
| Each group has different dependencies or classpath conditions | Missing an optional library should not drop the remaining groups |
| Separate enable/disable properties exist | Turning feature A on/off should not alter B |
| Applications may override beans for each group individually | `@ConditionalOnMissingBean` should check per concrete contract |
| Separate lifecycles or resource ownership exist | Shutdown/initialization/errors need management per real dependency |
| Separate test suites or release/compatibility schedules exist | A bug or upgrade in one adapter is easier to isolate |
| One group runs only in Servlet/Reactive/Batch contexts | Web conditions should not wrap neutral logic |
| One group uses a paid SDK or external infrastructure | Avoids accidentally enabling unexpected integrations |

Conversely, **do not split completely cohesive logic into dozens of auto-configurations just because a class is 100 lines long**. Multiple `@Bean` methods that genuinely belong to the same feature can stay in one class; if the parts share the same conditions and lifecycle, keeping them together remains easy to understand.

### 2.2. Choosing the Right Unit of Split

A good design unit typically has:
1. A **concisely expressible responsibility** (e.g., "provides the default audit client").
2. A consistent set of **activation conditions** (classpath, properties, runtime environment).
3. A **customization contract** (bean replacement, config properties, disable/exclude).
4. An **independent test suite**.
5. A clearly defined set of required and optional dependencies.

In Spring Boot, a single `AutoConfiguration.imports` file can list **multiple** auto-configuration classes. You do not need a new starter or a new imports file for every feature if they belong to the same library; module splitting depends on publishing needs.

## 3. Distinguishing the Three Organizational Levels

Do not confuse **feature**, **configuration class**, and **artifact**:

| Level | Example | Role |
| --- | --- | --- |
| API/core | `AuditService`, `NotificationService` | Defines functionality; can avoid Spring dependencies |
| Auto-configuration class | `AuditAutoConfiguration`, `NotificationAutoConfiguration` | Conditionally registers default beans for each feature |
| Artifact | `example-autoconfigure.jar`, `example-spring-boot-starter.jar` | Packages classes/metadata and conveniently pulls dependencies |

For a small library, multiple auto-configuration classes can live **together** in one `autoconfigure` artifact. For a large SDK, independent groups can split artifacts, starters, or even repositories; decide based on how users consume dependencies, not out of a preference for having many files.

### 3.1. Common Structure When Publishing a Library

```text
feature-core/
  AuditService.java
  NotificationService.java

feature-autoconfigure/
  AuditAutoConfiguration.java
  NotificationAutoConfiguration.java
  META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports

feature-spring-boot-starter/
  build.gradle or pom.xml
  (mostly declares dependencies)
```

Core holds contracts and independent logic; autoconfigure merely wires core into the ApplicationContext when appropriate; starter helps consumers pull in the required dependencies.

**Do not assume a starter is always necessary.** If your application only uses a small internal module, regular `@Configuration` may suffice. Auto-configuration is most valuable when you provide default behavior for **multiple applications to consume** without manual `@Import`s.

## 4. Spring Boot Mechanism: Splitting Classes Does Not Lose Automation

`@SpringBootApplication` includes `@EnableAutoConfiguration`. Boot's import mechanism reads the list of candidate auto-configurations from files at:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

You can declare:

```text
com.example.features.autoconfigure.AuditAutoConfiguration
com.example.features.autoconfigure.NotificationAutoConfiguration
```

Spring Boot evaluates the respective conditions of each configuration class in turn. This list declares **configuration candidates**, not a list of beans guaranteed to exist.

```text
@EnableAutoConfiguration
        |
        v
AutoConfiguration.imports
        |
        +------ AuditAutoConfiguration
        |          |
        |          +-- audit enabled?
        |          +-- missing AuditService bean?
        |          +-- register default AuditService if eligible
        |
        +------ NotificationAutoConfiguration
                   |
                   +-- notification enabled?
                   +-- missing NotificationService bean?
                   +-- register default NotificationService if eligible
```

Splitting into two classes provides **narrowly scoped condition evaluation**. When audit is disabled, `NotificationAutoConfiguration` is still evaluated normally as long as there is no dependency between the two groups.

### 4.1. Do Not Rely on the Application's Component Scanning

An auto-configuration library should be discovered by Boot through the imports file; **do not configure `@ComponentScan` covering both the application package and the library package** just to make the configuration "auto-run". That approach can pull unwanted internal beans/conditions into the context and behave differently when a consumer changes its base package.

In the complete example below, `DemoApplication` lives in `com.example.app`, while the auto-configurations live in `com.example.features.autoconfigure`. Two sibling package branches prevent the application's component scan from picking up autoconfigure classes directly; the imports file is the primary activation path.

### 4.2. Why Is `@ConditionalOnMissingBean` Still Needed?

Each feature must yield control to the application:

```java
@Bean
@ConditionalOnMissingBean(AuditService.class)
AuditService auditService() {
    return event -> "audit:" + event;
}
```

This is a fragment inside an auto-configuration, not a standalone Java file. When the application has already declared a matching bean of the same type, Boot does not register the corresponding default bean.

**Important separation:** feature A's bean should only check conditions relevant to A. Do not use a single "no bean from the library exists" condition that accidentally suppresses B as well.

Note that `@ConditionalOnMissingBean` inspects bean definitions already processed up to the moment the condition is evaluated. Auto-configuration is processed after application configuration via deferred import, fitting the back-off model. When two auto-configurations **both** compete for one bean type, explicit ordering may be needed; when they create two independent types, ordering usually does not need to be forced.

## 5. Runnable Demo: Two Independent Auto-Configurations

This section uses a single Maven project for ease of running. When publishing for real, you can split core/autoconfigure/starter as in section 3. The files below form a complete Spring Boot application.

### 5.1. Project Structure

```text
feature-split-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   └── features/
    │   │       ├── AuditService.java
    │   │       ├── NotificationService.java
    │   │       └── autoconfigure/
    │   │           ├── AuditAutoConfiguration.java
    │   │           └── NotificationAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/features/autoconfigure/
            └── FeatureAutoConfigurationTest.java
```

### 5.2. Maven POM

Create `pom.xml`:

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
    <artifactId>feature-split-demo</artifactId>
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

The parent manages Spring library versions compatible with Boot 3.3; `java.version` sets compilation to Java 17. JDK 17+ and Maven 3.x are required.

### 5.3. Pure Java APIs for Each Feature

Create `src/main/java/com/example/features/AuditService.java`:

```java
package com.example.features;

@FunctionalInterface
public interface AuditService {
    String record(String event);
}
```

Create `src/main/java/com/example/features/NotificationService.java`:

```java
package com.example.features;

@FunctionalInterface
public interface NotificationService {
    String send(String message);
}
```

The two interfaces are independent and do not import Spring. Both are only small APIs for the demo, not representative of production audit or notification systems (which might need asynchrony, persistence, retries, security, and error monitoring).

### 5.4. Audit Configuration

Create `src/main/java/com/example/features/autoconfigure/AuditAutoConfiguration.java`:

```java
package com.example.features.autoconfigure;

import com.example.features.AuditService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditService.class)
    AuditService auditService() {
        return event -> "audit:" + event;
    }
}
```

Audit has its own property `demo.audit.enabled`. When the key is absent, `matchIfMissing=true` allows creating the default bean. When the key equals `false`, the entire audit configuration is skipped. If the app already created its own `AuditService`, the default audit bean backs off.

### 5.5. Notification Configuration

Create `src/main/java/com/example/features/autoconfigure/NotificationAutoConfiguration.java`:

```java
package com.example.features.autoconfigure;

import com.example.features.NotificationService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.notification",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class NotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationService.class)
    NotificationService notificationService() {
        return message -> "sent:" + message;
    }
}
```

Notification does not depend on audit. It does not inject `AuditService`, does not check `demo.audit.enabled`, and is not gated by audit conditions. Both features can still be shipped in the same starter without being locked together operationally.

### 5.6. Declaring Both Configurations in One Imports File

Create the file at the exact path:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.features.autoconfigure.AuditAutoConfiguration
com.example.features.autoconfigure.NotificationAutoConfiguration
```

This is mandatory for auto-configuration discovery under Spring Boot 3.x conventions. If you forget to add a class to the imports file, that class may compile normally yet **not be automatically imported** in consuming applications.

Do not place the library's package under the app's component scan just to "fix" a forgotten imports entry. Fix the resource registration at the proper source.

### 5.7. Application Receiving Both Beans Without Manually Importing Configurations

Create `src/main/java/com/example/app/DemoApplication.java`:

```java
package com.example.app;

import com.example.features.AuditService;
import com.example.features.NotificationService;
import org.springframework.beans.factory.ObjectProvider;
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
    ApplicationRunner showFeatures(
            ObjectProvider<AuditService> audits,
            ObjectProvider<NotificationService> notifications) {
        return args -> {
            AuditService audit = audits.getIfAvailable();
            NotificationService notification = notifications.getIfAvailable();

            System.out.println(audit == null
                    ? "AUDIT=ABSENT"
                    : "AUDIT=" + audit.record("checkout"));
            System.out.println(notification == null
                    ? "NOTIFY=ABSENT"
                    : "NOTIFY=" + notification.send("checkout"));
        };
    }
}
```

`ObjectProvider` lets each feature be absent while the app still runs; that way we can observe independent enable/disable effects. In a real application, a caller using a feature should explicitly handle the optional case instead of assuming the bean always exists.

Run in the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

With both features enabled by default, the **two lines printed by `ApplicationRunner`** are:

```text
AUDIT=audit:checkout
NOTIFY=sent:checkout
```

Maven and Spring Boot also log startup output; this is not the entirety of stdout.

### 5.8. Disabling One Feature While Keeping the Other

Run with audit disabled:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.audit.enabled=false
```

Runner output lines:

```text
AUDIT=ABSENT
NOTIFY=sent:checkout
```

Run with notification disabled:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.notification.enabled=false
```

Output lines:

```text
AUDIT=audit:checkout
NOTIFY=ABSENT
```

The results show that one property does not drag down the other feature. If you used a single `EverythingAutoConfiguration` with class-level `@ConditionalOnProperty(prefix="demo.audit",...)`, the audit condition would suppress notification too—the exact modeling flaw that splitting classes solves.

### 5.9. Application Replacing Only the Audit Bean

Add the following method **inside `DemoApplication`**:

```java
@Bean
AuditService customAuditService() {
    return event -> "custom-audit:" + event;
}
```

This is a **fragment added to the class**, not a standalone Java file. Running with defaults, the runner prints:

```text
AUDIT=custom-audit:checkout
NOTIFY=sent:checkout
```

Thanks to `@ConditionalOnMissingBean(AuditService.class)`, the default audit bean is not created, while notification keeps its configuration. This is a critical check for shared APIs: consumers can customize parts individually.

To continue the original tests in the next section, **do not add the custom method yet**, or remove it after experimenting because the default test expects audit to produce `audit:checkout`.

## 6. Independent Testing with ApplicationContextRunner

Tests should prove isolation, not merely that both beans exist by default.

Create `src/test/java/com/example/features/autoconfigure/FeatureAutoConfigurationTest.java`:

```java
package com.example.features.autoconfigure;

import com.example.features.AuditService;
import com.example.features.NotificationService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            AuditAutoConfiguration.class,
                            NotificationAutoConfiguration.class));

    @Test
    void bothEnabledByDefault() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(AuditService.class);
            assertThat(context).hasSingleBean(NotificationService.class);
            assertThat(context.getBean(AuditService.class)
                    .record("checkout")).isEqualTo("audit:checkout");
            assertThat(context.getBean(NotificationService.class)
                    .send("checkout")).isEqualTo("sent:checkout");
        });
    }

    @Test
    void disablingAuditLeavesNotification() {
        runner.withPropertyValues("demo.audit.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AuditService.class);
                    assertThat(context).hasSingleBean(NotificationService.class);
                });
    }

    @Test
    void disablingNotificationLeavesAudit() {
        runner.withPropertyValues("demo.notification.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context).doesNotHaveBean(NotificationService.class);
                });
    }

    @Test
    void consumerAuditBeanOnlyOverridesAuditDefault() {
        runner.withUserConfiguration(CustomAuditConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context.getBean(AuditService.class)
                            .record("checkout"))
                            .isEqualTo("custom-audit:checkout");
                    assertThat(context).hasSingleBean(NotificationService.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomAuditConfiguration {

        @Bean
        AuditService customAuditService() {
            return event -> "custom-audit:" + event;
        }
    }
}
```

Run:

```bash
mvn test
```

The four tests verify:
- Both beans are present by default;
- Disabling audit removes only audit;
- Disabling notification removes only notification;
- The app can override audit without affecting notification.

`ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` **directly supplies the two classes**, which is great for testing condition logic. It does not prove that the `AutoConfiguration.imports` file in the JAR is packaged properly. To verify real discovery, run `DemoApplication` or write a consumer integration test.

### 6.1. Checking the Resource When Packaging

Run:

```bash
mvn package
jar tf target/feature-split-demo-0.0.1-SNAPSHOT.jar
```

In an executable JAR produced by the Boot Maven plugin, you should see the resource under:

```text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

In a regular library JAR, the resource path starts directly at `META-INF/spring/...`. If consumers do not receive beans even though runner tests pass, check this candidate-discovery metadata before suspecting code inside `@Bean`.

## 7. How to Split When Some Integrations Are Optional

Both features in the demo only use core APIs. In real libraries, each feature may depend on different external SDKs:

```text
AuditAutoConfiguration
  -> needs only feature-core

MailAutoConfiguration
  -> needs mail API/implementation

MetricsAutoConfiguration
  -> needs Micrometer MeterRegistry

WebServletAutoConfiguration
  -> runs only in a Servlet application

WebReactiveAutoConfiguration
  -> runs only in a Reactive application
```

**Wrong** design:

```java
// Bug illustration: missing mail SDK can block audit as well.
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.mail.MailClient")
class AllFeaturesAutoConfiguration {
    // creates audit, metrics, notification, mail...
}
```

Better-scoped design:

```java
@AutoConfiguration
public class AuditAutoConfiguration {
    // Only pure audit beans, with audit's own conditions.
}
```

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.mail.MailClient")
public class MailAutoConfiguration {
    // Only the mail integration in a module compiled against the mail SDK.
}
```

**The two fragments above only illustrate structure**, not standalone compilable Java files: methods/packages/imports are omitted and `com.vendor.mail.MailClient` is a hypothetical name.

When an integration is genuinely optional, consider:

1. Keep the **core APIs** that consumers use free of dependencies on optional SDKs.
2. Put `@ConditionalOnClass` on the **configuration class** or a nested static configuration to prevent the JVM from resolving `@Bean` signatures containing optional types too early.
3. Distinguish compile-only/optional dependencies of the autoconfigure module from runtime dependencies of the consumer. Maven `optional=true` prevents transitive propagation across the optional edge; Gradle `compileOnly` does not place the dependency on runtime from that edge.
4. Add **missing-classpath tests** with `FilteredClassLoader` to prove a missing SDK does not break other features.
5. Do not put optional SDK class names in superclasses, interfaces, or unguarded signatures of an auto-configuration class that is always loaded.
6. Clarify whether a feature is default-on or opt-in. Integrations with side effects (sending emails, connecting to external systems, scheduling jobs) often warrant intentional opt-in configuration.

### 7.1. Nested Class or Separate Auto-Configuration?

There are two ways to split:

**A. Split into multiple independent `@AutoConfiguration` classes**: makes sense when features have clear public boundaries, separate enable/disable controls, dependencies, and lifecycles; each class is listed in imports.

**B. One `@AutoConfiguration` containing separately guarded static nested `@Configuration(proxyBeanMethods=false)` classes**: makes sense when they are **implementation variants of the same feature** sharing an API contract, such as Servlet/Reactive clients or two classpath-based implementations.

Pattern B:

```java
@AutoConfiguration
public class DataClientAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sql.SqlClient")
    static class SqlClientConfiguration {
        // @Bean methods using only SQL SDK types.
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.nosql.NoSqlClient")
    static class NoSqlClientConfiguration {
        // @Bean methods using only NoSQL SDK types.
    }
}
```

This is **illustrative code, not standalone compilable**: imports and real methods are abbreviated, and the SDKs are hypothetical. In a real system, you must decide whether one or two beans should be created if both SDKs are present; `@ConditionalOnMissingBean`, a selection property, or splitting the auto-configuration may be needed.

**Selection rule:** if two branches represent **two independent public features**, prefer two auto-configurations. If they are merely **two implementations of one feature**, one auto-configuration with nested configurations can be cleaner.

## 8. Conditions and Configuration Boundaries

Splitting classes only truly helps when conditions are placed in the right spots too.

| Condition | Where to place | Warning |
| --- | --- | --- |
| `@ConditionalOnClass` | The adapter's auto-configuration class or separate nested config | Placing on too broad a class can drop other independent features |
| `@ConditionalOnProperty` | Feature class if the whole feature toggles together; method if only one bean is optional | Document the default value and what happens when the property is missing |
| `@ConditionalOnMissingBean` | The feature's default bean, by appropriate type/name/contract | Do not lump every feature under one shared "missing" condition |
| `@ConditionalOnBean` | Integrations that genuinely require an existing bean | Do not create artificial dependencies between two independent features |
| `@ConditionalOnWebApplication` | Config meaningful only in a web context | Separate Servlet/Reactive when APIs or conditions differ |
| `@ConditionalOnResource` | Features that truly require the corresponding resource | Verify real deployments include the resource |

### 8.1. Property Keys Should Be Named per Feature

Use separate namespaces:

```properties
demo.audit.enabled=true
demo.notification.enabled=false
demo.metrics.enabled=false
```

This lets consumers tune each branch individually; configuration docs do not have to document a single `demo.enabled` variable that unexpectedly governs everything.

If a feature has more parameters than an enable flag, you can create a `@ConfigurationProperties(prefix = "demo.audit")` class dedicated to that feature, registered via `@EnableConfigurationProperties` or an equivalent mechanism. Avoid one giant properties class holding every secret, retry, endpoint, and mode for every adapter if they operate independently.

### 8.2. When Is Auto-Configuration Ordering Needed?

For two unrelated features, do not declare arbitrary ordering relationships. If `NotificationAutoConfiguration` truly depends on a bean created by `AuditAutoConfiguration`, re-examine the architecture: is that dependency business-required? Only if yes should you consider `@AutoConfiguration(after = AuditAutoConfiguration.class)` or an appropriate `@ConditionalOnBean` condition.

`@AutoConfiguration(before/after)` governs the order of **applying auto-configurations / registering bean definitions**, not the order of instance initialization. Bean creation order depends on dependency injection and the Spring lifecycle.

If two auto-configurations both have `@ConditionalOnMissingBean(SomeClient.class)` and aim to provide different fallbacks, a before/after relationship can affect which one creates the default bean. Design a clear precedence rule and test combinations with and without app-provided beans.

## 9. When Multiple Auto-Configurations Share One Resource

Some libraries have shared components such as an HTTP transport, connection pool, or credential provider. Splitting features **does not mean duplicating resources**.

A suitable structure can be:

```text
TransportAutoConfiguration
  -> provides default Transport (if needed, if no bean exists yet)

AuditAutoConfiguration
  -> uses Transport when the audit feature actually needs it

NotificationAutoConfiguration
  -> uses Transport when the notification feature actually needs it
```

Both features inject one context-managed `Transport`, rather than each feature creating a separate pool or socket. However, avoid the opposite problem: if `TransportAutoConfiguration` always opens connections even when every feature is disabled, users still pay unnecessary startup and resource costs.

Decide explicitly:
- Is `Transport` always a public component of the starter, or only created when at least one feature needs it?
- Can consumers supply their own transport bean?
- Do you need lazy initialization, bean conditions, or per-feature registration branches?
- Where is transport closed, and could it accidentally be closed twice if the instance is shared?
- Should a connection error in one adapter fail fast for the whole app or degrade according to policy?

The answers depend on the library's contract. In particular, **do not arbitrarily use `@ConditionalOnBean` to block a feature just because a dependency bean is registered later**; bean conditions depend on definition processing order.

## 10. From Monolith to Multiple Auto-Configurations: Migration Process

Suppose you previously had:

```text
EverythingAutoConfiguration
  -> audit bean
  -> notification bean
  -> metrics bean
  -> vendor bean
```

The transition should proceed through clear steps:

### Step 1. Lock Down the Current Contract

Record public bean types/names, property keys, default enablement, behavior when optional SDKs are absent, actual ordering/conditions, imports registration paths, and how applications override beans.

If consumers excluded an old auto-configuration by FQCN, renaming the class can break or alter their exclusion behavior. This is a configuration-API compatibility change and must be treated as potentially consumer-impacting.

### Step 2. Identify Feature Boundaries

Tabulate each group:

| Group | Dependency | Flag | Default bean | Consumer override |
| --- | --- | --- | --- | --- |
| Audit | core | `demo.audit.enabled` | `AuditService` | `@Bean AuditService` |
| Notification | core | `demo.notification.enabled` | `NotificationService` | `@Bean NotificationService` |
| Metrics | Micrometer optional | `demo.metrics.enabled` | adapter/bridge | matching bean |
| Vendor | SDK optional | `demo.vendor.enabled` | client adapter | custom client/adapter |

Features that are merely internal helpers can stay in package-private configuration of the corresponding group rather than becoming public auto-configuration candidates.

### Step 3. Move Beans into Responsibility-Aligned Classes

Create each `@AutoConfiguration` with a clear name and purpose. Put shared feature conditions at class level; put exception conditions at method level. Audit unnecessary dependency injection between feature groups; remove fields or static initializers with side effects from configuration classes.

### Step 4. Update AutoConfiguration.imports

Publish each new candidate by fully qualified name. **Avoid publishing both the old monolith class and the new classes at the same time if both still register the same beans**, unless a compatibility mechanism has been explicitly designed and tested.

If renaming a published auto-configuration, Spring Boot supports `AutoConfiguration.replacements` metadata to express configuration renames for purposes such as exclusions/ordering. Still, **splitting one old class into multiple new classes is not a simple 1:1 rename mapping**: you must design a migration policy for each exclusion and bean, update release docs, and test consumers. Do not assume a rename line preserves all monolith behavior when splitting into independent features.

### Step 5. Write a Test Matrix

Do not only run the defaults. At minimum test:
- Both features enabled by default;
- Disabling A leaves B, disabling B leaves A;
- Disabling both leaves no default beans;
- Consumer creating bean A leaves B unchanged;
- Optional SDK for C absent does not break A/B;
- Excluding one new auto-configuration class affects only that feature;
- Imports/resources are packaged completely;
- Upgrading from the previous version does not unexpectedly alter public property/bean names.

### Step 6. Verify Against a Real Consumer Application

`ApplicationContextRunner` gives fast feedback on bean conditions, yet tests passing `AutoConfigurations.of(...)` directly **do not prove** candidate discovery from imports. Add an integration test that boots a consuming application or inspect JAR packaging to catch missing resources or typos in FQCNs.

### Step 7. Remove Obsolete Registration Paths

Once consumer compatibility is settled, remove the old import/scan paths, duplicate methods, and global conditions that inadvertently governed every feature. Keep one standard registration path to avoid bean definition conflicts.

## 11. What to Check After Splitting Configuration

### 11.1. Condition Report

When running the demo or a consumer, enable the report:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

In the condition report, look up each class:
- Did `AuditAutoConfiguration` match the audit condition?
- Did `NotificationAutoConfiguration` match the notification condition?
- Did a custom bean cause `@ConditionalOnMissingBean` to back off?
- Was a candidate excluded from the list before processing?

Use `--debug` for investigation. The report can include many unrelated configurations from other dependencies; do not infer a root cause from a generic log snippet.

### 11.2. Packaging Check

Maven example:

```bash
mvn package
jar tf target/feature-split-demo-0.0.1-SNAPSHOT.jar
```

Look for the imports resource and both corresponding `.class` files inside the JAR. When separating an autoconfigure artifact, verify that imports resides inside the exact JAR providing the configuration classes.

### 11.3. No Surprising Startup Side Effects

Splitting classes does not fix bugs where factory methods eagerly open network connections, run migrations, or send uncontrolled notifications. For each feature, verify:
- When the feature is disabled, are any beans/clients still initialized?
- When an optional SDK is missing, is any class containing that type loaded early by the JVM?
- When the app overrides a bean, does the default adapter stop being created?
- On configuration errors, does the message clearly identify the relevant feature and property?
- On teardown, are resources closed properly according to ownership?

### 11.4. Naming and Public API Scope

A name like `AuditAutoConfiguration` is meaningful when reading the condition report. Avoid `UtilsAutoConfiguration`, `EverythingAutoConfiguration`, or names that merely reflect a folder location rather than behavior.

In library code, keep beans/helpers serving only internal wiring at the minimum appropriate package and visibility. Prevent auto-configuration classes from being mistakenly picked up by the application's component scan. Most importantly, **the public contract seen by consumers** (bean types/names, properties, feature flags, exclusion mechanism) must be stable or have a clear migration path.

## 12. When You Do Not Need to Split into Multiple AutoConfigurations

**Case 1 — one feature comprising tightly coupled beans:** An HTTP client has a builder, codec, and interceptor that toggle together, share the same classpath, and share a lifecycle. You can keep them in one `HttpClientAutoConfiguration`, using methods or nested configurations for clarity.

**Case 2 — differing only in implementation:** One feature supports two implementations for the same API (e.g., JSON A / JSON B) while the user selects one. You can use conditional nested `@Configuration` classes inside one auto-configuration instead of creating two independent public features.

**Case 3 — configuration not reused outside the application:** If code belongs strictly to one application, internal `@Configuration` / `@Bean` classes are usually enough. There is no requirement to create a starter or imports file just to have more classes.

**Case 4 — splitting creates a dependency cycle:** If each configuration must inject a bean from the other to run, clarify the business boundaries and extract the shared part into a common API/service, or check whether they are truly two features. Do not distort structure with arbitrary `@AutoConfiguration(after=...)` ordering to mask a circular dependency.

## 13. Typical Errors and How to Fix Them

| Error | Consequence | Fix |
| --- | --- | --- |
| A vendor class-level `@ConditionalOnClass` wraps every feature | Missing vendor SDK drops unrelated features | Move the condition to the vendor adapter configuration |
| One `library.enabled` flag controls every feature | Consumers struggle to turn off a resource-heavy feature alone | Provide per-feature flags; use a global flag only when genuinely required |
| One shared `@ConditionalOnMissingBean` covers multiple types | Defining bean A unexpectedly suppresses bean B | Give each default bean a condition matching its own type contract |
| Using `@ComponentScan` on the library package | Beans are scanned outside the imports/condition pipeline | Publish auto-configurations via imports |
| Forgetting to list a new class in `AutoConfiguration.imports` | Class compiles, but consumers never see the default bean | Add the exact FQCN to the imports resource |
| Publishing old monolith class and new classes registering the same bean | Duplicate beans, order-dependent back-off, or conflicts | Keep one registration path or a controlled migration |
| Creating separate transport/pool per feature | Wastes resources, duplicates connections, hard to close | Share an infrastructure bean with clear ownership |
| Putting optional SDK types in signatures of an always-loaded config | Missing SDK can cause linkage errors before conditions run | Guard at class-level / nested configuration |
| Forcing order between two unrelated groups | Creates pointless coupling, harder upgrades | Only declare before/after for real dependencies |
| Stopping after default tests pass | Misses failures on disable/override/missing class | Add condition-matrix tests and consumer integration tests |
| Renaming configuration without considering old exclusions | Upgrading consumers experience different behavior | Plan compatibility; use migration metadata when appropriate |
| Splitting a small group into too many candidates | Harder to locate features, extra docs/test overhead | Keep beans sharing one activation contract in one feature config |

## 14. Self-Check Questions

**Question 1.** Audit and notification share a starter yet have two separate property flags. Does `demo.audit.enabled=false` remove notification?

**Answer:** No, provided notification's conditions depend only on that feature itself and have no mandatory business dependency on audit. That is the main benefit of splitting auto-configurations.

**Question 2.** `EverythingAutoConfiguration` has `@ConditionalOnClass(OptionalMetrics.class)` and also contains a pure-Java audit bean. What happens if the Metrics SDK is absent from the classpath?

**Answer:** The class-level condition fails to match, so the entire auto-configuration class is skipped, including audit. Move the metrics integration into a separate configuration guarded by its classpath condition.

**Question 3.** Why can a single `AutoConfiguration.imports` declare multiple classes?

**Answer:** The imports file is a list of candidate class names, not "one file per feature" or "one JAR per auto-configuration". One artifact can publish multiple independent auto-configurations.

**Question 4.** When a consumer creates its own `AuditService`, do you need to disable all of audit to avoid duplicate beans?

**Answer:** Usually no. If the default bean has `@ConditionalOnMissingBean(AuditService.class)`, it backs off for the consumer's bean; notification is unaffected.

**Question 5.** Should you put `@AutoConfiguration(after = AuditAutoConfiguration.class)` on Notification simply because Notification comes after Audit in the imports list?

**Answer:** No. Ordering should express a real dependency or precedence rule, not mirror file ordering.

**Question 6.** What does testing with `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` prove, and what does it not prove?

**Answer:** It tests bean/condition behavior for the explicitly supplied classes, but does not test discovery via the imports resource in the final artifact. You need to test a consuming app or JAR packaging.

**Question 7.** Should every `@Bean` get its own auto-configuration?

**Answer:** No. Split by **feature and activation contract**. Multiple beans that truly form one feature can reside in the same auto-configuration.

## 15. Takeaways and References

Good configuration splitting means **dividing along features that consumers can control independently**. Each feature should have its own classpath/property conditions, backing-off default beans, independent tests, clear diagnostics, and accurate entry in imports. There is no mandatory rule of one `@Bean` per class or one auto-configuration per starter.

Mental model to remember:

```text
Feature A -> condition A -> default bean A
Feature B -> condition B -> default bean B
Feature C -> optional SDK C -> condition C -> bean C

One group disabled / missing SDK / custom bean
              |
              v
      Independent groups remain active
```

**Official documentation:**

- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Condition Annotations: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.condition-annotations
- Spring Boot 3.3 — Using Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Boot 3.3 Javadoc — `AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3 Javadoc — `ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
