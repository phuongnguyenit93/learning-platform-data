# `@AutoConfigureOrder` for Priority Among Auto-Configurations in Spring Boot

When developing a **Spring Boot starter** or integrating multiple libraries, multiple auto-configurations may sometimes want to register a default bean. The order in which those configurations are processed can then affect the outcome of `@ConditionalOnBean` and `@ConditionalOnMissingBean`. Spring Boot provides `@AutoConfigureOrder` to assign a **general numeric priority among auto-configurations**.

**Core rule:** the **smaller** the `order` value, the **higher** the priority—meaning the auto-configuration is applied **earlier** during configuration processing. For example, `@AutoConfigureOrder(-100)` comes before `@AutoConfigureOrder(100)` when no other ordering constraint applies. This priority concerns **bean definition registration**, not constructor execution order or bean instantiation timing.

## 1. What is `@AutoConfigureOrder`?

The annotation lives in the package:

```java
import org.springframework.boot.autoconfigure.AutoConfigureOrder;
```

Declared on an auto-configuration class:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigureOrder;

@AutoConfiguration
@AutoConfigureOrder(-100)
public class HighPriorityAutoConfiguration {
    // Bean definitions, applicable conditions...
}

@AutoConfiguration
@AutoConfigureOrder(100)
public class LowPriorityAutoConfiguration {
    // Bean definitions, applicable conditions...
}
```

The two classes above are **annotation illustrations**; in a real Java project, each `public` class must reside in a file matching its class name. A runnable test example with complete file structure appears in Section 4.

`@AutoConfigureOrder` is the auto-configuration-specific counterpart to Spring Framework's `@Order` mechanism. In Spring Boot 3.x:

- `@AutoConfigureOrder(-100)`: higher priority than `@AutoConfigureOrder(0)` and `@AutoConfigureOrder(100)`.
- `@AutoConfigureOrder(0)`: the annotation's default level; without declaring a custom priority, an auto-configuration does not receive a negative-number advantage.
- `@AutoConfigureOrder(100)`: lower priority than the two configurations above, evaluated later in numeric order.
- You can use `Ordered.HIGHEST_PRECEDENCE` and `Ordered.LOWEST_PRECEDENCE` instead of raw integers, though note that these constants represent the two ends of the priority scale and do not create a dependency constraint between two classes.

The `order` value is **a priority level**, not a line index in a list. You should not infer a stable order between two configurations with the **same value** solely from `@AutoConfigureOrder`, nor rely on dependency declaration order to settle competition.

## 2. Which phase does priority affect?

Spring Boot discovers auto-configurations, determines their application order, and then processes eligible classes. In Spring Boot 3.x, a standalone starter typically publishes candidates in:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line is a **fully qualified class name**, for example:

```text
com.example.starter.PrimaryMessageAutoConfiguration
com.example.starter.FallbackMessageAutoConfiguration
```

The imports file helps Spring Boot **discover** auto-configurations. `@AutoConfigureOrder` helps order **the discovered candidates**. This annotation does not register a class absent from the auto-configuration loading mechanism, and it is not a way to order ordinary `@Configuration` classes in an application.

Distinguish three phases:

1. **Discovering and ordering auto-configurations:** Boot collects and sorts them by metadata, including `@AutoConfigureOrder` levels and `before/after` relationships if present.
2. **Processing configuration classes, registering bean definitions:** Spring evaluates conditions and registers bean definitions. `@ConditionalOnBean` or `@ConditionalOnMissingBean` can be affected by **which bean definitions have been processed up to that point**.
3. **Creating bean instances:** The container instantiates objects when needed, considering dependencies, `@DependsOn`, lazy initialization, and context lifecycle. The order in step 1 **does not guarantee** bean constructors run in the same sequence.

For example: A has `@AutoConfigureOrder(-100)` and B has `@AutoConfigureOrder(100)`. A may be processed before B, yet if a bean declared by A **depends on a bean declared by B**, Spring can still instantiate B's bean first to satisfy the dependency. Do not use `@AutoConfigureOrder` in place of `@DependsOn` or dependency injection.

## 3. Why can order change which default bean is chosen?

Suppose two auto-configurations both want to provide an implementation of the same `MessageService` interface:

```java
// Abbreviated snippet of configuration A:
@Bean
@ConditionalOnMissingBean(MessageService.class)
MessageService primaryMessageService() {
    return () -> "primary";
}

// Abbreviated snippet of configuration B:
@Bean
@ConditionalOnMissingBean(MessageService.class)
MessageService fallbackMessageService() {
    return () -> "fallback";
}
```

Assume there is no user-defined `MessageService` bean, A has order `-100`, and B has order `100`:

| Step | Processed state | Outcome |
| --- | --- | --- |
| Before A | No `MessageService` bean definition yet | A passes the "missing bean" check. |
| Processing A | A registers `primaryMessageService` | A's definition now exists. |
| Processing B | B sees a bean of the same type already exists | B's `@ConditionalOnMissingBean(MessageService.class)` does not match; B backs off. |
| After processing | Only A's default exists | Bean instance is initialized when the container needs it. |

If A is disabled by another condition (`@ConditionalOnProperty`, `@ConditionalOnClass`…), B can become the default. If the application **declares its own** `MessageService`, both auto-configurations normally *back off* when using the proper missing-bean condition. `@AutoConfigureOrder` must not "override the user's choice of bean."

Two limitations to understand:

- **Priority alone does not exclude beans.** If both A and B create `MessageService` without checking `@ConditionalOnMissingBean`, both beans can exist. When injecting strictly by type, Spring may fail to choose a single bean unless a disambiguation mechanism such as `@Qualifier` or `@Primary` is used.
- **Conditions check the declared type/name.** If A checks for missing `ServiceA.class` while B checks for missing `ServiceB.class`, both conditions may match even though both implementations implement the same interface. To guarantee a single shared default, check **the same contract type**.

## 4. Java 17 / Spring Boot 3.x example: priority, fallback, and overriding

This example has two auto-configurations competing for one `MessageService` bean. The primary class has `@AutoConfigureOrder(-100)`, and the fallback class has `@AutoConfigureOrder(100)`. `@ConditionalOnProperty` is added to demonstrate that if the primary configuration is disabled, the fallback configuration is selected. A third test shows that an application-provided bean takes precedence over both defaults.

### 4.1. Create the Maven project

```text
auto-order-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── AutoConfigureOrderTest.java
```

Content of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>auto-order-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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

### 4.2. Complete test file

Create `src/test/java/demo/AutoConfigureOrderTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.AutoConfigureOrder;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigureOrderTest {

    interface MessageService {
        String source();
    }

    @AutoConfiguration
    @AutoConfigureOrder(-100)
    @ConditionalOnProperty(
            prefix = "demo.primary",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    static class PrimaryMessageAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(MessageService.class)
        MessageService primaryMessageService() {
            return () -> "primary";
        }
    }

    @AutoConfiguration
    @AutoConfigureOrder(100)
    static class FallbackMessageAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(MessageService.class)
        MessageService fallbackMessageService() {
            return () -> "fallback";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfiguration {

        @Bean
        MessageService userMessageService() {
            return () -> "user";
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            FallbackMessageAutoConfiguration.class,
                            PrimaryMessageAutoConfiguration.class
                    ));

    @Test
    void smallerOrderValueWinsWhenBothAreEligible() {
        runner.run(context -> {
            assertThat(context.getBeansOfType(MessageService.class))
                    .containsOnlyKeys("primaryMessageService");

            assertThat(context.getBean(MessageService.class).source())
                    .isEqualTo("primary");
        });
    }

    @Test
    void fallbackWinsWhenPrimaryIsDisabled() {
        runner.withPropertyValues("demo.primary.enabled=false")
                .run(context -> {
                    assertThat(context.getBeansOfType(MessageService.class))
                            .containsOnlyKeys("fallbackMessageService");

                    assertThat(context.getBean(MessageService.class).source())
                            .isEqualTo("fallback");
                });
    }

    @Test
    void userProvidedBeanOverridesBothDefaults() {
        runner.withUserConfiguration(UserConfiguration.class)
                .run(context -> {
                    assertThat(context.getBeansOfType(MessageService.class))
                            .containsOnlyKeys("userMessageService");

                    assertThat(context.getBean(MessageService.class).source())
                            .isEqualTo("user");
                });
    }
}
```

Run from the `auto-order-demo` directory with **JDK 17+** and Maven:

```bash
mvn test
```

**Expected result:** three tests are run and all pass. Maven Surefire typically summarizes as `Tests run: 3, Failures: 0, Errors: 0, Skipped: 0`, while log lines depend on the Maven version and environment. The test code does not call `System.out.println`, so no domain stdout is assumed.

| Test | Configuration value | `MessageService` bean after loading context |
| --- | --- | --- |
| `smallerOrderValueWinsWhenBothAreEligible` | `demo.primary.enabled` unset | `primaryMessageService`, returns `"primary"` |
| `fallbackWinsWhenPrimaryIsDisabled` | `demo.primary.enabled=false` | `fallbackMessageService`, returns `"fallback"` |
| `userProvidedBeanOverridesBothDefaults` | With `UserConfiguration` | `userMessageService`, returns `"user"` |

**Important explanation:**

1. `AutoConfigurations.of(Fallback…, Primary…)` intentionally passes the **fallback class before the primary class**. When used as an auto-configuration source, Boot still applies `@AutoConfigureOrder` metadata to reorder priority. Argument order in that call is not an API for picking the winner.
2. When no user bean exists and primary's property condition matches, `-100` is applied earlier than `100`. The `primaryMessageService` bean definition is registered; when fallback is reached, `@ConditionalOnMissingBean` sees `MessageService` already exists and skips registering fallback.
3. When the property is `false`, the primary configuration class is not applied; fallback creates the default bean.
4. `withUserConfiguration(UserConfiguration.class)` registers the application-defined bean into the context before auto-configurations. Both primary and fallback yield to `userMessageService`.
5. The two auto-configuration classes in this lesson live **inside the test file** and are loaded directly via `AutoConfigurations.of`, so no `AutoConfiguration.imports` file is needed for the test suite. When packaging a **real starter**, each auto-configuration is usually a top-level class with its fully qualified name in the jar's imports file.

### 4.3. What happens if you change the priority?

Try changing:

```java
// Snippet for practice, not a standalone Java file:
@AutoConfigureOrder(200)  // Primary now has a larger number than Fallback (100).
```

After this change, when both are eligible and no other ordering constraint exists, fallback is applied first, registers its bean, and causes primary to back off. The first test expecting `primaryMessageService` will **fail**, so its assertion would need to change to `fallbackMessageService`/`"fallback"` if the new behavior is genuinely intended. This exercise illustrates the effect of changing order; it is not advice to alter production configuration arbitrarily.

## 5. Comparing `@AutoConfigureOrder` with other ordering tools

| Tool | Meaning | When to use |
| --- | --- | --- |
| `@AutoConfigureOrder(n)` | Sets **general** priority for an auto-configuration; smaller numbers run earlier. | Independent auto-configurations wanting a general priority level without referencing each other directly. |
| `@AutoConfiguration(before = Other.class)` | Expresses that A must be applied **before a specific auto-configuration**. | When there is a concrete relationship with another configuration. |
| `@AutoConfiguration(after = Other.class)` | Expresses that A must be applied **after a specific auto-configuration**. | When A needs bean definitions registered by Other before evaluating conditions. |
| `@AutoConfigureBefore` / `@AutoConfigureAfter` | Standalone annotations corresponding to `before`/`after`; also support referencing by name. | Same use cases as the two attributes above, or when writing in standalone-annotation style. |
| `@Order` / `Ordered` | Spring's general ordering mechanism, e.g., sorting injected lists of components per respective rules. | Do not use as a priority contract between **auto-configurations**. |
| `@DependsOn` | Requires a dependent bean to be initialized before another bean. | When controlling **instance initialization** relationships, not `@ConditionalOnMissingBean` evaluation order. |
| `@Primary` / `@Qualifier` | Disambiguates which bean is chosen for injection when multiple beans of the same type exist. | When intentionally allowing multiple beans to coexist. |

**When a specific relationship exists, prefer expressing it with `before/after`.** For example, if an auto-configuration needs to inspect bean definitions registered by `WebMvcAutoConfiguration`, declaring that relationship directly is clearer than guessing an integer to win a spot. Avoid combining numeric metadata and `before/after` with conflicting intentions: this makes logic hard to read and maintain.

Direct relationship example:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration(after = BaseClientAutoConfiguration.class)
public class ClientMetricsAutoConfiguration {
    // Only checks/registers beans after BaseClientAutoConfiguration.
}
```

This is an **excerpt**; `BaseClientAutoConfiguration` must be an existing class referenceable in the project. If the library does not want a direct compile-time dependency on another class, `afterName` can specify the fully qualified class name as a string. Distinguish that syntax from the numeric value of `@AutoConfigureOrder`.

## 6. How to apply in a real starter

A sound design workflow:

1. **Identify activation conditions:** classpath, property, web stack, or bean presence/absence. `@AutoConfigureOrder` does not replace any condition.
2. **Assess whether concrete dependencies exist:** if A needs B processed first, use `@AutoConfiguration(after = B.class)` or `afterName`.
3. **Assign priority when needed:** if auto-configurations do not directly depend on each other yet need a general priority order, add `@AutoConfigureOrder`. Document clearly why the number was chosen so maintainers do not misread its intent.
4. **Declare back-off conditions:** when providing a default bean, use `@ConditionalOnMissingBean` with the appropriate type; avoid creating two competing defaults with mismatched criteria.
5. **Register via the proper mechanism:** put auto-configuration classes into `AutoConfiguration.imports`; do not rely on `@ComponentScan` to load them.
6. **Test all paths:** with and without user beans; higher-priority configuration eligible/ineligible; additional starters on the classpath; Spring Boot upgrades.

Do not rely on line position in `AutoConfiguration.imports`, Maven `<dependency>` declaration order, or class argument order elsewhere as a priority contract. Those do not express the desired relationship the way auto-configuration annotations do.

If configurations belong to **two libraries not controlled by the same team**, adding `@AutoConfigureOrder` to your library is only part of the picture. The other library might declare `before/after` or different conditions. Test the **actual container outcome** with the supported dependency combinations instead of assuming "my number is smallest so I always win in every app."

## 7. Practical troubleshooting

### 7.1. Auto-configuration does not appear

- Check the starter's `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` file, verify exact class names, and confirm the dependency is actually on the classpath.
- Check whether the auto-configuration is excluded by `@SpringBootApplication(exclude = …)` or `spring.autoconfigure.exclude`.
- Inspect class-level conditions: `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnWebApplication`… The configuration might not apply even when ordered.
- Run the app with `--debug` and read the **Condition Evaluation Report**, or check Actuator `/actuator/conditions` (if enabled and accessible), to see why conditions matched or did not match. In unit tests, use `ApplicationContextRunner` as shown in the example.

### 7.2. A default bean "wins" unexpectedly

- Do both use **the same type** in `@ConditionalOnMissingBean`? Distinguish interface types from implementation types and **name-based** conditions.
- Did the user declare a bean before auto-configurations? If so, the expected behavior is usually for both defaults to back off.
- Is there an `@AutoConfiguration(before/after)` or `@AutoConfigureBefore/After` in either library? Are there additional conditions causing the expected configuration to be skipped?
- Is the class loaded as an **auto-configuration**, or merely as a `@Configuration` picked up by component scan / manual import? `@AutoConfigureOrder` is designed for the auto-configuration loading path.
- Try using `ApplicationContextRunner` to isolate the competing classes and verify which bean is registered.

### 7.3. Beans initialize in a different order despite right order numbers

This is not necessarily a bug. `@AutoConfigureOrder` governs **configuration application** order, whereas object instantiation depends on constructor injection, `@DependsOn`, `@Lazy`, requests from other beans, and Spring's lifecycle. If instance B must be ready when A initializes, express the dependency via constructor or an appropriate lifecycle relationship.

### 7.4. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking a larger number means higher priority | Expected configuration may be processed later | Remember **smaller number → earlier**. |
| Using `@Order` on a bean instead of `@AutoConfigureOrder` | Fails to order auto-configurations as intended | Place `@AutoConfigureOrder` on the auto-configuration class. |
| Using `@AutoConfigureOrder` to "override" custom beans | Risks breaking back-off design | Use `@ConditionalOnMissingBean` properly and test user-supplied beans. |
| Trying to control **instance creation** order with order numbers | Constructors do not run in the imagined sequence | Use dependency injection/`@DependsOn` if initialization dependencies exist. |
| Multiple classes sharing `@AutoConfigureOrder(0)` and assuming imports guarantees order | Behavior easily depends on structure or version changes | Declare `before/after` when order is a real requirement. |
| Auto-config class isn't loaded yet only checking order | The annotation never gets a chance to apply | Check imports file, exclusions, conditions, and the report. |
| Two beans of the same type without back-off | Can cause `NoUniqueBeanDefinitionException` on injection | Design missing-bean conditions or resolve via `@Primary`/`@Qualifier` as intended. |

## 8. Self-check questions

**Question 1:** A uses `@AutoConfigureOrder(-20)`, B uses `@AutoConfigureOrder(20)`; both are valid auto-configurations with no other ordering constraints. Which gets applied earlier?  
**Answer:** A, because `-20 < 20`.

**Question 2:** Both A and B have `@ConditionalOnMissingBean(PaymentService.class)`, with no user bean. A is applied before B and successfully registers a `PaymentService`. Will B still register its default?  
**Answer:** Normally no, because when B is evaluated, a bean definition of the same type already exists.

**Question 3:** If A is prioritized before B, can you conclude that beans defined by A are always **initialized before** beans defined by B?  
**Answer:** No. That is a separate phase governed by dependencies and bean lifecycle.

**Question 4:** To ensure A is always applied **specifically after B** because A checks for B's bean, what should you choose?  
**Answer:** `@AutoConfiguration(after = B.class)` (or `@AutoConfigureAfter(B.class)`) expresses the relationship more clearly than a general order number.

**Question 5:** An application already declared a matching `PaymentService`. A has `@AutoConfigureOrder(-1000)` and `@ConditionalOnMissingBean(PaymentService.class)`. Does A create its default bean to "beat" the application's bean?  
**Answer:** No. Application beans are normally present before auto-configurations; the missing-bean condition does not match and A backs off.

**Question 6:** Two auto-configurations both have order `0` with no `before/after` relationship. Can you rely on the order of the two lines in imports as a stable API?  
**Answer:** You should not. If order matters, express the requirement with explicit metadata and add tests.

## Remember

`@AutoConfigureOrder` provides **numeric priority among auto-configurations**, where **smaller values are applied earlier**. That order can determine which bean definition appears first, since bean conditions are evaluated against what Spring has already processed. It **does not exclude beans on its own**, **does not replace conditions**, **does not dictate instance initialization timing**, and **does not replace `before/after` when concrete dependencies exist**. In real starters, use the proper auto-configuration loading mechanism, design back-off cleanly, and test across multiple configuration combinations.

### Official reference documentation

- Spring Boot Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot API — `@AutoConfigureOrder`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfigureOrder.html
- Spring Boot API — `@AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot API — `@ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html