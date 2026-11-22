# Using Predicate, Function, and Consumer in a Pipeline

In the **Java Stream API**, a pipeline often reads like a sentence describing a requirement: "filter paid orders, turn each order into a report line, then print the results". Those three steps correspond to three very important *behavioral function types* in Java: **`Predicate`**, **`Function`**, and **`Consumer`**.

These three types belong to the `java.util.function` package, introduced alongside functional programming in Java 8. They are **functional interfaces**: each interface has one primary abstract method, so we can provide its implementation using a **lambda** or a **method reference**. As a result, `filter`, `map`, and `forEach` accept *the behavior to apply* instead of forcing the author to manually control the loop.

This lesson belongs to the **Behavioral Functions and Types** chapter of the **JAVA_STREAM_API** module. The goal is to understand the input/output contract of the three function types, compose them in a lazy pipeline, and avoid bugs caused by side effects, shared state, or false assumptions about execution order. This also serves as the foundation for learning `reduce`, `collect`, grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers in subsequent sections.

## 1. At a Glance: How Do the Three Function Types Differ?

| Functional interface | Primary method | Accepts | Returns | Typical role in Stream |
|---|---|---|---|---|
| `Predicate<T>` | `boolean test(T value)` | An element of type `T` | `boolean` | Selecting elements with `filter`; checking with `anyMatch`, `allMatch`, `noneMatch` |
| `Function<T, R>` | `R apply(T value)` | An element of type `T` | A value of type `R` | Transforming elements with `map`; serving as a grouping key; mapping values when collecting |
| `Consumer<T>` | `void accept(T value)` | An element of type `T` | No return value | Performing a final action with `forEach`, `forEachOrdered`, `Optional.ifPresent` |

Example with an order:

- **Predicate:** "Is this order paid?" → `true` or `false`.
- **Function:** "How do we turn this order into a display string?" → `String`.
- **Consumer:** "Where do we print this display string?" → no return value.

Pay attention to the type letters:

- `T` in `Predicate<T>` and `Consumer<T>` is **the type of the element received**.
- `T` in `Function<T, R>` is **the input type**, while `R` is **the result type**. These two types can be the same or different.
- `Consumer` is not the same as `Function<T, Void>`: the `accept` method has an actual `void` return type, so a Consumer lambda does not need to—and must not—return a value.

~~~mermaid
flowchart LR
    A["Stream<Order>"] --> B["filter(Predicate<Order>)"]
    B --> C["map(Function<Order, String>)"]
    C --> D["Stream<String>"]
    D --> E["forEach(Consumer<String>)"]
    E --> F["Side effect: print report"]
~~~

`filter` and `map` are **intermediate operations**, whereas `forEach` is a **terminal operation**. This distinction determines when the lambdas are executed.

## 2. Complete Example: Selecting Orders and Exporting a Report

Suppose we have a list of orders. We want to take the orders that are **paid and have a value of at least 100,000 VND**, turn them into report lines, and print each line.

The following complete example uses **JDK 17 or later** because it uses `record`, `List.of`, and `Stream.toList()`:

~~~java
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class BehavioralFunctionsDemo {
    record Order(String id, String customer, long amountVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("DH01", "An",   120_000, true),
            new Order("DH02", "Bình",  190_000, false),
            new Order("DH03", "Chi",   150_000, true),
            new Order("DH04", "An",    70_000, true)
        );

        // Predicate<Order>: decides which orders to keep.
        Predicate<Order> isPaid = Order::paid;
        Predicate<Order> isHighValue = order -> order.amountVnd() >= 100_000;

        // Function<Order, String>: converts an order into a report line.
        Function<Order, String> toReportLine = order ->
            order.id() + " | " + order.customer() + " | " + order.amountVnd();

        // Consumer<String>: consumes the result, returns no value.
        Consumer<String> printLine = System.out::println;

        List<String> report = orders.stream()
            .filter(isPaid.and(isHighValue))
            .map(toReportLine)
            .toList();

        report.forEach(printLine);
    }
}
~~~

Output:

~~~text
DH01 | An | 120000
DH03 | Chi | 150000
~~~

Reading the pipeline in order:

1. `orders.stream()` creates a `Stream<Order>` source from the list.
2. `filter(isPaid.and(isHighValue))` accepts a `Predicate<Order>` combining two conditions, keeping `DH01` and `DH03`.
3. `map(toReportLine)` accepts a `Function<Order, String>`, transforming `Stream<Order>` into `Stream<String>`.
4. `toList()` is the terminal operation, actually evaluating the pipeline and producing the list of strings.
5. `report.forEach(printLine)` is a call on the **resulting `List`** to print each line. It uses `Consumer<String>` but is no longer part of the first Stream.

You can write everything as a single direct Stream pipeline:

~~~java
orders.stream()
    .filter(isPaid.and(isHighValue))
    .map(toReportLine)
    .forEach(printLine);
~~~

In that case, `forEach` itself terminates the pipeline. The two approaches serve different purposes: **`toList`** is suitable when you need to store and reuse the results; **`forEach`** is suitable when you need to perform a final action. To compute sums, counts, groups, or build structured reports, you should usually choose a terminal operation like `sum`, `count`, or `collect` rather than manually adding elements to an external collection with `forEach`.

## 3. Predicate<T>: Representing True/False Rules

`Predicate<T>` has one abstract method:

~~~java
@FunctionalInterface
public interface Predicate<T> {
    boolean test(T value);
    // Default methods such as and, or, negate; static methods such as not.
}
~~~

This is an abbreviated form to understand the contract, not a full copy of the JDK source code. The key point is that a Predicate **takes a value and returns a boolean result**.

### 3.1. Creating and Calling a Predicate

~~~java
import java.util.function.Predicate;

Predicate<String> notEmpty = text -> !text.isEmpty();
Predicate<String> startsWithJ = text -> text.startsWith("J");

System.out.println(notEmpty.test("Java"));    // true
System.out.println(notEmpty.test(""));        // false
System.out.println(startsWithJ.test("Kotlin")); // false
~~~

`test` can be called directly, but in Streams we usually **pass the Predicate into `filter`**:

~~~java
List<String> names = List.of("Java", "", "Kotlin", "JavaScript");

List<String> validNames = names.stream()
    .filter(notEmpty)
    .toList(); // [Java, Kotlin, JavaScript]
~~~

`filter` behaves as follows: for each element, if `predicate.test(element)` is `true`, keep it; otherwise discard it. **The element type does not change** after `filter`: if the input is `Stream<String>`, the output remains `Stream<String>`.

### 3.2. Composing Rules with and, or, negate

Instead of stuffing multiple conditions into one long lambda, you can name each rule individually:

~~~java
Predicate<String> hasText = text -> !text.isBlank();
Predicate<String> startsWithJ = text -> text.startsWith("J");

Predicate<String> both = hasText.and(startsWithJ);
Predicate<String> either = hasText.or(startsWithJ);
Predicate<String> doesNotStartWithJ = startsWithJ.negate();

System.out.println(both.test("Java"));     // true
System.out.println(both.test("Kotlin"));   // false
System.out.println(either.test("Kotlin")); // true
System.out.println(doesNotStartWithJ.test("Go")); // true
~~~

- `a.and(b)` is true only when both conditions are true.
- `a.or(b)` is true when at least one condition is true.
- `a.negate()` inverts the result.
- `and` and `or` **short-circuit**: `and` skips `b` if `a` is false; `or` skips `b` if `a` is true.

`String.isBlank()` requires JDK 11+. Additionally, starting in JDK 11 you can write `Predicate.not(String::isBlank)` when you need to express the negation of a method reference. In Java 8, you can use `s -> !s.trim().isEmpty()` if that whitespace rule is appropriate.

**Note:** `Predicate.and` short-circuiting operates **at the level of the conditional expression for a single element**. It differs from Stream operations such as `findFirst` or `anyMatch`, which can **stop traversing the entire source** as soon as enough information is available.

### 3.3. Predicate Is Also Used in Terminal Operations

~~~java
List<Integer> scores = List.of(6, 8, 9, 3);

Predicate<Integer> passing = score -> score >= 5;

boolean anyPass = scores.stream().anyMatch(passing);    // true
boolean allPass = scores.stream().allMatch(passing);    // false
boolean nonePass = scores.stream().noneMatch(passing);  // false
~~~

`anyMatch`, `allMatch`, and `noneMatch` are all **terminal operations** that can short-circuit as soon as the result is determined. For an empty Stream, `allMatch` and `noneMatch` return `true` by logical definition (vacuous truth); do not mistake that for there being an element that satisfied the condition.

## 4. Function<T, R>: Mapping One Value to Another

`Function<T, R>` has the method:

~~~java
@FunctionalInterface
public interface Function<T, R> {
    R apply(T value);
    // Default methods compose, andThen; static method identity.
}
~~~

It returns **one result** per invocation. The result can be the same type as the input or a completely different type.

~~~java
import java.util.function.Function;

Function<String, Integer> length = String::length;
System.out.println(length.apply("Stream")); // 6

Function<Integer, String> display = number -> "Value: " + number;
System.out.println(display.apply(12)); // Value: 12
~~~

### 4.1. Function Goes with map

~~~java
List<String> names = List.of("An", "Bình", "Chi");

Function<String, Integer> toLength = String::length;

List<Integer> lengths = names.stream()
    .map(toLength)
    .toList(); // [2, 4, 3]
~~~

`map` accepts a `Function<? super T, ? extends R>` and produces a `Stream<R>`. It **changes the value and can change the element type**: `Stream<String>` becomes `Stream<Integer>` in the example. One input element normally corresponds to one output element; if you want to turn one element into multiple elements, look into `flatMap`, which takes a function returning a Stream.

`map` does not mean filtering; the return value from a Function **is not interpreted as a true/false condition**. If you need to discard elements, use `filter`.

### 4.2. Composing Functions with andThen and compose

Sometimes a string needs to be normalized across multiple steps:

~~~java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> trim = String::trim;
Function<String, String> uppercase = text -> text.toUpperCase(Locale.ROOT);

Function<String, String> normalizeA = trim.andThen(uppercase);
Function<String, String> normalizeB = uppercase.compose(trim);

System.out.println(normalizeA.apply(" java ")); // JAVA
System.out.println(normalizeB.apply(" java ")); // JAVA
~~~

- `f.andThen(g)` executes **`f` then `g`**, i.e., `g(f(x))`.
- `g.compose(f)` executes **`f` then `g`**, which is also `g(f(x))`.

Order matters greatly when the two transformations are not commutative. For example, "trim whitespace then take length" can yield a different result from "take length then compute further".

You can pass the composed function directly into `map`:

~~~java
List<String> normalized = List.of(" java ", " Kotlin ", "go").stream()
    .map(normalizeA)
    .toList(); // [JAVA, KOTLIN, GO]
~~~

In addition, `Function.identity()` is a function that returns its input argument unchanged. It is especially useful in collectors, such as when you want to use the element itself as the value in a `Map`.

### 4.3. Mapping to Primitives

For aggregating counts or monetary amounts, use `mapToInt`, `mapToLong`, or `mapToDouble` to obtain a primitive Stream:

~~~java
import java.util.List;
import java.util.function.ToIntFunction;

List<String> names = List.of("Java", "Go", "Kotlin");
ToIntFunction<String> length = String::length;

int totalCharacters = names.stream()
    .mapToInt(length)
    .sum(); // 12
~~~

`ToIntFunction<T>` has the method `int applyAsInt(T value)`. It is a specialized variant of the Function family that avoids boxing through `Integer` in numeric processing paths. Similarly, there are `ToLongFunction`, `ToDoubleFunction`, as well as `IntFunction<R>` which takes an `int` as input.

When reading APIs like `Collectors.groupingBy(classifier)` or `Collectors.toMap(keyMapper, valueMapper)`, you will also encounter Function: they determine the **grouping key**, **Map key**, or **collected value**, rather than only being used for `map`.

## 5. Consumer<T>: Accepting a Value and Performing an Action

`Consumer<T>` has the method:

~~~java
@FunctionalInterface
public interface Consumer<T> {
    void accept(T value);
    // Default method andThen.
}
~~~

Consumer is meant for actions such as logging, writing output, sending data to a receiver, or updating a UI. **It does not return a result to pass further down the pipeline**.

~~~java
import java.util.function.Consumer;

Consumer<String> print = System.out::println;
print.accept("Hello Stream API"); // Prints one line
~~~

### 5.1. forEach and forEachOrdered

~~~java
List<String> names = List.of("An", "Bình", "Chi");
Consumer<String> print = name -> System.out.println("Name: " + name);

names.stream().forEach(print);
~~~

`forEach` is a terminal operation. For a Stream running **sequentially** from a `List` as in the example, the lines are printed in traversal order. With a **parallel Stream**, `forEach` does not guarantee output order, even if the source has an encounter order. If you must preserve the source's encounter order, use `forEachOrdered`:

~~~java
names.parallelStream()
    .forEachOrdered(print);
~~~

This preserves order for ordered sources but can reduce the benefits of parallel execution. If the work can be completed via pure aggregation, it is usually better to collect the results first using `collect` or `toList` and perform I/O only at the final step.

### 5.2. Chaining Consumers with andThen

~~~java
Consumer<String> announce = name -> System.out.println("Name: " + name);
Consumer<String> separator = name -> System.out.println("---");

Consumer<String> printWithSeparator = announce.andThen(separator);
printWithSeparator.accept("An");
~~~

Output:

~~~text
Name: An
---
~~~

`first.andThen(second)` runs the first Consumer and then the second **for the same value**. If the first action throws an exception, the subsequent action will not run. Unlike `Function.andThen`, it **does not produce a new value**.

Outside Streams, `Optional.ifPresent(consumer)` also accepts a Consumer to handle a value when present:

~~~java
java.util.Optional.of("Java")
    .ifPresent(System.out::println); // Java
~~~

### 5.3. Why Shouldn't You Use Consumer to Manually Collect a List?

The following snippet looks reasonable but introduces **mutable external state** into the processing flow:

~~~java
List<String> collected = new java.util.ArrayList<>();

names.stream()
    .map(String::toUpperCase)
    .forEach(collected::add); // Should not be used to collect results.
~~~

In a simple sequential pipeline, this may run fine. However, in a parallel Stream, `ArrayList` is not thread-safe; adding elements concurrently can cause lost data or errors. Replace it with:

~~~java
List<String> collected = names.stream()
    .map(String::toUpperCase)
    .toList();
~~~

`toList` creates an unmodifiable result list since JDK 16. If you need Java 8, you can use `collect(Collectors.toList())`, noting that the API does not guarantee the resulting list is mutable. If you genuinely need a mutable list, specify the supplier explicitly: `collect(Collectors.toCollection(ArrayList::new))`.

**Rule of thumb:** Consumer is useful for *side effects at program boundaries* (printing to screen, controlled I/O). When you want to produce values, prefer Function and a result-producing terminal operation.

## 6. Lambda, Method Reference, and Target Type

Functional interfaces define **type contracts**; lambdas or method references are ways of **providing behavior** that conforms to those contracts.

| Written as lambda | Written as method reference | Target type |
|---|---|---|
| `order -> order.paid()` | `Order::paid` | `Predicate<Order>` |
| `order -> order.customer()` | `Order::customer` | `Function<Order, String>` |
| `text -> text.length()` | `String::length` | `Function<String, Integer>` |
| `text -> System.out.println(text)` | `System.out::println` | `Consumer<String>` |

A method call can be used with different interfaces **if the parameter types and return type are compatible**. The compiler relies on the *target type* of the variable or method parameter to interpret the lambda.

~~~java
Predicate<String> isLong = text -> text.length() >= 5;
Function<String, Integer> length = String::length;
Consumer<Integer> printLength = System.out::println;

Stream.of("Java", "Kotlin")
    .filter(isLong)
    .map(length)
    .forEach(printLength); // Prints 6
~~~

In the example, `Predicate` filters out `Java` (4 characters), `Function` turns `Kotlin` into the number 6, and `Consumer` prints 6. If you accidentally assign `String::length` to `Predicate<String>`, the compiler will report an error because `length()` returns `int`, not `boolean`.

Lambdas can also *capture* variables from the enclosing scope, but a captured local variable must be **final or effectively final** (not reassigned):

~~~java
int minimumLength = 4;
Predicate<String> longEnough = value -> value.length() >= minimumLength;

// minimumLength = 6; // If uncommented, the lambda above will not compile.
~~~

This rule curbs certain state bugs, but it does not make every captured object immutable. For instance, capturing an `ArrayList` and adding elements from multiple threads still carries a race condition risk.

## 7. Lazy Pipeline: When Are the Three Functions Actually Called?

Building a pipeline with `filter` and `map` **does not necessarily invoke** `Predicate.test` or `Function.apply` right away. Most Stream intermediate operations are *lazy*. Work is performed when a terminal operation is invoked, and the Stream may process only as many elements as needed.

~~~java
import java.util.stream.Stream;

Stream<Integer> pipeline = Stream.of(-1, 2, 3)
    .filter(n -> {
        System.out.println("test " + n);
        return n > 0;
    })
    .map(n -> {
        System.out.println("apply " + n);
        return n * 2;
    });

System.out.println("Pipeline created");

pipeline.forEach(n -> System.out.println("accept " + n));
~~~

Output of this sequential pipeline:

~~~text
Pipeline created
test -1
test 2
apply 2
accept 4
test 3
apply 3
accept 6
~~~

Notice that **each element** can travel through multiple steps before the next element is processed; a Stream does not necessarily run all of `filter` and then all of `map` like two separate loops. Only the line "Pipeline created" appears before the terminal operation runs.

However, **you must not rely on the number of invocations or the invocation order of lambdas for business logic**. With stateful operations like `sorted`, with parallel Streams, with short-circuiting operations like `findFirst`, or when the JDK can optimize away unnecessary steps, the evaluation pattern may differ.

The following example illustrates a false assumption:

~~~java
long count = List.of("A", "B", "C").stream()
    .map(text -> {
        System.out.println("map: " + text);
        return text.toLowerCase();
    })
    .count();

System.out.println(count); // 3
~~~

Do not expect the three `map: ...` lines to always appear. With a sized source and a pipeline that does not change the element count, the implementation may compute `count` **without calling the mapper**. `map` should describe a value transformation, not be used as a mandatory place to emit logs, write data, or mutate state.

Once `forEach`, `count`, or `toList` finishes, the Stream has been consumed; to process the data again, create a **new Stream from the source** if that source supports re-traversal.

## 8. Rules for Designing Safe Predicates and Functions

Functions supplied to a pipeline should satisfy two main principles:

1. **Non-interfering:** do not modify the data source being traversed.
2. **Stateless:** the result of processing an element does not depend on external state that changes during traversal.

Example of what not to write:

~~~java
List<Integer> values = new java.util.ArrayList<>(List.of(1, 2, 3));

// Never modify the source while traversing it with a Stream.
values.stream().filter(n -> {
    values.remove(n);
    return n > 1;
}).toList();
~~~

Modifying the source can lead to `ConcurrentModificationException`, skipped elements, or unpredictable behavior depending on the source and processing mode. If you want to filter into a new list:

~~~java
List<Integer> remaining = values.stream()
    .filter(n -> n > 1)
    .toList();
~~~

If you want to update the collection itself, use an appropriate operation like `values.removeIf(n -> n <= 1)` outside a pipeline traversing the same collection.

A well-behaved Predicate checking the same input generally returns the same result when business conditions haven't changed. A well-behaved Function transforms based on its input without unintended side effects. This makes reuse in `parallelStream()` safer, though parallel execution still requires evaluating the overhead of splitting, combining, ordering, and resources.

### Handling Nulls and Exceptions

- `List.of(...)` does not accept `null` elements, but other Stream sources may contain `null`. A Predicate like `text -> text.isBlank()` will throw a `NullPointerException` if `text` is null.
- If the source might contain nulls, place an explicit condition before mapping:

~~~java
List<String> result = java.util.Arrays.asList("Java", null, "Go").stream()
    .filter(java.util.Objects::nonNull)
    .map(String::toUpperCase)
    .toList(); // [JAVA, GO]
~~~

- The primary methods `test`, `apply`, and `accept` do not declare checked exceptions. If a call inside a lambda throws a checked exception, you must handle it according to your application policy (handle in place, wrap with contextual exception, or separate I/O out of the pipeline). You should not "swallow" errors by silently returning an invalid fallback value.
- `map` can return `null`, but some terminal operations—for example `findFirst` when selecting a null—will throw an error. Define your null policy before building the pipeline.

## 9. Choosing the Right Function Type in Common Scenarios

| Task | Choose | Why |
|---|---|---|
| Keep only active accounts | `Predicate<Account>` + `filter` | Returns true/false; does not change element type |
| Convert `Account` to email | `Function<Account, String>` + `map` | Returns a new value; can change type |
| Sum character counts from a list of strings | `ToIntFunction<String>` + `mapToInt` + `sum` | Handles primitive `int` directly |
| Check whether any order is overdue | `Predicate<Order>` + `anyMatch` | Boolean result and can short-circuit |
| Group invoices by customer | `Function<Order, String>` + `groupingBy` | Computes grouping key from each element |
| Print each processed result | `Consumer<String>` + `forEach` | Produces an effect, returns no value |
| Create a `List` from transformed elements | `map` + `toList` or `collect` | Collects values via a terminal operation |

Function types are easy to confuse when variable names are unclear. Name them to express intent: `isPaid`, `hasValidEmail` for Predicate; `toSummary`, `extractId` for Function; `printLine`, `sendNotification` for Consumer. If a lambda is long, has multiple branches, and is hard to name, consider extracting it into a named method and using a method reference.

## 10. Practice Exercise with Solution

Given a list of product codes:

~~~java
List<String> rawCodes = List.of(" java ", "", "KOTLIN", " go ", "Java");
~~~

**Requirements:**

1. Drop empty or whitespace-only codes.
2. Normalize codes by trimming whitespace and converting to uppercase.
3. Remove duplicate codes.
4. Sort in natural order and print each code in the format `Code: ...`.
5. Give a separate named variable to each Predicate, Function, and Consumer.

**Reference Solution (JDK 17+):**

~~~java
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class BehaviorExercise {
    public static void main(String[] args) {
        List<String> rawCodes = List.of(" java ", "", "KOTLIN", " go ", "Java");

        Predicate<String> hasContent = code -> !code.isBlank();
        Function<String, String> normalize =
            code -> code.trim().toUpperCase(Locale.ROOT);
        Consumer<String> printCode =
            code -> System.out.println("Code: " + code);

        List<String> normalizedCodes = rawCodes.stream()
            .filter(hasContent)
            .map(normalize)
            .distinct()
            .sorted()
            .toList();

        normalizedCodes.forEach(printCode);
    }
}
~~~

Output:

~~~text
Code: GO
Code: JAVA
Code: KOTLIN
~~~

In this exercise, `hasContent` is a `Predicate<String>` because it returns `boolean`; `normalize` is a `Function<String, String>` because it returns the normalized string; `printCode` is a `Consumer<String>` because it only prints. `distinct` and `sorted` ensure the results are unique and ordered; `toList` terminates the Stream to produce the data before performing the print action.

**Self-Check Questions:**

1. If we remove `toList()` and write `...sorted().forEach(printCode)`, does the pipeline run? — **Yes**, `forEach` becomes the terminal operation.
2. Can `filter(hasContent)` change `Stream<String>` into `Stream<Integer>`? — **No**; use `map` to change types.
3. Does `Function<String, String>` automatically remove duplicate codes? — **No**; you need `distinct` or equivalent handling rules.
4. If we replace `stream()` with `parallelStream()` and use `forEach(printCode)`, is the print order guaranteed? — **No**; consider `forEachOrdered` for ordered sources, and handle side effects appropriately.
5. Should we write data to a database inside `map` just to trigger the write when `count` runs? — **No**; the mapper may not be called in some pipelines, and write side effects do not belong to the data-transformation contract.

## 11. Takeaways and Next Steps

Read the three function types as follows:

- **`Predicate<T>`:** *should we keep this value?* → `test` → `boolean`.
- **`Function<T, R>`:** *what should this value be transformed into?* → `apply` → `R`.
- **`Consumer<T>`:** *what should we do with this value?* → `accept` → `void`.

In the Java Stream API, they commonly correspond to `filter` → `map` → `forEach`, though they are not limited to these three methods: Predicate is also used for matching; Function is also used for grouping and mapping in collectors; Consumer is also used with `Optional` and other data-consuming operations.

As pipelines grow more complex, keep a clear grasp on **type contracts**, **lazy execution conditions**, **non-interference with the source**, and **the boundaries of side effects**. Mastering this will help you understand aggregation functions in `reduce` and `collect`, as well as stricter requirements in parallel processing, custom collectors, `Spliterator`, and Stream Gatherers.
