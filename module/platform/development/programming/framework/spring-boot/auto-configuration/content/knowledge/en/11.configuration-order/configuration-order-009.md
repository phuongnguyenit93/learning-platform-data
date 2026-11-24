# Do Not Rely on Line Order in the imports File or Dependency Order

## 1. Problem to solve

In Spring Boot Auto Configuration, a library may contribute multiple auto-configuration classes. Some classes must be **evaluated before** or **after** others, especially when using conditions such as `@ConditionalOnBean` and `@ConditionalOnMissingBean`. A common mistake is trying to achieve that order by:

- Moving a class name higher or lower in **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
- Changing the order of library declarations in **pom.xml**, **build.gradle**, or a dependency list.
- Relying on the order observed in logs from a single run and treating it as a long-term guarantee.

None of these approaches is a contract for coordinating auto-configurations. Spring Boot **collects and sorts** auto-configuration candidates using metadata and its own rules. To express relationships between auto-configurations, use **@AutoConfiguration(before = ... / after = ...)** or equivalent annotations; use **@AutoConfigureOrder** when a general priority level is needed.

> Rule: **Listing order in the source is not a guaranteed semantic order. Configuration relationships must be declared explicitly.**

This lesson focuses on **auto-configuration processing order**, distinct from bean object creation order or business execution order.

## 2. What is AutoConfiguration.imports responsible for?

In Spring Boot 3.x, a library publishes its auto-configuration classes through the resource at the exact path:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example content:

~~~text
com.example.library.autoconfigure.ReportAutoConfiguration
com.example.library.autoconfigure.ClockAutoConfiguration
~~~

Each line is a fully qualified class name. The file sits on the library's or application's classpath. Spring Boot uses its import-candidates mechanism to discover auto-configurations, merges lists from relevant classpath sources, and then runs selection, condition filtering, and **sorting**.

**What the imports file guarantees:** helping Spring Boot **discover which classes are auto-configuration candidates**.

**What the imports file does NOT guarantee:** that the class on the first line is processed before every class below it; that the order across multiple imports files in different JARs is a fixed domain order; or that the first-listed class's beans are initialized first.

Spring Boot may need to:

1. Read candidates from multiple JARs containing imports files.
2. Deduplicate candidates and process exclusions (`exclude`/`excludeName` or related properties).
3. Apply candidate filtering based on environment/classpath and metadata.
4. **Sort auto-configurations** according to declared before/after relationships and priority.
5. Process bean definitions and conditions as configurations are evaluated.

This is a conceptual model; exact internal steps can change across versions. **Do not rely on line numbers** to predict registration order in the ApplicationContext.

## 3. Why doesn't dependency order replace configuration order?

A project might write:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>report-starter</artifactId>
        <version>1.0.0</version>
    </dependency>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>clock-starter</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
~~~

This is an **illustrative XML snippet of pom.xml**, not a complete POM. Declaring `report-starter` before `clock-starter` does not mean `ReportAutoConfiguration` is evaluated before `ClockAutoConfiguration`. The build tool resolves dependencies and assembles the classpath; Spring Boot is responsible for discovering, filtering, and ordering auto-configurations.

Similarly with Gradle:

~~~groovy
dependencies {
    implementation 'com.example:report-starter:1.0.0'
    implementation 'com.example:clock-starter:1.0.0'
}
~~~

Swapping two lines is not a mechanism for controlling dependency injection or `@ConditionalOnBean`. Classpath order can vary by build tool, packaging style, version, or dependency graph; even when one ordering happens to yield the desired result by coincidence, it still **does not express an auto-configuration relationship** that maintainers can rely on.

**Two independent roles:**

| Question | Belongs to |
| --- | --- |
| Are the library's classes placed on the classpath? | Maven/Gradle dependency resolution |
| Which auto-configurations are discovered? | `AutoConfiguration.imports` and Spring Boot's import mechanism |
| Must auto-configuration A be processed before/after B? | `@AutoConfiguration(before/after)`, Spring Boot ordering metadata |
| Is bean X registered? | Conditions on configuration/`@Bean`, e.g., `@ConditionalOnBean` |
| When creating bean Y, must dependency X exist? | Dependency injection mechanism, `@DependsOn` if an initialization constraint is genuinely needed |

## 4. Declaring order properly

### 4.1. @AutoConfiguration(after = ...)

If `ReportAutoConfiguration` has a condition that needs to observe a bean registered by `ClockAutoConfiguration`, declare:

~~~java
@AutoConfiguration(after = ClockAutoConfiguration.class)
public class ReportAutoConfiguration {
    // @Bean methods for reporting.
}
~~~

This is an **illustrative class snippet**, not a standalone program. Meaning: Spring Boot should **process `ClockAutoConfiguration` before `ReportAutoConfiguration` within the auto-configuration set**, regardless of the order in which the imports file lists their names.

You still must use an appropriate condition such as `@ConditionalOnBean(Clock.class)` if `ReportService` should only register when a `Clock` actually exists. **`after` does not guarantee the `Clock` bean exists**: `ClockAutoConfiguration` might be excluded, the classpath might not match, or an internal condition might fail.

### 4.2. @AutoConfiguration(before = ...)

If your class needs to be evaluated before another class:

~~~java
@AutoConfiguration(before = ReportAutoConfiguration.class)
public class ClockAutoConfiguration {
    // Register bean inspected by ReportAutoConfiguration.
}
~~~

Usually declaring the relationship clearly on one side is enough. Avoid declaring conflicting relationships or cycles such as A after B while B is also after A. A before/after graph must be coherently orderable.

**`before`/`after` only describes relationships among relevant auto-configurations**, not a global order across all application-authored `@Configuration` classes.

### 4.3. afterName/beforeName when the other class is optional

When avoiding a compile-time dependency on a class from an optional module, use **the fully qualified class name as a string**:

~~~java
@AutoConfiguration(
        afterName = "com.example.optional.OptionalStorageAutoConfiguration")
public class ReportingAutoConfiguration {
    // @Bean methods for reporting.
}
~~~

The example above is **illustrative** and does not require `OptionalStorageAutoConfiguration` on the classpath to compile `ReportingAutoConfiguration`. If the referenced auto-configuration is not an active candidate being processed, that relationship neither pulls in the missing module nor creates its beans.

### 4.4. Equivalent annotations and general priority

In Spring Boot you may encounter these annotations:

- **@AutoConfigureAfter(SomeAutoConfiguration.class)** and **@AutoConfigureBefore(SomeAutoConfiguration.class)**: the earlier form of declaring relationships; `@AutoConfiguration(after/before)` lets you express them directly on the primary annotation.
- **@AutoConfigureOrder(n)**: used when a general priority level for an auto-configuration is needed. Smaller values have higher priority per `Ordered` rules, yet **explicit `before/after` relationships** express dependencies much more clearly and should be preferred when a relationship is meaningful.
- **@Order** from Spring Framework generally relates to collection priority or ordered components in other contexts. Do not put `@Order` arbitrarily on an auto-configuration to replace `AutoConfigure` ordering.

**In practice:** Use **after** when your beans/conditions need to observe another configuration's results; use **before** when another configuration needs to observe yours; use **afterName/beforeName** when the other module is optional; use **@AutoConfigureOrder** only when you truly need general priority without describing a concrete dependency.

## 5. Why can ordering change @ConditionalOnBean outcomes?

Suppose:

- `ClockAutoConfiguration` declares a `Clock` bean if no user-supplied `Clock` exists yet.
- `ReportAutoConfiguration` registers `ReportService` **only if** a `Clock` bean already exists.

If `ReportAutoConfiguration` is processed when `Clock`'s bean definition **has not been processed yet**, `@ConditionalOnBean(Clock.class)` can evaluate to **no match**. Consequently `ReportService` is not registered, even though `Clock` configuration appears elsewhere during processing. This is the scenario requiring **after**.

~~~text
Without ordering declaration (not guaranteed):
  ReportAutoConfiguration
     |
     +-- @ConditionalOnBean(Clock.class) -> may not see Clock yet
  ClockAutoConfiguration
     |
     +-- registers Clock too late for the earlier evaluation

With @AutoConfiguration(after = ClockAutoConfiguration.class):
  ClockAutoConfiguration
     |
     +-- registers Clock bean definition when conditions match
  ReportAutoConfiguration
     |
     +-- @ConditionalOnBean(Clock.class) -> can now see Clock
     +-- registers ReportService
~~~

Distinguish **a bean definition already known** from **a bean object already initialized**. When checking conditions, Spring Boot primarily works with bean definition/context metadata at that moment; do not interpret conditions as waiting for every singleton to finish instantiating before evaluating.

Similarly, `@ConditionalOnMissingBean` checks "no matching bean seen yet" at evaluation time. Normally Spring Boot processes auto-configurations **after** application-declared bean definitions, giving custom beans a chance to suppress auto-configuration defaults. When two auto-configurations have a default/optional relationship with each other, they should still declare the required order rather than relying on lines in imports.

## 6. Runnable example: reversing imports order while keeping the right result

This example uses Java 17+ and **Spring Boot 3.3.5** with Maven. We intentionally place `ReportAutoConfiguration` **before** `ClockAutoConfiguration` in imports, then declare `after` to express the true desired order.

### 6.1. Directory tree

~~~text
order-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/
    │   │       ├── app/
    │   │       │   └── OrderDemoApplication.java
    │   │       └── library/autoconfigure/
    │   │           ├── ClockAutoConfiguration.java
    │   │           ├── ReportAutoConfiguration.java
    │   │           └── ReportService.java
    │   └── resources/
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/app/
            └── AutoConfigurationOrderTest.java
~~~

Note: the `@SpringBootApplication` class resides in package **com.example.app**, while the auto-configurations reside in **com.example.library.autoconfigure**, avoiding ordinary component scanning picking up the auto-configuration classes and accidentally registering them another way. This is an important detail when testing auto-configurations inside a single project.

### 6.2. pom.xml

~~~xml
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
    <groupId>com.example</groupId>
    <artifactId>order-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
~~~

### 6.3. ClockAutoConfiguration.java

**src/main/java/com/example/library/autoconfigure/ClockAutoConfiguration.java**

~~~java
package com.example.library.autoconfigure;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    Clock appClock() {
        // Fixed Clock solely for deterministic example output.
        return Clock.fixed(
                Instant.parse("2026-01-02T03:04:05Z"),
                ZoneOffset.UTC);
    }
}
~~~

This snippet returns a fixed Clock so stdout is easy to verify; real applications typically use **`Clock.systemUTC()`** or a suitable clock. `@ConditionalOnMissingBean(Clock.class)` lets the application supply its own Clock and causes the fallback `appClock` bean not to be registered.

### 6.4. ReportService.java

**src/main/java/com/example/library/autoconfigure/ReportService.java**

~~~java
package com.example.library.autoconfigure;

import java.time.Clock;

public class ReportService {
    private final Clock clock;

    public ReportService(Clock clock) {
        this.clock = clock;
    }

    public String generatedAt() {
        return clock.instant().toString();
    }
}
~~~

`ReportService` depends on `Clock`. Constructor injection guarantees that when instantiating `ReportService`, Spring must resolve the `Clock` dependency; it **does not by itself guarantee** that a `@ConditionalOnBean` condition at registration time was evaluated in the right order. Therefore ordering metadata between the two auto-configurations is still needed.

### 6.5. ReportAutoConfiguration.java

**src/main/java/com/example/library/autoconfigure/ReportAutoConfiguration.java**

~~~java
package com.example.library.autoconfigure;

import java.time.Clock;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = ClockAutoConfiguration.class)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnBean(Clock.class)
    @ConditionalOnMissingBean(ReportService.class)
    ReportService reportService(Clock clock) {
        return new ReportService(clock);
    }
}
~~~

This is the **relationship that genuinely matters**: `ReportAutoConfiguration` must be evaluated **after** `ClockAutoConfiguration`. `@ConditionalOnBean` registers `ReportService` only if a matching `Clock` is already present during evaluation; `@ConditionalOnMissingBean(ReportService.class)` lets users declare their own `ReportService`.

If `ClockAutoConfiguration` is excluded or does not register a `Clock`, declaring `after` does not turn a failing condition into a match; `ReportService` will not be registered either unless another `Clock` source exists.

### 6.6. AutoConfiguration.imports — intentionally written in reverse order

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.library.autoconfigure.ReportAutoConfiguration
com.example.library.autoconfigure.ClockAutoConfiguration
~~~

Report sits on line 1, Clock sits on line 2. **No need to swap the two lines.** Spring Boot reads the candidates and honors `@AutoConfiguration(after = ClockAutoConfiguration.class)`, rather than treating line order as a promise about processing relationships.

### 6.7. OrderDemoApplication.java

**src/main/java/com/example/app/OrderDemoApplication.java**

~~~java
package com.example.app;

import com.example.library.autoconfigure.ReportService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showReport(ReportService service) {
        return args ->
                System.out.println("Report time: " + service.generatedAt());
    }
}
~~~

Run:

~~~bash
mvn spring-boot:run
~~~

Besides Spring Boot's startup logs, `CommandLineRunner` prints the exact line:

~~~text
Report time: 2026-01-02T03:04:05Z
~~~

**Explanation:** `ClockAutoConfiguration` provides `Clock`; `ReportAutoConfiguration` is processed afterwards, `@ConditionalOnBean(Clock.class)` matches, `ReportService` is registered; `CommandLineRunner` receives `ReportService` and prints the fixed timestamp. This outcome does not require the two lines in imports to be in forward order.

### 6.8. Automated verification with ApplicationContextRunner

Add **src/test/java/com/example/app/AutoConfigurationOrderTest.java**:

~~~java
package com.example.app;

import java.time.Clock;
import com.example.library.autoconfigure.ClockAutoConfiguration;
import com.example.library.autoconfigure.ReportAutoConfiguration;
import com.example.library.autoconfigure.ReportService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationOrderTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(
                            ReportAutoConfiguration.class,
                            ClockAutoConfiguration.class));

    @Test
    void reportConfigurationIsEvaluatedAfterClockConfiguration() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Clock.class);
            assertThat(context).hasSingleBean(ReportService.class);
            assertThat(context.getBean(ReportService.class).generatedAt())
                    .isEqualTo("2026-01-02T03:04:05Z");
        });
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The test intentionally passes `ReportAutoConfiguration` before `ClockAutoConfiguration` when building the auto-configuration set. The `after` metadata still ensures conditions are evaluated in the right relationship, so the test verifies `Clock` and `ReportService` both exist. Detailed Maven output depends on the environment; **expected result is test passed with no assertion failures**.

**Deliberate experiment:** remove `after` from `ReportAutoConfiguration`, leaving imports and the test list as above. If the observed order then causes Report's condition to be evaluated before Clock, the test will no longer have `ReportService`. Never build a system relying on "it still passes on my machine" when `after` is missing: an undeclared order is not a contract. Restore `after` for an explicit design.

## 7. Auto-configuration order vs. bean creation order

This is a major confusion:

- **@AutoConfiguration(after = X.class)**: relates to **the processing order of auto-configuration classes / bean definitions**. It helps when conditions need to see already-registered bean definitions.
- **Constructor injection**: when creating bean Y requires X, the container must resolve X first to pass into Y's constructor, provided a matching dependency exists.
- **@DependsOn("x")**: declares an additional **bean initialization/destruction** dependency when a specific lifecycle order beyond constructor injection is needed. If bean `x` does not exist, the configuration can even fail.
- **ApplicationRunner/CommandLineRunner and lifecycle hooks**: control activity after the context is ready or along appropriate lifecycle phases; do not use imports order to coordinate business execution.

Illustrative example:

~~~java
@Bean
@DependsOn("cacheInitializer")
public CacheWorker cacheWorker() {
    return new CacheWorker();
}
~~~

This is merely an **illustrative method inside a `@Configuration` class**, assuming a bean named `cacheInitializer` and class `CacheWorker` exist. `@DependsOn` is for bean lifecycle; it does not replace `@AutoConfiguration(after=...)` to ensure `@ConditionalOnBean` sees a bean definition at condition evaluation time.

**Do not confuse `@Order` with `@AutoConfigureOrder`:** `@Order` is typically used to sort components such as `List<Handler>` or listeners in Spring-supported contexts. It is not a reliable mechanism to force two auto-configurations to be processed in a conditional relationship.

## 8. Actual conditions still determine whether a bean is registered

Evaluating in the right order **does not mean** a given auto-configuration will definitely create a bean. Beyond `before`/`after`, you must also check:

- Are the required classes/dependencies on the classpath (`@ConditionalOnClass`)?
- Was the prerequisite bean present when the condition was evaluated (`@ConditionalOnBean`)?
- Did the application already provide a bean so the default auto-configuration must back off (`@ConditionalOnMissingBean`)?
- Does a configuration property or profile enable the feature (`@ConditionalOnProperty`, `@Profile`)?
- Was the auto-configuration excluded or left undiscovered?

For example, `@AutoConfiguration(after = DatabaseAutoConfiguration.class)` only sets a relationship between **auto-configuration candidates**; it does not add a JDBC driver, does not create a `DataSource` if `DatabaseAutoConfiguration`'s conditions fail, and does not make an excluded bean appear.

**Right mindset:** order ensures conditions are **evaluated in the intended context**; the conditions and dependencies themselves determine whether beans are registered and created.

## 9. How to diagnose when ordering yields unexpected results

Follow step by step:

1. **Confirm the class is truly a candidate:** its fully qualified name must appear at the exact `AutoConfiguration.imports` path packaged in the JAR. With Spring Boot 3.x, do not use the legacy `spring.factories` mechanism as the default auto-configuration registration source if the project follows the imports standard.
2. **Check for excluded configurations or unmatched conditions:** run with **--debug** to inspect the Condition Evaluation Report. If Actuator is present and endpoints are appropriately configured/exposed, **`/actuator/conditions`** can also help inspect it.
3. **Locate `@ConditionalOnBean`/`@ConditionalOnMissingBean`:** note the exact bean type/name being checked and why its definition must appear first. If it is a relationship between two auto-configurations, declare `after`/`before`.
4. **Re-check component scan scope:** an auto-configuration scanned as an ordinary `@Configuration` can cause tests to stop reflecting the official imports loading path. In this example, `com.example.app` does not scan package `com.example.library.autoconfigure`.
5. **Check classpath and user-defined beans:** an auto-configuration may be processed in the right order yet still produce no bean due to another condition or an application override.
6. **Write an ApplicationContextRunner test:** load the specific set of auto-configurations, verify bean presence/absence when toggling prerequisites, vary user configuration, and intentionally reverse the candidate listing order. Tests must assert **domain/bean outcomes**, not merely check imports line numbers.

Never use swapping two lines in imports or two dependencies as a "fix" for a failing condition: that leaves an implicit assumption behind and can break across JAR, build-tool, or Spring Boot version changes.

## 10. Design mistakes to avoid

| Common pitfall | Problem | Fix |
| --- | --- | --- |
| Putting ClassA before ClassB in `AutoConfiguration.imports` to "force it to run first" | The imports file is a candidate list, with no such ordering contract | Declare `@AutoConfiguration(before/after)` |
| Swapping two starters in `pom.xml`/`build.gradle` | Dependency declarations do not describe auto-configuration processing relationships | Keep dependencies per classpath needs; declare ordering via Spring Boot metadata |
| Using `@Order` instead of `after` | `@Order` is not the dedicated tool for expressing auto-configuration relationships | Use `after`/`before`, or `@AutoConfigureOrder` for general priority |
| Using `after` and assuming the prerequisite bean definitely exists | `after` only orders evaluation; it does not make conditions match automatically | Use `@ConditionalOnBean` or check prerequisites explicitly |
| Switching `@ConditionalOnBean` to `@Primary` to "fix order" | `@Primary` picks a candidate at injection time, not ensuring a bean definition was registered | Fix conditions and ordering appropriately |
| Putting auto-configurations inside ordinary component-scan packages | Classes may be processed as application config, masking imports/ordering bugs | Separate packages and load via `AutoConfiguration.imports` |
| Using `after` to force startup methods to run in order | `after` is not lifecycle dependency | Use dependency injection, `@DependsOn`, or appropriate lifecycle APIs |
| Creating `before`/`after` cycles across multiple classes | Conflicting ordering relationships, hard to maintain | Design acyclic directed dependencies; split configurations if needed |

## 11. Self-check questions

**Question 1.** In `AutoConfiguration.imports`, A appears before B. Can you conclude A's beans are registered or initialized before B's?  
**Answer:** No. The imports file lists candidates; Spring Boot has its own auto-configuration sorting mechanism. Processing order and initialization order are two distinct concerns.

**Question 2.** `ReportAutoConfiguration` has `@ConditionalOnBean(Clock.class)`; `Clock` is registered by another auto-configuration. What should be expressed?  
**Answer:** Declare **@AutoConfiguration(after = ClockAutoConfiguration.class)** so Report is evaluated after Clock, while keeping the condition that verifies Clock actually exists.

**Question 3.** Does changing Maven dependency order guarantee `@ConditionalOnBean` matches?  
**Answer:** No. Dependency resolution determines the classpath; it is not an API guaranteeing the evaluation order of auto-configurations.

**Question 4.** What should you use to order relative to an optional auto-configuration without adding a compile-time dependency?  
**Answer:** **afterName** or **beforeName** with the fully qualified class name; you still must handle the case where that auto-configuration is absent.

**Question 5.** Does `@AutoConfiguration(after = X.class)` guarantee X must create its bean?  
**Answer:** No. X can be excluded or fail its conditions. `after` only expresses order among evaluated candidates.

**Question 6.** If bean `worker` must initialize after `initializer` even though it does not depend on `initializer` via constructor, should you use `after` on auto-configuration?  
**Answer:** You should not. That is a **bean lifecycle** constraint; consider `@DependsOn` or an explicit dependency design, depending on requirements.

## 12. Takeaways to apply

In Spring Boot Auto Configuration, **`AutoConfiguration.imports` answers "which configurations may be loaded?"**, whereas **@AutoConfiguration(before/after) answers "among related configurations, which must be evaluated first?"**. Maven/Gradle answers **providing dependencies on the classpath**. `@Conditional…` annotations decide whether beans are registered, and dependency injection/lifecycle determines how beans are created and wired.

Whenever an auto-configuration needs to see a bean definition provided by another auto-configuration, declare the `before`/`after` relationship right on the class and verify with `ApplicationContextRunner` and the condition report. **Do not rely on line order in imports or dependency declaration order.**
