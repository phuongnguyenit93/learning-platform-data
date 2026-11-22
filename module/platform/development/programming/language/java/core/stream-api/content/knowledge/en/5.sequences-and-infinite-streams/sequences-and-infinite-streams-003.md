# Generating Sequences Using `Stream.iterate` with a State Transition Function

## 1. Lesson Objectives

In the **`JAVA_STREAM_API`** module, the Stream API is used to process data declaratively: create a source, chain transformations like `filter`, `map`, `reduce`, and then collect the result with `collect`. Not every data source is a pre-existing `List` or array. Some problems require **generating a sequence** according to a rule:

- Natural numbers: 0, 1, 2, 3, ...
- Powers of 2: 1, 2, 4, 8, 16, ...
- Consecutive days: today, tomorrow, the day after tomorrow, ...
- Fibonacci sequence: 0, 1, 1, 2, 3, 5, ...

`Stream.iterate` is a way to create a source for sequences where **the next element is computed from the current state**. This approach clearly expresses the state transition rule and can produce an infinite stream without pre-storing all elements in memory.

After this lesson, you will be able to:

1. Write `Stream.iterate(seed, next)` to generate a sequence using a state transition function.
2. Use `limit` or the `iterate(seed, hasNext, next)` form to control the stopping point.
3. Explain laziness, execution order, and the difference between sequence state and the output produced by `map`.
4. Generate sequences with composite state using immutable objects.
5. Identify cases prone to infinite execution, numeric overflow, or poor efficiency.

This lesson is in the **Sequences and Infinite Streams** chapter. The `iterate` pattern also helps build reasoning about state, function purity, and resource limits before learning advanced topics such as Spliterator, parallel streams, and Stream Gatherers.

## 2. From Recurrence Rules to `Stream.iterate`

A sequence is built from two elements:

- **Initial value** (`seed`): the first element.
- **State transition function** (`next`): receives the current state and computes the next state.

This can be described as:

```text
state[0] = seed
state[1] = next(state[0])
state[2] = next(state[1])
state[3] = next(state[2])
...
```

For example, with `seed = 1` and `next(n) = n * 2`, we get:

```text
1 --×2--> 2 --×2--> 4 --×2--> 8 --×2--> 16 --×2--> 32 ...
```

Java provides the two-argument form of `Stream.iterate` since **Java 8**:

```java
public static <T> Stream<T> iterate(T seed, UnaryOperator<T> f)
```

`UnaryOperator<T>` is a functional interface representing a transformation from **`T` to `T` itself**. The `next` function therefore preserves the state type, even as the value changes.

### Complete Example: The First Six Powers of 2

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class DayLuyThuaHai {
    public static void main(String[] args) {
        List<Integer> ketQua = Stream.iterate(1, n -> n * 2)
            .limit(6)
            .collect(Collectors.toList());

        System.out.println(ketQua);
    }
}
```

Output:

```text
[1, 2, 4, 8, 16, 32]
```

Reading each part:

| Expression | Meaning | Result type |
| --- | --- | --- |
| `Stream.iterate(1, n -> n * 2)` | Start at 1; double to generate the next number | `Stream<Integer>` |
| `.limit(6)` | Take at most the first six elements | `Stream<Integer>` |
| `.collect(Collectors.toList())` | Trigger the pipeline and put elements into a list | `List<Integer>` |

The two-argument form by itself generates a **sequence with no defined stopping point**. It is `limit(6)` that tells the program it only needs six elements; no infinite list is pre-allocated.

## 3. Distinguishing the State Transition Function from `map`

These two operations are easily confused because both accept a function:

- In `iterate(seed, next)`, `next` determines **the state used to generate the next element**.
- In `map(mapper)`, `mapper` **transforms the output value** of each element; normally it does not determine what the next source element will be.

Consider the pipeline:

```java
List<Integer> ketQua = Stream.iterate(1, n -> n + 1)
    .map(n -> n * n)
    .limit(5)
    .collect(Collectors.toList());

System.out.println(ketQua); // [1, 4, 9, 16, 25]
```

`iterate` generates the states 1, 2, 3, 4, 5, ...; `map` merely transforms each state into its square. **The next state is still computed by adding 1**. If you replace it with `Stream.iterate(1, n -> n * n)`, that is a different sequence: starting from 1 it stays 1 forever.

Another important point: `Stream.iterate` requires the state transition function to return the same type `T`; to convert results from numbers to strings, add `map`:

```java
List<String> nhan = Stream.iterate(1, n -> n + 1)
    .limit(3)
    .map(n -> "Step " + n)
    .collect(Collectors.toList());

System.out.println(nhan); // [Step 1, Step 2, Step 3]
```

## 4. Laziness and Stopping Points When Generating Infinite Sequences

The Stream API evaluates operations on demand. Calling `Stream.iterate(...)`, `map(...)`, `filter(...)`, or `limit(...)` only builds the pipeline. Elements are generated when a **terminal operation** such as `collect`, `forEach`, `count`, or `findFirst` needs to consume them.

Example:

```java
Stream<Integer> day = Stream.iterate(0, n -> n + 3)
    .limit(4);

// Up to here, computing the entire sequence has not been requested.
List<Integer> ketQua = day.collect(Collectors.toList());

System.out.println(ketQua); // [0, 3, 6, 9]
```

`limit` is a **short-circuiting** intermediate operation: on a potentially infinite source, it allows the terminal operation to finish once the requested number of elements has been received.

### Terminal Operations Have Different Behaviors

| Pipeline on a potentially infinite sequence | Does it terminate? | Explanation |
| --- | --- | --- |
| `iterate(...).limit(10).collect(toList())` | Yes | Only takes the first ten elements. |
| `iterate(...).findFirst()` | Yes | Takes the first element if the source has one. |
| `iterate(...).count()` | Not guaranteed | Counting all elements of an infinite stream will not complete. |
| `iterate(...).collect(toList())` | No | Collecting an entire infinite sequence is an impossible request to complete. |
| `iterate(...).sorted().limit(10).collect(toList())` | Not guaranteed | `sorted` typically has to examine the entire input before emitting elements. |
| `iterate(...).limit(10).sorted().collect(toList())` | Yes | Before sorting, the source has already been limited to ten elements. |

**Pay attention to operation order.** Placing `limit` before an operation that needs to see all data can turn an infinitely waiting pipeline into a finite one. However, `limit` is not an absolute guarantee either: if placed after a filter that **never yields enough elements**, the stream can still run forever.

### Should `filter` Be Placed Before or After `limit`?

```java
List<Integer> namSoChan = Stream.iterate(1, n -> n + 1)
    .filter(n -> n % 2 == 0)
    .limit(5)
    .collect(Collectors.toList());

// [2, 4, 6, 8, 10]
```

The pipeline needs to inspect more than five source states to receive five even numbers. If you swap the two steps:

```java
List<Integer> soChanTrongNamSoDau = Stream.iterate(1, n -> n + 1)
    .limit(5)
    .filter(n -> n % 2 == 0)
    .collect(Collectors.toList());

// [2, 4]
```

The business meaning has changed: **take the first five even numbers** versus **filter even numbers from the first five natural numbers**.

## 5. Three-Argument Form: Generating a Sequence Until a Condition Is False (Java 9+)

Since **Java 9**, `Stream.iterate` has an overload:

```java
public static <T> Stream<T> iterate(
    T seed,
    Predicate<? super T> hasNext,
    UnaryOperator<T> next
)
```

Parameters:

- `seed`: initial state.
- `hasNext`: checks whether **the state under consideration** should be emitted into the stream.
- `next`: creates the next state after an accepted state.

The model closely corresponds to a `for` loop:

```java
for (int n = 1; n <= 5; n = n + 1) {
    System.out.println(n);
}
```

Written with the Stream API:

```java
List<Integer> motDenNam = Stream.iterate(
        1,
        n -> n <= 5,
        n -> n + 1
    )
    .collect(Collectors.toList());

System.out.println(motDenNam); // [1, 2, 3, 4, 5]
```

Progression:

```text
seed = 1
hasNext(1) = true   → emit 1 → next(1) = 2
hasNext(2) = true   → emit 2 → next(2) = 3
hasNext(3) = true   → emit 3 → next(3) = 4
hasNext(4) = true   → emit 4 → next(4) = 5
hasNext(5) = true   → emit 5 → next(5) = 6
hasNext(6) = false  → stop; do not emit 6
```

**The first element must also pass `hasNext`.** If `hasNext(seed)` is `false`, the stream is empty:

```java
long soLuong = Stream.iterate(10, n -> n < 10, n -> n + 1)
    .count();

System.out.println(soLuong); // 0
```

The three-argument form can create a **finite or infinite** sequence depending on the condition, for example `n -> true` creates no stopping point. The two overloads differ in how they express the termination condition, without changing the Stream's lazy evaluation rules.

### `limit` or `hasNext`?

| Requirement | Choice | Example |
| --- | --- | --- |
| Take exactly the first N states | Two-argument form + `limit(N)` | Take the first 10 Fibonacci numbers |
| Stop when **state** reaches a threshold | Three-argument form (Java 9+) | Generate 1, 2, 4, 8, 16, 32 with condition `n <= 32` |
| Stop based on **values passing through the pipeline** | Can use `takeWhile` (Java 9+) on an ordered stream | Generate increasing numbers and take while `n < 100` |
| Generate consecutive integer indices in a range | Consider `IntStream.range` / `rangeClosed` | Index sequence 0 to 9 |

Example of powers of 2 terminating at a threshold:

```java
List<Integer> day = Stream.iterate(
        1,
        n -> n <= 32,
        n -> n * 2
    )
    .collect(Collectors.toList());

System.out.println(day); // [1, 2, 4, 8, 16, 32]
```

Equivalent `takeWhile` example for an increasing number sequence:

```java
List<Integer> nhoHonNam = Stream.iterate(1, n -> n + 1)
    .takeWhile(n -> n < 5)
    .collect(Collectors.toList());

// [1, 2, 3, 4] — Java 9+
```

For an **ordered** stream like one generated by `iterate`, `takeWhile` takes the contiguous leading prefix that still satisfies the condition and then stops; it is not equivalent to `filter` when subsequent values might satisfy the condition again.

## 6. Practical Example: Generating a Date Sequence with `LocalDate`

Dates are a natural form of state: knowing today, you compute the next day with `plusDays(1)`. This is convenient for study schedules, work calendars, or generating timestamps.

```java
import java.time.LocalDate;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class LichTuan {
    public static void main(String[] args) {
        LocalDate batDau = LocalDate.of(2026, 11, 16);

        List<LocalDate> bayNgay = Stream.iterate(
                batDau,
                ngay -> ngay.plusDays(1)
            )
            .limit(7)
            .collect(Collectors.toList());

        System.out.println(bayNgay);
    }
}
```

Output:

```text
[2026-11-16, 2026-11-17, 2026-11-18, 2026-11-19,
 2026-11-20, 2026-11-21, 2026-11-22]
```

Since Java 9, if the end date is determined by business data, you can use the three-argument form:

```java
LocalDate batDau = LocalDate.of(2026, 11, 16);
LocalDate ketThuc = LocalDate.of(2026, 11, 20);

List<LocalDate> cacNgay = Stream.iterate(
        batDau,
        ngay -> !ngay.isAfter(ketThuc),
        ngay -> ngay.plusDays(1)
    )
    .collect(Collectors.toList());

// [2026-11-16, 2026-11-17, 2026-11-18, 2026-11-19, 2026-11-20]
```

The condition `!ngay.isAfter(ketThuc)` allows keeping **the end date inclusive**. If you use `ngay.isBefore(ketThuc)`, the end date will be excluded.

### Generating the First Three Workdays Starting from a Friday

```java
import java.time.DayOfWeek;

LocalDate batDau = LocalDate.of(2026, 11, 20); // Friday

List<LocalDate> ngayLamViec = Stream.iterate(
        batDau, ngay -> ngay.plusDays(1))
    .filter(ngay -> ngay.getDayOfWeek() != DayOfWeek.SATURDAY)
    .filter(ngay -> ngay.getDayOfWeek() != DayOfWeek.SUNDAY)
    .limit(3)
    .collect(Collectors.toList());

System.out.println(ngayLamViec);
// [2026-11-20, 2026-11-23, 2026-11-24]
```

Here, `filter` skips Saturday and Sunday; `limit(3)` only counts **three days that passed the filter**. This simple example does not account for public or company holidays.

## 7. Composite State: Fibonacci Sequence with an Immutable Object

Some sequences cannot compute the next element from just **one current value**. Fibonacci needs to remember the **two most recent values**:

```text
F(0) = 0
F(1) = 1
F(n + 2) = F(n + 1) + F(n)
```

The appropriate solution is to treat the state at each step as a pair `(a, b)`:

```text
(a, b) = (0, 1)
    ↓ (a, b) → (b, a+b)
(1, 1)
    ↓
(1, 2)
    ↓
(2, 3)
    ↓
(3, 5)
...
```

To avoid `int` or `long` overflow when generating many Fibonacci numbers, the example uses `BigInteger`. The state class has only `final` fields, and the transition creates a new object:

```java
import java.math.BigInteger;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FibonacciBangIterate {
    private static final class TrangThai {
        final BigInteger a;
        final BigInteger b;

        TrangThai(BigInteger a, BigInteger b) {
            this.a = a;
            this.b = b;
        }

        TrangThai tiepTheo() {
            return new TrangThai(b, a.add(b));
        }
    }

    public static void main(String[] args) {
        TrangThai batDau = new TrangThai(
            BigInteger.ZERO, BigInteger.ONE);

        List<BigInteger> fibonacci = Stream
            .iterate(batDau, TrangThai::tiepTheo)
            .map(trangThai -> trangThai.a)
            .limit(10)
            .collect(Collectors.toList());

        System.out.println(fibonacci);
        // [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
    }
}
```

Here:

- The source type is `Stream<TrangThai>`.
- `tiepTheo()` takes the current state and creates a **new state** of the same type.
- `map(trangThai -> trangThai.a)` selects only the value to emit, producing `Stream<BigInteger>`.
- `limit(10)` forces generation to end after the first ten values.

Using **immutable state** keeps the state transition transparent, easy to test, and free from dependence on variables outside the pipeline. Avoid using a mutated-in-place array or counter variables outside the lambda to "remember" the previous two numbers when you can represent state with a new value.

If building the application with Java 16+, you can replace the two-field class with a `record`; however, the code above still runs on Java 8.

## 8. Choosing `Stream<Integer>` or `IntStream`?

For integer sequences, Java has the primitive variant `IntStream.iterate`. It avoids boxing from `int` to `Integer` for each element, which is useful for arithmetic computations.

Java 8 example:

```java
import java.util.stream.IntStream;

int tong = IntStream.iterate(2, n -> n + 2)
    .limit(5)
    .sum();

System.out.println(tong); // 2 + 4 + 6 + 8 + 10 = 30
```

In Java 9+, `IntStream` also has the three-argument form:

```java
int[] day = IntStream.iterate(
        1,
        n -> n <= 16,
        n -> n * 2)
    .toArray();

// [1, 2, 4, 8, 16]
```

Quick comparison:

| Stream type | Value form | Characteristics |
| --- | --- | --- |
| `Stream<Integer>` | `Integer` objects | Suitable when generics, `collect(Collectors.toList())`, or object types are needed. |
| `IntStream` | Primitive `int` | Provides `sum()`, `average()`, `max()`, and `toArray()`. |
| `LongStream` | Primitive `long` | Useful when `int` range is insufficient, though overflow risk still applies. |
| `DoubleStream` | Primitive `double` | Used for floating-point data; watch out for floating-point precision errors. |

If you need to convert `IntStream` to `Stream<Integer>`, use `boxed()`. If you only need consecutive integers from A to B, `IntStream.range(A, B)` or `rangeClosed(A, B)` is usually more direct than writing `n -> n + 1`.

## 9. Practical Pitfalls When Generating Sequences

### 9.1. Forgetting a Stopping Point

The following snippet **can run forever and increase memory usage** because it tries to collect an entire sequence with no endpoint:

```java
// DO NOT RUN: no limit or termination condition.
List<Integer> voHan = Stream.iterate(0, n -> n + 1)
    .collect(Collectors.toList());
```

Limit the data before collecting into memory:

```java
List<Integer> motTramSo = Stream.iterate(0, n -> n + 1)
    .limit(100)
    .collect(Collectors.toList());
```

In real applications, choose a reasonable limit based on requirements and resources; do not create huge lists just because elements can be generated lazily.

### 9.2. A Filter That Never Yields Enough Results

`limit(k)` counts elements **passing through preceding steps**, not the number of states generated by the source. The following example can never obtain any element:

```java
// DO NOT RUN: filter is always false, limit(1) never gets enough elements.
Stream.iterate(0, n -> n + 1)
    .filter(n -> false)
    .limit(1)
    .count();
```

Similarly, `distinct().limit(3)` does not terminate if the source only has two distinct values repeating infinitely. When you cannot guarantee enough matching results, **limit the source before the filtering step** or design a source with a real stopping condition.

### 9.3. Integer Overflow

The `int` and `long` types have limits. For example, `Stream.iterate(1, n -> n * 2)` can overflow `int` if enough elements are taken; Java does not automatically promote to `BigInteger`.

Options:

- Reduce the element count with `limit` when the safe value range is known.
- Choose `long` if it suffices for the value range.
- Use `BigInteger` for large sequences, e.g., `Stream.iterate(BigInteger.ONE, n -> n.multiply(BigInteger.TWO))` on Java 9+ (`BigInteger.TWO` was introduced in Java 9); on Java 8, `BigInteger.valueOf(2)` can be used.

Limiting the number of elements and limiting **numeric values** are two separate concerns. When overflow detection is needed, consider `Math.addExact` or `Math.multiplyExact` to throw an exception if an arithmetic operation exceeds primitive bounds.

### 9.4. Side Effects in the `next` Function

The state transition function should depend on its input and not on external variables:

```java
// RECOMMENDED: the same n always yields the same n + 1.
Stream<Integer> nen = Stream.iterate(0, n -> n + 1);
```

Avoid using shared counters or shared lists to compute the next element. Most intermediate operations require **non-interfering** and **stateless** behavior; mutating source data or external state inside lambdas can cause logic bugs, especially when switching to a parallel stream.

Also remember that a `Stream` **can only be consumed once**. After `collect` or `count`, create a new stream if you want to recompute the sequence.

### 9.5. Parallel Is Not Automatically Faster

`Stream.iterate` creates an ordered source where each state depends on the previous state. This is inherently a **sequentially dependent** problem. Calling `parallel()` does not remove that dependency; splitting work, coordinating, and preserving order can make it slower.

For processing short sequences or cheap state transition rules, keeping the pipeline sequential is an easy-to-understand choice. Only consider parallel processing when you measure a real benefit and the functions in the pipeline are safe for concurrent execution.

## 10. Comparing `iterate` with Other Stream Creation Approaches

| Method | Idea | When to use |
| --- | --- | --- |
| `Stream.iterate(seed, next)` | Each state produces the next state; no default stopping point | Recurrence sequences, taking the first N values with `limit` |
| `Stream.iterate(seed, hasNext, next)` (Java 9+) | Recurrence sequence with a state-checking condition | Generating up to a threshold or end date |
| `Stream.generate(supplier)` | Each element comes from a `Supplier`; does not receive previous state | Generating independent data via a supplier |
| `IntStream.range(start, end)` | Consecutive integers, excluding `end` | Iterating over an index range |
| `IntStream.rangeClosed(start, end)` | Consecutive integers, including `end` | Taking a closed integer interval |
| `collection.stream()` | Iterates over existing elements in a collection | Processing already-stored data |

Example:

```java
import java.util.stream.IntStream;

// Consecutive integers 0, 1, 2, 3, 4.
int[] chiSo = IntStream.range(0, 5).toArray();

// Recurrence values 1, 3, 9, 27, 81.
List<Integer> luyThuaBa = Stream.iterate(1, n -> n * 3)
    .limit(5)
    .collect(Collectors.toList());
```

If generation depends on the **previous state**, `iterate` expresses the intent clearly. If you only need consecutive indices, the `range` API is easier to read.

## 11. Practice Exercises

### Exercise 1 — Arithmetic Progression

Use the two-argument `Stream.iterate` and `limit` to generate **six** numbers starting from 5, adding 3 each time. Predict the result before running.

### Exercise 2 — Conditionally Finite Sequence

Use the three-argument overload (Java 9+) to generate numbers starting from 2, multiplying by 3 each time, **keeping only numbers not exceeding 200**. When is the condition checked? Is the first element emitted if `seed > 200`?

### Exercise 3 — Swapping Processing Order

Given two pipelines:

```java
List<Integer> a = Stream.iterate(1, n -> n + 1)
    .filter(n -> n % 3 == 0)
    .limit(4)
    .collect(Collectors.toList());

List<Integer> b = Stream.iterate(1, n -> n + 1)
    .limit(4)
    .filter(n -> n % 3 == 0)
    .collect(Collectors.toList());
```

Explain why `a` and `b` differ.

### Exercise 4 — Choosing a State Type

To generate the first 100 Fibonacci numbers without numeric overflow, would you choose `int`, `long`, or `BigInteger`? Why do you need to keep the pair of most recent values as state instead of just a single Fibonacci number?

### Reference Solutions

**Exercise 1:**

```java
List<Integer> ketQua = Stream.iterate(5, n -> n + 3)
    .limit(6)
    .collect(Collectors.toList());

// [5, 8, 11, 14, 17, 20]
```

**Exercise 2:**

```java
List<Integer> ketQua = Stream.iterate(
        2,
        n -> n <= 200,
        n -> n * 3
    )
    .collect(Collectors.toList());

// [2, 6, 18, 54, 162]
```

`hasNext` checks **the current state**, including `seed`, before emitting that element. After 162, the transition produces 486; checking 486 fails so 486 is not emitted. If `seed > 200`, the result is empty.

**Exercise 3:** `a = [3, 6, 9, 12]` because filtering happens first and then it limits to four matching elements. `b = [3]` because only the four numbers 1, 2, 3, 4 are examined before filtering multiples of 3.

**Exercise 4:** `BigInteger` is appropriate if exact values up to the 100th element are needed, because both `int` and `long` overflow before then. The state transition function needs both values of the pair `(a, b)` to create `(b, a + b)`. An immutable state class can be used as in the Fibonacci example in section 7.

## 12. Key Takeaways

`Stream.iterate` creates a data source using a **state transition function**:

```java
// Java 8+: source can generate infinitely; limit the number of elements when needed.
Stream.iterate(seed, current -> next(current))
    .limit(soPhanTu);

// Java 9+: check current before emitting it into the stream.
Stream.iterate(seed,
    current -> conDuocPhep(current),
    current -> next(current));
```

Clearly define the **initial state**, **next-state transition rule**, **stopping condition**, and **appropriate data type**. Combine `iterate` with `filter`, `map`, `reduce`, and `collect` only once you understand how many elements are requested and how operation ordering affects the result. That is the foundation for generating and processing long sequences safely, testably, and extensibly.
