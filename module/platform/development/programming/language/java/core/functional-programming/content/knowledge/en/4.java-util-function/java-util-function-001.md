# `Function<T, R>`: transforming an input into a result in Java

## 1. Idea and use cases

In Java, `java.util.function.Function<T, R>` represents **a transformation**: it takes **a value of type `T`** and returns **a value of type `R`**. It is a *functional interface* with a single abstract method `R apply(T input)`. You can pass a function as a value, store it in a variable, pass it to another method, or combine multiple functions to build a pipeline.

For example:

- Take a `String` representing a username and return a normalized `String`.
- Take an `Order` and return a `BigDecimal` representing the order total.
- Take an `Order` and return an `OrderView` for display.
- Take a `String` and return an `Integer` representing the string length or a parsed number.
- Pass a transformation into `Stream.map(...)`, `Optional.map(...)`, or a reusable utility method.

You can visualize it as:

```text
T (input data)   ──[ Function<T, R> / apply ]──> R (result)
Order            ──[ compute total ]───────────> BigDecimal
String           ──[ normalize code ]──────────> String
Order            ──[ build display data ]──────> OrderView
```

**Distinguishing three operations:** `filter` decides **whether to keep or drop** an element according to a `Predicate<T>`; `map` uses `Function<T,R>` to **transform one element into one result**; `forEach` typically uses `Consumer<T>` to perform an action that returns no value. The fact that `Function` takes one input does not mean every pipeline must keep the same data type: `T` and `R` can be different.

## 2. Reading the `Function<T, R>` type signature

`Function` resides in the `java.util.function` package:

```java
import java.util.function.Function;

Function<String, Integer> length = text -> text.length();
int size = length.apply("Java"); // 4
```

The snippet above is code placed inside a method or in `jshell`. Explanation:

| Component | Meaning |
| --- | --- |
| `T` | Input type (*input*) of the function |
| `R` | Output type (*result*) of the function |
| `apply(T t)` | Executes the transformation; returns a result of type `R` |
| `text -> text.length()` | Lambda representing the transformation `String → Integer` |
| `Function<String, Integer>` | Type contract that helps the compiler catch returning the wrong type |
| `Function<String, String>` | Transforms one string into another string; `T` and `R` can be the same type |

When writing `Function<String, Integer> length`, the return value of `apply` has type `Integer`. Assigning it to an `int` variable uses automatic **unboxing**. Generics cannot accept primitive types directly, so `Function<String, int>` is a syntax error; use `Integer` or the specialized interfaces introduced below.

### `@FunctionalInterface` and lambdas

Conceptually, `Function` is equivalent to an interface with the following core contract:

```java
@FunctionalInterface
interface Converter<T, R> {
    R apply(T value);
}
```

This is a **custom interface for illustration**; you do not need to create it when using `java.util.function.Function`. A functional interface has **one abstract method**, so the compiler can turn a lambda or method reference into an instance that satisfies that interface. `default`/`static` methods on the interface do not break its functional interface status.

Example of the same transformation in three representations:

```java
Function<String, Integer> viaLambda = s -> s.length();
Function<String, Integer> viaReference = String::length;
Function<String, Integer> viaAnonymous = new Function<>() {
    @Override
    public Integer apply(String s) {
        return s.length();
    }
};
```

All three return `4` when calling `apply("Java")`. Lambdas and method references are usually concise and express the **conversion intent** more clearly than an anonymous class with verbose surrounding syntax.

## 3. Four operations to know: `apply`, `andThen`, `compose`, `identity`

| Operation | Effect | Execution order |
| --- | --- | --- |
| `f.apply(x)` | Directly transforms the input | Runs `f` |
| `f.andThen(g)` | Creates a function feeding the output of `f` into the input of `g` | `g(f(x))`: **f first, g second** |
| `f.compose(g)` | Creates a function letting `g` process the input before calling `f` | `f(g(x))`: **g first, f second** |
| `Function.identity()` | Creates a function returning the input value unchanged | `x -> x` |

Suppose we want to normalize a product code by stripping leading/trailing whitespace and then converting to uppercase using `Locale.ROOT`:

```java
Function<String, String> trim = String::trim;
Function<String, String> upper =
        value -> value.toUpperCase(java.util.Locale.ROOT);

Function<String, String> firstTrimThenUpper = trim.andThen(upper);
Function<String, String> upperAfterTrim = upper.compose(trim);

System.out.println(firstTrimThenUpper.apply("  book  ")); // BOOK
System.out.println(upperAfterTrim.apply("  book  "));     // BOOK
```

The two composed functions above are equivalent because both have the order **trim → upper**. Conversely, `trim.compose(upper)` executes **upper → trim**. For uppercasing and trimming whitespace, both orders may yield the same result in a simple example; for order-dependent transformations (such as "multiply by two" and "add three"), the results can differ significantly.

Example demonstrating **non-commutativity**:

```java
Function<Integer, Integer> doubleIt = x -> x * 2;
Function<Integer, Integer> plusThree = x -> x + 3;

System.out.println(doubleIt.andThen(plusThree).apply(4)); // 11
System.out.println(doubleIt.compose(plusThree).apply(4)); // 14
```

- `andThen`: `4 × 2 + 3 = 11`.
- `compose`: `(4 + 3) × 2 = 14`.

Here `andThen`/`compose` **return a new `Function`**; they do not immediately run on data. The transformation only runs when `apply` is called or when another API invokes that function.

### Type requirements when composing functions

For `f.andThen(g)` to be valid, **the result of `f` must be usable as the input to `g`**. For example:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, String> label = n -> "Quantity = " + n;
Function<String, String> parseThenLabel = parse.andThen(label);
System.out.println(parseThenLabel.apply("7")); // Quantity = 7
```

`String → Integer → String` is valid. If you try to compose `parse.andThen(String::trim)`, the compiler cannot turn `Integer` into the `String` input for `trim`. Generic type-checking rules catch this error at compile time.

The `before`/`after` argument passed to `compose`/`andThen` must not be `null`; if it is `null`, creating the composed function can throw `NullPointerException`. As for whether the input to `apply` accepts `null`, that **depends on the function implementation**: for example, `String::length` will fail if given `null`.

### What does `identity()` mean?

`Function.identity()` creates a mapping that preserves the value as-is:

```java
Function<String, String> keep = Function.identity();
System.out.println(keep.apply("A01")); // A01
```

It is commonly used when an API requires a mapper but you want to keep the element itself. For example, `Collectors.toMap(Order::id, Function.identity())` (where `Order` is the domain type and order IDs are unique) creates a map `id → the Order itself`. **Identity does not copy the object or make it immutable**: for reference types, it returns the exact reference passed in.

## 4. Complete Java 17 example: from orders to display data

Problem: we have orders, each consisting of several product lines. We want to define small transformations and then **combine them** to build display result strings. The transformations do not mutate the input data.

Create the file **`FunctionTransformDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Locale;
import java.util.function.Function;

public class FunctionTransformDemo {
    record Line(String sku, int quantity, BigDecimal unitPrice) {}

    record Order(String id, List<Line> lines) {
        Order {
            lines = List.copyOf(lines);
        }
    }

    record OrderView(String id, BigDecimal total) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A01", List.of(
                        new Line("BOOK", 2, new BigDecimal("120000")),
                        new Line("PEN", 3, new BigDecimal("10000"))
                )),
                new Order("A02", List.of(
                        new Line("BAG", 1, new BigDecimal("200000"))
                )),
                new Order("A03", List.of(
                        new Line("PEN", 5, new BigDecimal("10000"))
                ))
        );

        // Each transformation expresses exactly one task.
        Function<Line, BigDecimal> lineAmount =
                line -> line.unitPrice()
                        .multiply(BigDecimal.valueOf(line.quantity()));

        Function<Order, BigDecimal> orderTotal =
                order -> order.lines().stream()
                        .map(lineAmount)
                        .reduce(BigDecimal.ZERO, BigDecimal::add);

        Function<Order, OrderView> toView =
                order -> new OrderView(order.id(), orderTotal.apply(order));

        Function<OrderView, String> format =
                view -> view.id() + " = " + view.total().toPlainString();

        // Order -> OrderView -> String.
        Function<Order, String> show = toView.andThen(format);

        System.out.println("Order lines:");
        orders.stream()
                .map(show)
                .forEach(System.out::println);

        BigDecimal revenue = orders.stream()
                .map(orderTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("Total = " + revenue.toPlainString());

        Function<String, String> trim = String::trim;
        Function<String, String> upper =
                value -> value.toUpperCase(Locale.ROOT);

        Function<String, String> normalize = trim.andThen(upper);
        Function<String, String> sameByCompose = upper.compose(trim);
        Function<String, Integer> normalizedLength =
                normalize.andThen(String::length);

        System.out.println("Code = " + normalize.apply("  book  "));
        System.out.println("Length = "
                + normalizedLength.apply("  book  "));
        System.out.println("Compose = "
                + sameByCompose.apply("  book  "));

        Function<String, Integer> parse = Integer::parseInt;
        Function<Integer, String> label = n -> "Quantity = " + n;
        System.out.println(parse.andThen(label).apply("7"));

        Function<Order, Order> identity = Function.identity();
        System.out.println("Same object = "
                + (identity.apply(orders.get(0)) == orders.get(0)));
    }
}
```

Run with JDK 17 or later:

```bash
javac --release 17 FunctionTransformDemo.java
java FunctionTransformDemo
```

**Exact stdout**:

```text
Order lines:
A01 = 270000
A02 = 200000
A03 = 50000
Total = 520000
Code = BOOK
Length = 4
Compose = BOOK
Quantity = 7
Same object = true
```

Arithmetic check:

- A01: `2 × 120000 + 3 × 10000 = 270000`.
- A02: `1 × 200000 = 200000`.
- A03: `5 × 10000 = 50000`.
- Total: `270000 + 200000 + 50000 = 520000`.

`List.of` preserves element order as written in the sample; `orders.stream()` is an ordered stream, and `forEach` on this sequential stream prints in traversal order. If you switch the example to `parallelStream().forEach(...)`, the print order is no longer guaranteed; to preserve *encounter order*, use `forEachOrdered` or collect before printing.

## 5. Breaking down the transformations in the example

### `Function<Line, BigDecimal>` — a line item to line amount

```java
Function<Line, BigDecimal> lineAmount =
        line -> line.unitPrice().multiply(
                BigDecimal.valueOf(line.quantity()));
```

The input is `Line`; the output is `BigDecimal`. The function only reads the components and creates a new monetary amount object. Because we are handling money, `BigDecimal` is more suitable than `double` to avoid binary floating-point representation errors. In production code, you also need to validate quantity, unit price, taxes, fees, rounding, and business refund rules.

### `Function<Order, BigDecimal>` — an entire order to total amount

```java
Function<Order, BigDecimal> orderTotal =
        order -> order.lines().stream()
                .map(lineAmount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
```

`map(lineAmount)` converts each `Line` into a `BigDecimal`. `reduce` sums the line amounts. For an order with an empty list of lines, `reduce` starts and ends at `BigDecimal.ZERO`. All aggregation logic lives inside one `Order → BigDecimal` function, so the same capability can be reused for multiple purposes: building `OrderView` or computing revenue.

### `Function<Order, OrderView>` — creating a new display value

```java
Function<Order, OrderView> toView =
        order -> new OrderView(order.id(), orderTotal.apply(order));
```

The output type is **different** from the input. `OrderView` is a record storing the order ID and total amount, without needing to modify `Order` or add a "cachedTotal" field to the domain object. In the example, `Order` copies the list structure with `List.copyOf` to prevent unintended modification; the `Line` component is a record with immutable data types.

### `andThen` — combining conversion and formatting

```java
Function<Order, String> show = toView.andThen(format);
String first = show.apply(orders.get(0)); // "A01 = 270000"
```

`toView` creates an `OrderView`, and `format` takes the `OrderView` and produces a string. By composing functions, calling code does not need to repeat both steps manually. `show.apply(order)` is equivalent in meaning to `format.apply(toView.apply(order))`.

### `Stream.map` — applying a Function to each element

```java
orders.stream()
        .map(show)
        .forEach(System.out::println);
```

`Stream.map` has the conceptual form `Stream<T> → Stream<R>`; with `orders` above, `T = Order` and `R = String`. Each input element produces one output element in `map`, even when the output value may be `null` (if the mapper returns `null`; subsequent steps might not support it).

`map` is an **intermediate operation** and executes lazily: it does not traverse or transform data until there is a terminal operation such as `toList`, `reduce`, `collect`, or `forEach`. A stream should only be consumed once; the example intentionally calls a fresh `orders.stream()` for the revenue report.

## 6. Comparing `Function` with its closest functional interfaces

All reside in or relate to the `java.util.function` package:

| Interface | Core contract | When to use |
| --- | --- | --- |
| `Function<T,R>` | `R apply(T)` | Transform **one input** into **one result** |
| `Predicate<T>` | `boolean test(T)` | True/false decision, commonly passed to `filter` |
| `Consumer<T>` | `void accept(T)` | Take a value and perform an action, e.g. print/log |
| `Supplier<T>` | `T get()` | Supply a value **with no input** |
| `BiFunction<T,U,R>` | `R apply(T,U)` | Two inputs to compute one result |
| `UnaryOperator<T>` | Extends `Function<T,T>` | Transformation that preserves the **type** |
| `BinaryOperator<T>` | Extends `BiFunction<T,T,T>` | Combine two values of the same type into a value of the same type |

Illustrative snippets **not a standalone program**:

```java
Predicate<String> notBlank = s -> !s.isBlank();
Consumer<String> printer = System.out::println;
Supplier<String> defaultCode = () -> "UNKNOWN";
BiFunction<Integer, Integer, Integer> sum = Integer::sum;
UnaryOperator<String> trim = String::trim;
```

These declarations require `import java.util.function.*;` or importing each interface inside a class/method. When you need a `boolean` value representing a condition, `Predicate<T>` communicates intent more clearly than `Function<T, Boolean>`. When you need a side effect with no result, `Consumer<T>` is clearer than a `Function<T,Void>` that must return `null`.

For primitive inputs/outputs and large data volumes, you can use specialized interfaces to reduce boxing/unboxing:

- `IntFunction<R>`: takes `int`, returns `R`.
- `ToIntFunction<T>`: takes `T`, returns `int`; for example `String::length`.
- `IntUnaryOperator`: takes `int` and returns `int`.
- `DoubleFunction<R>`, `ToDoubleFunction<T>`, and similar variants for `double`.

## 7. When to use a lambda, when to use a method reference?

Both styles can express the same conversion:

```java
Function<String, Integer> length1 = text -> text.length();
Function<String, Integer> length2 = String::length;

Function<String, String> trim1 = text -> text.trim();
Function<String, String> trim2 = String::trim;
```

Use a **method reference** when it directly expresses an existing method with clear intent and matching types. Use a **lambda** when you need to combine multiple operations, constants, conditions, or business logic:

```java
Function<String, String> normalize =
        text -> text.trim().toUpperCase(java.util.Locale.ROOT);
```

Java does not automatically treat every method as a `Function` when the type context is unclear. For example, `String::length` requires a compatible **target type** such as `Function<String,Integer>` or `ToIntFunction<String>`; a lambda or method reference can be used directly at a `map(...)` call site because the compiler infers the type from that API.

## 8. Being "functional" does not automatically guarantee a pure function

`Function<T,R>` specifies the input and output types; it **does not require** the implementation to be a *pure function*. A lambda can modify a global variable, write to a file, query a database, or return a result based on the current time:

```java
// Counter-example with side effects; place in an appropriate class.
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger();

Function<String, String> addSerial =
        code -> code + "-" + counter.incrementAndGet();
```

`addSerial.apply("BOOK")` can return different results across calls because it depends on state outside the input. `AtomicInteger` protects the single increment from data races, but it does **not** make the function pure and does not automatically guarantee a multi-step business rule.

In `Stream.map(...)`, prefer functions that only transform data:

```java
Function<String, String> clean =
        text -> text.trim().toLowerCase(java.util.Locale.ROOT);

List<String> codes = List.of(" BOOK ", " PEN ")
        .stream()
        .map(clean)
        .toList();
```

`codes` contains `["book", "pen"]` and the input list is not modified. Avoid using `map` to both transform and manually update a shared `ArrayList`; let the terminal operation `toList`/`collect` manage collecting results. Requirements that genuinely have side effects, such as writing to a database, should be placed at the orchestration boundary so they are easy to understand and test.

## 9. Using `Function` outside `Stream.map`

### `Optional.map`

For a value that may be absent:

```java
java.util.Optional<String> raw = java.util.Optional.of("  book  ");
String code = raw
        .map(String::trim)
        .map(s -> s.toUpperCase(java.util.Locale.ROOT))
        .orElse("UNKNOWN");
// code == "BOOK"
```

`Optional.map` takes a `Function` to transform the value *if present*. If the mapper returns `null`, `Optional.map` produces `Optional.empty()`. If you need a function that returns `Optional<U>`, use `flatMap` to avoid nesting `Optional<Optional<U>>`.

### `Map.computeIfAbsent`

When you want to compute a value for a key **only if no suitable mapping exists yet**:

```java
Map<String, Integer> lengths = new java.util.HashMap<>();
int result = lengths.computeIfAbsent("BOOK", String::length);
// result == 4; lengths.get("BOOK") == 4
```

The example requires `import java.util.Map;` if not using the fully qualified name. `computeIfAbsent` takes `Function<? super K,? extends V>`, so `String::length` is valid when `K=String`, `V=Integer`. Note: this operation **updates the Map**, unlike `Stream.map`; you should consider concurrency rules and implementation behavior when multiple threads access it simultaneously. In the example, `HashMap` is used single-threaded; if multiple threads write concurrently, an appropriate map type or synchronization mechanism is needed.

### Passing a transformation into a custom method

A generic method can accept a `Function` from the caller, thereby reusing the algorithm instead of hardcoding the conversion:

```java
static <T, R> List<R> transform(
        List<T> source, Function<? super T, ? extends R> mapper) {
    return source.stream().map(mapper).toList();
}
```

This is an **illustrative method** that needs to be placed inside a class with `List` and `Function` imported. When calling `transform(List.of(1, 2, 3), x -> "N=" + x)`, the output is a `List<String>` containing `["N=1", "N=2", "N=3"]`. Using `? super T` for the mapper's input and `? extends R` for its output allows accepting functions with flexible types following the *producer extends, consumer super* (PECS) principle. In the pipeline, the mapper "consumes" elements `T` and "produces" results `R`.

## 10. Limitations and common pitfalls

**Confusing `apply` with `accept` or `test`.** `Function` uses `apply` and must return a value `R`; `Consumer` uses `accept` and returns no result; `Predicate` uses `test` and returns a boolean.

**Composing functions in the wrong order.** `f.andThen(g)` differs from `f.compose(g)`. Write down the explicit type flow `T → U → R` before coding, especially when multiple steps change types.

**Composing incompatible types.** `Function<String,Integer>` can only compose with a subsequent function that accepts a type compatible with `Integer`. The compiler rejects many invalid combinations at compile time.

**Assuming the mapper always runs.** `Stream.map` executes lazily and can be short-circuited by `findFirst`, `limit`, `anyMatch`, etc. Do not put side effects that must run a specific number of times inside a mapper. When a pipeline is optimized, you should not rely on the number of mapper invocations to drive business logic.

**Not handling invalid data.** `Integer::parseInt` succeeds with `"7"`, but throws `NumberFormatException` with `"seven"`. For external input, consider validating or using a conversion function that returns a result type representing errors such as `Optional`/a Result type, and handle it at the appropriate boundary.

**Null input or null return.** `Function` does not automatically reject `null`. `String::trim` fails if the input is `null`; a mapper returning `null` can cause the next step to fail. Establish a clear null contract for each transformation and prefer validating inputs. `Optional.map` and `Stream.map` behave differently when a mapper returns null; do not generalize a single rule.

**Using `Function<T,R>` for every kind of function.** For conditions, actions, two inputs, or primitive transformations, `Predicate`, `Consumer`, `BiFunction`, and `ToIntFunction` usually describe intent better. Using the right interface also makes the API self-documenting.

**Relying on mutable variables outside the lambda.** Captured local variables must be `final` or *effectively final*, but that does not prevent modifying state inside a referenced object. Moving state outside the lambda can cause results to differ between runs or cause race conditions in parallel streams.

**Assuming `andThen` handles exceptions automatically.** If the first transformation throws an exception, the second does not run and the exception propagates outward; handle it according to the business contract. `Function` has no built-in error type or automatic retry.

**Mistaking `identity` for a copy.** `Function.identity()` returns the exact original object; it does not deep copy, does not create a snapshot, and does not guarantee thread safety if that object is mutable.

## 11. Practice exercises and verification

1. Write a `Function<String, String>` that turns `"  pen  "` into `"PEN"` in two ways: `trim.andThen(upper)` and `upper.compose(trim)`. Verify both produce the same result.
2. Write a `Function<String,Integer>` that converts a string to an integer, then `andThen` with a doubling function. With `"7"` it should yield `14`. Try `"abc"` and explain the exception.
3. In the orders program, replace `orders.stream().map(show)` with `orders.stream().map(toView).map(format)`. The stdout of the three order lines must remain unchanged; only how the transformations are organized changes.
4. Write a `Function<Order,Boolean>` that checks whether the total is greater than `100000`, then convert it to `Predicate<Order>` and use `filter`. For the three sample orders, the result keeps A01 and A02. Explain why `Predicate` expresses intent better.
5. Add a `Function<Order,String>` that returns the order ID; use `orders.stream().map(...)` to create a `List<String>`. The result must be `["A01", "A02", "A03"]`.
6. Create `Function<Integer,Integer>` functions to add 3 and multiply by 2; verify `andThen` on value `4` gives `14` when adding 3 first then multiplying by 2, and reversing the order gives `11`.
7. Write a `transform` method taking `List<T>` and `Function<? super T, ? extends R>`; call it with a list of numbers and a mapper to strings, verifying the input is unmodified and the output has the exact same number of elements.
8. State a case where `Function.identity()` is appropriate when building `Collectors.toMap`. If two elements have duplicate keys and no merge function is provided, what happens?

**Self-check hints:** clearly identify `T` and `R`; read the transformation as the sentence "takes a ... returns a ..."; check the order of `compose`/`andThen`; state when `apply` actually runs; avoid side effects in mappers; test empty, null, parsing error, and duplicate key cases. Once you master these steps, you can use `Function<T,R>` to organize clear, composable, and independently testable transformations in Java.
