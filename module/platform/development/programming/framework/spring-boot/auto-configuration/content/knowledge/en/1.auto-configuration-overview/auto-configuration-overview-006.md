# Conditional default configuration and the user back-off mechanism

> **Context:** Spring Boot — auto-configuration, "Auto-configuration Overview" section. This lesson focuses on how Spring Boot registers default configurations only when conditions are met and lets application-provided configurations take precedence via the back-off mechanism. Examples use Java 17 and Spring Boot 3.5.7 for reproducibility; condition/back-off principles apply to modern Spring Boot releases as well, though specific auto-configuration names may vary across versions.

## 1. Why is conditional default configuration needed?

In Spring Framework, applications declare beans in `ApplicationContext` using `@Configuration`, `@Bean`, component scan, or other bean registration mechanisms. Spring Boot adds **auto-configuration** to provide beans/configurations suited to the libraries, environment, and what the application **has already declared itself**.

For example: when an application has JDBC libraries, meets connection conditions, and has not supplied its own `DataSource`, Spring Boot can configure the corresponding `DataSource`. If the application already has a `DataSource` of its own, the corresponding default configuration **backs off**. This is a conditional decision at context construction time, not a mechanism that continuously swaps beans after startup.

Two distinct questions must be answered when reading any auto-configuration:

1. **Is it considered for application?** Depends on classpath conditions, web/non-web application type, `Environment` properties, existing beans, resources, etc.
2. **If considered, is a specific default bean registered?** Usually guarded by `@ConditionalOnMissingBean` at the `@Bean` level; individual beans can back off independently.

**Back-off does not mean deleting or replacing an already-created bean.** Typically, Spring Boot skips registering the **default bean** when it detects that the user has already declared a suitable bean.

## 2. Ordered processing mechanism

```text
@SpringBootApplication
    └─ includes @EnableAutoConfiguration
          └─ finds auto-configuration candidates in
             META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
               └─ evaluates class-level conditions
                    └─ processes @Bean methods and their own conditions
                         ├─ satisfied, missing user-provided bean
                         │    └─ registers default bean
                         └─ unsatisfied or matching bean already exists
                              └─ does not register default bean
```

- `@SpringBootApplication` includes `@EnableAutoConfiguration`, `@ComponentScan`, and `@SpringBootConfiguration`. **Component scan** discovers application components; **auto-configuration** loads configuration classes declared as candidates. These two mechanisms have different responsibilities.
- An auto-configuration can contain multiple beans. One bean backing off **does not mean** the entire auto-configuration class is disabled, unless a **class-level** condition prevents the whole class from applying.
- Spring Boot processes user configuration definitions before auto-configurations imported through the standard mechanism, so `@ConditionalOnMissingBean` can see application-declared beans. Bean-dependent conditions only see **bean definitions already processed up to evaluation time**, so processing order matters.
- Auto-configuration ordering (`@AutoConfiguration(after = ...)`, `before = ...`, or `@AutoConfigureAfter`) pertains to **bean definition processing order**, not runtime bean instantiation order; instance creation order is also governed by dependencies/`@DependsOn`.

## 3. Common conditions

| Annotation | Condition | Application example and note |
| --- | --- | --- |
| `@ConditionalOnClass` | Class is on the classpath | Enable configuration for JDBC, Jackson, or integration libraries only when required APIs are present. |
| `@ConditionalOnMissingClass` | Class is not on the classpath | Choose a fallback option when a library is absent. |
| `@ConditionalOnBean` | A bean matching type/name exists | Create a dependent component only when the underlying component already exists. |
| `@ConditionalOnMissingBean` | No bean matching type/name exists yet | The most common **back-off** pattern: do not create a default if the application provides a matching bean. |
| `@ConditionalOnSingleCandidate` | A single suitable bean candidate exists for autowiring | Useful for configurations depending on one clearly chosen bean, including `@Primary` cases. |
| `@ConditionalOnProperty` | Property in `Environment` meets the condition | Toggle configuration options on/off, using `havingValue` and `matchIfMissing` to express intent clearly. |
| `@ConditionalOnResource` | Resource is found | Load configuration only when a file/resource is present. |
| `@ConditionalOnWebApplication` / `@ConditionalOnNotWebApplication` | Application type | Distinguish configurations for web vs. non-web; can specify servlet or reactive when needed. |
| `@ConditionalOnExpression` | SpEL expression evaluates to true | Use sparingly if simpler conditions suffice; referencing beans in expressions may cause premature bean initialization. |

`@ConditionalOnProperty(prefix = "demo.clock", name = "enabled", havingValue = "true", matchIfMissing = true)` means:

| Value of `demo.clock.enabled` | Result |
| --- | --- |
| Undeclared | **Matches**, because `matchIfMissing = true`. |
| `true` | **Matches** `havingValue = "true"`. |
| `false` | **Does not match**. |
| Another value, e.g. `other` | **Does not match** `havingValue = "true"`. |

If **`havingValue` is not declared**, `@ConditionalOnProperty`'s default matching rule is that the property **is present and its value does not equal `false`**; do not think of it simply as casting to boolean and checking. A missing property does not match by default if `matchIfMissing` is not enabled.

## 4. Complete example: default `Clock` and backing off when a custom bean exists

We want a library to provide `Clock.systemUTC()` as a default. An application using the library can declare its own `Clock` to replace it or completely disable *Clock auto-configuration* via the `demo.clock.enabled=false` property.

The example includes the files below in a Maven project. Java files sit in paths matching their `package`. Place the auto-configuration in `dev.example.clock`, **outside** the `dev.example.app` component scan branch to avoid accidentally loading it twice.

### 4.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>dev.example</groupId>
    <artifactId>conditional-clock</artifactId>
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

### 4.2. `src/main/java/dev/example/clock/ClockAutoConfiguration.java`

```java
package dev.example.clock;

import java.time.Clock;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "demo.clock",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class ClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    Clock defaultClock() {
        return Clock.systemUTC();
    }
}
```

- The **class-level** condition enables the default while allowing it to be turned off via property.
- The **method-level** condition looks for an existing `Clock` bean. When a matching bean already exists, `defaultClock` is not registered. Explicitly specify `Clock.class` so it does not rely on type inference from the method signature.
- `Clock` is a JDK class, so this example emphasizes **bean-based and property-based back-off**. In auto-configuration for optional libraries, `@ConditionalOnClass(ThirdPartyClient.class)` is typically added on a **separate nested configuration class** when the `@Bean` signature references a class that might be absent; a condition placed directly on the method does not always prevent class loading errors when the return type is missing.

### 4.3. Registering the auto-configuration candidate

Create the exact file `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` with **one line**:

```text
dev.example.clock.ClockAutoConfiguration
```

In Spring Boot 3.x and later, this is the standard mechanism to publish auto-configuration candidates from a JAR. Merely placing `@AutoConfiguration` without registering via imports (and without manually importing elsewhere) is **not sufficient** for the application to find this class automatically.

### 4.4. Application to check state

File `src/main/java/dev/example/app/DemoApplication.java`:

```java
package dev.example.app;

import java.time.Clock;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {
            Map<String, Clock> clocks = context.getBeansOfType(Clock.class);
            System.out.println("clock.count=" + clocks.size());
            clocks.forEach((name, clock) ->
                System.out.println("clock." + name + ".zone=" + clock.getZone())
            );
        }
    }
}
```

From the directory containing `pom.xml`, run:

```bash
mvn -q spring-boot:run
```

In the default case, the lines printed by the application are:

```text
clock.count=1
clock.defaultClock.zone=Z
```

These are **the lines printed by the program**, not all Spring Boot logs. `Z` is how `ZoneOffset.UTC` displays. When no application-provided `Clock` bean exists and the property does not disable it, auto-configuration creates `defaultClock`.

### 4.5. Adding an application bean: back-off

Create `src/main/java/dev/example/app/UserClockConfiguration.java`:

```java
package dev.example.app;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UserClockConfiguration {

    @Bean
    Clock businessClock() {
        return Clock.fixed(
            Instant.parse("2025-01-01T00:00:00Z"),
            ZoneId.of("Asia/Ho_Chi_Minh")
        );
    }
}
```

Restart `mvn -q spring-boot:run`. Relevant output:

```text
clock.count=1
clock.businessClock.zone=Asia/Ho_Chi_Minh
```

`ClockAutoConfiguration` is still considered as a candidate; however, `@ConditionalOnMissingBean(Clock.class)` sees the `businessClock` bean and **does not register** `defaultClock`. The custom bean name does not need to match the default name because the condition checks **by type `Clock`**. The default bean is not created and then replaced; it is never registered in the first place.

If you run with the custom configuration alongside `--demo.clock.enabled=false`, the output still has `businessClock`. The property on `ClockAutoConfiguration` only disables **that auto-configuration**, not self-declared beans.

To test the property condition **without a custom bean**, temporarily remove `UserClockConfiguration.java` from source or remove `@Configuration` from that class and run:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.clock.enabled=false
```

Lines printed by the program:

```text
clock.count=0
```

At that point, there is neither default configuration nor user configuration. This is a different branch from back-off caused by a custom bean.

## 5. Reading the true meaning of back-off

| State | Property condition | Application `Clock` bean present? | `defaultClock` | Result |
| --- | --- | --- | --- | --- |
| A. Default | Matches | No | Registered | 1 default `Clock` bean |
| B. User custom configuration | Matches | Yes | Backs off | 1 custom `Clock` bean |
| C. Auto-configuration disabled | Does not match | No | Not registered | 0 `Clock` beans |
| D. Auto-configuration disabled, user still declares | Does not match | Yes | Not registered | Custom bean still exists |

**Points to distinguish:**

- **Back-off**: the missing-bean condition is no longer true, so the default part is not registered. This is cooperative behavior between the application and auto-configuration.
- **Exclusion**: using `@SpringBootApplication(exclude = SomeAutoConfiguration.class)`, `@EnableAutoConfiguration(exclude = ...)`, or `spring.autoconfigure.exclude` removes an auto-configuration class from consideration; typically meant for cases where you do not want that configuration applied at all. Not every auto-configuration requires exclusion to be customized.
- **Property override**: changing values in `application.properties`/`application.yml` modifies parameters of Boot-created beans, *if the auto-configuration exposes corresponding properties*. Changing a property does not mean declaring a new bean.
- **`@Primary`**: resolves injection priority among multiple beans of the same type; **does not make a default bean disappear**. If an auto-configuration has no back-off and creates another bean of the same type, `@Primary` can only help select a bean during injection, not prevent the other bean from being created.
- **`@ConditionalOnMissingBean(name = "x")`** checks by name; **`@ConditionalOnMissingBean(SomeType.class)`** checks by type. You cannot infer the back-off mechanism solely from a `@Bean` method's name.

## 6. Writing conditions in the right place and order

An auto-configuration typically has this structure:

```java
@AutoConfiguration
@ConditionalOnClass(SomeLibraryApi.class)
class SomeLibraryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SomeLibraryClient.class)
    SomeLibraryClient someLibraryClient() {
        return new SomeLibraryClient();
    }
}
```

This snippet **illustrates the structure** and does not compile on its own since `SomeLibraryApi`/`SomeLibraryClient` are placeholder names for library APIs. When writing real code, only reference types present in the corresponding dependency and test the case where the dependency is absent.

Important constraints:

1. `@ConditionalOnMissingBean` and `@ConditionalOnBean` look at **already-processed bean definitions**. If used carelessly in regular application configuration, whether another bean is registered before or after can alter the result. Spring Boot recommends concentrating these bean conditions inside auto-configuration processed after user configuration.
2. If an optional class may be **absent**, avoid using it as a `@Bean` return type in a configuration that the JVM loads before the method condition is evaluated. Use a nested `@Configuration(proxyBeanMethods = false)` with class-level `@ConditionalOnClass`, or a suitable separated design.
3. Class-level conditions affect **the entire class**; method-level conditions affect **only that method's bean**. To let one bean back off while another bean is still created, place the condition on the corresponding bean.
4. Also consider the **bean hierarchy** (parent/child). The `search` attribute on bean conditions lets you limit where to search. By default it can inspect parent contexts, so with multiple contexts do not look only at one bean list in the child context.
5. When defining `@Bean`, declare a **concrete and exact** return type so Spring has sufficient metadata when evaluating conditions. Returning an overly generic type like `Object` can cause bean-type checks to fail to recognize the bean as intended.
6. With multiple beans of the same type, do not assume `@ConditionalOnMissingBean` decides which bean gets injected. It decides whether to create the default; bean selection rules at injection are a separate issue.

## 7. Testing all three branches with `ApplicationContextRunner`

Add `src/test/java/dev/example/clock/ClockAutoConfigurationTest.java`. Unit tests build a small context importing only the auto-configuration under test; therefore there is no need to run the entire application.

```java
package dev.example.clock;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ClockAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(ClockAutoConfiguration.class)
            );

    @Test
    void registersDefaultWhenClockIsMissing() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Clock.class);
            assertThat(context.getBean(Clock.class).getZone())
                .isEqualTo(ZoneOffset.UTC);
            assertThat(context).hasBean("defaultClock");
        });
    }

    @Test
    void backsOffWhenUserProvidesClock() {
        runner.withUserConfiguration(UserConfig.class)
            .run(context -> {
                assertThat(context).hasSingleBean(Clock.class);
                assertThat(context).doesNotHaveBean("defaultClock");
                assertThat(context.getBean(Clock.class).instant())
                    .isEqualTo(Instant.parse("2025-01-01T00:00:00Z"));
            });
    }

    @Test
    void disablesDefaultWhenPropertyIsFalse() {
        runner.withPropertyValues("demo.clock.enabled=false")
            .run(context ->
                assertThat(context).doesNotHaveBean(Clock.class)
            );
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfig {
        @Bean
        Clock businessClock() {
            return Clock.fixed(
                Instant.parse("2025-01-01T00:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh")
            );
        }
    }
}
```

Run:

```bash
mvn -q test
```

The three tests verify **default present**, **default backs off**, and **default disabled by property**, respectively. If run from an IDE, the tests use JUnit Jupiter; the `spring-boot-starter-test` dependency in `pom.xml` already provides Spring Boot's standard test suite. The tests above can run even if the real application does not declare `UserClockConfiguration`, because each `ApplicationContextRunner` creates an isolated context and the second test supplies `UserConfig` independently.

Note: `ApplicationContextRunner` is mainly for testing JVM contexts; Spring Boot documentation notes that this runner does not work when running tests **inside a native image**.

## 8. Diagnosing when a default bean does not appear

When the application is missing a bean you expected Boot to supply, read the **Condition Evaluation Report**:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Or with the built JAR:

```bash
java -jar target/conditional-clock-1.0.0.jar --debug
```

You can view the report via the Actuator `/actuator/conditions` endpoint if the application has Actuator added and allows exposing that endpoint. Endpoints are generally **not exposed over HTTP by default**; configure proper security and access permissions rather than exposing every endpoint publicly.

When reading the report, search for the auto-configuration class and method names: **positive matches** are matched conditions, and **negative matches** tell which conditions did not match and why. For instance, when `businessClock` exists, an unmatched `@ConditionalOnMissingBean(Clock.class)` condition is **a signal that back-off is working properly**, not necessarily an error.

Short troubleshooting procedure:

1. **Was the candidate loaded?** Check `@SpringBootApplication`, `AutoConfiguration.imports`, and whether the class is inside the dependency/JAR.
2. **Is the classpath right?** `@ConditionalOnClass` can fail due to a missing dependency or a class only available in test scope.
3. **What is the actual resolved property?** Check name, prefix, profiles, environment, `havingValue`, `matchIfMissing`; do not guess from one config file when multiple property sources exist.
4. **Does a bean of that type/name already exist?** Distinguish user beans, beans from other configurations, and how Spring recognizes types from `@Bean` signatures.
5. **Is the condition at class level or method level?** Class-level failure blocks all methods; method-level failure blocks only that bean.
6. **Are there multiple beans of the same type?** If the error is `NoUniqueBeanDefinitionException`, the issue concerns bean selection/injection; check `@Primary` and `@Qualifier` rather than assuming back-off is broken.

## 9. Common misunderstandings

| Misconception | Correct understanding |
| --- | --- |
| "With a starter, Spring Boot always creates every bean." | Starters bring dependencies onto the classpath; each auto-configuration still has to pass its conditions. |
| "`@ConditionalOnMissingBean` removes the default bean when a new bean appears after startup." | The condition decides bean definition registration during context construction; it is not a dynamic bean-replacement mechanism. |
| "`businessClock` has a different name from `defaultClock`, so it won't back off." | The condition checks **by type `Clock`**, regardless of bean name. |
| "Having `@Primary` prevents the default from being created." | `@Primary` chooses injection priority, not eliminating bean definitions. |
| "`@ConditionalOnProperty` always checks a boolean." | Matching behavior depends on `havingValue`, `matchIfMissing`, and property value. |
| "Just annotating `@AutoConfiguration` makes Boot scan and find it." | An auto-configuration provided via a JAR must be registered in `AutoConfiguration.imports`; it does not rely on component scan. |
| "A classpath condition on `@Bean` always avoids class loading errors." | If the method signature references a missing class, the JVM may resolve that type too early; separate configurations with class-level conditions. |
| "A negative match is always an error." | Back-off is often an **intentional negative match** when a user-provided bean already exists. |

## 10. Self-check questions

1. If `@ConditionalOnMissingBean(PaymentClient.class)` is on `@Bean` and the application has already declared a `PaymentClient` named `stripeClient`, will the default bean be registered? **No**, because the type-based condition is no longer true.
2. If `@ConditionalOnProperty(name = "demo.enabled", havingValue = "true", matchIfMissing = false)` is set and the property is absent, does the condition match? **No**.
3. If an auto-configuration contains three `@Bean` methods and only one backs off, do the other two automatically disappear? **No**, they are still evaluated according to their own conditions and class-level conditions.
4. When a user creates a bean with `@Primary`, can you conclude the default configuration definitely backs off? **No**; you must check whether the auto-configuration has `@ConditionalOnMissingBean` for the corresponding type/name.
5. To find out why `DataSourceAutoConfiguration` did not create a bean, what should you inspect first? **Condition Evaluation Report**, classpath, properties, and already-declared beans.

## Official reference documentation

- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): enabling/disabling, incrementally replacing default configuration, and condition evaluation reports.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): `AutoConfiguration.imports` registration, condition annotations, processing order, back-off, and `ApplicationContextRunner`.
- [Spring Boot — Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): conditions for exposing and securing monitoring endpoints.
