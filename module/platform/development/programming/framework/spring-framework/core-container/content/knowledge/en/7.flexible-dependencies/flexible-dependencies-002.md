# Bean Collection Ordering with `Ordered`, `@Order`, and `@Priority` in Spring

## 1. The Problem: Multiple Beans of the Same Type That Must Run in Order

In the Spring Core Container, an interface can have multiple bean implementations. When injecting `List<T>` or `T[]`, Spring can collect all matching beans and **sort the elements** according to ordering metadata. This is useful for processing pipelines, validator suites, plugin lists, normalization steps, or handler groups that must execute sequentially.

For example, consider three steps for processing an order:

1. Validate input.
2. Calculate price.
3. Write log.

If the price calculation step runs before input validation, results may be wrong or errors may occur. A `List<OrderStep>` sorted by Spring according to declared order metadata allows adding new steps without rewriting the entire pipeline structure.

Three common ways to declare order are:

- `org.springframework.core.Ordered`: an **interface** allowing a bean to provide its order value at runtime via `getOrder()`.
- `org.springframework.core.annotation.Order`: a **Spring annotation** attaching order metadata to a class or a `@Bean` method.
- `jakarta.annotation.Priority`: a **Jakarta standard annotation** placed on a type (class); Spring interprets it as ordering metadata, and it can also participate in selecting a single candidate in certain single-bean situations.

**General sorting convention:** **lower numbers come first**. For example, `5` is placed before `10`, then `30`. "Higher priority" here does not mean a larger numeric value.

The goal of this lesson is to understand the exact mechanism applied at multi-element injection points, choose the right tool for each scenario, and avoid confusing **list order** with **bean initialization order**.

## 2. Where Does Spring Sort?

A multi-element dependency can appear in a constructor, field, or `@Bean` method parameter:

```java
// Illustrative snippet; the Step interface and the bean owning
// this constructor are declared in full in the example below.
public Pipeline(List<Step> steps) {
    this.steps = List.copyOf(steps);
}
```

When Spring instantiates `Pipeline` and needs `List<Step>`, the container will:

1. Find beans compatible with type `Step`, also considering autowire eligibility and qualifiers if present.
2. Gather the selected beans into a collection.
3. For an autowired `List` or array, use the appropriate order comparator to sort beans based on `Ordered`, `@Order`, or `@Priority`.
4. Inject the sorted list/array into the target object.

Therefore, order **does not depend** on whether a `@Bean` method appears earlier or later in the source file. When different order values are present, Spring sorts based on those values.

When **no order value is declared at all**, Spring documentation notes that elements follow bean definition registration order in the container. However, you should not treat registration order as a durable business contract: configuration changes, component scanning, or registration order changes can alter observed ordering.

### Which Collections Have a Reliable Ordering Contract?

| Injection Point | Usage | What to Remember |
| --- | --- | --- |
| `List<Step>` | Pipeline needing ordered step traversal | **Recommended:** Spring supports sorting by order metadata |
| `Step[]` | API accepting an array of steps | Spring supports sorting by order metadata |
| `Set<Step>` | Set of elements without ordering emphasis | Do not rely on `Set` iteration order as an execution contract |
| `Map<String, Step>` | Looking up beans by name | Keys are bean names; do not equate map iteration order with pipeline order |

Key takeaway: use `List` or an array when *execution order is a business requirement*. If lookup by name is needed, `Map` is more suitable; if an execution sequence is needed, inject a `List` and iterate with `for` or `stream` in the received order.

## 3. Order Value Comparison Rules

Commonly used values:

| Metadata | Example Value | Position Relative to Others |
| --- | ---: | --- |
| `@Order(-100)` | -100 | Before `@Order(0)` |
| `@Order(0)` | 0 | Before `@Priority(10)` |
| `@Priority(10)` | 10 | Before `Ordered#getOrder() = 20` |
| `Ordered#getOrder()` | 20 | Before `@Order(100)` |
| `@Order(100)` | 100 | Before unordered beans |
| No order declared | `Ordered.LOWEST_PRECEDENCE` semantically | Typically at the end of the sorted list |

There is no rule saying "`@Priority` always comes before `@Order`" merely because the annotation is named Priority. **The order value itself is what decides** in standard comparison. `@Order(5)` precedes `@Priority(10)`, and `@Priority(10)` precedes `Ordered#getOrder() = 20`.

`Ordered` defines these constants:

```java
Ordered.HIGHEST_PRECEDENCE  // Integer.MIN_VALUE
Ordered.LOWEST_PRECEDENCE   // Integer.MAX_VALUE
```

Negative numbers are completely valid. Still, prefer readable increments like `0, 10, 20, 30` to leave room for inserting new steps. An order number is a **comparative rank**, not a number of seconds, thread count, or OS priority level.

### What If Values Are Equal?

If two beans both have `@Order(10)`, the comparator lacks sufficient ordering information to determine their relative order. In practice, the outcome also depends on the input order prior to sorting; **do not write business logic requiring bean A to always precede bean B solely because both share the same order**. Assign distinct values if their relative order matters.

### Another Similarly Named Interface: `PriorityOrdered`

`org.springframework.core.PriorityOrdered` extends `Ordered`, but it is a **separate interface**, not the `jakarta.annotation.Priority` annotation. In Spring's `OrderComparator`, objects implementing `PriorityOrdered` are sorted **ahead of plain `Ordered` objects**, even if their `getOrder()` value is numerically larger than that of a plain `Ordered` object. This mechanism mainly matters in Spring infrastructure processing; for typical application pipelines, `Ordered` or `@Order` is sufficient. Do not automatically infer `PriorityOrdered` behavior from the `@Priority` example below.

## 4. Distinguishing the Three Declaration Styles

### 4.1. `Ordered`: Instance-Level Order Value

A bean implements Spring's interface:

```java
import org.springframework.core.Ordered;

final class ConfigurableStep implements Step, Ordered {
    private final int order;

    ConfigurableStep(int order) {
        this.order = order;
    }

    @Override
    public int getOrder() {
        return order;
    }

    @Override
    public String name() {
        return "configurable";
    }
}
```

The snippet above is **illustrative**, using the same `Step` interface from the complete program in section 5. `getOrder()` can return a value loaded from configuration, allowing multiple instances of the same class to have different orders.

Advantage: flexible and determined per instance. Trade-off: the business class depends on the Spring API `Ordered`.

### 4.2. `@Order`: Static Metadata

Declared on a class:

```java
@Order(10)
final class ValidationStep implements Step {
    @Override
    public String name() {
        return "validation";
    }
}
```

Or declared separately on a **`@Bean` method**:

```java
@Bean
@Order(5)
Step loggingStep() {
    return new PlainStep("logging");
}
```

These are two **illustrative** snippets using `Step` and `PlainStep` declared in section 5; supporting imports and annotations appear in the full program.

Placing `@Order` on a `@Bean` method is especially useful when you do not control the source class (third-party libraries) or when one class is registered as multiple beans in different roles.

`@Order` on a **`@Configuration` class** serves a different purpose: it influences processing order among configuration classes. It **does not propagate the order value** down to beans created by `@Bean` methods inside it. To control beans in a collection, place metadata on the **target bean class** or **each corresponding `@Bean` method**.

### 4.3. `@Priority`: Jakarta Standard Annotation

Example:

```java
import jakarta.annotation.Priority;

@Priority(30)
final class NotifyStep implements Step {
    @Override
    public String name() {
        return "notify";
    }
}
```

This is an **illustrative** snippet using the `Step` interface from the complete program. With Spring Framework 6+, the correct import is `jakarta.annotation.Priority`. Avoid copying the legacy `javax.annotation.Priority` import from older Spring Framework 5 projects.

**Important note:** `jakarta.annotation.Priority` cannot be placed directly on a `@Bean` method. To assign an order to a bean created by a factory method, place `@Order` on that method. Beyond collection ordering, `@Priority` also carries semantics for selecting a preferred candidate when multiple beans match a single dependency; do not confuse that scenario with element ordering in a `List`.

### Quick Comparison

| Characteristic | `Ordered` | `@Order` | `@Priority` |
| --- | --- | --- | --- |
| Kind | Spring Interface | Spring Annotation | Jakarta Annotation |
| Typical placement | Bean instance implementing `getOrder()` | Bean class, `@Bean` method | Bean class |
| Order varies per instance | Yes | No (fixed annotation value) | No (fixed annotation value) |
| Processed by Spring for `List`/array injection | Yes | Yes | Yes |
| Usable directly on `@Bean` method | No; instance implements interface | Yes | **No** |
| Involved in single-bean selection | Not a replacement for `@Primary`/qualifiers | Not a replacement for `@Primary`/qualifiers | Can participate in priority resolution in specific cases |
| Best suited when | Order comes from configuration/runtime | Spring app with static ordering | Integrating libraries or Jakarta-standard code |

If an instance both implements `Ordered` and carries `@Order`/`@Priority` on its class, `AnnotationAwareOrderComparator` typically prioritizes the value returned by `getOrder()` over static annotations. Avoid configuring two conflicting ordering sources without reason: specifying one source is easier to maintain.

## 5. Runnable Project: One Collection, Three Ordering Mechanisms

The following example uses **JDK 17+** and **Spring Framework 6.2.19**, without Spring Boot or a web server. To demonstrate thoroughly, five `Step` beans are registered:

- `bean-method`: `@Order(5)` on a `@Bean` method.
- `annotated`: `@Order(10)` on the class.
- `dynamic`: implements `Ordered`, returning `20`.
- `jakarta-priority`: `@Priority(30)` on the class.
- `unordered`: no metadata declared, appears last.

### 5.1. File Structure

```text
spring-ordering-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── OrderingDemo.java
```

Contents of `settings.gradle`:

```groovy
rootProject.name = 'spring-ordering-demo'
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'jakarta.annotation:jakarta.annotation-api:2.1.1'
}

application {
    mainClass = 'OrderingDemo'
}
```

The Jakarta dependency is declared explicitly so Java can compile the `@Priority` annotation. Spring Context provides the container, `@Configuration`, `@Bean`, `@Order`, `Ordered`, and autowiring support.

### 5.2. Complete Java Source Code

`src/main/java/OrderingDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

import jakarta.annotation.Priority;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

public class OrderingDemo {

    interface Step {
        String name();
    }

    static final class PlainStep implements Step {
        private final String name;

        PlainStep(String name) {
            this.name = name;
        }

        @Override
        public String name() {
            return name;
        }
    }

    @Order(10)
    static final class AnnotatedStep implements Step {
        @Override
        public String name() {
            return "annotated";
        }
    }

    static final class DynamicStep implements Step, Ordered {
        @Override
        public int getOrder() {
            return 20;
        }

        @Override
        public String name() {
            return "dynamic";
        }
    }

    @Priority(30)
    static final class JakartaStep implements Step {
        @Override
        public String name() {
            return "jakarta-priority";
        }
    }

    record Inspection(List<Step> steps, Step[] array) {
        List<String> listNames() {
            return steps.stream().map(Step::name).toList();
        }

        List<String> arrayNames() {
            return Arrays.stream(array).map(Step::name).toList();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        Step unordered() {
            return new PlainStep("unordered");
        }

        @Bean
        Step dynamic() {
            return new DynamicStep();
        }

        @Bean
        Step annotated() {
            return new AnnotatedStep();
        }

        @Bean
        Step jakartaPriority() {
            return new JakartaStep();
        }

        @Bean
        @Order(5)
        Step orderedFactoryMethod() {
            return new PlainStep("bean-method");
        }

        @Bean
        Inspection inspection(List<Step> steps, Step[] array) {
            return new Inspection(List.copyOf(steps), array.clone());
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Inspection inspection = context.getBean(Inspection.class);

            System.out.println("list  = " + inspection.listNames());
            System.out.println("array = " + inspection.arrayNames());
        }
    }
}
```

### 5.3. How to Run

In the `spring-ordering-demo` directory, use a Gradle version compatible with your chosen JDK:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper, replace the command above with `./gradlew run --quiet` (macOS/Linux) or `.\gradlew.bat run --quiet` (Windows PowerShell).

Stdout printed by the program:

```text
list  = [bean-method, annotated, dynamic, jakarta-priority, unordered]
array = [bean-method, annotated, dynamic, jakarta-priority, unordered]
```

Comparing the values:

| Element | Order Source | Comparison Value |
| --- | --- | ---: |
| `bean-method` | `@Order(5)` on `@Bean` method | 5 |
| `annotated` | `@Order(10)` on class | 10 |
| `dynamic` | `Ordered#getOrder()` | 20 |
| `jakarta-priority` | `@Priority(30)` on class | 30 |
| `unordered` | No order metadata | `LOWEST_PRECEDENCE` |

Although the `unordered()` method appears **first** in `Config`, the `unordered` bean is placed **last** in `List<Step>` and `Step[]` because the other beans have explicit orders. This shows that collection ordering is governed by metadata, not by which method a developer writes first in the source file.

This test also proves that Spring reads `@Order` on the `orderedFactoryMethod()` method when resolving collections. The `PlainStep` class of that bean has no annotations; looking only at the instance class would not reveal the value `5`.

## 6. Commonly Confused Interactions

### 6.1. Order Is Not a Selection Criterion

Order answers **"which bean runs first?"**; type and qualifiers answer **"which beans participate?"**.

Example (illustrative, not a standalone Java program):

```java
@Autowired
@Qualifier("payment")
private List<Step> paymentSteps;
```

Spring first gathers `Step` beans matching the `payment` qualifier, then sorts them if order metadata exists. `@Order(1)` does not pull a wrong-type or qualifier-mismatched bean into the list. Likewise, a bean with `@Order(100)` still belongs in the list if it matches; it simply appears after beans with smaller order values.

### 6.2. `@Primary` Does Not Mean "Runs First"

`@Primary` helps resolve cases requiring **a single bean** when multiple candidates exist. It does not determine `List<Step>` order. A bean with `@Primary` and `@Order(100)` can still be placed after a bean with `@Order(5)` in a collection.

`@Priority` can influence single-bean selection at certain single-element injection points, but this is an **additional semantic** of the Jakarta annotation; it does not mean `@Order` or `Ordered` can substitute for `@Primary`/`@Qualifier` in all situations. Selecting a single bean and ordering multiple beans are two distinct problems.

### 6.3. Injection Order Is Not Singleton Creation Order

This is an important misconception: `@Order(1)` on bean A **does not force Spring to initialize A before B** just because B has `@Order(2)`. The container creates singletons based on dependency resolution and the initialization lifecycle, whereas element order in a collection is determined when constructing the dependency value.

If one bean truly depends on another bean to function, express the dependency via the constructor or, when initialization order must be specified by bean name, look at `@DependsOn`. Do not use `@Order` to build singleton initialization contracts.

```java
@Bean
@DependsOn("configurationLoader")
Step reportStep() {
    return new PlainStep("report");
}
```

This is an **illustrative snippet**, valid only when the context contains a bean named `configurationLoader` and the corresponding imports. `@DependsOn` applies to initialization relationships, not the position of `reportStep` inside `List<Step>`.

### 6.4. Configuration Class Processing Order Differs from Bean Order

`@Order` can be meaningful when applied to configuration classes or special Spring extension points. However, `@Order(1)` on `@Configuration AppConfig` does not mean every bean in `AppConfig` comes first when injecting `List<T>`. To order specific beans, annotate the bean class or individual `@Bean` methods, or implement `Ordered` on the instance.

### 6.5. Manually Sorting Objects with Spring's Comparator

Beyond autowiring, you can explicitly sort a `List` of **object instances** using `AnnotationAwareOrderComparator`:

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.core.annotation.AnnotationAwareOrderComparator;

// Illustrative snippet; classes are defined in OrderingDemo.
List<OrderingDemo.Step> steps = new ArrayList<>(List.of(
        new OrderingDemo.DynamicStep(),
        new OrderingDemo.JakartaStep(),
        new OrderingDemo.AnnotatedStep()
));
AnnotationAwareOrderComparator.sort(steps);
```

In this example, the object order is `annotated` (10), `dynamic` (20), `jakarta-priority` (30). However, a comparator running over **plain objects** does not necessarily have source metadata from a `@Bean` method. Spring collection autowiring can inspect the bean definition and factory method, which is why it reads `@Order(5)` on `orderedFactoryMethod()`. Do not assume `sort(getBeansOfType(...).values())` always reproduces the exact order of an autowired collection if order metadata exists only on factory methods.

## 7. Real-World Scenario: Sequential Processing Pipeline

A pipeline has three functional groups:

- `validate`: validates input data, `@Order(10)`.
- `transform`: normalizes data, `@Order(20)`.
- `notify`: emits events after successful processing, `@Order(30)`.

If we inject `List<Stage>` into a service, we can run `for (Stage stage : stages) { stage.execute(context); }` and each stage class is responsible for only one step. When adding `enrich` between validate and transform, set `@Order(15)` without editing the loop.

Keep in mind several design limits:

- Steps with **strong dependency ordering** may be better served by an explicit orchestrator, state machine, or dependency graph; relying solely on order numbers becomes hard to follow when branching or complex dependencies exist.
- Order metadata **does not handle errors automatically**. If `validate` throws an exception, whether the pipeline halts or continues depends on execution logic, not `@Order`.
- Order metadata **does not imply** sequential execution. `List` merely holds steps in order; the code iterating over them and calling `execute` decides whether execution is sequential, parallel, or asynchronous.
- When two steps genuinely require a fixed relative order, give them **two distinct values**. Test the resolved bean list against a real context to catch unintended changes.

## 8. Common Errors and How to Diagnose

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| List not in expected order | Order not placed on **target bean** or proper `@Bean` method | Check bean class, factory method, and autowire output |
| Bean with `@Priority(100)` appears after `@Order(10)` | **10 is smaller than 100** | Remember smaller numbers come first; assign values consistently |
| Using `@Priority` on a `@Bean` method causes a compiler error | Jakarta `@Priority` does not allow method targets | Switch to `@Order` on the method or place `@Priority` on the class |
| `@Order` on `@Configuration` does not change List order | Configuration class order does not propagate to bean methods | Place `@Order` directly on the beans/methods to sort |
| Bean implements `Ordered` but annotation has a different number | `getOrder()` may take precedence over static annotations | Pick one clear ordering source, or verify the actual comparator |
| Relative order between two equal-order beans changes | Two beans share the same order, giving no relative constraint | Assign distinct order values if business logic depends on it |
| Set or Map traversed out of pipeline order | Using a collection without an ordering contract | Inject `List<Stage>` or an array when order matters |
| `@Order(1)` bean still initializes after another bean | Confusing collection order with initialization relationships | Use constructor dependencies/`@DependsOn` for initialization |
| Primary bean is not first in List | `@Primary` is not ordering metadata | Use `@Order`/`Ordered`/`@Priority` for ordering |
| Manual sorting differs from autowired List | Losing `@Order` metadata on factory methods when holding only objects | Verify order at the real injection point or pass metadata separately |

To diagnose, log the **names and orders of beans in the injected List** at the exact point of use. Do not look only at method declaration order, initialization log order, or keys in `Map<String, T>`.

## 9. Exercises and Self-Check Questions

**Exercise 1 — Adding a stage.** Add an `IntermediateStep` class with `@Order(15)` and register it via a `@Bean` returning `new IntermediateStep()`. Predict the output order from section 5:

```text
[bean-method, annotated, intermediate, dynamic, jakarta-priority, unordered]
```

Because `5 < 10 < 15 < 20 < 30` and the unordered bean comes last.

**Exercise 2 — Changing order at runtime.** Change `DynamicStep#getOrder()` from `20` to `2`. New result:

```text
[dynamic, bean-method, annotated, jakarta-priority, unordered]
```

This is a case where `Ordered` allows tuning per instance without changing annotations.

**Exercise 3 — Equal values.** Give `@Order(10)` to both `AnnotatedStep` and `JakartaStep` (replacing `@Priority` on the latter). Is the relative order between these two beans guaranteed? **No:** equal order values do not express a before/after relationship between them.

**Exercise 4 — Initialization.** If one stage has `@Order(1)` and another has `@Order(99)`, can we conclude the first stage's constructor runs first? **No:** collection injection order does not dictate singleton instantiation order.

**Exercise 5 — API distinction.** One class implements `PriorityOrdered` with `getOrder() = 100`, while another implements only `Ordered` with `getOrder() = 1`. When comparing both objects via `OrderComparator`, which comes first? **PriorityOrdered** comes first, because the `PriorityOrdered` group has separate precedence rules. This is an exception to distinguish from the standard `@Priority` annotation.

**Exercise 6 — Architecture.** A workflow has dependency branches A→B, A→C, B+C→D and steps can run in parallel. Should it be modeled entirely with `@Order`? **Not ideal**: order numbers only express a linear before/after relationship; a dependency graph or explicit orchestration conveys the flow better.

## 10. Key Takeaways

1. When injecting multiple beans of the same type into **`List<T>` or `T[]`**, Spring can apply ordering values from `Ordered`, `@Order`, and `@Priority` to sort elements.
2. **Smaller numbers come first**; `@Order(5)` precedes `@Priority(30)` in normal comparisons.
3. `Ordered` provides instance-level values, `@Order` provides static metadata on classes or `@Bean` methods; `@Priority` is a Jakarta annotation typically placed on classes.
4. `@Priority` and `PriorityOrdered` are **two different mechanisms**. `PriorityOrdered` has separate group precedence over plain `Ordered` in `OrderComparator`.
5. Distinguish **bean filtering** (type/qualifier), **bean ordering** (`Ordered`/`@Order`/`@Priority`), **single-bean selection** (`@Primary` and resolution rules), and **initialization order** (dependency graph/`@DependsOn`).
6. If a pipeline truly requires execution order, use `List` with explicit order values and test the resolved result.

### Official References

- [Spring Framework Reference — Using `@Autowired` (collection ordering)](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html).
- [Spring Framework Javadoc — `Ordered`](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/Ordered.html).
- [Spring Framework Javadoc — `@Order`](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/annotation/Order.html).
- [Spring Framework Javadoc — `AnnotationAwareOrderComparator`](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/annotation/AnnotationAwareOrderComparator.html).
- [Spring Framework Javadoc — `OrderComparator`](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/OrderComparator.html).
