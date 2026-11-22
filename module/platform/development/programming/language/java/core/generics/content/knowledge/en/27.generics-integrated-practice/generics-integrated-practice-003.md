# Designing a Copy Function Properly with PECS in Java Generics

A very common operation when designing Java APIs is **reading elements from a source and writing them into a destination**. If you only declare `List<T>` on both sides, the API can become overly restrictive: you want to read `Integer`s from a `List<Integer>` and write them into a `List<Number>`, but **Java Generics are invariant**, so `List<Integer>` is not a subtype of `List<Number>`.

The right solution is choosing wildcards according to **the role of each parameter**:

> **PECS = Producer Extends, Consumer Super.** The side that *produces* elements for us to read uses `? extends T`; the side that *consumes* elements we want to write uses `? super T`.

A typical signature:

```java
static <T> int appendAll(
        Iterable<? extends T> source,
        Collection<? super T> destination)
```

This states that **the source supplies elements readable as `T`** and **the destination accepts `T` elements**. The method can work with `List<Integer>` → `List<Number>`, `List<Integer>` → `List<Object>`, without needing raw types or unchecked casts.

However, the word "copy" can refer to **two different contracts**:

- **Append:** iterate the source and add elements to the destination, typically using `Collection.add`. The destination may grow in size or, with a `Set`, stay the same size if an element is already present.
- **Overwrite/replace:** overwrite existing slots in a `List`, typically using `List.set`. The destination must already have enough slots; the operation does not add new slots.

This lab builds both variants, illustrates a temporary snapshot to handle overlapping data regions, and explains runtime constraints such as `null`, mutation, aliasing, partial failure, and concurrent modification.

## 1. Objectives and Background

After this lesson, you will be able to:

1. Explain why `List<Integer>` is not assignable to `List<Number>`, even though `Integer extends Number`.
2. Choose **`Iterable<? extends T>` for the source** and **`Collection<? super T>` for the destination** in a read-from-source, write-to-destination operation.
3. Build a cast-free `appendAll` method with a well-defined processed-element count.
4. Build an `overwritePrefix` method using `List.set`, checking destination size and snapshotting the source to avoid bugs when list views overlap.
5. Distinguish `Collections.copy` from `Collection.addAll`/custom append methods.
6. Know when to use `List<T>`, `List<?>`, `? extends T`, `? super T`, or a method's own `<T>`.
7. Extend to copying **with type transformation** using `Function<? super S,? extends R>`.
8. Write Javadoc, tests, and document guarantees that a generic signature **does not automatically provide**: mutability, null policy, atomicity, aliasing, ordering, and multithreading.

This lab uses Java 17 or later, with no external libraries outside the JDK.

## 2. Why `List<T>` on Both Sides Is Not Flexible Enough

Consider an initial attempt:

```java
static <T> void copyTooNarrow(
        List<T> source,
        List<T> destination) {
    for (T value : source) {
        destination.add(value);
    }
}
```

The method works when both arguments have type arguments compatible with the same `T`, but calling it with `List<Integer>` and `List<Number>` **is not naturally expressed by `copyTooNarrow`** when inferring directly against invariant `List<T>`.

```java
List<Integer> ints = List.of(1, 2, 3);
List<Number> numbers = new ArrayList<>();

// copyTooNarrow(ints, numbers); // Cannot infer a compatible common T
```

`List<Integer>` is not a `List<Number>`. If that assignment were allowed, code using the `List<Number>` reference could add a `Double` into a list viewed elsewhere as `List<Integer>`:

```java
// Hypothetical snippet INVALID in Java:
// List<Number> aliases = ints;
// aliases.add(3.14); // Breaks the List<Integer> contract
```

**The solution is not `(List<Number>)(List<?>)ints`.** An unchecked cast destroys the safety the compiler is trying to protect. Let the method state explicitly that it **only reads** from the source and **only writes** to the destination by placing wildcards in the right positions.

## 3. Reading PECS from Producer and Consumer Perspectives

Let `T = Integer`:

```java
List<Integer> integers = List.of(2, 4, 6);

List<? extends Number> producer = integers;
Number first = producer.get(0); // Readable as Number.

// producer.add(8); // Does not compile for a regular non-null Integer.

List<? super Integer> consumer = new ArrayList<Number>();
consumer.add(9); // Writing Integer is valid.
Object item = consumer.get(0); // Safely readable at least as Object.
```

The two wildcards have distinct meanings:

| Reference type | What is it used for? | Read | Write |
| --- | --- | --- | --- |
| `List<T>` | Element type `T` is known at the reference | `T` | `T` |
| `List<? extends T>` | **Producer** of values readable as `T` | `T` | Cannot add an arbitrary non-null `T` value |
| `List<? super T>` | **Consumer** that can accept `T` | `Object` if no more specific target type is known | `T` |
| `List<?>` | Element type need not be known | `Object` | Cannot add an arbitrary non-null value |

Technical note: some operations like adding `null` may be accepted by the compiler through a wildcard, but **that is not a reason to choose a source type** and still depends on the collection's null policy. When learning PECS, understand it as "cannot add an arbitrary `T` element through `? extends T`," avoiding absolute claims that every `add` call is forbidden.

**Wildcards do not dictate runtime mutability.** A `List<? super Integer>` reference can still point to a list that does not support `add`, and a well-typed call may throw `UnsupportedOperationException`.

## 4. Core Signature of the Append Operation

Design:

```java
static <T> int appendAll(
        Iterable<? extends T> source,
        Collection<? super T> destination) {
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(destination, "destination");

    int processed = 0;
    for (T value : source) {
        destination.add(value);
        processed++;
    }
    return processed;
}
```

Part-by-part explanation:

- `<T>` is the **method's type parameter**, linking the element type read from source with the element type accepted by destination.
- `Iterable<? extends T>` says the source can be a `List<Integer>`, `Set<Integer>`, or another iterable producing values compatible with `T`. We only need iteration, so we do not require the source to be a `List`.
- `Collection<? super T>` says the destination can accept `T` elements. It does not force destination to be strictly `List<T>`.
- `for (T value : source)` reads safely: each source element is a compatible subtype of `T`.
- `destination.add(value)` writes safely: destination accepts `T` or a matching supertype.
- `processed` **increments after each `add` returns normally** without throwing an exception. It is not the count of genuinely new elements added for every kind of `Collection`.

Example:

```java
List<Integer> integers = List.of(2, 4, 6);
List<Number> numbers = new ArrayList<>(List.of(0.5));

int count = appendAll(integers, numbers);
System.out.println(count);   // 3
System.out.println(numbers); // [0.5, 2, 4, 6]
```

The compiler verifies the `Integer <: Number` relationship through the wildcards without needing raw types.

### Why choose `Iterable` and `Collection` instead of two `List`s?

This method **only reads sequentially**, needing neither `get(i)` nor `set(i)` on the source. The destination only needs to support `add`, not indexed access. Hence using `Iterable` for source and `Collection` for destination removes unnecessary API constraints.

If business rules only permit copying from `List` to `List` due to ordering, size, or random access needs, a narrower signature may be justified. Choose abstractions **based on actual operations**, not out of a habit of writing `List<T>` everywhere.

## 5. Which Type Pairs Does `appendAll` Accept?

Look at these calls:

```java
List<Integer> ints = List.of(1, 2);
Collection<Number> numbers = new ArrayList<>();
Collection<Object> objects = new ArrayList<>();

appendAll(ints, numbers); // Valid: Number can consume Integer.
appendAll(ints, objects); // Valid: Object can consume Integer.
```

A container of a subtype can also serve as the source when the result is allowed by the destination. Example:

```java
List<Double> doubles = List.of(2.5, 4.5);
Collection<Number> numbers = new ArrayList<>();
appendAll(doubles, numbers); // Valid.
```

Conversely:

```java
List<Number> source = List.of(1, 2.5);
List<Integer> target = new ArrayList<>();

// appendAll(source, target); // Does not compile: destination cannot accept every Number.
```

If that last call were permitted, a `Double` element from source could be written into `List<Integer>`, violating the destination's typed contract.

**Do not fix this with an unchecked cast.** This case indicates incompatible data or copy direction design; convert the data with validation/transformation (for example, rounding according to domain policy) or pick a wider destination type.

## 6. `Collection.add` Might Not Add a New Element

In `Collection<E>`, `add(E)` returns a `boolean` indicating whether the collection **changed as a result of the call** per the method's contract. For a mutable `List`, adding an element normally increases size; for a `Set`, an already-present element causes `add` to return `false`.

Example:

```java
List<Integer> source = List.of(2, 4, 6);
Set<Number> unique = new LinkedHashSet<>(List.of(2, 4));

int processed = appendAll(source, unique);

System.out.println(processed); // 3
System.out.println(unique);    // [2, 4, 6]
```

Even though only element 6 creates a new entry, `processed == 3` because the method **successfully processed three `add` calls**, including calls where `add` returned `false`.

If the contract wants to return **the number of `add` calls that actually modified the collection**, write a separate method or a clearer name:

```java
static <T> int countAccepted(
        Iterable<? extends T> source,
        Collection<? super T> destination) {
    int accepted = 0;
    for (T value : source) {
        if (destination.add(value)) {
            accepted++;
        }
    }
    return accepted;
}
```

The two counts return different values on a `Set` with duplicate elements. Do not write Javadoc saying "number of inserted elements" for an `appendAll` method that actually counts **processed elements**.

## 7. Append vs. Overwrite: A `List` Destination with Pre-Existing Slots

Some "copy" problems do not want to **append**, but rather **overwrite** existing positions. The Java library provides:

```java
Collections.copy(destination, source);
```

Its generic signature has the form:

```java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

`src` is the producer; `dest` is the consumer. That is PECS. However, **its runtime contract differs from `appendAll`**:

- `Collections.copy` replaces the leading positions of `dest` with elements from `src`.
- `dest` must already have **at least** `src.size()` existing elements.
- `dest` must support `set` at the written indices; an unmodifiable `List.of` will not work.
- If `dest` is longer than source, remaining elements are preserved.
- If `dest` is too short, `IndexOutOfBoundsException` may be thrown.
- Certain overlapping/live views can cause direct copying to yield unexpected results; consider alias semantics.

Example:

```java
List<Integer> src = List.of(2, 4, 6);
List<Number> dest = new ArrayList<>(List.of(-1, -1, -1, -1));

Collections.copy(dest, src);
System.out.println(dest); // [2, 4, 6, -1]
```

Distinguish this from:

```java
dest.addAll(src); // Appends three elements at the end; does not replace the first three slots.
```

**Do not call `new ArrayList<>(capacity)` and immediately call `Collections.copy`.** Capacity is only internal allocation space; the new list has `size()==0`. You must populate enough **existing elements** or use append instead of overwrite.

## 8. Building `overwritePrefix`: Checking Length and Snapshotting the Source

Writing a safer variant when **source/destination are two overlapping subList views**:

```java
static <T> int overwritePrefix(
        List<? super T> destination,
        List<? extends T> source) {
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(destination, "destination");

    // Copy source before mutating destination, avoiding overwriting data
    // still needed for reading when two list views share backing storage.
    List<T> snapshot = new ArrayList<>(source);

    if (destination.size() < snapshot.size()) {
        throw new IndexOutOfBoundsException(
                "destination too short: "
                + destination.size() + " < " + snapshot.size());
    }

    for (int i = 0; i < snapshot.size(); i++) {
        destination.set(i, snapshot.get(i));
    }

    return snapshot.size();
}
```

**Two notable design choices:**

1. **Snapshot the source before writing** so that if source and destination share a backing list, writing to destination does not mutate elements still waiting to be read from source during copying.
2. **Check slot count before starting to write** so a too-short destination is rejected without any `set` calls having been performed by this loop.

Example:

```java
List<Integer> source = List.of(2, 4, 6);
List<Number> slots = new ArrayList<>(List.of(-1, -1, -1, -1));

int n = overwritePrefix(slots, source);
System.out.println(n);     // 3
System.out.println(slots); // [2, 4, 6, -1]
```

**Not an atomic transaction:** if destination does not support `set`, a `set` rejects a value, or concurrent side effects occur from another caller, some positions may already have been written before an error occurs. Checking size up front only guarantees **no failure due to insufficient initial length** in the absence of concurrent modifications.

### Destination smaller than source

```java
List<Number> tooSmall = new ArrayList<>(List.of(-1, -1));

try {
    overwritePrefix(tooSmall, List.of(2, 4, 6));
} catch (IndexOutOfBoundsException expected) {
    System.out.println("Destination too short");
}

System.out.println(tooSmall); // [-1, -1]
```

The method takes a snapshot and compares lengths **before any `set` call**, so in this single-threaded example the destination remains untouched. `Collections.copy` also requires sufficient length, though it does not carry the same snapshot/aliasing guarantees as this custom variant.

## 9. Common Mistakes When Using `Collections.copy`

A snippet that looks reasonable but is wrong:

```java
List<Integer> source = List.of(1, 2, 3);
List<Number> destination = new ArrayList<>(source.size());

// NOT supported because destination currently still has size = 0:
// Collections.copy(destination, source);
```

The `ArrayList<>(initialCapacity)` constructor only sets **capacity**, not elements. Two options:

```java
// If you want to append:
destination.addAll(source);
```

or:

```java
// If you want to overwrite existing slots:
List<Number> destination = new ArrayList<>(
        Arrays.asList(0, 0, 0));
Collections.copy(destination, source);
```

Another issue: `List.of` does not support `set`; `Arrays.asList` has **fixed size but allows `set`**. Thus:

```java
List<Number> fixed = Arrays.<Number>asList(-1, -1, -1);
Collections.copy(fixed, source); // Valid when elements/size match.
```

Whereas:

```java
List<Number> unmodifiable = List.of(-1, -1, -1);
// Collections.copy(unmodifiable, source); // May throw UnsupportedOperationException.
```

The commented-out line is not a compile error: the call is well-typed, but the implementation rejects mutation **at runtime**.

## 10. Self-Copy and Overlapping `subList` Regions

A subtle bug in copying algorithms occurs when **source and destination reference the same underlying data structure**.

### 10.1. Appending a list to itself

```java
List<Integer> list = new ArrayList<>(List.of(1, 2, 3));

// Do not assume iterating source while adding to the
// same collection is safe:
// appendAll(list, list);
```

In a standard `ArrayList`, the `for-each` loop uses an iterator. Structurally modifying the list via `add` during iteration can cause `ConcurrentModificationException`. With certain other iterables or concurrent collections, iteration behavior and outcomes may differ; do not assume "every self-copy will always throw a specific exception."

A deliberate way is to **snapshot before appending**:

```java
static <T> int appendSnapshot(
        Iterable<? extends T> source,
        Collection<? super T> destination) {
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(destination, "destination");

    List<T> snapshot = new ArrayList<>();
    for (T value : source) {
        snapshot.add(value);
    }

    for (T value : snapshot) {
        destination.add(value);
    }
    return snapshot.size();
}
```

With:

```java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3));
appendSnapshot(values, values);

System.out.println(values); // [1, 2, 3, 1, 2, 3]
```

The source finishes iterating **before** destination is mutated, making this self-append predictable in single-threaded cases. Snapshotting takes **O(n)** memory proportional to source size, and does not itself guarantee a consistent snapshot if another thread mutates source while the snapshot is being built.

### 10.2. Two `subList` views sharing a backing list

```java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4));

List<Integer> source = values.subList(0, 3);
List<Integer> target = values.subList(1, 4);

overwritePrefix(target, source);

System.out.println(values); // [1, 1, 2, 3]
```

If an algorithm interleaved reads and writes directly on the two views, writing to target could alter elements the loop was about to read from source; with overlapping views, that is an unaccounted dependency. In `overwritePrefix`, `snapshot` holds `[1,2,3]` before any writes happen, so what gets copied is unambiguous.

**Do not claim this is a thread-safe/atomic snapshot.** In multi-threaded code, building the snapshot and performing `set` calls still require synchronization if a consistent view must be observed.

## 11. Comparing the Copying Strategies

| Strategy | Source | Destination | Main operation | Conditions and trade-offs |
| --- | --- | --- | --- | --- |
| `appendAll` | `Iterable<? extends T>` | `Collection<? super T>` | `add` in a loop | Can change size; not inherently safe for self-append |
| `appendSnapshot` | `Iterable<? extends T>` | `Collection<? super T>` | Snapshot then `add` | Extra O(n) memory; more predictable self-copy |
| `overwritePrefix` | `List<? extends T>` | `List<? super T>` | Snapshot then `set` | Requires `dest.size >= src.size`, supports `set`; avoids overlapping read–write bugs |
| `Collections.copy` | `List<? extends T>` | `List<? super T>` | Replace existing elements | Built into JDK; needs enough slots, check contract on views/mutation |
| `destination.addAll(source)` | `Collection<? extends E>` | `Collection<E>` | Bulk add per collection API | Convenient when compatible collection exists; own contracts for self-add and failures |

**Complexity** depends on the implementation. For ArrayList, sequential appending typically takes O(n) total amortized time; snapshotting also takes O(n) memory; for LinkedList or custom Collections, costs may differ. There is no guarantee that `Collection.add`, `List.get`, or `List.set` are all O(1) across every implementation.

If you need to **append** and the source is a `Collection<? extends T>`, `destination.addAll(source)` is usually sufficient. If the API needs to accept any `Iterable`, count processed elements, control validation/exceptions, or snapshot before mutation, custom helpers earn their keep.

## 12. Extended Generic Method: Copy with Type Transformation `S -> R`

PECS also applies when input and output values **do not share the same type**.

```java
static <S,R> int mapAppend(
        Iterable<? extends S> source,
        Collection<? super R> destination,
        Function<? super S, ? extends R> mapper) {
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(destination, "destination");
    Objects.requireNonNull(mapper, "mapper");

    int processed = 0;
    for (S value : source) {
        destination.add(mapper.apply(value));
        processed++;
    }
    return processed;
}
```

Here:

- `S` is the **source element type**, `R` is the **result element type**.
- `Iterable<? extends S>` produces values readable as `S`.
- `Function<? super S, ? extends R>` **consumes `S`** and **produces `R`**.
- `Collection<? super R>` consumes `R` results.

Example:

```java
List<Integer> ints = List.of(2, 4, 6);
List<Number> halves = new ArrayList<>();

mapAppend(ints, halves, n -> n / 2.0);

System.out.println(halves); // [1.0, 2.0, 3.0]
```

Because the mapper returns `Double`, destination type `Number` is wide enough to receive the results. No unchecked cast from `Integer` to `Double` is needed; the division happens through an ordinary numeric expression.

**Contract note:** if `mapper` throws an exception or `destination` rejects `add`, earlier elements may already have been written. If `mapper` returns null, whether null can be written depends on the destination; the API may explicitly forbid it with `requireNonNull` if business rules demand it.

## 13. Complete Java 17+ Demo

Save as **`PecsCopyDemo.java`**. The program includes all four helpers and multiple scenarios verifying PECS, append, overwrite, overlap, size, Set, and unmodifiable destinations.

```java
import java.util.*;
import java.util.function.Function;

public class PecsCopyDemo {
    static <T> int appendAll(
            Iterable<? extends T> source,
            Collection<? super T> destination) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");

        int processed = 0;
        for (T value : source) {
            destination.add(value);
            processed++;
        }
        return processed;
    }

    static <T> int appendSnapshot(
            Iterable<? extends T> source,
            Collection<? super T> destination) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");

        List<T> snapshot = new ArrayList<>();
        for (T value : source) {
            snapshot.add(value);
        }
        for (T value : snapshot) {
            destination.add(value);
        }
        return snapshot.size();
    }

    static <T> int overwritePrefix(
            List<? super T> destination,
            List<? extends T> source) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");

        List<T> snapshot = new ArrayList<>(source);
        if (destination.size() < snapshot.size()) {
            throw new IndexOutOfBoundsException(
                    "destination too short: " + destination.size()
                    + " < " + snapshot.size());
        }

        for (int i = 0; i < snapshot.size(); i++) {
            destination.set(i, snapshot.get(i));
        }
        return snapshot.size();
    }

    static <S,R> int mapAppend(
            Iterable<? extends S> source,
            Collection<? super R> destination,
            Function<? super S, ? extends R> mapper) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");
        Objects.requireNonNull(mapper, "mapper");

        int processed = 0;
        for (S value : source) {
            destination.add(mapper.apply(value));
            processed++;
        }
        return processed;
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(2, 4, 6);
        List<Number> numbers =
                new ArrayList<>(List.of(0.5));

        System.out.println("Append count: "
                + appendAll(integers, numbers));
        System.out.println("Numbers: " + numbers);

        List<Object> objects = new ArrayList<>();
        appendAll(integers, objects);
        System.out.println("Objects: " + objects);

        List<Number> slots =
                new ArrayList<>(List.of(-1, -1, -1, -1));
        System.out.println("Replaced count: "
                + overwritePrefix(slots, integers));
        System.out.println("Slots: " + slots);

        List<Number> tooSmall =
                new ArrayList<>(List.of(-1, -1));
        try {
            overwritePrefix(tooSmall, integers);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println(
                    "Too small: IndexOutOfBoundsException");
        }
        System.out.println(
                "Too small unchanged: " + tooSmall);

        List<Integer> same =
                new ArrayList<>(List.of(1, 2, 3));
        System.out.println("Self-copy count: "
                + appendSnapshot(same, same));
        System.out.println("Self-copy: " + same);

        List<Integer> overlap =
                new ArrayList<>(List.of(1, 2, 3, 4));
        overwritePrefix(
                overlap.subList(1, 4),
                overlap.subList(0, 3));
        System.out.println("Overlapping views: " + overlap);

        List<Number> mapped = new ArrayList<>();
        System.out.println("Mapped count: "
                + mapAppend(integers, mapped, n -> n / 2.0));
        System.out.println("Mapped: " + mapped);

        Set<Number> unique =
                new LinkedHashSet<>(List.of(2, 4));
        System.out.println("Set processed: "
                + appendAll(integers, unique));
        System.out.println("Set values: " + unique);

        List<Number> immutable = List.of(0);
        try {
            appendAll(integers, immutable);
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                    "Immutable destination: "
                    + "UnsupportedOperationException");
        }

        List<? extends Number> producer = integers;
        System.out.println(
                "Producer read: " + producer.get(0));

        List<? super Integer> consumer =
                new ArrayList<Number>();
        consumer.add(9);
        System.out.println("Consumer read type: "
                + consumer.get(0).getClass().getSimpleName());

        List<Number> standard =
                new ArrayList<>(List.of(-1, -1, -1));
        Collections.copy(standard, integers);
        System.out.println(
                "Collections.copy: " + standard);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 -Xlint:all PecsCopyDemo.java
java PecsCopyDemo
```

**Standard output** (no time-dependent data):

```text
Append count: 3
Numbers: [0.5, 2, 4, 6]
Objects: [2, 4, 6]
Replaced count: 3
Slots: [2, 4, 6, -1]
Too small: IndexOutOfBoundsException
Too small unchanged: [-1, -1]
Self-copy count: 3
Self-copy: [1, 2, 3, 1, 2, 3]
Overlapping views: [1, 1, 2, 3]
Mapped count: 3
Mapped: [1.0, 2.0, 3.0]
Set processed: 3
Set values: [2, 4, 6]
Immutable destination: UnsupportedOperationException
Producer read: 2
Consumer read type: Integer
Collections.copy: [2, 4, 6]
```

Notable points:

- The first line uses `List<Integer>` and `List<Number>`: accepted by the compiler thanks to PECS.
- `List<Object>` is also a valid destination.
- `overwritePrefix` **replaces the leading positions** and keeps the trailing `-1`; it does not append.
- An undersized destination is rejected **before the write loop**, so in the example it stays `[-1,-1]`.
- Self-append uses a snapshot and produces `[1,2,3,1,2,3]`, avoiding iterating a collection while the loop itself mutates it via `add`.
- Two overlapping views produce `[1,1,2,3]` because source is copied into a snapshot first.
- `Set` illustrates **processed count** versus **newly added value count**.
- `List.of` has a compatible signature but does not support modification, so the error stems from the collection's runtime contract.
- `Collections.copy` shows the built-in JDK copy method on a destination with enough slots.

## 14. Null Contract Choices

A signature `<T> void copy(...)` **does not mean `T` is always non-null**. When the source contains `null`, whether destination accepts it depends on the specific API:

```java
List<String> source = new ArrayList<>();
source.add(null);

List<Object> allowNull = new ArrayList<>();
appendAll(source, allowNull); // May accept null.

List<Object> noNull = new ArrayList<>(List.of("existing"));
// Do not assume every List implementation allows null.
```

Collections from the `List.of` factory disallow null and mutation, whereas `ArrayList` allows null. `Set.of` also forbids null by contract.

If a copy API must forbid null, check explicitly:

```java
for (T value : source) {
    destination.add(Objects.requireNonNull(value, "element"));
}
```

If you need to **reject all bad data before writing anything**, validate/snapshot the entire source before touching the destination. Even then, that does not prevent exceptions from `destination.add` or mutations from another thread.

If business data permits null, do not use `List.copyOf(source)` as a snapshot step forgetting that this factory rejects null; `new ArrayList<>(source)` preserves nulls in the copied structure.

## 15. Mutation, Partial Failure, and Atomicity

PECS solves **type compatibility**, not transactional properties of a copy function.

Failures that can occur:

1. `destination.add` throws `UnsupportedOperationException` because the collection does not support addition.
2. `destination.set` throws an exception because the list is unmodifiable or restricts per-slot values.
3. `destination.add` rejects an element due to null/value type/special contract.
4. The source is modified during iteration, potentially causing `ConcurrentModificationException` or inconsistent data depending on the implementation.
5. The `mapper` callback throws an exception while processing an element.
6. Capacity-bounded collections may reject additions after some limit.
7. The caller provides an infinite/lazy iterable; snapshotting everything will not terminate.

With `appendAll`, if the third element causes an error, the first and second elements **may already have been added**. `appendSnapshot` only separates **reading source** from **writing destination**; it does not turn the `add` calls into an atomic transaction.

With `overwritePrefix`, checking sufficient length up front eliminates errors from **a destination being too short at check time**, yet individual `set` calls can still fail or have intermediate states observed by other code.

If the system requires **all-or-nothing**, use a different approach: build a separate result collection and swap references/commit under an appropriate synchronization boundary, use persistence-layer transactions, or use a domain-specific mechanism. Never promise atomicity merely because there is a local snapshot.

## 16. Safety with Multiple Threads and Mutable Data

An input may be a mutable `Collection`; if another thread modifies it while reading, the result can be inconsistent. `new ArrayList<>(source)` or a `for` loop loading elements into a snapshot **does not** guarantee an atomic snapshot for every concurrent source.

Options depending on requirements:

- Use an immutable structure or a snapshot created before starting the operation.
- Use a shared `synchronized`/lock across **both writers and copiers**, holding the lock long enough to read a consistent state.
- Use a concurrent collection with documented iteration semantics, accepting its consistent-view behavior when appropriate.
- If the destination also has shared readers/writers, ensure they synchronize with the write phase or use copy-on-write/result publication.

Safety of generic type arguments does not solve race conditions. A valid `<T>` method can still be non-thread-safe.

### Element references and deep copy

`appendSnapshot` and `overwritePrefix` only **copy element references**; they do not clone mutable objects.

```java
List<StringBuilder> source =
        List.of(new StringBuilder("A"));
List<Object> target = new ArrayList<>();

appendSnapshot(source, target);
source.get(0).append("B");

System.out.println(target.get(0)); // AB
```

That is a **shallow copy**. If deeply independent values are needed, a domain-supplied mapper/copier must handle the mutable internal state of each element — you cannot expect the `? extends T` wildcard to do that.

## 17. Parameter Naming and PECS-Friendly Javadoc

For a public API, describe the **source/destination** roles and return value meaning:

```java
/**
 * Appends every visited source element to destination.
 *
 * <p>The destination must support add operations. This method
 * may partially modify destination before an exception occurs.
 *
 * @param <T> element type transferred from source to destination
 * @param source producer of elements compatible with T
 * @param destination consumer accepting elements of type T
 * @return number of source elements whose destination.add call completed
 * @throws NullPointerException if source or destination is null
 * @throws UnsupportedOperationException if destination rejects an add
 */
static <T> int appendAll(
        Iterable<? extends T> source,
        Collection<? super T> destination) {
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(destination, "destination");
    int count = 0;
    for (T value : source) {
        destination.add(value);
        count++;
    }
    return count;
}
```

**Distinguish `@param <T>` from `@param source`:** the former documents the type parameter; the latter documents the formal value parameter. When switching from processed-count to accepted-count, update both the name and Javadoc; otherwise the API has a bug in its **promised semantics**, even if type checking still passes.

One design to avoid mixing up argument order places destination first like `Collections.copy(dest,src)`; another places source first like `appendAll(source,destination)`. Either works when documentation and parameter names are clear. **Do not guess parameter order solely from the two wildcards** when the method name is ambiguous.

## 18. Proper Compile-Time and Runtime Testing

Required **positive compile tests**:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

appendAll(integers, numbers);
appendAll(integers, objects);
```

A **negative compile test** (placed in a separate file intentionally failing to compile):

```java
List<Number> source = List.of(1, 2.5);
List<Integer> destination = new ArrayList<>();

// DOES NOT COMPILE:
appendAll(source, destination);
```

**Runtime tests** to verify:

| Case | Expectation |
| --- | --- |
| Empty source, mutable destination | Count 0; destination unchanged |
| `List<Integer>` → `List<Number>` | Succeeds, preserves list order |
| `List<Integer>` → `List<Object>` | Succeeds |
| `Set` already containing duplicate elements | Processed-count includes `add` calls returning false |
| Unmodifiable destination list | `UnsupportedOperationException` when copy attempts mutation |
| Overwrite with enough destination slots | Destination `size` unchanged, leading positions updated |
| Overwrite with too-short destination | Exception, checked before `set` loop |
| Self-append with snapshot | Appends exact snapshot of source |
| Two overlapping `subList`s | Result matches initial source snapshot |
| Source containing null | Matches method and destination null policy |
| Mapper transforming `Integer` → `Double` | Result compatible with `Collection<Number>` |
| Mapper throwing exception | No rollback guarantee for elements already added |
| Concurrent mutation | No default guarantee of consistent snapshot |

In JUnit, use assertions like `assertEquals`/`assertThrows` to test **actual values and exceptions**. A test that merely observes a call compiling does not prove the destination supports mutation; conversely, a runtime test cannot replace a negative compilation test for type safety.

## 19. Common Mistakes

**Mistake 1 — Writing two `List<T>` parameters because "both hold T."** When the intent is only reading source and writing destination, `? extends T`/`? super T` allow subtype/supertype combinations that invariant `List<T>` cannot express.

**Mistake 2 — Reversing PECS.** `Collection<? extends T>` is not the right type for adding arbitrary non-null `T` elements; `Iterable<? super T>` does not guarantee reading `T`.

**Mistake 3 — Casting `List<Integer>` to `List<Number>`.** An unchecked cast does not make the collection safely wider; `Double` data can break the `Integer` contract.

**Mistake 4 — Assuming `Collections.copy` grows destination's size automatically.** It overwrites, requiring enough existing positions for source.

**Mistake 5 — Calling `new ArrayList<>(n)` and assuming the list has n elements.** That constructor only sets initial capacity, not size.

**Mistake 6 — Using `addAll` when overwrite is intended.** `addAll` appends elements rather than replacing leading positions with `set`.

**Mistake 7 — Assuming a typed destination is always mutable.** `List.of`, unmodifiable views, and other implementations can reject `add`/`set` at runtime.

**Mistake 8 — Treating `processed` as newly added elements in a `Set`.** `add` returning `false` may count as a successfully processed element without increasing size.

**Mistake 9 — Copying directly between overlapping views without accounting for aliasing.** Use a snapshot or an algorithm with a proven safe read–write order.

**Mistake 10 — Passing the same collection as source and destination when a for-each loop reads and adds concurrently.** Can cause concurrent modification errors or unintended semantics; snapshot first if you want to support that scenario.

**Mistake 11 — Assuming snapshots perform deep copies.** They only retain references, without cloning element objects.

**Mistake 12 — Assuming snapshots automatically create atomic transactions.** Exceptions while writing destination can still leave partial modifications; concurrent writes also need separate synchronization.

**Mistake 13 — Assuming generic `T` is always non-null.** Null policy resides in the method and collection, not automatically enforced by a type parameter.

**Mistake 14 — Using raw types to allow different collection types.** Wildcard-typed APIs already express the requirement without discarding compiler checks.

**Mistake 15 — Forgetting `? super S`/`? extends R` when writing a mapper.** The callback needs to consume source and produce result; PECS applies to `Function`'s type arguments too.

## 20. Self-Practice Exercises

**Exercise 1.** Write `<T> int appendAll(Iterable<? extends T>, Collection<? super T>)`. State the exact meaning of `int` if the destination is a `Set`.

**Hint:** counting after `add` completes means "number of processed elements," not new elements when `add` returns `false`.

**Exercise 2.** Given `List<Integer> source` and `List<Number> target`, call the method without casts; try `List<Object>` as target as well. Explain why both are valid.

**Core answer:** target is a consumer of source elements; both `Number` and `Object` can accept `Integer`.

**Exercise 3.** Given `List<Number> source` containing `Integer` and `Double`, and `List<Integer> target`. Why can't you copy everything directly keeping the types?

**Answer:** target cannot accept every `Number`. If business logic requires converting `Double` to `Integer`, write a mapper/validator with an explicit policy instead of an unchecked cast.

**Exercise 4.** Does `Collections.copy(new ArrayList<>(10), List.of(1,2))` succeed?

**Answer:** no, if destination still has size 0 at the call site; capacity 10 does not mean 10 existing slots.

**Exercise 5.** How do `Arrays.asList(0,0)` and `List.of(0,0)` differ when used as an overwrite destination?

**Answer:** `Arrays.asList` supports `set` though not resizing; `List.of` does not support any mutation, including `set`.

**Exercise 6.** When source and destination are two `subList`s of the same list, why does `overwritePrefix` copy source first?

**Answer:** to prevent writes to destination from altering elements in source that the loop has not read yet.

**Exercise 7.** If `appendSnapshot(source, dest)` fails during `dest.add` on the last element, are earlier elements rolled back?

**Answer:** no. Snapshotting only separates reading source from writing destination; it does not make the operation transactional.

**Exercise 8.** What type can be safely read from `Collection<? super Integer>` without additional information?

**Answer:** `Object`. The compiler does not know whether the reference currently holds `Collection<Integer>`, `Collection<Number>`, or `Collection<Object>`.

**Exercise 9.** Design a helper that converts `String` values to `Integer` and appends them into `Collection<Number>`.

**Hint:** use `mapAppend(strings, numbers, Integer::parseInt)`, with `Function<? super S,? extends R>`; consider `NumberFormatException` and partial writes.

**Exercise 10.** Add a `tryAppendAll` variant reporting how many times `Collection.add` returned `true`, distinguishing it from the number of visited elements. Write a test with `LinkedHashSet` containing duplicate keys.

## 21. Checklist Before Publishing a Copy API

1. **Is the intent append or overwrite?** Method name, logic, and Javadoc must agree.
2. **Is PECS oriented correctly?** Source `? extends T`, destination `? super T`.
3. **Was the minimal abstraction chosen?** If only iteration is needed, `Iterable`; if `set(i)` is needed, `List`.
4. **Is a named `<T>` truly needed?** Yes, when linking source–destination types.
5. **Are raw casts avoided?** If conversion is needed, use a semantically explicit mapper.
6. **Does destination need pre-existing size or grow automatically?** This is the key difference between `Collections.copy` and append.
7. **What does the return value count?** Processed, accepted, inserted, or old values?
8. **Are null source/dest/mapper checked?** Where does the null-element policy live?
9. **Are self-copy/overlap supported?** If so, has the snapshot/algorithm been verified?
10. **Is atomicity promised?** If not, document the possibility of partial mutation on failure.
11. **Could destination refuse modification?** Is `UnsupportedOperationException` documented in the contract?
12. **With `Set`, are processed count and size increase distinguished?**
13. **Is there a concurrency policy?** An O(n) snapshot does not automatically guarantee thread safety.
14. **Are nested mutable values checked?** Shallow copy does not clone object state.
15. **Are wrong-direction compile-time tests included?** For example, `List<Number>` → `List<Integer>` must be rejected.
16. **Are runtime tests included for size, aliasing, null, unsupported operations, and mapper exceptions?**
17. **Does documentation state implementation expectations for ordering, duplicates, and performance?**

## 22. Conclusion

**PECS is how data-flow direction is expressed at the type level.** When writing a copy function from source to destination, start with **`Iterable<? extends T>` for reading** and **`Collection<? super T>` for writing**, or for positional operations use **`List<? extends T>` and `List<? super T>`**. Wildcards allow Java to pass subtype elements into supertype containers while remaining compiler-checked.

A good `copy` function must also clearly specify **whether it appends or overwrites**, whether it **requires pre-sized slots**, whether it **handles overlapping views**, whether it counts **visited elements or actually added ones**, and what its **contracts are for null, mutation, errors, aliasing, and concurrency**. `Collections.copy` is a standard PECS example for overwriting; `appendAll`, `appendSnapshot`, `overwritePrefix`, and `mapAppend` demonstrate how to design variants with accurate semantics without raw types or unchecked casts.

Let **signatures express type safety**, **method names express operations**, and **Javadoc/tests verify runtime behaviors**.