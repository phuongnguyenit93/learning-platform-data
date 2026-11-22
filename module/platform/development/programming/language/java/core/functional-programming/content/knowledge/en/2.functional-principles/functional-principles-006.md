# Eager Evaluation and Lazy Evaluation in Java

**Eager evaluation** computes an expression immediately when the program reaches the point where its value is needed. **Lazy evaluation** defers the computation until there is an actual request to consume the result. This is a difference in **execution timing**, not merely a shorter way of writing code.

In functional programming with Java, these two concepts are especially important when working with `Stream`, `Supplier`, short-circuiting logical operators, and the fallback value selection methods of `Optional`.

After this lesson, you will be able to:
- Distinguish an expression that is evaluated immediately from work that is only described.
- Predict the execution timing of `map`, `filter`, `limit`, `findFirst`, and Stream terminal operations.
- Choose correctly between `orElse` and `orElseGet`, and use `Supplier` to defer work.
- Identify risks related to side effects, exceptions, resources, memory, and re-runnability.

## 1. Fundamentals: a computed value or work to be computed?

Consider a regular method call:

```java
String result = normalize(loadText());
```

Java evaluates the argument `loadText()` **before** calling `normalize(...)`. If `loadText()` accesses the disk or throws an exception, that happens right at the line above; `normalize` cannot decide to skip computing an argument that has already been passed in.

To pass **how to produce a result** instead of an already-produced result, use a zero-argument function such as `Supplier<T>`:

```java
Supplier<String> pending = () -> loadText(); // does not call loadText() yet
String result = normalize(pending.get());     // loadText() runs at get()
```

The two snippets above are illustrative examples that require `loadText`, `normalize`, and `import java.util.function.Supplier;` in an actual program. The lambda only holds the behavior to be executed later; `get()` itself is what triggers it.

Java does **not** evaluate every expression lazily by default. Even with lambdas, values used to construct an object or arguments passed into a lambda may still have been computed beforehand. For example, `() -> expensive()` defers the call to `expensive()`, whereas `String s = expensive(); Supplier<String> f = () -> s;` does not.

### Short-circuiting is a form of avoiding unnecessary evaluation

```java
String name = null;
boolean valid = name != null && !name.isBlank();
```

The right-hand side of `&&` does not run if the left-hand side is `false`; similarly, the right-hand side of `||` does not run if the left-hand side is `true`. The conditional operator `condition ? a : b` only evaluates one of the two branches `a` or `b` after evaluating `condition`. This is a Java language rule, not a property specific to Stream. With `&` and `|` on two `boolean` operands, both sides are evaluated: do not substitute them arbitrarily if the right-hand side can throw an exception or has side effects.

## 2. Stream: declare the pipeline first, traverse elements when there is a terminal operation

A Stream pipeline typically consists of:
1. **Source**: `collection.stream()`, `Stream.of(...)`, `Files.lines(...)`...
2. **Intermediate operations**: `map`, `filter`, `distinct`, `sorted`, `peek`, `limit`... They create a new Stream describing an additional processing step, usually without traversing the source yet.
3. **Terminal operations**: `toList`, `collect`, `forEach`, `reduce`, `count`, `findFirst`, `anyMatch`... They trigger the processing needed to produce the specified result or side effect.

A complete runnable example on Java 17+:

**File: `EvaluationDemo.java`**

```java
import java.util.List;
import java.util.stream.Stream;

public class EvaluationDemo {
    private static int doubleValue(int value) {
        System.out.println("map " + value);
        return value * 2;
    }

    public static void main(String[] args) {
        System.out.println("A: create pipeline");
        Stream<Integer> pipeline = List.of(1, 2, 3, 4).stream()
                .map(EvaluationDemo::doubleValue)
                .filter(value -> {
                    System.out.println("filter " + value);
                    return value > 4;
                });

        System.out.println("B: source not traversed yet");
        int first = pipeline.findFirst().orElse(-1);
        System.out.println("C: result = " + first);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 EvaluationDemo.java
java EvaluationDemo
```

**Exact stdout:**

```text
A: create pipeline
B: source not traversed yet
map 1
filter 2
map 2
filter 4
map 3
filter 6
C: result = 6
```

Step-by-step explanation:
- The two calls `map(...)` and `filter(...)` only build the pipeline; neither `map` nor `filter` is printed yet.
- `findFirst()` needs to find the first element that passes `filter`, so it starts requesting data from the source.
- With this **sequential Stream**, element 1 goes through `map` then `filter`, followed by element 2, and then element 3. This is typically how each element is processed through multiple stages, rather than always running `map` over the entire list first and only then `filter`.
- After seeing `3 * 2 = 6` satisfy the condition, `findFirst` stops. Element 4 is not processed, avoiding unnecessary work.
- `orElse(-1)` here takes a simple constant; `findFirst()` has already created an `Optional<Integer>` and only uses `-1` if no value is found.

**Important:** `Stream` does not pre-store intermediate results as a new list after each step. However, not every operation can emit results immediately: stateful operations such as `sorted`, and some cases of `distinct` or `skip`, may require significant accumulation/traversal. Optimizations and the number of lambda invocations may also depend on the source, the terminal operation, and what the Stream specification permits implementations to do.

## 3. The terminal operation determines how much work needs to be performed

For the same intermediate pipeline, different terminal operations can require different amounts of processing:

| Terminal | Processing requirement |
| --- | --- |
| `findFirst()` | Can stop as soon as it encounters the first matching element in encounter order. |
| `anyMatch(predicate)` | Can stop when an element satisfying the predicate is found. |
| `allMatch(predicate)` | Can stop when an element not satisfying the predicate is encountered. |
| `limit(n).toList()` | With a suitable pipeline, can stop after producing `n` elements. |
| `toList()`, `collect(...)` | Usually needs to traverse all output elements of a finite source. |
| `count()` | Can use the source's size information and skip some intermediate steps that do not affect the count, depending on the pipeline. |

Short example:

```java
List<Integer> firstThree = java.util.stream.Stream.iterate(1, n -> n + 1)
        .filter(n -> n % 10 == 0)
        .limit(3)
        .toList();
// firstThree = [10, 20, 30]
```

This `iterate` source is infinite in principle; `limit(3)` allows `toList()` to complete once three elements divisible by 10 are obtained. Calling `toList()` on the infinite source itself without a stopping condition will not terminate normally. Placing `sorted()` before `limit` on an infinite stream can also prevent the process from ever producing a result, because `sorted` needs to know the entire input before determining the complete order.

**Do not infer the number of lambda invocations solely from the presence of a terminal operation.** For example, for a `SIZED` source, `stream.map(f).count()` may not call `f` at all, because `map` does not change the number of elements. Therefore, never rely on side effects inside `map` or `peek` as mandatory work that must run. When intentional side effects are needed, use an appropriate terminal operation such as `forEach`, while understanding ordering and parallelism rules.

## 4. Supplier: defers a value, does not automatically cache the result

`Supplier<T>` is a functional interface with the method `T get()`. It is useful when work might be skipped, is expensive, or only needs to be performed at the point of decision.

Complete example:

**File: `FallbackDemo.java`**

```java
import java.util.Optional;
import java.util.function.Supplier;

public class FallbackDemo {
    private static String backup() {
        System.out.println("Creating fallback data");
        return "fallback";
    }

    public static void main(String[] args) {
        Optional<String> available = Optional.of("ready");

        System.out.println("orElse: " + available.orElse(backup()));
        System.out.println("orElseGet: " + available.orElseGet(FallbackDemo::backup));

        Supplier<String> pending = () -> {
            System.out.println("Running task");
            return "done";
        };

        System.out.println("Created Supplier");
        System.out.println("get: " + pending.get());

        Optional<String> missing = Optional.empty();
        System.out.println("empty: " + missing.orElseGet(FallbackDemo::backup));
    }
}
```

Run:

```bash
javac -encoding UTF-8 FallbackDemo.java
java FallbackDemo
```

**Exact stdout:**

```text
Creating fallback data
orElse: ready
orElseGet: ready
Created Supplier
Running task
get: done
Creating fallback data
empty: fallback
```

Why is `backup()` called on the `orElse` line even though `available` already has a value? Because Java must evaluate the argument of `orElse(T other)` **before** calling the method. It still returns `"ready"`, but the work of creating the fallback has already occurred. In contrast, `orElseGet(Supplier<? extends T>)` only calls the Supplier's `get()` if the `Optional` is empty. With `Optional.empty()`, the fallback is genuinely needed.

Distinguish the APIs:
- `optional.orElse(value)`: `value` is already computed before the call.
- `optional.orElseGet(() -> create())`: defers creating the fallback until empty.
- `optional.orElseThrow(() -> new IllegalStateException("missing"))`: defers creating the exception until empty.
- `optional.map(fn)`: `fn` is only called when `Optional` has a value; this is not a Stream pipeline, but an immediate transformation on the current Optional state.

**Lazy does not mean memoization (caching the result).** Every time `pending.get()` is called, the lambda in the example above runs again. If you want it to execute only once and reuse the result, you must design your own cache or use an API with an appropriate caching contract. When shared across multiple threads, a one-time initialization mechanism must handle thread safety; `Supplier` itself does not guarantee that.

## 5. Practical impact: timing, exceptions, side effects, and resources

### Performance and memory

Lazy evaluation can avoid unused computations, allowing pipelines to run over large sources without building multiple intermediate collections. For example, `filter(...).findFirst()` is usually a better fit for finding a single element than creating a list of all matching elements and then taking the first one.

However, lazy is **not always faster**: creating pipelines/lambdas, boxing with `Stream<Integer>`, stateful processing like `sorted`, and terminal steps still have overhead. Measure with appropriate benchmarks when optimizing, keeping correctness as the top priority. For large integer computations, consider `IntStream` to avoid boxing.

### When exceptions are thrown

```java
Supplier<Integer> pending = () -> 10 / 0; // creating the lambda does not throw an error
int result = pending.get();               // ArithmeticException here
```

Similarly, an exception originating from a `map` lambda usually occurs when the terminal operation actually processes that element. If short-circuiting skips the failing element, the exception may not appear at all. This changes where errors are observed and when logs are written.

### Side effects and ordering

A pipeline should prefer functions that do not mutate external state. Do not rely on `peek` always being called or `map` always processing every element. If using `parallelStream()`, execution order and threads may differ from a sequential pipeline; `forEach` does not guarantee encounter order, whereas `forEachOrdered` respects encounter order if present. Shared side effects must be properly synchronized; it is better to prefer pure transformations and appropriate collectors.

### Sources with resources that must be closed

A Stream created by `Files.lines(path)` uses I/O resources and must be closed, even though intermediate operations are lazy:

```java
try (java.util.stream.Stream<String> lines =
             java.nio.file.Files.lines(path)) {
    java.util.Optional<String> match = lines
            .filter(line -> line.contains("ERROR"))
            .findFirst();
    // use match while the resource is still open
}
```

This is an illustrative snippet assuming a `path` variable of type `java.nio.file.Path` is already defined and `IOException` is handled or declared. Do not return a Stream backed by a closed resource for later execution.

## 6. Designing pipelines to match your goal

Suppose you need to find the first valid record and transform it:

```java
java.util.Optional<String> result = names.stream()
        .filter(name -> name != null && !name.isBlank())
        .map(String::trim)
        .findFirst();
```

This is an illustrative snippet with `names` as an existing `List<String>`. Laziness allows the pipeline to stop once a result is found. Operation order **matters**: putting a very expensive `map` before `filter` can compute unnecessarily for many elements; however, only reorder operations when doing so preserves semantics. For instance, checking `isBlank()` before vs. after `trim()` should be considered according to business specifications and null values.

You can recreate a stream after consumption by storing how the source is created:

```java
Supplier<java.util.stream.Stream<String>> source = names::stream;
long count = source.get().count();
java.util.List<String> copy = source.get().toList();
```

Each `get()` creates a **new Stream**, instead of reusing a Stream that has already had a terminal operation. With mutable data, two calls may observe different contents if the collection changes between them. If you only have a single Stream, calling a terminal operation a second time is invalid (usually throwing `IllegalStateException`).

### Quick selection table

| Need | Suitable approach | Reason |
| --- | --- | --- |
| Need to compute an argument immediately for a call | Regular Java method call | The value is produced before invoking the method. |
| Expensive fallback computation that may not be used | `Optional.orElseGet(...)` | Only creates the fallback when a value is missing. |
| Pass work to be invoked later | `Supplier<T>` | Not computed before `get()`; does not cache automatically. |
| Find one element in a large list | `stream().filter(...).findFirst()` | Can stop early. |
| Transform all elements into a list | `stream().map(...).toList()` | Terminal operation requires collecting the output elements. |
| Null-safe condition check | `x != null && predicate(x)` | The right-hand side is skipped if `x == null`. |
| Must record side effects for every element | Use an explicit traversal design and appropriate terminal | Do not rely on intermediate side effects that may be elided. |

## 7. Common mistakes and how to self-check

1. **Confusing building a Stream with running a Stream:** `map`/`filter` do not execute immediately when declaring the pipeline; place breakpoints/logs both before and after the terminal operation to observe.
2. **Mistaking `orElse` for lazy:** passing `expensive()` to `orElse` still calls `expensive()`; use `orElseGet` when deferral is needed.
3. **Expecting `peek` or `map` to always produce side effects:** a terminal operation may short-circuit or optimize away some steps; separate side effects from transformations whenever possible.
4. **Reusing a consumed Stream:** each Stream serves only one terminal operation chain; create a new Stream if you need to traverse again.
5. **Assuming lazy automatically caches results:** calling `Supplier.get()` again may re-execute the work and trigger side effects again.
6. **Forgetting a terminal operation or closing resources:** a pipeline without a terminal operation does no traversal; a Stream backed by a file must be closed with `try-with-resources`.
7. **Assuming `limit` always caps all work:** operations such as `sorted` before `limit` may have to consume the entire source.
8. **Inferring execution order from a parallel Stream:** to get ordered results, understand encounter order and the corresponding terminal operation; do not depend on internal log order.

**Self-check:**
- With `Optional.of("A").orElse(expensive())`, does `expensive()` run? **Yes**: the argument is evaluated eagerly.
- With `Optional.of("A").orElseGet(() -> expensive())`, does it run? **No**: the Optional already has a value.
- With the sequential pipeline `Stream.of(1, 2, 3).filter(n -> n > 1).findFirst()`, what is the result? **`Optional[2]`**; processing can stop at 2.
- Does `Supplier<T>` guarantee computing only once? **No**; a separate memoization mechanism is needed.
- Why is `map(...).count()` unsuitable for enforcing per-element logging? **Because** `count` may rely on the source size and skip calling `map` if the count does not change.

When reading functional-style Java code, ask two questions: **“Does this line produce a value or only describe how to produce a value?”** and **“Which operation forces that value to be produced?”**. Answering these two questions accurately helps predict performance, exception timing, and side effects in your program.
