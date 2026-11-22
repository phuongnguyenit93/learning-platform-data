# Extracting Complex Lambda Bodies into Methods for Testing in Java

## 1. Why extract complex lambdas?

A short lambda helps Java Streams express data flow directly:

```java
List<String> activeNames = employees.stream()
        .filter(Employee::active)
        .map(Employee::name)
        .toList();
```

This is an illustrative snippet inside a method with `employees` and an appropriate `Employee` record/class.

However, not every lambda is short. A lambda with multiple `if/else` branches, `null` checks, business rules, format conversions, or service calls makes the `filter`/`map` block hard to understand, hard to debug, and hard to test independently.

The example below describes a discount policy:

```java
List<Integer> totals = orders.stream()
        .map(order -> {
            if (order == null) {
                throw new IllegalArgumentException("order is null");
            }
            int subtotal = order.subtotal();
            if (subtotal < 0) {
                throw new IllegalArgumentException("negative subtotal");
            }
            int percent;
            if (order.member()) {
                percent = 20;
            } else if (subtotal >= 100) {
                percent = 10;
            } else {
                percent = 0;
            }
            return subtotal * (100 - percent) / 100;
        })
        .toList();
```

This illustrative snippet assumes each `Order` has `subtotal()` and `member()`. It may run properly, yet testing a case like subtotal equal to 100 requires going through a Stream. The business details also obscure the pipeline's main intent: "turn each order into its final amount".

After **extract method**:

```java
List<Integer> totals = orders.stream()
        .map(PricingRules::calculateNetAmount)
        .toList();
```

The method `calculateNetAmount(Order)` has a meaningful name; it can be called directly in tests to verify every branch and exception. The pipeline becomes easier to read because it describes **what it does**, while the method describes **how it does it**.

**The core benefit is testability**: isolating a unit of logic with clear inputs and outputs for direct testing, rather than testing rules only through a Stream terminal operation. You do not need to extract every lambda; extraction should make the code easier to understand and the logic independently verifiable.

## 2. When is a lambda worth extracting?

Consider extracting when:

1. It has multiple `if`, `switch`, or complex conditional combinations that are hard to follow.
2. It contains a named business rule, such as "eligible for refund" or "discounted price".
3. It has many edge cases: null, empty, negative, exact threshold, above threshold.
4. The same logic needs to be reused across Streams, Optional, another service, or imperative code.
5. You want to write unit tests checking each branch, exception, and result without setting up a full pipeline.
6. There are external dependencies (repository, clock, HTTP) that should be separated from computation.
7. A long lambda keeps the pipeline from clearly expressing data structure.
8. You need to debug or set breakpoints on a specific rule.
9. Clear policies are needed for rounding, case sensitivity, or null.
10. The new method name helps readers understand the meaning without decoding conditionals.

Do not extract unconditionally:

- `n -> n * 2` is usually clear enough.
- `String::trim` is already the name of an operation.
- `p -> p.active()` can use `Person::active`.
- A helper that only wraps a trivial operation without adding meaning in its name adds unnecessary indirection.

Consider **responsibility structure**, not just line count. A one-line lambda `x -> service.save(x)` with side effects can still be very hard to test, whereas a long but pure boolean expression can become easy to test once placed in a well-named method.

## 3. How to refactor step by step without changing behavior

A practical approach:

1. Identify the lambda's input, return type, and possible exceptions.
2. List the logic branches and current input/output examples.
3. Name the method after its business purpose.
4. Move the body into the method, preserving condition order and exception rules.
5. Replace the original lambda with a method reference or thin lambda.
6. Write unit tests for the new method, including boundaries and errors.
7. Test a small pipeline to verify `filter/map/collect` wiring.
8. Only optimize or simplify logic after behavior has been verified.

Diagram:

```text
Before:
Stream<Order> ── map(lambda: validate + calculate) ──> Stream<Integer>

After:
Stream<Order> ── map(PricingRules::calculateNetAmount) ──> Stream<Integer>
                            │
                            └── direct unit tests:
                                null, -1, 0, 99, 100, member
```

**Refactoring does not authorize changing business behavior.** If the new method rounds in a different place, reorders conditions with side effects, or swallows an exception that used to be thrown, that is a behavioral change and must be reviewed and tested as a functional change.

## 4. Standalone runnable example: extracting pricing rules

Create the file `PricingRefactorDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public class PricingRefactorDemo {
    record Order(String id, int subtotal, boolean member) {}

    static final class PricingRules {
        private PricingRules() {}

        static int calculateNetAmount(Order order) {
            Objects.requireNonNull(order, "order");

            int subtotal = order.subtotal();
            if (subtotal < 0) {
                throw new IllegalArgumentException("negative subtotal");
            }

            int discountPercent;
            if (order.member()) {
                discountPercent = 20;
            } else if (subtotal >= 100) {
                discountPercent = 10;
            } else {
                discountPercent = 0;
            }

            return subtotal * (100 - discountPercent) / 100;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 120, true),
                new Order("B", 80, false),
                new Order("C", 200, false),
                new Order("D", 150, true)
        );

        List<Integer> nets = orders.stream()
                .map(PricingRules::calculateNetAmount)
                .toList();

        System.out.println("nets=" + nets);
        System.out.println("A=" +
                PricingRules.calculateNetAmount(orders.get(0)));
        System.out.println("C=" +
                PricingRules.calculateNetAmount(orders.get(2)));
    }
}
```

Run with JDK 17 or newer:

```bash
javac PricingRefactorDemo.java
java PricingRefactorDemo
```

Output:

```text
nets=[96, 80, 180, 120]
A=96
C=180
```

Explanation: A and D receive a 20% discount as members; B gets no discount because subtotal is under 100 and not a member; C is not a member but reaches the 100 threshold so it gets a 10% discount.

The pipeline only has `map(PricingRules::calculateNetAmount)`. `calculateNetAmount` is responsible for validation and calculation. It takes an `Order`, returns an integer, and can be tested with ordinary method calls without building a Stream.

**Limitation of the example**: this uses small-integer math to illustrate refactoring; for real money, you must design currency units, handle overflow, use rounding division, and possibly use `BigDecimal` per business policy. Do not take the integer formula above as a general monetary solution.

## 5. Testing the method directly: branch, boundary, exception

Basic test case table:

| Input | Branch tested | Expected |
| --- | --- | --- |
| (120, member=true) | 20% member branch | 96 |
| (80, member=false) | No discount | 80 |
| (100, member=false) | Exact 10% threshold | 90 |
| (99, member=false) | Just below threshold | 99 |
| (0, member=true) | Zero amount | 0 |
| (-1, member=false) | Invalid value | `IllegalArgumentException` |
| null Order | Missing input | `NullPointerException` |

Testing 99 and 100 is important because that is the **condition boundary**. Testing only 200 does not prove `>=` was used instead of `>`.

Create the file `PricingRulesTestDemo.java` — runs standalone without JUnit:

```java
import java.util.Objects;

public class PricingRulesTestDemo {
    record Order(int subtotal, boolean member) {}

    static int calculateNetAmount(Order order) {
        Objects.requireNonNull(order, "order");
        if (order.subtotal() < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }

        int rate = order.member()
                ? 20
                : (order.subtotal() >= 100 ? 10 : 0);

        return order.subtotal() * (100 - rate) / 100;
    }

    static void check(String title, int expected, int actual) {
        if (expected != actual) {
            throw new AssertionError(title +
                    ": expected " + expected + ", got " + actual);
        }
        System.out.println("PASS " + title);
    }

    static void expectException(String title,
            Class<? extends Throwable> expected,
            Runnable operation) {
        try {
            operation.run();
            throw new AssertionError(title + ": no exception");
        } catch (Throwable error) {
            if (!expected.isInstance(error)) {
                throw new AssertionError(
                        title + ": unexpected exception", error);
            }
            System.out.println("PASS " + title);
        }
    }

    public static void main(String[] args) {
        check("member", 96,
                calculateNetAmount(new Order(120, true)));
        check("regular", 80,
                calculateNetAmount(new Order(80, false)));
        check("threshold", 90,
                calculateNetAmount(new Order(100, false)));
        check("below threshold", 99,
                calculateNetAmount(new Order(99, false)));
        check("zero", 0,
                calculateNetAmount(new Order(0, true)));

        expectException("negative",
                IllegalArgumentException.class,
                () -> calculateNetAmount(new Order(-1, false)));
        expectException("null",
                NullPointerException.class,
                () -> calculateNetAmount(null));
    }
}
```

Compile/run:

```bash
javac PricingRulesTestDemo.java
java PricingRulesTestDemo
```

Stdout:

```text
PASS member
PASS regular
PASS threshold
PASS below threshold
PASS zero
PASS negative
PASS null
```

This is a self-contained demo: to keep example files independent, it defines a version of the function inside the test file. In a **real project**, you must test the **actual production class `PricingRules`**, not copy the formula into the test. If you copy it, production code and test code can share the same bug, making the check meaningless. Place the production class in a package with a testable API and call it from the test class.

## 6. Extracting long Predicates in `Stream.filter`

A lambda in `filter` has type `Predicate<T>`: each call to `test(T)` returns boolean.

Example condition:

```java
orders.stream()
        .filter(o -> o != null
                && o.approved()
                && o.quantity() > 0
                && o.unitPrice() > 0
                && (long) o.quantity() * o.unitPrice() >= 100)
        .toList();
```

This is an illustrative snippet inside a method with an `Order` record having matching accessors. Reading this, others have to infer "what makes an order eligible". Extract it into:

```java
static boolean isEligible(Order order) {
    if (order == null || !order.approved()) {
        return false;
    }
    if (order.quantity() <= 0 || order.unitPrice() <= 0) {
        return false;
    }
    return (long) order.quantity() * order.unitPrice() >= 100;
}
```

Then call `filter(OrderRules::isEligible)` when the method lives in `OrderRules`.

Casting to `long` before multiplication avoids `int` overflow when multiplying two typical positive `int` values; however, if data has extreme values or requires large totals, you still need explicit value-range control.

### Standalone Predicate test program

Save `PredicateExtractionDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class PredicateExtractionDemo {
    record Order(String code, int quantity,
                 int unitPrice, boolean approved) {}

    static boolean isEligible(Order order) {
        if (order == null || !order.approved()) {
            return false;
        }
        if (order.quantity() <= 0 || order.unitPrice() <= 0) {
            return false;
        }
        return (long) order.quantity() * order.unitPrice() >= 100;
    }

    static void check(String name, boolean expected, boolean actual) {
        if (expected != actual) {
            throw new AssertionError(name);
        }
        System.out.println("PASS " + name);
    }

    public static void main(String[] args) {
        List<Order> orders = new ArrayList<>();
        orders.add(new Order("A", 2, 60, true));
        orders.add(new Order("B", 1, 80, true));
        orders.add(new Order("C", 1, 200, false));
        orders.add(new Order("D", 5, 20, true));
        orders.add(null);

        check("approved enough",
                true, isEligible(orders.get(0)));
        check("below threshold",
                false, isEligible(orders.get(1)));
        check("not approved",
                false, isEligible(orders.get(2)));
        check("boundary",
                true, isEligible(orders.get(3)));
        check("null",
                false, isEligible(null));

        List<String> accepted = orders.stream()
                .filter(PredicateExtractionDemo::isEligible)
                .map(Order::code)
                .toList();

        System.out.println("accepted=" + accepted);
    }
}
```

Run:

```bash
javac PredicateExtractionDemo.java
java PredicateExtractionDemo
```

Result:

```text
PASS approved enough
PASS below threshold
PASS not approved
PASS boundary
PASS null
accepted=[A, D]
```

`isEligible` is tested independently with five scenarios. The pipeline test verifies that `filter` keeps A and D and `map(Order::code)` extracts their codes. Because the source contains null, the example uses `ArrayList`; `List.of(...)` rejects null elements.

In a real application, decide clearly whether `null` means "not eligible" or "corrupt data that must fail". Both policies can be valid in different contexts; do not silently filter out null if business rules require detecting input errors.

## 7. Extracting complex Functions in `Stream.map`

`map` takes a `Function<T,R>`, meaning an input value T is transformed into R. If string-normalization logic involves null, trim, and case conversion, extract it into a separate method instead of placing multiple statements inside the lambda.

Example method:

```java
static String normalizeName(String rawName) {
    if (rawName == null) {
        return "";
    }
    String trimmed = rawName.trim();
    return trimmed.isEmpty()
            ? ""
            : trimmed.toUpperCase(Locale.ROOT);
}
```

Code inside a class importing `Locale`. When used:

```java
List<String> normalized = names.stream()
        .map(NameRules::normalizeName)
        .toList();
```

This example assumes a `NameRules` class and a `names` variable. The mapper now has an explanatory name and can be tested with null, blank, mixed-case, and leading/trailing spaces. `Locale.ROOT` keeps uppercasing independent of the machine's locale, though `trim()` does not handle every kind of Unicode whitespace. Actual normalization rules must be stated explicitly.

### Standalone demo for the normalize method

Create `NormalizeNameTestDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class NormalizeNameTestDemo {
    static String normalizeName(String rawName) {
        if (rawName == null) {
            return "";
        }
        String trimmed = rawName.trim();
        return trimmed.isEmpty()
                ? ""
                : trimmed.toUpperCase(Locale.ROOT);
    }

    static void check(String title, String expected, String actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(title + ": " + actual);
        }
        System.out.println("PASS " + title);
    }

    public static void main(String[] args) {
        check("null", "", normalizeName(null));
        check("blank", "", normalizeName("   "));
        check("trim", "LAN", normalizeName(" lan "));
        check("already uppercase", "AN", normalizeName("AN"));

        List<String> inputs = new ArrayList<>();
        inputs.add("  minh ");
        inputs.add(null);
        inputs.add(" an ");
        inputs.add("   ");

        List<String> result = inputs.stream()
                .map(NormalizeNameTestDemo::normalizeName)
                .toList();

        System.out.println("mapped=" + result);
    }
}
```

Run:

```bash
javac NormalizeNameTestDemo.java
java NormalizeNameTestDemo
```

Output:

```text
PASS null
PASS blank
PASS trim
PASS already uppercase
mapped=[MINH, , AN, ]
```

`map` does not automatically drop empty strings; the two elements normalized to `""` remain in the result. If the problem requires keeping only non-empty names, add `filter(s -> !s.isEmpty())` after normalization, or change the policy. Do not assume a method named "normalize" automatically filters data.

## 8. Method references keep pipelines coherent

Common forms:

| Lambda | Method reference | Meaning |
| --- | --- | --- |
| `x -> Rules.isValid(x)` | `Rules::isValid` | Static method |
| `x -> x.name()` | `Person::name` | Method called on the input itself |
| `x -> service.normalize(x)` | `service::normalize` | Bound instance method |
| `() -> Factory.empty()` | `Factory::empty` | Static supplier |
| `x -> new Result(x)` | `Result::new` | Constructor |
| `(a, b) -> a.compareTo(b)` | `String::compareTo` | Two-parameter unbound instance method |

A method reference does not make a lambda run eagerly. For example, `map(Rules::transform)` is still an intermediate operation; the body of `transform` does not execute just because the pipeline is constructed.

You cannot always convert to a method reference: if the method takes an extra threshold parameter, the pipeline can keep a short lambda:

```java
int minPoints = 100;
customers.stream()
        .filter(c -> CustomerRules.isEligible(c, minPoints))
        .toList();
```

Illustrative snippet with appropriate variables and class. `minPoints` must be final or effectively final. Do not try to write `filter(CustomerRules::isEligible)` if the method takes two parameters while `Predicate<Customer>` only supplies one.

You can create a factory:

```java
static Predicate<Customer> atLeast(int threshold) {
    return c -> c != null && c.points() >= threshold;
}
```

and `stream.filter(atLeast(100))` when configuration reuse is needed. This is a method inside a class with `Customer.points()` and `Predicate` imported.

## 9. Functional interfaces shape the extracted method

| API used | Callback contract | Extractable method signature |
| --- | --- | --- |
| `Stream.filter` | `Predicate<T>` | `boolean isEligible(T value)` |
| `Stream.map` | `Function<T,R>` | `R toResult(T value)` |
| `Stream.flatMap` | `Function<T,Stream<R>>` | `Stream<R> expand(T value)` |
| `Stream.forEach` | `Consumer<T>` | `void handle(T value)` |
| `Optional.map` | `Function<T,R>` | `R transform(T value)` |
| `Stream.reduce` | `BinaryOperator<T>` | `T combine(T a,T b)` |
| `IntStream.filter` | `IntPredicate` | `boolean test(int value)` |
| `IntStream.map` | `IntUnaryOperator` | `int transform(int value)` |
| `Comparator.comparing` | `Function<T,U>` | `U extractKey(T value)` |

Extracting a method must preserve **parameter types, return type, nullability, and checked exceptions**. For instance, `Predicate<T>` returns `boolean`, not `Optional<T>`. `Function<T,R>` takes one element and returns a transformed result; it cannot emit multiple elements: if one input needs to produce multiple outputs, you usually need `flatMap` with a method returning `Stream<R>`.

Do not use raw types `Function` or `Predicate` just to satisfy the compiler; declaring explicit generics makes tests accurate and IDE refactoring safer.

## 10. How do direct unit tests differ from pipeline tests?

A **unit test** of a rule method answers: "For a specific input, does the rule return the right result or expected error?"

A **pipeline test** answers: "Are the rules wired into the right stages, in the right order, with the right types?"

For example, to keep normalized names of at least three characters:

```java
List<String> selected = names.stream()
        .map(NameRules::normalizeName)
        .filter(s -> s.length() >= 3)
        .toList();
```

A pipeline test also checks that `map` comes before `filter`; if `filter(s -> s.length() >= 3)` is written before `map`, null can cause `NullPointerException` and length would be measured on untrimmed strings. A `normalizeName` method that is individually right **does not guarantee the pipeline is wired properly**.

A good strategy:

1. Thoroughly test rule logic at the method level: every branch, null, boundary, exception.
2. Use only a few representative inputs at the pipeline level to check stage order and result structure.
3. If there is external I/O, add appropriate integration tests; do not cram all dependency testing into unit tests of computation functions.

This keeps tests fast, failure reasons clear, and avoids repeating the same many cases across every layer.

## 11. Pure functions and stable testability

A **pure function** does not mutate external state and returns the same result for the same input (under deterministic conditions). Pure rules are easy to test:

- No database, network, or system clock needed.
- No dependency on global variables that can change between tests.
- No mocks needed for simple calculations, validations, or formatting.
- Can be called repeatedly and outputs compared.
- Generally safer to use in parallel streams, provided the processed objects themselves are not concurrently mutated either.

Examples:

```java
static boolean isAdult(int age) {
    return age >= 18;
}
```

or:

```java
static int pointsAfterBonus(int points, int bonus) {
    return Math.addExact(points, bonus);
}
```

These are class methods without I/O. `Math.addExact` throws `ArithmeticException` if integer addition overflows — a testable behavior.

By contrast, a `calculatePrice(order)` method that fetches exchange rates from the web, reads the clock, and updates the database is no longer pure computation. Merely moving it out of a lambda does not make testing simple. Separate data fetching (effects) from pure computation and pass required dependencies/configuration via parameters or constructors.

## 12. Separating side effects to avoid hidden Stream bugs

Lambdas for `map` and `filter` should be **stateless and non-interfering** per Java Stream rules. Putting side effects inside a lambda can cause problems:

```java
List<String> audit = new ArrayList<>();
List<Order> selected = orders.parallelStream()
        .filter(order -> {
            audit.add(order.id());
            return order.approved();
        })
        .toList();
```

This is a **counterexample**, assuming `orders`, `Order`, and `ArrayList`. `audit` is unsynchronized shared mutable state; parallel execution can cause races or lost elements. Even if you extract the lambda body to `Rules::auditAndCheck`, the side effect still exists and the risk does not disappear.

Moreover, pipelines using short-circuiting like `findFirst` or optimizations like `count` may **not invoke every callback**. Do not use logging/auditing inside `peek` or `map` as a business guarantee.

If you want to:

- **filter**: use `filter(Rules::isEligible)` with a pure predicate;
- **count**: use `count()`, a collector, or a corresponding statistics step;
- **mandatory audit**: design a dedicated audit operation with an explicit contract for ordering, errors, and idempotency;
- **write to DB**: perform it at a clear boundary, with required transactions and error handling.

Good refactoring makes side effects **visible at clear boundaries**, rather than hiding them behind a method reference.

## 13. Exceptions and null: preserve the contract when extracting

A change that often happens accidentally during refactoring: turning `throw` into `return null`, or turning "fail immediately on bad data" into "silently drop data". Those two behaviors are different.

Example:

```java
static int parseQuantity(String raw) {
    Objects.requireNonNull(raw, "raw");
    int value = Integer.parseInt(raw);
    if (value < 0) {
        throw new IllegalArgumentException("negative quantity");
    }
    return value;
}
```

This is a method inside a class importing `Objects`. Unit tests should check:

- `"12"` → 12.
- `"0"` → 0.
- `"-1"` → `IllegalArgumentException`.
- `"abc"` → `NumberFormatException`.
- `null` → `NullPointerException`.

If used in `stream.map(Rules::parseQuantity)`, exceptions occur when the mapper is invoked while the terminal operation consumes the Stream. Extracting the method **does not** cause parsing to run eagerly when building the pipeline.

For checked exceptions, standard functional interfaces like `Function.apply` and `Predicate.test` do not declare checked exceptions. If a method calls an API throwing `IOException`, design appropriate handling or an abstraction; you cannot use a method reference alone to bypass compiler constraints.

## 14. JUnit 5: example with a real test framework

If the project already has JUnit Jupiter installed, you can use `@Test`, `assertEquals`, and `assertThrows`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class PricingRulesTest {
    @Test
    void thresholdIsInclusive() {
        assertEquals(90,
                PricingRules.calculateNetAmount(
                        new Order("X", 100, false)));
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> PricingRules.calculateNetAmount(
                        new Order("X", -1, false)));
    }
}
```

**This is illustrative code for a project with JUnit 5**, having `Order` and `PricingRules` classes with appropriate visibility. JUnit **is not included in the standard JDK**, so you cannot take this file and run it with `javac`/`java` on an empty classpath. The `*Demo.java` programs in this lesson are standalone Java 17 examples.

Test the actual production code instead of copying the formula into the test class. If a method is `private`, you do not have to make it `public` just to test it: you can test through the public contract or place the business rule in a separate component with sensible visibility. Encapsulation remains a design requirement.

## 15. Static method, instance method, or service method?

Extracting logic does not force the method to be static.

**Static methods** fit pure calculations, validations, or formatting that do not depend on state.

**Instance methods** fit when behavior depends on immutable configuration or injected collaborators:

```java
PriceService service = new PriceService(policy);

List<Result> mapped = orders.stream()
        .map(service::calculate)
        .toList();
```

This illustrative snippet assumes `PriceService`, `policy`, `Result`, and `orders` are appropriately defined; `service::calculate` is a bound instance method reference. To test, inject a fake policy or a dependency with deterministic behavior.

**Domain methods** fit an object's natural behavior, e.g. `Order::isExpired` if expiration calculation truly belongs on Order and the needed parameters are present.

**Service methods** make sense when coordinating multiple dependencies, though you should still separate service orchestration from core logic that can be tested independently.

Do not create an oversized "utils" class holding unrelated rules. Methods should live where they make sense for the domain/module's responsibilities.

## 16. Multi-parameter methods: a thin lambda is still a good refactor

Suppose the check function takes an additional threshold:

```java
static boolean isEligible(Order order, int minimumAmount) {
    return order != null && order.total() >= minimumAmount;
}
```

Used in `filter`:

```java
int minimumAmount = 100;
List<Order> accepted = orders.stream()
        .filter(order -> isEligible(order, minimumAmount))
        .toList();
```

These two snippets are illustrations inside a class with an appropriate `Order` record and `orders` variable; `minimumAmount` is effectively final.

You cannot automatically change this to `filter(Rules::isEligible)` if `isEligible` takes two parameters while `Predicate<Order>` supplies only one. A thin lambda like the one above still achieves the goal: the business rule lives in a named method, and the pipeline only passes configuration.

When reused often, a factory returning a Predicate can be clearer:

```java
static Predicate<Order> atLeast(int threshold) {
    return order ->
            order != null && order.total() >= threshold;
}
```

Then call `orders.stream().filter(atLeast(100))`. The factory can be unit tested with `atLeast(100).test(order)`.

## 17. Testing by levels: method, pipeline, integration

A strategy you can apply in projects:

**Level 1 — Method-level tests:** normal values, boundaries, null, missing data, exceptions. This is the largest portion when logic is complex.

**Level 2 — Pipeline-level tests:** verify stage order, data types, grouping/sorting, result order, empty or duplicate cases. No need to repeat every business branch at this level once the method is tested separately.

**Level 3 — Integration tests:** only for real dependencies (DB, network, file, clock) when the system requires them. You can use fakes/mocks to unit test services, though certain resource/transaction contracts need verification in an integrated environment.

Example of a name-transforming pipeline:

```java
List<String> result = names.stream()
        .map(NameRules::normalizeName)
        .filter(s -> !s.isEmpty())
        .toList();
```

Method tests answer whether normalization is right. Pipeline tests answer whether null is normalized **before** filtering, and whether names are kept in encounter order. The two test levels catch different kinds of bugs.

## 18. Do not misunderstand lazy evaluation when testing

Extracting a method does not change Stream laziness:

```java
Stream<Order> pipeline = orders.stream()
        .filter(Rules::isEligible)
        .map(Rules::toDto);
```

In the lines above, the method references are bound into the pipeline, yet the bodies of `isEligible`/`toDto` have usually not been called for each element yet. When a terminal operation like `toList()` is invoked, the stages are evaluated on demand.

With short-circuiting, some elements never reach the mapper. With `count()` on a sized source and cardinality-preserving stages, the framework may skip some mapper calls. Therefore:

- **Unit test logic** by calling the method directly.
- **Pipeline test** by comparing meaningful outputs.
- Do not assert "the method must log exactly n times" as a general contract of intermediate operations.
- Do not reuse a Stream already consumed by a terminal operation.
- With parallel streams, do not infer callback order from result order.

This is also why extracting methods makes tests reliable: they do not depend on Stream optimization strategies to trigger a logic branch.

## 19. Self-practice exercise

Given record `Customer(String name, int points, boolean active)` and a list `customers`. Requirement: keep active customers with 100 or more points and a non-null/non-blank name.

Initial lambda:

```java
List<Customer> selected = customers.stream()
        .filter(c -> c != null
                && c.active()
                && c.points() >= 100
                && c.name() != null
                && !c.name().isBlank())
        .toList();
```

Snippet inside a method with an appropriate `customers` list.

Exercises:

1. Extract into `static boolean isEligibleCustomer(Customer c)`.
2. Use a method reference in `filter`.
3. Test points at exact 100 and just below at 99.
4. Test null object, null name, blank name, and active false.
5. Test a pipeline with three customers where only one is eligible.
6. Explain why `map(Customer::name)` should come after `filter` if the Predicate needs the `active` and `points` fields.
7. If names must be uppercased or trimmed, what additional method should you extract for testing?

Illustrative solution in `CustomerRules`:

```java
static boolean isEligibleCustomer(Customer c) {
    return c != null
            && c.active()
            && c.points() >= 100
            && c.name() != null
            && !c.name().isBlank();
}
```

Usage:

```java
List<String> names = customers.stream()
        .filter(CustomerRules::isEligibleCustomer)
        .map(Customer::name)
        .toList();
```

Here `CustomerRules` is a class containing the method; the snippets are not standalone programs. Suggested tests:

- `new Customer("Lan", 100, true)` → true.
- `new Customer("Lan", 99, true)` → false.
- `new Customer("Lan", 120, false)` → false.
- `new Customer(null, 120, true)` → false.
- `new Customer("   ", 120, true)` → false.
- `null` → false.

If normalization is needed, you can write `normalizeCustomerName(String name)` and call it after `map(Customer::name)`, with clear null/whitespace/locale policies. Do not cram validation, normalization, DB writes, and auditing into one helper just to keep the pipeline on a single line.

## 20. Common mistakes

1. **Extracting only to shorten the lambda** while naming the method generically like `doIt`; name it after the rule.
2. **Keeping 100 lines inside the new method** mixing I/O, validation, calculation, and persistence; coupling is not truly reduced.
3. **Copying the formula into the test** instead of calling production code, allowing both to share the same bug.
4. **Testing only the happy path** while skipping thresholds 99/100, empty inputs, null, and exceptions.
5. **Changing conditions during refactoring** without treating it as a behavioral change.
6. **Hiding side effects inside a method reference**; parallel streams can race, and short-circuiting can skip callbacks.
7. **Turning a method static even when explicit state/dependencies are needed**; choose the right design.
8. **Making a private method public at all costs** just to call it from tests, weakening encapsulation unnecessarily.
9. **Trying to use a method reference for a two-parameter function** in a one-parameter `filter`; use a thin lambda or factory.
10. **Not preserving exception/null policies**; swallowing errors with `return null` can hide issues.
11. **Not re-testing the pipeline after extraction**; stage order or generic types may be wrong.
12. **Testing log order** instead of materialized results of a parallel stream.
13. **Reusing a consumed Stream** to run multiple checks; create a new stream from the collection.
14. **Assuming method references are always faster than lambdas**; the main goal is clarity, and performance must be measured.
15. **Splitting a trivial calculation across many helper classes**, making code harder to navigate.
16. **Dropping business parameters** by passing only the input object and reading values from mutable global variables.
17. **Confusing Predicate and Function**; `filter` requires boolean whereas `map` requires a transformed value.
18. **Calling I/O from a supposedly pure rule**, making unit tests depend on the machine or external data.
19. **Changing rounding and overflow handling** when moving computation, altering numeric results.
20. **Using separate methods as the sole metric of good code**; readability, testability, and correctness are the real criteria.

## 21. Adoption checklist

Before finishing a refactor, self-check:

- What type does the original lambda take, and what type must it return?
- Does the new method have a name representing an independent rule?
- Are branches, null, exceptions, and boundaries clearly specified?
- If there is I/O or mutable state, are responsibility and thread safety defined?
- Does a method reference match the types, or is a thin lambda needed?
- Do unit tests call the real **production method**?
- Does a pipeline test verify stage order and output?
- Are there empty-source, duplicate, or ordered/unordered scenarios affecting output?
- Are any side effects depending on how many times the Stream framework invokes the callback?
- Does the refactor make the overall code easier to understand?

**Conclusion:** a complex lambda should be extracted into a **named method with clear inputs, outputs, and contract** when doing so enables independent testing and keeps the pipeline focused on data flow. For simple lambdas, keeping them inline is often better. The goal is to improve maintainability and logic verification, not merely to turn `x -> f(x)` into `Class::f`.

**References:** Java SE 17 API `java.util.function.Predicate`, `Function`, `Consumer`, `java.util.stream.Stream.map`, `Stream.filter`, Java Language Specification on lambdas/method references, JUnit 5 User Guide on tests and assertions.
