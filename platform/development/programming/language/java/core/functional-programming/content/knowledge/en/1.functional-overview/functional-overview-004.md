# Combining Functional Style with Object-Oriented Programming in Java

## Objectives

After this lesson, you can explain why Java is both an object-oriented programming (OOP) language and supports a functional programming (FP) style; choose where to use classes/objects and where to use functions; pass behavior via functional interfaces, lambdas, and method references; combine Streams with a domain model; and control state and side effects so that code is easy to test and maintain.

## 1. Two styles solve two different problems

**Object-oriented programming** organizes a program around objects that have identity, data, rules, and responsibilities. For example, `Order` manages a collection of order lines and protects invariants: quantity must be positive, unit price must be non-negative. Encapsulation prevents outside code from arbitrarily modifying internal state; interfaces allow swapping implementations according to a contract.

**Functional style** focuses on data transformations through functions: taking inputs, returning results, and allowing functions to be passed or combined like values. A pure function does not modify externally observable state and, given the same inputs, always produces the same output. This approach is conducive to reasoning, testing, and reuse.

Java does not force you to choose one over the other. A practical design often uses **objects to model the domain and manage lifecycles**, and **functions to express rules, filtering, and transformations**. Lambdas, method references, and Streams are tools that help write those transformations; using Stream by itself does not automatically make code purely functional.

| Problem | Typically suitable Java tool | Reason |
| --- | --- | --- |
| Data and invariants of an entity | `class`, `record`, constructor, methods | Bundle data with validation rules |
| Contract or role of a service | `interface` and implementation classes | Separate responsibilities, replaceable |
| Context-dependent rules | Functional interface, lambda, method reference | Pass behavior into objects instead of duplicating conditional branches |
| Filtering, mapping, aggregating datasets | `Stream`, `Predicate`, `Function`, `Collectors` | Express the data pipeline |
| File I/O, database, network calls | Dedicated service objects | Isolate side effects at clear boundaries |

## 2. Bridging the two styles via functional interfaces

A **functional interface** is an interface with only one abstract method (SAM); `default` methods, `static` methods, or methods corresponding to `Object` do not increase the number of abstract methods to implement. `@FunctionalInterface` asks the compiler to check that constraint. Java provides common contracts in `java.util.function`:

- `Predicate<T>`: `boolean test(T)` — selection condition; combined with `and`, `or`, `negate`.
- `Function<T,R>`: `R apply(T)` — value transformation; combined with `andThen` or `compose`.
- `UnaryOperator<T>`: a `Function<T,T>`, suitable for same-type transformations.
- `Consumer<T>`: `void accept(T)` — performs an action, often with side effects.
- `Supplier<T>`: `T get()` — supplies a value when needed.
- `ToLongFunction<T>`: `long applyAsLong(T)` — avoids boxing when calculating money in integer units in the example.
- `Comparator<T>`: comparison rule; also a functional interface.

The lambda `x -> x > 0` is a way to create behavior for a functional interface at the call site. The method reference `Line::subtotal` expresses calling an existing method; both are still objects implementing the SAM contract. A lambda can read captured local variables, but those variables must be `final` or **effectively final** (not reassigned); this does not make a captured mutable object immutable or thread-safe.

When a strategy has multiple methods, requires its own state/lifecycle, or has complex configuration, an interface with an explicit implementation class is usually more appropriate than a long lambda. When behavior is a small, self-contained, and easily named rule, a lambda or method reference can reduce the verbosity of strategy classes.

## 3. Java 17 example: objects hold invariants, functions decide pricing

Problem: an order stores valid order lines. The same order must be able to calculate the normal total, the total after a 10% book discount policy, and the total for book lines only. If you write each total calculation with a loop and repeat accessing the list, the processing logic easily becomes scattered. We let `Order` be responsible for storing and iterating over order lines, while selection and pricing rules are passed in as functions.

Save the following code to **`FunctionalOopDemo.java`**:

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;
import java.util.function.ToLongFunction;

public class FunctionalOopDemo {
    record Line(String name, int quantity, long unitPrice) {
        Line {
            Objects.requireNonNull(name, "name");
            if (name.isBlank() || quantity <= 0 || unitPrice < 0) {
                throw new IllegalArgumentException("Invalid line");
            }
        }

        long subtotal() {
            return Math.multiplyExact(unitPrice, quantity);
        }
    }

    static final class Order {
        private final List<Line> lines;

        Order(List<Line> lines) {
            this.lines = List.copyOf(lines);
        }

        long total(Predicate<Line> select,
                   ToLongFunction<Line> priceRule) {
            Objects.requireNonNull(select, "select");
            Objects.requireNonNull(priceRule, "priceRule");
            return lines.stream()
                    .filter(select)
                    .mapToLong(priceRule)
                    .reduce(0L, Math::addExact);
        }
    }

    static long discount10Percent(long amount) {
        return Math.multiplyExact(amount, 9) / 10;
    }

    public static void main(String[] args) {
        Order order = new Order(List.of(
                new Line("Sách", 2, 100_000),
                new Line("Bút", 3, 10_000)
        ));

        Predicate<Line> all = line -> true;
        ToLongFunction<Line> normal = Line::subtotal;
        ToLongFunction<Line> campaign = line ->
                line.name().equals("Sách")
                        ? discount10Percent(line.subtotal())
                        : line.subtotal();

        System.out.println("Tổng gốc: " + order.total(all, normal));
        System.out.println("Sau ưu đãi: " + order.total(all, campaign));
        System.out.println("Chỉ sách: " + order.total(
                line -> line.name().equals("Sách"), normal));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac FunctionalOopDemo.java
java FunctionalOopDemo
```

Output:

```text
Tổng gốc: 230000
Sau ưu đãi: 210000
Chỉ sách: 200000
```

**Explanation of each role:**

1. `Line` is a `record` holding the data of an order line. The compact constructor validates the input data; `subtotal()` keeps logic tightly coupled with the line. With the `String` and primitive components here, a created `Line` cannot be modified through its API.
2. `Order` is an object class responsible for managing order lines. `List.copyOf` creates a list copy that cannot be structurally modified and rejects `null` elements; there is no need to expose the internal list. This copy is a **shallow copy**: if elements are mutable objects, the state of the elements themselves can still change.
3. `Predicate<Line>` decides which lines are counted. `ToLongFunction<Line>` decides the amount contributed by each line. The `Order` object does not need to know the specific policies.
4. `stream()` obtains the data source; `filter` excludes lines that do not meet the condition; `mapToLong` converts each line into an amount; `reduce(0L, Math::addExact)` sums the amounts while throwing an error if the `long` sum overflows. The intermediate operations `filter`/`mapToLong` are lazy and only execute when the terminal operation `reduce` is called.
5. `Line::subtotal` is a method reference that reuses an OOP method as a function. `campaign` is a strategy lambda, while `discount10Percent` is a pure function: the same `amount` produces the same result and mutates no objects.
6. Monetary totals use integer units so the example is easy to verify; integer division in the discount **rounds down any fractional remainder**. In real monetary systems, you must specify currency units, rounding modes, negative number handling, taxes, and financial rules; usually consider `BigDecimal` with an appropriate `RoundingMode` instead of arbitrarily applying integer division.

In the example, changing the pricing strategy does not mutate the original order. You can add a new pricing rule with a `ToLongFunction<Line>` without modifying the structure of `Order`. This is a form of **composition**: the object delegates to supplied behavior instead of having to create numerous subclasses for each policy.

## 4. Functional core and imperative shell

A useful boundary is to split the processing flow into:

1. **Imperative shell**: receives HTTP requests, reads from the database, gets the current time, calls payment services, writes logs/results. These steps have side effects and require error and transaction management.
2. **Functional core**: receives the collected data and explicit rules, computes or transforms them into a **new result** without accessing the external environment on its own.
3. The shell uses the core's result to decide which actions to perform.

For example, the application can load `Order` through a repository, call `order.total(...)` to compute the amount, and pass the result to a payment gateway. The payment gateway, repository, and clock belong to the integration layer; the amount calculation should be independent of them. To ensure the same inputs yield the same output, explicitly pass the validated timestamp, tax table, or promo code into the function instead of reading global state in the middle of the calculation.

This also helps testing: the calculation can be tested with plain Java data without starting a server or connecting to a database; the shell is tested separately with appropriate stubs/fakes.

## 5. Combining object models with Stream and Optional

Stream expresses a pipeline over data, not a replacement for all object methods:

```java
// Illustration using the Line record declared in the full example:
List<String> names = List.of(
        new Line("Sách", 2, 100_000),
        new Line("Bút", 3, 10_000))
        .stream()
        .filter(line -> line.quantity() >= 2)
        .map(Line::name)
        .toList(); // [Sách, Bút]; toList() is available since Java 16
```

`map` creates a new value from each element; `filter` keeps elements matching a condition; `sorted` sorts the stream; `collect` or `toList()` produces the result. `Stream.toList()` returns a list that **cannot be structurally modified**, but it does not automatically make the objects inside immutable. Each Stream is normally consumed only once; to process again, create a new Stream from the source.

`Optional<T>` is useful when a result may be absent, especially at return boundaries of search methods:

```java
// Standalone illustration independent of the main program; products is a List<Line>.
String firstBook = products.stream()
        .filter(line -> line.name().equals("Sách"))
        .findFirst()
        .map(Line::name)
        .orElse("Không có sách");
```

`findFirst()` returns `Optional<Line>`, `map` transforms the result if present, and `orElse` provides a fallback value. Avoid calling `get()` without checking for presence; consider `orElseGet` if creating the default value is expensive because `orElse` evaluates its argument eagerly even when the Optional has a value. There is no need to turn every field or parameter into an Optional.

## 6. When to prefer classes, and when to prefer functions?

Keep **classes/records** for domain values and rules that must hold everywhere, such as `Line` having a positive quantity. Keep **service interfaces** for large contracts with multiple operations, transactions, lifecycles, and dependencies. Pass **functions** for filter predicates, comparators, mappers, and small interchangeable calculation policies. For long or heavily branched algorithms, extract them into named methods or strategy classes so you do not turn lambdas into "black boxes".

A useful design rule is: **enforce invariants where data is created, place transformations in functions with clear inputs/outputs, and keep side effects in the integration layer**. There is no need to eliminate every `for` loop; for flows with many branches, `break`/`continue`, intentional state updates, or tasks that need step-by-step debugging, an explicit loop can be easier to understand than a Stream pipeline.

Combining them also follows SOLID in a pragmatic sense: `Order` has a clear single domain responsibility; varying behavior is passed via functional contracts, allowing policies to be extended with minimal modification; dependency inversion remains useful at repository or large service boundaries. You should not put everything into `Function<Object,Object>` because it loses type information and domain meaning.

## 7. Common pitfalls

- **Side effects inside `map`, `filter`, or `peek`**: writing to an external list or incrementing a shared counter makes the pipeline hard to reason about; with parallel streams it can cause race conditions. Prefer `map` to produce new values and `collect`/`reduce` to aggregate; place intentional logging/I/O only at appropriate boundaries. `peek` is primarily for observation/debugging.
- **Confusing "non-reassigned variable" with immutability**: a `final List<Line>` can still be mutated if it is a mutable list; `record` only prevents reassigning components, it does not make every reference deeply immutable. Consider defensive copies and immutable value types.
- **Putting database calls or current time inside calculation functions**: the same arguments can produce different results. Read those external inputs in the shell and pass them into the core.
- **Overusing inheritance to represent every business option**: dozens of subclasses like `DiscountForBooksOrder` are hard to compose. Simple policies are usually cleaner when passed via a functional interface; for complex behavior, a clearly named strategy object is still good.
- **Using `parallelStream()` as a default optimization**: parallelization has overhead, requires avoiding shared mutable state, and depends on the associativity of the aggregation; measure before using. Parallel reduce is only semantically safe when the combining operation is associative and has a proper identity.
- **Using `Stream` for unsuitable operations**: Stream is a data processing pipeline, not a storage collection; do not reuse the same stream after a terminal operation.
- **Overusing nested lambdas**: extract `Predicate` and `Function`/`ToLongFunction` into named variables or named methods to test and communicate intent.

## 8. How to self-verify

With the running example, try changing the discount policy from 10% to 20% by creating **a new function/policy**, without modifying `Order`; predict stdout beforehand. Try building a `Predicate<Line>` that only counts lines with `unitPrice >= 50_000`; the normal total of those lines is `200000`. Try passing quantity `0` to `new Line(...)`: the constructor must throw `IllegalArgumentException` before the order is created. Try using `List.copyOf` with a `null` element: Java throws `NullPointerException`.

For automated testing, separately test `Line.subtotal()`, `discount10Percent(...)`, and `Order.total(...)` for an empty list, a single line, multiple lines, policies matching all/no lines, boundary values, and overflow. Then test the integration layer to verify that it calls the data source, payment, and recording of results properly. Clear calculations in the functional core make these tests simple and stable.

**Conclusion:** Java combines OOP and FP effectively when the object model is responsible for keeping data valid, while small functions are responsible for selection and transformation. Side-effect boundaries are kept clear, making it possible to extend business policies while remaining easy to read, test, and maintain.
