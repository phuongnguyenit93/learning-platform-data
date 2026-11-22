# Lambdas and Method References for Stream Operations

> **Chapter:** Behavioral Functions and Types  
> **Module:** JAVA_STREAM_API  
> **Focus:** Write, read, and choose lambdas or method references to pass behavior into Stream operations clearly, type-safely, and securely.

The Java Stream API lets you describe data processing declaratively: **which elements to select** with `filter`, **how to transform them** with `map`, **how to aggregate them** with `reduce` or `collect`. Those operations need to be supplied with *behavior*; in Java, behavior is commonly represented by a **lambda expression** or a **method reference** matching a *functional interface*.

This lesson focuses on how to write behavior, choose the right function type, and understand the impact of behavior on lazy pipelines. This is the foundation for learning grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers in the **JAVA_STREAM_API** module, as well as recognizing limits around state, resources, and performance.

## 1. Why Do Streams Accept Functions as Parameters?

Suppose we need to get the names of customers who have paid for orders of 100,000 VND or more:

```java
import java.util.List;

class LambdaIntro {
    record Order(String customer, long amount, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("An", 150_000, true),
            new Order("Bình", 70_000, true),
            new Order("Chi", 210_000, false),
            new Order("Dung", 180_000, true)
        );

        List<String> customers = orders.stream()
            .filter(order -> order.paid() && order.amount() >= 100_000)
            .map(Order::customer)
            .toList();

        System.out.println(customers); // [An, Dung]
    }
}
```

A pipeline consists of three roles:

1. **Source:** `orders.stream()` supplies each `Order` object.
2. **Intermediate operations:** `filter(...)` needs a function returning `boolean`; `map(...)` needs a function turning an `Order` into a `String`.
3. **Terminal operation:** `toList()` triggers pipeline evaluation to produce the resulting list.

`order -> order.paid() && order.amount() >= 100_000` is a **lambda**. `Order::customer` is a **method reference**. They are two ways of supplying behavior to the API, not two different kinds of pipelines.

In `filter(...)`, Java already knows what kind of behavior is required: an object implementing the `Predicate<Order>` interface. In `map(...)`, Java needs a behavior compatible with `Function<Order, String>`. That expected type is called the **target type**, and it explains why you do not need to declare the parameter type of `order` in most lambdas.

## 2. What Is a Lambda Expression?

A lambda is an expression representing the implementation of the single abstract method of a functional interface.

General syntax:

```java
(thamSo1, thamSo2) -> bieuThuc

(thamSo1, thamSo2) -> {
    // One or more statements
    return ketQua;
}
```

Examples of common forms:

```java
Predicate<String> nonBlank = s -> !s.isBlank();
Function<String, Integer> length = s -> s.length();
Consumer<String> printer = s -> System.out.println(s);
BinaryOperator<Integer> add = (a, b) -> a + b;

Predicate<String> longName = (String s) -> {
    String trimmed = s.trim();
    return trimmed.length() >= 3;
};
```

These examples require the corresponding imports from `java.util.function`; `String.isBlank()` has been available since Java 11.

| Syntax | Meaning |
| --- | --- |
| `s -> s.trim()` | Single parameter, body is an expression yielding a result. |
| `(s) -> s.trim()` | Equivalent, parameter enclosed in parentheses. |
| `(String s) -> s.trim()` | Explicit type declaration. |
| `(a, b) -> a + b` | Two parameters. |
| `() -> "default"` | No parameters. |
| `s -> { return s.trim(); }` | Block body; requires `return` when the target method returns a value. |

**Syntax note:** for multi-parameter lambdas, the parameters must be enclosed in parentheses. Do not mix explicitly typed parameters with type-inferred parameters in the same list; for example, `(String s, n) -> ...` is invalid.

### 2.1. A Lambda Needs a Target Type

A lambda does not have an independent type like `String` or `int`; Java interprets it in the context of a specific functional interface:

```java
Predicate<String> hasText = s -> !s.isBlank();
Function<String, Integer> countChars = s -> s.length();

boolean a = hasText.test("Java");   // true
int b = countChars.apply("Java");   // 4
```

The same syntax `s -> ...` implements different methods: `Predicate.test` or `Function.apply`.

The following example does not compile:

```java
// var operation = value -> value.trim(); // Error: lambda is missing a target type
```

You can supply the target type via a variable declaration, method parameter, cast, or an appropriate API call:

```java
Function<String, String> operation = value -> value.trim();

List<String> cleaned = List.of("  An  ", " Bình ").stream()
    .map(value -> value.trim()) // Target type is inferred from map
    .toList();
```

A lambda only implements a single abstract method according to the functional interface contract; the lambda expression itself is not a method call executed immediately.

## 3. Functional Interface: The Bridge Between Lambdas and Streams

A **functional interface** has exactly one abstract method to implement; it may still have `default` methods, `static` methods, or methods matching `Object`. The `@FunctionalInterface` annotation helps the compiler enforce this constraint.

Common types live in `java.util.function`:

| Type | Abstract method | Behavior shape | Usage examples |
| --- | --- | --- | --- |
| `Predicate<T>` | `boolean test(T t)` | `T → boolean` | `filter`, `anyMatch`, `allMatch` |
| `Function<T,R>` | `R apply(T t)` | `T → R` | `map`, `groupingBy` |
| `Consumer<T>` | `void accept(T t)` | `T → action` | `forEach`, `peek` |
| `Supplier<T>` | `T get()` | `() → T` | Supplying values or on-demand data sources |
| `UnaryOperator<T>` | `T apply(T t)` | `T → T` | `Stream.iterate`, same-type transformation |
| `BinaryOperator<T>` | `T apply(T a, T b)` | `(T,T) → T` | `reduce` |
| `Comparator<T>` | `int compare(T a, T b)` | `(T,T) → int` | `sorted`, `min`, `max` |
| `BiFunction<T,U,R>` | `R apply(T t, U u)` | `(T,U) → R` | Two-input accumulator in three-argument `reduce` |

`Comparator<T>` is in `java.util`; the remaining types in the table are in `java.util.function`.

There are also primitive variants to avoid boxing:

| Type | Purpose |
| --- | --- |
| `IntPredicate`, `LongPredicate`, `DoublePredicate` | Conditions on primitive values. |
| `IntFunction<R>` | Turns an `int` into `R`. |
| `ToIntFunction<T>`, `ToLongFunction<T>`, `ToDoubleFunction<T>` | Turns an object into a primitive value; used with `mapToInt`, `mapToLong`, `mapToDouble`. |
| `IntUnaryOperator`, `LongUnaryOperator`, `DoubleUnaryOperator` | Same-type primitive transformation. |
| `IntBinaryOperator`, `LongBinaryOperator`, `DoubleBinaryOperator` | Combines two primitive values of the same type. |
| `ObjIntConsumer<T>` and corresponding variants | Accepts an object and a primitive argument. |

Example:

```java
List<String> names = List.of("An", "Bình", "Chi");

Predicate<String> longEnough = name -> name.length() >= 3;
Function<String, String> normalize = String::trim;
ToIntFunction<String> nameLength = String::length;

List<String> selected = names.stream()
    .map(normalize)
    .filter(longEnough)
    .toList(); // [Bình, Chi]

int totalCharacters = names.stream()
    .mapToInt(nameLength)
    .sum(); // 9
```

With the given names, `"An"` has 2 characters, `"Bình"` has 4, and `"Chi"` has 3, so the sum is **9**. `String.length()` counts UTF-16 code units; for certain Unicode characters outside the BMP, this result does not equal the number of user-perceived characters.

### 3.1. Reading Stream Operation Signatures

Methods in `Stream<T>` have generic type signatures. For example, in abbreviated form:

```java
Stream<T> filter(Predicate<? super T> predicate);

<R> Stream<R> map(Function<? super T, ? extends R> mapper);

IntStream mapToInt(ToIntFunction<? super T> mapper);

boolean anyMatch(Predicate<? super T> predicate);

Optional<T> reduce(BinaryOperator<T> accumulator);

<R, A> R collect(Collector<? super T, A, R> collector);
```

Here `T` is the current element type; `R` is the output type after mapping. The `? super` and `? extends` clauses are wildcard variance bounds, allowing the API to accept functions with compatible input/output types instead of forcing exact matches.

For `Stream<Order>`, `filter` expects a condition taking an `Order`; `map` can turn elements into another type:

```java
List<Long> amounts = orders.stream()
    .filter(Order::paid)    // Predicate<Order>
    .map(Order::amount)     // Function<Order, Long>, involves boxing
    .toList();
```

If the goal is to compute a sum, using the primitive variant is more appropriate:

```java
long total = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amount) // ToLongFunction<Order>
    .sum();
```

These snippets use the `Order` type defined in section 1.

## 4. Method Reference: Referencing an Existing Method

A **method reference** uses the `::` syntax to represent a call to an existing method or constructor matching the target type. It shortens a lambda when the lambda merely forwards its parameters to an existing method.

Four key forms:

| Form | Method reference | Behaviorally equivalent lambda | Example target type |
| --- | --- | --- | --- |
| `static` method | `Integer::parseInt` | `s -> Integer.parseInt(s)` | `Function<String,Integer>` |
| Instance method of a specific object (*bound*) | `System.out::println` | `s -> System.out.println(s)` | `Consumer<String>` |
| Instance method of an incoming object (*unbound*) | `String::trim` | `s -> s.trim()` | `Function<String,String>` |
| Constructor | `ArrayList::new` | `() -> new ArrayList<>()` | `Supplier<ArrayList<String>>` |

Example:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

class MethodReferenceKinds {
    public static void main(String[] args) {
        Function<String, Integer> parse = Integer::parseInt;
        Function<String, String> trim = String::trim;
        Consumer<String> print = System.out::println;
        Supplier<ArrayList<String>> factory = ArrayList::new;

        List<Integer> nums = List.of(" 10 ", " 20 ").stream()
            .map(trim)
            .map(parse)
            .toList();

        ArrayList<String> output = factory.get();
        output.add("OK");

        nums.forEach(n -> print.accept(String.valueOf(n)));
        System.out.println(output); // [OK]
    }
}
```

`String::trim` does not create a `String` object ahead of time: each incoming value becomes the **receiver** when `trim()` is called. By contrast, `System.out::println` references a method on a specific `PrintStream` object.

### 4.1. Looking at Signatures to Understand Zero-Parameter and Multi-Parameter Method References

`String::length` looks like it takes no parameters because `length()` declares no parameters. Yet with target type `Function<String,Integer>`, the incoming `String` is the receiver:

```java
Function<String, Integer> length = String::length;
int n = length.apply("Stream"); // 6
```

An unbound method reference can also accept additional method arguments:

```java
BiPredicate<String, String> startsWith = String::startsWith;

boolean ok = startsWith.test("stream-api", "stream"); // true
```

Here the first parameter of `BiPredicate` is the receiver, and the second parameter is the argument to `String.startsWith(String prefix)`.

### 4.2. Constructor References and Array Constructor References

Constructor references are commonly used when creating output collections or new objects:

```java
Supplier<List<String>> listFactory = ArrayList::new;
List<String> list = listFactory.get();

IntFunction<String[]> arrayFactory = String[]::new;
String[] array = arrayFactory.apply(3); // Length 3
```

`ArrayList::new` is compatible with various target types if a matching constructor exists; `String[]::new` needs a length, so it accepts an `int` via `IntFunction<String[]>`.

In a collector:

```java
ArrayList<String> result = Stream.of(" An ", " Bình ")
    .map(String::trim)
    .collect(Collectors.toCollection(ArrayList::new));
```

`Collectors.toCollection` takes a `Supplier` to create the accumulation collection, which fits a constructor reference well.

### 4.3. When Is a Method Reference Not Appropriate?

A method reference is only concise when the intent can be read directly from the method name. A lambda is clearer if you need to combine conditions, transform arguments, catch exceptions, or express multi-step logic:

```java
.filter(order -> order.paid() && order.amount() > 100_000)

.map(name -> name.trim().toUpperCase())

.sorted((left, right) ->
    Integer.compare(left.length(), right.length()))
```

Do not force yourself to create an extra helper method just to replace every lambda with a method reference. If a method reference becomes confusing due to overloads or generic type inference, an explicit lambda can be easier to maintain.

## 5. Applying Lambdas and Method References to Each Operation

### 5.1. `filter`: Selecting Elements with `Predicate<T>`

`filter` keeps an element when the condition returns `true`:

```java
List<String> names = List.of("An", "", " Bình ", "Chi");

List<String> valid = names.stream()
    .map(String::trim)
    .filter(name -> !name.isEmpty())
    .toList();

// [An, Bình, Chi]
```

If a checking method already exists, you can reference it directly:

```java
List<String> nonEmpty = names.stream()
    .filter(Predicate.not(String::isBlank)) // Java 11+
    .toList();
```

`Predicate` also supports combining conditions with `and`, `or`, and `negate`:

```java
Predicate<String> hasLength = name -> name.length() >= 3;
Predicate<String> beginsWithB = name -> name.startsWith("B");

Predicate<String> selected = hasLength.and(beginsWithB);

boolean b = selected.test("Bình"); // true
```

This combination uses short-circuit semantics similar to `&&` and `||`. Consider condition ordering when evaluations have different costs.

### 5.2. `map` and `flatMap`: Transforming with `Function`

`map` takes each element and returns one result:

```java
List<String> ids = List.of(" A01 ", " B02 ");

List<String> normalized = ids.stream()
    .map(String::trim)
    .map(String::toLowerCase)
    .toList(); // [a01, b02]
```

`flatMap` needs a function whose output is a Stream in order to flatten:

```java
List<List<String>> teams = List.of(
    List.of("An", "Bình"),
    List.of("Chi")
);

List<String> members = teams.stream()
    .flatMap(List::stream)
    .toList(); // [An, Bình, Chi]
```

With `Stream<List<String>>`, `List::stream` is the method reference corresponding to `team -> team.stream()`. Each list produces a sub-stream; `flatMap` merges them into `Stream<String>`.

### 5.3. `sorted`, `min`, and `max`: Comparing with `Comparator<T>`

When sorting by name length, you can write:

```java
List<String> sorted = List.of("Bình", "An", "Chi").stream()
    .sorted((a, b) -> Integer.compare(a.length(), b.length()))
    .toList(); // [An, Chi, Bình]
```

A clearer way to express intent is:

```java
List<String> sorted = List.of("Bình", "An", "Chi").stream()
    .sorted(Comparator.comparingInt(String::length))
    .toList(); // [An, Chi, Bình]
```

`Comparator.comparingInt` takes a `ToIntFunction<String>`, so `String::length` acts as the integer key extractor for comparison. With business objects:

```java
Comparator<Order> byAmountDescending =
    Comparator.comparingLong(Order::amount).reversed();

List<Order> expensiveFirst = orders.stream()
    .sorted(byAmountDescending)
    .toList();
```

If a secondary sort order is needed:

```java
Comparator<Order> byAmountThenName = Comparator
    .comparingLong(Order::amount)
    .thenComparing(Order::customer);
```

When using `sorted`, be mindful of buffering/sorting cost; on an unbounded source, a global sort operation may never produce a result.

### 5.4. `reduce`: Aggregating with `BinaryOperator<T>`

Two-argument `reduce` takes an **identity** and a combining function:

```java
int sum = Stream.of(10, 20, 30)
    .reduce(0, Integer::sum); // 60
```

`Integer::sum` is equivalent to `(left, right) -> left + right` and matches `BinaryOperator<Integer>`. `0` is the identity for addition.

Not every two-parameter lambda is suitable for `reduce`. The combining operation must be **associative** so it yields the correct result regardless of how computation is grouped. Subtraction does not satisfy this requirement:

```java
// Not suitable as a general reduce operation, especially in parallel:
int value = Stream.of(10, 3, 2)
    .reduce(0, (a, b) -> a - b);
```

Grouping order can change the result of subtraction. For numeric data when computing a sum, use `sum` or `Integer::sum`.

### 5.5. `collect`: Passing Functions to a Collector

Collectors also require behavior, such as a grouping classifier and an amount extractor:

```java
Map<String, Long> revenueByCustomer = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::customer,
        Collectors.summingLong(Order::amount)
    ));
```

In the example:

- `Order::paid` is a `Predicate<Order>` condition.
- `Order::customer` is a `Function<Order,String>` classifier.
- `Order::amount` is used by `summingLong` as a `ToLongFunction<Order>`.

`Collectors.toMap` can also accept a `BinaryOperator` to resolve duplicate keys:

```java
Map<String, Long> maxOrderByCustomer = orders.stream()
    .collect(Collectors.toMap(
        Order::customer,
        Order::amount,
        Long::max
    ));
```

If you omit the merge function and two elements produce the same key, two-argument `toMap` throws `IllegalStateException`. Choose a merge function based on data rules: summing, picking the maximum, or choosing the preferred record.

### 5.6. `forEach` and `peek`: Acting with `Consumer<T>`

`forEach` accepts a `Consumer<T>`, commonly seen with printing:

```java
Stream.of("An", "Bình").forEach(System.out::println);
```

`peek` is an intermediate operation, typically used to observe processing during debugging:

```java
List<Integer> doubled = Stream.of(1, 2, 3)
    .peek(n -> System.out.println("Saw: " + n))
    .map(n -> n * 2)
    .toList();
```

Do not use `peek` to update business data or count elements as a required step: Streams are lazy and some terminal operations can optimize away element traversal. `forEach` on a parallel Stream also does not guarantee encounter order; when order must be preserved, consider `forEachOrdered`.

## 6. Reusing and Composing Defined Functions

You can extract processing rules into explicitly typed variables to reuse them multiple times:

```java
Predicate<String> isUseful = Predicate.not(String::isBlank);
Function<String, String> trim = String::trim;
Function<String, String> upper = String::toUpperCase;

List<String> result = Stream.of("  java ", "", " stream ")
    .map(trim)
    .filter(isUseful)
    .map(upper)
    .toList(); // [JAVA, STREAM]
```

`Function` provides two important composition methods:

- `f.andThen(g)`: executes `f` first, then `g`.
- `f.compose(g)`: executes `g` first, then `f`.

```java
Function<String, String> trim = String::trim;
Function<String, String> upper = String::toUpperCase;

Function<String, String> normalize = trim.andThen(upper);

String a = normalize.apply("  java "); // JAVA
String b = upper.compose(trim).apply("  java "); // JAVA
```

For `Predicate`, `and`, `or`, and `negate` help express complex rules as individually testable conditions.

**Note:** an extracted function must have a type compatible with where it is used. For example, `Predicate<Object>` can accept a `String` if the check only needs `Object`, whereas `Predicate<Integer>` is not compatible with a `Stream<String>`.

## 7. External Variables in Lambdas and the Effectively Final Rule

A lambda can use local variables from the enclosing scope if the variable is declared `final` or is **effectively final** (never reassigned after initialization):

```java
long minimum = 100_000;

List<Order> chosen = orders.stream()
    .filter(order -> order.amount() >= minimum)
    .toList();
```

Even without the `final` keyword, `minimum` is effectively final. Invalid example:

```java
long minimum = 100_000;
minimum = 200_000;

// Compile error: variable minimum is no longer effectively final.
// List<Order> chosen = orders.stream()
//     .filter(order -> order.amount() >= minimum)
//     .toList();
```

**Distinguish variables from objects:** not reassigning a reference variable does not mean the referenced object is immutable. The following compiles, yet it is a dangerous design:

```java
List<String> output = new ArrayList<>();

names.stream().forEach(output::add); // Compiles, but uses external mutable state.
```

Especially with `parallelStream()`, `ArrayList` is not safe for concurrent additions from multiple threads. Express accumulation with `toList()` or `collect(...)` instead:

```java
List<String> output = names.stream()
    .filter(Predicate.not(String::isBlank))
    .toList();
```

A lambda can also read/write fields of external objects, but **syntactic validity does not guarantee thread safety** or compliance with non-interference. When running a pipeline, avoid mutating the source being traversed and avoid relying on shared mutable state.

### 7.1. Lambdas Do Not Guarantee When They Execute

`filter`, `map`, and many intermediate operations are lazy:

```java
Stream<String> pipeline = Stream.of("An", "Bình")
    .map(value -> {
        System.out.println("Mapping: " + value);
        return value.toUpperCase();
    });

System.out.println("Configured");
List<String> result = pipeline.toList();
```

Here `Configured` is printed before the `map` lambda runs; `toList()` triggers evaluation. With `findFirst` or `anyMatch`, only part of the source may need to pass through the lambda. Some terminal operations can also apply optimizations that avoid traversing elements altogether.

Therefore, lambdas in intermediate operations should describe **computations**, not hide essential side effects that the program requires to happen.

## 8. Method References, Overloads, and Type Inference

The compiler selects the referenced method based on the target type, parameter count, and compatible return type. An overloaded method name can still be used with `::` if the context is unambiguous:

```java
Function<String, Integer> parse = Integer::valueOf;
int n = parse.apply("42");
```

Similarly, `System.out::println` has many overloads, but `Consumer<String>` tells the compiler it needs the overload taking one `String`.

When the compiler lacks sufficient information to pick a method, declare the functional interface explicitly or use an explicit lambda:

```java
Function<String, Integer> converter = text -> Integer.parseInt(text);
```

Do not add casts merely to save a few characters. Naming variables after business intent usually makes the code much easier to read.

### 8.1. A Nuance with Bound References

With a bound method reference of the form `obj::method`, **the receiver expression `obj` is evaluated when the method reference is created**, even though the method invocation itself may happen later.

```java
String prefix = "ID-";
Function<String, String> addPrefix = prefix::concat;

String id = addPrefix.apply("123"); // ID-123
```

Compare this with the unbound form `String::concat`: it requires two values (receiver and argument):

```java
BinaryOperator<String> join = String::concat;

String result = join.apply("ID-", "123"); // ID-123
```

If the receiver of a bound method reference is `null`, creating the reference can throw a `NullPointerException` immediately at evaluation time. With a lambda `x -> obj.method(x)`, accessing `obj` happens inside the lambda body when the lambda is called. This is a semantic difference when handling potentially null values.

## 9. Lambdas and Exceptions

Standard functional interfaces like `Function` and `Predicate` **do not declare checked exceptions** on their abstract methods. Because of this, you cannot directly pass a lambda calling a method that throws `IOException` without handling the exception:

```java
// Does not compile because IOException is a checked exception:
//
// List<String> contents = paths.stream()
//     .map(path -> Files.readString(path))
//     .toList();
```

One approach is to wrap the I/O error into an `UncheckedIOException` while preserving the cause:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

class ReadFilesExample {
    public static void main(String[] args) {
        List<Path> paths = List.of(Path.of("a.txt"), Path.of("b.txt"));

        List<String> contents = paths.stream()
            .map(path -> {
                try {
                    return Files.readString(path);
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            })
            .toList();

        System.out.println(contents.size());
    }
}
```

The example assumes the files exist. In real systems, you must decide on an error policy: abort the entire pipeline, record per-element errors, or return a result type holding errors. Do not swallow exceptions to make invalid data appear valid.

When a Stream is backed by a resource such as `Files.lines(path)`, manage its lifecycle with `try-with-resources`. Method references and lambdas do not automatically release resources outside the API's management scope.

## 10. Complete Example: A Pipeline Using Multiple Function Types

Problem: given a list of orders, normalize customer names, filter paid orders with positive amounts, compute revenue per customer, and list names in descending order of revenue.

Java 17+ example; save in `BehavioralFunctionsDemo.java`:

```java
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class BehavioralFunctionsDemo {
    record Order(String customer, long amount, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order(" An ",   150_000, true),
            new Order("Bình",    75_000, true),
            new Order("An",      90_000, true),
            new Order("Chi",    220_000, false),
            new Order("Dung",    -5_000, true)
        );

        Predicate<Order> valid = order ->
            order.paid() && order.amount() > 0;

        Function<String, String> normalizeName = String::trim;

        Map<String, Long> revenue = orders.stream()
            .filter(valid)
            .collect(Collectors.groupingBy(
                order -> normalizeName.apply(order.customer()),
                Collectors.summingLong(Order::amount)
            ));

        Comparator<Map.Entry<String, Long>> byRevenueDesc =
            Map.Entry.<String, Long>comparingByValue()
                .reversed()
                .thenComparing(Map.Entry.comparingByKey());

        LinkedHashMap<String, Long> ranked = revenue.entrySet().stream()
            .sorted(byRevenueDesc)
            .collect(Collectors.toMap(
                Map.Entry::getKey,
                Map.Entry::getValue,
                (left, right) -> left,
                LinkedHashMap::new
            ));

        System.out.println(ranked);
        // {An=240000, Bình=75000}
    }
}
```

Analysis:

| Code snippet | Function type | Role |
| --- | --- | --- |
| `order -> order.paid() && order.amount() > 0` | `Predicate<Order>` | Identifies valid orders. |
| `String::trim` | `Function<String,String>` | Normalizes names during grouping. |
| `order -> normalizeName.apply(order.customer())` | `Function<Order,String>` | Extracts normalized grouping key. |
| `Order::amount` | `ToLongFunction<Order>` | Extracts amount for `summingLong`. |
| `Map.Entry.comparingByValue()` and `thenComparing(...)` | `Comparator<Map.Entry<...>>` | Ranks revenue; ties broken by name. |
| `Map.Entry::getKey`, `Map.Entry::getValue` | `Function` | Transfers entries back into a map. |
| `(left, right) -> left` | `BinaryOperator<Long>` | Merge function if duplicate keys arise in `toMap`. |
| `LinkedHashMap::new` | `Supplier<LinkedHashMap<...>>` | Preserves insertion order into the map. |

In this problem, every key in `revenue` is already unique, so the merge function in `toMap` never has to resolve a collision. `LinkedHashMap` preserves the order produced by `sorted`, so the printed order reflects the ranking.

### 10.1. What Happens If We Want to Run in Parallel?

You can change `orders.stream()` to `orders.parallelStream()` to use parallel execution. However:

- `valid` and `normalizeName` must hold no mutable state and not depend on invocation order.
- `groupingBy` can incur map coordination overhead when run in parallel; actual speedup depends on data size and group count.
- `sorted` must establish result ordering and often carries significant overhead.
- Do not use an external `ArrayList` variable and add elements via `forEach` from multiple threads.
- Choose parallel execution only after benchmarking on realistic workloads and understanding source/collector characteristics.

These same rules apply when writing custom collectors, leveraging `Spliterator`, or using Stream Gatherers to build more powerful intermediate operations: correctness of behavioral functions matters far more than saving a few characters when writing a lambda.

## 11. Common Mistakes and Fixes

| Mistake | Why it fails | Fix |
| --- | --- | --- |
| Writing `var f = x -> ...` | Lambda lacks a target type. | Declare `Function<T,R>` or the appropriate function type. |
| Passing `name -> name.length()` to `filter` | `filter` requires `boolean`, while `length()` returns `int`. | Use `name -> name.length() > 0`. |
| Using `map` when sub-lists need flattening | Result remains `Stream<List<T>>`. | Use `flatMap(List::stream)`. |
| Choosing `Function<Order,Long>` for large sums without needing boxing | Boxing adds overhead. | Use `ToLongFunction<Order>` and `mapToLong`. |
| Using `peek` for mandatory side effects | Pipeline may short-circuit or optimize away traversal. | Use a terminal operation or separate explicit business actions. |
| Passing `(a,b) -> a-b` to `reduce` | Subtraction is not associative. | Choose an associative operation and proper identity. |
| Using a shared mutable list in `parallelStream` | Easily causes race conditions or lost data. | Use an appropriate collector. |
| Using overly cryptic method references | Overloads or type inference obscure intent. | Write a lambda with clear parameter names and logic. |
| Not handling checked exceptions | `Function.apply` does not declare `IOException`. | Handle exceptions inside the lambda or build an abstraction with an error policy. |
| Assuming every Stream can be reused | A Stream instance can be consumed only once. | Create a new Stream from a re-traversable source. |

## 12. Check Your Understanding

1. Why is `filter(String::isBlank)` valid, while `filter(String::length)` is not?
2. Is `String::trim` a bound or unbound method reference? What role does the parameter of `Function<String,String>` play?
3. When should you use `mapToLong(Order::amount)` instead of `map(Order::amount)`?
4. Why is `(a,b) -> a-b` unsuitable for parallel `reduce`?
5. In `Collectors.groupingBy(Order::customer, Collectors.summingLong(Order::amount))`, which two target types do the two method references need?
6. Why must a local variable captured by a lambda be effectively final, yet the object referenced by that variable can still be mutable?
7. If a method reference is hard to read because of an overloaded method, what syntax can replace it?
8. Why does a `map` lambda usually not execute immediately when `map(...)` is called?

**Quick check:** (1) `filter` requires a `Predicate<String>` returning `boolean`; (2) unbound, the parameter is the receiver; (3) when you need a primitive `long` stream for efficient numeric processing; (4) subtraction is not associative; (5) `Function<Order,String>` and `ToLongFunction<Order>`; (6) the capture rule restricts reassigning the variable, not making the object immutable; (7) an explicit lambda; (8) Stream intermediate operations are typically lazy.

## 13. Key Takeaways

- **Lambdas** are a concise way to write behavioral implementations, inferred from the functional interface expected by the API.
- **Method references** reuse existing methods/constructors when signatures match the target type; they shorten code as long as intent stays clear.
- **`Predicate`, `Function`, `Consumer`, `Supplier`, `Comparator`, and `BinaryOperator`** are the core function types in the Stream API. Understanding target types helps pick the right behavior for each operation.
- **Primitive variants** such as `ToLongFunction` and `IntUnaryOperator` avoid unnecessary boxing and match the APIs of `IntStream`, `LongStream`, and `DoubleStream`.
- **Lambdas in lazy pipelines** may run deferred, partially, or be optimized away in some cases; do not put essential side effects inside intermediate operations.
- **Associativity, non-interference, and avoiding shared mutable state** are critical requirements when moving from simple pipelines to `reduce`, `collect`, parallel processing, custom collectors, and Gatherers.
