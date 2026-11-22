# Referencing Static Methods with `Type::method` in Java

## 1. Concept and goal

A **method reference** is a syntax using `::` to point to an existing method, in order to provide an implementation for a **functional interface** without rewriting a lambda body. When the referenced method is `static`, the common form is:

```java
TypeName::staticMethodName
```

For example, `Integer::parseInt`, `Math::max`, `Integer::sum`, or `MyClass::convert`. The `::` syntax **does not call the method immediately**. Java uses the target type context to create a functional interface value; only when the abstract method of that interface is called is the referenced static method executed.

Short example:

```java
import java.util.function.Function;

Function<String, Integer> parse = Integer::parseInt;
int value = parse.apply("42"); // 42
```

`Integer.parseInt("42")` is a regular **method call**. `Integer::parseInt` is a **method reference** acting as a `String → Integer` function. When assigned to `Function<String, Integer>`, Java understands it needs a method that takes a `String` and returns a result compatible with `Integer`; `parseInt(String)` returns `int`, and the result is boxed into `Integer` if needed.

This lesson focuses on how to write references **to static methods**, how Java maps parameters and return values to a functional interface, applying them in streams, and situations easily confused with instance references.

## 2. Identifying the parts of `Type::method`

| Component | Meaning | Example |
| --- | --- | --- |
| `Type` | Class or type declaring the static method | `Integer`, `Math`, `OrderFunctions` |
| `::` | Method reference operator | `Integer::parseInt` |
| `method` | Method name, **without** `()` and argument list | `parseInt` |
| **Target type** | Functional interface determining the signature to match | `Function<String,Integer>` |
| **Invocation** | Call to the functional interface's method | `parse.apply("42")` |

Compare:

```java
int direct = Integer.parseInt("42");            // Called immediately, result is 42.
Function<String, Integer> viaLambda = text -> Integer.parseInt(text);
Function<String, Integer> viaReference = Integer::parseInt;
int deferred = viaReference.apply("42");        // Parsed only at this point.
```

Both `viaLambda` and `viaReference` represent the `String → Integer` conversion. Method references reduce boilerplate when a lambda **merely forwards parameters to an existing method**.

A method reference can target `Function`, `Predicate`, `Consumer`, `Supplier`, `BiFunction`, `Comparator`, or a custom functional interface, provided the parameter and return types are compatible.

> Note on notation: `Type::method` **does not always mean static**. For example, `String::length` is an **unbound instance method reference**; `String` here is just the type of the receiver. To identify the static form, check that the selected method is actually declared `static`.

## 3. How parameters and return types are mapped

Suppose we have a method:

```java
static String format(String code, int quantity) {
    return code + " x " + quantity;
}
```

If it belongs to the `OrderTools` class, you can write:

```java
BiFunction<String, Integer, String> formatter = OrderTools::format;
String result = formatter.apply("BOOK", 3); // "BOOK x 3"
```

These two snippets only **illustrate the signature**; you need to declare `format` inside `OrderTools` and import `java.util.function.BiFunction` to compile. The method `format(String,int)` takes two parameters; `BiFunction<String,Integer,String>` also takes two parameters and returns `String`. Java unboxes `Integer` to `int` when needed.

General rules:

- **Number of parameters:** the static method receives arguments corresponding to the parameter list of the abstract method in the target functional interface.
- **Parameter types:** Java checks valid type conversions in the invocation context, including boxing/unboxing and generic type inference when applicable.
- **Return value:** the static method must return a value compatible with the target interface's result; if the target returns `void`, in valid cases, the call's return value can be ignored.
- **Exceptions:** exceptions thrown by the referenced method are not automatically caught or converted. Checked exceptions must conform to the `throws` contract of the target interface, or be handled through an appropriate wrapper.

Mapping table for some common cases:

| Static method | Target functional interface | Meaning |
| --- | --- | --- |
| `Integer.parseInt(String)` | `Function<String,Integer>` | Convert a string to an integer |
| `Math.abs(int)` | `IntUnaryOperator` | Convert an `int` to its absolute value |
| `Math.max(int,int)` | `IntBinaryOperator` | Get the larger of two integers |
| `Integer.sum(int,int)` | `BinaryOperator<Integer>` | Add two `Integer`s after unboxing |
| `String.valueOf(int)` | `IntFunction<String>` | Create a string from an `int` |
| `System.currentTimeMillis()` | `LongSupplier` | Provide the current time as a `long` |

`System::currentTimeMillis` is a valid static reference, but its result depends on time, so using a method reference is **not synonymous** with a pure function or an immutable result.

## 4. Complete Java 17 program: processing orders with static method references

We have initial order data in string form. Requirements:

1. Transform each `RawOrder` into an `Order` after normalizing the ID/customer and parsing the amount.
2. Filter orders with an amount of **at least 100000**.
3. Sort orders by amount ascending, breaking ties by order ID.
4. Convert each order into a report line and calculate the total amount.
5. Demonstrate static method references with one or two arguments.

Create the file **`StaticReferenceDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.function.IntBinaryOperator;
import java.util.function.Predicate;

public class StaticReferenceDemo {
    record RawOrder(String id, String customer, String amount) {}

    record Order(String id, String customer, BigDecimal amount) {}

    // One RawOrder input, one Order result.
    static Order parseOrder(RawOrder raw) {
        return new Order(
                raw.id().trim(),
                raw.customer().trim(),
                new BigDecimal(raw.amount())
        );
    }

    // One Order input, one boolean result.
    static boolean isLarge(Order order) {
        return order.amount().compareTo(new BigDecimal("100000")) >= 0;
    }

    // Two Order inputs, one int result for Comparator.
    static int compareByAmount(Order left, Order right) {
        int byAmount = left.amount().compareTo(right.amount());
        return byAmount != 0
                ? byAmount
                : left.id().compareTo(right.id());
    }

    // One Order to a formatted string.
    static String render(Order order) {
        return order.id()
                + " | " + order.customer()
                + " | " + order.amount().toPlainString();
    }

    // Two BigDecimals to a BigDecimal sum.
    static BigDecimal add(BigDecimal left, BigDecimal right) {
        return left.add(right);
    }

    // Two strings to one string.
    static String join(String left, String right) {
        return left + ":" + right;
    }

    public static void main(String[] args) {
        List<RawOrder> rawOrders = List.of(
                new RawOrder(" A01 ", " Lan ", "120000"),
                new RawOrder(" A02 ", " Minh ", "80000"),
                new RawOrder(" A03 ", " Lan ", "200000")
        );

        // Static method references to methods of this same class.
        Function<RawOrder, Order> parser = StaticReferenceDemo::parseOrder;
        Predicate<Order> large = StaticReferenceDemo::isLarge;
        Comparator<Order> byAmount = StaticReferenceDemo::compareByAmount;
        Function<Order, String> formatter = StaticReferenceDemo::render;
        BinaryOperator<BigDecimal> sum = StaticReferenceDemo::add;
        BiFunction<String, String, String> joiner = StaticReferenceDemo::join;

        List<Order> orders = rawOrders.stream()
                .map(parser)
                .toList();

        System.out.println("All orders:");
        orders.stream()
                .map(formatter)
                .forEach(System.out::println);

        System.out.println("Large orders:");
        orders.stream()
                .filter(large)
                .map(formatter)
                .forEach(System.out::println);

        System.out.println("Sorted ascending:");
        orders.stream()
                .sorted(byAmount)
                .map(formatter)
                .forEach(System.out::println);

        BigDecimal total = orders.stream()
                .map(Order::amount)
                .reduce(BigDecimal.ZERO, sum);
        System.out.println("Total: " + total.toPlainString());

        // Built-in static method references in the JDK.
        Function<String, Integer> numberParser = Integer::parseInt;
        IntBinaryOperator maximum = Math::max;

        System.out.println("Parsed: " + numberParser.apply("42"));
        System.out.println("Max: " + maximum.applyAsInt(7, 9));
        System.out.println("Label: " + joiner.apply("Lan", "A01"));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 StaticReferenceDemo.java
java StaticReferenceDemo
```

**Program stdout:**

```text
All orders:
A01 | Lan | 120000
A02 | Minh | 80000
A03 | Lan | 200000
Large orders:
A01 | Lan | 120000
A03 | Lan | 200000
Sorted ascending:
A02 | Minh | 80000
A01 | Lan | 120000
A03 | Lan | 200000
Total: 400000
Parsed: 42
Max: 9
Label: Lan:A01
```

Checking the output:

- `parseOrder` strips leading/trailing whitespace with `trim()`, then creates a `BigDecimal` from the numeric string. Because integer strings are used, `toPlainString()` prints `120000`, `80000`, `200000`.
- `isLarge` uses `compareTo`; `120000` and `200000` meet the `>= 100000` threshold, while `80000` does not.
- `compareByAmount` sorts ascending: `80000 → 120000 → 200000`; the order ID is only used to break ties if the amounts are equal.
- `reduce(BigDecimal.ZERO, sum)` returns `120000 + 80000 + 200000 = 400000`.
- `Integer.parseInt("42")` returns `int 42`, which is boxed to match `Function<String,Integer>`.
- `Math.max(7,9)` returns `9`, `join("Lan","A01")` returns `"Lan:A01"`.

The `.map(Order::amount)` and `System.out::println` parts in the example are **instance method references** to show that a pipeline can combine multiple reference forms; the **static** references are clearly illustrated by `StaticReferenceDemo::parseOrder`, `::isLarge`, `::compareByAmount`, `::render`, `::add`, `::join`, `Integer::parseInt`, and `Math::max`.

## 5. Converting each lambda to a static method reference

Read both forms as the same parameterized call:

### One parameter with a return value

```java
Function<RawOrder, Order> lambda =
        raw -> StaticReferenceDemo.parseOrder(raw);

Function<RawOrder, Order> reference =
        StaticReferenceDemo::parseOrder;
```

When `apply(raw)` runs, both call `parseOrder(raw)`. `Function<RawOrder,Order>` shapes the input and output. When a transformation is just "argument forwarding", the reference is usually easier to read.

### One parameter with a boolean result

```java
Predicate<Order> lambda =
        order -> StaticReferenceDemo.isLarge(order);

Predicate<Order> reference =
        StaticReferenceDemo::isLarge;
```

Used in `Stream.filter(...)` because `filter` expects a `Predicate<? super T>`. `Predicate<Order>` has the method `boolean test(Order)`; the static method `isLarge(Order)` returns that exact boolean.

### Two parameters with an integer result

```java
Comparator<Order> lambda =
        (a, b) -> StaticReferenceDemo.compareByAmount(a, b);

Comparator<Order> reference =
        StaticReferenceDemo::compareByAmount;
```

`Comparator<T>` has the method `int compare(T a, T b)`. A negative, zero, or positive result expresses the comparison order; do not use boolean `true/false` as a substitute.

### Two parameters and a result of the same type

```java
BinaryOperator<BigDecimal> lambda =
        (a, b) -> StaticReferenceDemo.add(a, b);

BinaryOperator<BigDecimal> reference =
        StaticReferenceDemo::add;
```

`BinaryOperator<T>` is a specialization of `BiFunction<T,T,T>`. `BigDecimal` addition has the identity value `BigDecimal.ZERO` and produces a new value, making it suitable for summing amounts. Using `BigDecimal` for monetary data avoids decimal representation errors from `double`, though rounding rules must still be defined if division/tax is involved.

## 6. Static method references and compile-time type checking

A method reference is a **poly expression**: its type is inferred from the target functional interface, not from the `Type::method` syntax alone. Thus the following usages have clear types:

```java
Function<String, Integer> parser = Integer::parseInt;
IntBinaryOperator maxOfTwo = Math::max;
Predicate<String> blank = String::isBlank;
```

In these three lines, `parser` and `maxOfTwo` use **static method references**. The line `String::isBlank`, however, is an **unbound instance method reference**: the `String` object received from `Predicate.test(String)` becomes the receiver of `isBlank()`.

You cannot declare a method reference as a standalone expression without a suitable target type:

```java
// WRONG: the compiler cannot infer a functional interface for the method reference.
// var parser = Integer::parseInt;

// RIGHT: provide a target type.
Function<String, Integer> parser = Integer::parseInt;
```

The comment illustrates an error and should not be included in the main program. When a method reference is passed as an argument like `map(Integer::parseInt)`, the `map` API and the source element type provide the context for the compiler to infer the target type.

### Overloads selected by target type

`Math` has multiple `abs` and `max` overloads. Java can select the matching overload based on the interface signature:

```java
java.util.function.IntUnaryOperator intAbs = Math::abs;
java.util.function.DoubleUnaryOperator doubleAbs = Math::abs;

System.out.println(intAbs.applyAsInt(-7));       // 7
System.out.println(doubleAbs.applyAsDouble(-2.5)); // 2.5
```

A method reference does not "contain" a single overload ahead of time. When the target type differs, method resolution can also differ. If multiple overloads are applicable and none is most specific, the compiler reports an **ambiguous method reference**; adding an explicit target type, writing an explicit lambda, or renaming the API helps clarify it.

### Generic static methods

Static methods can be generic; the compiler infers the type when the target interface is known:

```java
import java.util.Objects;
import java.util.function.Function;

Function<String, String> requireString = Objects::requireNonNull;
System.out.println(requireString.apply("Java")); // Java
```

`Objects.requireNonNull(T)` returns the non-null reference as-is, or throws `NullPointerException` if null. With the target `Function<String,String>`, the compiler can choose the one-parameter overload and infer `T` accordingly. Being generic does not remove the requirement for a target type.

## 7. Distinguishing commonly confused method reference forms

| Syntax | Kind | Interpretation |
| --- | --- | --- |
| `Integer::parseInt` | Static | `s -> Integer.parseInt(s)` |
| `Math::max` | Static | `(a,b) -> Math.max(a,b)` |
| `StaticReferenceDemo::render` | Static | `order -> StaticReferenceDemo.render(order)` |
| `String::length` | Unbound instance | `s -> s.length()` |
| `Order::amount` | Unbound instance | `order -> order.amount()` |
| `System.out::println` | Bound instance | `x -> System.out.println(x)` |
| `somePrinter::print` | Bound instance | `x -> somePrinter.print(x)` |
| `ArrayList::new` | Constructor | `() -> new ArrayList<>()` in a suitable supplier context |

The **static form** does not add a receiver parameter. If the static method takes two parameters, the target functional interface needs two compatible parameters. With an **unbound instance reference** like `String::length`, the first parameter of the functional interface acts as the **receiver**; the `length()` method itself takes no parameters, but `ToIntFunction<String>` has one `String` parameter on which to invoke the method.

`System.out::println` looks at first glance like it contains the class name `System`, but it is a **bound instance reference**: `out` is a static field of `System`, while `println` is an instance method of `PrintStream`. Read the exact expression **before `::`**, then determine whether the referenced method is static or instance.

### Watch out for static methods sharing a name with instance methods

Java has rules for searching and resolving method references based on syntax, arity, types, overloads, and applicability. With the `Type::method` form, both static and instance candidates may exist; a method reference can become ambiguous when the signature and target interface make multiple interpretations possible. Do not conclude that `Type::` automatically forces Java to pick a static method.

When you want to express intent clearly and the compiler reports ambiguity, write an explicit lambda, such as `(String s) -> Utility.parse(s)`, or adjust the API so method names do not cause confusion.

## 8. Choosing the right interface to avoid boxing and express intent

With static method references, choose an interface that accurately reflects the parameter count, inputs, and output:

```java
Function<String, Integer> boxed = Integer::parseInt;

java.util.function.ToIntFunction<String> primitive =
        Integer::parseInt;

java.util.function.IntBinaryOperator sum =
        Integer::sum;

java.util.function.LongSupplier currentMillis =
        System::currentTimeMillis;
```

- `Function<String,Integer>` calls `apply` and returns `Integer`. When referencing a method that returns primitive `int`, boxing may occur.
- `ToIntFunction<String>` calls `applyAsInt` and returns `int` directly, suitable when you want to avoid boxing in data-heavy processing loops.
- `IntBinaryOperator` calls `applyAsInt(int,int)`.
- `LongSupplier` calls `getAsLong()` and takes no input.

Do not force every method reference into `Function<T,R>`. If the static method returns `boolean`, `Predicate<T>` is usually clearer. If two parameters and the result have the same type, `BinaryOperator<T>` is convenient. If the method takes no input, `Supplier<R>` or a primitive variant is usually more appropriate.

## 9. When to use a lambda instead of a static method reference?

A method reference is great when it expresses **an exact existing call**. A lambda remains appropriate if you want to add logic, transform arguments, or disambiguate a call.

### Methods requiring additional arguments

```java
// Want every number parsed in base 16.
Function<String, Integer> parseHex =
        text -> Integer.parseInt(text, 16);

// Cannot use Integer::parseInt directly for Function<String,Integer>
// to bind the radix = 16 parameter.
```

`Integer::parseInt` can point to the two-parameter overload when the target is `BiFunction<String,Integer,Integer>`, but `Function<String,Integer>` has no way to pass a fixed radix parameter using just a method reference. A lambda solves the fixed-argument part.

### Intentional error handling

```java
Function<String, Integer> parseOrZero = text -> {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        return 0;
    }
};
```

This is an **illustrative policy**: invalid data is turned into 0. In real business logic, 0 may be a valid value; consider returning `Optional<Integer>`, a Result type, or reporting the error explicitly to avoid masking failures. Method references do not include built-in exception handling or retries.

### Controlling side effects or expressing business logic clearly

```java
Function<String, String> normalizedCode =
        text -> text.trim().toUpperCase(java.util.Locale.ROOT);
```

A lambda with two transformations expresses this process. If a static method `normalizeCode(String)` already exists implementing the exact rule, switching to `CodeTools::normalizeCode` avoids duplicating logic across multiple places.

## 10. Error rules and common misconceptions

**Confusing `::` with an immediate call.** `Integer::parseInt` does not immediately take a string or return an `int`; it provides behavior matching the target interface. `Integer.parseInt("42")` is the direct call.

**Writing parentheses when creating a reference.** `Integer::parseInt("42")` is not valid Java syntax. The right syntax is `Integer::parseInt`, then calling `apply("42")` on the functional interface, or calling `Integer.parseInt("42")` directly.

**Missing target type.** `var f = Integer::parseInt` does not provide enough information on its own to determine a functional interface. Declare `Function<String,Integer> f` or pass it to an API with a matching functional parameter.

**Choosing an interface with the wrong signature.** `Supplier<Integer> parser = Integer::parseInt` is invalid because `parseInt` requires at least one argument, while `Supplier.get()` takes no arguments. `Function<String,Integer>` is more appropriate.

**Confusing static and instance.** `String::length` differs from `Integer::parseInt` regarding the receiver. A form with a class name before `::` can represent either one depending on the method.

**Mistaking `System.out::println` for static.** `System.out` is an expression accessing a `PrintStream` object, and `println` is an instance method on that object.

**Not validating parsed data.** `Integer::parseInt` throws `NumberFormatException` on malformed strings or values out of `int` range; `new BigDecimal(text)` also requires valid input. Method references do not protect against bad data.

**Thinking method references create pure functions.** `System::currentTimeMillis` is a static reference but produces results that change over time. A static method can update shared state or call external services; purity depends on the implementation, not the syntax.

**Ignoring side effects or execution order.** If a static function both computes a value and mutates a shared static variable, running it in `parallelStream().map(Type::method)` can cause races. Keep transformations read-only and return new results where appropriate; aggregations should use reduce/collectors with proper contracts.

**Assuming `sorted` mutates the original list.** `stream().sorted(...)` produces a stream ordered by the comparator without directly modifying the `List`. In the example, the original `orders` list remains in A01, A02, A03 order.

**Relying on `==` to compare method references.** Two references with the same body are not guaranteed to have the same object identity. Use them to invoke behavior via the target interface, not as business identity keys.

## 11. Practice exercises

1. Write `Function<String,Integer> parse = Integer::parseInt` and call `parse.apply("17")`. Explain why `String::length` cannot be assigned to `Supplier<Integer>` without a bound receiver.
2. Write `IntUnaryOperator abs = Math::abs`. Call it with `-12` and explain how the compiler selects the `abs(int)` overload.
3. Write `IntBinaryOperator larger = Math::max` and call it with `5`, `9`. Compare the lambda `(a,b) -> Math.max(a,b)` with the reference `Math::max`.
4. In `StaticReferenceDemo`, change `Function<RawOrder,Order> parser` to the lambda `raw -> StaticReferenceDemo.parseOrder(raw)`. Verify that stdout does not change.
5. Replace `Predicate<Order> large` with the equivalent lambda, then run `orders.stream().filter(large).count()`. The result should be `2`.
6. Sort orders by amount descending using the comparator `StaticReferenceDemo::compareByAmount` and `reversed()`; predict `A03, A01, A02`.
7. Add data with `amount = "not-a-number"`. Point out the exception in `parseOrder`, then design a clear error policy before feeding the data into the stream.
8. Write a `BiFunction<String,Integer,String>` that joins a product code and quantity using a static method. Compare the method signature with the `apply` signature.
9. Compare `System.out::println`, `String::toUpperCase`, and `String::valueOf`: which is bound instance, unbound instance, and static? Choose a suitable target type for each.
10. Use `Map<String,Integer>` to try `Integer::parseInt` on each string value. Consider how to handle duplicate keys, invalid values, and output immutability when building the result map.

## 12. Checklist when reading or writing static references

1. Is the target method **declared `static`**? If not, identify the receiver of the instance reference form.
2. How many **parameters** does the target functional interface have, what are their types, and what is the return type?
3. Which method overload is selected? Is there boxing/unboxing or type inference?
4. Can the method throw checked exceptions, throw runtime exceptions, or have side effects?
5. Is the method reference actually **clearer than a lambda** for the reader?
6. When used in a Stream, do you need to preserve order, avoid mutating state, and verify associativity for `reduce`?

Read `Type::method` as "use this method as the implementation of the required functional interface." For static methods, the parameters of the target interface are passed straight into the corresponding static call; **there is no extra receiver object**. Mastering signatures and target types is the key to using `Type::method` properly, especially when writing pipelines for transforming, filtering, comparing, and aggregating data.