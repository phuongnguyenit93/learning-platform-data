# Designing a Copy Method from `List<? extends T>` to `List<? super T>`

## Goal

In Java Generics, a copy method needs to take elements from a source list and put them into a destination list **without losing type safety**. When the source contains `Integer` and the destination contains `Number` or `Object`, we want the program to compile even though `List<Integer>` is not a subtype of `List<Number>`.

The general signature that solves this requirement is:

```java
static <T> void appendCopy(
        List<? super T> destination,
        List<? extends T> source)
```

This is an **illustrative signature**; the full body is presented in the standalone runnable example below. This lesson helps you:

- Correctly identify the **reading source** (producer) and **writing destination** (consumer) roles under the PECS rule.
- Explain why `List<? extends T>` can read elements as `T`, while `List<? super T>` can accept elements of type `T`.
- Design a method to **append a copy of elements** in order while preserving the source list.
- Distinguish an appending method from `Collections.copy(destination, source)`, which **overwrites by index** and requires *existing* capacity/elements in the destination.
- Know how to handle the case where source and destination are the same list, unmodifiable lists, and runtime limitations.

## 1. The Problem and the Limits of Invariant Generics

Suppose:

```java
List<Integer> integers = new ArrayList<>(List.of(2, 4));
List<Number> numbers = new ArrayList<>();
```

We have `Integer extends Number`, yet **we cannot assign `List<Integer>` to `List<Number>`**:

```java
// List<Number> invalid = integers; // compilation error
```

If that assignment were accepted, a holder of `List<Number>` could add a `Double` into an actual `List<Integer>` object. That is why Java keeps `List<Integer>` and `List<Number>` **invariant in their type arguments**.

However, this is a legitimate need:

- **Read** integers from `List<Integer>`.
- **Write** each of those integers into `List<Number>`.

We do not need to treat the two lists as the same type; we only need to specify the type relationship at **the point of retrieving elements** and **the point of inserting elements**.

## 2. PECS: Producer `extends`, Consumer `super`

The **PECS** (*Producer Extends, Consumer Super*) rule guides wildcard selection by parameter role:

| Role | Declared type | What can be done safely |
| --- | --- | --- |
| Source supplying `T` | `List<? extends T>` | Read elements into a variable of type `T` |
| Destination receiving `T` | `List<? super T>` | Add a value of type `T` to the destination |
| List with exact type | `List<T>` | Read and add values of type `T`, if the implementation permits |

### Why Does `source` Use `? extends T`?

`List<? extends T>` has an actual element type that is an **unknown** subtype of `T`. Every value retrieved can be used as `T`:

```java
static <T> T firstOf(List<? extends T> source) {
    return source.get(0);
}
```

The snippet above is an illustrative method, assuming a non-empty list. The compiler allows `source.get(0)` to return type `T`. However, calling `source.add(valueOfTypeT)` generally **does not compile**, because the actual element type could be a narrower subtype than `T`.

For instance, with `T = Number`, the source might be `List<Integer>` or `List<Double>`. Writing an arbitrary `Number` into that list is unsafe.

### Why Does `destination` Use `? super T`?

`List<? super T>` has an actual element type that is `T` or an unknown supertype of `T`. If `T = Integer`, an `Integer` can be safely added to `List<Integer>`, `List<Number>`, or `List<Object>`:

```java
static <T> void addOne(List<? super T> destination, T value) {
    destination.add(value);
}
```

This method is a standalone illustration, not a complete Java example. Conversely, retrieving from `List<? super T>` is only guaranteed as `Object` because elements already in the destination may be declared with a type broader than `T`.

**Key point:** the copy method reads `T` from the producer and writes that same `T` into the consumer; it needs no unchecked cast and does not require converting `List<Integer>` into `List<Number>`.

## 3. Copy Method Signature and the Meaning of Each Part

We choose the parameter order **destination first, source second**:

```java
static <T> void appendCopy(
        List<? super T> destination,
        List<? extends T> source) {

    for (T value : source) {
        destination.add(value);
    }
}
```

The snippet above illustrates the basic idea and **does not yet handle the case where source and destination are the same list**. The next section uses a temporary snapshot to make that scenario safe.

Signature breakdown:

- `static <T>`: declares **the method's type parameter**; this is not a “less than” comparison syntax.
- `void`: the method performs the copy operation and returns no value.
- `List<? super T> destination`: a destination capable of accepting values of type `T`.
- `List<? extends T> source`: a source supplying values usable as `T`.
- `T value : source`: safe read; each source value is at least compatible with `T`.
- `destination.add(value)`: safe write; the destination's element type is `T` or a supertype of `T`.

A type inference example: calling `appendCopy(numbers, integers)` with `List<Number>` as destination and `List<Integer>` as source. The compiler can choose `T = Integer`: source `List<Integer>` matches `List<? extends Integer>` and destination `List<Number>` matches `List<? super Integer>`. It is not that `List<Integer>` itself becomes `List<Number>`.

You can also use a call with an explicit type argument:

```java
// Given numbers and integers as above:
appendCopy(numbers, integers);             // infer T
MyUtility.<Integer>appendCopy(numbers, integers); // syntax specifying T explicitly,
                                                   // if the method belongs to class MyUtility
```

The two lines only **illustrate call syntax**; the line with `MyUtility` requires placing the method in the corresponding class. In most cases, letting the compiler infer `T` automatically is shorter and clearer.

## 4. Safe Version When Source and Destination Are the Same List

An append method written with a `for-each` loop directly over the source usually works fine when source and destination are independent. However, if the same list is simultaneously iterated and passed `add`, many implementations such as `ArrayList` may detect structural modification and throw `ConcurrentModificationException`. Do not rely on the behavior of simultaneously iterating and adding to the same list.

An easily verifiable solution: **take a temporary snapshot of the source elements first, then modify the destination**:

```java
static <T> void appendCopy(
        List<? super T> destination,
        List<? extends T> source) {
    Objects.requireNonNull(destination, "destination");
    Objects.requireNonNull(source, "source");

    List<T> snapshot = new ArrayList<>(source);
    for (T value : snapshot) {
        destination.add(value);
    }
}
```

Calling `new ArrayList<>(source)` creates a **new list containing the existing element references**. It does not deep-clone each element object. This temporary snapshot ensures the loop only reads a stable structure while the method adds to the destination.

When `destination == source`, suppose the initial data is `[7, 8]`; the snapshot contains exactly `[7, 8]`; adding those two elements to the source/destination object produces `[7, 8, 7, 8]`. The method finishes without iterating and growing the same list at the same time.

`Objects.requireNonNull` validates both parameters before copying and reports `NullPointerException` with the argument name when an input is null. Two non-null parameters **do not mean every element inside is also non-null**; the destination list may have its own rules regarding null elements.

This version is used in the complete program next.

## 5. Standalone Runnable Java 17+ Example

Save the file as **`PecCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class PecCopyDemo {
    static <T> void appendCopy(
            List<? super T> destination,
            List<? extends T> source) {
        Objects.requireNonNull(destination, "destination");
        Objects.requireNonNull(source, "source");

        List<T> snapshot = new ArrayList<>(source);
        for (T value : snapshot) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(2, 4));
        List<Number> numbers = new ArrayList<>(List.of(1.5));
        appendCopy(numbers, integers);
        System.out.println("numbers: " + numbers);

        List<Object> objects = new ArrayList<>(List.of("begin"));
        appendCopy(objects, integers);
        System.out.println("objects: " + objects);

        List<Integer> same = new ArrayList<>(List.of(7, 8));
        appendCopy(same, same);
        System.out.println("same: " + same);
        System.out.println("integers unchanged: " + integers);

        List<Number> slots = new ArrayList<>(List.of(-1, -1, -1));
        Collections.copy(slots, integers);
        System.out.println("slots after Collections.copy: " + slots);

        List<Number> tooShort = new ArrayList<>(List.of(-1));
        try {
            Collections.copy(tooShort, integers);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("too short: IndexOutOfBoundsException");
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac PecCopyDemo.java
java PecCopyDemo
```

**Exact stdout:**

```text
numbers: [1.5, 2, 4]
objects: [begin, 2, 4]
same: [7, 8, 7, 8]
integers unchanged: [2, 4]
slots after Collections.copy: [2, 4, -1]
too short: IndexOutOfBoundsException
```

**Explanation of the output lines:**

1. `List<Integer> integers` serves as source and `List<Number> numbers` as destination. `appendCopy` appends `2`, `4` after `1.5`: result `[1.5, 2, 4]`.
2. `List<Object> objects` is also a valid destination for a `List<Integer>` source, yielding `[begin, 2, 4]`.
3. `appendCopy(same, same)` snapshots the two source elements before adding: `[7, 8]` becomes `[7, 8, 7, 8]`; no infinite loop occurs.
4. `integers` remains `[2, 4]` because copying only **reads** it without removing or modifying elements.
5. `Collections.copy(slots, integers)` differs from `appendCopy`: it replaces the first two elements of the destination `[-1, -1, -1]` and leaves the remaining element untouched, giving `[2, 4, -1]`.
6. `Collections.copy(tooShort, integers)` throws `IndexOutOfBoundsException` because the destination list only has one slot, whereas the source has two elements.

The program uses only `java.util` imports and has no external framework dependencies. `Number` and `Integer` belong to `java.lang`, so they need no separate import.

## 6. “Copy” Has Two Meanings: Appending and Overwriting

A common source of ambiguity in requirements is the word **“copy.”** Both mechanisms read a source and put data into a destination, yet have different semantics:

| Characteristic | `appendCopy(destination, source)` above | `Collections.copy(destination, source)` |
| --- | --- | --- |
| Operation on destination | `add` each element at the end | `set` overwrites each corresponding position |
| Initial destination | Can be empty, as long as adding is permitted | Must have at least `source.size()` elements |
| Change in destination size | Increases by number of source elements | Unchanged |
| Example destination `[9, 9, 9]`, source `[1, 2]` | `[9, 9, 9, 1, 2]` | `[1, 2, 9]` |
| Suitable mutable destination | List supporting adding | List supporting `set` |
| When both parameters are the same list | Temporary snapshot keeps append finite | No need to grow size |
| Basic complexity of sample implementation | O(n) add time for `ArrayList`, O(n) snapshot memory | Overwrites n positions without growing size; actual cost depends on implementation |

The standard API itself has a very similar signature:

```java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

This is the **illustrative signature** of `java.util.Collections.copy`. The method takes **destination first, source second**. With `Collections.copy`, the destination's current element count must be **greater than or equal to** the source's element count. Calling `new ArrayList<>(capacity)` only allocates *internal capacity*, **it does not increase the list's `size()`**, so it does not satisfy that requirement.

Common mistaken example:

```java
List<Number> destination = new ArrayList<>(10);
List<Integer> source = List.of(1, 2);

// Collections.copy(destination, source); // runtime IndexOutOfBoundsException
```

Here the `destination` list has `size() == 0` despite an initial capacity of 10. To append two numbers, use `appendCopy(destination, source)`; to overwrite via `Collections.copy`, you must initialize enough **actual elements** and ensure `set` is supported.

Conversely, `Arrays.asList(...)` creates a fixed-size list that still typically supports `set`, so it can suit `Collections.copy` if it has enough elements; it does not support `add` to grow its size, so `appendCopy` is unsuitable.

## 7. Why Are Casts or Raw Types Unnecessary?

A dangerous approach is trying to turn a `List<Integer>` source into `List<Number>`, or using a raw `List` to bypass type checks. The example below **should not be used**:

```java
// Wrong direction; this is an example of an unsafe cast:
@SuppressWarnings({"rawtypes", "unchecked"})
static void unsafe(List destination, List source) {
    destination.addAll(source);
}
```

Raw type operations can discard type information, allowing unsuitable values to be added to a list meant to contain only a specific subtype. The failure might only surface later at read/cast time (`ClassCastException`).

PECS lets the compiler prove the relationship is valid without casting:

- Source: `List<? extends T>` supplies a `T`.
- Destination: `List<? super T>` accepts that `T` value.
- All constraints are checked at **compile time**.

If you only need to append data and **know for certain the source is not modified during the operation** and source and destination cannot be the same object, you can write it concisely with `destination.addAll(source)` under the same PECS signature. The snapshot in the main example clarifies self-append semantics and copy cost, making it suitable for an instructional example.

## 8. Type Inference for `T` in Practical Cases

Consider typical combinations:

| Source type | Destination type | `appendCopy(dest, src)` | Explanation |
| --- | --- | --- | --- |
| `List<Integer>` | `List<Integer>` | Valid | Same element type |
| `List<Integer>` | `List<Number>` | Valid | Destination can hold `Integer` |
| `List<Integer>` | `List<Object>` | Valid | `Object` is a supertype of `Integer` |
| `List<Double>` | `List<Number>` | Valid | Destination can hold `Double` |
| `List<Number>` | `List<Object>` | Valid | `Object` can hold `Number` |
| `List<Number>` | `List<Integer>` | Invalid | Source could hold `Double`, which `Integer` destination cannot hold |
| `List<Object>` | `List<Number>` | Invalid | Source could hold non-`Number` types |
| `List<String>` | `List<Object>` | Valid | Every `String` is an `Object` |
| `List<Integer>` | `List<String>` | Invalid | No suitable `T` guarantees write safety |

The table considers **compilability** of the call. It does not guarantee the destination implementation supports `add` at runtime. For example, `List<Number> numbers = List.of(1, 2)` has a valid destination type, yet does not permit adding elements.

Another inference mistake is thinking the type argument `T` must always equal the exact type of either source or destination. In reality, the compiler finds constraints satisfying both the `extends` and `super` sides. Callers should not be required to manually cast two lists to a common type just to call a method with standard wildcards.

## 9. Runtime Risks and Limitations to Document Clearly

### 9.1. The Destination Must Support Adding

`List<? super T>` proves **the element type can be accepted**, but does not guarantee `add` will succeed. `List.of(...)`, `List.copyOf(...)`, or `Collections.unmodifiableList(...)` reject modifications; `Arrays.asList(...)` has a fixed size.

Therefore, an `appendCopy` API must document that the destination must be a **resizable list**, such as `ArrayList`. If the source has `n` elements and the additions succeed, the destination grows by `n` elements.

### 9.2. “Copy” Here Copies Element References

`new ArrayList<>(source)` and `destination.add(value)` do not deep-copy the state of a mutable `T` object. If the source holds mutable objects, source and destination may both point to those same element objects. Changing a property on a source object can be observed through the corresponding element in the destination.

For a **deep copy**, you need a copying rule per element type, such as passing in a mapper/copy factory function. Do not call `appendCopy` a deep copy.

### 9.3. No Atomicity or Automatic Synchronization

The illustrative version checks for null first, creates a snapshot, and then calls `add` one by one. If a later `add` call fails, elements added earlier **may remain in the destination**. Hence the method does not promise “all-or-nothing.”

The temporary snapshot also **does not automatically guarantee thread safety** if another thread concurrently modifies the source while creating the snapshot. Appropriate synchronization/ownership or a collection guaranteeing the required consistency is needed.

### 9.4. `null` and Data Validation

`Objects.requireNonNull` only forbids **the two list parameters themselves** from being null. If the source contains a null element, the snapshot may contain null and `destination.add(null)` will depend on whether the destination list accepts null. If you want to disallow null elements, define that contract and validate explicitly.

### 9.5. Order Preservation

The method uses `List` and `for-each`, so elements are added in source iteration order. Provided no other thread modifies the source during copying, the order of newly added elements in the destination matches the order of source elements at snapshot time. The destination may already hold prior elements; the method does not remove them.

## 10. Designing APIs by Intended Use

If you need to **append source into destination**, choose a name conveying appending, such as `appendCopy`, `appendFrom`, or `appendAll`; use the signature:

```java
static <T> void appendCopy(
        List<? super T> destination,
        List<? extends T> source)
```

If you need to **overwrite the beginning of the destination list**, use the built-in:

```java
Collections.copy(destination, source);
```

When you only need to **create a new list independent of the source's structure**, you do not necessarily have to take a destination list:

```java
static <T> List<T> mutableCopy(List<? extends T> source) {
    return new ArrayList<>(source);
}
```

This creates a new `ArrayList<T>`, rather than modifying the caller's list. This is also a **shallow copy** for reference-type elements. Given suitable input and a requirement for an unmodifiable list, `List.copyOf(source)` is another option, though that method does not accept null elements and does not guarantee a deep copy.

Choose the signature and return type based on the actual purpose. Wildcards are unnecessary if the API only operates on one exact concrete type and does not need to accept different subtype/supertype lists.

## 11. Common Mistakes

**Mistake 1 — Using `List<T>` for both source and destination.** This is overly restrictive: `List<Integer>` and `List<Number>` do not share the same type argument. If you only read the source and only add to the destination, `? extends T` and `? super T` allow a broader API while staying safe.

**Mistake 2 — Reversing the wildcards.** `List<? super T> source` only guarantees elements read out are `Object`, while `List<? extends T> destination` does not accept adding arbitrary `T` values. Producer/consumer roles must be determined by data direction.

**Mistake 3 — Treating `Collections.copy` as appending.** It overwrites elements by index and requires the destination to have at least as many elements as the source. `ArrayList` capacity does not equal the current number of elements.

**Mistake 4 — Iterating over and adding to the same list.** Using a `for-each` loop directly on a list when that list is also the destination can fail due to structural modification during iteration. Take a snapshot before adding if you want to support self-appending.

**Mistake 5 — Assuming wildcards make the destination mutable.** Generics prove type compatibility; they do not guarantee the `add` operation is supported by the implementation.

**Mistake 6 — Using casts or raw types instead of wildcards.** Casts can hide type errors until runtime and break element constraints.

**Mistake 7 — Expecting destination elements to be completely independent copies.** `appendCopy` copies references; it does not deep-clone the element objects.

## 12. Self-Check Questions

**Question 1.** Why does `appendCopy(List<Number>, List<Integer>)` compile even though `List<Integer>` is not a subtype of `List<Number>`?

Because the compiler infers a matching `T` (such as `Integer`) for the two wildcards. It takes a `T` from `List<? extends T>` and adds that same `T` to `List<? super T>`.

**Question 2.** When the source is `List<Number>` containing both `Integer` and `Double`, can it be copied to `List<Integer>`?

No; a destination list declared as `Integer` cannot safely hold arbitrary `Number` elements.

**Question 3.** Does `new ArrayList<Number>(100)` have enough space for `Collections.copy(dest, source)` with a 3-element source?

Not necessarily: that constructor only allocates capacity; `size()` is still 0. At least three actual elements must already exist and the destination must support `set`.

**Question 4.** When calling `appendCopy(list, list)` with `list = [7, 8]`, what does the snapshot version produce?

`[7, 8, 7, 8]`. The snapshot captures only the two source elements before the method begins adding.

**Question 5.** Does `List<? super Integer>` guarantee reading elements as type `Integer`?

No. Because the destination could be `List<Number>` or `List<Object>`, values read out are only guaranteed as type `Object`. In this problem, the method **does not need to read from the destination**.

**Question 6.** If the destination is a `List.of(...)`, does the generic signature guarantee adding will work?

No. The compiler may accept the type relationship, but runtime throws `UnsupportedOperationException` when attempting to modify a list that does not support modification.

## Key Takeaway

A PECS copy method has the form `<T> void copy(List<? super T> destination, List<? extends T> source)`: **the source produces `T`, so it uses `extends`; the destination consumes `T`, so it uses `super`**. In the implementation, clearly distinguish **appending** from **overwriting** semantics; the `appendCopy` example in this lesson appends and snapshots the source first to support self-appending, whereas `Collections.copy` overwrites existing positions. Wildcards guarantee type safety; list mutability, aliasing, deep copying, and synchronization remain separate runtime and design concerns.
