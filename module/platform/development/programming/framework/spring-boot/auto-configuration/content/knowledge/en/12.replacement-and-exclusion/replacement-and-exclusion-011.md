# Checking cascading impacts when removing a foundational bean needed by other configurations

## 1. Why can a single exclusion affect multiple configurations?

A foundational bean (infrastructure/foundation bean) is an object that other beans or configuration mechanisms rely on to operate: `DataSource` for JDBC/JPA, `TransactionManager` for transactions, `CacheManager` for caching, `ObjectMapper` for JSON, or a shared client provided by an internal starter.

When excluding the auto-configuration that creates a foundational bean, the impact **does not stop at one bean**. Configurations depending on that bean may:

1. **Stop matching conditions**: `@ConditionalOnBean(FoundationService.class)` evaluates to false, so the dependent bean **is not registered**. The application might still start, yet lose functionality.
2. **Fail at startup**: a bean is still registered and requires `FoundationService` via constructor or `@Bean` parameter; Spring finds no matching candidate and startup fails.
3. **Switch to a fallback branch**: another `@ConditionalOnMissingBean` or `@ConditionalOnProperty` configuration may begin matching, creating a default/replacement bean. This could be intentional or an unexpected change in behavior.
4. **Still use a user-supplied bean**: if the application supplies a foundational bean matching the same contract, consumers can keep working even though the auto-configuration providing the default was excluded.
5. **Continue starting up but fail at runtime**: optional dependencies (`ObjectProvider`, `Optional`) or code looking up beans on demand can delay detecting the missing dependency until the feature is invoked.

Therefore, checking cascading impacts requires looking at **the graph of beans and conditions**, rather than just checking whether the excluded configuration appears in the logs.

### Dependency model

```mermaid
flowchart TD
    A["FoundationAutoConfiguration"] -->|registers default| B["FoundationService"]
    B -->|@ConditionalOnBean| C["DependentService (conditional)"]
    B -->|required @Bean parameter| D["StrictConsumerService"]
    B -->|optional dependency| E["Optional consumer"]
    X["Exclude FoundationAutoConfiguration"] -.->|loses default| B
    B -.->|absent| F["C: not registered"]
    B -.->|absent| G["D: startup failure"]
    B -.->|absent| H["E: branch without dependency"]
    U["User bean with same contract"] -->|can replace default| B
```

The diagram illustrates **possible branches**. Merely excluding `FoundationAutoConfiguration` **does not necessarily** make `FoundationService` vanish if that bean is still supplied from elsewhere.

## 2. Identifying precisely what is being excluded

### 2.1. Excluding an auto-configuration does not mean deleting beans by type

Spring Boot lets you exclude an auto-configuration class, for example:

```java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class Application {
}
```

This is an illustrative snippet and requires importing `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration` along with `org.springframework.boot.autoconfigure.SpringBootApplication`. Another option is configuring:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Or, when specifying by string in Java:

```java
@SpringBootApplication(
    excludeName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class Application {
}
```

All three approaches state that **Spring Boot does not apply the named auto-configuration** via the auto-configuration import mechanism. They **do not delete** a `DataSource` separately declared by the application; nor do they mean all JDBC/JPA-related auto-configurations are automatically excluded by name.

Key points to remember:

- `exclude` and `excludeName` on `@SpringBootApplication`, or `spring.autoconfigure.exclude`, target **auto-configuration candidates**, not arbitrary `@Configuration` or `@Bean` definitions.
- Excluding a class does not remove libraries from the classpath. `@ConditionalOnClass` in other configurations can still match.
- A bean of the same type provided by user configuration, another starter, or a parent context can still exist.
- Excluding an auto-configuration can drop **multiple beans supplied by that class or its nested configurations**, not just the single bean name you are watching.
- Do not treat tweaking `@Order` numbers or adding `@DependsOn` as a way to "restore" an excluded bean definition. They solve ordering problems; they do not recreate an excluded configuration.

### 2.2. Replacing a default bean is a different mechanism

Starter configurations commonly use:

```java
@Bean
@ConditionalOnMissingBean(FoundationService.class)
FoundationService foundationService() {
    return new FoundationService("default");
}
```

If the user registers a matching `FoundationService`, the default above **backs off**, while other auto-configurations can still use the user's bean. This is a more stable extension style if the goal is merely to **replace how a foundational bean is built**.

**Only exclude the entire auto-configuration** when you truly want to disable the capability it provides and have reviewed its related consumers. If you only want to change connection settings, serializers, cache backends, or bean implementations, first look for customization APIs, properties, or bean overrides supported by the library.

### 2.3. Do not confuse the three states

| State | Provider auto-configuration | Foundational bean in context | Possible consequence |
| --- | --- | --- | --- |
| Normal default | Present, condition matches | Default exists | Consumers keep using default |
| Provider excluded, no replacement | Absent | Absent | Conditional consumers skipped; required consumers may fail |
| Provider excluded, user bean exists | Absent | Custom bean exists | Conditional consumers can keep working |
| Provider present, `@ConditionalOnMissingBean` backs off | Present, default method does not match | Custom bean exists | Other beans in the same configuration can still register |

**Inspect actual beans by type, name, and qualifier**, rather than only checking whether the auto-configuration class was loaded.

## 3. Three forms of cascading impact to distinguish

### 3.1. "Silent feature loss" due to `@ConditionalOnBean`

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class DependentAutoConfiguration {

    @Bean
    @ConditionalOnBean(FoundationService.class)
    public DependentService dependentService(FoundationService foundation) {
        return new DependentService("uses:" + foundation.origin());
    }
}
```

This is an illustrative snippet, assuming the types are already defined. If no `FoundationService` bean exists when the condition is evaluated, Spring **does not register** `dependentService`. Since no factory method needs to be invoked, the application may start successfully without `DependentService`.

Important: `@ConditionalOnBean` checks bean definitions processed up to that moment. In auto-configurations, declaring `after = FoundationAutoConfiguration.class` ensures the consumer configuration is processed **after** the provider configuration, though it does not guarantee instance creation in that order. User-declared beans are normally processed before auto-configurations.

### 3.2. "Startup failure" due to required dependencies

```java
@Bean
StrictConsumerService strictConsumerService(
        FoundationService foundationService) {
    return new StrictConsumerService(
            "strict:" + foundationService.origin());
}
```

When this bean is still registered without `FoundationService`, Spring cannot resolve the mandatory parameter. A common root cause is `NoSuchBeanDefinitionException`, wrapped inside `UnsatisfiedDependencyException` or a bean creation exception depending on the path.

Adding `@DependsOn("foundationService")` **does not fix** an absent bean. It only enforces that a bean of that name initializes first; if no bean of that name exists, it still fails.

### 3.3. "Behavior change" due to fallbacks or optional dependencies

A consumer can proactively handle a missing foundational bean:

```java
@Bean
ReportingService reportingService(
        ObjectProvider<FoundationService> provider) {
    FoundationService foundation = provider.getIfAvailable();
    return foundation == null
            ? new ReportingService("offline")
            : new ReportingService("online:" + foundation.origin());
}
```

This is an illustrative snippet with an undefined `ReportingService`, requiring `import org.springframework.beans.factory.ObjectProvider`. The consumer **still registers**, switching to `offline` mode. This is only valid if the business contract genuinely allows running without that foundation.

In another configuration, `@ConditionalOnMissingBean(FoundationService.class)` may begin matching and supply a fallback; verify whether the fallback uses the right data, environment, security policy, or transaction semantics.

**A successful startup is not enough to conclude safety**: you might silently lose a consumer, activate an unwanted fallback, or only fail on the first request/job.

## 4. Runnable example with Spring Boot 3.3.5 and Java 17+

We build an application with two auto-configurations:

- `FoundationAutoConfiguration` creates `FoundationService("default")` when the application does not already have a bean of that type.
- `DependentAutoConfiguration` creates `DependentService` **when `FoundationService` exists**; it also includes a `StrictConsumerService` toggled by a property to simulate a mandatory dependency.

The application also allows declaring a custom foundational bean. We run **the same JAR** with exclude/custom flags to observe cascading impacts directly.

### 4.1. Project structure

```text
cascade-check-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── demo/
    │   │       ├── api/
    │   │       │   ├── FoundationService.java
    │   │       │   ├── DependentService.java
    │   │       │   └── StrictConsumerService.java
    │   │       ├── app/
    │   │       │   └── DemoApplication.java
    │   │       └── autoconfigure/
    │   │           ├── FoundationAutoConfiguration.java
    │   │           └── DependentAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/demo/app/
            └── DependencyCascadeTests.java
```

The auto-configuration classes lie **outside** the `demo.app` scan package and are loaded by Spring Boot via `AutoConfiguration.imports`. This reflects Spring Boot 3.x starter mechanics rather than accidentally component-scanning auto-configuration classes.

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>cascade-check-demo</artifactId>
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

### 4.3. Three data types in `demo.api`

**`src/main/java/demo/api/FoundationService.java`**

```java
package demo.api;

public record FoundationService(String origin) {
}
```

**`src/main/java/demo/api/DependentService.java`**

```java
package demo.api;

public record DependentService(String description) {
}
```

**`src/main/java/demo/api/StrictConsumerService.java`**

```java
package demo.api;

public record StrictConsumerService(String description) {
}
```

We use Java 17 `record` types so outputs are easy to inspect. The records hold no Spring logic themselves; bean creation and wiring live in the configuration classes.

### 4.4. Provider: `src/main/java/demo/autoconfigure/FoundationAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.FoundationService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FoundationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FoundationService.class)
    public FoundationService foundationService() {
        return new FoundationService("default");
    }
}
```

The default bean has two characteristics: it depends on **the auto-configuration being applied**, and it backs off if a matching `FoundationService` already exists. When the entire `FoundationAutoConfiguration` is excluded, this factory method never gets a chance to create the default.

### 4.5. Consumer: `src/main/java/demo/autoconfigure/DependentAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.DependentService;
import demo.api.FoundationService;
import demo.api.StrictConsumerService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class DependentAutoConfiguration {

    @Bean
    @ConditionalOnBean(FoundationService.class)
    public DependentService dependentService(
            FoundationService foundationService) {
        return new DependentService(
                "uses:" + foundationService.origin());
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "strict",
            havingValue = "true")
    public StrictConsumerService strictConsumerService(
            FoundationService foundationService) {
        return new StrictConsumerService(
                "strict:" + foundationService.origin());
    }
}
```

The two consumers **react differently** to the absence of the foundational bean:

- `dependentService()` has `@ConditionalOnBean`, so it automatically **does not register** when the foundational bean is missing.
- `strictConsumerService()` **only** has the property condition `demo.strict=true`; when the property is enabled and the foundational bean is missing, Spring still attempts to create the bean and **fails due to the required dependency**.

`@AutoConfiguration(after = FoundationAutoConfiguration.class)` orders bean definition processing so `@ConditionalOnBean` sees the provider when the provider is present. It **does not** cause Spring to conjure up `FoundationService` when the provider is excluded.

### 4.6. Registering auto-configuration candidates

Create the file at exact path **`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**:

```text
demo.autoconfigure.DependentAutoConfiguration
demo.autoconfigure.FoundationAutoConfiguration
```

In the example, we deliberately list the consumer before the provider in the file. Spring Boot orders auto-configuration application by `after` metadata; it does not derive bean initialization order from line positions in this file.

### 4.7. Main application: `src/main/java/demo/app/DemoApplication.java`

```java
package demo.app;

import demo.api.DependentService;
import demo.api.FoundationService;
import demo.api.StrictConsumerService;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "provide-custom-foundation",
            havingValue = "true")
    public FoundationService customFoundationService() {
        return new FoundationService("custom");
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {

            FoundationService foundation =
                    context.getBeanProvider(FoundationService.class)
                            .getIfAvailable();

            DependentService dependent =
                    context.getBeanProvider(DependentService.class)
                            .getIfAvailable();

            StrictConsumerService strict =
                    context.getBeanProvider(StrictConsumerService.class)
                            .getIfAvailable();

            System.out.println("foundation=" +
                    (foundation == null ? "none" : foundation.origin()));

            System.out.println("dependent=" +
                    (dependent == null ? "none" : dependent.description()));

            System.out.println("strict=" +
                    (strict == null ? "none" : strict.description()));
        }
    }
}
```

The user-declared bean via `customFoundationService()` only appears when `demo.provide-custom-foundation=true`. When that bean appears, `@ConditionalOnMissingBean(FoundationService.class)` in the provider auto-configuration backs off; if the provider auto-configuration was excluded, the custom bean still exists because it belongs to the application.

### 4.8. Building and running four scenarios

Requires JDK 17+, Maven, and network access to download dependencies on first build. In `cascade-check-demo`:

```bash
mvn -q test
mvn -q -DskipTests package
```

**Scenario A — no exclude: both default provider and consumer are present**

```bash
java -jar target/cascade-check-demo-0.0.1-SNAPSHOT.jar --spring.main.banner-mode=off --logging.level.root=OFF
```

Program stdout lines:

```text
foundation=default
dependent=uses:default
strict=none
```

`FoundationAutoConfiguration` creates the default foundational bean; `DependentAutoConfiguration` sees that bean and supplies `DependentService`. The strict bean is not registered because the property is not enabled.

**Scenario B — exclude provider, no replacement bean declared**

```bash
java -jar target/cascade-check-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=demo.autoconfigure.FoundationAutoConfiguration --spring.main.banner-mode=off --logging.level.root=OFF
```

Program stdout lines:

```text
foundation=none
dependent=none
strict=none
```

`FoundationAutoConfiguration` is excluded, and `FoundationService` is not supplied elsewhere. `@ConditionalOnBean` on the consumer does not match, so `DependentService` also disappears: this is a **silent cascading impact**. The application still starts cleanly.

**Scenario C — exclude provider, but provide custom foundational bean**

```bash
java -jar target/cascade-check-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=demo.autoconfigure.FoundationAutoConfiguration --demo.provide-custom-foundation=true --spring.main.banner-mode=off --logging.level.root=OFF
```

Stdout lines:

```text
foundation=custom
dependent=uses:custom
strict=none
```

Even though the default provider was excluded, the application provides `FoundationService("custom")`, so the conditional consumer continues working. This illustrates **replacing according to the contract rather than merely deleting the default**.

**Scenario D — exclude provider while enabling required consumer**

```bash
java -jar target/cascade-check-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=demo.autoconfigure.FoundationAutoConfiguration --demo.strict=true --spring.main.banner-mode=off
```

**Expected:** the application **fails to start**, because `strictConsumerService(FoundationService foundationService)` needs a bean that the context lacks. Startup logs typically report a bean creation / unresolvable `FoundationService` failure, possibly featuring `UnsatisfiedDependencyException` with root cause `NoSuchBeanDefinitionException`. **Do not expect a verbatim fixed stack trace**, as messages and cause chains vary across environment versions.

This scenario differs from B: both lack the foundational bean, yet B starts while D fails. The difference lies in **each consumer's dependency contract**, not in the exclusion mechanism.

### 4.9. Result matrix

| Scenario | Default provider | Custom bean | `DependentService` | `StrictConsumerService` | Context |
| --- | --- | --- | --- | --- | --- |
| A. Default | Present | Absent | Present | Absent (property false) | Starts |
| B. Exclude provider | Absent | Absent | Absent (condition false) | Absent (property false) | Starts, missing functionality |
| C. Exclude + custom bean | Absent | Present | Present, uses custom | Absent (property false) | Starts |
| D. Exclude + strict=true | Absent | Absent | Absent | Factory needs missing bean | **Startup fails** |
| E. No exclude + strict=true | Present | Absent | Present | Present, uses default | Starts |
| F. Exclude + custom + strict=true | Absent | Present | Present, uses custom | Present, uses custom | Starts |

Scenarios E and F are extra checks ensuring the strict consumer is not accidentally filtered out by its own configuration when the foundational bean actually exists.

## 5. Automated testing of cascading impacts with `ApplicationContextRunner`

For starters, test **key bean states inside the context**, rather than just asserting whether the program runs. `ApplicationContextRunner` lets you build small contexts with the exact set of auto-configurations and user-supplied beans.

Below is **one complete Java test file**, matching `spring-boot-starter-test` declared in `pom.xml`. Create **`src/test/java/demo/app/DependencyCascadeTests.java`**:

```java
package demo.app;

import demo.api.DependentService;
import demo.api.FoundationService;
import demo.api.StrictConsumerService;
import demo.autoconfigure.DependentAutoConfiguration;
import demo.autoconfigure.FoundationAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class DependencyCascadeTests {

    private final ApplicationContextRunner bothAutoConfigs =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            FoundationAutoConfiguration.class,
                            DependentAutoConfiguration.class));

    @Test
    void bothPresentCreatesDependentService() {
        bothAutoConfigs.run(context -> {
            assertThat(context).hasSingleBean(FoundationService.class);
            assertThat(context).hasSingleBean(DependentService.class);
            assertThat(context).doesNotHaveBean(StrictConsumerService.class);

            assertThat(context.getBean(FoundationService.class).origin())
                    .isEqualTo("default");
            assertThat(context.getBean(DependentService.class).description())
                    .isEqualTo("uses:default");
        });
    }

    @Test
    void missingProviderAlsoRemovesConditionalConsumer() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        DependentAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(FoundationService.class);
                    assertThat(context).doesNotHaveBean(DependentService.class);
                    assertThat(context).hasNotFailed();
                });
    }

    @Test
    void customProviderRestoresConsumer() {
        bothAutoConfigs
                .withBean(FoundationService.class,
                        () -> new FoundationService("custom"))
                .run(context -> {
                    assertThat(context).hasSingleBean(FoundationService.class);
                    assertThat(context).hasSingleBean(DependentService.class);
                    assertThat(context.getBean(FoundationService.class).origin())
                            .isEqualTo("custom");
                    assertThat(context.getBean(DependentService.class)
                            .description())
                            .isEqualTo("uses:custom");
                });
    }

    @Test
    void requiredConsumerWithoutProviderFailsStartup() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        DependentAutoConfiguration.class))
                .withPropertyValues("demo.strict=true")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .isNotNull();
                });
    }

    @Test
    void requiredConsumerWithProviderStarts() {
        bothAutoConfigs
                .withPropertyValues("demo.strict=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(StrictConsumerService.class);
                    assertThat(context.getBean(StrictConsumerService.class)
                            .description())
                            .isEqualTo("strict:default");
                });
    }
}
```

Run:

```bash
mvn -q test
```

When all five tests pass, you have verified the branches: default, missing provider, custom provider, required dependency causing failure, and required dependency with provider.

**Limitation to understand clearly:** the "missing provider" test above simulates the effect by **omitting `FoundationAutoConfiguration` from the context**. It accurately tests consumer logic when the foundational bean is absent, yet **it is not a direct integration test of the `spring.autoconfigure.exclude` property**. The JAR commands in Section 4.8 separately test `SpringApplication`'s actual exclusion path. Both kinds of testing complement each other.

If broader tests covering environment configuration, auto-configuration imports, and the real startup path are needed, use `@SpringBootTest` with isolated properties/profiles or run the application in an integration test environment, then verify beans and business outcomes.

## 6. Cascading review workflow in real projects

Before excluding a foundational bean or an entire auto-configuration, build a checklist based on **actual consumers**:

### Step 1 — identify provider and contract

Record:

- **Which bean** is expected to vanish: type, bean name, qualifier, and contract interface.
- **Who provides it**: which auto-configuration, `@Bean`, or application configuration.
- **Creation conditions**: `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, `@ConditionalOnBean`; whether conditions sit at the **class** level or per **`@Bean`**.
- **Are there replacement paths**: user bean, bean from another starter, fallback, or parent context.
- **How is it excluded**: `@SpringBootApplication(exclude=...)`, `excludeName`, `spring.autoconfigure.exclude`, or disabled via a starter-provided property.

Do not infer "removes bean X" from an auto-configuration class name: that class may create multiple beans, some of which are foundational dependencies for the rest.

### Step 2 — follow direct and indirect dependency edges

Check each consumer across these mechanisms:

| How does the consumer use the foundational bean? | When the foundational bean vanishes | Verification |
| --- | --- | --- |
| Constructor injection / mandatory `@Bean` parameter | May fail bean creation if consumer still registers | Test context failure and root cause |
| `@ConditionalOnBean` | Consumer bean/config may not register | Assert absence and business consequence |
| `@ConditionalOnSingleCandidate` | May stop matching if no single eligible candidate remains | Assert candidate list and outcome |
| `@ConditionalOnMissingBean` | Fallback may start registering | Assert new default bean type and config |
| `ObjectProvider` / `Optional` | Consumer may switch branches or fail lazily upon lookup | Exercise both with/without provider branches |
| `@DependsOn("name")` | If named bean does not exist, consumer initialization can fail | Assert lifecycle and exact bean name |
| Consumer calls `ApplicationContext.getBean(...)` at runtime | May start up and fail at usage time | Integration test real business path |
| Consumer also has `@ConditionalOnClass` | Classpath does not change on exclude, so class condition may still match | Inspect bean conditions and actual dependencies |

After finding consumer B, check **who depends on B**. This finds **transitive impacts** A → B → C. For example, removing `FoundationService` makes `DependentService` vanish, causing another `@ConditionalOnBean(DependentService.class)` to stop matching.

Not every dependency edge leads to a startup error. Document **intentionally skipped beans**, **new fallback beans**, **changed behavior**, **startup failures**, or **runtime errors**.

### Step 3 — inspect condition evaluation order

With `@ConditionalOnBean`/`@ConditionalOnMissingBean`, conditions are evaluated against **bean definitions processed up to that point**. If provider and consumer live in separate auto-configurations, declare the proper metadata:

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class DependentAutoConfiguration {
    // Consumer bean conditions.
}
```

The `after` metadata ensures the consumer's condition sees the provider when the provider auto-configuration is present. However, it **does not turn an excluded provider into an existing one** and does not guarantee instantiation order.

If a bean still appears missing despite the provider being declared, also check `@Bean` declared return types, generic types, names/qualifiers, other conditions, and context hierarchy. A bean implementation existing in Java source does not mean its bean definition was registered.

### Step 4 — run a before-and-after matrix

At minimum, distinguish:

1. Baseline: default foundational bean present.
2. Exclude: default provider absent, no replacement.
3. Custom: custom foundational bean present, auto-configuration active while default backs off.
4. Exclude + custom: default provider gone, yet contract bean still present.
5. Corresponding required/optional consumer configurations.
6. Actual business paths: requests, scheduled jobs, or message handlers still operate as intended.

For each row, record **whether the context starts**, **bean counts by type/name**, **which conditions matched**, **which consumers appeared**, **which fallbacks appeared**, and **business outcomes**. Do not just assert no exceptions.

### Step 5 — use the condition report to trace causes

To view the **Condition Evaluation Report**, you can start Spring Boot with:

```bash
java -jar target/cascade-check-demo-0.0.1-SNAPSHOT.jar --debug
```

When using Spring Boot Actuator with endpoints properly configured, condition details are visible via `/actuator/conditions`. This endpoint **does not imply public access by default**; configure exposure and security per application policy.

Look in the report for:

- Was the provider auto-configuration excluded, or did a condition simply not match?
- Did `@ConditionalOnBean` on the consumer fail to match because a bean was not seen?
- Did `@ConditionalOnMissingBean` on a new fallback start matching?
- Did another configuration still match `@ConditionalOnClass` yet fail due to missing real dependencies?
- Was the custom bean registered with the right type, name, and qualifier?

Distinguish a **"condition negative match"** (normal registration filtering) from a **"bean creation failure"** (instance creation failing on unresolved dependencies). Do not conflate the two even when both trace back to a missing foundation.

### Step 6 — put checks into regular tests

A starter test suite should protect at least three contracts:

- **Back-off**: default provider yields properly when a custom bean exists; no extra ambiguous bean is created.
- **Graceful absence**: if the foundation is optional, the consumer does not register or switches to fallback **intentionally**.
- **Required dependency**: if the foundation is mandatory, a clear startup failure or precise activation condition occurs rather than silently skipping.

For transitive dependencies, verify downstream beans and real usage behavior; avoid tests that only assert a foundational bean is gone while ignoring B/C that rely on it.

## 7. How to fix unintended cascading impacts

**Case A — only want to swap an implementation while keeping the infrastructure.** Do not exclude the provider auto-configuration if it also creates shared components. Declare a custom bean matching the supported contract and let the `@ConditionalOnMissingBean` default back off. Check bean counts to avoid multiple candidates of the same type.

**Case B — consumer makes no sense without the foundation.** Place `@ConditionalOnBean(FoundationService.class)` on the consumer class or `@Bean`. If the class also holds other beans independent of the foundation, put the condition **on each dependent bean** to avoid losing extra capabilities.

**Case C — consumer needs the foundation to operate.** Keep mandatory dependency injection and supply a valid foundation; optionally use `@ConditionalOnBean` to enable the consumer only when the dependency exists, if that matches the intended design contract. Do not carelessly use `@Autowired(required=false)` or `null` fallbacks just to hide serious configuration errors.

**Case D — degraded mode when foundation is missing is required.** Design a transparent fallback with dedicated tests for degraded mode. Decide whether using the fallback changes data consistency, transactions, caching, or security; avoid letting `@ConditionalOnMissingBean` accidentally pick an implementation unsuitable for production.

**Case E — entire feature must be turned off.** Exclude the provider/consumer or use a starter-supported toggle property; assess full scope. If an auto-configuration class mixes foundational beans with unrelated beans, consider splitting auto-configurations by responsibility so one group can be disabled without affecting others.

**Case F — "fixing" with `@DependsOn` or `@Order` still fails.** Re-examine the problem: `@DependsOn` only orders initialization of **already-existing** beans, `@Order` mostly orders candidates/callbacks; `@AutoConfiguration(after=...)` orders **bean definition** processing. None of these tools recreate an excluded bean.

## 8. Common misinterpretations

1. **"Excluding an auto-configuration makes all beans from that library disappear."** False: beans created by application configuration, other auto-configurations, or other imports may remain. Always check the bean registry after startup.
2. **"If startup succeeds, there are no cascading impacts."** False: `@ConditionalOnBean` can cause consumers to be skipped entirely, or fallbacks to activate silently.
3. **"Having the class on the classpath means having the bean."** False: `@ConditionalOnClass` and `@ConditionalOnBean` test different things; excluding an auto-configuration does not remove dependency JARs.
4. **"`@ConditionalOnMissingBean` always sees every bean that might appear later."** False: the condition checks already-processed bean definitions; auto-configuration processing order and declared return types matter greatly.
5. **"Exclude the provider and add `@DependsOn` on the consumer to make it work."** False: the depended-upon bean still does not exist; `@DependsOn` does not replace dependencies or bean definitions.
6. **"Changing the bean name while keeping the type hides it from `@ConditionalOnBean`."** Not necessarily: conditions usually match by **type** when declared with a class; names/qualifiers and types must be verified against the exact contract.
7. **"Making beans optional is always safer than required beans."** Not by default: optional only changes when failures surface and which branch executes; it can mask missing critical infrastructure.
8. **"Replacing a default bean requires excluding the entire auto-configuration."** No: many starters actively support custom beans via `@ConditionalOnMissingBean`; contract-compliant replacement keeps other consumers and infrastructure intact.
9. **"Testing only that the provider is gone is enough."** Insufficient: test downstream B/C beans, fallbacks, startup failures, and core business behavior.
10. **"Just look at source file order."** False: Spring Boot orders auto-configurations via metadata, while bean instantiation order follows the dependency graph. Distinguish **bean definition availability** from **bean instance creation**.

## 9. Self-check questions

**Question 1.** You exclude `FoundationAutoConfiguration`, yet the application declares its own `FoundationService`. Is `@ConditionalOnBean(FoundationService.class)` on the consumer always false?  
**Answer:** No. If a matching custom bean is already registered when the condition evaluates, the condition can still match.

**Question 2.** A consumer uses `@ConditionalOnBean`, and the application starts cleanly after excluding the provider. Does that mean there are no issues?  
**Answer:** Not enough to conclude. The consumer may have been dropped entirely; verify the capability the consumer represents and downstream beans.

**Question 3.** A consumer has a mandatory `FoundationService foundationService` factory parameter without conditions, and the provider is excluded. What can happen?  
**Answer:** The consumer still registers, yet Spring cannot resolve the dependency, causing context startup to fail.

**Question 4.** Does `@AutoConfiguration(after = FoundationAutoConfiguration.class)` automatically recreate the foundation after it was excluded?  
**Answer:** No. It only specifies processing order among auto-configuration candidates actually being applied.

**Question 5.** To replace a foundational bean's implementation without losing other beans, what capability should you check first?  
**Answer:** The starter's customization APIs/properties and `@ConditionalOnMissingBean` mechanism that allow custom beans to replace defaults.

**Question 6.** Why are both `ApplicationContextRunner` tests and running the JAR with `spring.autoconfigure.exclude` necessary?  
**Answer:** The runner isolates individual bean conditions and dependencies; running the JAR verifies Spring Boot's real path from auto-configuration imports and the exclusion property.

## Official documentation

- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html): how to disable auto-configuration via `exclude`, `excludeName`, or `spring.autoconfigure.exclude`.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `AutoConfiguration.imports`, `before`/`after` ordering, bean conditions, and testing auto-configuration.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/index.html): `spring-boot-starter-test` and testing infrastructure.
- [Spring Boot API — `@ConditionalOnBean`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html) and [`@ConditionalOnMissingBean`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): conditions based on already-processed beans.
- [Spring Boot API — `@AutoConfiguration`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): configuration ordering metadata.
