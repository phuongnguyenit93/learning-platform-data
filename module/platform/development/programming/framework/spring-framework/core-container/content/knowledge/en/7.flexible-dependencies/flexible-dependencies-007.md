# Iterating Multiple Candidates with stream and orderedStream in Spring Core Container

## Objectives

When an application has multiple beans implementing the same interface — such as multiple validation steps, converters, handlers, plugins, or business strategies — you sometimes want to **obtain all compatible beans and iterate over them**. The Spring Core Container supports this through `org.springframework.beans.factory.ObjectProvider<T>`:

- `provider.stream()` provides a sequential Java `Stream<T>` of matching beans with **no ordering guarantee**.
- `provider.orderedStream()` provides a sequential Java `Stream<T>` of matching beans **sorted by Spring's bean order comparator**.

Both methods belong to Spring's IoC/Dependency Injection mechanism; they are **not reactive streams** like Reactor `Flux`, HTTP data streams, or Java virtual threads. The result is a standard `java.util.stream.Stream`, using ordinary Java operations like `map`, `filter`, `forEach`, `findFirst`, and `toList`.

This lesson guides you through injecting providers, controlling order via `@Order`/`Ordered`, combining `@Qualifier` and generics, handling 0–n beans, understanding lazy/scope semantics, avoiding business logic mistakes, and practicing with a runnable Java 17 program.

## 1. From a Single Dependency to Multiple Candidates

Suppose an application has three beans implementing this interface:

```java
interface Rule {
    String name();
}
```

The three beans might validate input, enrich data, or record analytics. If a consumer declares a single `Rule rule`, Spring must find **one** candidate; when multiple beans exist without an unambiguous selection, the application may fail with `NoUniqueBeanDefinitionException`.

To process **all** candidates, you have these options:

| Dependency Form | Meaning | When to Use |
| --- | --- | --- |
| `Rule rule` | Pick one `Rule` bean | Exactly one strategy must exist or be explicitly selected |
| `List<Rule> rules` | Collection of matching beans injected at consumer creation | Fixed pipeline whose components are known at startup |
| `ObjectProvider<Rule> provider` | Retains on-demand bean lookup capability | Flexible lookup, queried at processing time |
| `provider.stream()` | Retrieve matching beans with no guaranteed order | Membership checks, metrics, order-independent tasks |
| `provider.orderedStream()` | Retrieve matching beans in Spring order | Pipelines, validation chains, or prioritized callbacks |

Conceptual example with a provider:

```java
// Illustrative snippet inside a Spring-managed bean.
private final ObjectProvider<Rule> rules;

Pipeline(ObjectProvider<Rule> rules) {
    this.rules = rules;
}

void execute() {
    rules.orderedStream().forEach(rule -> runRule(rule));
}
```

In this snippet, `runRule` is an application-defined method; import the provider via:

```java
import org.springframework.beans.factory.ObjectProvider;
```

An `ObjectProvider<T>` can be injected by Spring **even when zero `T` beans exist**. Having no candidates when iterating simply yields an **empty stream**, rather than a `null` collection.

## 2. Exact Difference Between `stream()` and `orderedStream()`

### `stream()` Does Not Guarantee Order

```java
provider.stream()
        .map(Rule::name)
        .forEach(System.out::println);
```

The provider returns a sequential stream of matching bean instances. Per Spring's contract, the order of `stream()` is **not guaranteed**; in some applications you might observe something resembling bean registration order, but that is not a basis for business design.

If you only want to list beans by name, sort the result explicitly:

```java
List<String> names = provider.stream()
        .map(Rule::name)
        .sorted()
        .toList();
```

Here `sorted()` is **application-chosen alphabetical sorting**, not Spring's `@Order` sorting. `Stream.toList()` has been available since Java 16, so it works on Java 17.

### `orderedStream()` Follows Spring Order

```java
provider.orderedStream()
        .forEach(rule -> runRule(rule));
```

Spring uses the bean factory's *common order comparator* to sort beans in the stream. With standard annotation configuration, the key directives are:

- `org.springframework.core.Ordered` — objects supplying their order number via `getOrder()`.
- `org.springframework.core.annotation.Order` — priority declared on a bean class or `@Bean` method.
- `jakarta.annotation.Priority` — standard class-level annotation recognized by Spring's ordering mechanism.

**Lower order values come first.** For example, `@Order(10)` takes precedence over `@Order(30)`. Two beans with the same order value or no declared order do not establish a reliable relative business contract; if two steps must run in a strict before–after sequence, assign distinct priorities or build a comparator with a secondary key.

`@Order` governs the order **when retrieving multiple beans through a sorting mechanism**, not a directive forcing Spring to instantiate lower-numbered beans before higher-numbered ones. Creation timing depends on dependency relationships and Spring's lifecycle.

### Comparing Both in One Example

Suppose:

| Bean | `Rule.name()` Value | Order |
| --- | --- | --- |
| `validationRule` | `validate` | 30 |
| `enrichmentRule` | `enrich` | 10 |
| `analyticsRule` | `analytics` | 20 |

When calling `stream().map(Rule::name).sorted().toList()`, the result is `[analytics, enrich, validate]` because it is sorted by **name**.

When calling `orderedStream().map(Rule::name).toList()`, the result is `[enrich, analytics, validate]` because it is sorted by **10, 20, 30**.

Do not treat the first result as evidence of `stream()`'s native order; `sorted()` itself produced the predictable order.

## 3. Complete Compilable and Runnable Example

The following program uses plain Spring Framework, Java 17, and Maven. It demonstrates both APIs, `@Qualifier` filtering multiple beans, `@Primary` selecting one bean, and a provider with no candidates.

### 3.1. Project Structure

```text
provider-stream-demo/
├── pom.xml
└── src/main/java/demo/ProviderStreamDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>provider-stream-demo</artifactId>
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

Contents of `src/main/java/demo/ProviderStreamDemo.java`:

```java
package demo;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

public class ProviderStreamDemo {

    interface Rule {
        String name();
    }

    record NamedRule(String name) implements Rule {
    }

    static final class ReportService {
        private final ObjectProvider<Rule> all;
        private final ObjectProvider<Rule> mandatory;
        private final ObjectProvider<Rule> missing;
        private final Rule preferred;

        ReportService(ObjectProvider<Rule> all,
                      ObjectProvider<Rule> mandatory,
                      ObjectProvider<Rule> missing,
                      Rule preferred) {
            this.all = all;
            this.mandatory = mandatory;
            this.missing = missing;
            this.preferred = preferred;
        }

        void printReport() {
            // Sort BY NAME for stable output, without relying on
            // the default order of ObjectProvider.stream().
            System.out.println("all.byName=" +
                    all.stream().map(Rule::name).sorted().toList());

            // Order determined by Spring via @Order.
            System.out.println("all.bySpringOrder=" +
                    all.orderedStream().map(Rule::name).toList());

            // Only select Rule beans with the "mandatory" qualifier.
            System.out.println("mandatory.bySpringOrder=" +
                    mandatory.orderedStream().map(Rule::name).toList());

            // No candidates: empty stream.
            System.out.println("missing.size=" +
                    missing.stream().toList().size());

            // Select one bean using @Primary.
            System.out.println("single.preferred=" + preferred.name());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean("validationRule")
        @Order(30)
        @Qualifier("mandatory")
        Rule validationRule() {
            return new NamedRule("validate");
        }

        @Bean("enrichmentRule")
        @Order(10)
        @Qualifier("mandatory")
        Rule enrichmentRule() {
            return new NamedRule("enrich");
        }

        @Bean("analyticsRule")
        @Order(20)
        @Primary
        @Qualifier("metrics")
        Rule analyticsRule() {
            return new NamedRule("analytics");
        }

        @Bean
        ReportService reportService(
                ObjectProvider<Rule> all,
                @Qualifier("mandatory") ObjectProvider<Rule> mandatory,
                @Qualifier("notRegistered") ObjectProvider<Rule> missing,
                Rule preferred) {
            return new ReportService(all, mandatory, missing, preferred);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(ReportService.class).printReport();
        }
    }
}
```

Open a terminal in the `provider-stream-demo` directory and run (requires JDK 17+ and Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ProviderStreamDemo
```

Lines **printed by the program itself** (excluding logging messages added by Maven or Spring):

```text
all.byName=[analytics, enrich, validate]
all.bySpringOrder=[enrich, analytics, validate]
mandatory.bySpringOrder=[enrich, validate]
missing.size=0
single.preferred=analytics
```

### 3.2. Explanation of Each Result

**`all.byName`:** `ObjectProvider<Rule> all` finds all three `Rule` beans. After `map(Rule::name).sorted()`, they are sorted lexicographically into `analytics, enrich, validate`. Calling `sorted()` is required for this output to be deterministic.

**`all.bySpringOrder`:** `orderedStream()` uses the declared order. `enrichmentRule` has `@Order(10)`, `analyticsRule` has `@Order(20)`, and `validationRule` has `@Order(30)`. Hence the list is `enrich, analytics, validate`.

**`mandatory.bySpringOrder`:** parameter `ObjectProvider<Rule> mandatory` carries `@Qualifier("mandatory")`. Spring selects only `enrichmentRule` and `validationRule`, then sorts by `10` then `30`. One qualifier can be attached to **multiple beans** at once.

**`missing.size`:** no `Rule` bean has qualifier `notRegistered`. Spring still injects `ObjectProvider<Rule>`, and `stream()` yields an empty stream, so the size is 0.

**`single.preferred`:** Spring must select **one** `Rule` for the `Rule preferred` parameter, so `analyticsRule`'s `@Primary` applies. However, `@Primary` does not exclude other beans from `all.stream()` or `all.orderedStream()`.

### 3.3. Testing Order Changes

Change `@Order(30)` on `validationRule` to `@Order(5)` and re-run:

- `all.byName` stays `[analytics, enrich, validate]` because it still sorts by name.
- `all.bySpringOrder` becomes `[validate, enrich, analytics]` because `5` precedes `10` and `20`.
- `mandatory.bySpringOrder` becomes `[validate, enrich]`.
- `missing.size` and `single.preferred` remain unchanged.

This experiment cleanly separates **custom Java Stream ordering** from **Spring BeanFactory ordering**.

## 4. Ordering and Candidate Selection When Streaming

`orderedStream()` uses Spring's ordering rule: smaller values come first. `Ordered#getOrder()` fetches the value from the instance, `@Order` is declared on a class or `@Bean` method, and `jakarta.annotation.Priority` applies at class level. When two beans share the same order, the application should not assume relative order is always stable; pipelines requiring strict before–after ordering need distinct orders or an explicit comparator.

An important point when using **provider streams** is that metadata lives on the **bean definition**. For example, `@Order(5)` on a `@Bean` method is used by Spring when `orderedStream()` sorts, even if the returned object's class has no annotations. If you collect those objects and manually invoke a comparator outside the BeanFactory, factory-method metadata may no longer be available. Therefore, test ordering at the exact provider usage site.

| Mechanism | Effect When Streaming Beans |
| --- | --- |
| `@Qualifier` and generic type at injection point | Narrows **candidates** before streaming |
| `@Order`, `Ordered`, `@Priority` | Sorts **inside `orderedStream()`** |
| `@Primary` | Prioritizes when choosing **a single bean**; does not remove elements from streams |
| `@DependsOn` | Controls initialization relationships, not stream traversal order |

`@Order` on `@Configuration` does not automatically cascade down to every `@Bean` inside it. The lesson on collection ordering covered `PriorityOrdered`, tie-breaking, and factory methods in detail; here, simply remember those rules govern **`orderedStream()`**, whereas `stream()` makes no ordering commitment.

## 5. Filtering Multiple Beans with `@Qualifier` and Generics

### 5.1. `@Qualifier` on the Provider Injection Point

Spring can apply qualifiers when creating the provider at an injection point:

```java
// Illustrative snippet in a Spring-managed class:
private final ObjectProvider<Rule> mandatoryRules;

MyService(@Qualifier("mandatory") ObjectProvider<Rule> mandatoryRules) {
    this.mandatoryRules = mandatoryRules;
}
```

When `mandatoryRules.stream()`/`orderedStream()` is later called, the candidate set is already filtered accordingly. In practice, a qualifier such as `mandatory` can be attached to **two or more beans**. Do not treat a qualifier as a "single-selection command" when the application needs a group.

Qualifiers can be placed on beans registered via `@Bean` or `@Component`. Bean names also participate in certain candidate-matching rules, though **bean names** and **domain qualifiers** are two distinct concepts that should be kept clear in design.

### 5.2. Generic Types Help Narrow Candidates

Spring can use generic types on beans and injection points as candidate selection criteria. Example:

```java
// Illustrative snippet, to be placed inside a complete configuration/bean.
interface Decoder<T> {
    T decode(byte[] input);
}

@Bean
Decoder<String> stringDecoder() {
    return input -> new String(input,
            java.nio.charset.StandardCharsets.UTF_8);
}

@Bean
Decoder<byte[]> bytesDecoder() {
    return input -> input.clone();
}

// In another bean's constructor:
DecoderRegistry(ObjectProvider<Decoder<String>> stringDecoders) {
    this.stringDecoders = stringDecoders;
}
```

This is an illustrative snippet to place in an appropriate configuration, not a standalone program. `ObjectProvider<Decoder<String>>` can select beans whose generic metadata matches `Decoder<String>`. This depends on Spring having full generic info on bean definitions; declaring a `@Bean` returning raw `Decoder` loses critical information.

Using `ObjectProvider<Object>` queries a very broad and hard-to-control set of beans. Prefer narrow interfaces, explicit generics, and domain-meaningful qualifiers.

### 5.3. Do Not Confuse Type Filtering with Instance Filtering

`@Qualifier` and generics affect the **bean candidate set** before streaming. By contrast, `provider.stream().filter(rule -> ...)` is a Java Stream operation processing **already-retrieved bean instances**. For beans with expensive initialization, this difference matters: filtering after obtaining beans does not prevent Spring from instantiating them when needed.

## 6. Zero Beans, One Bean, and Multiple Beans

`ObjectProvider<T>` supports both single lookup and multi-bean iteration. Distinguish each API's result:

| Matching Candidate Set | `stream()` | `orderedStream()` | `getObject()` / `getIfAvailable()` |
| --- | --- | --- | --- |
| Zero beans | Empty stream | Empty stream | `getObject()` throws missing-bean error; `getIfAvailable()` returns `null` |
| One bean | One element | One element | Returns that bean |
| Multiple beans | Multiple elements | Multiple elements in Spring order | Must resolve a single candidate; may fail with ambiguity |

When multiple candidates exist, `stream()` **does not default to picking just one**. That is why querying a stream is usually more appropriate than calling `getObject()` in multi-implementation plugin architectures.

Example checking for zero candidates:

```java
// Illustrative snippet in a class that already has ObjectProvider<Rule> rules.
if (rules.stream().findAny().isEmpty()) {
    System.out.println("No matching Rule beans");
}
```

If a matching bean exists yet throws an exception in its constructor or `@Bean` factory method, consuming the stream **can still throw a bean creation error**. Do not catch every exception and treat it as "no rules": an empty candidate set is a valid state, whereas a failing bean is a configuration/runtime defect.

Note that `getIfAvailable()` handles missing dependencies, yet **does not guarantee freedom from ambiguity errors** when multiple candidates exist. If you only want a single candidate when unique, refer to the contract of `getIfUnique()`/`ifUnique()`. For running 0..n rules, streams are the right API.

## 7. Java Streams: Safe Operations and Execution Timing

The return value of `ObjectProvider.stream()`/`orderedStream()` is a Java `Stream<T>`, so standard operations apply:

```java
// The illustrative snippets below live inside a class with provider:
// Retrieve a list at the current moment:
List<Rule> current = provider.orderedStream().toList();

// Retrieve names only, independent of original order:
List<String> names = provider.stream()
        .map(Rule::name).sorted().toList();

// Retrieve the first rule according to Spring order:
Optional<Rule> first = provider.orderedStream().findFirst();

// Execute business logic in Spring order:
provider.orderedStream().forEach(rule -> apply(rule));
```

These snippets require importing `java.util.List` and `java.util.Optional`; `apply` must be defined by the application.

### 7.1. Streams Are Single-Use

Do not store a `Stream<Rule>` directly in a field and invoke multiple terminal operations on the same stream object:

```java
// Illustrative erroneous code:
Stream<Rule> once = provider.orderedStream();
long count = once.count();
List<Rule> again = once.toList(); // IllegalStateException or reuse error
```

The right way is to **re-query the provider** to obtain a fresh stream or collect into a `List<Rule>` when reusing a single snapshot:

```java
List<Rule> snapshot = provider.orderedStream().toList();
long count = snapshot.size();
snapshot.forEach(rule -> apply(rule));
```

In Java 17, `Stream.toList()` returns an unmodifiable list. If you need to mutate the collection, create a mutable copy intentionally.

### 7.2. Stream Operations Can Short-Circuit

`findFirst()`, `anyMatch()`, and `limit(n)` may visit only a subset of candidates. Use them for search queries, not to guarantee every handler ran. When every rule must execute, use `forEach` on the chosen stream. Never call `count()` expecting side effects in intermediate operations to always execute: Java Streams may optimize within API contract bounds.

### 7.3. Do Not Blindly Switch to Parallel Processing

Both Spring methods return **sequential streams**. Calling `parallel()` switches execution to Java Stream's parallel model; Spring order still relates to encounter order, yet side effects can interleave across threads.

A pipeline writing to a database, calling APIs, or depending on state from previous steps **should not arbitrarily add `parallel()`**. Concurrency requires deliberate thread safety, transaction boundaries, and ordering semantics.

### 7.4. Use a Custom Comparator for Non-Spring Ordering

For example, if the application wants to sort by `Rule.name()`:

```java
List<Rule> alphabetical = provider.stream()
        .sorted(java.util.Comparator.comparing(Rule::name))
        .toList();
```

If two rules share the same name, the comparator returns zero; when a total domain order is required, add an explicit secondary identifier/key. Do not treat bean registration order as a stable tie-breaker.

## 8. Providers, Lazy Initialization, and Scope

`ObjectProvider<T>` is injected as an access point into the BeanFactory. When a consumer invokes the provider, the BeanFactory resolves candidates at that moment.

However, two aspects should not be confused:

**When the consumer calls the provider** differs from **when singleton beans were created**. By default, Spring may instantiate non-lazy singletons during context startup. Thus, holding `ObjectProvider<T>` in a field does not mean none of the `T` beans have been instantiated yet. `@Lazy` and dependency relationships determine deferred creation.

**Re-looking up a bean** differs from **creating a new instance**. For singletons, two provider calls normally return the same singleton. For prototypes, each bean resolution can return a new instance per scope rules. For scoped proxies, you must also understand how the proxy delegates to the active target.

When a pipeline needs a fixed snapshot:

```java
// Illustrative: constructor section of a class that has provider.
this.rules = provider.orderedStream().toList();
```

Because the collection is resolved when the constructor runs, the consumer behaves as if holding a fixed list. When per-invocation lookup is desired:

```java
// Illustrative: execution method in a class that has provider.
void process() {
    provider.orderedStream().forEach(this::processOne);
}
```

This is an intentional design choice, not a mechanism for mutating Spring configuration arbitrarily at runtime. Most applications register beans during startup; providers do not guarantee every system can hot-plug beans into a running context and have all operations observe those changes.

## 9. Type-Filtering Overloads in Spring Framework 6.2

Beyond zero-arg `stream()`/`orderedStream()`, recent Spring 6.2 releases support filtering **by candidate class type**:

```java
// Illustrative API signatures, not a standalone Java class:
Stream<T> stream(Predicate<Class<?>> customFilter);
Stream<T> orderedStream(Predicate<Class<?>> customFilter);

Stream<T> stream(Predicate<Class<?>> customFilter,
                 boolean includeNonSingletons);
Stream<T> orderedStream(Predicate<Class<?>> customFilter,
                        boolean includeNonSingletons);
```

The two overloads taking `Predicate<Class<?>>` were introduced in Spring **6.2.3**; the overloads adding `includeNonSingletons` appeared in **6.2.5**. They are present in Spring Framework 6.2.19 used in the example `pom.xml`.

- `customFilter` receives the **candidate class type**, unlike `Stream.filter(Predicate<T>)` which filters already-fetched instances.
- `includeNonSingletons` controls whether prototype/scoped beans are included alongside singletons in the corresponding overload, instead of singletons only.
- The `ObjectProvider.UNFILTERED` constant supports bypassing default filtering on certain overloads. This is an advanced capability that can surface candidates outside typical autowiring scope. Do not overuse it to bypass deliberately designed qualifiers.

Example syntax when filtering by a class-naming convention:

```java
// Illustrative snippet in a class with ObjectProvider<Rule> provider:
List<Rule> selected = provider.orderedStream(
        type -> type.getSimpleName().endsWith("Rule"),
        true
).toList();
```

This example shows the predicate receiving `Class<?>` rather than `Rule`. However, class names easily change during refactoring/proxying/lambdas; for real business rules, qualifiers or dedicated interfaces are clearer and more stable. Most applications using regular `stream()`/`orderedStream()` do not need these overloads.

## 10. Typical Application Scenarios

### 10.1. Business-Ordered Pipeline

For example, an order processing system has `ValidationStep`, `EnrichmentStep`, and `PersistenceStep`. If the required order is validate → enrich → persist, assign explicit order metadata and call `orderedStream()`. Before implementing, define which steps may fail and when to halt the pipeline. `@Order` does not define rollback or error policies for individual steps.

### 10.2. Independent, Order-Agnostic Plugins

A task that counts plugins, checks capabilities, or builds a set of names can use `stream()`. When printing a report for humans, sort names with Java Streams for deterministic output without tying business behavior to bean registration.

### 10.3. Selecting the First Matching Handler

```java
// Illustrative snippet; interface Handler requires supports(Request) and handle(Request).
Optional<Handler> selected = handlers.orderedStream()
        .filter(handler -> handler.supports(request))
        .findFirst();

selected.ifPresent(handler -> handler.handle(request));
```

`findFirst()` picks the first handler in stream order; here `orderedStream()` plays the decisive role. If multiple handlers share equal priority and both support the request, establish a stable secondary order or adjust the selection design.

### 10.4. Registering by Business Key

```java
// Illustrative snippet in a class with ObjectProvider<Rule> provider:
Map<String, Rule> byBusinessName = provider.stream().collect(
        java.util.stream.Collectors.toMap(Rule::name, rule -> rule)
);
```

The key here is the application-defined `Rule.name()`, not the Spring bean name. If two rules return the same name, `Collectors.toMap` configured this way throws on duplicate keys. Define an explicit duplicate-key policy rather than silently overwriting.

## 11. Common Errors and Resolutions

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Rules run in unexpected order | Relying on registration order when calling `stream()` | Use `orderedStream()` with proper order metadata |
| `orderedStream()` not in expected order | `@Order` placed on wrong level, missed bean, equal orders | Place order on bean class/`@Bean`; use clear tie-breakers |
| Expected bean does not appear | Not registered, outside component scan, generic/qualifier mismatch, or not an autowire candidate | Check bean definition and injection point |
| Multiple beans exist yet `getObject()` fails | That API must return one bean, while candidates are not uniquely resolved | Use `stream()`/`orderedStream()` if all are genuinely needed |
| `@Primary` chosen yet stream still has multiple beans | `@Primary` prioritizes single-bean resolution, does not filter streams | Use qualifiers/distinct types if a subset is wanted |
| Provider stream is empty | No valid candidates at injection point | Check `T`, qualifiers, generics, and registration config |
| Iterating stream throws bean creation error | Target bean initialization or scope failure | Fix root exception; do not treat as an empty set |
| Reusing stream fails | Stream already consumed by a terminal operation | Re-query provider for a new stream or save a list snapshot |
| Only one handler runs when all were expected | Used `findFirst()`/`limit(1)` | Use `forEach` to process all |
| Handlers run concurrently unexpectedly | Added `parallel()` with side effects | Keep sequential or design intentional concurrency |
| Output differs across environments | Relied on unguaranteed order or tied orders | Test order with explicit `@Order`/comparator and secondary key |

When debugging, check in order: (1) beans are registered in the right context; (2) type `T` and generics; (3) qualifiers and autowire-candidate status; (4) whether this is a multi-bean or single-bean query; (5) presence of `@Order`/`Ordered` metadata; (6) whether a bean fails initialization or has an unexpected scope.

Also remember: `@Order` on `@Configuration` does not propagate to `@Bean` methods, `@DependsOn` is not traversal order, and `ObjectProvider<T>` does not suppress bean creation failures.

## 12. Testing and Exercises

### Meaningful Tests

In `ProviderStreamDemo` from section 3, we can place assertions inside `printReport()` to verify the contract between application and container:

```java
// Additional snippet for use inside ReportService from section 3.
if (!all.orderedStream().map(Rule::name).toList()
        .equals(java.util.List.of("enrich", "analytics", "validate"))) {
    throw new AssertionError("Wrong Spring order");
}

if (!mandatory.orderedStream().map(Rule::name).toList()
        .equals(java.util.List.of("enrich", "validate"))) {
    throw new AssertionError("Wrong mandatory selection or order");
}

if (!missing.stream().findAny().isEmpty()) {
    throw new AssertionError("Expected empty stream");
}
```

No new stdout lines are printed when assertions pass; when they fail, the code throws the corresponding `AssertionError`. These checks are stronger than asserting incidental order from unsorted `stream()`.

### Exercise 1: Changing `@Order`

Change validation's `@Order(30)` to `@Order(5)`. Predict `all.bySpringOrder` and `mandatory.bySpringOrder`.

**Answer:** `[validate, enrich, analytics]` and `[validate, enrich]` respectively. `all.byName` still sorts by name, so it remains unchanged.

### Exercise 2: Expanding a Qualifier Group

Change the qualifier on `analyticsRule` from `metrics` to `mandatory`. What does `mandatory.bySpringOrder` become?

**Answer:** `[enrich, analytics, validate]` because all three beans qualify and sort by `10,20,30`.

### Exercise 3: Zero `Rule` Beans

Remove the `@Bean` methods returning `Rule`. Also remove or adjust `reportService`'s `Rule preferred` parameter since it is a required dependency. What does `ObjectProvider<Rule>.orderedStream().toList()` return?

**Answer:** an empty list; a provider can be injected even with zero target beans. If the mandatory `Rule preferred` parameter is kept, the context will fail to construct that consumer.

### Exercise 4: `List<T>` vs. `ObjectProvider<T>`

A consumer only needs to know all plugins **once at bean creation time**. Is a provider needed?

**Answer:** not necessarily. Direct `List<Plugin>` is a simpler design that accurately expresses the requirement. A provider fits when per-invocation lookup or scope-aware behavior is needed.

### Exercise 5: Two Beans with Equal Order

If `validationRule` and `analyticsRule` both have `@Order(20)` and business rules require validation to always precede analytics, can you trust their incidental list order?

**Answer:** you should not. Give them distinct orders or define a comparator with a stable secondary key, and test the tied-order scenario.

## Knowledge Summary

`ObjectProvider<T>` enables a Spring bean to query `T` candidates on demand. `stream()` fits when iterating all candidates without ordering dependencies; `orderedStream()` fits when business logic requires Spring-established order via `Ordered`, `@Order`, or corresponding annotation mechanisms.

Qualifiers and generics decide **which candidates participate**; order decides **traversal sequence**; `@Primary` normally solves **single-bean selection**, without filtering streams. When no candidates exist, an empty stream is normal; when a selected bean fails to initialize, the error still must be handled. Standard Java Stream properties apply: single-use consumption, potential short-circuiting, and concurrency requiring explicit design.

## Official Documentation

- Spring Framework — [`ObjectProvider<T>` Javadoc, 6.2.x](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html): `stream()`, `orderedStream()`, type filters, and scope-parameter overloads.
- Spring Framework — [Using `@Autowired`, 6.2](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html): multiple bean candidates, ordering, injection rules.
- Spring Framework — [Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html): qualifiers on injection points.
- Spring Framework — [`Order` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/annotation/Order.html): annotation semantics and limitations.
- Java SE 17 — [`Stream<T>` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): sequential stream processing, terminal operations, and reuse restrictions.
