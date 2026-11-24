# Filtering Bean Collections with `@Qualifier` and Distinguishing from `@Primary`

## 1. Objectives and Context

When an interface has multiple implementations managed by the Spring IoC container, a dependency may require either **a single matching implementation** or **an entire group of matching implementations**. These two cases carry different meanings:

- A **single** dependency like `PaymentHandler handler`: Spring must choose one exact bean.
- A **multi-element** dependency like `List<PaymentHandler>`, `Set<PaymentHandler>`, `PaymentHandler[]`, or `Map<String, PaymentHandler>`: Spring gathers type-compatible beans. You can further narrow that group with qualifiers.
- `@Primary` only expresses **selection preference** when one bean must be chosen among multiple candidates; it does not mean other beans are excluded from collections.
- `@Qualifier` expresses a **filtering criterion** among type-matched beans, and does not have to identify a unique bean.

This lesson focuses on **filtering collections with qualifiers** and directly comparing this with `@Primary`. This is the dependency resolution mechanism in the Spring Framework Core Container; no Spring Boot, web controller, or database is required.

## 2. How Spring Selects Beans

Suppose there are four beans of type `Processor`:

| Bean Name | Declared Qualifier | `@Primary` |
| --- | --- | --- |
| `main` | `general` | Yes |
| `fastOne` | `fast` | No |
| `fastTwo` | `fast` | No |
| `slow` | `slow` | No |

How will Spring resolve the following dependency injection points?

| Injection Point | Result | Explanation |
| --- | --- | --- |
| `Processor preferred` | `main` | One bean needed; `main` is the sole primary candidate |
| `@Qualifier("slow") Processor selected` | `slow` | Filtered by type `Processor` and qualifier `slow`, leaving one candidate |
| `@Qualifier("fast") List<Processor> fast` | `fastOne` and `fastTwo` | Both beans match type and qualifier; not selecting just one bean |
| `List<Processor> all` | All four beans | No qualifier at the injection point; primary does not exclude other beans |
| `@Qualifier("fast") Map<String, Processor> fastMap` | Two entries with keys `fastOne` and `fastTwo` | Values are filtered, while keys are **bean names** |
| `@Qualifier("fast") Processor oneFast` | Ambiguity error | Two beans share qualifier `fast`, with no unique selection |

You can picture the process as:

```text
Injection point + generic type (if any)
          |
          v
Identify candidate beans by type and autowire eligibility
          |
          v
If @Qualifier is present: keep only matching beans
          |
          +--> List/Set/array/Map dependency:
          |    receive matching beans (List/array may be sorted)
          |
          +--> Single dependency:
               must select one bean;
               check unique @Primary (and other resolution rules)
               or fail if still ambiguous
```

This is a conceptual model, not a method-by-method description of Spring's internals. Single-bean selection rules also consider other signals, such as bean name/parameter name, `@Priority`, and `@Fallback` in supported versions; do not rely on secondary rules when business intent already has an explicit qualifier.

## 3. `@Qualifier` with Collections: One Label Can Belong to Multiple Beans

For example, a data processing system has multiple high-speed strategies. Both `fastOne` and `fastTwo` carry the same `fast` label. Place the qualifier **on the bean** to declare group membership, and **on the injection point** to request that group:

```java
@Bean
@Qualifier("fast")
Processor fastOne() {
    return new Processor("fastOne");
}

@Bean
@Qualifier("fast")
Processor fastTwo() {
    return new Processor("fastTwo");
}

// On a constructor or @Bean method parameter:
@Qualifier("fast") List<Processor> fastProcessors
```

Spring injects **two elements**, because a qualifier is not a unique key. If `fastThree` is added later with qualifier `fast`, the collection automatically includes that bean without modifying the constructor.

Common forms:

- `@Qualifier("fast") List<Processor>`: retrieves matching beans; suitable when processing order matters.
- `@Qualifier("fast") Set<Processor>`: retrieves matching beans as a set; do not rely on `Set` iteration order if business logic requires ordering.
- `@Qualifier("fast") Processor[]`: retrieves matching beans as an array.
- `@Qualifier("fast") Map<String, Processor>`: retrieves matching beans; **keys are bean names** and **values are bean instances**. This is not a map from qualifier to bean.

Qualifiers first narrow down the set of **type-matched** beans. A bean of a different type with the same qualifier will not be added to `List<Processor>`.

### Qualifier vs. Bean Name

`@Qualifier("fast")` is usually a domain-meaningful label such as `fast`, `regional`, or `audit`. Spring can also use the **bean name** as a fallback qualifier value when applicable; for instance, `@Qualifier("fastOne")` can select a bean named `fastOne` even if no matching qualifier string was attached. However, business code is more resilient when using capability-descriptive labels rather than tying to factory method names.

For `@Bean`, a qualifier placed on the **factory method** provides metadata for that bean; a qualifier on the **injected parameter** acts as the selection condition. Placing a qualifier on only one side without a matching value will not yield the expected result.

## 4. `@Primary`: Preference at Single Injection Points

Mark a bean as `@Primary` when multiple beans share a type and you want a default bean chosen whenever **one** instance is needed:

```java
@Bean
@Primary
@Qualifier("general")
Processor main() {
    return new Processor("main");
}
```

With the beans from the table at the start of the lesson:

- `Processor preferred` without a qualifier receives `main` because it is the sole primary among candidates for that single injection point.
- `@Qualifier("slow") Processor selected` receives `slow` even though `main` has `@Primary`: bean `main` does not satisfy qualifier `slow`, so it is not prioritized here.
- `List<Processor> all` still contains `main`, `fastOne`, `fastTwo`, and `slow`. `@Primary` does not "filter out" the remaining three beans.
- `@Qualifier("fast") List<Processor> fast` still contains **both** fast beans. Marking one bean as primary does not turn a `List` into a single-element list.

If **two primary beans** are both candidates for a single injection point, primary by itself cannot resolve the ambiguity. If only **one** bean remains after qualifier filtering, Spring selects that bean; it does not need to be primary. If multiple beans remain after qualifier filtering and exactly one of them is primary, primary can select one bean **for a single dependency**, whereas a collection still receives all qualifier-matching beans.

| Criterion | `@Qualifier` | `@Primary` |
| --- | --- | --- |
| Meaning | Narrows candidates by label/attribute | Designates the preferred default bean |
| Effect on single dependency | Yes, though multiple candidates may still remain | Yes, if a unique primary resolves |
| Effect on collections | **Filters elements** | **Does not filter elements** |
| Reusable with the same value across beans? | Yes; very useful for grouping | Multiple primaries of the same type can cause ambiguity at single injection points |
| When to use | Selecting a strategy group or a bean by criterion | Choosing a default implementation among same-type beans |

## 5. Complete Runnable Example with Java 17+ and Spring Framework 6

Create a plain Spring Context Gradle application with this structure:

```text
qualifier-collections-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/QualifierCollectionsDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'qualifier-collections-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'QualifierCollectionsDemo'
}
```

`src/main/java/QualifierCollectionsDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

public class QualifierCollectionsDemo {

    record Processor(String id) {
    }

    record Inspector(
            Processor preferred,
            List<Processor> fast,
            Processor slow,
            List<Processor> all,
            Map<String, Processor> fastMap) {
    }

    @Configuration
    static class Config {

        @Bean
        @Primary
        @Qualifier("general")
        @Order(30)
        Processor main() {
            return new Processor("main");
        }

        @Bean
        @Qualifier("fast")
        @Order(20)
        Processor fastOne() {
            return new Processor("fastOne");
        }

        @Bean
        @Qualifier("fast")
        @Order(10)
        Processor fastTwo() {
            return new Processor("fastTwo");
        }

        @Bean
        @Qualifier("slow")
        @Order(40)
        Processor slow() {
            return new Processor("slow");
        }

        @Bean
        Inspector inspector(
                Processor preferred,
                @Qualifier("fast") List<Processor> fast,
                @Qualifier("slow") Processor slow,
                List<Processor> all,
                @Qualifier("fast") Map<String, Processor> fastMap) {
            return new Inspector(preferred, fast, slow, all, fastMap);
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            Inspector result = context.getBean(Inspector.class);

            System.out.println("single = " + result.preferred().id());
            System.out.println("fast = " + names(result.fast()));
            System.out.println("slow = " + result.slow().id());
            System.out.println("all = " + names(result.all()).stream().sorted().toList());
            System.out.println("fastKeys = " + new TreeSet<>(result.fastMap().keySet()));
        }
    }

    private static List<String> names(List<Processor> items) {
        return items.stream().map(Processor::id).toList();
    }
}
```

Run from the directory containing `build.gradle` with Gradle and JDK 17 or higher:

```bash
gradle run --quiet
```

Lines printed by `System.out.println`:

```text
single = main
fast = [fastTwo, fastOne]
slow = slow
all = [fastOne, fastTwo, main, slow]
fastKeys = [fastOne, fastTwo]
```

**Line-by-line explanation:**

1. `single = main`: parameter `Processor preferred` receives the primary bean. Parameter name `preferred` does not match bean name `main`, so the outcome demonstrates primary policy.
2. `fast = [fastTwo, fastOne]`: qualifier `fast` accepts exactly two beans; `@Order(10)` on `fastTwo` precedes `@Order(20)` on `fastOne`. `@Order` dictates list element order, not primary status.
3. `slow = slow`: only bean `slow` matches `@Qualifier("slow")`, regardless of `main` having `@Primary`.
4. `all = [...]`: with no qualifier, all four beans are received; the demo sorts the list **by name** before printing for stable stdout, so do not infer Spring's default ordering from this line.
5. `fastKeys = [fastOne, fastTwo]`: `Map<String, Processor>` filters by qualifier, while keys remain **bean names**. `TreeSet` is used solely to display keys in deterministic order.

In the example, `@Order` on `@Bean` methods serves as metadata for Spring to sort elements injected into `List`. When no order is declared, do not design logic that depends on incidentally observed ordering. If strict processing order is required, use explicit `@Order`/`Ordered` and pick an appropriate collection type. Singleton initialization order is a separate matter and is not dictated by `@Order`.

## 6. Three Common Misconceptions and How to Verify

### 6.1. Mistaking `@Primary` for Filtering

**Wrong expectation:** Marking `main` with `@Primary` leaves only `main` in `List<Processor>`.

**Actual behavior:** `List<Processor>` includes all type-matching beans. `@Primary` applies to single-dependency resolution; it does not restrict collection membership. To get only one group, use `@Qualifier` at the injection point.

### 6.2. Assuming Qualifiers Must Be Unique

**Wrong expectation:** Two beans sharing `@Qualifier("fast")` is invalid configuration.

**Actual behavior:** Sharing a qualifier is normal when multiple beans belong to a group. `@Qualifier("fast") List<Processor>` receives both. Only when requesting `@Qualifier("fast") Processor oneFast` without a unique choice is there a risk of `NoUniqueBeanDefinitionException` (typically wrapped in a bean creation error during context startup).

To test this on the example above, temporarily add this parameter to `inspector`:

```java
@Qualifier("fast") Processor oneFast
```

Both `fastOne` and `fastTwo` become candidates; with no primary inside the `fast` group, context startup fails. This is a **modification for reproducing the error**, not part of the working program run in section 5.

### 6.3. Assuming Qualifiers Override Primary Without Type Matching

**Wrong expectation:** `@Qualifier("slow")` always picks a bean labeled `slow`, even if that bean does not implement the injected type.

**Actual behavior:** A bean must satisfy both the **type** and the qualifier criterion. If the injection point is `@Qualifier("slow") Processor selected`, only `Processor`-typed beans with a matching qualifier are candidates. Qualifiers do not force Spring to inject a wrong-type bean into a dependency.

## 7. Practical Rules When Scaling a System

### Constructor Injection

Prefer constructor injection when the dependency is required. Place `@Qualifier` directly on the parameter to be filtered so intent is visible at the usage site:

```java
// Illustrative constructor in a Spring-managed bean.
final class Pipeline {
    private final List<Processor> fastProcessors;

    Pipeline(@Qualifier("fast") List<Processor> fastProcessors) {
        this.fastProcessors = List.copyOf(fastProcessors);
    }
}
```

This is a short illustrative snippet using the application's `Processor` type or declaring the corresponding type in a real project. For Spring to instantiate `Pipeline`, register the class as a bean via `@Component`/`@Bean`. With a single constructor, Spring does not require `@Autowired` on that constructor.

### Designing Meaningful Labels

Qualifiers should describe **capability or role**, such as `fast`, `audit`, or `offline`. Avoid labels that merely encode implementation names, because swapping implementations would leak technical details into constructors. To avoid error-prone repeated strings, you can define a **custom qualifier annotation** (meta-annotated with `@Qualifier`) to attach group characteristics at both declaration and injection sites.

### Distinguishing a Group of Beans from a Collection-Typed Bean

`@Qualifier("fast") List<Processor>` in the example means **aggregating `Processor` beans** matching the `fast` label. This is the typical case of multi-element injection. It must be distinguished from a bean whose **own type is `List<Processor>`** created via `@Bean`. When you need to select a predefined collection bean, declare clear generics, consider name-based injection with `@Resource` where appropriate, and verify actual container resolution; do not blindly apply the "filter individual Processors" rule to every collection-typed bean.

### When No Matching Bean Exists

- `@Autowired` requires the dependency to be satisfied by default; for autowired `List`/arrays/`Map`, at least one matching element bean is required by default. If a qualifier filters out every bean, bean creation may fail with an unsatisfied dependency error.
- `@Autowired(required = false)` can make a field/method injection point optional; do not infer that Spring automatically passes `List.of()` into every constructor.
- If business logic allows zero elements, consider explicitly designing an empty default or using `ObjectProvider<Processor>` and querying/streaming conditionally. Make the empty-collection policy explicit in the API design.

### When Is Ordering Needed?

If a group of handlers executes sequentially, order may be business-critical. For `List<Handler>`, use `@Order` or `Ordered` and test the actual ordering. For `Set`/`Map`, do not assume business semantics are preserved by iteration order. `@Primary` is not a mechanism for ordering handlers.

### When to Use `@Primary`?

Use `@Primary` when there is a default adapter and other adapters serve specific cases. For instance, `@Primary` on a default cache adapter prevents ambiguity for a single `CacheAdapter`, while `@Qualifier("audit") List<CacheAdapter>` still gathers the audit group independently. If peer behaviors are all meant to be used together, a qualifier-grouped collection is usually cleaner than forcing a primary.

## 8. Common Errors and Fixes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` on single dependency | Multiple beans share the type and remain ambiguous after filtering | Add a more specific qualifier; or declare one default primary if semantically appropriate |
| `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException` | No bean matches type and qualifier at a required injection point | Check bean registration, `@Bean` return type, qualifiers on both sides, package scanning |
| `@Qualifier("fast") List<...>` has fewer elements than expected | Bean lacks qualifier, generic mismatch, or is not an autowire candidate | Inspect element/generic types and qualifier metadata on each bean |
| Map has keys different from qualifier string | Keys of `Map<String, T>` are **bean names** | Use keys to identify beans; if a map by domain label is needed, convert with duplicate-label handling |
| List runs out of order | Missing `@Order`/`Ordered` or relying on non-contractual order | Declare explicit execution order and verify with tests |
| Multiple `@Primary` annotations added, yet single dependency still fails | Primary is no longer unique in the candidate set | Designate a single clear default or distinguish with qualifiers |
| Confusing a `List<T>` bean with a set of `T` beans | Two different collection configurations | Clarify whether you want a single collection bean or aggregated element beans |

Do not fix errors by randomly renaming parameters to match bean names. Spring supports parameter-name/bean-name matching for single dependencies, but grouping intent should be expressed with qualifiers so code remains resilient during refactoring.

## 9. Self-Check Exercises

1. Add a `fastThree` bean with `@Qualifier("fast")` to `Config`, without primary. Predict how `fast`, `all`, and `fastKeys` change. Correct result: the `fast` group grows to three, `all` grows to five, `Map` gains key `fastThree`; `preferred` remains `main`.
2. Place `@Primary` on both `main` and `slow`. Predict injecting `Processor preferred`. If both remain candidates and no other resolution rule applies, an ambiguity error occurs; the `fast` group is unaffected.
3. Keep `@Primary` on `main`, and add `@Qualifier("fast")` to `main` (removing `general`). How many beans will `@Qualifier("fast") List<Processor>` contain? Answer: three (`main`, `fastOne`, `fastTwo`). Primary still **does not exclude** the other two fast beans.
4. Why might `@Qualifier("fast") Processor selected` fail while `@Qualifier("fast") List<Processor> selected` succeeds? Because a single injection point must identify **one** bean, whereas a collection intentionally gathers **multiple** beans.
5. Should `@Primary` be used to order a multi-handler pipeline? No; use `@Order`/`Ordered` and express the execution flow transparently.

## 10. Key Takeaways and Official Documentation

- **Qualifiers are filters**, so one qualifier value can be attached to multiple beans to select an entire group.
- **Primary indicates preference for selecting one bean**; it does not limit the element count of `List`, `Set`, arrays, or `Map`.
- `@Qualifier` on collections and `@Order` address two independent concerns: **who participates** and **in what order**.
- Distinguish a collection of same-type beans from a single bean that itself has a collection type.

Official documentation: [Spring — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html), [Spring — Fine-tuning with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html), [Spring — `@Primary` and `@Fallback`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html), [Spring — Using Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html).
