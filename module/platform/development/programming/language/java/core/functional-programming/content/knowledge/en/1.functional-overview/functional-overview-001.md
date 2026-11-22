# What Is Functional Programming and What Problems Does It Solve in Java?

## 1. Where does the problem come from?

When a program processes data, we often need to filter, transform, aggregate, and then return a result. The imperative style describes each execution step: creating a result variable, iterating in a loop, checking conditions, adding elements, or accumulating values. This approach is completely valid, but as logic grows larger, state can be mutated in many places. The reader has to track both **the value being computed** and **when variables are modified**.

Functional programming (*functional programming*, FP) is a way of organizing programs that centers on **functions and value transformations**. We aim to express how input data is transformed into output; we favor functions with predictable results, limit the mutation of shared state, and compose small processing steps into a clear pipeline.

Java is a multi-paradigm language, primarily object-oriented, but it supports a functional programming style through lambdas, method references, functional interfaces, the Stream API, and many APIs that accept functions as parameters. Writing Java in a functional style **does not mean** every line must use Stream, nor that you must abandon classes and objects.

## 2. How does functional programming differ from the imperative style?

Suppose we need to take non-empty names, trim whitespace from both ends, and convert them to uppercase:

**Imperative style:** manually controlling the loop and mutating the result list.

~~~java
List<String> result = new ArrayList<>();
for (String name : names) {
    String clean = name.trim();
    if (!clean.isEmpty()) {
        result.add(clean.toUpperCase(Locale.ROOT));
    }
}
~~~

**Transformation-based expression:** describing a chain of operations on the data.

~~~java
List<String> result = names.stream()
        .map(String::trim)
        .filter(name -> !name.isEmpty())
        .map(name -> name.toUpperCase(Locale.ROOT))
        .toList();
~~~

Both can produce the same value. The second version highlights the steps **map → filter → map → collect** and eliminates the need to manually manage the result list. However, a loop can still be easier to understand for very short tasks or when complex state manipulation is needed. FP is a way of thinking and designing, not a contest to use fewer lines of code.

## 3. Core ideas

### 3.1. Pure functions

A function is considered pure when (1) the same inputs in the same semantic context always produce the same output and (2) calling it produces no externally observable side effects such as modifying shared variables, writing files, making network calls, or printing to the console.

~~~java
static long applyDiscount(long amountInDong) {
    return amountInDong * 90 / 100; // 10% discount, assuming amount is non-negative
}
~~~

With an input of 200_000, the function always returns 180_000. A reader can replace the call with its result without changing the program's meaning in the corresponding context: this property is called **referential transparency**.

Conversely, the following function depends on state that can be changed elsewhere and produces a side effect:

~~~java
static int totalCalls = 0;

static long calculateAndCount(long amount) {
    totalCalls++;
    return amount * 90 / 100;
}
~~~

The resulting monetary amount may be consistent, but the overall behavior of the function is impure because it modifies the `totalCalls` variable. It is also important to distinguish between **local variables** inside a function (which do not necessarily cause external side effects) and **shared state** that a call mutates.

### 3.2. Immutability

Immutability means preferring to create a new value rather than mutating an existing value that is referenced by multiple parts of the program. This reduces the number of places where changes must be tracked, making testing and reasoning about concurrency easier.

In Java, List.of(...) creates a list that does not allow adding or removing elements; Stream.toList() (Java 16+) also returns a structurally unmodifiable list. However, **an unmodifiable list does not mean the objects inside it are immutable**. A Java record has final components, but it is only shallowly immutable: if it contains a List or a mutable object, the internal contents can still change.

Not all state changes are bad. Updating a database, writing logs, and handling UI updates are necessary effects. What is useful is **isolating the side-effecting parts at the boundaries** and keeping the core computation simple and independently testable.

### 3.3. Functions as passable objects

In Java, we can pass behavior through a **functional interface**: an interface with exactly one abstract method under the SAM (*single abstract method*) rule. A lambda is a concise way to provide the implementation for that interface.

Some common types in java.util.function:

| Interface | Meaning | Main method |
| --- | --- | --- |
| Predicate<T> | Tests a condition T → boolean | test |
| Function<T,R> | Transforms T → R | apply |
| Consumer<T> | Accepts T and performs an action, returns no result | accept |
| Supplier<T> | Supplies T, takes no arguments | get |
| UnaryOperator<T> | Transforms T → T | apply |
| BinaryOperator<T> | Combines two values T → T | apply |

Example:

~~~java
Predicate<String> nonBlank = s -> !s.isBlank();
Function<String, String> normalize = String::trim;
System.out.println(nonBlank.test(" Java ")); // true
System.out.println(normalize.apply(" Java ")); // Java
~~~

A **higher-order function** is a function that takes another function as input or produces a function as its result. In Java, filter takes a Predicate; map takes a Function. They express the general processing logic, while the specific behavior is passed in from outside.

### 3.4. Function composition

Complex processing can be built by combining small transformations:

~~~java
Function<String, String> trim = String::trim;
Function<String, String> upper = s -> s.toUpperCase(Locale.ROOT);
Function<String, String> normalize = trim.andThen(upper);
System.out.println(normalize.apply("  java  ")); // JAVA
~~~

For Function, a.andThen(b) means applying a first and then b; a.compose(b) means applying b first and then a. Composition is easiest to reason about when each function does not depend on side effects or implicit ordering.

### 3.5. Describing the result instead of controlling each step

The *declarative* style usually states **what you want to compute** via filter, map, reduce, and data grouping, instead of manually specifying each loop step and variable update. In Java, Stream is a commonly used tool for this, but the two concepts **functional programming** and **Stream API** are not identical: you can write pure functions without using Stream, and you can also write Streams that contain side effects and are hard to predict.

## 4. Complete example runnable with Java 17+

The following example does three things: calculates the total of paid orders, normalizes a list of names, and composes two functions. The data is declared only once; the computation steps do not modify the source.

Create the file **FunctionalIntro.java**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.function.Function;

public class FunctionalIntro {
    record Order(String id, long amountInDong, boolean paid) {}

    static long paidTotal(List<Order> orders) {
        return orders.stream()
                .filter(Order::paid)
                .mapToLong(Order::amountInDong)
                .sum();
    }

    static List<String> validNames(List<String> names) {
        return names.stream()
                .map(String::trim)
                .filter(name -> !name.isEmpty())
                .map(name -> name.toUpperCase(Locale.ROOT))
                .toList();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 120_000, true),
                new Order("B", 70_000, false),
                new Order("C", 80_000, true)
        );
        List<String> names = List.of(" An ", "Binh", " ", "Chi");

        System.out.println("Tổng đơn đã thanh toán: " + paidTotal(orders));
        System.out.println("Tên hợp lệ: " + validNames(names));

        Function<String, String> trim = String::trim;
        Function<String, String> upper =
                s -> s.toUpperCase(Locale.ROOT);
        Function<String, String> normalize = trim.andThen(upper);
        System.out.println("Chuẩn hóa: " + normalize.apply("  java  "));
    }
}
~~~

Compile and run:

~~~bash
javac FunctionalIntro.java
java FunctionalIntro
~~~

Output:

~~~text
Tổng đơn đã thanh toán: 200000
Tên hợp lệ: [AN, BINH, CHI]
Chuẩn hóa: JAVA
~~~

**Explanation:** filter(Order::paid) keeps orders with paid = true; mapToLong extracts the amount and sum adds the two amounts 120_000 + 80_000. validNames sequentially trims, removes empty names, and converts to uppercase using Locale.ROOT for consistent results regardless of locale differences. andThen composes the two Functions in the exact order.

paidTotal does not modify the input List and always returns the same result for the same order contents. It **does not automatically guarantee purity** if the list or its elements are designed to be concurrently mutable. In this example, List.of and the record contain only String, long, and boolean, so the input data fits immutable reasoning.

## 5. What practical problems does FP solve?

1. **Reduces bugs from shared state:** instead of multiple functions silently mutating the same variable, transformations take clear inputs and return clear outputs. This is especially useful when logic is called repeatedly or runs concurrently.
2. **Easy and reproducible testing:** a function that computes a price from parameters can be tested with an input/output table, without needing to start a database, a fake clock, or another system just to compute an operation.
3. **Separates business policy from iteration mechanics:** filtering by condition, calculating tax, normalizing strings, and grouping are small reusable functions, rather than duplicating large loops with many branches.
4. **Easier-to-read data processing flows:** a pipeline describes a clear sequence of filtering, mapping, grouping, and aggregating; the reader sees the processing intent without having to simulate temporary variables in each loop.
5. **Reduces execution-order dependencies:** independent operations without side effects are generally safer to reorder or run in parallel, though parallelization still requires considering output order, associativity of the reduction operation, the source data, and execution overhead.

Order service design example: fetching data and writing results in the database access layer are the side-effecting parts; inside, there can be functions to calculate shipping fees, discounts, and totals based solely on the passed-in data. When pricing policies change, the calculation functions can be tested in isolation without mocking the entire application.

## 6. When applying in Java, understand Stream properly

**A Stream is a description of a processing pipeline, not a collection holding precomputed results.** Intermediate operations like filter and map are typically *lazy*: they build the pipeline without traversing elements yet. Only a terminal operation such as toList, count, sum, or forEach triggers processing. A Stream can usually be used only once; to process it again, create a new Stream from the source.

Avoid sneaking mutations to external variables inside map/filter/forEach, such as incrementing a mutable counter from a lambda. Doing so defeats the reasoning benefits and can especially cause race conditions when using parallelStream(). Instead, use sum, count, reduce, or an appropriate collector. When reducing in parallel, the reduction operation must satisfy the API contracts, especially associativity and a proper identity; simply calling parallel() does not automatically make it faster or safe.

**Ordering:** a pipeline with an ordered source like List usually preserves encounter order for many operations, but some operations and sources do not guarantee order. Do not rely on implicit ordering when using unordered collections, findAny, or parallel streams.

**Complexity:** each filter/map still needs to process the relevant elements. Chaining Streams does not turn an O(n) algorithm into O(1). Lambdas, boxing, allocations, and intermediate steps can incur overhead; measure with an appropriate benchmark if performance is a priority, rather than assuming Stream is faster than a loop.

**Null values:** List.of does not accept null elements. If the source can contain null, define a data convention and filter/handle it intentionally before invoking methods on elements; do not assume every map operation is safe.

## 7. When should you prefer it and when should you not?

**Consider a functional style** when processing lists, converting DTOs, checking conditions, aggregating metrics, applying independent calculation rules, or building business steps that are easy to compose and test.

**Do not force** every task into long lambda chains. Logic requiring many control branches, resource handling, stateful transactions, I/O, or high-performance loops is sometimes clearer with standard methods and statements. A practical combination is to have the core logic take data and return values, while the outer layer handles interacting with the outside world.

Also, do not turn every line into an obscure method reference. Give transformations clear names, extract long pipelines into functions with business meaning, and use a loop when that is the most readable form.

## 8. Common misconceptions and pitfalls

- **“Using lambdas means you have FP”:** a lambda can write to a file, mutate object fields, or depend on global state. You must look at behavior as well, not just syntax.
- **“A function without reassigned variables is pure”:** a function that reads the current time, makes a network call, or writes logs still involves state/side effects even if it does not mutate local variables.
- **“An immutable List means all the data is immutable”:** elements inside can be mutable; a record also only guarantees shallow immutability.
- **“Stream is always fast and runs immediately”:** intermediate operations are typically lazy; the main benefit here is expressing processing clearly, not a speed guarantee.
- **“parallelStream automatically fixes concurrency issues”:** code with shared state can produce wrong results; overhead can also make small workloads slower.
- **“A Stream can be reused”:** after a terminal operation, the Stream has been consumed; create a new pipeline instead.
- **“Functional programming cannot have I/O”:** applications need I/O; what you need to do is identify and confine side effects to appropriate places.

## 9. Self-check questions

1. If two calls to a function receive the same arguments but read a mutable global variable, can the function be considered pure? **No:** the result also depends on state outside the parameters.
2. Why is returning a new List usually easier to test than mutating a List owned by the caller? **Because** the state before the call is not altered and the result can be observed directly.
3. When do map and filter on a Stream typically execute? **When a terminal operation** requests evaluation of the pipeline (except for optimizations that skip unnecessary operations according to the Stream contract).
4. Should every problem use Stream? **No:** choose the expression that makes the intent clearest, considering state handling, readability, and execution cost.

**Remember:** Functional programming helps break logic into small, predictable, and easily composable transformations. Its practical value in Java lies in **reducing reliance on mutable state, improving testability, and clarifying data flow**; lambdas and Streams are simply tools to realize that mindset.
