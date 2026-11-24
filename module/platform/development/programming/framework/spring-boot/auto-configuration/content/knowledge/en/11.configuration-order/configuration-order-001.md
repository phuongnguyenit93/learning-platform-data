# Why Must Configuration Creating a Foundation Bean Be Processed Before Configuration Using That Bean?

> **Spring Boot Auto Configuration → Configuration Order.** This lesson distinguishes the order of **processing auto-configurations/registering bean definitions** from the order of **initializing bean instances**, explains when depending on a foundation bean makes configuration order matter, and guides how to declare, test, and diagnose ordering with Spring Boot 3.x / Java 17+.

## 1. The problem: one foundation bean serving multiple features

Suppose an integration library provides:

- **CoreAutoConfiguration**: creates the foundation bean `CoreClient` (managing connections, encoders, shared configuration, or an infrastructure service).
- **FeatureAutoConfiguration**: registers the `FeatureService` bean only when `CoreClient` is already present in the context.
- **Application**: can enable/disable the core part, supply its own bean, or want only specific features.

Dependency model:

~~~text
          CoreAutoConfiguration
                |
                v
       bean definition: CoreClient
                |
                v  (@ConditionalOnBean)
          FeatureAutoConfiguration
                |
                v
       bean definition: FeatureService
                |
                v
       FeatureService uses CoreClient
~~~

A consuming configuration may declare a condition:

~~~java
@AutoConfiguration
@ConditionalOnBean(CoreClient.class)
public class FeatureAutoConfiguration {
    // @Bean FeatureService...
}
~~~

`@ConditionalOnBean` **does not wait for all configurations to finish being evaluated** before deciding. This condition relies on **the bean definitions that Spring has already processed up to the moment of evaluation**. If the configuration creating `CoreClient` has not been processed yet, the condition on `FeatureAutoConfiguration` may fail to match; in that case, the feature bean is skipped even though the foundation configuration class will be processed later.

Therefore, when an auto-configuration **uses a condition on the existence of a bean provided by another configuration**, you need to order them so that **the configuration providing the foundation bean is processed first**. This ensures the condition sees all the definitions it depends on.

**Crucial point:** not every constructor injection requires forcing auto-configuration order. Spring can usually create a foundation bean before a bean that uses it **based on the dependency graph**, even when the registration order of the definitions differs. The specific issue here is **when conditions are evaluated and bean definitions are registered**.

## 2. Two kinds of "order" commonly confused with each other

| Phase | What is Spring Boot/Spring doing? | What does order affect? | Related tools |
| --- | --- | --- | --- |
| **Selecting and ordering auto-configurations** | Finds candidate configurations and orders them to be applied | Decides which auto-configuration is processed first | `@AutoConfiguration(before/after)`, `@AutoConfigureBefore`, `@AutoConfigureAfter`, `@AutoConfigureOrder` |
| **Evaluating conditions and registering bean definitions** | Reads `@Configuration`, `@Bean`, `@Conditional...` metadata and registers valid bean definitions | Conditions such as `@ConditionalOnBean` / `@ConditionalOnMissingBean` see the definitions already processed | Conditional configuration, auto-configuration ordering |
| **Initializing and wiring bean instances** | Spring instantiates objects, resolves constructor arguments, dependencies, callbacks, and lifecycle | A required dependency bean generally must be created before the bean using it | Constructor injection, `@DependsOn`, bean lifecycle |
| **Running application logic** | `ApplicationRunner`, request handlers, scheduled jobs... use ready beans | Determines when features start executing | Lifecycle and runtime logic design |

You can visualize it as:

~~~text
A. READ CONFIGURATION AND REGISTER DEFINITIONS
   CoreAutoConfiguration -> registers CoreClient
   FeatureAutoConfiguration -> checks CoreClient -> registers FeatureService

B. INITIALIZE INSTANCES
   Spring creates CoreClient when FeatureService needs it
   Spring creates FeatureService with CoreClient injected

C. USAGE
   ApplicationRunner or request calls FeatureService
~~~

`@AutoConfiguration(after = CoreAutoConfiguration.class)` affects **A**, not directly forcing the constructor call sequence in **B**. Spring Boot explicitly states that the order in which auto-configurations are applied affects **the order in which bean definitions are defined**; when beans are subsequently instantiated depends on bean dependencies and `@DependsOn`.

## 3. What symptoms occur when the order is wrong?

### 3.1. @ConditionalOnBean: the foundation bean may not be visible yet

If `FeatureAutoConfiguration` is evaluated first:

~~~text
1. FeatureAutoConfiguration is processed.
2. @ConditionalOnBean(CoreClient.class) checks: no CoreClient definition yet.
3. Condition DOES NOT MATCH -> FeatureService is not registered.
4. CoreAutoConfiguration is processed and registers CoreClient.
5. Spring does not automatically go back to register FeatureService just because CoreClient appeared later.
~~~

The result can be that **CoreClient exists while FeatureService does not**. The configuration does not necessarily crash; the feature may simply disappear because its condition was evaluated too early.

If processed according to the proper relationship:

~~~text
1. CoreAutoConfiguration -> registers CoreClient.
2. FeatureAutoConfiguration -> @ConditionalOnBean(CoreClient.class) MATCHES.
3. FeatureAutoConfiguration -> registers FeatureService.
4. When initializing FeatureService, Spring provides CoreClient.
~~~

This is the primary reason for ordering **foundation configuration before configuration using the foundation bean**.

### 3.2. @ConditionalOnMissingBean: a fallback configuration may register by mistake

`@ConditionalOnMissingBean` is also sensitive to evaluation timing. For example, `FallbackAutoConfiguration` only wants to create a default `CoreClient` when no other configuration provides a matching bean:

~~~java
@Bean
@ConditionalOnMissingBean(CoreClient.class)
CoreClient defaultCoreClient() {
    return new CoreClient();
}
~~~

This is an **illustrative snippet**: `CoreClient` must be defined/imported in the corresponding project. If another configuration defines `CoreClient` **after** the condition above has already been evaluated, the default bean may get registered even though the intent was to yield to a specialized bean. Depending on bean names, types, and injection style, this can cause multiple beans of the same type or selection of the wrong bean.

A better approach: identify **who the primary bean provider is** and who the **fallback** is, then order the auto-configurations so the fallback condition observes the beans that should take precedence before it. In a starter, `@ConditionalOnMissingBean` also lets you yield to user-defined application beans: Spring Boot processes user-supplied configuration before auto-configurations.

**Important limitation:** a configuration ordered earlier **is not guaranteed to create a bean**. It can still be blocked by `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, or execution errors. Ordering only fixes the **evaluation/registration** relationship; it does not satisfy a missing condition on its own.

### 3.3. Constructor injection alone is different

Suppose both bean definitions already exist in the context, with no `@ConditionalOnBean` on the consuming class:

~~~java
@Bean
FeatureService featureService(CoreClient coreClient) {
    return new FeatureService(coreClient);
}
~~~

When creating `FeatureService`, Spring knows it needs `CoreClient` because it is a parameter of the `@Bean` method. It will resolve the dependency, create `CoreClient` first if needed, and only then create `FeatureService`. It is **not mandatory** to force auto-configuration order merely so that "`CoreClient`'s constructor runs first."

This is the difference between:
- **Whether a bean definition exists for a condition to see**; and
- **Which bean instance is created before another instance needs it**.

## 4. Declaring proper order in Spring Boot

With Spring Boot 2.7+/3.x, prefer `@AutoConfiguration` with `before` / `after` attributes.

### 4.1. Consuming configuration placed after foundation configuration

~~~java
@AutoConfiguration(after = CoreAutoConfiguration.class)
public class FeatureAutoConfiguration {
    // Bean depending on CoreClient
}
~~~

Meaning: **If both auto-configurations participate in processing**, Boot orders `FeatureAutoConfiguration` after `CoreAutoConfiguration`. This expresses the relationship "Feature requires Core to have already been declared."

Equivalent form using the dedicated annotation:

~~~java
@AutoConfiguration
@AutoConfigureAfter(CoreAutoConfiguration.class)
public class FeatureAutoConfiguration {
}
~~~

This is an **illustrative snippet**; you must import `AutoConfiguration` / `AutoConfigureAfter` and have the corresponding `CoreAutoConfiguration` to compile.

### 4.2. Declaring from the foundation configuration side

~~~java
@AutoConfiguration(before = FeatureAutoConfiguration.class)
public class CoreAutoConfiguration {
}
~~~

Or:

~~~java
@AutoConfiguration
@AutoConfigureBefore(FeatureAutoConfiguration.class)
public class CoreAutoConfiguration {
}
~~~

Both state the same relationship from opposite directions. **Do not declare both `before` and `after` redundantly** if one relation is already clear; keeping a single source of expression avoids redundant constraints or ordering cycles.

### 4.3. Referencing a class you do not want a direct dependency on

You can use `beforeName` / `afterName` with the fully qualified class name:

~~~java
@AutoConfiguration(afterName = "com.vendor.core.CoreAutoConfiguration")
public class FeatureAutoConfiguration {
}
~~~

Benefit: no direct compile-time `Class` reference to an optional auto-configuration is required. The name must be exact, including package. For nested classes, the JVM naming convention uses the `$` character.

### 4.4. How do @AutoConfigureOrder and @Order differ?

- `@AutoConfigureOrder` provides a general ordering for **auto-configurations**, useful when two configurations have no direct reference to each other yet still need relative priority.
- `@Order` is commonly used to order multiple beans of the same type when injecting a collection, processors, aspects, etc., depending on context; it **does not replace** `before/after` directives for ordering auto-configurations.
- When there is an explicit relationship "Feature needs the foundation bean provided by Core," `@AutoConfiguration(after = CoreAutoConfiguration.class)` is far clearer than an obscure order number.

Neither line order in `AutoConfiguration.imports` nor source file naming order should serve as the mechanism controlling foundation–dependent relationships. Declare constraints explicitly.

### 4.5. @DependsOn solves a different problem

~~~java
@Bean
@DependsOn("coreClient")
FeatureService featureService(CoreClient coreClient) {
    return new FeatureService(coreClient);
}
~~~

This is an **illustrative snippet** requiring appropriate imports and application types. `@DependsOn("coreClient")` requires the bean named `coreClient` to be **initialized before** `featureService`; however:
- It does not force `CoreAutoConfiguration` to be processed before a `@ConditionalOnBean` is evaluated.
- It does not register the `coreClient` bean if that bean does not exist.
- With direct constructor/method injection of `CoreClient` as above, Spring already knows the dependency from the parameter; `@DependsOn` is usually redundant.

Use `@DependsOn` only when there is genuinely an **initialization** relationship not expressed through parameters, such as needing an infrastructure bean initialized before a bean with side effects. Do not use it to fix a bean condition evaluated too early.

## 5. Runnable project: proving definition order without confusing it with instance order

This lab uses Java 17, Maven, and Spring Boot 3.3.13. It has two auto-configurations independent of component scanning. They are **listed in reverse order** in the imports file, yet the `after` constraint guarantees the proper processing relationship.

### 5.1. Project structure

~~~text
config-order-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── app/
        │       │   └── OrderDemoApplication.java
        │       └── autoconfigure/
        │           ├── CoreAutoConfiguration.java
        │           └── FeatureAutoConfiguration.java
        └── resources/
            └── META-INF/
                └── spring/
                    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Place the application class in `demo.app` and the two auto-configurations in `demo.autoconfigure` so the auto-configurations are loaded **via imports**, rather than accidentally appearing due to the application's component scan.

### 5.2. File pom.xml

~~~xml
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
    <groupId>demo</groupId>
    <artifactId>config-order-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
~~~

### 5.3. File src/main/java/demo/autoconfigure/CoreAutoConfiguration.java

~~~java
package demo.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.core",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class CoreAutoConfiguration {

    @Bean
    public CoreClient coreClient() {
        return new CoreClient("core-ready");
    }

    public record CoreClient(String id) {}
}
~~~

`CoreClient` is the foundation bean type. Here it is a Java 17 `record` for brevity. `demo.core.enabled` has an **enabled-by-default** policy; set it to `false` to skip the entire `CoreAutoConfiguration`. The example performs no real network connections.

### 5.4. File src/main/java/demo/autoconfigure/FeatureAutoConfiguration.java

~~~java
package demo.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = CoreAutoConfiguration.class)
@ConditionalOnBean(CoreAutoConfiguration.CoreClient.class)
public class FeatureAutoConfiguration {

    @Bean
    public FeatureService featureService(
            CoreAutoConfiguration.CoreClient coreClient) {
        return new FeatureService(coreClient);
    }

    public record FeatureService(
            CoreAutoConfiguration.CoreClient coreClient) {

        public String message() {
            return "feature uses " + coreClient.id();
        }
    }
}
~~~

Two distinct ideas appear together:
1. `after = CoreAutoConfiguration.class` ensures the foundation configuration is processed **before** Feature's condition is evaluated.
2. The `CoreClient` parameter in `featureService(...)` ensures that when creating the `FeatureService` instance, Spring can resolve the foundation bean.

With `@ConditionalOnBean`, the condition checks **known bean definitions**, without calling `new CoreClient(...)`. Thus `after` solves the definition registration problem; method injection solves the instance problem.

### 5.5. File src/main/java/demo/app/OrderDemoApplication.java

~~~java
package demo.app;

import demo.autoconfigure.FeatureAutoConfiguration.FeatureService;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ApplicationContext context) {
        return args -> {
            boolean corePresent = context.containsBean("coreClient");
            boolean featurePresent = context.containsBean("featureService");

            System.out.println("coreBean=" + corePresent);
            System.out.println("featureBean=" + featurePresent);

            if (featurePresent) {
                FeatureService service = context.getBean(FeatureService.class);
                System.out.println(service.message());
            }
        };
    }
}
~~~

From package `demo.app`, `@SpringBootApplication` does not component-scan the sibling package `demo.autoconfigure`. The two auto-configurations must be picked up by Boot from the imports file, so the lab demonstrates the exact mechanism being studied.

### 5.6. Auto-configuration registration file

Create the exact path:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Content:

~~~text
demo.autoconfigure.FeatureAutoConfiguration
demo.autoconfigure.CoreAutoConfiguration
~~~

Intentionally place **Feature before Core in the file** to illustrate: the intended relationship is determined by `@AutoConfiguration(after = CoreAutoConfiguration.class)`, **not by line order**. In a real starter, each auto-configuration must be listed by a valid fully qualified class name.

### 5.7. Packaging and running

In the `config-order-demo` directory, with JDK 17+ and Maven:

~~~bash
mvn -q -DskipTests package
java -jar target/config-order-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Three lines printed by the program:

~~~text
coreBean=true
featureBean=true
feature uses core-ready
~~~

Conclusion: `CoreAutoConfiguration` is present and processed early enough, so `FeatureAutoConfiguration`'s condition matches; the feature bean is registered and can subsequently receive the `CoreClient` dependency.

### 5.8. Turning off the foundation configuration completely: correct order still cannot create an absent bean

Run again:

~~~bash
java -jar target/config-order-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.core.enabled=false
~~~

Two lines printed by the program:

~~~text
coreBean=false
featureBean=false
~~~

Because `@ConditionalOnProperty` does not match, the foundation configuration supplies no bean. `FeatureAutoConfiguration` is ordered after it properly, yet `@ConditionalOnBean(CoreClient.class)` still **does not match**. That is the right outcome: **ordering does not replace a required condition**.

If started with `--debug` and normal logging enabled, you can read the *Condition Evaluation Report* to inspect why each auto-configuration matched or did not match.

## 6. Testing order with ApplicationContextRunner

Running the application once is not enough to protect a starter against future changes. You can test both when the foundation configuration is enabled and when it is disabled.

Add to the `<dependencies>` section of `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create the file:

~~~text
src/test/java/demo/app/OrderAutoConfigurationTest.java
~~~

Content:

~~~java
package demo.app;

import demo.autoconfigure.CoreAutoConfiguration;
import demo.autoconfigure.FeatureAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class OrderAutoConfigurationTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    FeatureAutoConfiguration.class,
                    CoreAutoConfiguration.class
            ));

    @Test
    void featureIsAvailableWhenCoreIsAvailable() {
        runner.run(context -> {
            assertThat(context).hasBean("coreClient");
            assertThat(context).hasBean("featureService");
            var feature = context.getBean(
                    FeatureAutoConfiguration.FeatureService.class
            );
            assertThat(feature.message()).isEqualTo("feature uses core-ready");
        });
    }

    @Test
    void featureIsSkippedWhenCoreIsDisabled() {
        runner.withPropertyValues("demo.core.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean("coreClient");
                    assertThat(context).doesNotHaveBean("featureService");
                });
    }
}
~~~

The order passed into `AutoConfigurations.of(...)` intentionally lists Feature before Core; the `after` constraint still dictates the processing relationship. Run:

~~~bash
mvn test
~~~

Expected: **2 tests PASS**. The tests verify both the proper consequence of ordering and the case where the foundation condition is genuinely disabled. When writing a complex starter, expand tests to cover user-defined beans, fallback mode, missing classpath dependencies, and profile changes if those are part of the starter's contract.

## 7. Distinguishing the tools through practical scenarios

| Need | Mechanism to use | Why |
| --- | --- | --- |
| Feature auto-configuration should match only if foundation auto-configuration has registered its bean | `@AutoConfiguration(after = CoreAutoConfiguration.class)` | Orders configuration application before `@ConditionalOnBean` is checked |
| Foundation configuration must precede a specific configuration | `@AutoConfiguration(before = FeatureAutoConfiguration.class)` | Expresses the same relationship from the foundation side |
| Configuration should not depend directly on an optional auto-config class | `afterName` / `beforeName` | Expresses the relationship by fully qualified class name |
| Choosing relative order for independent auto-configs with no direct link | `@AutoConfigureOrder` | Uses auto-configuration ordering |
| Bean B needs object A as a parameter to be constructed | Constructor injection or `@Bean` parameter | Dependency graph instructs Spring to create A when B needs it |
| Bean B needs bean A initialized earlier even without injecting A | `@DependsOn("a")` | Controls **instance initialization** order |
| Wanting fixed order when injecting multiple strategies into a list | `@Order` / `Ordered` depending on context | Orders selected elements; does not replace auto-config constraints |
| Wanting to create a default bean only if the user has not provided one | `@ConditionalOnMissingBean` | Registers fallback based on already processed bean definitions |
| Wanting to activate a feature only when a library is on the classpath | `@ConditionalOnClass` | Checks classpath; does not resolve order or create dependencies |

**Design rule:** choose the right layer to order. Auto-config ordering ensures **definitions/conditions see each other**; dependency injection and `@DependsOn` control **when objects are created**.

## 8. Unmatched conditions and runtime errors: reading the signs

### Case A — Core exists but Feature is absent

- **Symptom:** `CoreClient` is in the context; `FeatureService` is not.
- **Investigation:** Does `FeatureAutoConfiguration`'s condition report show `@ConditionalOnBean` did not match? Is the Feature auto-configuration actually imported?
- **Possible causes:** Feature was evaluated before Core registered its definition; another condition blocked it; wrong bean name/type.
- **Evidence-based fix:** If processing order is the cause, add `@AutoConfiguration(after=CoreAutoConfiguration.class)` or `@AutoConfigureAfter`, then re-test both states. Do not add `@DependsOn` to fix a skipped condition.

### Case B — Core does not exist, Feature does not exist

- **Symptom:** Both beans are absent.
- **Investigation:** Is `CoreAutoConfiguration` actually listed in `AutoConfiguration.imports`? Did a classpath, property, or existing-bean condition cause Core to be skipped?
- **Fix:** Clarify the core module's contract and provide the appropriate dependency/property. **Proper ordering cannot create a bean whose foundation configuration was excluded by a condition**.

### Case C — Context throws UnsatisfiedDependencyException

- **Symptom:** A bean requires `CoreClient` unconditionally, but no matching bean exists, causing an error during initialization.
- **Investigation:** Distinguish a **genuinely missing bean definition** from a **definition that exists but failed to instantiate**. Inspect the `Caused by` chain and reasons in the condition report.
- **Fix:** Supply/enable the foundation bean, use conditions to cleanly skip optional functionality, or fix the injection configuration. Auto-config ordering helps only if the problem is **processing order**.

### Case D — Circular dependency

~~~text
ServiceA -> needs ServiceB
ServiceB -> needs ServiceA
~~~

This is a **bean-instance dependency graph** issue. Forcing `@AutoConfiguration(before/after)` or reordering the imports file **will not eliminate a circular dependency**. Split responsibilities, remove the bidirectional relationship, or redesign how they connect. Deferral mechanisms like `@Lazy` should only be considered with a clear rationale, not used to hide a circular design.

### Case E — Two beans of the same type and fallback ambiguity

- **Symptom:** Injecting by type finds multiple candidates, and Spring reports it cannot choose a single bean.
- **Investigation:** Who registered the default bean, who registered the specialized bean, and was `@ConditionalOnMissingBean` evaluated too early?
- **Fix:** Fix the ordering relationship between the auto-configurations, use precise conditions so the fallback yields to the right bean, and use `@Primary`/`@Qualifier` when multiple beans are genuinely intended. Do not arbitrarily pick one bean to mask the source of duplication.

## 9. Diagnosing order with a repeatable workflow

1. **Draw the dependency relationship between configurations**: "Which bean does Feature want; which Core is responsible for registering it; does Feature use `@ConditionalOnBean` or only inject it?"
2. **Inspect the auto-configurations actually imported**: with Spring Boot 3.x, check `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` in the JAR/starter. A misspelled class name or missing file means Boot does not know about that configuration.
3. **Inspect conditions**: try `--debug` for the Condition Evaluation Report; if Actuator is enabled and safely exposed, check `/actuator/conditions`. Look for positive/negative matches of Core and Feature.
4. **Read effective Environment values and classpath**: `@ConditionalOnClass`, `@ConditionalOnProperty`, and `@ConditionalOnMissingBean` can make the foundation bean absent even when its configuration runs first.
5. **Verify `after/before` constraints**: use types if both configurations are present at compile time; use `afterName/beforeName` when name references are needed. Avoid cyclic constraints ("A after B" and "B after A").
6. **Separate error meanings**: no match → possibly definition/order; injection failure → no qualifying bean; cycle → instance graph; runtime method failure → inspect bean logic, do not blame everything on order.
7. **Write verification tests**: use `ApplicationContextRunner` to assert bean presence/absence under clear conditions. Do not rely solely on seeing "started" in logs.

When a bean is not supposed to be created, a negative match may be the **correct behavior**. Diagnosis must start from the module's contract: is Feature optional or required? Should users be allowed to override the foundation bean?

## 10. Common mistakes when designing configuration order

1. **"All beans must initialize in the order configurations are declared."** False: Spring primarily follows the dependency graph when creating instances; auto-config order affects definitions/conditions.
2. **"@DependsOn fixes an unmatched @ConditionalOnBean."** False: `@DependsOn` controls initialization after definitions exist; it does not make an early-evaluated condition match.
3. **"Just put Core on the first line of AutoConfiguration.imports."** Fragile: you need explicit `before/after` relationships, not reliance on file line order.
4. **"@Order and @AutoConfigureOrder are the same way of writing it."** They should not be swapped arbitrarily; their ordering targets differ. When there is a Core–Feature relationship, prefer `@AutoConfiguration(after=...)`.
5. **"If Core is ordered first, Feature is guaranteed to exist."** False: Core can be excluded by `@ConditionalOnProperty` or `@ConditionalOnClass`, or Core's bean can be altered by another condition.
6. **"@ConditionalOnMissingBean always sees beans declared in any later configuration."** False: only definitions already processed affect the condition at evaluation time.
7. **"If constructor injection fails, you just need @AutoConfigureAfter."** Not necessarily: confirm the dependency bean has a definition, wasn't excluded by conditions, doesn't have a mismatched type/qualifier, and can actually be instantiated.
8. **"Circular dependencies can be fixed with configuration ordering."** False: you must fix the runtime graph.
9. **"Same bean name means type conditions will always behave the same."** False: `@ConditionalOnBean` can check by type or name; sufficiently specific types and `@Bean` method return types matter greatly.
10. **"Component scan automatically discovers every @AutoConfiguration class."** For Spring Boot 3.x starters, you must use the standard imports mechanism; library configurations should avoid being accidentally picked up by component scanning as regular configurations.

## 11. Self-check

**Question 1.** Feature has `@ConditionalOnBean(CoreClient.class)`; Core provides `CoreClient` but is evaluated after Feature. Why might Feature fail to appear?  
**Answer:** The condition checks bean definitions already processed up to that point; Core has not registered its definition yet, so Feature may be excluded and will not automatically be re-evaluated.

**Question 2.** Which annotation explicitly states "Feature must be applied after Core"?  
**Answer:** `@AutoConfiguration(after = CoreAutoConfiguration.class)` or `@AutoConfigureAfter(CoreAutoConfiguration.class)` on Feature.

**Question 3.** Feature receives `CoreClient` via constructor but has no `@ConditionalOnBean`. Is it strictly necessary to force auto-configuration order so `CoreClient` is created first?  
**Answer:** Not strictly necessary. Once definitions exist, Spring resolves the dependency and creates the foundation bean before creating the consuming bean.

**Question 4.** What does `@DependsOn("coreClient")` do?  
**Answer:** Requires the `coreClient` bean to be initialized before the bean declaring `@DependsOn`; it does not cause another auto-configuration to register or re-evaluate an excluded condition.

**Question 5.** Core is disabled by `demo.core.enabled=false`. Does adding `after=CoreAutoConfiguration.class` guarantee `FeatureService` will appear?  
**Answer:** No. The order may be right, yet `@ConditionalOnBean` still does not match because `CoreClient` is absent.

**Question 6.** Does a fallback's `@ConditionalOnMissingBean` see a bean declared in an auto-configuration that will only be processed later?  
**Answer:** Not guaranteed. The condition relies on bean definitions already processed, so appropriate ordering must be designed.

## 12. Conclusion and references

**Key takeaway:** In Spring Boot Auto Configuration, "foundation configuration must be processed before configuration using the foundation bean" matters especially when **the consuming configuration checks for the presence or absence of a bean to decide whether to register**. This order ensures conditions are evaluated against the required bean definitions. When it comes time to instantiate objects, Spring uses **dependency injection and lifecycle** to determine instance creation order.

You can remember it in two lines:

~~~text
@AutoConfiguration(after = Core...) -> CONFIGURATION PROCESSING / DEFINITION REGISTRATION order
constructor injection, @DependsOn  -> INSTANCE INITIALIZATION order
~~~

Official documentation:
- [Spring Boot — Creating Your Own Auto-configuration: Ordering Auto-configurations](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.condition-annotations)
- [Spring Boot 3.3.13 — @AutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3.13 — @AutoConfigureBefore Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html)
- [Spring Boot — Bean Conditions and @ConditionalOnBean/@ConditionalOnMissingBean](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Framework — @DependsOn Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/DependsOn.html)