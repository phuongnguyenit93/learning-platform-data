# Checking Conditions with anyMatch, allMatch, and noneMatch

> **Chapter:** Traversal, Search, and Matching  
> **Module:** JAVA_STREAM_API  
> **Focus:** Three `boolean`-returning terminal operations of the Java Stream API: `anyMatch`, `allMatch`, and `noneMatch`. They check conditions across elements declaratively, leverage lazy pipelines, and can stop early (*short-circuit*).

## Learning Objectives

After this lesson, you can:

1. Accurately explain the meaning of `anyMatch`, `allMatch`, and `noneMatch` through the quantifiers “exists”, “for all”, and “does not exist”.
2. Predict results on non-empty Streams and **empty Streams**, including cases where all elements are filtered out.
3. Distinguish the `boolean` result of these three operations from the `Optional` result of `findFirst`/`findAny`.
4. Describe **terminal** behavior, **short-circuiting**, evaluation order, and behavior in parallel Streams.
5. Build safe predicates that do not interfere with the source, and express combined or nested conditions.
6. Choose the right API for validation, error detection, data confirmation, and searching.
7. Recognize pitfalls involving shared state, infinite sources, single-use Streams, and I/O resources.

Examples use Java 17. The `anyMatch`, `allMatch`, and `noneMatch` operations and their primitive Stream variants exist since Java 8; examples using `List.of` require Java 9+ and `Stream.toList` (where used) requires Java 16+. Short snippets sit in a method context unless a complete class is declared.

## 1. Three Different Questions on the Same Stream

Suppose a list of scores is `[7, 8, 10, 5]`. We want to ask:

- **Is there at least one score of 10?** Use `anyMatch`.
- **Are all scores between 0 and 10?** Use `allMatch`.
- **Are we sure there are no negative scores?** Use `noneMatch`.

~~~java
import java.util.List;

List<Integer> scores = List.of(7, 8, 10, 5);

boolean hasPerfectScore = scores.stream()
        .anyMatch(score -> score == 10);

boolean allInRange = scores.stream()
        .allMatch(score -> score >= 0 && score <= 10);

boolean noNegativeScore = scores.stream()
        .noneMatch(score -> score < 0);

System.out.println(hasPerfectScore); // true
System.out.println(allInRange);       // true
System.out.println(noNegativeScore);  // true
~~~

All three methods accept a **predicate**: a function returning `true` or `false` for each element. They are **terminal operations**, returning **a single** `boolean` value and consuming the Stream.

| Method | Question with predicate `P` | When is the result `true`? | Can stop immediately when… |
|---|---|---|---|
| `anyMatch(P)` | Does **at least one** element satisfy `P`? | An element with `P(x) == true` exists | An element satisfying `P` is found |
| `allMatch(P)` | Do **all** elements satisfy `P`? | No element violates `P` | An element **not** satisfying `P` is found |
| `noneMatch(P)` | Do **no** elements satisfy `P`? | No element satisfies `P` exists | An element satisfying `P` is found |

With a finite source, if no early-stopping condition is encountered, the operation must examine enough elements to reach a conclusion. None of these methods return a list of matching elements: their result is always `boolean`.

## 2. Logical Meaning: Exists, For All, and None Exists

Let `S` denote the set of elements the Stream will supply, and `P(x)` be the condition applied to element `x`:

| Java | Logical expression | Verbal reading |
|---|---|---|
| `stream.anyMatch(P)` | \(\exists x \in S: P(x)\) | There exists at least one `x` making `P` true |
| `stream.allMatch(P)` | \(\forall x \in S: P(x)\) | For every `x` in the source, `P` is true |
| `stream.noneMatch(P)` | \(\nexists x \in S: P(x)\) | There exists no `x` making `P` true |

These quantifiers immediately explain the short-circuiting behavior:

- To prove **existence**, only one matching element is needed.
- To disprove **all elements match**, only one counterexample is needed.
- To disprove **none exists**, finding one matching element suffices.

Example:

~~~java
import java.util.List;

List<Integer> values = List.of(2, 4, 7, 8);

boolean anyOdd  = values.stream().anyMatch(n -> n % 2 != 0);
boolean allEven = values.stream().allMatch(n -> n % 2 == 0);
boolean noZero  = values.stream().noneMatch(n -> n == 0);

System.out.println(anyOdd);  // true  — 7 is present
System.out.println(allEven); // false — 7 is a counterexample
System.out.println(noZero);  // true  — no 0 present
~~~

**Distinguish meanings:** `noneMatch(P)` means “no element satisfies `P`”, while `allMatch(P)` means “every element satisfies `P`”. They are not two ways of asking the same question.

## 3. The Most Error-Prone Case: An Empty Stream

Consider a Stream **containing no elements**:

~~~java
import java.util.stream.Stream;

System.out.println(Stream.<Integer>empty()
        .anyMatch(n -> n > 0));   // false

System.out.println(Stream.<Integer>empty()
        .allMatch(n -> n > 0));   // true

System.out.println(Stream.<Integer>empty()
        .noneMatch(n -> n > 0));  // true
~~~

Result table:

| Source after intermediate operations | `anyMatch(P)` | `allMatch(P)` | `noneMatch(P)` |
|---|---|---|---|
| Empty stream | **false** | **true** | **true** |
| Non-empty and all satisfy `P` | true | true | false |
| Non-empty and none satisfy `P` | false | false | true |
| Non-empty and some satisfy, some do not | true | false | false |

**Why does `allMatch` on an empty Stream return `true`?** There is no element contradicting the statement “every element matches”. In logic, this is **vacuous truth**. Similarly, no element satisfies the predicate, so `noneMatch` is `true` and `anyMatch` is `false`.

There is no need to invoke the predicate on an empty Stream; in fact, there are no elements to pass into the predicate.

### 3.1. Filtering Out Everything Also Produces an Empty Case

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3);

boolean result = values.stream()
        .filter(n -> n > 100)
        .allMatch(n -> n % 2 == 0);

System.out.println(result); // true
~~~

The result `true` here **does not mean** the program found an even number above 100. The `filter` pipeline excluded every element; `allMatch` received an empty Stream and returned `true`.

### 3.2. If Business Logic Requires at Least One Element, State It Explicitly

For example, “every product code must be valid **and the list must have at least one code**”:

~~~java
import java.util.List;

List<String> productCodes = List.of("SP01", "SP02");

boolean validBatch = !productCodes.isEmpty()
        && productCodes.stream()
                .allMatch(code -> code.startsWith("SP"));

System.out.println(validBatch); // true
~~~

With `List.of()`, `validBatch` will be `false`, because the **non-empty** check is evaluated separately. If the source is only a single-use Stream, do not call `count()` and then `allMatch()` on the **same Stream object**: the first terminal operation already consumed it. When you need both “non-empty” and “all elements valid” on a single-pass source, consider designing an appropriate aggregation or checking from a reusable source.

### 3.3. `noneMatch` on Empty Is Also True

~~~java
import java.util.List;

List<String> names = List.of();

boolean noBlankNames = names.stream()
        .noneMatch(String::isBlank);

System.out.println(noBlankNames); // true
~~~

This only confirms **no blank names were detected**; it does not confirm the list contains names. Separate the requirement “must not be empty” from “no violating elements”.

## 4. How Do Terminal Operations and Short-Circuiting Work?

`anyMatch`, `allMatch`, and `noneMatch` are all **short-circuiting terminal operations**. They **can** finish before traversing all elements once enough information is gathered to decide the outcome.

Observation example in an **ordered sequential Stream**:

~~~java
import java.util.List;

List<Integer> numbers = List.of(2, 5, 8, 13);

boolean found = numbers.stream()
        .anyMatch(n -> {
            System.out.println("Checking: " + n);
            return n > 6;
        });

System.out.println("Result: " + found);
~~~

With this sequential pipeline on a `List`, illustrative output:

~~~text
Checking: 2
Checking: 5
Checking: 8
Result: true
~~~

Element `13` does not need to be checked: `8 > 6` already proves “at least one element matches”.

Two similar cases:

~~~java
import java.util.List;

List<Integer> numbers = List.of(2, 5, 8, 13);

boolean allSmall = numbers.stream()
        .allMatch(n -> n < 10); // false upon encountering 13

boolean noneEqualFive = numbers.stream()
        .noneMatch(n -> n == 5); // false upon encountering 5

System.out.println(allSmall);     // false
System.out.println(noneEqualFive);// false
~~~

**Understand “can stop early” within its proper bounds:** the `boolean` result is guaranteed by contract; how many elements get evaluated, the order of predicate calls, and when in-flight work is cancelled are **not contracts for business logic to depend on**, especially in parallel Streams. The `println` snippet is solely for observing a sequential pipeline.

### 4.1. Lazy Intermediate Operations, Matching Operations Trigger the Pipeline

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> names = List.of("An", "Bình", "Chi");

Stream<String> pipeline = names.stream()
        .filter(name -> name.length() >= 2)
        .map(String::toUpperCase);

boolean hasBinh = pipeline.anyMatch("BÌNH"::equals);

System.out.println(hasBinh); // true
~~~

`filter` and `map` set up the pipeline; `anyMatch` triggers traversal as needed. Afterward, the `pipeline` variable has been consumed and **cannot be reused** for another terminal operation.

To run other checks, create a **new** Stream from `names`:

~~~java
boolean allNonBlank = names.stream().allMatch(name -> !name.isBlank());
boolean noVeryLong = names.stream().noneMatch(name -> name.length() > 20);
~~~

## 5. `anyMatch`: Searching for Existence

`anyMatch(P)` fits questions like “is there any element that…?” or “is there at least one…?”.

### 5.1. Detecting an Order Above a Threshold

~~~java
import java.util.List;

record Order(String id, long totalVnd) {}

List<Order> orders = List.of(
        new Order("DH-01", 200_000),
        new Order("DH-02", 1_600_000),
        new Order("DH-03", 850_000)
);

boolean hasLargeOrder = orders.stream()
        .anyMatch(order -> order.totalVnd() > 1_000_000);

System.out.println(hasLargeOrder); // true
~~~

This is an existence check; there is no need to build a list of large orders just to know whether it contains at least one element. When you need **the order itself** exceeding the threshold, use `filter(...).findFirst()` or `filter(...).findAny()` to receive `Optional<Order>`.

### 5.2. Elements Must Satisfy Multiple Conditions Simultaneously

~~~java
boolean hasLargePriorityOrder = orders.stream()
        .anyMatch(order -> order.id().startsWith("DH-")
                && order.totalVnd() >= 1_500_000);

System.out.println(hasLargePriorityOrder); // true
~~~

For each order, the predicate combines two conditions using `&&`. If clearer readability is needed, extract a separate `Predicate<Order>`. Java's `&&` operator also short-circuits evaluating the right-hand subexpression if the left-hand side is `false`.

### 5.3. Distinguishing from Counting All Matching Elements

~~~java
long expensiveCount = orders.stream()
        .filter(order -> order.totalVnd() > 1_000_000)
        .count(); // 1
~~~

`count` returns a quantity, while `anyMatch` returns a `boolean`. When you only need to know **whether any exists**, `anyMatch` directly expresses the intent and can stop early.

## 6. `allMatch`: Validating the Whole Set

`allMatch(P)` fits requirements like “every element must…” or “no element violates the standard condition”.

### 6.1. Validating Input Data

~~~java
import java.util.List;

List<String> emails = List.of(
        "an@example.com",
        "binh@example.org",
        "chi@example.net"
);

boolean allHaveAtSign = emails.stream()
        .allMatch(email -> email.contains("@"));

System.out.println(allHaveAtSign); // true
~~~

This example merely illustrates a predicate and is **not a complete email validation algorithm**. In real applications, use validation rules suited to the business domain.

### 6.2. Detecting One Invalid Element That Fails the Whole Batch

~~~java
import java.util.List;

List<Integer> quantities = List.of(3, 5, 0, 2);

boolean allPositive = quantities.stream()
        .allMatch(quantity -> quantity > 0);

System.out.println(allPositive); // false
~~~

`0` is the first counterexample in the sequence. With a sequential Stream, after encountering the counterexample, checking `2` is unnecessary to determine the result. For datasets of unknown size, this is a concise check that avoids keeping a list of errors.

### 6.3. Combining “Has Elements” and “All Valid”

If the requirement is “there is at least one order and **every** order has a positive total”, write both conditions:

~~~java
import java.util.List;

List<Order> orders = List.of(
        new Order("DH-01", 100_000),
        new Order("DH-02", 200_000)
);

boolean validOrderBatch = !orders.isEmpty()
        && orders.stream().allMatch(order -> order.totalVnd() > 0);

System.out.println(validOrderBatch); // true
~~~

Here `record Order(String id, long totalVnd) {}` is assumed to be declared as in the previous example. Placing the **non-empty** requirement before `allMatch` avoids the vacuous-truth trap.

## 7. `noneMatch`: Confirming No Forbidden Element Exists

`noneMatch(P)` is used when `P` describes **what is not allowed to appear**.

~~~java
import java.util.List;

List<String> fileNames = List.of(
        "report.csv", "summary.txt", "orders.json"
);

boolean noExecutable = fileNames.stream()
        .noneMatch(name -> name.endsWith(".exe"));

System.out.println(noExecutable); // true
~~~

This is only a filename extension check, not a security-reliable file type verification solution.

### 7.1. Writing Predicates to Avoid Double-Negative Reading

~~~java
import java.util.List;

List<Integer> quantities = List.of(2, 4, 7);

boolean noneNegative = quantities.stream()
        .noneMatch(q -> q < 0);

boolean allNonNegative = quantities.stream()
        .allMatch(q -> q >= 0);

System.out.println(noneNegative);    // true
System.out.println(allNonNegative);  // true
~~~

Both expressions are logically equivalent if `q < 0` and `q >= 0` are exact negations of each other over the data domain. Which reads better depends on domain phrasing:

- “No negative quantities” → `noneMatch(q -> q < 0)`.
- “All quantities are non-negative” → `allMatch(q -> q >= 0)`.

### 7.2. Checking Absence of Error States

~~~java
import java.util.List;

enum State { NEW, ACTIVE, BLOCKED }

List<State> states = List.of(State.NEW, State.ACTIVE, State.ACTIVE);

boolean hasNoBlocked = states.stream()
        .noneMatch(state -> state == State.BLOCKED);

System.out.println(hasNoBlocked); // true
~~~

If a `State.BLOCKED` is present, `noneMatch` can immediately conclude `false` at that element.

## 8. Negation Relationships and De Morgan's Laws

Let `P` be a stable, side-effect-free predicate; the following expressions are equivalent **in result** when applied to the same sequence of elements:

| Expression | Equivalent |
|---|---|
| `noneMatch(P)` | `!anyMatch(P)` |
| `noneMatch(P)` | `allMatch(not P)` |
| `allMatch(P)` | `!anyMatch(not P)` |
| `anyMatch(P)` | `!allMatch(not P)` |

Concrete example, three ways of expressing “no negative numbers”:

~~~java
import java.util.List;

List<Integer> numbers = List.of(2, 4, 6);

boolean byNoneMatch = numbers.stream()
        .noneMatch(n -> n < 0);

boolean byNegation = !numbers.stream()
        .anyMatch(n -> n < 0);

boolean byAllMatch = numbers.stream()
        .allMatch(n -> n >= 0);

System.out.println(byNoneMatch == byNegation); // true
System.out.println(byNoneMatch == byAllMatch); // true
~~~

**Note:** each expression calls `numbers.stream()` to create a separate Stream. You cannot reuse the same `Stream` object for multiple terminal operations.

These logical identities also hold on an **empty** Stream: `noneMatch(P) == true`, `anyMatch(P) == false`, `allMatch(not P) == true`.

### 8.1. Using `Predicate.not` When Clearer

`Predicate.not` was added in Java 11 and is useful when negating a method reference:

~~~java
import java.util.List;
import java.util.function.Predicate;

List<String> labels = List.of("A", "B", "C");

boolean allNonBlank = labels.stream()
        .allMatch(Predicate.not(String::isBlank));

System.out.println(allNonBlank); // true
~~~

`Predicate.not(String::isBlank)` creates the negated predicate of `String::isBlank`. This is cleaner than writing a separate lambda just to put `!` in front of a method call.

### 8.2. Do Not Confuse `anyMatch` and `allMatch` as Opposites

~~~java
import java.util.List;

List<Integer> values = List.of(1, -1);

boolean anyPositive = values.stream().anyMatch(n -> n > 0);
boolean allPositive = values.stream().allMatch(n -> n > 0);

System.out.println(anyPositive); // true
System.out.println(allPositive); // false
~~~

“At least one positive number” and “all numbers are positive” can both be `true`, both `false` (on an empty Stream: `false` and `true`), or differ. Therefore, there is **no** general rule that `allMatch(P) == !anyMatch(P)`.

## 9. Composing Predicates and Pipelines for Readability

`Predicate<T>` provides combinators `and`, `or`, and `negate`. They let you name conditions when logic grows long.

~~~java
import java.util.List;
import java.util.function.Predicate;

record Candidate(String name, int years, boolean active) {}

List<Candidate> candidates = List.of(
        new Candidate("An", 3, true),
        new Candidate("Bình", 1, false),
        new Candidate("Chi", 5, true)
);

Predicate<Candidate> experienced = c -> c.years() >= 3;
Predicate<Candidate> isActive = Candidate::active;

boolean hasEligibleCandidate = candidates.stream()
        .anyMatch(experienced.and(isActive));

boolean noneActiveWithoutExperience = candidates.stream()
        .noneMatch(isActive.and(experienced.negate()));

System.out.println(hasEligibleCandidate);          // true
System.out.println(noneActiveWithoutExperience);    // true
~~~

Here, `Predicate.and` and `Predicate.or` use short-circuit evaluation just like Java's `&&` and `||`. With pure predicates, naming components improves readability and testability. Do not rely on side effects occurring on the right-hand side: that side might never be invoked if the outcome is already known.

### 9.1. Checking “Every Filtered Element Is Valid”

~~~java
import java.util.List;

record Product(String code, boolean active, int stock) {}

List<Product> products = List.of(
        new Product("A", true, 5),
        new Product("B", false, -2),
        new Product("C", true, 3)
);

boolean allActiveHaveStock = products.stream()
        .filter(Product::active)
        .allMatch(p -> p.stock() >= 0);

System.out.println(allActiveHaveStock); // true
~~~

The condition here means: **every active product has non-negative stock**. It **does not** check the stock of inactive products.

If there are no active products, `allMatch` after `filter` returns `true`. If business logic requires “there must be at least one active product and all of them are valid”, add an existence check:

~~~java
boolean hasActive = products.stream().anyMatch(Product::active);

boolean activeBatchValid = hasActive && products.stream()
        .filter(Product::active)
        .allMatch(p -> p.stock() >= 0);
~~~

Because `products` is a `List`, two fresh Streams can be created. For a single-pass source, an appropriate single-pass aggregation design is required instead of attempting to reuse the same Stream.

## 10. Checking Nested Structures with Quantifiers

Matching operations can be nested, but **the order of quantifiers changes the meaning of the problem**.

Suppose each order contains multiple line items:

~~~java
import java.util.List;

record Item(String sku, int quantity) {}
record Order(String id, List<Item> items) {}

List<Order> orders = List.of(
        new Order("O-01", List.of(
                new Item("PEN", 2),
                new Item("BOOK", 1))),
        new Order("O-02", List.of(
                new Item("BAG", 0))),
        new Order("O-03", List.of())
);
~~~

### 10.1. Does At Least One Order Have an Invalid Line Item?

~~~java
boolean hasOrderWithInvalidItem = orders.stream()
        .anyMatch(order -> order.items().stream()
                .anyMatch(item -> item.quantity() <= 0));

System.out.println(hasOrderWithInvalidItem); // true (O-02)
~~~

Here it checks **there exists an order** in which **there exists an item** with a non-positive quantity. Empty order `O-03` has no items to trigger an error under this expression.

### 10.2. Does Every Order Contain At Least One Valid Line Item?

~~~java
boolean everyOrderHasPositiveItem = orders.stream()
        .allMatch(order -> order.items().stream()
                .anyMatch(item -> item.quantity() > 0));

System.out.println(everyOrderHasPositiveItem); // false
~~~

`O-02` only has an item with quantity `0`, and `O-03` has no items; both cause the order-level predicate to return `false`.

### 10.3. Does Every Order Have At Least One Item and Are All Items Valid?

~~~java
boolean fullyValid = !orders.isEmpty()
        && orders.stream().allMatch(order ->
                !order.items().isEmpty()
                && order.items().stream().allMatch(item -> item.quantity() > 0));

System.out.println(fullyValid); // false
~~~

You must check **two levels of non-emptiness** if the problem requires:

1. There must be at least one order.
2. Each order must have at least one line item.
3. Every line item of every order has a positive quantity.

Writing plain `orders.stream().allMatch(order -> order.items().stream().allMatch(...))` would yield `true` for an empty order, because the inner `allMatch` is true on an empty Stream. This is an easily overlooked business bug.

### 10.4. “No Order Contains Prohibited Goods” Can Be Expressed Two Ways

~~~java
boolean noForbiddenSku = orders.stream()
        .noneMatch(order -> order.items().stream()
                .anyMatch(item -> "BANNED".equals(item.sku())));

boolean everyOrderClean = orders.stream()
        .allMatch(order -> order.items().stream()
                .noneMatch(item -> "BANNED".equals(item.sku())));
~~~

Both are logically equivalent on the same stable dataset. Choose the phrasing closest to the business specification to avoid accidentally swapping `anyMatch` and `noneMatch` across levels.

## 11. Distinguishing Matching from `filter`, `findFirst`, `findAny`, and `count`

For the same predicate “number greater than 100”, each API serves a different outcome:

| Need | Appropriate API | Return Type |
|---|---|---|
| Only need to know if at least one element matches | `anyMatch(P)` | `boolean` |
| Confirm every element is valid | `allMatch(P)` | `boolean` |
| Confirm no forbidden element exists | `noneMatch(P)` | `boolean` |
| Get the first matching element in encounter order (if source is ordered) | `filter(P).findFirst()` | `Optional<T>` |
| Get any matching element | `filter(P).findAny()` | `Optional<T>` |
| Count all matching elements | `filter(P).count()` | `long` |
| Get a list of matching elements | `filter(P).toList()` | `List<T>` (Java 16+) |

~~~java
import java.util.List;
import java.util.Optional;

List<Integer> values = List.of(12, 101, 35, 150);

boolean exists = values.stream()
        .anyMatch(n -> n > 100);

Optional<Integer> first = values.stream()
        .filter(n -> n > 100)
        .findFirst();

long count = values.stream()
        .filter(n -> n > 100)
        .count();

System.out.println(exists);            // true
System.out.println(first.orElse(-1));  // 101
System.out.println(count);             // 2
~~~

`anyMatch` does not tell you which element matched; `findFirst` and `findAny` do not guarantee finding “all matching elements”; `count` provides the quantity. Choose based on the **kind of information** actually needed, rather than always filtering and collecting to a List.

If you only need a `boolean`, `anyMatch(P)` is usually clearer than `filter(P).findAny().isPresent()`; both share the goal of checking existence, but `anyMatch` expresses intent directly.

## 12. Primitive Streams: `IntStream`, `LongStream`, and `DoubleStream`

Data is not always a `Stream<Integer>` or `Stream<Double>`. For primitive-specialized Streams, the matching methods take specialized predicates:

| Stream | Predicate Type | Example |
|---|---|---|
| `IntStream` | `IntPredicate` | `anyMatch(n -> n < 0)` |
| `LongStream` | `LongPredicate` | `allMatch(n -> n >= 0)` |
| `DoubleStream` | `DoublePredicate` | `noneMatch(x -> Double.isNaN(x))` |

Example:

~~~java
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

boolean hasMultipleOfSeven = IntStream.rangeClosed(1, 20)
        .anyMatch(n -> n % 7 == 0);

boolean allPositive = LongStream.of(2L, 7L, 100L)
        .allMatch(n -> n > 0L);

boolean noNaN = DoubleStream.of(1.5, 2.0, 3.25)
        .noneMatch(x -> Double.isNaN(x));

System.out.println(hasMultipleOfSeven); // true
System.out.println(allPositive);        // true
System.out.println(noNaN);              // true
~~~

Primitive Streams avoid boxing/unboxing overhead when processing large volumes of numeric values. However, you cannot conclude they are always faster than every other design without considering pipeline cost, data source, operations, and actual JDK.

### 12.1. Watch Out for `NaN` Values

With `double`, ordinary comparisons can behave surprisingly when encountering `NaN`:

~~~java
import java.util.stream.DoubleStream;

boolean allNonNegative = DoubleStream.of(1.0, Double.NaN)
        .allMatch(x -> x >= 0.0);

System.out.println(allNonNegative); // false
~~~

`Double.NaN >= 0.0` is `false`. When validating floating-point data, decide whether business rules allow `NaN`, infinities, or other special values, and compose the predicate accordingly.

## 13. Pure Predicates, Null Data, and Execution Errors

Matching operations accept a behavioral parameter that must be **non-interfering** and **stateless** according to the Stream contract:

- **Non-interfering:** do not modify the data source in a way unsupported by the source while the Stream is traversing it.
- **Stateless:** the predicate's result must not depend on state that can change during pipeline execution.

### 13.1. Avoid Modifying the Source Inside a Predicate

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

// Do not do this:
// numbers.stream().anyMatch(n -> {
//     numbers.add(n * 10); // Interferes with the source currently being traversed
//     return n == 2;
// });
~~~

Doing so can cause erratic behavior, exceptions, or unexpected results. A predicate should express a check; adding, removing, or modifying source elements belongs in another appropriate processing step.

### 13.2. Side Effects Cause Misunderstandings About Predicate Call Counts

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

List<Integer> numbers = List.of(2, 5, 8, 13);
AtomicInteger calls = new AtomicInteger();

boolean found = numbers.stream().anyMatch(n -> {
    calls.incrementAndGet(); // For illustration only, do not use for business logic
    return n > 6;
});

System.out.println(found);       // true
System.out.println(calls.get()); // 3 with the sequential pipeline shown
~~~

When switching to a parallel Stream, the timing, order, and total number of predicate calls can differ. `AtomicInteger` makes counter updates atomic, but **does not** turn a side-effecting predicate into a stateless one. If you need to record every element, the three matching operations are not the right tool because they can stop early.

### 13.3. `null` Must Be Decided Explicitly in the Predicate

`List.of(...)` disallows `null` elements, but some other collections can contain `null`. Calling a method on a `null` element can throw `NullPointerException`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

List<String> names = new ArrayList<>(
        Arrays.asList("An", null, "Chi")
);

// Avoid if data may contain null:
// names.stream().allMatch(String::isBlank);
~~~

How to check “every name must be non-null and non-blank”:

~~~java
boolean allValid = names.stream()
        .allMatch(name -> name != null && !name.isBlank());

System.out.println(allValid); // false
~~~

Using `filter(Objects::nonNull).allMatch(...)` **skips** null elements instead of marking them invalid. The two approaches have different business meanings. Note: if all elements are filtered out, `allMatch` returns `true` because the post-filter source is empty.

### 13.4. Exceptions from Predicates

~~~java
import java.util.List;

List<String> tokens = List.of("12", "bad", "4");

// May throw NumberFormatException upon encountering "bad":
// boolean hasLarge = tokens.stream()
//         .anyMatch(token -> Integer.parseInt(token) > 10);
~~~

If data is not guaranteed to be well-formed, establish an error-handling policy: validate upfront, reject malformed data, or model errors as explicit values. Do not rely on short-circuiting happening to skip a bad element, because changing order, conditions, or parallel execution can alter evaluation.

## 14. Matching on Parallel Streams and Unordered Sources

~~~java
import java.util.List;

List<Integer> values = List.of(1, 5, 8, 13, 21);

boolean found = values.parallelStream()
        .anyMatch(n -> n > 10);

System.out.println(found); // true
~~~

With a pure predicate, `true` is expected because `13` and `21` satisfy the condition. However:

1. Multiple elements may be checked **concurrently**.
2. Several elements may already begin processing before a thread finds a match.
3. The number of checks and predicate invocation order are **not guaranteed** to match a sequential Stream.
4. `anyMatch` answers *yes or no*, so there is no concept of “must find the first element” like `findFirst`.
5. `allMatch` and `noneMatch` can also short-circuit at the result level, but should not be used to drive a side effect that must happen once per element.

`unordered()` can give the framework extra freedom to ignore encounter order when valid. With these three operations returning only `boolean` and stateless predicates, reordering elements does not alter the mathematical result on a finite, stable source. This **does not guarantee** a parallel pipeline will run faster; work-splitting overhead, thread coordination, and the source's `Spliterator` characteristics can slow down small workloads.

### 14.1. Do Not Infer Processing Order from the Result

~~~java
import java.util.List;

List<String> values = List.of("a", "b", "c", "d");

boolean exists = values.parallelStream()
        .anyMatch(s -> s.equals("b"));
~~~

The result is `true`, but there is no guarantee the predicate was called on `"a"` first. If you need to retrieve the first element in encounter order, use `filter(...).findFirst()` on an ordered source; that is a different problem from matching.

## 15. Infinite Sources, Early Stopping, and Completion

Because matching operations are **short-circuiting**, they can sometimes process infinite Streams:

~~~java
import java.util.stream.IntStream;

boolean found = IntStream.iterate(0, n -> n + 1)
        .anyMatch(n -> n == 5);

System.out.println(found); // true
~~~

In this sequential Stream, upon seeing `5`, `anyMatch` can terminate. But short-circuiting **does not guarantee termination**. If the deciding element never appears, an infinite source can keep the terminal operation running forever:

~~~java
import java.util.stream.Stream;

// Avoid running: no counterexample for allMatch to stop.
// Stream.generate(() -> "ok")
//         .allMatch("ok"::equals);

// Avoid running: no matching element for noneMatch to stop.
// Stream.generate(() -> "ok")
//         .noneMatch("bad"::equals);

// Avoid running: no matching element for anyMatch to stop.
// Stream.generate(() -> "ok")
//         .anyMatch("bad"::equals);
~~~

If business logic only wants to inspect a fixed number of initial elements, apply `limit` before matching:

~~~java
import java.util.stream.Stream;

boolean firstHundredOk = Stream.generate(() -> "ok")
        .limit(100)
        .allMatch("ok"::equals);

System.out.println(firstHundredOk); // true
~~~

Now the actual question is: “Are the first 100 elements all `"ok"`?”. Do not confuse this with verifying the **entirety** of a potentially infinite source. Similarly, `takeWhile` and other bounding mechanisms only ensure completion when the stopping condition is met according to the source and proper ordering.

## 16. Matching with File-Reading Streams: Resource Management

`Files.lines` creates a `Stream<String>` reading lines from a file, holding system resources that must be closed. Matching can stop early, but the terminal operation **does not replace closing the I/O Stream**.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path logFile = Path.of("application.log");

try (Stream<String> lines = Files.lines(logFile, StandardCharsets.UTF_8)) {
    boolean hasError = lines.anyMatch(line -> line.contains("ERROR"));
    System.out.println("Has error line: " + hasError);
} catch (IOException | UncheckedIOException e) {
    System.err.println("Cannot read file: " + e.getMessage());
}
~~~

Points to remember:

- `Files.lines` creates a source that reads lines on demand.
- `anyMatch` stops early once a matching line is detected; it does not require loading the entire file into a `List`.
- `try-with-resources` guarantees `close()` is called on exit from the block, even when matching returns `true` early.
- `IOException` can occur when opening the source; read errors during Stream consumption may be wrapped in `UncheckedIOException`.
- If you want to continue processing other lines after finding a result, you must open/create a new Stream according to the source's requirements and lifecycle.

These concepts connect to resource handling, `Spliterator`, parallel Streams, and performance in this module. Choosing the right terminal operation is only half the story: whether the source gets closed and whether the check is independent enough for pipelined execution must also be considered.

## 17. Quick Decision Table

| Business requirement | Suggested expression | Points to watch |
|---|---|---|
| Is at least one order over 1 million? | `anyMatch(order -> order.totalVnd() > 1_000_000)` | Returns only `boolean` |
| Does every order have a positive total? | `allMatch(order -> order.totalVnd() > 0)` | Returns `true` if Stream is empty |
| Do no orders have negative quantity? | `noneMatch(order -> order.quantity() < 0)` | Predicate describes the forbidden condition |
| Are all elements valid **and list non-empty**? | `!list.isEmpty() && list.stream().allMatch(P)` | Check non-emptiness separately |
| Are there any errors in the data? | `anyMatch(isInvalid)` | Can stop immediately upon seeing an error |
| Are there no errors? | `noneMatch(isInvalid)` | Equivalent to `allMatch(isValid)` if negated accurately |
| Find the first invalid element itself? | `filter(isInvalid).findFirst()` | Returns `Optional<T>` |
| Count total errors? | `filter(isInvalid).count()` | Must determine exact quantity |
| Check lines of a file? | `Files.lines(...).anyMatch(P)` | Use `try-with-resources` |
| Check elements across nested structures? | Nested matching | Watch quantifiers and emptiness at every level |

## 18. Practice Exercises

### Exercise 1. Predict Three Results

~~~java
import java.util.List;

List<Integer> values = List.of(3, 6, 9);

System.out.println(values.stream().anyMatch(n -> n % 2 == 0));
System.out.println(values.stream().allMatch(n -> n > 0));
System.out.println(values.stream().noneMatch(n -> n > 10));
~~~

**Answer:** `true`, `true`, `true`. There is one even number (`6`); all are positive; none are greater than 10.

### Exercise 2. Empty Stream and Vacuous Truth

~~~java
import java.util.List;

List<Integer> empty = List.of();

System.out.println(empty.stream().anyMatch(n -> n < 0));
System.out.println(empty.stream().allMatch(n -> n < 0));
System.out.println(empty.stream().noneMatch(n -> n < 0));
~~~

**Answer:** `false`, `true`, `true`. No element makes the predicate true, there is no counterexample for `allMatch`, and no element violates the “none” condition.

### Exercise 3. Write the Condition “Every Name Is Non-Blank and There Is At Least One Name”

**Prompt:** Given `List<String> names`, elements may be empty or contain only whitespace. The result must be `false` if `names` is empty.

**Reference answer:**

~~~java
boolean valid = !names.isEmpty()
        && names.stream().allMatch(name -> !name.isBlank());
~~~

If the list can contain `null`, add `name != null &&` to the predicate.

### Exercise 4. Negate Using De Morgan's Laws

**Prompt:** Rewrite `!values.stream().anyMatch(n -> n < 0)` using exactly one other matching operation and no outer negation operator.

**Answer:**

~~~java
boolean noNegative = values.stream().noneMatch(n -> n < 0);
~~~

You can write `values.stream().allMatch(n -> n >= 0)` if the data domain permits treating the two conditions as exact negations.

### Exercise 5. Nested Quantifiers

**Prompt:** You have the `orders` list from section 10. Check “there is at least one order where every line item in that order has a positive quantity **and that order is not empty**”.

**Reference answer:**

~~~java
boolean existsFullyPositiveOrder = orders.stream()
        .anyMatch(order -> !order.items().isEmpty()
                && order.items().stream()
                        .allMatch(item -> item.quantity() > 0));

System.out.println(existsFullyPositiveOrder); // true (O-01)
~~~

The `!order.items().isEmpty()` condition excludes empty order `O-03`, which would otherwise make the inner `allMatch` return `true` inappropriately for the business rule.

### Exercise 6. Why Does Using the Same Stream Twice Fail?

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> source = List.of(1, 2, 3).stream();

boolean hasTwo = source.anyMatch(n -> n == 2);
// boolean allPositive = source.allMatch(n -> n > 0);
// The line above compiles but throws IllegalStateException at runtime.
~~~

**Answer:** `anyMatch` is a terminal operation that consumed `source`. You must create a new Stream from the `List` (or design a single-pass traversal if the source can only be read once).

### Exercise 7. Side Effects in a Parallel Stream

**Prompt:** Should you use an `AtomicInteger counter` incremented on every predicate call in `parallelStream().anyMatch(...)` to count all elements?

**Answer:** No. `anyMatch` is allowed to stop once enough information is found, so the predicate is not forced to run on all elements; parallel mode also does not guarantee order or invocation counts like a sequential loop. `AtomicInteger` only makes updates atomic, not turn a check into a full count. If you need a count, use `count` appropriately.

### Exercise 8. Choosing the Right API

**Prompt:** You want to return **the ID of the first order** with a negative total, if any. Is `anyMatch` enough?

**Answer:** No. `anyMatch` only returns `boolean`. Use:

~~~java
import java.util.List;
import java.util.Optional;

record Order(String id, long totalVnd) {}

List<Order> orders = List.of(
        new Order("DH-01", 100_000),
        new Order("DH-02", -50_000),
        new Order("DH-03", 20_000)
);

Optional<String> firstInvalidId = orders.stream()
        .filter(order -> order.totalVnd() < 0)
        .map(Order::id)
        .findFirst();

System.out.println(firstInvalidId.orElse("None")); // DH-02
~~~

This example uses `Order` with `id()` and `totalVnd()` accessors as in section 5, separate from the order structure with `items()` in section 10. If keeping the first order is not required, consider `findAny()`.

---

**Key Takeaways:** `anyMatch` asks **is there at least one**, `allMatch` asks **do all**, and `noneMatch` asks **do none** satisfy the predicate. All three are **short-circuiting terminal operations** returning `boolean`. On an empty Stream, the results are **false – true – true** respectively. Write stateless/non-interfering predicates, manage I/O Stream lifecycles, create a fresh Stream for each independent check, and add a “non-empty” check when business rules require it.

