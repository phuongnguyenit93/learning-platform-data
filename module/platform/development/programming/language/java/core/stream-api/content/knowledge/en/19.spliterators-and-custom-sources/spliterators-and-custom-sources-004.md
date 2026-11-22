# Characteristics: ORDERED, DISTINCT, SORTED, and NONNULL

> **Chapter:** Spliterators and Custom Sources  
> **Module:** JAVA_STREAM_API  
> **Focus:** Accurately understand four `Spliterator` characteristics in the Java Stream API: `ORDERED`, `DISTINCT`, `SORTED`, and `NONNULL`. When creating custom Stream sources, these flags are **guarantees about data and traversal**, not mere optimization hints.

## Learning Objectives

After this lesson, you will be able to:

1. Explain what `Spliterator` does in a lazy pipeline and in data partitioning for `parallelStream()`.
2. Distinguish **encounter order** (`ORDERED`), **uniqueness per `equals`** (`DISTINCT`), **sorted order per comparator** (`SORTED`), and **absence of null elements** (`NONNULL`).
3. State the exact relationships and differences: `SORTED` implies `ORDERED`; `ORDERED` does not necessarily mean `SORTED`; `DISTINCT` does not mean sorted.
4. Inspect flags via `characteristics()`/`hasCharacteristics(...)` and understand `getComparator()` rules.
5. Write a custom `Spliterator` with `tryAdvance`, `trySplit`, `estimateSize`, and `characteristics` satisfying the contract.
6. Verify parts returned by `trySplit`, traversal order, uniqueness, null-freeness, size, and sequential/parallel execution.
7. Recognize the risks of misdeclaring flags, using an unsuitable comparator, or mutating the source while a Stream is processing.
8. Understand how these characteristics relate to `filter`, `map`, `distinct`, `sorted`, `unordered`, and optimizations.

Examples use **Java 17+** for `List.of`, `List.copyOf`, and `Stream.toList()`. `Spliterator` itself, the four flags studied here, and `StreamSupport` have existed since **Java 8**. For Java 8–15, use compatible APIs like `collect(Collectors.toList())` instead of `Stream.toList()`.

---

## 1. Where Does Spliterator Sit in the Java Stream API?

`Spliterator<T>` is an interface used to **traverse** and, when appropriate, **split** elements of a data source. Many collections provide it via `collection.spliterator()`. `StreamSupport.stream(...)` can use a Spliterator as the source for a new Stream.

~~~text
Collection / array / custom source
                  |
                  v
          Spliterator<T>
           |          |
           |          +--- trySplit() ---> Another Spliterator<T>
           |
           +--- tryAdvance(Consumer<T>) / forEachRemaining(...)
                  |
                  v
      Stream<T> (lazy pipeline)
                  |
      filter -> map -> distinct -> sorted -> ...
                  |
                  v
        terminal operation
         collect / reduce / ...
~~~

Three aspects to distinguish:

- **Traversal:** `tryAdvance` passes individual elements to the supplied action.
- **Partitioning:** `trySplit` can split off remaining work into other Spliterators.
- **Source description:** `characteristics()` returns a flag set telling the Stream what guarantees the source truly provides.

A source that knows its data is ordered, duplicate-free, sorted, and null-free can publish the corresponding flags. However, a source that merely "usually looks that way" has no right to declare them.

Initial example:

~~~java
import java.util.List;
import java.util.Spliterator;

List<Integer> numbers = List.of(4, 1, 4, 2);
Spliterator<Integer> source = numbers.spliterator();

System.out.println(source.hasCharacteristics(Spliterator.ORDERED));
// true: List has an encounter order.

System.out.println(source.hasCharacteristics(Spliterator.SORTED));
// false: List does not guarantee being sorted.
~~~

Even if the data is changed to `List.of(1, 2, 3)`, a regular List Spliterator **does not automatically infer `SORTED`**: flags are guarantees committed by the source, not an ad-hoc data check at read time.

## 2. Characteristics Are a Bitmask, Not a List of Labels

`Spliterator` defines `int` constants. You can inspect them using:

~~~java
int flags = spliterator.characteristics();

boolean ordered = spliterator.hasCharacteristics(Spliterator.ORDERED);
boolean distinct = spliterator.hasCharacteristics(Spliterator.DISTINCT);
boolean sorted = spliterator.hasCharacteristics(Spliterator.SORTED);
boolean nonNull = spliterator.hasCharacteristics(Spliterator.NONNULL);
~~~

These are independent or constrained **bits**. They can be combined with bitwise OR:

~~~java
int flags =
        Spliterator.ORDERED
        | Spliterator.DISTINCT
        | Spliterator.SORTED
        | Spliterator.NONNULL;
~~~

When checking with bitwise AND, you can query whether a group of flags coexists:

~~~java
boolean allFour = spliterator.hasCharacteristics(
        Spliterator.ORDERED
        | Spliterator.DISTINCT
        | Spliterator.SORTED
        | Spliterator.NONNULL
);
~~~

`hasCharacteristics` only reports **declared characteristics**. It **does not scan the entire source to prove** the data is actually duplicate-free or null-free. Therefore, if the code creating the Spliterator makes a false declaration, flag checks will still return results based on that false declaration.

### 2.1. The four core flags at a glance

| Flag | What does the source guarantee? | What does it NOT guarantee? |
|---|---|---|
| `ORDERED` | Defined encounter order for traversal | Not guaranteed sorted, nor that every lambda runs in that order |
| `DISTINCT` | No two elements at different positions are equal per `equals` | Not guaranteed sorted, non-null, or that secondary keys are unique |
| `SORTED` | Traversed in a defined sort order; has comparator or natural order | Not guaranteed duplicate-free; does not imply `NONNULL` |
| `NONNULL` | No `null` elements are emitted | Not guaranteed business-valid, nor equivalent to `DISTINCT` |

Key relationships:

~~~text
SORTED ───────> ORDERED      (required)
ORDERED ──X──> SORTED       (does not imply)
DISTINCT ──X─> SORTED       (does not imply)
SORTED ──X───> DISTINCT     (does not imply)
NONNULL: independent of the three properties above
~~~

Besides the four flags studied here, `Spliterator` also has `SIZED`, `SUBSIZED`, `IMMUTABLE`, and `CONCURRENT`. They describe other guarantees and should not be confused with element content or quality.

---

## 3. ORDERED: Source with an Encounter Order

`Spliterator.ORDERED` means the source has a defined **encounter order**. When traversing sequentially with `tryAdvance` or `forEachRemaining`, the Spliterator must emit elements in that order.

Example with a `List` source:

~~~java
import java.util.List;
import java.util.Spliterator;

List<String> names = List.of("Bình", "An", "Chi");
Spliterator<String> sp = names.spliterator();

System.out.println(sp.hasCharacteristics(Spliterator.ORDERED)); // true

sp.forEachRemaining(System.out::println);
// Bình
// An
// Chi
~~~

This order is **the element order in the List**, not alphabetical order. Thus `ORDERED` does not mean `SORTED`.

A source can have a defined order due to:

- **Position:** `List` and arrays.
- **Insertion order:** collections such as `LinkedHashSet`.
- **Key/comparator order:** a `SortedSet`.
- **Custom source rules:** for example, records ordered by ascending sequence number.

Conversely, collections like `HashSet` **do not guarantee an encounter order**. One traversal might look stable, but a program must not rely on that order as a contract.

### 3.1. Encounter order differs from parallel execution order

~~~java
import java.util.List;

List<String> values = List.of("A", "B", "C", "D");

values.parallelStream().forEach(System.out::println);
// Printing A, B, C, D in order is not guaranteed.

values.parallelStream().forEachOrdered(System.out::println);
// A
// B
// C
// D
~~~

In an ordered Stream, `forEachOrdered` preserves encounter order for the executed actions. This can limit useful parallelism compared to `forEach`.

`ORDERED` does not mean every operation in a parallel pipeline will **execute** sequentially by position. The framework can process partitions concurrently and enforce ordering only at operations or outputs required by the contract.

### 3.2. ORDERED and trySplit()

For an `ORDERED` Spliterator, `trySplit()` must return a Spliterator covering a **strict prefix** of the remaining elements; the current Spliterator retains the corresponding **suffix**.

~~~text
Remaining source: [A, B, C, D, E, F]
                        |
                     trySplit()
                        |
            +-----------+-----------+
            |                       |
   Returned Spliterator    Original Spliterator
        [A, B, C]               [D, E, F]
          prefix                  suffix
~~~

If an `ORDERED` source arbitrarily returns `[B, D, F]` from `trySplit` and keeps `[A, C, E]`, that split **violates the partitioning contract of an ordered source**.

If `trySplit()` returns `null`, it simply means the Spliterator cannot split further this time. There is no requirement that a Spliterator must be splittable to be `ORDERED`.

---

## 4. DISTINCT: No Duplicate Elements per equals

`Spliterator.DISTINCT` means **for any pair of elements at different positions**, the two values are not equal according to `Object.equals` (with appropriate null semantics).

~~~java
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.Spliterator;

Set<String> tags = new LinkedHashSet<>();
tags.add("java");
tags.add("stream");
tags.add("java"); // Does not create a second element.

Spliterator<String> sp = tags.spliterator();

System.out.println(sp.hasCharacteristics(Spliterator.DISTINCT)); // true
System.out.println(tags); // [java, stream]
~~~

A `Set`, by its set contract, never contains two elements equal per `equals`. `LinkedHashSet` also has insertion-based encounter order, yet **DISTINCT itself does not require ORDERED**.

### 4.1. DISTINCT does not mean unique across every attribute

~~~java
import java.util.List;
import java.util.stream.Collectors;

record Product(long id, String category) {}

List<Product> products = List.of(
        new Product(1L, "BOOK"),
        new Product(2L, "BOOK"),
        new Product(3L, "PEN")
);
~~~

These three records differ per `equals`, so the objects can all be `DISTINCT`, yet **category is not unique**: two products belong to `BOOK`. If indexing with `Collectors.toMap(Product::category, ...)`, duplicate keys will still occur.

The condition "no duplicate elements per `equals`" differs from "no duplicate IDs," "no duplicate emails," or "no duplicate categories" when the element type's `equals` does not depend solely on that attribute.

### 4.2. DISTINCT does not imply SORTED

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

Set<Integer> numbers = new LinkedHashSet<>();
numbers.add(9);
numbers.add(1);
numbers.add(5);

System.out.println(numbers); // [9, 1, 5]
~~~

The elements are unique, yet not sorted in ascending order. You can also have a source that is **SORTED without being DISTINCT**, such as `[1, 1, 2, 3]`.

### 4.3. Warning about comparators inconsistent with equals

A `Comparator` may treat two values as equivalent (`compare(a, b) == 0`) while `a.equals(b)` returns `false`, or vice versa. Thus, **proving keys differ according to a comparator is not enough to conclude `DISTINCT` per `equals`**.

When writing a `SORTED | DISTINCT` custom source, verify both:

1. Data is properly ordered according to the declared comparator.
2. No two elements are equal per `equals`.

In the strictly increasing `Integer` source example in section 10, natural ordering is consistent with `equals`, so checking `previous < current` satisfies both conditions.

---

## 5. SORTED: Contracted Sort Order

`Spliterator.SORTED` means elements are traversed in a defined sort order:

- **Natural order** of the elements, if the source uses natural ordering; or
- A **`Comparator`** provided by the source.

A Spliterator declaring `SORTED` **must** also declare `ORDERED`.

~~~java
import java.util.SortedSet;
import java.util.Spliterator;
import java.util.TreeSet;

SortedSet<Integer> sorted = new TreeSet<>();
sorted.add(9);
sorted.add(1);
sorted.add(5);

Spliterator<Integer> sp = sorted.spliterator();

System.out.println(sp.hasCharacteristics(Spliterator.ORDERED)); // true
System.out.println(sp.hasCharacteristics(Spliterator.SORTED));  // true

sp.forEachRemaining(System.out::println);
// 1
// 5
// 9
~~~

The ascending order here comes from `Integer`'s natural ordering, not because a list happened to be sorted by coincidence.

### 5.1. getComparator() is part of the SORTED contract

If a Spliterator has `SORTED`, `getComparator()` must:

- Return `null` when the source is sorted in **natural order**.
- Return the appropriate `Comparator<? super T>` if a custom order is used.

If the Spliterator **does not** have `SORTED`, calling `getComparator()` must throw `IllegalStateException`.

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Spliterator;
import java.util.TreeSet;

Spliterator<Integer> natural =
        new TreeSet<>(List.of(3, 1, 2)).spliterator();

System.out.println(natural.getComparator() == null); // true

TreeSet<String> reversed = new TreeSet<>(
        Comparator.reverseOrder()
);
reversed.addAll(List.of("An", "Bình", "Chi"));

Spliterator<String> customOrder = reversed.spliterator();

System.out.println(customOrder.getComparator() != null); // true

Spliterator<Integer> listSp = List.of(1, 2, 3).spliterator();

try {
    listSp.getComparator(); // List spliterator does not declare SORTED.
} catch (IllegalStateException expected) {
    System.out.println("Source does not declare SORTED");
}
~~~

**Common mistake:** overriding `getComparator()` to return `null` just to "make it pass" even though the `SORTED` flag is absent; or declaring `SORTED` while returning a comparator that does not reflect the actual element order.

### 5.2. SORTED does not guarantee uniqueness

~~~java
import java.util.List;

List<Integer> values = List.of(1, 1, 2, 3);

System.out.println(
        values.stream().sorted().toList()
); // [1, 1, 2, 3]
~~~

`sorted()` sorts elements but does not remove duplicates. If you need both properties, you usually need both `sorted()` and `distinct()` (unless the source already guarantees one of them).

### 5.3. Do not declare SORTED on a List just because you inspected the data

`List.of(1, 2, 3)` happens to have ascending contents in this example, but the general List source type does not guarantee that property for every List instance. In a custom source, **taking an immutable snapshot and validating upfront** before declaring `SORTED` can be valid; that is the strategy used in section 10.

---

## 6. NONNULL: Source Guarantees No null Values Are Emitted

`Spliterator.NONNULL` states that every element emitted by the Spliterator is **non-`null`**.

~~~java
import java.util.List;
import java.util.Spliterator;

List<String> names = List.of("An", "Bình", "Chi");

// List.of does not allow null elements.
boolean noNullInData = names.stream().noneMatch(v -> v == null);
System.out.println(noNullInData); // true
~~~

**However:** from the fact that data currently in a List is non-null, you **must not deduce** that `names.spliterator()` necessarily declares the `NONNULL` flag. This is a property of **the Spliterator implementation**, not a runtime inference over the List.

A custom source may declare `NONNULL` if its data structure, input validation, or element-emission protocol guarantees no nulls.

### 6.1. NONNULL does not replace business validation

~~~java
record Employee(String name, int age) {}

Employee e = new Employee("", -5);
System.out.println(e != null); // true
~~~

An object is non-null, yet its contents may be invalid under business rules. `NONNULL` does not certify positive ages, non-blank names, valid email formats, or any domain rule.

### 6.2. Do not declare NONNULL if the source can emit null

~~~java
import java.util.Arrays;
import java.util.List;

List<String> source = Arrays.asList("An", null, "Chi");

// Example explicitly handling null before calling String::length.
List<Integer> lengths = source.stream()
        .filter(java.util.Objects::nonNull)
        .map(String::length)
        .toList();

System.out.println(lengths); // [2, 3]
~~~

If a source can emit null, declaring `NONNULL` is wrong. Calling `filter(Objects::nonNull)` in the pipeline can handle nulls at the application layer, but it does not "fix" a **false source declaration** that may already have affected how the Stream optimized operations.

### 6.3. NONNULL does not make every terminal operation null-safe

For instance, `Stream.findFirst()` returns an `Optional<T>` and cannot represent a selected null value via `Optional.of(null)`:

~~~java
import java.util.stream.Stream;

// Can throw NullPointerException because the first element is null.
// Stream.of((String) null).findFirst();
~~~

Sources that may contain null need an explicit handling policy. Do not treat `NONNULL` as a way to "turn off" null checks on an unverified source.

---

## 7. Comparison Table of Characteristic Combinations

Do not read the four flags as four ascending levels of "quality." They describe **four distinct dimensions of information**:

| Conceptual Data Source | ORDERED | DISTINCT | SORTED | NONNULL |
|---|---|---|---|---|
| Sequence `[3, 1, 3]` by position | Yes | No | No | Yes, if guaranteed |
| Ascending sequence `[1, 1, 3]` | Yes | No | Yes | Yes, if guaranteed |
| Set `{3, 1, 5}` with no defined traversal order | No | Yes | No | Depends on source |
| Ascending natural integers `[1, 3, 5]` | Yes | Yes | Yes | Yes, if guaranteed |
| Sequence `[null, "A"]` by position | Yes | Yes if the two elements differ per equals | Possible, if comparator supports null | No |

The table describes **possible guarantees**; it does not assert that every Java implementation of a given collection automatically emits the exact flag set shown in the corresponding row.

### 7.1. Common collection examples

| Source Type | What You Can Usually Rely On |
|---|---|
| `List` | Has encounter order; does not imply DISTINCT or SORTED |
| `LinkedHashSet` | Set-unique and traverses in insertion order |
| `HashSet` | Set-unique; no guaranteed encounter order |
| `SortedSet`/`TreeSet` | Sorted order per comparator/natural order |
| `StreamSupport.stream(customSpliterator, ...)` | Depends entirely on the supplied Spliterator's contract |

In real code, check flags when decisions depend on them; alongside that, **verify the source implementation itself** to ensure flags reflect real data.

---

## 8. Inspecting Flags via API

~~~java
import java.util.List;
import java.util.Spliterator;

Spliterator<Integer> sp = List.of(5, 1, 5).spliterator();

int flags = sp.characteristics();

System.out.println(
        (flags & Spliterator.ORDERED) != 0
);

System.out.println(
        sp.hasCharacteristics(Spliterator.ORDERED)
);

System.out.println(
        sp.hasCharacteristics(
                Spliterator.ORDERED | Spliterator.SIZED
        )
);
~~~

When passing multiple bits to `hasCharacteristics`, the result is `true` only if **all requested bits** are present.

### 8.1. Commonly paired methods

| Method | Purpose |
|---|---|
| `characteristics()` | Returns the bitmask of source characteristics |
| `hasCharacteristics(flags)` | Checks whether all requested flags are declared |
| `estimateSize()` | Estimates the number of remaining elements |
| `getExactSizeIfKnown()` | Exact size if `SIZED` is present, otherwise `-1` |
| `tryAdvance(action)` | Emits at most one element and reports whether one remained |
| `forEachRemaining(action)` | Emits the remaining elements |
| `trySplit()` | Splits off part of the remaining source or returns `null` |
| `getComparator()` | Meaningful only if `SORTED` |

Example of safely checking `getComparator`:

~~~java
import java.util.Comparator;
import java.util.Spliterator;

static <T> Comparator<? super T> comparatorIfSorted(
        Spliterator<T> sp) {

    if (!sp.hasCharacteristics(Spliterator.SORTED)) {
        throw new IllegalArgumentException("Source has not declared SORTED");
    }

    return sp.getComparator();
    // null means natural ordering; not a broken comparator.
}
~~~

The snippet above belongs inside a Java utility class. If you need to compare using natural order when the comparator is `null`, verify clearly that the element type actually supports `Comparable` per the source contract.

---

## 9. When May a Custom Source Declare These Four Flags?

Before writing `characteristics()` for a custom Spliterator, ask four questions:

1. **ORDERED:** Does the source have a defined traversal order? If `trySplit` splits the source, is the split-off part a prefix of the remaining portion?
2. **DISTINCT:** Is every pair of elements at different positions guaranteed unequal per `equals`? Duplicate secondary keys alone do not prevent elements from being `DISTINCT`.
3. **SORTED:** Do elements truly follow natural order or the declared comparator? Are `ORDERED` declared and `getComparator` properly implemented?
4. **NONNULL:** Can none of the element-emission paths produce null? Could source mutations during traversal break this guarantee?

Characteristics must hold for **the entire lifetime of the Spliterator**, not just for the first few elements or sample data.

A simple, verifiable approach is:

- Create an immutable snapshot of the input source.
- Validate the data and ordering when creating the snapshot.
- Traverse using an index pair `[index, fence)`.
- When splitting, create a child Spliterator over the **prefix** `[index, mid)`, while the original Spliterator keeps `[mid, fence)`.
- Ensure every child Spliterator uses the same flag set accurately reflecting the snapshot slices.

The next section turns that approach into a runnable program.

---

## 10. Complete Example: Strictly Increasing, Non-Null Integer Source

The sample source provides clear guarantees:

- Values of type `Integer`, no nulls.
- Elements are sorted **strictly increasing** in natural order.
- No duplicate elements per `equals`.
- Encounter order matches ascending order.
- Snapshot cannot be structurally modified after creation.
- Each Spliterator knows its exact remaining element count and splits by index slice.

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;
import java.util.stream.StreamSupport;

public class SortedUniqueSpliteratorDemo {

    static final class SortedUniqueIntegers
            implements Spliterator<Integer> {

        private final List<Integer> data;
        private int index;
        private final int fence;

        // Public constructor: copies and validates source data.
        SortedUniqueIntegers(List<Integer> input) {
            Objects.requireNonNull(input, "input");

            // List.copyOf disallows null elements.
            List<Integer> snapshot = List.copyOf(input);

            for (int i = 1; i < snapshot.size(); i++) {
                if (snapshot.get(i - 1) >= snapshot.get(i)) {
                    throw new IllegalArgumentException(
                            "Values must be strictly increasing at index " + i
                    );
                }
            }

            this.data = snapshot;
            this.index = 0;
            this.fence = snapshot.size();
        }

        // Internal constructor: shares immutable snapshot over a slice.
        private SortedUniqueIntegers(
                List<Integer> snapshot, int index, int fence) {
            this.data = snapshot;
            this.index = index;
            this.fence = fence;
        }

        @Override
        public boolean tryAdvance(
                Consumer<? super Integer> action) {
            Objects.requireNonNull(action, "action");

            if (index >= fence) {
                return false;
            }

            action.accept(data.get(index++));
            return true;
        }

        @Override
        public Spliterator<Integer> trySplit() {
            int remaining = fence - index;

            if (remaining <= 1) {
                return null;
            }

            int middle = index + remaining / 2;

            // Return the prefix of remaining elements.
            SortedUniqueIntegers prefix =
                    new SortedUniqueIntegers(data, index, middle);

            // Current Spliterator retains the suffix.
            index = middle;

            return prefix;
        }

        @Override
        public long estimateSize() {
            return fence - index;
        }

        @Override
        public int characteristics() {
            return ORDERED
                    | DISTINCT
                    | SORTED
                    | NONNULL
                    | SIZED
                    | SUBSIZED
                    | IMMUTABLE;
        }

        @Override
        public Comparator<? super Integer> getComparator() {
            // Source is SORTED by Integer natural ordering.
            return null;
        }
    }

    public static void main(String[] args) {
        List<Integer> values = List.of(1, 3, 7, 9, 11);

        SortedUniqueIntegers source =
                new SortedUniqueIntegers(values);

        int required = Spliterator.ORDERED
                | Spliterator.DISTINCT
                | Spliterator.SORTED
                | Spliterator.NONNULL;

        System.out.println(source.hasCharacteristics(required));
        // true

        System.out.println(source.getComparator() == null);
        // true: natural order

        List<Integer> sequential = StreamSupport.stream(
                new SortedUniqueIntegers(values), false
        ).toList();

        List<Integer> parallel = StreamSupport.stream(
                new SortedUniqueIntegers(values), true
        ).toList();

        System.out.println(sequential); // [1, 3, 7, 9, 11]
        System.out.println(parallel);   // [1, 3, 7, 9, 11]
    }
}
~~~

### 10.1. Why is the example allowed to declare all four flags?

| Flag | Evidence from Implementation |
|---|---|
| `ORDERED` | Traverses in ascending index order and `trySplit` returns a **prefix** slice |
| `DISTINCT` | Constructor rejects any non-increasing adjacent pair; for `Integer`, natural order is consistent with `equals` |
| `SORTED` | Snapshot is validated as strictly increasing; `getComparator()` returns `null` to indicate natural order |
| `NONNULL` | `List.copyOf` rejects null elements before the source is exposed |

Additional flags:

- `SIZED`: `fence - index` is the exact remaining element count.
- `SUBSIZED`: after splitting, both the split-off part and retained part know their exact sizes.
- `IMMUTABLE`: traversal is backed by a structurally unmodifiable snapshot containing immutable `Integer` values.

**Limitations:** This is a specialized illustrative source for strictly increasing `Integer` values. You cannot blindly copy `DISTINCT | SORTED | NONNULL` onto an arbitrary source without the corresponding guarantees.

### 10.2. Why create a fresh Spliterator for each Stream?

~~~java
// Create a new source for each usage:
List<Integer> a = StreamSupport.stream(
        new SortedUniqueIntegers(values), false
).toList();

List<Integer> b = StreamSupport.stream(
        new SortedUniqueIntegers(values), true
).toList();
~~~

A `Spliterator` typically holds mutable traversal position. If one Stream has consumed a Spliterator, reusing that object for another Stream may yield only untraversed elements or none at all. **Never reuse a consumed source expecting two independent reads.**

---

## 11. Testing trySplit: Prefix, Suffix, and Uniqueness

Consider an ordered source:

~~~text
[1, 3, 7, 9, 11, 15]

trySplit:
  returned: [1, 3, 7]
  retained: [9, 11, 15]

When traversing returned part first, then retained part:
  [1, 3, 7, 9, 11, 15]
~~~

To test directly, place the following snippet inside `SortedUniqueSpliteratorDemo.main`:

~~~java
List<Integer> values = List.of(1, 3, 7, 9, 11, 15);

SortedUniqueIntegers remainder =
        new SortedUniqueIntegers(values);

Spliterator<Integer> prefix = remainder.trySplit();

if (prefix == null) {
    throw new AssertionError("A sufficiently large source must be splittable");
}

List<Integer> left = StreamSupport.stream(prefix, false).toList();
List<Integer> right = StreamSupport.stream(remainder, false).toList();

System.out.println(left);  // [1, 3, 7]
System.out.println(right); // [9, 11, 15]

java.util.ArrayList<Integer> recombined =
        new java.util.ArrayList<>(left);
recombined.addAll(right);

if (!recombined.equals(values)) {
    throw new AssertionError("Lost, duplicated, or reordered elements");
}
~~~

This snippet tests a single split. For a complex Spliterator, perform **multi-level** splitting repeatedly, verifying that all parts:

- Emit no elements outside the source.
- Never drop or duplicate elements.
- Preserve encounter order if `ORDERED`.
- Emit no nulls if `NONNULL`.
- Produce no duplicates per `equals` if `DISTINCT`.
- Preserve comparator/ordering of split parts if `SORTED`.
- Have exact sizes when `SIZED | SUBSIZED` is declared.

### 11.1. Flags after splitting

~~~java
int flags = Spliterator.ORDERED
        | Spliterator.DISTINCT
        | Spliterator.SORTED
        | Spliterator.NONNULL;

SortedUniqueIntegers source =
        new SortedUniqueIntegers(List.of(1, 2, 5, 8));

Spliterator<Integer> prefix = source.trySplit();

System.out.println(prefix != null
        && prefix.hasCharacteristics(flags)); // true

System.out.println(source.hasCharacteristics(flags)); // true
~~~

Both slices point to the validated snapshot and split into prefix/suffix, so all four guarantees still hold after splitting.

---

## 12. How Do Source Flags Affect the Stream Pipeline?

The Stream API uses metadata from the source and intermediate operations to plan execution. Certain operations can leverage known characteristics:

- `distinct()` can avoid unnecessary deduplication work if data is already guaranteed `DISTINCT`.
- `sorted()` can skip re-sorting if the source/pipeline is already guaranteed to be in the requested natural order.
- Encounter order affects `findFirst`, `limit`, `forEachOrdered`, and many stateful operations, especially in parallel.
- `SIZED`/`SUBSIZED` (beyond the four core flags) can aid partitioning, allocation, or count optimizations.

These are **valid optimization possibilities**, not guarantees that a specific JDK version will skip or perform a specific number of steps.

### 12.1. filter preserves element values but changes count

~~~java
import java.util.List;

List<Integer> values = List.of(1, 3, 7, 9, 11);

List<Integer> result = values.stream()
        .filter(n -> n > 5)
        .toList();

System.out.println(result); // [7, 9, 11]
~~~

Data-semantically, simply filtering elements from an already `SORTED`/`DISTINCT`/`NONNULL` sequence leaves remaining elements with those same properties and the same encounter order.

However, `filter` makes the element count no longer directly derivable from the source size. **Do not assume a Spliterator's bitmask after intermediate operations remains identical to the source bitmask**; Streams have their own rules for propagating or clearing flags.

### 12.2. map can lose DISTINCT, SORTED, and NONNULL

~~~java
import java.util.List;

List<Integer> values = List.of(1, 3, 5);

List<Integer> mapped = values.stream()
        .map(n -> n % 2)
        .toList();

System.out.println(mapped); // [1, 1, 1]
~~~

Even if the input source is duplicate-free and sorted, a general `map` can:

- Introduce **duplicates** when multiple elements map to the same value.
- Break **sort order** when the mapping function is non-monotonic.
- Return **null** even when inputs are non-null.

Therefore, `DISTINCT`, `SORTED`, or `NONNULL` must never be inferred automatically for the output of an arbitrary `map`. If a pipeline has special behavior preserving those properties, that guarantee must be evaluated specifically.

### 12.3. distinct(), sorted(), and unordered()

~~~java
import java.util.List;

List<Integer> numbers = List.of(3, 1, 3, 2);

System.out.println(numbers.stream().distinct().toList());
// [3, 1, 2]: ordered source keeps first occurrence.

System.out.println(numbers.stream().sorted().toList());
// [1, 2, 3, 3]: sorted, but duplicate 3 remains.

System.out.println(numbers.stream()
        .distinct().sorted().toList());
// [1, 2, 3]
~~~

`unordered()` is an intermediate operation that can **drop the Stream's encounter-order constraint**, giving the framework greater freedom to optimize. It **does not promise to shuffle elements**, nor does it imply elements lose `DISTINCT` or must contain nulls.

~~~java
List<Integer> result = numbers.parallelStream()
        .unordered()
        .distinct()
        .toList();

// Do not rely on element order in result when the pipeline no longer
// enforces encounter order.
~~~

**Do not alter source flags to force a desired order.** If you want sorting, use `sorted` with an appropriate comparator; if you want deduplication, use `distinct` or a set structure matching your `equals` policy.

---

## 13. Warning: Misdeclaring Characteristics Can Produce Wrong Results

An unvalidated source:

~~~text
Data: [1, 1, 2]
Reality:
  ORDERED  = yes, by position
  DISTINCT = no
  SORTED   = yes, in natural order
  NONNULL  = yes, if data has no nulls
~~~

If custom source code **incorrectly declares `DISTINCT`**, a Stream implementation may trust that deduplication is unnecessary and optimize away `distinct()`. The output could then still contain both `1`s.

~~~java
// DO NOT do this:
// characteristics() returns DISTINCT when the actual source contains [1, 1, 2].
//
// StreamSupport.stream(broken, false)
//         .distinct()
//         .toList();
//
// Do not use the result to assume the Stream fixed the source's invalid data.
~~~

Similarly:

- Declaring `SORTED` for unsorted data may cause `sorted()` to skip work the caller expected.
- Declaring `ORDERED` while `trySplit` fails to return a proper prefix can corrupt encounter-order-dependent results.
- Declaring `NONNULL` when the source can emit null **violates the contract** and invalidates downstream consumer assumptions.
- Declaring `SIZED` with an inaccurate `estimateSize` can break size-based optimizations.

Rule of thumb: **under-declaring what the source truly knows usually only forfeits optimization opportunities; over-declaring beyond the truth can produce wrong results.** Never add flags just because one benchmark or sample dataset "looked fine."

---

## 14. Custom Sources with Unknown Size

Not every source has data sitting in a `List` or knows its size before traversal. For instance, an application-provided `Iterator<String>`:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

Iterator<String> iterator = List.of("A", "B", "C").iterator();

Spliterator<String> source = Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED | Spliterator.NONNULL
);

List<String> values = StreamSupport.stream(source, false).toList();

System.out.println(values); // [A, B, C]
~~~

In this example:

- The iterator's order comes from `List`, so `ORDERED` can be declared.
- `List.of` contains no nulls and the iterator only yields List elements, so `NONNULL` can be declared.
- Do not declare `SIZED`, because `spliteratorUnknownSize` does not know the total element count upfront.
- Do not declare `DISTINCT` or `SORTED`, because this sample input is insufficient to establish a general contract for all similar sources.

When used on a real iterator from network, files, or database queries, recognize that the source may change, grow, fail, and require resource cleanup. `Spliterators.spliteratorUnknownSize` does not auto-close the iterator's underlying resources.

### 14.1. Infinite sources and traversal limits

~~~java
import java.util.stream.Stream;

List<Integer> firstFive = Stream.iterate(0, n -> n + 1)
        .limit(5)
        .toList();

System.out.println(firstFive); // [0, 1, 2, 3, 4]
~~~

This example is a demand-driven Stream generator rather than requiring a custom Spliterator. It shows that some sources have no known final count; in such cases, never declare `SIZED` without a valid exact size.

Generated data appearing ascending does not automatically make every infinite source `SORTED`; if writing a custom Spliterator and declaring `SORTED`, you must prove comparator ordering across every element actually emitted.

---

## 15. IMMUTABLE, CONCURRENT, and the Stability of the Four Flags

The four flags `ORDERED`/`DISTINCT`/`SORTED`/`NONNULL` describe the data; meanwhile, `IMMUTABLE` and `CONCURRENT` relate to how the source handles **modifications during traversal**.

| Additional Flag | Core Meaning | Does NOT Mean |
|---|---|---|
| `IMMUTABLE` | Element source cannot be structurally modified during traversal | Does not mean every element object is deeply immutable |
| `CONCURRENT` | Source supports concurrent modifications per its contract | Does not automatically guarantee DISTINCT/SORTED/NONNULL |
| `SIZED` | Remaining element count is known exactly per contract | Does not mean sorted order |
| `SUBSIZED` | Child Spliterators after splitting have exact sizes per contract | Does not mean balanced splits or always splittable |

A custom source backed by a mutable collection modified by another thread during traversal can break published guarantees. For example:

- Ascending sorted data modified by mid-list insertion may no longer be `SORTED`.
- Data unique at creation time may receive duplicate values during traversal, breaking `DISTINCT`.
- Reference fields inside mutable objects may become null, breaking business assumptions—even if the element reference itself is non-null.

Creating a read-only snapshot is a simple way to avoid those issues. When data must update continuously, pick an appropriate data structure and source contract; merely adding `CONCURRENT` to the bitmask does not make an arbitrary collection thread-safe.

### 15.1. SIZED and downstream transformations

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);

long count = values.stream()
        .filter(n -> n % 2 == 0)
        .count();

System.out.println(count); // 2
~~~

The `List` source knows its element count, but after `filter` the remaining count depends on the predicate. An intermediate operation can invalidate a count characteristic for the resulting pipeline. This is one reason not to treat source flags and pipeline flags as the same thing.

---

## 16. Characteristics with Primitive Spliterators

Java also provides:

- `Spliterator.OfInt`.
- `Spliterator.OfLong`.
- `Spliterator.OfDouble`.

These specialized types allow traversing primitive values without boxing into `Integer`/`Long`/`Double` at every step.

~~~java
import java.util.Spliterator;
import java.util.stream.IntStream;

Spliterator.OfInt ints = IntStream.range(0, 5).spliterator();

System.out.println(ints.hasCharacteristics(Spliterator.ORDERED));
// true

System.out.println(ints.hasCharacteristics(Spliterator.SORTED));
// true

System.out.println(ints.getComparator() == null);
// true: natural ordering in range source.
~~~

`IntStream.range(0, 5)` supplies the ascending, duplicate-free, finite sequence `0,1,2,3,4`. The `range` source's guarantees should be read under its own contract; do not extrapolate them to an arbitrary `IntStream` after `map`.

### 16.1. NONNULL with primitive types

Primitive `int`/`long`/`double` **cannot be null**. Still, whether a primitive Spliterator explicitly publishes `NONNULL` remains an implementation/contract detail of that specific Spliterator; when coding, you never need to box to `Integer` just to null-check primitive data.

If you convert via `mapToObj` returning objects, the mapping function **can return null**. You can no longer infer that the object stream has `NONNULL` just because the original integer source had no nulls.

---

## 17. Testing Custom Sources: Don't Just Compare Sequential vs Parallel

A solid Spliterator source needs verification across **four content and split-contract dimensions**. Suggested test matrix:

| Test Case | What to Verify |
|---|---|
| Empty source | `tryAdvance` returns false, `estimateSize` is 0; emits nothing |
| Single element | No loss/duplication, `trySplit` may return null |
| Multiple elements | Sequential traversal matches original order |
| 2-way split | Returned Spliterator covers prefix, retained part covers suffix |
| Multi-level split | Reassembling parts in order loses/duplicates nothing |
| Duplicate data | `DISTINCT` source constructor rejects or omits DISTINCT |
| Unsorted data | `SORTED` source constructor rejects or omits SORTED |
| Null element | `NONNULL` constructor rejects or handles per policy |
| Non-natural comparator | `getComparator` returns right comparator or omits SORTED |
| Mutated input source | Snapshot remains unaffected in published data |
| Parallel run | Terminal result matches contract, independent of thread order |
| Flags | Both original and split parts carry truly accurate flags |
| Size | If SIZED/SUBSIZED, remaining count matches `estimateSize` |
| Downstream operations | `distinct`, `sorted`, `limit`, `toList` return right results |

### 17.1. Framework-independent verification snippet

Place the following methods inside `SortedUniqueSpliteratorDemo` from section 10:

~~~java
static void expectInvalid(List<Integer> values) {
    try {
        new SortedUniqueIntegers(values);
        throw new AssertionError("Source should have been invalid: " + values);
    } catch (IllegalArgumentException | NullPointerException expected) {
        // PASS: constructor rejected non-compliant source.
    }
}

static void verifySource() {
    List<Integer> expected = List.of(1, 2, 5, 8, 13, 21);

    SortedUniqueIntegers sp = new SortedUniqueIntegers(expected);

    int required = Spliterator.ORDERED
            | Spliterator.DISTINCT
            | Spliterator.SORTED
            | Spliterator.NONNULL
            | Spliterator.SIZED
            | Spliterator.SUBSIZED;

    if (!sp.hasCharacteristics(required)) {
        throw new AssertionError("Missing required characteristics");
    }

    if (sp.getComparator() != null) {
        throw new AssertionError("Source must use natural order");
    }

    Spliterator<Integer> prefix = sp.trySplit();
    if (prefix == null || !prefix.hasCharacteristics(required)) {
        throw new AssertionError("Split violates contract");
    }

    List<Integer> left = StreamSupport.stream(prefix, false).toList();
    List<Integer> right = StreamSupport.stream(sp, false).toList();

    java.util.ArrayList<Integer> recombined =
            new java.util.ArrayList<>(left);
    recombined.addAll(right);

    if (!recombined.equals(expected)) {
        throw new AssertionError("Lost, duplicated, or reordered elements");
    }

    List<Integer> parallel = StreamSupport.stream(
            new SortedUniqueIntegers(expected), true
    ).toList();

    if (!parallel.equals(expected)) {
        throw new AssertionError("Parallel result mismatch");
    }

    expectInvalid(List.of(1, 1, 2)); // DISTINCT violated.
    expectInvalid(List.of(3, 2, 4)); // SORTED violated.
    expectInvalid(java.util.Arrays.asList(1, null, 3)); // NONNULL.

    System.out.println("SPLITERATOR_OK");
}
~~~

Call `verifySource()` from `main` or a unit test. Add test cases with varied lengths and split paths, especially if the Spliterator uses a partitioning algorithm more complex than an array slice.

**Do not trust `hasCharacteristics` alone.** In tests, compare emitted data against an independent oracle from the validated snapshot.

### 17.2. Checking every element of the full output

~~~java
List<Integer> result = StreamSupport.stream(
        new SortedUniqueIntegers(List.of(1, 2, 3, 5, 8)),
        true
).toList();

for (int i = 0; i < result.size(); i++) {
    if (result.get(i) == null) {
        throw new AssertionError("NONNULL violated");
    }

    if (i > 0 && result.get(i - 1) >= result.get(i)) {
        throw new AssertionError("Not strictly increasing");
    }
}
~~~

The strictly increasing check suits **the custom Integer source designed in this lesson**. For sources with a custom comparator or other value types, replace the condition with a comparator-based check and verify `DISTINCT` via `equals`.

---

## 18. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | How to Fix |
|---|---|---|
| Declaring `ORDERED` because a test run looked stable | Accidental order is not a defined encounter order | Check the source and `trySplit` algorithm |
| Thinking `ORDERED` means ascending | List order can be `[9,1,5]` | Use `SORTED` only when truly sorted |
| Thinking `DISTINCT` means unique `id` key | `equals` may depend on multiple fields | Separate `equals`-based uniqueness from unique business keys |
| Declaring `SORTED` without `ORDERED` | Violates `SORTED` implies `ORDERED` | Declare both and uphold traversal order |
| Not overriding `getComparator` for custom SORTED | Default method may throw `IllegalStateException` | Return null for natural order, right comparator for custom order |
| Declaring `SORTED` when only a prefix is sorted | Remaining parts could still be out of order | Validate entire dataset, or omit SORTED |
| Declaring `DISTINCT` when source has two equal values | `distinct` may optimize on a false premise | Deduplicate upfront or omit flag |
| Declaring `NONNULL` when mapper/iterator can return null | Violates source commitment | Null-check or omit NONNULL |
| `trySplit` picks interleaved elements from an ORDERED source | Returned split is no longer a prefix | Split by contiguous slices |
| Reusing an already-traversed Spliterator | Cursor state has already advanced | Create a new source for each pipeline |
| Letting a mutable source change during traversal | Can invalidate flags and traversal | Snapshot, synchronize, or use a compliant concurrent source |
| Relying on parallel `forEach` to print in ORDERED order | Execution order across threads is unguaranteed | Use `forEachOrdered` when order is needed |
| Treating source flags as every pipeline's flags | `map`/`filter`/`unordered` can alter metadata | Evaluate each operation's contract |
| Adding `SIZED` to speed things up | Wrong size can break optimizations | Declare only if `estimateSize` is truly exact |

---

## 19. Design Workflow for a Spliterator with Accurate Characteristics

A checklist to apply before publishing a custom source:

1. **Define the value domain:** What is type `T`, can the source contain nulls, which elements could be equal?
2. **Define encounter order:** Positional, chronological, or comparator-based? Must it be preserved in parallel?
3. **Determine DISTINCT:** Use `equals`, not uniqueness of an arbitrary field outside `equals`.
4. **Determine SORTED:** Choose natural ordering or a comparator; if declaring `SORTED`, declare `ORDERED` and implement `getComparator` properly.
5. **Determine NONNULL:** Do all emission paths and allowed source mutations guarantee no nulls?
6. **Design tryAdvance:** Emit exactly one element per successful call, stay within bounds, reject null actions.
7. **Design trySplit:** For `ORDERED`, return a prefix; ensure no lost/duplicated elements and all partitions still obey the flags.
8. **Declare SIZED/SUBSIZED if size is truly known:** `estimateSize` must reflect remaining elements after splitting/traversal.
9. **Manage source lifecycle:** If backed by I/O resources, close properly; Spliterator does not make resources safe automatically.
10. **Verify:** Empty data, single element, duplicates, unsorted data, nulls, multi-level splits, sequential/parallel runs, downstream `distinct` and `sorted`.
11. **Measure performance after correctness:** Adding flags does not guarantee faster Streams; benchmark on realistic data and JDKs.

Summary workflow:

~~~text
Have source data
       |
       v
Identify guaranteed properties
       |
       +--- uncertain? ---> Do not declare that flag
       |
       v
Validate / snapshot as appropriate
       |
       v
Implement tryAdvance + trySplit
       |
       v
Declare accurate characteristics + getComparator
       |
       v
Test source and all split parts
       |
       v
Create Stream via StreamSupport
       |
       v
Measure / optimize after correctness
~~~

---

## 20. Self-Check Exercises (with Answers)

### Exercise 1. How does ORDERED differ from SORTED?

**Prompt:** Source `List.of(9, 1, 5)` traverses in List element order. Is it ORDERED? Is it SORTED?

**Answer:** The List source has encounter order `9, 1, 5`, so it can declare ORDERED; it must not declare ascending SORTED because the data is unsorted. ORDERED does not imply SORTED.

### Exercise 2. DISTINCT and business keys

**Prompt:** Two records `Product(1, "BOOK")` and `Product(2, "BOOK")` differ per `equals`. If the source has no duplicate records, can it be DISTINCT? Does that prove category is unique?

**Answer:** It can guarantee DISTINCT for **`Product` elements** if every pair of elements differs per `equals`. However, category is not unique because both records have `"BOOK"`. If you need a one-to-one Map by category, you still need a duplicate-key policy or `groupingBy`.

### Exercise 3. Can SORTED omit ORDERED?

**Prompt:** Is a Spliterator that declares `SORTED` without `ORDERED` compliant with the contract?

**Answer:** No. `SORTED` implies `ORDERED`. A custom source must guarantee traversal order and declare the proper flags; `getComparator()` must reflect the sort order.

### Exercise 4. When does getComparator return null?

**Prompt:** For a Spliterator that is `SORTED` in `Integer`'s natural order, what does `getComparator()` return?

**Answer:** It returns `null`. If the source is SORTED by a custom comparator, it returns that comparator. Without SORTED, `getComparator()` must throw `IllegalStateException`.

### Exercise 5. Sequence [1, 1, 2, 3]

**Prompt:** An ascending sequence `[1, 1, 2, 3]`, no nulls. Which of the four flags can hold?

**Answer:** `ORDERED`, `SORTED`, and `NONNULL` if guaranteed by the source; **not `DISTINCT`**, because `1` appears twice. If the actual source is a regular List, do not assume List declares `SORTED` merely because the current data happens to be sorted.

### Exercise 6. trySplit on an ORDERED source

**Prompt:** Remaining source is `[A, B, C, D]`; `trySplit` returns `[B, D]` and keeps `[A, C]`. Is this valid if the source declares ORDERED?

**Answer:** No. The returned portion must be a **prefix** of the remaining elements. A valid split returns `[A, B]` and keeps `[C, D]`.

### Exercise 7. Does NONNULL prove valid emails?

**Prompt:** A Stream of `Customer` objects contains no nulls, yet some customers have blank emails. Does the NONNULL flag detect blank emails?

**Answer:** No. NONNULL only says `Customer` elements themselves are not `null`; it does not inspect field values or business rules.

### Exercise 8. Falsely declared DISTINCT flag

**Prompt:** A custom source emits `[2, 2, 3]` yet declares `DISTINCT`. Why is this dangerous if the pipeline has `distinct()`?

**Answer:** The framework may trust the DISTINCT flag and optimize away deduplication work. The output may still contain duplicate `2`s. Either remove the flag or deduplicate at the source before publishing.

### Exercise 9. Checking custom SORTED with a comparator

**Prompt:** A String source is sorted by `Comparator.reverseOrder()`. What should `getComparator()` return?

**Answer:** Return the comparator reflecting that reverse order; do not return `null`, because `null` means natural order only. The source must also declare ORDERED and actually traverse in that reverse order.

### Exercise 10. Does map preserve NONNULL?

**Prompt:** A `List<Integer>` source has no nulls, followed by `map(n -> n > 10 ? "big" : null)`. Can the result automatically be declared NONNULL?

**Answer:** No. The `map` function can produce `null`. An input source free of nulls does not guarantee the output is free of nulls.

### Exercise 11. SIZED and SUBSIZED

**Prompt:** A Spliterator has `estimateSize() == 10` initially, but after `trySplit` the exact sizes of both parts are unknown. Should `SUBSIZED` be declared?

**Answer:** No. `SUBSIZED` requires Spliterators produced via splitting to also satisfy the exact size contract. Only declare it when the splitting logic guarantees it.

### Exercise 12. Testing parallel sources

**Prompt:** Why is comparing `sequential.equals(parallel)` alone insufficient to confirm the four flags are declared accurately?

**Answer:** Both modes could share the same bug, honor the same false flag, or run on test data that fails to trigger edge cases. You need to **directly** test the flag set, emitted data, null/duplicate/sort properties, prefix/suffix splitting, sizes, and invalid source cases.

---

**Remember:** `ORDERED` is **encounter order**, `DISTINCT` is **uniqueness per `equals`**, `SORTED` is **sorted per natural order/comparator** (requiring ORDERED), and `NONNULL` is **no null elements emitted**. These flags are the **Spliterator's contract**, not guesses from sample data. When writing custom sources for the Java Stream API, validate data, implement `trySplit` consistently with encounter order, provide the proper `getComparator`, and test both the original source and split parts—especially before using parallel Streams.
