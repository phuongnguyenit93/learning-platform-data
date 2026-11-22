# Using `Supplier`, `BiFunction`, and `BinaryOperator` in Their Proper Roles

In the **Java Stream API**, operations like `filter`, `map`, `reduce`, `collect`, and collectors accept **behavioral functions** to describe how data is processed. Pipelines are evaluated *lazily*: most intermediate operations only execute when a terminal operation is invoked. Three functional interfaces that frequently appear when generating data, computing with two inputs, and combining results are `Supplier`, `BiFunction`, and `BinaryOperator`.

They can be written as lambdas or method references, but **they are not arbitrarily interchangeable**. Choosing the wrong function type can prevent compilation, violate `reduce`/`collect` semantics, or produce unstable results under parallel execution.

## 1. Looking at Inputs and Outputs to Distinguish Them

The types below belong to the `java.util.function` package, available since Java 8:

| Functional interface | Single abstract method | Meaning | Example |
| --- | --- | --- | --- |
| `Supplier<T>` | `T get()` | Takes no arguments; **supplies** a value `T` when called. | `ArrayList::new`, `() -> "new"` |
| `BiFunction<T, U, R>` | `R apply(T t, U u)` | Takes **two values**, possibly of different types, and returns a result of type `R`. | `(name, n) -> name + n` |
| `BinaryOperator<T>` | `T apply(T left, T right)` | Takes **two values of the same type `T`**, and returns a result also of type `T`. | `Integer::sum` |

`BinaryOperator<T>` **extends** `BiFunction<T, T, T>`; it is a specialized case used when behavior combines two values of the same type into one value of that same type. Conversely, `BiFunction<String, Integer, Long>` cannot be treated as a `BinaryOperator<?>`, because the input and output types are not uniform.

```java
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;
import java.util.function.Supplier;

Supplier<String> newLabel = () -> "pending";
BiFunction<String, Integer, String> appendIndex =
    (label, index) -> label + "-" + index;
BinaryOperator<Integer> add = Integer::sum;

System.out.println(newLabel.get());              // pending
System.out.println(appendIndex.apply("task", 7)); // task-7
System.out.println(add.apply(10, 20));            // 30
```

**Quick rule of thumb:** with no parameters, think `Supplier`; with two parameters needing one result, think `BiFunction`; if both parameters and the result must share the same type, `BinaryOperator` expresses the intent more clearly.

## 2. `Supplier<T>`: Providing Values or Creating Objects on Demand

`Supplier<T>` has a single `get()` method and takes no arguments. It commonly serves as a **factory** creating new objects, generating elements for a stream, or deferring fallback value computation.

### Creating a New Container for Each Request

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

Supplier<List<String>> newList = ArrayList::new;

List<String> left = newList.get();
List<String> right = newList.get();
left.add("Java");

System.out.println(left);          // [Java]
System.out.println(right);         // []
System.out.println(left == right); // false
```

**The interface itself does not guarantee that each `get()` call returns a new object.** That guarantee comes from the implementation `ArrayList::new`. For `collect`, `groupingBy`, and custom collectors requiring a mutable container, the supplier must typically create **independent containers** for each accumulation branch; using `() -> sharedList` easily causes mixed data and concurrency errors.

### Generating Elements on Demand with `Stream.generate`

```java
import java.util.List;
import java.util.UUID;
import java.util.function.Supplier;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Supplier<String> makeId = () -> UUID.randomUUID().toString();

List<String> ids = Stream.generate(makeId)
    .limit(3)
    .collect(Collectors.toList());

System.out.println(ids.size()); // 3
```

`Stream.generate(supplier)` creates a sequential, **unordered** (no guaranteed encounter order), potentially infinite stream; `limit(3)` sets a finite bound in this case. When the pipeline runs, the stream invokes the supplier to fulfill element demand. Do not assume `get()` is called only once for the entire stream, nor assume the call order or count when switching the pipeline to parallel. If the supplier holds mutable state, you must consider thread safety and result stability.

### Computing a Fallback Value Only When Truly Needed

```java
import java.util.Optional;
import java.util.function.Supplier;

Optional<String> cached = Optional.of("ready");

Supplier<String> fallback = () -> {
    System.out.println("Creating fallback value");
    return "default";
};

String result = cached.orElseGet(fallback);
System.out.println(result); // ready
// Does not print "Creating fallback value" because Optional already has a value.
```

`orElseGet(Supplier<? extends T>)` only calls the supplier when the `Optional` is empty; whereas the argument expression to `orElse(value)` is evaluated before the method is called. When creating a fallback value is expensive or has side effects, this difference is significant. **Supplier does not create lazy evaluation by itself**: deferral depends on whether the API accepting the supplier decides to call `get()`.

## 3. `BiFunction<T, U, R>`: Turning Two Inputs into One Result

`BiFunction` accepts two arguments that can have **different types** and returns a result of its own type. For example, combining a product name with a quantity to generate a label:

```java
import java.util.function.BiFunction;

BiFunction<String, Integer, String> formatOrder =
    (product, quantity) -> product + " x " + quantity;

System.out.println(formatOrder.apply("Notebook", 3));
// Notebook x 3
```

The three type parameters have clear roles: `T` is the first input type, `U` is the second input type, and `R` is the result type. If the result must pass through a subsequent transformation step, `BiFunction.andThen(Function<? super R, ? extends V>)` lets you attach an extra processing step:

```java
import java.util.function.BiFunction;

BiFunction<String, Integer, String> format =
    (product, quantity) -> product + " x " + quantity;

BiFunction<String, Integer, String> loudFormat =
    format.andThen(String::toUpperCase);

System.out.println(loudFormat.apply("notebook", 3));
// NOTEBOOK X 3
```

### Applying `BiFunction` in a Pipeline

`Stream.map` accepts a single-parameter `Function<T, R>`, so you cannot pass a `BiFunction` directly to `map`. If the second argument comes from context, you can use a single-parameter lambda to call `apply`:

```java
import java.util.List;
import java.util.function.BiFunction;
import java.util.stream.Collectors;
import java.util.stream.Stream;

BiFunction<String, Integer, String> attachBatch =
    (name, batchNo) -> name + "@batch-" + batchNo;

int batchNo = 12;
List<String> labels = Stream.of("filter", "map", "reduce")
    .map(name -> attachBatch.apply(name, batchNo))
    .collect(Collectors.toList());

System.out.println(labels);
// [filter@batch-12, map@batch-12, reduce@batch-12]
```

In other Java APIs, `Map.compute(key, remappingFunction)` takes a `BiFunction<? super K, ? super V, ? extends V>`: the function processes both the key and the old value. You must read the specific API's contract; for example, returning `null` from `Map.compute`'s remapping function can cause the existing mapping to be removed.

## 4. `BinaryOperator<T>`: Combining Two Values of the Same Type

`BinaryOperator<T>` is simply `BiFunction<T, T, T>` with a name indicating its role of **combining two values of the same type**. This is the type used by `reduce` when the input elements and the accumulated result share the same type.

```java
import java.util.Optional;
import java.util.function.BinaryOperator;
import java.util.stream.Stream;

BinaryOperator<Integer> add = Integer::sum;

int total = Stream.of(4, 6, 8).reduce(0, add);
Optional<Integer> maybeTotal = Stream.of(4, 6, 8).reduce(add);

System.out.println(total);              // 18
System.out.println(maybeTotal.orElse(0)); // 18
```

`reduce(identity, BinaryOperator<T>)` returns `T` and requires an appropriate initial identity value. `reduce(BinaryOperator<T>)` returns `Optional<T>` because the stream may be empty. For integer addition, `0` is the identity element; for multiplication, `1` is the identity element.

`BinaryOperator` also provides static methods `minBy(comparator)` and `maxBy(comparator)` to create operators that pick the smaller or larger element according to a comparator:

```java
import java.util.Optional;
import java.util.function.BinaryOperator;
import java.util.stream.Stream;

BinaryOperator<String> longest = BinaryOperator.maxBy(
    (a, b) -> Integer.compare(a.length(), b.length())
);

Optional<String> value = Stream.of("API", "Stream", "Java")
    .reduce(longest);

System.out.println(value.orElse("(empty)")); // Stream
```

When the goal is purely finding the maximum value, `stream.max(comparator)` is usually more direct; the `BinaryOperator.maxBy` example helps recognize that `reduce` expects a same-type combining operation. If the comparator considers two values equal, you should not rely on picking the left or right one to encode specific business requirements.

## 5. Three-Argument `reduce`: How Do `BiFunction` and `BinaryOperator` Work Together?

The general version of `Stream.reduce` has the following type signature:

```java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
```

Here, stream elements have type `T`, while the accumulated result has type `U`, which **can differ from `T`**:

- `identity`: the initial value of result type `U`.
- `accumulator`: combines an **intermediate result `U`** and **an element `T`** to produce a new `U`; therefore it uses `BiFunction<U, T, U>`.
- `combiner`: combines **two intermediate results of the same type `U`** to produce a `U`; therefore it uses `BinaryOperator<U>`.

Example computing the total number of characters in a stream of strings:

```java
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;
import java.util.stream.Stream;

BiFunction<Integer, String, Integer> countChars =
    (total, word) -> total + word.length();

BinaryOperator<Integer> mergeTotals = Integer::sum;

int charCount = Stream.of("Java", "Stream", "API")
    .parallel()
    .reduce(0, countChars, mergeTotals);

System.out.println(charCount); // 13 (= 4 + 6 + 3)
```

In a sequential execution branch, the accumulator receives the running total and the next string. When executing in parallel, branches may compute separate subtotals; the combiner sums those subtotals. Regardless of how many branches a particular execution uses, the correct result must obey the contracts of `reduce`.

### Rules for Correct Parallel Reduction

1. **The combiner must be associative:** `(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)` according to the operation's semantics. Integer addition qualifies; subtraction generally does not.
2. **The identity must be a two-sided identity for the combiner:** `combiner(identity, u) = combiner(u, identity) = u`.
3. **The accumulator must be compatible with the combiner:** `combiner(u, accumulator(identity, t)) = accumulator(u, t)` for any accumulated value `u` and element `t`.
4. **Behavioral functions must be non-interfering and not rely on mutable external state:** do not modify the source collection, and do not update a shared counter as the primary way of computing the result.

Common incorrect example:

```java
import java.util.stream.Stream;

// DO NOT USE as a reliable reduce operation when running in parallel:
int result = Stream.of(10, 3, 2)
    .parallel()
    .reduce(0, (left, right) -> left - right);

// Subtraction is not associative; 0 is not a two-sided identity either.
// You cannot derive a stable "sequential subtraction total" from this reduce.
```

**Commutativity** (`a ⊕ b = b ⊕ a`) is not a mandatory requirement for all reductions. For instance, string concatenation is associative but not commutative; on a source with encounter order and a compliant reduction, order remains part of the result semantics. Still, you must not rely on lambda execution order or side effects across parallel branches.

## 6. When to Use `Supplier` in `collect` vs. `BinaryOperator`?

`reduce` leans toward producing an **accumulated value** through combining operations. `collect` is *mutable reduction*: accumulating into a mutable container, typically suitable for building lists, grouping data (`groupingBy`), or writing custom collectors.

### Three-Argument `Stream.collect` Uses `BiConsumer`, Not `BinaryOperator`

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Binh", "Chi")
    .parallel()
    .collect(
        ArrayList::new,                     // Supplier<List<String>>
        (list, name) -> list.add(name),     // BiConsumer<List<String>, String>
        (left, right) -> left.addAll(right) // BiConsumer<List<String>, List<String>>
    );

System.out.println(names); // [An, Binh, Chi] for an ordered source
```

In this overload, `supplier` creates the container; `accumulator` adds one element; `combiner` **moves elements between two containers**. The last two functions have the `BiConsumer` contract: they perform mutations and **return no result** to `collect`. The expressions `list.add` and `left.addAll` happen to return `boolean`, but the lambdas are used in the `void` context of `BiConsumer`, so that value is discarded.

### `Collector.of` Has a `BinaryOperator<A>` Combiner

Unlike the overload above, `Collector.of` requires the combiner to accept two containers of type `A` and **return the merged container** of type `A`. This is where `Supplier` and `BinaryOperator` appear together:

```java
import java.util.StringJoiner;
import java.util.stream.Collector;
import java.util.stream.Stream;

Collector<String, StringJoiner, String> joinWords = Collector.of(
    () -> new StringJoiner(" | "),             // Supplier<StringJoiner>
    (joiner, word) -> joiner.add(word),          // BiConsumer<StringJoiner, String>
    (left, right) -> left.merge(right),          // BinaryOperator<StringJoiner>
    StringJoiner::toString                      // Function<StringJoiner, String>
);

String text = Stream.of("filter", "map", "reduce")
    .parallel()
    .collect(joinWords);

System.out.println(text); // filter | map | reduce
```

`Supplier<StringJoiner>` must create a new accumulator. In the combiner, `left.merge(right)` mutates `left` and returns `left` itself, satisfying the `BinaryOperator<StringJoiner>` signature. Accumulators across branches must be independent; do not return a shared `StringJoiner` from every supplier call. If you only need to join strings, the standard API `Collectors.joining(" | ")` is more concise; the `Collector.of` example illustrates how custom collectors are written.

### `Collectors.toMap` Uses `BinaryOperator` to Resolve Duplicate Keys

When turning a stream into a map, two elements may produce the same key. The `Collectors.toMap(keyMapper, valueMapper, mergeFunction)` overload requires a function that **combines two values of the same type** for duplicate keys:

```java
import java.util.Comparator;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<Character, String> longestByInitial = Stream.of("An", "Anh", "Binh")
    .collect(Collectors.toMap(
        word -> word.charAt(0),
        word -> word,
        BinaryOperator.maxBy(Comparator.comparingInt(String::length))
    ));

System.out.println(longestByInitial.get('A')); // Anh
System.out.println(longestByInitial.get('B')); // Binh
```

If you omit the merge function and duplicate keys occur, the two-argument overload of `Collectors.toMap` throws `IllegalStateException`. Meanwhile, `groupingBy` has the semantics of **collecting multiple elements into a group**; choose `groupingBy` when you need to keep all values per key, and `toMap` with a merge function when you need one aggregated value per key.

## 7. Common Confusions

| Confusion | Consequence | Correct understanding |
| --- | --- | --- |
| Passing `BiFunction` to `Stream.map` | Does not match `Function<T, R>` signature. | Wrap in `name -> biFunction.apply(name, context)` if a second argument exists. |
| Assuming `Supplier` always creates a new object | Shares a container across `collect` branches, causing bugs in parallel. | Use a factory like `ArrayList::new`; verify independence of `get()` results. |
| Using subtraction as `BinaryOperator` in parallel `reduce` | Violates associativity and/or identity requirements. | Use an appropriate associative operation, such as `Integer::sum`. |
| Using `reduce` with a mutable `ArrayList` as identity and calling `add` directly on it | The identity may be reused across multiple branches; breaks the reduction contract, especially in parallel. | Use `collect` with a supplier that creates separate containers. |
| Thinking `collect(supplier, accumulator, combiner)` requires the combiner to return a container | Confused with `Collector.of`; wrong types or wrong intent. | The `Stream.collect` overload uses `BiConsumer`; `Collector.of` uses `BinaryOperator` as the combiner. |
| Assuming every lambda is guaranteed to be called for every element | Short-circuiting, optimizations, and parallelism alter call counts and order. | Do not use side effects as a mandatory tracking mechanism; rely on terminal operation results. |

Specialized primitive types also help avoid boxing: `IntSupplier` (for `IntStream.generate`), `IntBinaryOperator` (for `IntStream.reduce`), `LongBinaryOperator`, `DoubleBinaryOperator`. For example, `IntStream.of(1, 2, 3).reduce(0, Integer::sum)` takes an operation matching `IntBinaryOperator` rather than requiring `BinaryOperator<Integer>`. Only use the `Integer` wrapper when the pipeline genuinely needs objects or generic APIs.

## 8. Process for Choosing the Right Behavioral Function

When writing a Java Stream API pipeline, ask three questions:

1. **Does it need input data?** If it only supplies a value, creates an object, or defers a fallback, use `Supplier<T>`; with `Stream.generate`, remember to bound the source when termination is needed.
2. **Do you need to combine two inputs into a result of a different type?** Use `BiFunction<T, U, R>`; for example, the accumulator of three-argument `reduce` typically takes an intermediate result of type `U` and an element of type `T`.
3. **Are you merging two results of the same type?** Use `BinaryOperator<T>` for `reduce`, the combiner of three-argument `reduce`, the combiner of `Collector.of`, or the merge function of `toMap`. Ensure associativity and identity rules if the API supports parallel reduction.

Having a function with the right type signature is **not enough** for a pipeline to be correct: the behavioral function must also satisfy the contract of the API being called. For parallel streams, pay particular attention to associativity, shared state, encounter order, and merging cost. For resource-backed streams such as `Files.lines`, close the stream with `try-with-resources`; returning results via `Supplier`, `BiFunction`, or `BinaryOperator` does not automatically manage resource lifecycles.

**Self-Check:** To compute the total length of strings, why does `reduce(0, (total, word) -> total + word.length(), Integer::sum)` need both `BiFunction<Integer, String, Integer>` and `BinaryOperator<Integer>`? To collect strings into a mutable list, why is `collect(ArrayList::new, ..., ...)` a more appropriate choice than `reduce` with an `ArrayList` as the identity? If you can answer these two questions, you can distinguish the roles of all three functional interfaces in most common pipelines.
