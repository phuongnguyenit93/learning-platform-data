# Injecting Arrays, List, Set, and Map<String, T> in Spring Core Container

## Learning Objectives

When a feature needs **multiple implementations of the same interface**, Spring can inject all matching beans into a single dependency instead of forcing you to pick just one bean. After this lesson, you will know how to inject `T[]`, `List<T>`, `Set<T>`, and `Map<String, T>`; understand bean names, qualifier filtering, execution ordering, behavior when no beans exist, and common pitfalls.

Application example: an order processing system has multiple validation steps; each step is a bean implementing `OrderRule`. The service receives `List<OrderRule>` and iterates through each step without needing to hardcode a fixed list of implementation classes.

## 1. Four Forms of Dependency Collections

Suppose the Spring container has three beans implementing the `Handler` interface. An injection point can declare:

```java
Handler[] handlers;
List<Handler> handlers;
Set<Handler> handlers;
Map<String, Handler> handlersByName;
```

| Target Type | Injected Value | When to Use |
| --- | --- | --- |
| `Handler[]` | Array containing matching `Handler` beans | Integrating with Java APIs that expect arrays |
| `List<Handler>` | List of matching beans | A pipeline that needs iteration in a defined order |
| `Set<Handler>` | Set of matching beans | Set semantics matter; should not depend on iteration order |
| `Map<String, Handler>` | Keys are **bean names**, values are the corresponding beans | Selecting a strategy by bean name or looking up handlers |

This is **multi-bean autowiring**: Spring finds multiple beans whose type matches `T`. It differs from explicitly declaring a separate bean whose value is a `List<T>` or a configuration `Map`. The element type still matters: `List<Handler>` does not mean pulling every bean in the application.

Common injection points are constructor parameters, `@Bean` method parameters, `@Autowired` setters, or `@Autowired` fields. For a bean with only **one constructor**, Spring uses that constructor automatically without requiring `@Autowired`.

## 2. How Does Spring Select Elements?

A practical mental model of the dependency resolution process:

1. Spring has bean definitions registered via `@Component`/component scan, `@Bean` in a configuration class, or equivalent registration mechanisms. Only container-managed objects participate in autowiring.
2. For `List<T>`, `T[]`, or `Set<T>`, Spring looks for autowire-candidate beans compatible with type `T`. For `Map<String, T>`, it searches by the **value type `T`** and uses the **bean name** as the key.
3. Spring evaluates metadata on the injection point, including qualifiers and generic type information when present. `@Qualifier` can **filter multiple beans at once**, not only pick a single bean.
4. The container supplies the resulting collection. `@Order`/`Ordered` affects element order for arrays and lists; other collection types should not be relied upon as an execution ordering contract.

**Note on `@Primary`:** For a single `Handler handler`, `@Primary` helps choose one bean among multiple candidates. For `List<Handler>`/arrays/sets/maps, matching beans **still appear together**; `@Primary` does not collapse a list into a single element. `@Qualifier` is the right tool for narrowing down the group.

Bean names can come from `@Bean("name")`, `@Component("name")`, or default naming rules. For an autowired map, the key is **not** the class name, the return value of `handler.id()`, or the qualifier name.

## 3. Complete Runnable Example with Java 17 and Spring Framework 6.2

The following example registers three `Handler` beans, injects all four forms, filters the `fast` group, and contrasts them with a single dependency resolved via `@Primary`. It uses plain Spring Framework without Spring Boot.

Project structure:

```text
spring-collection-injection/
├── pom.xml
└── src/main/java/demo/CollectionInjectionDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-collection-injection</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/demo/CollectionInjectionDemo.java`:

```java
package demo;

import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

public class CollectionInjectionDemo {

    interface Handler {
        String id();
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean("alphaHandler")
        @Order(20)
        @Qualifier("fast")
        Handler alphaHandler() {
            return () -> "A";
        }

        @Bean("betaHandler")
        @Order(10)
        @Primary
        @Qualifier("fast")
        Handler betaHandler() {
            return () -> "B";
        }

        @Bean("gammaHandler")
        @Order(30)
        @Qualifier("slow")
        Handler gammaHandler() {
            return () -> "C";
        }

        @Bean
        Report report(
                Handler[] array,
                List<Handler> list,
                Set<Handler> set,
                Map<String, Handler> byName,
                @Qualifier("fast") List<Handler> fast,
                Handler preferred) {
            return new Report(array, list, set, byName, fast, preferred);
        }
    }

    record Report(
            Handler[] array,
            List<Handler> list,
            Set<Handler> set,
            Map<String, Handler> byName,
            List<Handler> fast,
            Handler preferred) {

        void print() {
            System.out.println("Array: " + ids(Arrays.asList(array)));
            System.out.println("List: " + ids(list));
            System.out.println("Set size: " + set.size());
            System.out.println("Map keys (sorted): " + new TreeSet<>(byName.keySet()));
            System.out.println("Fast: " + ids(fast));
            System.out.println("Single (@Primary): " + preferred.id());
        }
    }

    private static String ids(Collection<Handler> handlers) {
        return handlers.stream().map(Handler::id)
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(Report.class).print();
        }
    }
}
```

Run in the directory containing `pom.xml` (requires JDK 17+ and Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.CollectionInjectionDemo
```

Lines printed by the program (excluding Maven or library logs if logging is enabled in the environment):

```text
Array: B,A,C
List: B,A,C
Set size: 3
Map keys (sorted): [alphaHandler, betaHandler, gammaHandler]
Fast: B,A
Single (@Primary): B
```

Explanation of each result:

- The array and `List` contain all three handlers in `@Order(10)`, `@Order(20)`, `@Order(30)` order. **Lower values come first**.
- `Set` contains the matching beans. The example prints only its size because application logic should not assume `Set` iteration order matches `List`.
- `Map<String, Handler>` has the three declared **bean names** as keys. `TreeSet` in the print statement only **sorts the names for deterministic output**; it does not prove that Spring supplies the map in alphabetical or `@Order` order.
- The `@Qualifier("fast") List<Handler> fast` parameter receives only the two beans with the `fast` qualifier, and that list still follows `@Order` rules.
- `Handler preferred` takes a single value and selects `betaHandler` thanks to `@Primary`. Marking `betaHandler` with `@Primary` **does not exclude** it or other beans from the collections.

In a `@Component`-managed bean, the common style is constructor injection:

```java
// Illustrative snippet: requires Handler to be a type defined in the application.
@Component
class HandlerPipeline {
    private final List<Handler> handlers;

    HandlerPipeline(List<Handler> handlers) {
        this.handlers = handlers;
    }

    void execute() {
        handlers.forEach(handler -> System.out.println(handler.id()));
    }
}
```

In the snippet above, the `@Component` import is `org.springframework.stereotype.Component`. The class must be within component scan scope, and `Handler` plus its implementations must be registered as beans. This short snippet is **illustrative for dropping into a project**, not a standalone runnable program.

## 4. Filtering Collections with `@Qualifier`

`@Qualifier` works with collection injection. For instance, if two beans both carry the `fast` label, Spring injects **both** into a `List<Handler>` annotated with `@Qualifier("fast")`. Qualifier values are not required to be unique.

You can place a qualifier on beans defined via `@Component` or `@Bean` methods; on the consumer side, place it on a field, constructor parameter, or method parameter. Spring first matches the `Handler` type, then the qualifier narrows the candidate set. Even if a qualifier matches a bean name, the qualifier is still interpreted as a filter condition within type-matched beans, not a mechanism to bypass type checking.

Common syntax (illustrative snippet, used inside a Spring bean):

```java
@Autowired
@Qualifier("fast")
private List<Handler> fastHandlers;

// Conceptually equivalent when using a constructor:
// MyService(@Qualifier("fast") List<Handler> fastHandlers) { ... }
```

Prefer constructor injection for required dependencies because it is easier to test, keeps fields `final`, and makes the class contract explicit.

## 5. Ordering: `@Order`, `Ordered`, `@Priority`, and `@DependsOn`

When running a pipeline, **order is part of the business logic**. For autowired arrays and `List<T>`, Spring reads ordering metadata from `org.springframework.core.Ordered`, `@Order`, or the standard `@Priority`. Smaller numbers have higher precedence; if no order is declared, the default typically follows bean registration order, though you should not rely on that as a durable business contract.

```java
@Bean
@Order(100)
Handler lastHandler() {
    return () -> "last";
}
```

`@Order` can be placed on a component class or individual `@Bean` methods. If multiple `@Bean` methods create instances of the same class, placing it on **each method** defines the order of each bean. `jakarta.annotation.Priority` is a class-level alternative; this standard annotation cannot be declared on `@Bean` methods. Use `Ordered` when precedence needs to be supplied by the object instance itself.

Do not confuse these:

- `@Order` controls **element order when retrieving multiple beans** or certain framework sorting mechanisms; it does **not** force singletons to initialize in that order.
- `@DependsOn` specifies **bean initialization/destruction dependencies**, not element order inside `List<T>`.
- `@Primary` primarily resolves **a single-typed injection point** when multiple candidates exist, not list filtering.
- With `Set<T>` and `Map<String, T>`, if business flow strictly requires ordering, use `List<T>` with `@Order`, or sort a copy yourself using an explicit comparator. Do not rely on set/map iteration order.

## 6. Generic Types as Part of Selection Criteria

Spring can use generic type information on beans and injection points to locate the right candidates. For example, `Store<String>` and `Store<Integer>` do not belong to the same group when requesting `List<Store<String>>`.

```java
// Illustrative snippet inside a @Configuration;
// assuming interface Store<T> { T get(); } is already declared
@Bean
Store<String> textStore() {
    return () -> "ready";
}

@Bean
Store<Integer> countStore() {
    return () -> 42;
}

// In the consuming bean:
@Autowired
List<Store<String>> stringStores; // only matching Store<String> beans
```

This relies on generic metadata that Spring reads from bean declarations, such as the return type of `@Bean`. **Do not use raw types** like `List` or `Map` and expect Spring to infer `T`. With `Map<String, Store<String>>`, the first `String` is the **bean name key type**, while `Store<String>` is the value type being filtered.

If you explicitly define a bean that is itself a `List<Handler>` (rather than multiple `Handler` beans), distinguish two intents: **injecting an explicitly defined collection bean** versus **collecting multiple element beans**. Spring can match a collection bean by type information, but if the goal is referencing **that specific collection bean by name**, you can use `@Resource(name = "...")` on a field/setter or explicit configuration. That injection style does not mean collecting all implementations. For constructor parameters, `@Qualifier` or explicit configuration is more appropriate than `@Resource`.

## 7. When No `T` Bean Is Found

Here you must distinguish **injection site** and requiredness rules:

| Situation | Behavior to Note |
| --- | --- |
| Default `@Autowired` field or setter, empty candidate set | A required injection point can cause bean creation to fail (`UnsatisfiedDependencyException`/related error). Per Spring docs, at least one matching element is generally required. |
| `@Autowired(required = false)` field or setter, no candidates | Spring skips injection; the field keeps its initial value and the setter may not be called. Do not assume a field automatically receives an empty collection. |
| **Single constructor** of a bean, array/collection/map parameter with no elements | Spring has a special rule: a multi-element parameter can receive an **empty** container. This is an important exception when designing optional plugins. |
| Dynamic access with `ObjectProvider<T>` | Can use `orderedStream()` to query matching beans at the time of use. |

Example of an optional field keeping a default:

```java
// Illustrative snippet inside a Spring-managed bean:
@Autowired(required = false)
private List<Handler> optionalHandlers = List.of();
```

If you want to clearly express an optional dependency with dynamic/lazy resolution, `ObjectProvider<T>` is useful:

```java
// Illustrative: import org.springframework.beans.factory.ObjectProvider;
private final ObjectProvider<Handler> handlerProvider;

MyService(ObjectProvider<Handler> handlerProvider) {
    this.handlerProvider = handlerProvider;
}

void process() {
    handlerProvider.orderedStream().forEach(handler -> {
        // Invoke each handler in the order supported by Spring.
    });
}
```

This snippet belongs inside a Spring-managed `MyService` class. It lets you query the container at usage time instead of holding a fixed list initialized at startup.

Additional scope note: injecting a `List<PrototypeBean>` directly into a singleton does not mean iterating over the list creates a new prototype each time. Dependency resolution already happened when the singleton was created. When you need fresh instances per use, consider `ObjectProvider` or an appropriate scoping mechanism.

## 8. Distinguishing a Bean Map from a Configuration Data Map

Two declarations look similar but have different meanings:

```java
@Autowired
Map<String, Handler> handlersByName;  // bean name -> Handler instance
```

This is a **map of beans**. Keys such as `alphaHandler` come from the container.

```java
// Configuration-backed application data declaration, not an example of autowiring Handler beans:
Map<String, String> endpoints;
```

If `endpoints` holds YAML/properties data like `payments: https://...`, use configuration binding mechanisms (such as `@ConfigurationProperties` in Spring Boot, or `@Value`/appropriate value conversion). Do not expect autowiring `Map<String, String>` with `@Autowired` to turn all configuration properties into a map.

An important constraint: **multi-bean map** injection requires `String` keys because keys are bean names. `Map<Long, Handler>` is not a way to ask Spring to build a map keyed by numeric IDs automatically. If you need lookups by a business key, build your own map:

```java
// Illustrative: building a business index from the injected collection:
Map<String, Handler> byBusinessId = handlers.stream()
        .collect(Collectors.toMap(Handler::id, h -> h));
```

When using `Collectors.toMap`, handle duplicate IDs if your domain allows them; the snippet above throws an exception if two handlers share the same ID.

## 9. Safe Design and Operations

**Choose the data type according to intended usage.** If executing a chain of filters/validators/plugins in order, `List<T>` is the clear choice. If selecting an implementation by registered name, use `Map<String, T>`. If a library requires an array, use `T[]`. If you only need a group of objects, `Set<T>` fits, but do not assume `Set` deduplicates distinct beans just because they share the same class or business ID.

**Identity and stability.** Keys in `Map<String, T>` depend on bean names. Renaming a `@Bean`, changing a component name, or refactoring registration can break string-based lookups. If keys are part of a public business contract, declare bean names explicitly or design a dedicated registry keyed by a stable business identifier.

**Encapsulation.** An injected collection is a collection of bean references. Avoid adding/removing elements directly and assuming container registrations have changed. If a service wants to protect its state, take a defensive copy (`List.copyOf`, `Map.copyOf`) or an appropriate structure; if map ordering must be preserved, choose a structure with clear ordering semantics. All references still point to the original beans; copying the collection does not clone the underlying objects.

**Candidate set size.** An overly generic interface can pull in unrelated beans. Use domain-meaningful interfaces, qualifiers, or clear generics; avoid scanning components outside the intended scope. In particular, a bean with `autowireCandidate=false` or unmet registration conditions may be excluded from the candidate set.

**Resolution timing.** Constructor collection injection is typically resolved when the consumer is instantiated. If beans are registered or changed later, do not assume an injected collection updates over time; if dynamic lookup is genuinely needed, intentionally use `ApplicationContext`/`ObjectProvider` APIs.

## 10. Common Errors and How to Check

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException` | No matching `T` bean; required field/setter | Check `@Component`, component scan, `@Bean`, qualifiers, conditions, and injection form |
| `NoUniqueBeanDefinitionException` on single `T` injection | Multiple `T` beans without a unique candidate | Use `@Qualifier` or `@Primary`, or switch to multi-bean injection if all are needed |
| `List<T>` missing an expected bean | Bean not registered, generic/qualifier mismatch, or not an autowire candidate | Inspect bean definition and return type signature |
| `Map<String, T>` lacks expected key | Confusing bean name with class name, qualifier, or business ID | Specify `@Bean("...")` or `@Component("...")` explicitly and inspect `keySet()` |
| Pipeline runs out of order | Relying on registration order or `Set`/`Map` iteration order | Use `List<T>` and place `@Order` on target beans |
| `@Order` mistaken for singleton creation order | `@Order` only serves compatible sorting mechanisms | Use dependency relationships/`@DependsOn` if initialization order is required |
| Optional field is `null` | `@Autowired(required=false)` skipped injection | Initialize a safe default value or switch to constructor injection/`ObjectProvider` |
| Map receives wrong data type | Mixing bean-name map with properties map or using non-`String` keys | Separate bean registries from configuration binding |

Quick debugging steps: check whether **beans are created/registered**; check **`T` and generics**; check **qualifiers/conditions**; finally check **bean names and `@Order`**. In tests, you can call `context.getBeansOfType(Handler.class)` to inspect beans of that type, keeping in mind that type-based lookup does not automatically replicate every qualifier constraint of a specific injection point.

## 11. Self-Check Exercises

1. Add a `deltaHandler` bean with `@Order(5)` and qualifier `slow` to the complete example. Predict how `Array`, `List`, `Set size`, `Map keys`, and `Fast` change.
2. Remove `@Primary` from `betaHandler` while keeping the `Handler preferred` parameter. Analyze why single-bean injection can fail when multiple `Handler` beans match, while collections can still resolve.
3. Change `@Qualifier("fast")` on the `List<Handler>` parameter to `@Qualifier("slow")`. Explain the expected result and why `@Order` does not replace qualifiers.
4. Build a `Map<String, Handler>` keyed by `Handler.id()` from the injected `List<Handler>`. How would you handle two beans returning the same ID?

**Self-check answers:** Exercise 1: `Array`/`List` start with D (order `5,10,20,30`), set size increases to 4, map gains `deltaHandler`, and `Fast` still contains B and A. Exercise 2: there are multiple candidates for a single `Handler`, requiring a selection rule; collection injection still collects matching beans. Exercise 3: the filtered list takes only `gammaHandler`. Exercise 4: a duplicate-key policy is needed (throw an error, keep first/last, or enforce unique IDs by design).

## Official Documentation

- Spring Framework — [Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html): array, collection, and map injection, ordering, and optional dependencies.
- Spring Framework — [Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html): qualifiers as filters, including on collections.
- Spring Framework — [Using Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html): filtering candidates using generics.
- Spring Framework — [`@Autowired` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/beans/factory/annotation/Autowired.html): API contract for array/collection/map injection.
