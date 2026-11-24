# before, after, beforeName, and afterName on @AutoConfiguration

## 1. Goal and problem to solve

In a Spring Boot application, multiple auto-configuration classes may participate in registering beans. One class may provide a foundational bean; another may want to register an integration bean **only if that foundational bean has already been declared**. At that point, the processing order of the **auto-configuration classes** becomes an important part of the outcome.

Spring Boot 3.3 provides four attributes directly on `@AutoConfiguration` to express ordering relationships:

- `before`: apply the current auto-configuration **before** one or more auto-configurations referenced by `Class`.
- `after`: apply the current auto-configuration **after** one or more auto-configurations referenced by `Class`.
- `beforeName`: similar to `before`, but referenced by **fully qualified class name** (`String`).
- `afterName`: similar to `after`, but referenced by **fully qualified class name** (`String`).

After this lesson, you should be able to: choose the right attribute; understand why both `Class` and `String` variants exist; recognize the boundary between bean definition registration order and bean creation order; read nested class names using `$` properly; and test whether order-dependent bean conditions produce the expected result.

**Scope:** this lesson covers **auto-configuration** ordering in Spring Boot 3.3.x only; it does not redefine component scanning order, the lifecycle of all beans, or Java method invocation order.

## 2. How does Spring Boot load and order auto-configurations?

For a starter or library providing auto-configurations, eligible classes are listed in the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Example:

```text
com.acme.autoconfigure.CacheAutoConfiguration
com.acme.autoconfigure.MetricsAutoConfiguration
com.acme.autoconfigure.CacheMetricsAutoConfiguration
```

Spring Boot collects candidates from the `AutoConfiguration.imports` files on the classpath, evaluates exclusions/conditions, and applies sorting rules. The `before`/`after` attributes and their two `Name` variants act as **relative ordering hints** for the selected auto-configurations.

**Do not design ordering to depend on line order in `AutoConfiguration.imports`.** The file is for **declaring candidates**, while "which configuration comes before which" should be written explicitly using ordering attributes.

A conceptual sequence:

```text
AutoConfiguration.imports
           |
           v
  Auto-configuration candidate set
           |
           v
  Apply metadata and before/after rules
           |
           v
  Process configurations, register bean definitions
           |
           v
  Initialize beans when context needs them
           ^
           |
  Bean dependencies / @DependsOn take effect here
```

**Mandatory boundary to remember:** Spring Boot documentation states that the order in which auto-configurations are applied only affects **the order in which bean definitions are defined**. The order in which bean instances are subsequently initialized is governed by bean dependencies and `@DependsOn`, and is not guaranteed solely by `before` or `after`.

Why does definition order still matter? `@ConditionalOnBean` and `@ConditionalOnMissingBean` observe the bean definitions **that have been processed up to the moment the condition is evaluated**. When an auto-configuration genuinely depends on another configuration's definitions, explicit ordering helps avoid missing beans.

## 3. Four attributes: comparison table

Assume the class being written is `CurrentAutoConfiguration` and the referenced class is `TargetAutoConfiguration`.

| Attribute on `CurrentAutoConfiguration` | Data type | Meaning when both are candidates | Example |
| --- | --- | --- | --- |
| `before` | `Class<?>[]` | `Current` is applied before `Target` | `@AutoConfiguration(before = TargetAutoConfiguration.class)` |
| `after` | `Class<?>[]` | `Current` is applied after `Target` | `@AutoConfiguration(after = TargetAutoConfiguration.class)` |
| `beforeName` | `String[]` | `Current` is applied before the auto-configuration with that class name | `@AutoConfiguration(beforeName = "com.acme.TargetAutoConfiguration")` |
| `afterName` | `String[]` | `Current` is applied after the auto-configuration with that class name | `@AutoConfiguration(afterName = "com.acme.TargetAutoConfiguration")` |

All default to an empty array `{}`; omitting an attribute means adding no corresponding constraint. Each attribute accepts **multiple elements**:

```java
@AutoConfiguration(
    after = {CoreAutoConfiguration.class, StorageAutoConfiguration.class},
    beforeName = {"com.acme.optional.ReportingAutoConfiguration"}
)
public class IntegrationAutoConfiguration {
    // Bean definitions ...
}
```

This is an **illustrative snippet**; the classes `CoreAutoConfiguration`, `StorageAutoConfiguration`, and `IntegrationAutoConfiguration` are assumed to exist. When the target classes are also selected, `IntegrationAutoConfiguration` must come after the first two, while coming before `ReportingAutoConfiguration`. If a referenced class **is not a candidate being applied**, declaring an ordering relationship does not automatically add or activate it.

In Spring Boot 3.3, the four attributes are **aliases** for the dedicated annotations:

- `before` ↔ `@AutoConfigureBefore(value = ...)`.
- `beforeName` ↔ `@AutoConfigureBefore(name = ...)`.
- `after` ↔ `@AutoConfigureAfter(value = ...)`.
- `afterName` ↔ `@AutoConfigureAfter(name = ...)`.

In new code using `@AutoConfiguration`, declaring one of the four attributes directly is usually clearer; there is no need to repeat both the attribute and the dedicated annotation to express the same relationship.

### 3.1. Understanding `before`

```java
@AutoConfiguration(before = SearchClientAutoConfiguration.class)
public class SearchTransportAutoConfiguration {
    // Declares transport used for search client.
}
```

Meaning: if `SearchClientAutoConfiguration` is selected, process `SearchTransportAutoConfiguration` before it. This is an "**I come before the target class**" relationship, not a statement that the target class is excluded or that the transport bean is guaranteed to be instantiated first.

### 3.2. Understanding `after`

```java
@AutoConfiguration(after = SearchTransportAutoConfiguration.class)
public class SearchClientAutoConfiguration {
    // Declares search client depending on transport.
}
```

Meaning: if `SearchTransportAutoConfiguration` is selected, process `SearchClientAutoConfiguration` after it. You can choose to declare `before` on the provider side or `after` on the consumer side depending on which side knows the dependency best; in most cases, **a single explicit relationship is enough**.

**Do not interpret `after` as `@DependsOn`.** Nor does it mean Spring Boot will wait for an active network connection or wait until the target configuration's beans have finished initializing.

## 4. Why do `beforeName` and `afterName` exist?

These two attributes express **the same kind of ordering relationship**, but use `String` class names instead of `Class` literals.

```java
@AutoConfiguration(
    afterName = "org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration"
)
public class MyMvcIntegrationAutoConfiguration {
    // MVC integration is registered after the corresponding auto-configuration.
}
```

`afterName` fits when your code wants to reference an auto-configuration from an optional library or avoid creating a direct **compile-time** coupling to the target class. It is also useful when two starters are developed by different teams, or when referencing a class name from a dependency that may not exist in every dependency combination.

**The name must be a fully qualified Java class name**, not a bean name, package name, Maven module name, or file name. Examples:

- Correct for a top-level class: `"com.acme.search.SearchAutoConfiguration"`.
- Correct for a nested class: `"com.acme.search.SearchModule$TransportAutoConfiguration"`.
- Wrong when referencing a nested class: `"com.acme.search.SearchModule.TransportAutoConfiguration"`.
- Wrong if writing only a bean name: `"searchClient"`.

For nested classes, the `$` character is the binary name convention required in string references and in `AutoConfiguration.imports`.

### 4.1. When to use Class, when to use String name?

- **Use `before` / `after`** when your code directly knows the target auto-configuration class and can reference it at compile time. IDE tooling makes navigation easy and checks names during refactoring.
- **Use `beforeName` / `afterName`** when you want to express a relationship with an optional auto-configuration without referencing the class directly in source code. You must verify yourself that the string still matches the real Java name after refactoring.
- **If the target class is absent** or not imported as an auto-configuration, the ordering relationship with it has no target to apply against. There is no "find and load dependency" mechanism triggered by these four attributes.

**An important limitation:** `afterName` does not replace `@ConditionalOnClass`. If an integration feature requires classes from another library, add appropriate class conditions and isolate beans/methods that reference optional classes. Ordering and library-presence checking are **two distinct responsibilities**.

Example for an optional integration:

```java
@AutoConfiguration(
    afterName = "org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration"
)
@ConditionalOnClass(name = "org.springframework.web.servlet.DispatcherServlet")
public class MyOptionalMvcAutoConfiguration {
    // MVC beans belonging to this configuration ...
}
```

This is an **illustrative snippet**; a real project must have the corresponding dependencies and bean code. `afterName` only orders relatively when MVC auto-configuration is actually applied; `@ConditionalOnClass` is what checks for the required class.

## 5. Ordering relationships are relative, not a global execution schedule

You can picture the four attributes as declaring edges in a directed graph:

```text
@AutoConfiguration(before = B.class) on A:     A ---> B

@AutoConfiguration(after = B.class) on C:      B ---> C

When all three are applied:                    A ---> B ---> C
```

This is not a command to "run A, finish all beans of A, then run B." Auto-configuration processing order must honor the declared relationships, but among classes with **no direct relationship**, multiple valid orders may exist.

Example:

```text
A ---> B ---> C       D (no constraints with A/B/C)
```

Do not assume D will always come before or after A/B/C. If correctness depends on D, declare a relationship with D. Avoid creating cycles like `A before B` and `B before A` because conflicting constraints are hard to maintain and do not reflect valid system dependencies.

### 5.1. An ordering relationship does not force the target's condition to true

Suppose `B` is registered after `A` via `after = A.class`, but A has:

```java
@AutoConfiguration
@ConditionalOnProperty(prefix = "sample", name = "enabled",
                       havingValue = "true")
public class A {
    // Beans of A ...
}
```

If `sample.enabled=false`, A creates no beans from that configuration. `@ConditionalOnBean` in B can still fail to match; **setting order does not override conditions**. Likewise, if the target is not in `AutoConfiguration.imports`, it is not automatically included merely by being mentioned in `before`/`after`.

## 6. Standalone Java 17+ example: observing all four attributes

To observe each attribute's effect independently, this example creates **four pairs** of auto-configurations. In each pair, the "source" registers a source bean; the "target" registers a result bean only when it sees the source bean via `@ConditionalOnBean(name = ...)`.

Intentional point of the exercise: the `AutoConfiguration.imports` file **lists target before source** to show that `before`/`after` declarations work independently of line order in the file. We inspect bean state after the context is created, **not using constructor print order as evidence**.

Uses **Spring Boot 3.3.13**, **JDK 17+**, **Maven 3.8+**. Structure:

```text
auto-configuration-order-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── OrderDemo.java
        └── resources/
            └── META-INF/
                └── spring/
                    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>auto-configuration-order-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
            <version>3.3.13</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/OrderDemo.java`:

```java
package demo;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration(proxyBeanMethods = false)
@EnableAutoConfiguration
public class OrderDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(OrderDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println(
                "before=" + context.containsBean("beforeResult")
            );
            System.out.println(
                "after=" + context.containsBean("afterResult")
            );
            System.out.println(
                "beforeName=" + context.containsBean("beforeNameResult")
            );
            System.out.println(
                "afterName=" + context.containsBean("afterNameResult")
            );
        }
    }

    // PAIR 1: before (Class reference).
    @AutoConfiguration(before = BeforeTarget.class)
    public static class BeforeSource {
        @Bean("beforeSeed")
        String beforeSeed() {
            return "available";
        }
    }

    @AutoConfiguration
    public static class BeforeTarget {
        @Bean("beforeResult")
        @ConditionalOnBean(name = "beforeSeed")
        String beforeResult() {
            return "matched";
        }
    }

    // PAIR 2: after (Class reference).
    @AutoConfiguration
    public static class AfterSource {
        @Bean("afterSeed")
        String afterSeed() {
            return "available";
        }
    }

    @AutoConfiguration(after = AfterSource.class)
    public static class AfterTarget {
        @Bean("afterResult")
        @ConditionalOnBean(name = "afterSeed")
        String afterResult() {
            return "matched";
        }
    }

    // PAIR 3: beforeName (fully qualified class name, using $ character).
    @AutoConfiguration(beforeName = "demo.OrderDemo$BeforeNameTarget")
    public static class BeforeNameSource {
        @Bean("beforeNameSeed")
        String beforeNameSeed() {
            return "available";
        }
    }

    @AutoConfiguration
    public static class BeforeNameTarget {
        @Bean("beforeNameResult")
        @ConditionalOnBean(name = "beforeNameSeed")
        String beforeNameResult() {
            return "matched";
        }
    }

    // PAIR 4: afterName (fully qualified class name, using $ character).
    @AutoConfiguration
    public static class AfterNameSource {
        @Bean("afterNameSeed")
        String afterNameSeed() {
            return "available";
        }
    }

    @AutoConfiguration(afterName = "demo.OrderDemo$AfterNameSource")
    public static class AfterNameTarget {
        @Bean("afterNameResult")
        @ConditionalOnBean(name = "afterNameSeed")
        String afterNameResult() {
            return "matched";
        }
    }
}
```

File `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
# Each pair intentionally lists target before source.
demo.OrderDemo$BeforeTarget
demo.OrderDemo$BeforeSource

demo.OrderDemo$AfterTarget
demo.OrderDemo$AfterSource

demo.OrderDemo$BeforeNameTarget
demo.OrderDemo$BeforeNameSource

demo.OrderDemo$AfterNameTarget
demo.OrderDemo$AfterNameSource
```

**Why use nested classes?** To keep the example in a single Java file. Spring Boot 3.3 allows nested auto-configuration classes if the binary name with `$` is used in the imports file. Real starter projects usually place each `@AutoConfiguration` in its own top-level class for clarity.

**Why use `@SpringBootConfiguration` + `@EnableAutoConfiguration`?** This enables auto-configuration importing without turning on component scanning for the `demo` package. Auto-configurations are loaded via the imports file according to the boundary described in the documentation, preventing component scanning from accidentally picking up the nested classes and invalidating the test.

Run from the `auto-configuration-order-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.OrderDemo
```

Four lines printed by the program (ignoring any additional Spring/Maven environment log lines):

```text
before=true
after=true
beforeName=true
afterName=true
```

**Reading the output:**

1. `before=true`: `BeforeSource` is ordered before `BeforeTarget` thanks to `before = BeforeTarget.class`. Therefore, when the condition in target is evaluated, the bean definition named `beforeSeed` has already been processed.
2. `after=true`: `AfterTarget` is ordered after `AfterSource` thanks to `after = AfterSource.class`. The condition on `afterSeed` matches.
3. `beforeName=true`: `BeforeNameSource` references target via the string `"demo.OrderDemo$BeforeNameTarget"`. Ordering works the same as `before` even without a class literal.
4. `afterName=true`: `AfterNameTarget` references source via the string `"demo.OrderDemo$AfterNameSource"`. The `afterNameSeed` bean definition is evaluated before target.

In this experiment, the result beans are registered only when the source bean is already in the inspected definition set; having all four result beans present **proves the bean conditions see the sources in the run scenario**, rather than measuring object instantiation timing.

**Example limitation:** the output above is the expected result based on Spring Boot 3.3 rules and logic. If you want to verify in your current environment, run the Maven command and inspect the four output lines from `OrderDemo`; dependency download/log output may vary across machines. Do not rely on removing an attribute and running once as definitive proof of failure: without an explicit relationship, the default order in a particular environment might still happen to work by chance.

## 7. Auto-configuration order vs. bean initialization order

Consider two questions:

**Question A:** "When evaluating `@ConditionalOnBean(PaymentGateway.class)` in auto-configuration B, does Spring already know about the `PaymentGateway` bean definition from auto-configuration A?"

→ Related to **auto-configuration application order**, so `@AutoConfiguration(after = A.class)` on B can be a valid declaration if A is the provider of that definition.

**Question B:** "When creating the `OrderService` bean, has the `PaymentGateway` bean finished being created?"

→ This is a **bean-creation dependency relationship**. Declare the dependency directly via `@Bean` parameter or constructor:

```java
@Bean
OrderService orderService(PaymentGateway gateway) {
    return new OrderService(gateway);
}
```

This snippet assumes the types `OrderService` and `PaymentGateway` exist. Spring will resolve the dependency when creating `OrderService`. If you only need the `metricsBootstrap` bean to initialize before another bean without a normal type dependency, you can use `@DependsOn("metricsBootstrap")` after considering lifecycle design.

**Do not use `before` / `after` to solve Question B.** Conversely, `@DependsOn` cannot replace ordering metadata to make an auto-configuration condition "see" bean definitions processed later.

## 8. Starter practices and how to test

When building a starter with two interdependent auto-configurations:

1. Clearly identify which class **provides the bean definition** and which class needs that definition to decide `@ConditionalOnBean`/`@ConditionalOnMissingBean`.
2. Pick **one clear place to declare the relationship**, usually `after` on the consuming class. If the dependency is optional or you want to avoid direct compile-time coupling, use `afterName` with a verified FQCN.
3. Put every auto-configuration owned by the starter in `AutoConfiguration.imports`. Do not rely on component scanning; do not use `@ComponentScan` inside an auto-configuration to scan an arbitrary package area.
4. Add library availability conditions (`@ConditionalOnClass`, `@ConditionalOnProperty` where appropriate). Ordering attributes do not enable/disable libraries or guarantee a bean is created.
5. Test both with and without the target auto-configuration, with the target's condition true/false, with user-defined beans, and with optional classes absent. In Spring Boot, `ApplicationContextRunner` with `AutoConfigurations.of(...)` is a concise way to test; across multiple auto-configurations, Boot applies the same ordering rules as at application runtime.

To inspect a real application, enable `--debug` or use `ConditionEvaluationReport` to see why bean conditions matched/did not match. Combine this with checking `@AutoConfiguration` metadata and entries in the imports file. The condition report describes **condition outcomes**, not the exact sequence in which instances are created.

### 8.1. When to use `@AutoConfigureOrder`?

`@AutoConfigureOrder` supports general priority among auto-configurations that do not need to know about each other directly, similar in ordering semantics to `@Order` but designed specifically for auto-configuration. For a concrete dependency like "configuration B needs A's definition first," **`after`/`afterName` is clearer than an obscure priority number**.

Do not assume that adding `@Order(1)` to every class or reordering lines in the imports file replaces `before`/`after` relationships. Nor should you use priority numbers to solve bean initialization issues that require real dependencies.

## 9. Common mistakes

| Wrong practice or misconception | Why it is wrong | How to handle it |
| --- | --- | --- |
| `after = X.class` guarantees X's beans are created first | `after` governs auto-configuration processing/bean definitions, not instance initialization timing | Use injection/constructor or `@DependsOn` to express bean-creation dependencies |
| `afterName = "myBean"` | `afterName` expects an **auto-configuration class name**, not a bean name | Use `"com.acme.MyAutoConfiguration"` |
| Using `.` instead of `$` for nested classes in strings | Java binary names for nested classes use `$` | Use `Outer$InnerAutoConfiguration` |
| Reading line order in the imports file as initialization order | The imports file lists candidates; Boot applies sorting metadata | Declare `before`/`after`; use bean dependencies for lifecycle |
| Assuming `beforeName` automatically adds the target auto-configuration | Ordering attributes do not import dependencies or bypass the target's conditions | Ensure the target is registered via the imports file if needed |
| Setting `before` and `after` to form a cycle | No valid ordering can satisfy all constraints | Redesign dependencies to eliminate the cycle |
| Thinking `@ConditionalOnBean` always sees beans from all auto-configurations | Conditions evaluate against already-processed bean definitions | Identify the bean-providing configuration and declare valid ordering |
| Using a `Class` reference for an optional library without checking build dependencies | Can create unwanted compile-time coupling | Consider `beforeName`/`afterName` and `@ConditionalOnClass` in the right place |
| Using `@AutoConfigureOrder` instead of an explicit dependency relationship | Priority levels do not express which target B needs | For A → B, put `after = A.class` or `afterName` on B |
| Auto-configuration gets component-scanned | May bypass candidate discovery and auto-configuration ordering as intended | Import only via `AutoConfiguration.imports` and keep in a dedicated package |

## 10. Self-check quiz

**Question 1.** `@AutoConfiguration(after = DatabaseAutoConfiguration.class)` is on `AuditAutoConfiguration`. What is guaranteed?  
**Answer:** When both are applied as auto-configurations, `DatabaseAutoConfiguration` is processed before `AuditAutoConfiguration` to register bean definitions; it does **not** guarantee every database bean has initialized before every audit bean.

**Question 2.** You need compatibility with an optional starter whose auto-configuration is `com.vendor.cloud.CloudAutoConfiguration`, without importing that class into your source code. Which attribute should you choose if your configuration must apply **after** it?  
**Answer:** `afterName = "com.vendor.cloud.CloudAutoConfiguration"`, along with adding necessary conditions for the optional class/feature. If the target is absent, this attribute does not load it automatically.

**Question 3.** The target class is `com.acme.Main$NestedAutoConfiguration`. Can you use `afterName = "com.acme.Main.NestedAutoConfiguration"`?  
**Answer:** That is not the right binary name format for a nested class; use `afterName = "com.acme.Main$NestedAutoConfiguration"`.

**Question 4.** A declares `before = B.class`, C declares `after = B.class`. What relationship is established? Where is D if nothing is declared for it?  
**Answer:** `A → B → C` when all three are applied. D has no fixed position relative to that chain.

**Question 5.** `@AutoConfiguration(after = A.class)` is present, but A is excluded by `@ConditionalOnClass`. Will `@ConditionalOnBean` in B match automatically because of `after`?  
**Answer:** No. `after` only expresses order among present candidates; it does not cause A to register beans when A's conditions are not met.

**Question 6.** `InventoryAutoConfiguration` needs to create a bean after `CacheWarmup` finishes initializing. Should you choose `after = CacheAutoConfiguration.class` or declare a bean dependency?  
**Answer:** It is a bean-initialization dependency; use injection/constructor or `@DependsOn` as appropriate. `after` only resolves auto-configuration application order.

## 11. Takeaways and references

- `before` / `after` take `Class`, `beforeName` / `afterName` take fully qualified `String` class names; both groups express the same **before/after** relationship.
- Ordering is **relative among auto-configurations**. Ordering attributes do not create dependencies, select beans, force conditions to true, or guarantee instance creation order.
- Use `beforeName`/`afterName` for optional class names and remember `$` if the target class is nested inside another class.
- Bean definition order matters for `@ConditionalOnBean`/`@ConditionalOnMissingBean` because conditions inspect only the bean definitions known at that time.
- A starter's auto-configurations must be listed in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Use `@AutoConfigureOrder` for general priority, and bean dependencies/`@DependsOn` to control initialization.

Official documentation (Spring Boot 3.3.13):

1. [`@AutoConfiguration` Javadoc — `before`/`after`/`beforeName`/`afterName`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html).
2. [Creating Your Own Auto-configuration — locating candidates, ordering, and bean conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
3. [`@AutoConfigureBefore` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html).
4. [`@AutoConfigureAfter` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html).
5. [`@AutoConfigureOrder` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureOrder.html).