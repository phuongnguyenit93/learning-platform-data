# Captured Variables and the Effectively Final Requirement

> **Chapter:** Behavioral Functions and Types  
> **Context:** In the Java Stream API, `filter`, `map`, `reduce`, `collect`, and many other operations accept behavioral functions as lambdas or method references. When these functions use variables from an enclosing scope, Java enforces the **capture** and **effectively final** rules.

## Learning Objectives

After this lesson, you will be able to:

1. Identify which variables are **captured** by a lambda and distinguish local variables from object fields.
2. Explain the **final or effectively final** rule when a lambda accesses local variables, method parameters, and variables from an enclosing scope.
3. Predict which code snippets compile, which produce errors, and how to fix them while preserving the intended processing semantics.
4. Distinguish **not reassigning a reference** from **not mutating the state of the object** that the reference points to.
5. Design lambdas that do not depend on mutable state to process sequential or parallel Streams more safely.
6. Replace external-variable accumulation patterns with `sum`, `reduce`, or `collect` when appropriate.

The examples use Java 17+ syntax (some lambda and Stream syntax has been available since Java 8; `Stream.toList()` was added in Java 16). Short illustrative snippets are written as if placed inside a method, with necessary `import`s included or noted in the example.

## 1. Where Do Lambdas Use Variables?

A lambda is an expression representing a behavioral function. In the Stream API, we commonly pass lambdas to functional interfaces such as:

| Functional interface | Abstract method | Stream example |
|---|---|---|
| `Predicate<T>` | `boolean test(T value)` | `filter(n -> n > limit)` |
| `Function<T, R>` | `R apply(T value)` | `map(name -> name.trim())` |
| `Consumer<T>` | `void accept(T value)` | `forEach(value -> log(value))` |
| `Supplier<T>` | `T get()` | Container supplier when using a collector |
| `BinaryOperator<T>` | `T apply(T left, T right)` | `reduce((a, b) -> a + b)` |

Consider an example:

~~~java
import java.util.List;

List<Integer> prices = List.of(45, 120, 75, 200);
int minimum = 100;

List<Integer> expensive = prices.stream()
        .filter(price -> price >= minimum)
        .toList();

System.out.println(expensive); // [120, 200]
~~~

Two names appear in the lambda `price -> price >= minimum`, yet their roles are very different:

- `price` is a **parameter** of the lambda; the Stream passes each element into this parameter.
- `minimum` is a local variable declared **outside** the lambda but used **inside** the lambda.

A lambda's use of `minimum` is called **capturing a variable from an enclosing scope** (*capturing a local variable*). The lambda can continue using that value after the method call containing the local variable has returned, because the captured value is retained according to function-object semantics rather than relying on keeping a local variable slot alive on the stack.

**Not every name appearing in a lambda is captured.** The parameter `price` is an input to the lambda; only variables or references from an enclosing scope involve capture.

## 2. What Is the Effectively Final Rule?

A local variable used by a lambda must be declared `final` **or be effectively final**. In practical terms:

- **Explicit `final`:** the variable is declared with the `final` keyword and cannot be reassigned after being assigned a value according to Java language rules.
- **Effectively final:** the variable **does not have the `final` keyword**, yet the program never reassigns it after its initial valid assignment. Java can treat the variable as a `final` variable for capture purposes.
- Reassignment `=`, compound assignment `+=`, `-=`, or operators `++`, `--` can cause a variable to **no longer be effectively final**.

Valid example:

~~~java
import java.util.List;

List<Integer> values = List.of(4, 9, 12);

final int thresholdA = 8; // Explicit final
int thresholdB = 8;       // Effectively final because it is never reassigned

System.out.println(values.stream()
        .filter(n -> n > thresholdA)
        .toList()); // [9, 12]

System.out.println(values.stream()
        .filter(n -> n > thresholdB)
        .toList()); // [9, 12]
~~~

Invalid example:

~~~java
import java.util.List;

List<Integer> values = List.of(4, 9, 12);
int threshold = 8;
threshold = 10; // Variable threshold is reassigned

// Compile error: threshold is not effectively final.
List<Integer> result = values.stream()
        .filter(n -> n > threshold)
        .toList();
~~~

The error message typically looks like:

~~~text
Local variable threshold defined in an enclosing scope must be
final or effectively final
~~~

Note: **the rule inspects how the variable is assigned in source code**, not whether the value after reassignment happens to equal the old value. For instance, `threshold = threshold;` is still a reassignment and prevents the variable from being effectively final.

### 2.1. "Assigned Only Once" Does Not Mean Always Assigned at the Declaration Line

A variable can be assigned in different branches as long as along **every valid execution path**, it is initialized properly and never reassigned.

~~~java
import java.util.function.IntPredicate;

boolean promotion = true;
int minimum;

if (promotion) {
    minimum = 50;
} else {
    minimum = 100;
}

IntPredicate passes = value -> value >= minimum;
System.out.println(passes.test(75)); // true
~~~

`minimum` is **effectively final** because every execution path assigns it only once before it is used in the lambda. Java also requires the variable to be **definitely assigned** before being read; being effectively final does not replace this initialization requirement.

By contrast:

~~~java
boolean promotion = true;
int minimum = 50;
if (promotion) {
    minimum = 100; // Reassigns an already initialized variable
}

// Predicate<Integer> p = x -> x >= minimum;
// Error if the lambda accesses minimum.
~~~

If the goal is to pick a configuration value conditionally, you can compute it once:

~~~java
boolean promotion = true;
int minimum = promotion ? 50 : 100;

java.util.function.IntPredicate passes = value -> value >= minimum;
System.out.println(passes.test(75)); // true
~~~

Using `var` or explicit types does not change the effectively final rule; here, writing a conditional expression makes it clear that `minimum` is not reassigned.

### 2.2. Method Parameters Are Also Subject to This Rule

~~~java
import java.util.function.IntPredicate;

class Filters {
    static IntPredicate greaterThan(int limit) {
        return value -> value > limit; // limit is a captured parameter
    }
}
~~~

`limit` is not reassigned inside the method, so it is effectively final. If you add `limit++` in the same method, capturing it will fail to compile.

Local variables declared in an enclosing scope of an **anonymous class** must satisfy the same rule. This is not a restriction exclusive to lambda syntax.

## 3. Why Does Java Require Effectively Final?

Distinguish two things:

1. **Retaining a value so a function can use it later.**
2. **Sharing a mutable local variable slot so the function and the outer method continuously mutate it together.**

Java chose capture-by-**value** semantics for local variables: primitive values are captured as values, while reference variables are captured as a **reference** to an object. There is no guarantee that a lambda holds a reassignable local variable slot from the enclosing scope.

Example of a lambda returned for later use:

~~~java
import java.util.function.IntPredicate;

class PredicateFactory {
    static IntPredicate atLeast(int minimum) {
        return value -> value >= minimum;
    }

    public static void main(String[] args) {
        IntPredicate adultAge = atLeast(18);

        System.out.println(adultAge.test(16)); // false
        System.out.println(adultAge.test(20)); // true
    }
}
~~~

When `atLeast(18)` returns, the parameter variable `minimum` from that call is no longer in the original execution frame; `adultAge` can still use the captured value `18`.

The effectively final requirement makes this semantic explicit: developers cannot write `minimum = 21` later in an enclosing block and implicitly expect the lambda to maintain a live link to that local variable slot.

With the Stream API, this rule is especially useful because intermediate operations are typically **lazy**: a lambda is declared upfront but may be invoked later when a terminal operation executes.

## 4. Capturing Primitives vs. Capturing References Are Two Different Things

### 4.1. For Primitives: The Value Is Retained

~~~java
import java.util.function.IntPredicate;

int threshold = 10;
IntPredicate greaterThan = value -> value > threshold;

System.out.println(greaterThan.test(12)); // true

// threshold = 20; // If uncommented, compile error.
~~~

Here, the lambda uses the value `10`. It is not an independent variable inside the lambda that outer code can reassign.

### 4.2. For Objects: The Reference Does Not Change, Yet Its Contents Can

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;

List<String> acceptedNames =
        new ArrayList<>(List.of("An", "Bình"));

Predicate<String> accepted =
        name -> acceptedNames.contains(name);

System.out.println(accepted.test("Chi")); // false

acceptedNames.add("Chi"); // Mutates List contents, does not reassign variable
System.out.println(accepted.test("Chi")); // true
~~~

The local variable `acceptedNames` **remains effectively final**: it never receives a new reference. However, the `ArrayList` object that this variable references has changed.

This is the easiest point to confuse:

| What changes? | Does the local variable lose effectively final? | Can it change lambda behavior? |
|---|---|---|
| `threshold = 20` after initializing `threshold` | **Yes** | Does not compile if a lambda captures that variable |
| `names = new ArrayList<>()` after initializing `names` | **Yes** | Does not compile if a lambda captures that variable |
| `names.add("Chi")` | **No** | **Yes**, if the lambda reads `names` contents |
| `array[0]++` | **No** | **Yes**, if the lambda reads `array[0]` |
| `object.setStatus("DONE")` | **No** | **Yes**, if the lambda reads the object's state |

The `final` keyword **does not make an object immutable either**:

~~~java
import java.util.ArrayList;
import java.util.List;

final List<Integer> numbers = new ArrayList<>();
numbers.add(10); // Valid: mutates object contents

// numbers = new ArrayList<>(); // Error: cannot reassign a final variable
~~~

If you want genuinely stable data for filtering, design immutable data structures, take appropriate snapshots, or avoid mutating state that the lambda depends on. An effectively final reference **is not synonymous** with thread safety.

### 4.3. Lazy Streams Can Observe Object State at Execution Time

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<Integer> allowed = new ArrayList<>(List.of(2, 4));
Stream<Integer> pipeline = List.of(1, 2, 3, 4).stream()
        .filter(allowed::contains);

allowed.add(3); // Modifies the lookup list before the terminal operation.

System.out.println(pipeline.toList()); // [2, 3, 4]
~~~

The Stream is declared beforehand, yet `filter` executes when `toList()` is called. The lambda/method reference retains a reference to `allowed`; it **does not snapshot the entire contents** of the `ArrayList` at pipeline creation time.

The example above only illustrates a **sequential change before consumption** on an auxiliary lookup list, without modifying the source `List.of(1, 2, 3, 4)` directly. Mutating state read by a predicate **while a pipeline is running** can produce unstable results, especially in parallel Streams.

When you need results fixed to an initial configuration, intentionally snapshot the value or data:

~~~java
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

Set<Integer> allowedSnapshot = Set.copyOf(List.of(2, 4));
Predicate<Integer> isAllowed = allowedSnapshot::contains;

System.out.println(
        List.of(1, 2, 3, 4).stream().filter(isAllowed).toList()
); // [2, 4]
~~~

`Set.copyOf` creates a structurally unmodifiable set; here the `Integer` elements are also immutable. With a set containing mutable objects, copying the collection this way only copies element references and does not automatically make each object immutable.

## 5. Capturing Local Variables Differs from Accessing Fields

The effectively final requirement applies to **captured local variables**, including method parameters, rather than forbidding every kind of state change inside a lambda.

~~~java
import java.util.List;

class ThresholdFilter {
    private int threshold = 10; // Instance field

    List<Integer> filter(List<Integer> source) {
        return source.stream()
                .filter(n -> n > threshold) // Reads field via this
                .toList();
    }

    void setThreshold(int newValue) {
        threshold = newValue; // Valid at compile time
    }
}
~~~

Here the lambda accesses `this.threshold`; `this` inside a lambda refers to **the enclosing instance**, not a new `this` object like in an anonymous class. Fields can be reassigned and are not constrained by the local-variable effectively final rule.

However, **compiling cleanly does not mean safe concurrent execution**. If another thread modifies `threshold` while the Stream is processing, the application must explicitly design synchronization, *visibility*, and consistency. Merely adding `volatile` to a field can assist visibility in certain cases, yet it does not make compound operations atomic or create consistent snapshots.

A more predictable choice is to fix the configuration at the start of the method:

~~~java
import java.util.List;

class ThresholdFilter {
    private int threshold = 10;

    List<Integer> filter(List<Integer> source) {
        int currentThreshold = threshold; // Primitive value snapshot
        return source.stream()
                .filter(n -> n > currentThreshold)
                .toList();
    }
}
~~~

`currentThreshold` is effectively final, so every invocation of the predicate during this `filter` call uses the same value. If multiple threads access the field concurrently, reading the snapshot must still follow the application's synchronization/visibility design.

### 5.1. Method References Can Also Capture a Receiver

~~~java
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

Set<String> allowed = Set.of("java", "stream");
Predicate<String> predicate = allowed::contains;

System.out.println(
        List.of("java", "sql", "stream").stream()
                .filter(predicate)
                .toList()
); // [java, stream]
~~~

`allowed::contains` is a **bound method reference**: it captures the receiver `allowed`. Reference-capture and mutable-state rules must still be considered when replacing the receiver with a mutable object. Method references do not automatically make code *pure* or parallel-safe.

## 6. Why Does Accumulating into an External Variable Inside a Lambda Fail?

A very common pattern when converting a loop to a Stream:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);
int total = 0;

// COMPILE ERROR:
// values.stream().forEach(value -> total += value);
~~~

`total += value` reassigns the local variable `total`. Because it is captured in the lambda, `total` must be effectively final, so this reassignment is forbidden.

A traditional loop has no capture restriction:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);
int total = 0;

for (int value : values) {
    total += value;
}

System.out.println(total); // 10
~~~

This is a case where **a regular loop is completely reasonable**. If you choose a Stream, express the aggregation using the API instead of trying to bypass lambda restrictions.

### 6.1. Use Specialized Aggregations: sum, count, average

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);

int total = values.stream()
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 10
~~~

`mapToInt` turns `Stream<Integer>` into `IntStream`, then `sum()` performs the addition. For data that may exceed `int` bounds, consider `mapToLong` / `LongStream.sum` or `BigInteger` / `BigDecimal` depending on precision needs. Integer addition in Java can overflow.

### 6.2. Use reduce for Associative Aggregations

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);

int total = values.stream()
        .reduce(0, Integer::sum);

System.out.println(total); // 10
~~~

In `reduce(identity, accumulator)`, the merge operation must satisfy the **identity** and **associativity** contracts so it works properly when splitting and combining in parallel Streams. For instance, integer addition above has identity `0` and is associative under Java's 32-bit modular `int` arithmetic.

Do not turn `reduce` into an operation that mutates a mutable container shared across threads. For collecting into lists, maps, or groups, `collect` and an appropriate collector are generally the right choice.

### 6.3. Use collect to Gather and Group Data

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> words = List.of("java", "jdk", "stream", "sql");

Map<Integer, List<String>> byLength = words.stream()
        .collect(Collectors.groupingBy(String::length));

System.out.println(byLength.get(3)); // [jdk, sql]
~~~

The library manages the collector's containers and result merging. You do not need an external `Map` variable and `computeIfAbsent` calls inside `forEach`. In parallel Streams, the framework can supply thread-local containers for sub-tasks and merge them with the combiner according to the collector contract; that differs fundamentally from every lambda concurrently mutating a shared `ArrayList` or `HashMap`.

## 7. "Workarounds" for Effectively Final Using Mutable Objects: Valid Yet Error-Prone

One way to make the accumulation snippet compile is to wrap the number in an array:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);
int[] total = {0};

values.stream().forEach(value -> total[0] += value);

System.out.println(total[0]); // 10 for this sequential pipeline
~~~

The local variable `total` keeps the **same reference to the array**, so it is effectively final. Yet the element `total[0]` can change.

This is **not a recommended style** for data aggregation: the lambda has a side effect on external state. Switching to a parallel stream introduces a race condition:

~~~java
import java.util.stream.IntStream;

int[] total = {0};

IntStream.rangeClosed(1, 100_000)
        .parallel()
        .forEach(n -> total[0] += n); // Data race; increments can be lost

System.out.println(total[0]); // Unreliable result
~~~

`total[0] += n` is a read–add–write sequence, not an atomic update. Multiple threads can read the same stale value and overwrite each other. Do not rely on results that happen to look right across a few runs.

Replace it with:

~~~java
import java.util.stream.IntStream;

long total = IntStream.rangeClosed(1, 100_000)
        .parallel()
        .asLongStream()
        .sum();

System.out.println(total); // 5_000_050_000
~~~

Use `long` because the sum exceeds `int` range. There is no accumulation state in an outer scope; aggregation is managed by the Stream.

### 7.1. Does AtomicInteger Solve the Problem?

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

AtomicInteger total = new AtomicInteger();

IntStream.rangeClosed(1, 1_000)
        .parallel()
        .forEach(total::addAndGet);

System.out.println(total.get()); // 500500
~~~

In this example that **reads the entire stream**, `AtomicInteger` enables atomic updates and yields the correct sum within `int` range. Yet it still introduces shared state, update contention, side-effect dependency, and can negate parallel processing benefits.

More seriously, a pipeline with a **short-circuiting operation** like `findAny`, `anyMatch`, or `limit` does not guarantee that every element is processed; counting side effects inside `filter`/`map` may not match the expected element count. The Stream library can skip intermediate operations when optimization does not alter the defined result.

**Design conclusion:** `AtomicInteger` is useful for appropriate synchronization purposes, but should not be used by default to replace `sum`, `count`, `reduce`, or `collect`.

## 8. Capture in Loops: The Classic `for`-Index Mistake

Consider code intended to store three tasks to run later:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Runnable> tasks = new ArrayList<>();

// COMPILE ERROR: i++ makes i not effectively final.
// for (int i = 0; i < 3; i++) {
//     tasks.add(() -> System.out.println(i));
// }
~~~

`i` changes on every iteration, so it cannot be captured directly. The solution is to create a separate variable for **each iteration**:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Runnable> tasks = new ArrayList<>();

for (int i = 0; i < 3; i++) {
    int snapshot = i;
    tasks.add(() -> System.out.println(snapshot));
}

tasks.forEach(Runnable::run);
// 0
// 1
// 2
~~~

Each entry into the loop body creates a distinct `snapshot` variable assigned once. This is not "bypassing effectively final" but creating valid captured data.

An enhanced `for` loop is often simpler:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Runnable> tasks = new ArrayList<>();

for (String name : List.of("An", "Bình", "Chi")) {
    tasks.add(() -> System.out.println(name));
}

tasks.forEach(Runnable::run);
// An
// Bình
// Chi
~~~

The loop variable `name` in an enhanced `for` corresponds to a fresh variable per iteration, so it is effectively final as long as it is not reassigned inside the loop body. Do not confuse this with an index `i` incremented across iterations with `i++`.

## 9. Effectively Final in Lazy Pipelines

A captured local variable must be effectively final from the compiler's perspective, regardless of whether you call the terminal operation immediately or later:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> values = List.of(2, 5, 8, 11);
int threshold = 6;

Stream<Integer> pipeline = values.stream()
        .filter(value -> value > threshold); // Does not traverse values yet

System.out.println("Pipeline created");
System.out.println(pipeline.toList());        // [8, 11]
~~~

If you add `threshold = 9;` after creating the pipeline, the program **will not compile**, even if that assignment precedes `toList()`. Java does not establish a live link for a lambda to automatically read a local variable's new value.

A valid way to handle a business requirement that wants to change the threshold is to **create a new pipeline with the new configuration**:

~~~java
import java.util.List;

List<Integer> values = List.of(2, 5, 8, 11);

int firstThreshold = 6;
List<Integer> first = values.stream()
        .filter(n -> n > firstThreshold)
        .toList();

int secondThreshold = 9;
List<Integer> second = values.stream()
        .filter(n -> n > secondThreshold)
        .toList();

System.out.println(first);  // [8, 11]
System.out.println(second); // [11]
~~~

This also expresses intent more clearly when each run requires a fixed configuration. A Stream object that has executed a terminal operation cannot be reused; creating a new Stream from a re-traversable collection is appropriate.

## 10. Stateless and Non-Interfering: Two Related Yet Distinct Requirements

With Streams, especially parallel streams, behavioral functions generally must be:

- **Stateless:** the result of processing an element does not depend on state that can change while the pipeline runs, such as an external counter or a continuously updated field.
- **Non-interfering:** does not modify a data source that does not support concurrent modification while the Stream is traversing it.

Effectively final only concerns **whether a local variable can be reassigned**. It **does not guarantee** that a lambda is stateless or non-interfering.

Example of what not to do:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

// Avoid: side effect modifying the source itself during traversal.
// numbers.stream().forEach(n -> numbers.add(n * 2));
~~~

The example above can throw an exception or lead to undefined results depending on implementation. Even though `numbers` is effectively final, the lambda modifies the source collection itself.

A purer approach:

~~~java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4);

List<Integer> doubled = numbers.stream()
        .map(n -> n * 2)
        .toList();

System.out.println(doubled); // [2, 4, 6, 8]
System.out.println(numbers); // [1, 2, 3, 4]
~~~

The lambda `n -> n * 2` is an independent per-element transformation. The Stream has greater freedom to choose execution order, short-circuit, or run in parallel without altering the described values.

### 10.1. Side Effects in Intermediate Operations Can Mislead

~~~java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3);

long count = numbers.stream()
        .map(n -> {
            System.out.println("map: " + n);
            return n * 2;
        })
        .count();

System.out.println("count = " + count);
~~~

With a sized `List` source, a valid Stream implementation can deduce `count()` **without running `map`**. Therefore, do not use `map` or `peek` to perform a mandatory effect (business logging, data updates, charging money, incrementing counters).

If side effects are the actual goal, express them explicitly via an intentional terminal operation or an appropriate loop while considering ordering and concurrency. `forEach` on a parallel stream **does not guarantee encounter order**; `forEachOrdered` preserves order for ordered sources but may reduce throughput.

### 10.2. Is Reading a Mutable Field in a Parallel Stream Safe?

For example, a lambda `n -> n > configuration.minimum()` can validly capture an effectively final reference variable `configuration`, yet if another thread concurrently mutates `configuration`'s state, processing iterations may see differing values or hit visibility issues.

It is usually better to create an immutable configuration for a single run:

~~~java
import java.util.List;

int minimumForRun = 10;

List<Integer> result = List.of(5, 12, 20, 8)
        .parallelStream()
        .filter(n -> n >= minimumForRun)
        .toList();

System.out.println(result); // [12, 20]
~~~

Independent filter checks and fixed configuration data in the example make reasoning much easier. Even so, effectively final is **not** a parallel-safety proof for the entire algorithm: collectors, element objects, sources, ordering, and reductions must still be evaluated against the Stream API contract.

## 11. Capture in Callbacks, Method References, and Resources

Points to remember when integrating with other Stream sources:

**Callbacks capture data from the enclosing scope:** for instance, `fileName` in `line -> line.contains(fileName)` must be effectively final if it is a local variable. Even though the callback is invoked inside library code, capture rules still apply.

**Do not treat capture as a resource management mechanism:** a lambda can hold a reference to a `Reader` or I/O configuration object, yet that does not automatically close resources, extend resource lifetime safely, or permit safe use after closing.

**I/O-backed Streams must be closed when needed:**

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("application.log");
String marker = "ERROR"; // Effectively final

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long errors = lines
            .filter(line -> line.contains(marker))
            .count();

    System.out.println("Error line count: " + errors);
} catch (IOException | UncheckedIOException ex) {
    System.err.println("Cannot read log: " + ex.getMessage());
}
~~~

`marker` is captured; `Files.lines` provides a lazy file-backed data source. `try-with-resources` closes the Stream and releases associated resources. The effectively final rule and the resource-closing rule solve **two independent concerns**, both critical in real-world pipelines.

Regarding advanced module topics — custom collectors, `Spliterator`, parallel processing, and Stream Gatherers — this lesson provides a foundational principle: **processing functions should communicate through parameters and return values, avoiding reliance on shared mutable state**. When an operation genuinely requires state, use the state-management mechanism and concurrency contract of the respective API rather than creating shared variables outside a lambda.

## 12. Process for Fixing Capture Errors While Keeping Good Design

When you see the message *must be final or effectively final*, check step by step:

1. **Which variable is being captured?** Distinguish lambda parameters from local variables outside the lambda.
2. **Where is the variable reassigned?** Look for `=`, `+=`, `++`, or `--` on the variable in the enclosing scope, including assignments appearing after the lambda expression.
3. **Does the value actually need to change, or only be chosen once?** If it is just configuration for one run, compute a single final value conditionally or create a snapshot variable.
4. **Are you accumulating results?** Use `sum`, `count`, `reduce`, `collect`; or a regular loop if that is clearer and more suitable.
5. **Are you mutating a captured object?** Ensure you do not modify the Stream source itself and do not introduce unsynchronized shared state into parallel tasks.
6. **Are external resources involved?** Ensure proper I/O lifecycle handling, independent of capture.

| Situation | Appropriate fix | Avoid |
|---|---|---|
| `int limit = 5; limit = 10; filter(n -> n > limit)` | Compute `limit` once or create `finalLimit` for the pipeline | Using a single-element array just to evade the error |
| `int total = 0; forEach(n -> total += n)` | `mapToInt(...).sum()` or `reduce` | Creating a shared mutable variable |
| `for (int i = 0; i < n; i++)` with lambda using `i` | `int index = i` on each iteration | Expecting the lambda to capture per-iteration `i` automatically |
| Lambda reads mutable configuration object | Immutable snapshot per run, synchronize when needed | Letting another thread mutate configuration mid-run |
| Lambda adds elements to the Stream source itself | Build result collection with `map`/`filter`/`collect` | Mutating the source inside `forEach` |
| Reading files via `Files.lines` | `try-with-resources` and clean pipeline | Assuming terminal operations auto-close the Stream |

## 13. Self-Check Exercises

### Exercise 1. Will This Compile?

~~~java
import java.util.List;

int a = 10;
int b = a + 5;

List<Integer> numbers = List.of(1, 10, 20);
List<Integer> filtered = numbers.stream()
        .filter(n -> n > b)
        .toList();
~~~

**Answer:** Yes. Both `a` and `b` are assigned exactly once. `b` is validly captured; `filtered` evaluates to `[20]`.

### Exercise 2. Can the Outer Value Change After Creating the Lambda?

~~~java
import java.util.function.IntPredicate;

int minimum = 10;
IntPredicate predicate = value -> value >= minimum;
// minimum = 20;
~~~

**Answer:** You cannot uncomment the last line and still compile: the local variable `minimum` is no longer effectively final. If you want two thresholds, create two predicates or pass the threshold as a parameter to a predicate factory method.

### Exercise 3. Why Can the Change Still Be Observed?

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

List<String> names = new ArrayList<>();
Supplier<Integer> size = names::size;

names.add("An");
names.add("Bình");

System.out.println(size.get());
~~~

**Answer:** Prints `2`. The reference `names` is not reassigned, yet the `ArrayList` contents change; the bound method reference `names::size` reads the current size.

### Exercise 4. Should `int[] total` Be Used with a Parallel Stream?

**Answer:** No: `total[0] += n` is a non-atomic update and can cause a data race. Use `mapToLong(...).sum()`, `reduce`, or an appropriate collector to aggregate.

### Exercise 5. Fix Capture Error in a Loop

~~~java
import java.util.ArrayList;
import java.util.List;

List<Runnable> tasks = new ArrayList<>();

// Wrong:
// for (int i = 1; i <= 3; i++) {
//     tasks.add(() -> System.out.println(i));
// }
~~~

**Reference answer:**

~~~java
for (int i = 1; i <= 3; i++) {
    int itemNumber = i;
    tasks.add(() -> System.out.println(itemNumber));
}

tasks.forEach(Runnable::run); // 1, 2, 3 in insertion order
~~~

### Exercise 6. Does Effectively Final Guarantee a Pure Function?

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntUnaryOperator;

AtomicInteger counter = new AtomicInteger();
IntUnaryOperator op = x -> x + counter.incrementAndGet();
~~~

**Answer:** No. `counter` is an effectively final local variable, yet the lambda mutates the state of the `AtomicInteger` object on every call. The result of `op.applyAsInt(10)` depends on prior invocation counts and order. Atomic types make counter updates atomic; they do not make a lambda stateless.

---

**Takeaway:** When a lambda or method reference needs a local variable from an enclosing scope, that variable must be **final or effectively final**. The rule governs **variable reassignment**, and does not guarantee that the referenced object is immutable. In the Java Stream API, the most robust solution is usually to use **fixed configuration values**, write **non-interfering** behavioral functions, and let `reduce`/`collect`/specialized aggregations manage results, especially when processing in parallel.
