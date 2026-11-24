# withUserConfiguration and Application-Provided Beans in Auto-Configuration Testing

In Spring Boot, **auto-configuration** supplies default beans so a library or starter "works out of the box" when the application has not declared the corresponding component itself. However, when the application already supplies its own bean, auto-configuration must usually **back off**, rather than silently creating a competing bean or overriding user configuration.

The specialized tool to test this contract is `ApplicationContextRunner` along with:

- `withConfiguration(AutoConfigurations.of(...))`: declares the auto-configuration under test.
- **`withUserConfiguration(MyApplicationConfiguration.class)`**: brings `@Configuration` classes containing `@Bean` definitions provided by **the application** into the test context.
- `withBean(...)`: simulates an application-provided bean without creating a separate `@Configuration`.
- `withPropertyValues(...)`: tests application property options.
- `run(context -> ...)`: creates an isolated context, asserts actual bean presence/absence, and closes the context after the callback finishes.

This lesson belongs to the **Auto-Configuration Testing** group of **Spring Boot - testing**, focusing on the meaning of **withUserConfiguration and application-provided beans**. We will test defaults, user bean overrides by **type**, partial replacement, multiple user beans, bean names, `@Primary`, feature flags, the difference between **back-off** and **bean definition overriding**, condition evaluation order issues, and reading `ConditionEvaluationReport`.

The hands-on section is **a self-contained Maven project using Java 17 + Spring Boot 3.5**. An auto-configuration creates default `GreetingFormatter` and `GreetingService` beans, while multiple application configurations simulate override choices. The suite of **14 JUnit Jupiter tests** runs quickly and **does not require Docker, a Spring web server, or a database**.

## 1. Why must we test with application-provided beans?

Imagine a library starter provides:

```text
Application configures NOTHING:
    GreetingAutoConfiguration
        |
        +-- @ConditionalOnMissingBean(GreetingFormatter)
        |       +-- default GreetingFormatter
        |
        +-- @ConditionalOnMissingBean(GreetingService)
                +-- default GreetingService
                           |
                           +-- uses default formatter

Application declares its own @Bean GreetingFormatter:
    UserConfiguration
        |
        +-- @Bean customFormatter
                |
                v
    GreetingAutoConfiguration
        |
        +-- detects GreetingFormatter already exists
        |       +-- DOES NOT create default greetingFormatter
        |
        +-- no GreetingService yet
                +-- creates default GreetingService
                       +-- injects application's customFormatter
```

The critical contract is not merely "the context starts":

1. **Default**: if the application provides no bean of the same type, the starter must create the default bean properly.
2. **Back-off**: if the application has a matching bean, the starter must **not create the default bean** for that part.
3. **Preserve the right bean**: the context must use **the application's exact instance/config**, rather than creating a default instance and relying on `@Primary` to mask competition.
4. **Partial replacement**: the application can customize only the formatter, while the default service continues to be auto-configured and must wire that exact formatter.
5. **Do not interfere with unrelated beans**: a user bean of another type must not cause the default formatter to disappear.
6. **Feature flags**: disabling auto-configuration does not mean deleting beans declared by the application itself.
7. **Ambiguity**: when the application supplies **two beans of the same type**, auto-config can back off, yet a dependency requiring a single bean may still fail to resolve without `@Primary`/`@Qualifier`.

That is why a test that only asserts `hasSingleBean(GreetingService.class)` **is not enough**. It needs to verify the bean's **name, type, identity, and behavior**, while proving the default bean is genuinely absent when the user bean appears.

## 2. How does `@ConditionalOnMissingBean` work?

In Spring Boot, the basic declaration:

```java
@Bean
@ConditionalOnMissingBean(GreetingFormatter.class)
GreetingFormatter greetingFormatter() {
    return new PrefixGreetingFormatter("Hello");
}
```

This is a snippet inside an auto-configuration, not a standalone program. The condition says: **register the default bean only if at evaluation time there is no matching bean of type `GreetingFormatter`** within the configured search scope.

Points to remember:

- `@ConditionalOnMissingBean(GreetingFormatter.class)` checks by **bean type**, not just the `greetingFormatter` method name.
- If the user names the bean `customFormatter` with type `GreetingFormatter`, the condition still **does not match** and auto-config must back off.
- If `@ConditionalOnMissingBean` is placed on `@Bean` **without supplying value/type/name/annotation**, Spring Boot defaults to using **the method's return type** as the check target. For example, `@Bean GreetingFormatter greetingFormatter()` checks `GreetingFormatter`.
- If using `@ConditionalOnMissingBean(name = "greetingFormatter")`, the condition checks **bean name**; a bean of the same type with a different name is **not enough** to make this condition back off. Therefore, pick type-based checking when allowing apps to swap implementations by interface.
- Per Javadoc 3.5, the check relies on **bean definitions already processed up to evaluation time**; beans that are not autowire/default candidates have separate semantics. Do not treat the condition as a scan of every bean that "might appear in the future".
- With parent/child contexts, the `search` attribute decides whether the parent is checked. In complex context hierarchies, tests must simulate the appropriate hierarchy.
- With multiple bean conditions, ordering between auto-configurations may require `@AutoConfiguration(after = ...)` or `@AutoConfigureAfter`.

**Why place it in auto-configuration?** Spring Boot intentionally processes auto-configurations **after user-defined bean definitions**, letting `@ConditionalOnMissingBean` see application components before deciding to create defaults. Putting this condition on an ordinary component-scanned `@Configuration` in arbitrary order can yield unstable results. Spring Boot documentation recommends using `@ConditionalOnBean` and `@ConditionalOnMissingBean` primarily in auto-configurations.

### A `@Bean`'s return type is also input to the condition

A subtle mistake:

```java
@Configuration(proxyBeanMethods = false)
class ApplicationConfiguration {
    @Bean
    Object customFormatter() {
        return new PrefixGreetingFormatter("APP");
    }
}
```

Even though the runtime object implements `GreetingFormatter`, at condition evaluation time the `BeanFactory` may **only know the return type `Object`** from the method signature before instantiation. Therefore, do not hide type information when auto-config must detect beans by interface/implementation. Declaring `@Bean GreetingFormatter customFormatter()` suffices for the contract tested in this lesson; in real libraries, expose the clearest, most specific return type possible as recommended by Spring Boot.

## 3. How does `withUserConfiguration` differ from `withConfiguration` and `withBean`?

| API | Purpose | Use when |
|---|---|---|
| `withConfiguration(AutoConfigurations.of(AutoConfig.class))` | Brings **auto-configurations** into the context using auto-config ordering | Testing starter defaults, conditions, and dependencies |
| **`withUserConfiguration(UserConfig.class)`** | Brings `@Configuration`/`@Bean` **supplied by the application** into the context | Testing custom bean precedence and proper auto back-off |
| `withBean(MyInterface.class, () -> new Impl())` | Directly registers a user bean via a supplier | Only need to simulate one bean without a `@Configuration` |
| `withPropertyValues("demo.x=y")` | Adjusts `Environment` for a single run | Testing property conditions, prefixes, feature flags |
| `withClassLoader(new FilteredClassLoader(...))` | Simulates a missing class on the classpath | Testing `@ConditionalOnClass`/missing classes |
| `withInitializer(...)` | Additional initialization, reports, or context customization | Diagnosing conditions |
| `withParent(parentContext)` | Creates a parent/child hierarchy | Testing bean visibility from parent context |
| `withAllowBeanDefinitionOverriding(boolean)` | Allows/disallows two definitions **with the same name** to override each other | Testing intentional collisions, **not a substitute for back-off** |

**Two things never to confuse:**

- `withUserConfiguration(...)` **is not a "bean definition override" command**; it sets up the context where the application has already declared its beans so auto-config conditions are evaluated properly. With `@ConditionalOnMissingBean`, **the default bean is not registered**, so no overriding occurs.
- `withConfiguration(...)` normally takes `AutoConfigurations.of(...)`, not an ordinary `@Configuration` passed in hoping it will be treated like user configuration. Keep each configuration's role accurate so condition ordering matches the real application.

### Runners can be reused safely

`ApplicationContextRunner` is an **immutable-style test builder**: `withUserConfiguration`, `withPropertyValues`, and `withBean` return **a new runner** with added customizations; the original runner keeps its base config.

```java
ApplicationContextRunner base = new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(GreetingAutoConfiguration.class));

ApplicationContextRunner withUser =
        base.withUserConfiguration(UserFormatterConfiguration.class);

withUser.run(context -> {
    // Application-supplied bean; auto formatter backs off.
});

base.run(context -> {
    // Still no user bean; default formatter is created.
});
```

This is a snippet using hypothetical classes from the example in section 5. Calling `run` creates a fresh context and closes it automatically, so you do not need `@DirtiesContext` to reset a small runner. Do not hold onto beans taken from the callback and use them after the context closes if the beans have context-dependent resources/lifecycles.

## 4. Matrix for verifying true back-off

| Test context | Expected GreetingFormatter | Expected GreetingService | Conclusion |
|---|---|---|---|
| No user config | default formatter | default service | Auto-config works |
| User declares `GreetingFormatter customFormatter` | only **customFormatter** | default service uses custom | Back-off **by type** |
| `withBean(GreetingFormatter.class, supplier)` | only bean from supplier | default service uses bean from supplier | Direct bean is respected too |
| User declares only `GreetingService customService` | default formatter still present | only **customService** | **Per-bean** back-off |
| User declares both formatter + service | only the two user beans | no default beans of those types | App has full control |
| User bean of type `String` present | default formatter still present | default service still present | Unrelated bean does not block auto |
| Property `demo.greeting.prefix=Bonjour` | default with prefix Bonjour | default service | Config property affects default |
| User formatter + prefix property | user formatter preserved | service uses user formatter | Default property does not overwrite user bean |
| Feature flag `demo.greeting.enabled=false` | no auto formatter | no auto service | Auto-config disabled |
| Feature flag false + user formatter | user formatter still exists | no auto service | Disabling auto != deleting app beans |
| User bean with same **name** as default and same type | user bean | default service | Back-off, no definition override needed |
| Two user formatters with different names | two formatters | default service may fail ambiguous injection | MissingBean does not resolve ambiguity itself |
| Two user formatters, one `@Primary` | two formatters | default service picks primary | Primary resolves injection, does not create back-off |
| Custom runner then run base runner | each context follows its own customization | independent | Base runner is not mutated |

Tests will assert **type, name, behavior**, and responses on startup failure; merely "context runs" is not enough.

## 5. Complete Maven example: Java 17 + Spring Boot 3.5

This is a **starter/library**-style example, not a web application: `ApplicationContextRunner` directly puts the auto-config into a Spring context. No `@SpringBootApplication` main class is needed to run JUnit tests. When packaging a real starter, the `AutoConfiguration.imports` file enables external applications to discover the auto-config.

### 5.1. Directory structure

```text
greeting-autoconfigure-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/greeting/
    │   │   ├── GreetingFormatter.java
    │   │   ├── PrefixGreetingFormatter.java
    │   │   ├── GreetingService.java
    │   │   └── autoconfigure/
    │   │       └── GreetingAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/example/greeting/autoconfigure/
        └── GreetingAutoConfigurationTest.java
```

**Do not create `@SpringBootApplication` in the same package and directly component-scan the auto-configuration** for testing: a starter must be imported by Boot via the standard auto-config mechanism rather than relying on application component scanning. The runner's `withConfiguration(AutoConfigurations.of(...))` handles importing the auto-config in tests; the imports file serves the module when used as a real dependency.

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>greeting-autoconfigure-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
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
</project>
```

`spring-boot-starter` supplies core Spring context + auto-configuration; `spring-boot-starter-test` brings JUnit Jupiter and AssertJ along with test runner utilities. Do not add `spring-boot-maven-plugin` because this is a **library jar without a main class**, not an executable Boot app. `mvn test` runs JUnit tests; `mvn package` packages the library jar per standard Maven.

### 5.3. Application interface: `GreetingFormatter.java`

File **`src/main/java/com/example/greeting/GreetingFormatter.java`**:

```java
package com.example.greeting;

public interface GreetingFormatter {
    String format(String name);
}
```

This is the contract for which the application can supply its own implementation. Auto-configuration should register a default only if no bean matching this contract exists yet.

### 5.4. Default implementation: `PrefixGreetingFormatter.java`

File **`src/main/java/com/example/greeting/PrefixGreetingFormatter.java`**:

```java
package com.example.greeting;

import java.util.Objects;

public final class PrefixGreetingFormatter
        implements GreetingFormatter {

    private final String prefix;

    public PrefixGreetingFormatter(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    @Override
    public String format(String name) {
        return prefix + ", " + name;
    }
}
```

Tests distinguish values via prefixes like `Hello`, `Bonjour`, `APP`, `DIRECT`, etc.; they do not depend on object identity alone or system locale. The class does not use `@Component` so bean creation is controlled entirely by auto-config or user config.

### 5.5. Business service: `GreetingService.java`

File **`src/main/java/com/example/greeting/GreetingService.java`**:

```java
package com.example.greeting;

import java.util.Objects;

public final class GreetingService {

    private final GreetingFormatter formatter;

    public GreetingService(GreetingFormatter formatter) {
        this.formatter = Objects.requireNonNull(formatter);
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
```

We intentionally have the constructor accept the **`GreetingFormatter` interface**: if the application declares two beans of that type without `@Primary`/`@Qualifier`, Spring cannot resolve a unique dependency when creating the default `GreetingService`. Negative tests will demonstrate the difference between **successful back-off** and **dependency injection still failing**.

### 5.6. Auto-configuration under test

File **`src/main/java/com/example/greeting/autoconfigure/GreetingAutoConfiguration.java`**:

```java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingFormatter;
import com.example.greeting.GreetingService;
import com.example.greeting.PrefixGreetingFormatter;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingFormatter.class)
    GreetingFormatter greetingFormatter(
            @Value("${demo.greeting.prefix:Hello}") String prefix) {
        return new PrefixGreetingFormatter(prefix);
    }

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(GreetingFormatter formatter) {
        return new GreetingService(formatter);
    }
}
```

Configuration contract:

- `@AutoConfiguration`: Boot treats this as an auto-configuration, processed during the auto-config phase.
- `@ConditionalOnProperty` **at class level**: when `demo.greeting.enabled=false`, **neither default bean method is loaded**. If the property is omitted, `matchIfMissing=true` enables defaults.
- `@ConditionalOnMissingBean(GreetingFormatter.class)`: does not create the formatter if the app has a valid formatter bean, regardless of the bean name chosen by the application.
- `@ConditionalOnMissingBean(GreetingService.class)`: the default service is registered only if the app has not provided a service of that type.
- `@Value("${demo.greeting.prefix:Hello}")`: default prefix is `Hello`; application properties only configure **the default formatter**, without altering the behavior of a user-defined formatter.
- `GreetingService greetingService(GreetingFormatter formatter)`: the parameter comes from the context, so it receives the custom user formatter if the auto formatter backed off.

**Note on return type:** here `GreetingFormatter` is a public contract and the condition explicitly checks that interface. When real code has multi-level inheritance or subtle bean conditions, prefer declaring `@Bean` return types as specifically as possible (avoiding `Object` or overly broad interfaces) per Spring Boot recommendations.

### 5.7. Auto-configuration imports

Exact file **`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**:

```text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
```

The file uses **one fully qualified class name per line**, with no commas or XML. This is how Boot 3.x discovers auto-configuration when the jar is added as a dependency to an application. An auto-config class **must not rely on component scan** to be found; `@Import` in an application can explicitly pull it in, but does not represent standard starter discovery. In runner tests, we supply the class **explicitly** via `AutoConfigurations.of`, so the lesson does not need to boot `SpringApplication`.

### 5.8. JUnit tests: 14 scenarios on user configuration

File **`src/test/java/com/example/greeting/autoconfigure/GreetingAutoConfigurationTest.java`**:

```java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingFormatter;
import com.example.greeting.GreetingService;
import com.example.greeting.PrefixGreetingFormatter;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            GreetingAutoConfiguration.class));

    @Test
    void noUserBeanCreatesBothDefaults() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(GreetingFormatter.class);
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context).hasBean("greetingFormatter");
            assertThat(context).hasBean("greetingService");

            assertThat(context.getBean(GreetingService.class)
                    .greet("Lan")).isEqualTo("Hello, Lan");
        });
    }

    @Test
    void userFormatterMakesOnlyFormatterDefaultBackOff() {
        runner.withUserConfiguration(UserFormatterConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).hasSingleBean(GreetingService.class);

                    assertThat(context).hasBean("customFormatter");
                    assertThat(context).doesNotHaveBean("greetingFormatter");
                    assertThat(context).hasBean("greetingService");

                    assertThat(context.getBean("customFormatter"))
                            .isSameAs(context.getBean(
                                    GreetingFormatter.class));
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("APP, Lan");
                });
    }

    @Test
    void withBeanRegistersUserBeanWithoutConfigurationClass() {
        runner.withBean(
                GreetingFormatter.class,
                () -> new PrefixGreetingFormatter("DIRECT"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("DIRECT, Lan");
                });
    }

    @Test
    void userServiceMakesOnlyServiceDefaultBackOff() {
        runner.withUserConfiguration(UserServiceConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context).hasBean("greetingFormatter");
                    assertThat(context).hasBean("customService");
                    assertThat(context).doesNotHaveBean("greetingService");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan"))
                            .isEqualTo("APP-SERVICE, Lan");
                });
    }

    @Test
    void userCanSupplyBothBeansAndKeepBothDefaultsOut() {
        runner.withUserConfiguration(BothUserBeansConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).hasSingleBean(GreetingService.class);

                    assertThat(context).hasBean("appFormatter");
                    assertThat(context).hasBean("appService");
                    assertThat(context).doesNotHaveBean("greetingFormatter");
                    assertThat(context).doesNotHaveBean("greetingService");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("APP-BOTH, Lan");
                });
    }

    @Test
    void unrelatedUserBeanDoesNotPreventDefaultBeans() {
        runner.withUserConfiguration(UnrelatedUserConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasBean("applicationMarker");
                    assertThat(context).hasBean("greetingFormatter");
                    assertThat(context).hasBean("greetingService");
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("Hello, Lan");
                });
    }

    @Test
    void propertyCustomizesDefaultWhenUserHasNotSuppliedIt() {
        runner.withPropertyValues("demo.greeting.prefix=Bonjour")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasBean("greetingFormatter");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("Bonjour, Lan");
                });
    }

    @Test
    void propertyForDefaultDoesNotReplaceUserFormatter() {
        runner.withPropertyValues("demo.greeting.prefix=Bonjour")
                .withUserConfiguration(UserFormatterConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).doesNotHaveBean("greetingFormatter");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("APP, Lan");
                });
    }

    @Test
    void disabledFeatureCreatesNoAutoBeans() {
        runner.withPropertyValues("demo.greeting.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(GreetingFormatter.class);
                    assertThat(context).doesNotHaveBean(GreetingService.class);
                });
    }

    @Test
    void disabledAutoConfigurationDoesNotDeleteUserBeans() {
        runner.withPropertyValues("demo.greeting.enabled=false")
                .withUserConfiguration(UserFormatterConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).hasBean("customFormatter");
                    assertThat(context).doesNotHaveBean(GreetingService.class);
                    assertThat(context.getBean(GreetingFormatter.class)
                            .format("Lan")).isEqualTo("APP, Lan");
                });
    }

    @Test
    void sameNameUserBeanBacksOffWithoutDefinitionOverride() {
        runner.withAllowBeanDefinitionOverriding(false)
                .withUserConfiguration(SameNameUserConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).hasBean("greetingFormatter");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("SAME-NAME, Lan");
                });
    }

    @Test
    void twoUserFormattersWithoutPrimaryMakeServiceAmbiguous() {
        runner.withUserConfiguration(TwoFormattersConfig.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context).getFailure()
                            .hasRootCauseInstanceOf(
                                    NoUniqueBeanDefinitionException.class);
                });
    }

    @Test
    void primaryChoosesInjectionButDoesNotRemoveOtherUserBean() {
        runner.withUserConfiguration(PrimaryFormatterConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).getBeans(GreetingFormatter.class)
                            .hasSize(2);
                    assertThat(context).doesNotHaveBean("greetingFormatter");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("PRIMARY, Lan");
                });
    }

    @Test
    void userCustomizationDoesNotMutateBaseRunner() {
        runner.withUserConfiguration(UserFormatterConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("APP, Lan");
                });

        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasBean("greetingFormatter");
            assertThat(context.getBean(GreetingService.class)
                    .greet("Lan")).isEqualTo("Hello, Lan");
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFormatterConfig {
        @Bean
        GreetingFormatter customFormatter() {
            return new PrefixGreetingFormatter("APP");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserServiceConfig {
        @Bean
        GreetingService customService() {
            return new GreetingService(
                    new PrefixGreetingFormatter("APP-SERVICE"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BothUserBeansConfig {
        @Bean
        GreetingFormatter appFormatter() {
            return new PrefixGreetingFormatter("APP-BOTH");
        }

        @Bean
        GreetingService appService(GreetingFormatter formatter) {
            return new GreetingService(formatter);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UnrelatedUserConfig {
        @Bean
        String applicationMarker() {
            return "hello";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class SameNameUserConfig {
        @Bean
        GreetingFormatter greetingFormatter() {
            return new PrefixGreetingFormatter("SAME-NAME");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoFormattersConfig {
        @Bean
        GreetingFormatter firstFormatter() {
            return new PrefixGreetingFormatter("ONE");
        }

        @Bean
        GreetingFormatter secondFormatter() {
            return new PrefixGreetingFormatter("TWO");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimaryFormatterConfig {
        @Bean
        @Primary
        GreetingFormatter primaryFormatter() {
            return new PrefixGreetingFormatter("PRIMARY");
        }

        @Bean
        GreetingFormatter secondaryFormatter() {
            return new PrefixGreetingFormatter("SECONDARY");
        }
    }
}
```

### 5.9. Mapping each test to requirements

| Test method | Context input | Expected and what was proven |
|---|---|---|
| `noUserBeanCreatesBothDefaults` | Auto-config only | Two default beans; behavior `Hello, Lan` |
| `userFormatterMakesOnlyFormatterDefaultBackOff` | `withUserConfiguration(UserFormatterConfig.class)` | No bean named `greetingFormatter`, only custom formatter; default service uses custom |
| `withBeanRegistersUserBeanWithoutConfigurationClass` | `withBean(GreetingFormatter.class, supplier)` | Direct bean also makes default back off |
| `userServiceMakesOnlyServiceDefaultBackOff` | User-provided service | Default formatter remains; default service yields to custom service |
| `userCanSupplyBothBeansAndKeepBothDefaultsOut` | Both user beans | No defaults, service uses user formatter |
| `unrelatedUserBeanDoesNotPreventDefaultBeans` | `String applicationMarker` | Bean of different type does not affect defaults |
| `propertyCustomizesDefaultWhenUserHasNotSuppliedIt` | Prefix property | Default receives value Bonjour |
| `propertyForDefaultDoesNotReplaceUserFormatter` | User formatter + Bonjour | User bean remains effective, not overwritten by default property |
| `disabledFeatureCreatesNoAutoBeans` | Enabled=false | Neither auto bean created |
| `disabledAutoConfigurationDoesNotDeleteUserBeans` | Enabled=false + custom user formatter | User bean still exists, auto service absent |
| `sameNameUserBeanBacksOffWithoutDefinitionOverride` | Same name, override=false | Context starts due to back-off, without needing definition override |
| `twoUserFormattersWithoutPrimaryMakeServiceAmbiguous` | Two formatters, no primary | Startup fails due to ambiguous dependency; condition backed off but insufficient alone |
| `primaryChoosesInjectionButDoesNotRemoveOtherUserBean` | Two formatters, one primary | Both user beans remain; service uses primary |
| `userCustomizationDoesNotMutateBaseRunner` | Run user then run base | Two independent contexts, no contamination |

**14 tests** use only `ApplicationContextRunner`; no `@SpringBootTest`, no web server started. The runner closes the context after the callback. The multi-formatter test expecting **startup failure** still **PASSES** when failing with the right root cause, and must not be mistaken for an unexpected JUnit failure.

### 5.10. Running and verifying

Requires JDK 17+, Maven, no Docker needed:

```bash
mvn test
```

Or run a single class:

```bash
mvn -Dtest=GreetingAutoConfigurationTest test
```

With the POM and source code above, Maven Surefire is expected to report **Tests run: 14, Failures: 0, Errors: 0**. Cases intentionally failing context startup assert `hasFailed()` and root cause, so they still count as JUnit PASS.

This example was reviewed against **Spring Boot 3.5.0 + Java 17** APIs and is **not a claim that Maven was executed while authoring the lesson**. When applying to a real module, run tests on CI to check compatibility with actual dependencies and classpath.

## 6. How to be certain the application's bean was chosen?

You should not write only:

```java
assertThat(context).hasSingleBean(GreetingFormatter.class);
```

That assertion can PASS in **both cases**: context has the default formatter, or context has the custom formatter. To prove **back-off**, test three layers:

1. **Bean count/type**: exactly one bean of the target type.
2. **Bean name/identity**: `customFormatter` exists and **`greetingFormatter` does not** (when the default name is known).
3. **Behavior or instance**: calling service must yield `APP, Lan`; `context.getBean("customFormatter")` matches the same object as `context.getBean(GreetingFormatter.class)`.

```java
assertThat(context).hasSingleBean(GreetingFormatter.class);
assertThat(context).hasBean("customFormatter");
assertThat(context).doesNotHaveBean("greetingFormatter");
assertThat(context.getBean("customFormatter"))
        .isSameAs(context.getBean(GreetingFormatter.class));
assertThat(context.getBean(GreetingService.class).greet("Lan"))
        .isEqualTo("APP, Lan");
```

Snippet taken from the user formatter test in section 5. If auto-config were changed to always create the default bean alongside the user bean, at least one count/absence assertion would fail; if the service mistakenly injected the default, the behavior assertion would fail.

### User bean with a different name but same type

`@ConditionalOnMissingBean(GreetingFormatter.class)` evaluates **type**. Thus a user bean named `customFormatter` is enough to make the default `greetingFormatter` back off. This is the standard contract for starters providing default implementations via an interface.

**Do not write by mistake:**

```java
@Bean
@ConditionalOnMissingBean(name = "greetingFormatter")
GreetingFormatter greetingFormatter() {
    return new PrefixGreetingFormatter("Hello");
}
```

If the application declares `@Bean GreetingFormatter customFormatter()`, a bean named `greetingFormatter` does not exist yet so the name-based condition can create **an extra default formatter**. Then two beans of the same type cause ambiguous injection without primary/qualifier. When the goal is allowing replacement by interface, choose a type-based condition appropriately.

### User bean with the same name as default

In the `SameNameUserConfig` test, the user also declares a `greetingFormatter()` method. Because the type-based condition detects the application's bean, auto **does not register a definition with the same name**. That is **back-off**, not Spring overriding a same-named bean. We intentionally configure `withAllowBeanDefinitionOverriding(false)` to prove startup still succeeds.

If you remove `@ConditionalOnMissingBean` and leave two same-named definitions, the context typically hits a `BeanDefinitionOverrideException` when overriding is disallowed. Turning on `spring.main.allow-bean-definition-overriding=true` just to make tests green can mask a starter violating its contract, rather than fixing it properly.

## 7. Multiple user beans: back-off and autowiring are two distinct checks

A scenario worth learning:

```java
@Configuration(proxyBeanMethods = false)
class MultipleFormatters {
    @Bean
    GreetingFormatter first() {
        return new PrefixGreetingFormatter("ONE");
    }

    @Bean
    GreetingFormatter second() {
        return new PrefixGreetingFormatter("TWO");
    }
}
```

At condition time, a `GreetingFormatter` bean already exists so the default formatter **backs off successfully**. However, the auto service takes a single `GreetingFormatter` in its constructor while the context has **two choices**. Without `@Primary`, `@Qualifier`, or unambiguous parameter-name resolution, the context may fail with `NoUniqueBeanDefinitionException`.

This **does not prove `@ConditionalOnMissingBean` is broken**; it proves the user's configuration created dependency ambiguity. A library can:

- Activate only when there is a single candidate (using an appropriate condition, e.g., `@ConditionalOnSingleCandidate` where needed).
- Let the user designate `@Primary` or `@Qualifier`.
- Accept and process a collection/map of beans when business logic truly needs multiple implementations.
- Produce clear error messages/diagnostics instead of arbitrarily picking based on registration order.

In the `PrimaryFormatterConfig` test, Spring keeps **both user beans**, the default formatter still backs off, and the service receives the `@Primary` bean. `@Primary` is **not** a condition that makes the auto bean disappear; **`@ConditionalOnMissingBean`** is responsible for back-off.

### Do not abuse `@Primary` to hide auto-configuration bugs

If auto-config creates the default formatter **alongside** the custom formatter, `@Primary` helps injection pick one bean, yet **two beans** still exist. Consumers using `List<GreetingFormatter>` or `Map<String,GreetingFormatter>` will see both; behavior may diverge from production expectations. For a starter allowing user override by type, tests should require **only the user bean** when a custom one is present.

## 8. Property conditions and precedence

A property can adjust defaults, but should not **override an object created by the application itself**:

```text
Runner:
  withPropertyValues("demo.greeting.prefix=Bonjour")
  + auto-config only
  -> greetingFormatter("Bonjour")
  -> greetingService uses formatter("Bonjour")

Runner:
  withUserConfiguration(UserFormatterConfig.class)
  withPropertyValues("demo.greeting.prefix=Bonjour")
  -> customFormatter("APP")
  -> no default greetingFormatter bean
  -> greetingService uses customFormatter("APP")
```

What must be tested is **the actual value and bean type used**, not merely that `Environment` contains a property. If the app chooses its own implementation, a property meant only for the default implementation may no longer apply.

### Class-level feature flag

`@ConditionalOnProperty(prefix="demo.greeting", name="enabled", havingValue="true", matchIfMissing=true)` on the auto-config class:

- **Property absent** -> auto-config is allowed to run.
- `demo.greeting.enabled=true` -> auto-config is allowed to run.
- `demo.greeting.enabled=false` -> auto-config class does not create default formatter/service.
- User config is still registered independently of auto-config, since it is not inside that class.

Do not interpret "disable starter" as "delete every application bean of that type". Spring does not automatically remove a user's `@Bean` just because an auto-configuration class is conditioned off.

If the product requires turning off the whole feature at the service layer, design and test an explicit condition where the user bean is used rather than expecting an auto-config property to control every component.

## 9. ConditionEvaluationReport: finding why an auto bean was or wasn't created

When a test fails, inspect **conditions** instead of adding assertions by guesswork. Spring Boot provides `ConditionEvaluationReport`, and in unit tests you can enable the official listener:

```java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

ApplicationContextRunner debugRunner = new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(GreetingAutoConfiguration.class))
        .withInitializer(
                ConditionEvaluationReportLoggingListener
                        .forLogLevel(LogLevel.INFO));
```

This is a non-standalone snippet (needs the example's `GreetingAutoConfiguration` class). Calling `debugRunner.withUserConfiguration(...).run(...)` lets Spring Boot print the report at the specified log level. Enable it on tests needing diagnosis; do not spam CI logs on every run.

You can also inspect it programmatically from a **started** context:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
    if (source.contains("GreetingAutoConfiguration")) {
        System.out.println(source + " -> " + outcomes.isFullMatch());
    }
});
```

This snippet requires importing `org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport` and the `context` variable inside the runner callback. Source names usually include class/method, though message formatting/details can change across Spring Boot patch versions. Tests **should not depend on verbatim condition text** or log message names when all you need to prove is bean count/identity/behavior.

### Reading the report in order

1. **Property condition**: did `demo.greeting.enabled` match?
2. **Missing-bean condition**: did any bean make default `GreetingFormatter` or `GreetingService` back off?
3. **Type information**: what type did the user `@Bean` method declare? Is the return type too broad?
4. **Scope and candidate**: is the bean in a child/parent context? Are there excluded/non-default/autowireCandidate settings?
5. **Auto-configuration order**: which dependency config ran earlier? Did component scanning accidentally register the auto-config class too early?
6. **Actual beans**: what do `context.getBeanNamesForType(...)` or AssertJ assertions say?
7. **Startup failure**: use `assertThat(context).hasFailed()` and `getFailure()` instead of calling `getBean(...)` on a failed context.

A report showing a negative match due to `@ConditionalOnMissingBean` **can be by design**: it proves auto-config yielded to the user bean, not a test failure.

## 10. What `ApplicationContextRunner` does not test in place of a full app

`ApplicationContextRunner` is primarily for small **non-web test contexts**. It works very well for testing bean registration and conditions, but it does not guarantee:

- A real project actually imported the starter jar when running `SpringApplication` with all classpaths/dependencies and profiles.
- HTTP servlet/reactive context is valid if auto-config depends on a web runtime.
- User component scanning, conditional scans, and `BeanFactoryPostProcessor`s from other modules are fully simulated.
- Database, Redis, Kafka, OAuth2, or external services actually connect.
- Ahead-of-time native image support: Spring Boot documentation states `ApplicationContextRunner` **cannot be used when running tests in a native image**.
- Full application startup succeeds alongside all other auto-configurations.

**When to switch runners?**

| Need | Tool |
|---|---|
| Web-independent bean conditions | `ApplicationContextRunner` |
| Auto-config requiring servlet web context | `WebApplicationContextRunner` |
| Auto-config requiring reactive WebFlux context | `ReactiveWebApplicationContextRunner` |
| Testing auto-configuration in a real app, profiles, dependency graph | `@SpringBootTest`, appropriate test slice |
| Testing library works when imported from a real artifact | Consumer/sample application integration test |
| Testing classpath missing a dependency | `FilteredClassLoader` combined with runner |
| Testing DB/broker readiness | Testcontainers or service integration tests |

Do not use a full `@SpringBootTest` for **every** small user-bean/property combination if the runner already simulates it accurately; high startup costs and other auto-configurations can mask issues. Conversely, do not rely solely on the runner and claim you tested the starter's full behavior in a real consumer app.

## 11. Common mistakes with `withUserConfiguration`

| Mistake | Consequence | Fix |
|---|---|---|
| Using `withConfiguration` for user class as auto-config | Condition ordering may not match app | Use `withUserConfiguration` for app `@Bean`s |
| Putting `@ConditionalOnMissingBean` in regular scanned config | Condition evaluates before sufficient bean defs exist | Put in auto-config loaded in Boot order |
| Only asserting `hasSingleBean` | Unknown whether bean is default or user | Assert name, identity, behavior as well |
| Checking missing bean by **name** when replacing by **type** | Differently named user bean fails to back off default | Use `@ConditionalOnMissingBean(GreetingFormatter.class)` |
| User `@Bean Object ...` returns right implementation | Type inference may not see real type early | Declare specific return type/contract |
| Relying on `@Primary` as proof of back-off | Default bean still exists alongside user | Assert default bean **absent** and exact count |
| Two user beans of same type without qualifier | Ambiguous dependency | Use `@Primary`/`@Qualifier` or multi-bean design |
| Enabling bean-definition overriding to pass tests | Masks bean collision | Fix condition and config ordering |
| Using `@MockBean`/`@MockitoBean` instead of full user config | Does not prove app declaration/return type | Use `withUserConfiguration`/`withBean` to test conditional registration |
| Not testing disabled property + user bean | May mistakenly think feature flag deletes app bean | Test user bean independently of auto feature flag |
| Using component scan to find auto-config | Auto-config may be processed in wrong order | Use `AutoConfiguration.imports` and `AutoConfigurations.of` |
| Using `@DirtiesContext` after every runner test | Slow, does not fix underlying condition | Runner creates/closes context every time |
| Keeping context bean outside callback and using after close | Lifecycle/resources already closed | Assert inside `run(context -> ...)` |
| Testing web-only config with non-web runner | `@ConditionalOnWebApplication` does not match | `WebApplicationContextRunner`/Reactive runner |
| Not inspecting startup failure when context fails | Vague test failure | `assertThat(context).getFailure()`, `ConditionEvaluationReport` |
| Thinking auto-config always beats app config | User bean may be duplicated/overridden | Proper back-off semantics is **app wins** |

## 12. Self-check questions

**Question 1:** Auto-config uses `@ConditionalOnMissingBean(GreetingFormatter.class)`. The application declares `@Bean GreetingFormatter customFormatter()`. Should the default `greetingFormatter` bean appear?

**Answer:** No. The condition targets **type**, independent of bean name; there must be only `customFormatter` if no other bean of that type exists.

**Question 2:** The application creates its own `GreetingFormatter`, but not `GreetingService`. Should the default service be created?

**Answer:** Yes, if the service's conditions match; the default service must inject the custom formatter. This is standard **partial override**.

**Question 3:** Does `withUserConfiguration` automatically enable bean definition overriding?

**Answer:** No. It registers user-provided configuration; auto-configuration back-off conditions prevent registering a conflicting definition. Overriding same-named definitions is a different mechanism.

**Question 4:** Two user beans of the same type, without `@Primary`. The auto formatter backed off, yet startup fails. Does that prove back-off is broken?

**Answer:** No. Back-off already yielded. The remaining error is **dependency injection ambiguity** when the default service requires a single formatter.

**Question 5:** `demo.greeting.enabled=false` while the application has `@Bean GreetingFormatter customFormatter()`. Is the custom bean deleted?

**Answer:** No. The feature flag is placed on the **auto-config class**, not the user config.

**Question 6:** Is changing `@Bean GreetingFormatter customFormatter()` to `@Bean Object customFormatter()` safe for condition detection?

**Answer:** Not guaranteed. Spring Boot relies on bean definitions/type metadata; an overly broad return type starves the condition of information. Declare the proper type.

**Question 7:** Why test name/identity alongside value?

**Answer:** The same output could come from either the default or user bean. Asserting identity/name proves the user implementation was actually used rather than accidentally matching the same output.

## 13. QA checklist for starter auto-configuration

- [ ] I accurately identified the interfaces/types the application is allowed to supply.
- [ ] Auto-configuration uses `@AutoConfiguration` and is registered via `AutoConfiguration.imports` in the library jar.
- [ ] `@ConditionalOnMissingBean` targets the right type/name/annotation, without confusing name with type.
- [ ] Bean conditions are placed where processing order appropriately follows user bean definitions.
- [ ] `@Bean` methods declare clear enough return types for accurate condition detection.
- [ ] Base runner has `withConfiguration(AutoConfigurations.of(...))`.
- [ ] User overrides are supplied via **`withUserConfiguration`** or `withBean` according to the goal.
- [ ] Default test: no user bean -> creates proper defaults.
- [ ] Partial override test: custom formatter -> auto service still created and uses custom formatter.
- [ ] Service-only override test: default formatter remains, default service backs off.
- [ ] Both user beans test: no default beans of matching types.
- [ ] Feature flag/property tests cover both default-only and custom-bean modes.
- [ ] Unrelated user bean test confirms it does not block auto beans.
- [ ] Type vs name test: custom bean with a different name still causes default back-off.
- [ ] Do not use bean-definition overriding or `@Primary` to hide duplicated defaults.
- [ ] Negative test for multiple user candidates if the service requires unique injection.
- [ ] Assert **count, name, identity, and behavior**, not just that the context starts.
- [ ] Runner customizations do not mutate base and contexts close after run.
- [ ] When context fails, inspect `getFailure()`/root cause rather than guessing from console output.
- [ ] Inspect `ConditionEvaluationReport` if conditions match/unmatch unexpectedly.
- [ ] For web-only configs, use the right web runner; native image needs dedicated testing flows.
- [ ] Run `mvn test` on JDK 17+ and run real tests in a consumer app if publishing a starter.

**Conclusion:** `withUserConfiguration` is the accurate way to simulate **application-provided beans** in an auto-configuration test. When a starter obeys `@ConditionalOnMissingBean`, the application's configuration **takes precedence**, and the default bean is **not registered**. Good tests must verify **proper back-off**, **injection of the right implementation**, **property conditions**, and **failure when user config is ambiguous**; never confuse back-off with overriding same-named beans.

### Official documentation

- [Spring Boot 3.5 — Creating Your Own Auto-configuration; Testing Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.5 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot 3.5 — AbstractApplicationContextRunner and withUserConfiguration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html)
- [Spring Boot 3.5 — ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.5 — ApplicationContextAssert Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/assertj/ApplicationContextAssert.html)