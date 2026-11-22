# Referential Transparency and Replacing Expressions with Values

## Lesson Objectives

Understand **referential transparency** at the expression level: when an expression can be replaced by its own result while keeping the observable behavior of the program unchanged. From there, distinguish pure functions from functions with side effects, identify points that break substitutability in Java, and design computation logic that is easy to test, reuse, and optimize.

This is a core principle of functional programming, not a synonym for "using lambdas", "using Stream", or "avoiding loops".

## 1. What is Referential Transparency?

An expression is **referentially transparent** when we can replace an occurrence of that expression with **the value it computes**, in an appropriate context, without changing the observable behavior of the program. This relationship is often expressed as *substitution* or *equational reasoning*.

Mathematical example:

```text
f(x) = x * x + 1

f(4) + f(4)
= 17 + 17
= 34
```

If `f` only uses the argument `x` and does not change anything outside, each evaluation of `f(4)` yields `17`. We can think about the expression `f(4)` through the value `17` without having to care about when it is called or how many times it has been called.

In Java, the equivalent expression:

```java
static int squarePlusOne(int x) {
    return x * x + 1;
}

// For x = 4 and no overflow:
int result = squarePlusOne(4) + squarePlusOne(4); // 34
```

This snippet illustrates substitution; **it is not a standalone program**. We will have a complete Java program in a later section.

Important point: referential transparency is evaluated based on **observable behavior**, not merely whether two expressions print the same string or two objects are equal according to `equals`. Observable things include results, exceptions, I/O operations, state changes, execution order, object identity in contexts using `==`, and interaction with other threads. Therefore, substitutability must be stated conditionally, especially in Java, which is a language that allows state and side effects.

## 2. Why Do Pure Functions Make Expressions Substitutable?

A **pure function** has two practical properties:

1. **The result is determined solely by the inputs:** given the same inputs and the same data type semantics, the computation returns the same result, without secretly depending on a clock, global variables, database state, or a mutable counter.
2. **No observable side effects:** it does not modify externally observable objects, write files, send network requests, update a database, print logs, or mutate a shared counter.

Pure methods on immutable data form the foundation for expression substitution. For example, `Math.multiplyExact(7, 6)` yields `42` on every evaluation with these two arguments and does not alter external state. This method can throw `ArithmeticException` on overflow; that is why when stating "replace with a value", one must consider calls that **return normally** and preserve error semantics in other cases.

Contrast with the following method:

```java
static int nextId(java.util.concurrent.atomic.AtomicInteger counter) {
    return counter.incrementAndGet();
}
```

If the counter starts at `0`, two consecutive calls yield `1` and then `2`. Even though the reference argument is still the same `counter`, the result depends on the current state and the call also mutates the counter. Replacing both calls with `1` would change both the value and the side effect: **there is no equivalent substitution as with a pure function**.

| Expression or action | Can it be replaced by a fixed value under the same conditions? | Explanation |
| --- | --- | --- |
| `5 * 8` | Yes | Does not read or modify external state |
| `Math.max(3, 9)` | Yes | Stable result for the given arguments |
| `price * quantity`, with two unchanging primitive variables | Yes | Depends on stable inputs; note overflow rules |
| `counter.incrementAndGet()` | No | Reads and modifies counter state |
| `Instant.now()` | No | Reads the environment's current time; the next call may differ |
| `System.out.println("Hello")` | No | Produces an I/O side effect, even though it returns `void` |
| `order.total()` with an immutable `order` and a pure calculation | Yes, under the stated conditions | The value does not change; if the object or its elements are mutated, the conclusion may no longer hold |

**Determinism is not enough to be pure.** A method that always returns `100` while also writing logs or incrementing a counter still has side effects. Conversely, a method that receives data via explicit arguments but secretly mutates that data cannot be considered pure just because multiple test runs happen to produce the same result.

## 3. Replacing Expressions with Values: How to Reason Correctly

Consider a fixed order with a total amount of `230_000` and a pure discount function `discountPercent`:

```text
discountPercent(total(items), 10)
= discountPercent(230_000, 10)
= 207_000
```

This substitution is valid **in the context** where `items` and each element are kept immutable during computation, `total` has no side effects, and the discount calculation uses the same pricing rules. If the contents of `items` change later, you must not take the old result `230_000` to replace all calls to `total(items)` at the new point in time.

The benefit is being able to reason piecewise: prove `total(items) == 230_000`; prove `discountPercent(230_000, 10) == 207_000`; then combine the two results. Each step can be tested independently.

For stateful computations, the same reasoning cannot be applied:

```text
nextId(counter) + nextId(counter)
```

When `counter` starts at `0`, Java's left-to-right evaluation order produces `1 + 2 = 3`, and the counter ends at `2`. If both calls were replaced by a single value `1`, the addition would become `2` and the counter would not increment: both the result and the observable state differ.

**Note on the scope of transformations:** Java evaluates arguments according to specific rules, with exceptions, object identity, short-circuiting (`&&`, `||`), and side effects. You must not arbitrarily move, omit, or execute an expression an extra time if doing so changes when errors are thrown, state, or observable behavior. Referential transparency is a criterion to justify substitution, not a license to arbitrarily optimize every Java call.

## 4. A Runnable Java 17 Program

The example below places order data in a `record`, uses an immutable list of items, and computes the total via a pure function under the stated conditions. It contrasts this with a stateful sequence-number function and an explicit time-reading operation.

Save to **`ReferentialTransparencyDemo.java`**:

```java
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class ReferentialTransparencyDemo {
    record Item(String name, int quantity, long unitPrice) {
        Item {
            Objects.requireNonNull(name, "name");
            if (name.isBlank() || quantity <= 0 || unitPrice < 0) {
                throw new IllegalArgumentException("Invalid item");
            }
        }

        long subtotal() {
            return Math.multiplyExact(unitPrice, quantity);
        }
    }

    static long total(List<Item> items) {
        Objects.requireNonNull(items, "items");
        return items.stream()
                .mapToLong(Item::subtotal)
                .reduce(0L, Math::addExact);
    }

    static long discountPercent(long amount, int percent) {
        if (amount < 0 || percent < 0 || percent > 100) {
            throw new IllegalArgumentException("Invalid discount");
        }
        return Math.multiplyExact(amount, 100L - percent) / 100;
    }

    static int nextId(AtomicInteger counter) {
        return counter.incrementAndGet();
    }

    static boolean beforeDeadline(Instant observedAt, Instant deadline) {
        return observedAt.isBefore(deadline);
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("Sách", 2, 100_000),
                new Item("Bút", 3, 10_000)
        );

        long savedTotal = total(items);
        long direct = discountPercent(total(items), 10);
        long substituted = discountPercent(savedTotal, 10);

        System.out.println("Tổng: " + savedTotal);
        System.out.println("Thay thế tương đương: " + (direct == substituted));
        System.out.println("Giá sau giảm: " + direct);

        AtomicInteger counter = new AtomicInteger(0);
        int first = nextId(counter);
        int second = nextId(counter);
        System.out.println("Số vé: " + first + ", " + second);

        Instant observedAt = Instant.parse("2026-10-28T12:00:00Z");
        Instant deadline = Instant.parse("2026-11-01T00:00:00Z");
        System.out.println("Trước hạn: " + beforeDeadline(observedAt, deadline));
    }
}
```

Run with JDK 17 or newer:

```bash
javac ReferentialTransparencyDemo.java
java ReferentialTransparencyDemo
```

Expected output:

```text
Tổng: 230000
Thay thế tương đương: true
Giá sau giảm: 207000
Số vé: 1, 2
Trước hạn: true
```

**Analysis:**

- `Item` keeps the name, quantity, and unit price immutable in its constructor. `String` is immutable and the other two components are primitives; every `Item` in the example cannot be modified after creation. `List.of` is a list whose elements cannot be added, removed, or modified. As a result, the input to `total(items)` is stable.
- `subtotal` takes all its inputs from the immutable state of `Item` and does not change anything outside. `total` only reads the list, converts elements to `long`, and sums them; it uses `Math.addExact` and `Math.multiplyExact` to detect overflow. In the example with non-negative prices and no overflow, the total is stably `230000`.
- `discountPercent` computes `230000 * 90 / 100 = 207000`. Replacing `total(items)` with `savedTotal` is valid here because the data does not change and there are no side effects. Integer division truncates downward; in real financial applications, an appropriate currency unit and rounding policy must be specified.
- `nextId` accesses and then mutates an external counter. Even with the same reference argument, each call receives a different state and causes a side effect. `AtomicInteger` guarantees atomic increments for the counter, but **does not make the method pure**.
- `beforeDeadline` takes the observation timestamp as an argument rather than calling `Instant.now()` itself. With the two given `Instant` values, the result `true` is stable and can be verified on any day the program is run.

In this pattern, `record` and `List.of` are tools to help manage data, but **they do not automatically guarantee that every function using them is pure**. For example, a method can still log or make a network request inside. Purity must be evaluated across the entire behavior.

## 5. Hidden State: Three Common Causes That Break Substitutability

### 5.1. Reading Global or Environment State

```java
// Illustration, not a standalone Java program.
static boolean isExpired(java.time.Instant deadline) {
    return java.time.Instant.now().isAfter(deadline);
}
```

For the same `deadline`, the method can return `false` before the deadline and `true` after it. If a pure result is needed, pass the observed timestamp in:

```java
static boolean isExpired(
        java.time.Instant deadline,
        java.time.Instant observedAt) {
    return observedAt.isAfter(deadline);
}
```

In real-world architecture, the orchestration layer (*imperative shell*) can call `clock.instant()` at the exact decision point and then pass the `Instant` to the computation layer (*functional core*). Simply passing a `Clock` object into a function and letting the function call `clock.instant()` is not enough to guarantee purity if the `Clock` is a clock that advances with time.

Similarly, reading a mutable configuration variable, a mutable cache, `System.getenv`, or a database directly inside a computation function can make the result depend on the environment instead of only on parameters.

### 5.2. Causing Side Effects Even When the Return Value Does Not Change

```java
// Illustration, not a standalone Java program.
static int priceWithLog(int price) {
    System.out.println("Đang tính giá");
    return price;
}
```

Two calls still return the same number, but they print two lines. Replacing the calls with the value `price` would eliminate those log lines, thereby changing observable behavior. Therefore, **returning the same result does not mean referential transparency**.

Side effects also include modifying an external collection, updating a `static` variable, incrementing a metric, emitting an event, writing to a database, or mutating state inside a passed-in object. An operation may be useful and intentional, but it should be placed at a clear boundary if you want to keep the computation part pure.

### 5.3. Inputs That Are References to Mutable Data

```java
// Illustration, not a standalone Java program.
static int sum(java.util.List<Integer> numbers) {
    return numbers.stream().mapToInt(Integer::intValue).sum();
}

java.util.List<Integer> numbers = new java.util.ArrayList<>();
numbers.add(2);
int first = sum(numbers); // 2
numbers.add(3);
int second = sum(numbers); // 5
```

It is the same **reference** `numbers`, yet the contents of the list have changed. You cannot replace all calls to `sum(numbers)` with `2` for the entire runtime. During a single calculation over a stable snapshot without side effects, the computation can still be easy to reason about; what to avoid is claiming a value is time-independent when its state can change.

`final` only prevents reassigning the reference variable; it does not prevent mutating the object. A `record` is shallowly immutable across its components and does not automatically freeze mutable objects held inside. `List.copyOf` creates a structurally unmodifiable list, but mutable-type elements can still mutate themselves. For problems requiring safe substitution, use immutable value objects, appropriate defensive copies, or explicit snapshots.

## 6. Java-Specific Pitfalls: Values, Identity, and Exceptions

In mathematics, two equal values can usually be substituted for each other. In Java, **objects have both state and identity**, and identity can be observed with `==`. For example:

```java
String a = new String("Java");
String b = new String("Java");

System.out.println(a.equals(b)); // true
System.out.println(a == b);      // false
```

This is an illustrative snippet (it needs to be placed inside a method to run). The two strings have the same **content** but are two distinct objects. If the program context uses `==`, `System.identityHashCode`, identity-based keys, or synchronization locks on the object, replacing an object creation with a shared object can change the outcome. **Equality via `equals` must not be treated as sufficient proof of substitutability in every Java context**.

A method that returns a new list on each call may produce equal elements but different list identities. If the caller keeps and mutates the list, or compares references, the difference becomes even more observable. When you need value-based reasoning, use immutable types, avoid letting identity become an unnecessary part of the business contract, and clearly define the observable context.

**Exceptions are also behavior.** For example, `Math.divideExact` does not exist in Java 17; even a simple `a / b` throws `ArithmeticException` if `b == 0` for integer division. A substitution may only be performed after knowing the result is a normal value, or it must preserve the possibility of throwing, the location, and the effect of the error. In the main example, `Math.multiplyExact` intentionally throws on overflow instead of silently returning an incorrect number.

**Expression evaluation also has cost and execution timing.** Moving a pure computation out of a loop can preserve the value while changing when it is computed, memory cost, and when an error occurs. When performance and exception timing are part of the requirements, further verification is needed rather than assuming "pure" means every transformation is risk-free.

## 7. Do Lambdas and Streams Help Preserve Referential Transparency?

Yes, **when the functions passed in are truly pure and the source data is stable**. APIs such as `Function<T,R>`, `Predicate<T>`, and `Stream` allow expressing transformations like:

```java
// Illustration with a fixed List<Integer>:
List<Integer> doubled = List.of(1, 2, 3).stream()
        .map(x -> x * 2)
        .toList(); // [2, 4, 6]
```

The lambda `x -> x * 2` does not mutate state and produces the same value for the same `x`. The pipeline becomes readable and easy to test. However, **a lambda is just syntax** and does not guarantee purity:

```java
// Illustration with counter as an already created AtomicInteger.
List<Integer> ids = List.of("A", "B", "C").stream()
        .map(name -> counter.incrementAndGet())
        .toList();
```

Here, `map` is mutating the counter; the results depend on previous state. With a parallel stream, shared mutable state also makes reasoning about ordering and safety difficult. Similarly, `peek(System.out::println)` produces I/O and can behave unpredictably when the pipeline is optimized, short-circuited, or has no terminal operation executed. Do not use `peek` as the primary mechanism for business tasks with side effects.

When a pipeline is built from pure transformations, certain optimizations such as splitting work or caching results become easier to consider. Still, aggregation operations have their own conditions: a reducer used in parallel needs associativity and a proper identity; adding `double` values in different orders can differ due to floating-point error, even when each addition writes no state. With `long`, overflow must be considered. Purity is the foundation for reasoning, not a guarantee by itself that every execution order returns bit-for-bit identical results.

## 8. From Principles to Application Design

Business flows can be structured according to the **functional core, imperative shell** model:

```text
HTTP/CLI/Scheduler
       |
       v
Read data, clock, config, database       <-- has I/O and state
       |
       v
Create an immutable input snapshot
       |
       v
Pure computation function: input -> output
       |
       v
Write results, emit events, call services <-- has I/O and state
```

Example of an ordering service:

1. **Shell** loads prices and inventory, records an `Instant`, and determines the active discount policy.
2. **Core** receives explicit values, computes amounts, validation conditions, and business decisions; returns an immutable result object.
3. **Shell** sends the transaction to the payment gateway and updates the database according to the outcome. These operations have their own error handling, retries, and transactions.

The advantage does not lie in eliminating all side effects: real-world applications necessarily have I/O. The goal is to **keep the computation part reason-able by value**, while placing interactions with the environment where they are easy to observe and integration-test.

When a rule needs time-varying data, turn that data into a **parameter**. When a new result is needed, prefer returning a new object instead of mutating the input object. When a side effect is needed, make it clear through method names and APIs rather than hiding it inside a mapper or predicate.

## 9. Practical Benefits and Limitations

**Easy to test.** The function `discountPercent(230_000, 10)` can be tested independently of time, network, or database. Test cases mainly consist of inputs, outputs, and boundary conditions, without having to set up complex system state.

**Easy to reason about and refactor.** A pure expression can be named, extracted into a function, reused, or precomputed in contexts that preserve semantics. This is the foundation for equational reasoning at the program level.

**Opportunities for memoization/caching.** When the output depends only on immutable data used as a key, results can be stored to avoid recomputation. However, a cache has its own state, memory cost, and lifecycle policy; it needs a key that fully represents the inputs, concurrency handling, and exact error semantics. Do not automatically cache functions that read a clock or mutable data, because old results may no longer be valid.

**Favorable for concurrency.** Functions that do not share mutable state reduce the risk of race conditions when multiple threads compute concurrently. That does not mean every source data structure, accumulator, or API used is already thread-safe; the entire processing path must be reviewed.

**Not mandatory everywhere.** Services that write to a database, counters, loggers, UI event handlers, and network operations are not pure functions. For stateful business logic, an object that manages state explicitly can be more accurate and easier to understand than trying to force everything into a Stream or lambda.

## 10. Common Misconceptions

- **"Same output means referential transparency."** False if the call also logs, mutates state, or throws different errors.
- **"Adding `final` makes a function pure."** False: `final` on a reference variable does not prevent mutating the object's contents.
- **"`record` and `List.copyOf` always create deeply immutable data."** False for elements or components that reference mutable objects.
- **"Lambdas and Streams are functional/pure by default."** False: a lambda body can still access global variables and perform I/O.
- **"Two objects equal by `equals` can always be substituted for each other."** Insufficient in contexts that observe identity, aliasing, or state.
- **"Every call can be replaced by a single precomputed result."** False when inputs change, there are side effects, or exception timing must be preserved.
- **"Pure functions guarantee a parallel stream always produces the same result."** Insufficient if the reduction operation is not properly associative or the source is mutated concurrently.

## 11. Self-Check Exercises

1. Given `int square(int x) { return x * x; }` and `x = 5`, when can `square(5)` be replaced with `25`? State the assumptions about the numeric type and observable behavior.
2. Why is `int f() { log(); return 5; }` not referentially transparent, even though calling it multiple times always returns `5`?
3. `long price(List<Item> items)` only reads each element. Can the result always be cached by **list reference**? What happens if the list or its elements are mutable?
4. Compare `isExpired(deadline)` using `Instant.now()` with `isExpired(deadline, observedAt)` taking the timestamp as an argument. Which option is easier to test with two fixed timestamps?
5. In Java, why does using `==` on two objects make the reasoning "same content, interchangeable" dangerous?

**Answer hints:** (1) With a fixed `5`, multiplication within the `int` range does not overflow and has no side effects; the result is `25`. (2) Removing the call loses the log entry. (3) No; if the data changes over time, the same reference key can represent different data. (4) The version taking `observedAt` is purer and does not depend on system time. (5) `==` compares reference identity, unlike `equals` which compares content/value contract.

**Conclusion:** Referential transparency allows replacing an expression with its value while preserving observable behavior. In Java, an effective practice is to design pure computations over immutable data, pass environment data explicitly into functions, and keep side effects at integration boundaries. As a result, programs become easier to reason about, test, and change while still utilizing Java's full object-oriented capabilities.
