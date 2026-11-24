# @AutoConfigureBefore and @AutoConfigureAfter When Declaring Ordering Relationships

## 1. Goal and problem to solve

In Spring Boot, multiple **auto-configuration** classes contribute bean definitions into an `ApplicationContext`. One configuration may provide a foundational bean, while another should only operate after the foundational bean definitions have been evaluated. If Spring Boot applies them in the wrong relationship, conditions such as `@ConditionalOnBean` or `@ConditionalOnMissingBean` may produce unexpected results.

For example: `EngineAutoConfiguration` provides an `Engine` bean; `ReportAutoConfiguration` only creates `ReportService` if an `Engine` bean already exists. We want Spring Boot to **apply Engine configuration before Report configuration**, regardless of the order in which the two class names appear in the auto-configuration list.

Two annotations in the `org.springframework.boot.autoconfigure` package express this relationship:

- `@AutoConfigureBefore`: the **annotated** configuration must be applied **before** the specified configuration.
- `@AutoConfigureAfter`: the **annotated** configuration must be applied **after** the specified configuration.

This lesson helps you read the dependency direction accurately, choose between referencing by class or class name, distinguish **auto-configuration application order** from **bean initialization order**, and test relationships with Spring Boot 3.3 / Java 17+.

## 2. Understanding "before" and "after" correctly

Suppose there are two auto-configurations:

```text
EngineAutoConfiguration
       │
       │ provides Engine bean definition
       ▼
ReportAutoConfiguration
       │
       │ @ConditionalOnBean(Engine.class)
       ▼
ReportService bean definition (if condition matches)
```

Either of the following expresses the same ordering relationship:

```java
// Placed on EngineAutoConfiguration:
@AutoConfigureBefore(ReportAutoConfiguration.class)

// Or placed on ReportAutoConfiguration:
@AutoConfigureAfter(EngineAutoConfiguration.class)
```

These are **illustrative annotation snippets**, not a standalone Java program.

If `A` needs to be applied before `B`:

| Where is the annotation placed? | How it is written | Resulting relationship |
|---|---|---|
| On `A` | `@AutoConfigureBefore(B.class)` | `A → B` |
| On `B` | `@AutoConfigureAfter(A.class)` | `A → B` |
| On `A` | `@AutoConfigureAfter(B.class)` | `B → A` |
| On `B` | `@AutoConfigureBefore(A.class)` | `B → A` |

**The subject of the annotation is always the class carrying the annotation.** For instance, `@AutoConfigureAfter(EngineAutoConfiguration.class)` on `ReportAutoConfiguration` means "Report comes **after Engine**," not "Engine comes after Report."

### What the annotations actually guarantee

These annotations provide **ordering hints for applying auto-configuration classes** when Spring Boot sorts the selected configurations. This order affects **the order of registering and evaluating bean definitions**, which matters for conditions that inspect beans already processed at evaluation time.

They **do not force bean objects to be instantiated in the same order**. Runtime bean creation follows dependency injection, constructor/`@Bean` parameters, `@DependsOn`, lazy initialization, and related lifecycle mechanisms.

For example, both bean definitions may be registered in Engine-then-Report order, yet Spring can still instantiate instances in a different sequence if dependency relationships allow it. If `ReportService` takes `Engine` via constructor, Spring resolves the dependency when creating `ReportService`. Do not use `@AutoConfigureBefore` as a workaround for "this object's constructor must run before that object's constructor."

## 3. API: class reference, class name, and modern syntax

The two dedicated annotations support two attributes:

| Annotation | Attribute | Type | Meaning |
|---|---|---|---|
| `@AutoConfigureBefore` | `value` | `Class<?>[]` | Auto-configurations that must be applied after the current class |
| `@AutoConfigureBefore` | `name` | `String[]` | Fully qualified names of auto-configurations that must come after |
| `@AutoConfigureAfter` | `value` | `Class<?>[]` | Auto-configurations that must be applied before the current class |
| `@AutoConfigureAfter` | `name` | `String[]` | Fully qualified names of auto-configurations that must come before |

Example when the current module can directly reference the target class:

```java
@AutoConfiguration
@AutoConfigureAfter(EngineAutoConfiguration.class)
public class ReportAutoConfiguration {
    // ...
}
```

This is an illustrative fragment of a configuration class, assuming `EngineAutoConfiguration` is available on the compile classpath. With multiple targets:

```java
@AutoConfigureAfter({
    EngineAutoConfiguration.class,
    StorageAutoConfiguration.class
})
```

The current configuration must be evaluated after **both** target configurations; the annotation does not enforce an order between `EngineAutoConfiguration` and `StorageAutoConfiguration` unless a separate constraint exists.

If you want to avoid a compile-time dependency on a class that may only exist in another starter, use the `name` attribute:

```java
@AutoConfiguration
@AutoConfigureAfter(name = "com.example.engine.EngineAutoConfiguration")
public class ReportAutoConfiguration {
    // ...
}
```

The value must be a **fully qualified class name**, not a bean name or file path. For nested classes, the API docs require the JVM binary name with the `$` character, such as `com.example.Outer$InnerAutoConfiguration`.

Starting in Spring Boot 2.7, `@AutoConfiguration` also provides corresponding attributes and is commonly used directly:

```java
@AutoConfiguration(after = EngineAutoConfiguration.class)
public class ReportAutoConfiguration {
    // ...
}
```

```java
@AutoConfiguration(
    beforeName = "com.example.report.ReportAutoConfiguration")
public class EngineAutoConfiguration {
    // ...
}
```

Equivalence table in Spring Boot 3.3:

| Dedicated annotation | Equivalent attribute on `@AutoConfiguration` |
|---|---|
| `@AutoConfigureBefore(A.class)` | `@AutoConfiguration(before = A.class)` |
| `@AutoConfigureBefore(name = "pkg.A")` | `@AutoConfiguration(beforeName = "pkg.A")` |
| `@AutoConfigureAfter(A.class)` | `@AutoConfiguration(after = A.class)` |
| `@AutoConfigureAfter(name = "pkg.A")` | `@AutoConfiguration(afterName = "pkg.A")` |

**Recommendation:** in new code, use `@AutoConfiguration(before = …, after = …)` where appropriate to keep metadata on a single annotation; the two dedicated annotations remain meaningful and fully supported in Spring Boot 3.3. Pick one consistent style. You do not need to declare the same relationship on both ends when one side is clear enough; declaring both ends in the runnable example below is only so learners can see both annotations.

### Valid placement and applicability

Before/after directives are used by Spring Boot when **sorting imported auto-configurations**. They do not automatically add the target class to the imports list. If `EngineAutoConfiguration` is not selected or does not exist, `@AutoConfigureAfter(EngineAutoConfiguration.class)` does not turn Engine on.

In Spring Boot 3.3, an auto-configuration published by a library must be listed in:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line is the fully qualified name of an auto-configuration class. Do not place these classes under ordinary component scanning, and do not assume that putting `@AutoConfigureAfter` on an arbitrary `@Configuration` class will cause Spring to reorder manually registered configurations through the same mechanism.

## 4. Why is order especially critical for bean conditions?

Consider a scenario with two configurations:

```java
// Auto-configuration providing Engine:
@Bean
Engine engine() {
    return new Engine();
}

// Another auto-configuration that creates ReportService only when Engine exists:
@Bean
@ConditionalOnBean(Engine.class)
ReportService reportService(Engine engine) {
    return new ReportService(engine);
}
```

This is abbreviated illustrative code; `Engine` and `ReportService` are user-defined application types.

`@ConditionalOnBean` typically relies on bean definitions that Spring Boot **has already processed at the time the condition is evaluated**. If the class with `@ConditionalOnBean(Engine.class)` is evaluated before Engine's bean definition is added, the condition may fail to match, even though Engine appears later.

The `ReportAutoConfiguration after EngineAutoConfiguration` relationship helps order **auto-configuration evaluation** so the foundational bean definition has a chance to be registered first.

This does not mean simply adding `@AutoConfigureAfter` guarantees the bean exists. Engine can still fail to be created when:

- `EngineAutoConfiguration` is not imported or is excluded.
- A condition on `EngineAutoConfiguration` itself or its `@Bean` method does not match.
- Another configuration replaces Engine, or the declared bean type/name does not satisfy `@ConditionalOnBean`.
- The bean definition exists, yet subsequent bean instantiation fails due to an invalid dependency.

Order is **a necessary prerequisite for handling dependencies on registered bean definitions properly**, not a rule that overrides every other condition.

### Decision matrix

| Engine auto-config | Report auto-config | Ordering relationship | Expected outcome with `@ConditionalOnBean(Engine.class)` |
|---|---|---|---|
| Selected, creates Engine | Selected | Engine before Report | Report can create `ReportService` |
| Excluded from list | Selected | Report declares after Engine | Without Engine, Report's condition does not match |
| Selected, but Engine creation condition does not match | Selected | Engine before Report | Report does not match unless Engine comes from another source |
| Selected | Not selected | Engine declares before Report | Only Engine is present |
| Selected | Selected | No explicit relationship | Result may depend on application order; do not infer from line order in the file |

When there is no explicit relationship, you should not claim it will definitely fail or succeed: actual order also depends on metadata, other constraints, and the sorter. Declare required relationships explicitly rather than relying on coincidental ordering.

## 5. Java 17+, Spring Boot 3.3 example: testing before/after relationships

This example builds a small Maven project. `EngineAutoConfiguration` has `@AutoConfigureBefore`; `ReportAutoConfiguration` has `@AutoConfigureAfter`. The test intentionally lists **Report before Engine** in `AutoConfigurations.of(...)`, then verifies that Spring Boot still honors the ordering relationship properly.

Structure:

```text
ordering-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/order/
    │   │   ├── Engine.java
    │   │   ├── ReportService.java
    │   │   ├── EngineAutoConfiguration.java
    │   │   └── ReportAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/order/
        └── AutoConfigurationOrderTest.java
```

### 5.1. Maven: pom.xml

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

    <groupId>demo.order</groupId>
    <artifactId>ordering-demo</artifactId>
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
</project>
```

`spring-boot-starter` provides the Spring Boot/Spring Framework classes; `spring-boot-starter-test` provides `ApplicationContextRunner`, JUnit 5, and AssertJ for verifying results. No database or HTTP server is needed.

### 5.2. Foundation bean type: Engine.java

```java
package demo.order;

public record Engine(String name) {
}
```

`record` is valid Java 17 syntax. A named `Engine` instance helps tests verify whether the default bean or the user-defined bean was selected.

### 5.3. Dependent type: ReportService.java

```java
package demo.order;

public record ReportService(Engine engine) {
}
```

`ReportService` requires `Engine`. This relationship expresses dependency injection at **instance creation**; it is separate from **auto-configuration class** ordering directives.

### 5.4. Auto-configuration providing Engine

File `EngineAutoConfiguration.java`:

```java
package demo.order;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigureBefore;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@AutoConfigureBefore(ReportAutoConfiguration.class)
public class EngineAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Engine.class)
    Engine engine() {
        return new Engine("auto-engine");
    }
}
```

Here, `@AutoConfigureBefore(ReportAutoConfiguration.class)` asks for Engine to be **applied before Report**. `@ConditionalOnMissingBean` yields if the user has already provided a matching `Engine` bean.

### 5.5. Auto-configuration depending on Engine

File `ReportAutoConfiguration.java`:

```java
package demo.order;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigureAfter;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@AutoConfigureAfter(EngineAutoConfiguration.class)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnBean(Engine.class)
    @ConditionalOnMissingBean(ReportService.class)
    ReportService reportService(Engine engine) {
        return new ReportService(engine);
    }
}
```

`@AutoConfigureAfter(EngineAutoConfiguration.class)` expresses the same direction **Engine → Report**. Once the Engine bean definition is registered, `@ConditionalOnBean(Engine.class)` can match and `ReportService` is created, unless a replacement bean already exists.

In production systems, only a single before/after relationship declared appropriately on one side is needed; the example puts both annotations only to illustrate the syntax, not as a strict requirement.

### 5.6. Publishing auto-configurations for a real application

Create `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` with the exact content:

```text
demo.order.EngineAutoConfiguration
demo.order.ReportAutoConfiguration
```

Spring Boot uses this file to discover a library's auto-configurations. Line order in the file **is not an API for describing dependencies**: domain relationships are declared via `@AutoConfigureBefore`/`@AutoConfigureAfter` metadata or the equivalent attributes on `@AutoConfiguration`.

In the `ApplicationContextRunner` test below, we explicitly list the classes to load into the test context; that does not replace the imports file in an actual published library.

### 5.7. Testing auto-configurations

File `AutoConfigurationOrderTest.java`:

```java
package demo.order;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationOrderTest {

    @Test
    void bothConfigurationsApplyInRequiredOrder() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        ReportAutoConfiguration.class,
                        EngineAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Engine.class);
                    assertThat(context).hasSingleBean(ReportService.class);
                    assertThat(context.getBean(ReportService.class).engine())
                            .isSameAs(context.getBean(Engine.class));
                    assertThat(context.getBean(Engine.class).name())
                            .isEqualTo("auto-engine");
                });
    }

    @Test
    void reportConfigurationAloneDoesNotInventEngine() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        ReportAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(Engine.class);
                    assertThat(context).doesNotHaveBean(ReportService.class);
                });
    }

    @Test
    void engineConfigurationAloneDoesNotInventReportService() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        EngineAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Engine.class);
                    assertThat(context).doesNotHaveBean(ReportService.class);
                });
    }

    @Test
    void userEngineOverridesDefaultWithoutBreakingReport() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserEngineConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        ReportAutoConfiguration.class,
                        EngineAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(Engine.class);
                    assertThat(context).hasSingleBean(ReportService.class);
                    Engine engine = context.getBean(Engine.class);
                    assertThat(engine.name()).isEqualTo("user-engine");
                    assertThat(context.getBean(ReportService.class).engine())
                            .isSameAs(engine);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserEngineConfiguration {
        @Bean
        Engine engine() {
            return new Engine("user-engine");
        }
    }
}
```

From the `ordering-demo` directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn test
```

**Expected result:** all four test methods PASS. The Maven Surefire report should total **4 tests, 0 failures, 0 errors**, assuming the project contains only the test class above. Exact Maven log output depends on the Maven/Surefire version, so no verbatim stdout transcript is assumed.

Explanation of each scenario:

1. **Both auto-configs present:** even though `AutoConfigurations.of(Report, Engine)` passes them in reverse order, the auto-configuration sorter honors Engine before Report. Both `Engine` and `ReportService` are registered; Report receives that exact Engine bean.
2. **Only Report:** `@AutoConfigureAfter` does not import Engine for you. Because no `Engine` bean is seen, `@ConditionalOnBean(Engine.class)` does not match; `ReportService` is absent.
3. **Only Engine:** `@AutoConfigureBefore` does not import Report for you. Only the Engine bean exists; there is no `ReportService`.
4. **User supplies Engine:** user configuration is processed by the runner before auto-configurations; `@ConditionalOnMissingBean(Engine.class)` lets the default Engine back off. Report still sees the user's Engine and registers `ReportService`.

**Testing note:** `ApplicationContextRunner` creates an isolated context per test. `AutoConfigurations.of(...)` simulates auto-configuration ordering just like a real application; this is far more appropriate than manually calling `context.register(…)` and guessing the parse order of regular `@Configuration` classes.

## 6. Choosing how to declare

| What you need to express | Where to write it? | Suggestion |
|---|---|---|
| `A` must come before `B` | `A`: `@AutoConfigureBefore(B.class)` | Use when A knows B and has an appropriate compile-time dependency |
| `B` must come after `A` | `B`: `@AutoConfigureAfter(A.class)` | Use when B depends on bean definitions provided by A |
| Need an "after" relationship where the target class may be absent at compile time | `@AutoConfigureAfter(name = "pkg.A")` | Use fully qualified class name, avoiding direct references |
| Writing a new auto-config with `@AutoConfiguration` | `@AutoConfiguration(after = A.class)` | Integrated syntax, equivalent to `@AutoConfigureAfter` |
| Just want general priority among independent auto-configs | `@AutoConfigureOrder` | Consider when there is no concrete dependency |
| Want bean A created before bean B | Dependency injection or `@DependsOn` | Do not use auto-configuration ordering as a lifecycle mechanism |
| Want to order elements injected as a List | `@Order` / `Ordered` depending on context | This is collection/extension ordering, distinct from auto-configuration ordering |

### BEFORE vs. AFTER: which side to pick?

If the author of `ReportAutoConfiguration` knows for certain it depends on Engine, the most readable form is:

```java
@AutoConfiguration(after = EngineAutoConfiguration.class)
public class ReportAutoConfiguration {
    // can contribute ReportService only if Engine is suitable
}
```

If the Engine author wants to state that a set of other auto-configurations must be evaluated after it, `before` is also reasonable. However, avoid creating unnecessary bidirectional dependencies or forcing a foundational module to import classes from dependent modules just to write `before`; in those cases, using `after` on the dependent side or declaring via string name is more natural.

## 7. Complex relationships: graphs, multiple targets, and cycles

A valid chain:

```text
StorageAutoConfiguration
          │
          ▼
EngineAutoConfiguration
          │
          ▼
ReportAutoConfiguration
```

Can be expressed as:

```java
// On EngineAutoConfiguration:
@AutoConfigureAfter(StorageAutoConfiguration.class)

// On ReportAutoConfiguration:
@AutoConfigureAfter(EngineAutoConfiguration.class)
```

From these two relationships, Storage precedes Engine and Engine precedes Report. You do not need to assign absolute order numbers to each class.

If `MetricsAutoConfiguration` is completely independent, the graph does not establish a unique relative position between Metrics and those three classes. A **before/after** constraint is generally a **relative order**, not a global ordering guarantee across all auto-configurations.

### Avoiding cycles

Bad design example:

```java
// On AAutoConfiguration:
@AutoConfigureAfter(BAutoConfiguration.class)

// On BAutoConfiguration:
@AutoConfigureAfter(AAutoConfiguration.class)
```

The two directives require A after B **and** B after A; no valid order satisfies both. Do not try to "fix" this by switching to `@AutoConfigureOrder`; instead, revisit responsibility boundaries, extract an intermediate bean, or remove an unnecessary constraint.

Do not speculate on exact error messages or resolution strategies across every version when encountering a cycle. The key point is to **design an acyclic dependency graph** and test context startup with the relevant combinations of auto-configurations.

### Constraints referencing an unselected auto-configuration

Writing:

```java
@AutoConfigureAfter(name =
        "com.example.optional.OptionalClientAutoConfiguration")
```

does not force `OptionalClientAutoConfiguration` to exist on the classpath or be imported. When the target class is absent, that relationship creates no beans. If the current configuration genuinely requires a library class, also use `@ConditionalOnClass` or an appropriate condition to express that requirement independently of ordering.

## 8. Misconceptions to avoid

### Misconception 1: "After means the bean initializes later"

**Incorrect.** It means the **auto-configuration is applied later**. Bean creation order depends on dependency relationships. One bean may be created lazily via `@Lazy`; another may be created early due to a dependency chain. If you need to control initialization order for side effects, design explicit dependencies, consider `@DependsOn`, or use appropriate lifecycle callbacks.

### Misconception 2: "Declaring after automatically enables the target auto-config"

**Incorrect.** `@AutoConfigureAfter` is not `@Import`, not a Maven/Gradle dependency, and does not bypass `@ConditionalOnClass`. It only specifies a relationship among candidates already participating in auto-configuration.

### Misconception 3: "The order in AutoConfiguration.imports is the final order"

**Do not rely on it.** The imports file declares **candidates**. Spring Boot still sorts auto-configs using metadata and declared relationships. Similarly, the order classes are passed to `AutoConfigurations.of(...)` in tests must not be used to express dependencies instead of annotations.

### Misconception 4: "@Order, @AutoConfigureOrder, and @DependsOn are equivalent"

They serve different needs:

- `@AutoConfigureBefore`/`@AutoConfigureAfter`: relative relationship between **auto-configuration classes**.
- `@AutoConfigureOrder`: general priority order for auto-configurations when there is no specific dependency; does not replace the dependency graph.
- `@Order`/`Ordered`: ordering of multiple objects, extension elements, beans injected into collections, or Spring components depending on the injection point.
- `@DependsOn`: **initialization/destruction** dependency between bean instances within the same context per the Spring contract.

Do not use an annotation from one layer to fix an issue belonging to another.

### Misconception 5: "@ConditionalOnBean will see every bean in the application"

**Not true at all times.** The condition is evaluated while configurations and bean definitions are being processed. A bean can appear after the condition has already completed evaluation. Hence both auto-configuration application order and the declared return type of `@Bean` methods affect whether a condition can detect a bean's existence.

### Misconception 6: "Auto-config ordering applies to any arbitrary @Configuration"

**Not a general guarantee.** Spring Boot uses auto-configuration metadata for the set of auto-configuration candidates imported via Boot's mechanism. For ordinary application configurations, registration order via `@Import`, component scanning, and Spring's configuration processing follow their own rules. Do not rely on `@AutoConfigureAfter` to control execution order for arbitrary Spring `@Configuration` classes.

## 9. Checklist when declaring ordering relationships

Before adding an annotation, answer:

1. **Which class creates the bean definition first?** Identify the specific auto-config name and bean type rather than guessing from package names.
2. **Who depends on whom?** Draw an arrow A → B and check whether `@AutoConfigureBefore` goes on A or `@AutoConfigureAfter` goes on B.
3. **Are they actually auto-configurations?** Both classes must participate in the auto-config import process in real usage; an absent target class is not loaded automatically by the annotation.
4. **Is there a compile-time dependency?** If not, or if the dependency is optional, consider `name`/`beforeName`/`afterName`.
5. **Are there any cycles?** Review existing relationships to ensure the graph admits a valid order.
6. **Is there confusion with bean lifecycle?** If the goal is creating/initializing instances in order, solve it at the bean dependency level.
7. **Have combinations been tested?** Run tests with both configurations, only A, only B, and with a user-provided replacement bean.

In an application with multiple starters, check the **Condition Evaluation Report** when a bean fails to appear. Run Spring Boot with `--debug` or inspect the Actuator `/actuator/conditions` endpoint (if installed, enabled, and exposed) to see which conditions matched or did not match. Combine that with checking the list of actually imported auto-configs rather than reading annotations alone.

## 10. Self-check questions

**Question 1.** `MailAutoConfiguration` needs a bean contributed by `TransportAutoConfiguration`. To ensure Mail is applied after Transport, which annotation should be placed on Mail?

**Answer:** `@AutoConfigureAfter(TransportAutoConfiguration.class)` or `@AutoConfiguration(after = TransportAutoConfiguration.class)`.

**Question 2.** What does placing `@AutoConfigureBefore(A.class)` on B mean?

**Answer:** B is applied before A; not A before B.

**Question 3.** A declares after B, yet B is not imported into the application. Does A automatically cause B to appear?

**Answer:** No. An ordering relationship does not activate the target class or register beans on its behalf.

**Question 4.** A is applied before B; does that guarantee bean A is instantiated before bean B?

**Answer:** No. Auto-configuration application order determines the order of registering bean definitions, whereas instance initialization depends on dependencies and lifecycle.

**Question 5.** A library wants to order `ReportAutoConfiguration` after `com.vendor.storage.StorageAutoConfiguration` without taking a compile-time dependency on the vendor library. What is a sensible declaration?

**Answer:** `@AutoConfigureAfter(name = "com.vendor.storage.StorageAutoConfiguration")` or `@AutoConfiguration(afterName = "com.vendor.storage.StorageAutoConfiguration")`.

## 11. Summary

- `@AutoConfigureBefore(Target.class)`: **current class before Target**.
- `@AutoConfigureAfter(Target.class)`: **current class after Target**.
- `@AutoConfiguration(before = …, after = …, beforeName = …, afterName = …)` is the equivalent syntax in Spring Boot 3.3.
- This relationship applies only during **auto-configuration sorting** and affects **bean definition/condition evaluation**; it neither dictates bean object creation order nor automatically imports the referenced configuration.
- When ordering is a real dependency, declare explicit relationships, avoid cycles, and verify with `ApplicationContextRunner` across combinations with and without the related auto-configs.

### Official documentation

- [Spring Boot 3.3 — AutoConfigureBefore](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html)
- [Spring Boot 3.3 — AutoConfigureAfter](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html)
- [Spring Boot 3.3 — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot — Testing Auto-configuration with ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
