# Designing Flexible yet Type-Safe Methods that Accept Collections

## 1. “Flexibility” Must Serve the Right Contract

A well-designed method that accepts a collection allows callers to pass suitable data structures and element types without forcing casts or wasteful defensive copies. At the same time, its signature must help the compiler reject usages that could introduce elements of the wrong type into the data.

For example, a summation function only needs to read numbers. Accepting `ArrayList<Integer>` ties the method to both a concrete implementation class and an overly narrow numeric type. Accepting a raw `Collection` and casting each element loses type safety guarantees.

A more appropriate choice is:

```java
// Signature sketch, not a standalone program.
static double sum(Iterable<? extends Number> source)
```

This signature states:

- The algorithm only needs to iterate over the source.
- Each element can be used as a `Number`.
- It can accept a source of `Integer`, `Double`, or `Number`.
- The return value has a fixed type of `double`.

However, the signature alone does not fully specify behavior regarding `null`, source mutability, numeric precision, or multithreaded access. Method design must combine **type relationships**, **observable behavior**, and **data ownership**.

This article uses Java 17 and focuses on design patterns directly applicable to collections and maps. Familiarity with generics, subtyping relationships, and core collection interfaces is assumed.

## 2. Identify the Operations Before Choosing Parameters

Do not start by slapping wildcards onto an arbitrary signature. First, clearly specify what the method will do.

| Actual need | Parameter type to consider | Reason |
| --- | --- | --- |
| Iterate over elements only | `Iterable<? extends T>` or `Iterable<?>` | Does not require `size`, indexing, or insertion capabilities |
| Need `size`, `contains`, or a collection copy constructor | `Collection<? extends T>` | Provides enough group-level element API |
| Need positional access and replacement | `List<T>` | Position is part of the contract |
| Need uniqueness semantics | `Set<T>` or an appropriate wildcard variant | Expresses the set model |
| Receive elements to add into a destination | `Collection<? super T>` | Destination can hold `T` |
| Key-based lookup | `Map<K, V>` or role-specific wildcards | Requires a key–value relationship |

The guiding principle is to choose an interface that **adequately expresses both semantics and required operations**, not merely the interface with the fewest methods.

For example, if list ordering is a business requirement, changing the parameter to `Collection` while implicitly relying on indexing or unguaranteed iteration order weakens the contract. Conversely, if the method only computes a sum via a loop, requiring `ArrayList` specifically adds no value.

Foundational API references: [Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html), [List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), and [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

## 3. Assign Roles: Source, Destination, and Read–Write Data

For each parameter, ask:

1. Does the method only read elements from here?
2. Does the method put elements into here?
3. Does the method need to both read and write back the same element type?
4. Does that type need to be linked to the return type or another parameter?

From there, choose:

| Role | Signature pattern | What is known |
| --- | --- | --- |
| Observation only, no element-specific API needed | `Collection<?>` | Read as `Object` |
| Producer supplying elements usable as `T` | `Collection<? extends T>` | Read as `T` |
| Consumer receiving elements of type `T` | `Collection<? super T>` | Write `T`; read generally as `Object` |
| Must preserve the exact element type across read–write | `Collection<T>` or `List<T>` | Type variable `T` links type positions |
| Return type preserves a relationship with the source | Generic method `<T>` | Can express the return type in terms of `T` |

The PECS mnemonic — a producer of elements uses `extends`, a consumer of elements uses `super` — is helpful at this stage. It must be understood in terms of data flow within the algorithm.

`extends` does not create immutability; nor does `super` grant mutation capabilities to an object that does not support additions. [Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html)

## 4. Reading Sources: Use Upper Bounds tailored to the Need

```java
// Method declaration snippet; requires import java.util.Objects.
static double sum(Iterable<? extends Number> source) {
    Objects.requireNonNull(source, "source");

    double total = 0;
    for (Number value : source) {
        total += Objects.requireNonNull(value, "element").doubleValue();
    }
    return total;
}
```

Valid inputs:

```java
// Illustrative snippet inside a method, assuming sum is declared.
// Requires import java.util.*.
List<Integer> integers = List.of(1, 2, 3);
List<Double> decimals = List.of(0.5, 1.5);

System.out.println(sum(integers)); // 6.0
System.out.println(sum(decimals)); // 2.0
```

Why not use `Iterable<Number>`? Generics are invariant: `Iterable<Integer>` is not automatically an `Iterable<Number>`. An upper-bounded wildcard opens up the right range of inputs while guaranteeing that every element can be read as a `Number`. [Upper Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/upperBounded.html)

Additional contract details to document:

- Both the source and its elements must be non-`null`.
- An empty source returns `0.0`.
- The method does not mutate the source.
- Arithmetic uses `double`, which does not guarantee exact decimal representation for monetary values.
- The source must be safely iterable under the application's concurrency policy.

`Objects.requireNonNull` helps enforce input preconditions and provides a clear failure site. It does not validate all business rules for the elements. [Objects API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String))

## 5. Data Destinations: Use Lower Bounds

If a method produces or supplies `Integer` instances to add into a destination, that destination could be a collection of `Integer`, `Number`, or `Object`.

```java
// Method declaration snippet; requires import java.util.Collection.
static void addDefaults(Collection<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

Using `Collection<Integer>` in the signature would restrict callers unnecessarily. `Collection<Object>` cannot accept a `Collection<Integer>` either because of invariance. `? super Integer` accurately expresses “a destination capable of holding `Integer` values”.

However, reading from `destination` only yields `Object` in general: a `Collection<Number>` destination might already contain `Double` instances.

The method's contract also requires that:

- The destination exists (is non-`null`).
- The destination supports `add`.
- The added values satisfy the destination's constraints.
- The caller permits mutating the passed-in object directly.

A `List.of(...)` instance may match the type signature yet fail at runtime because it does not support mutation. No choice of wildcard can solve that. [Lower Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/lowerBounded.html)

## 6. Linking Source and Destination with the Same T

When transferring data from one collection to another, a type parameter is needed to name the relationship between them:

```java
// Signature sketch; requires import java.util.Collection.
static <T> void addFrom(
        Collection<? super T> destination,
        Collection<? extends T> source)
```

Reading the signature:

1. The source supplies elements of type `T` or a subtype of `T`.
2. Every element read from the source can be treated as a `T`.
3. The destination can accept `T` because its element type is `T` or a compatible supertype.

Example:

```java
// Illustrative snippet inside a method, assuming addFrom is declared.
// Requires import java.util.*.
List<Integer> source = List.of(1, 2, 3);
List<Number> destination = new ArrayList<>();

addFrom(destination, source);
```

The `Integer` elements are added into the `Number` destination without any casting.

You cannot use this method to add `Double` elements into a `List<Integer>`. The compiler cannot infer a single `T` that satisfies both a `Double` source and an `Integer` destination; such a call is rightfully rejected.

Never use two unrelated wildcards and assume they resolve to the same type. Sharing an upper bound like `Number` does not guarantee that an `Integer` source and a `Double` destination are compatible.

Generic methods are covered in [Generic Methods](https://docs.oracle.com/javase/tutorial/java/generics/methods.html).

### 6.1. Choose an Aliasing Policy Before Implementing

The source and destination might be the exact same object or views backed by the same underlying data. A loop that iterates over the source while simultaneously adding to the destination can invalidate the iterator.

In this article, `addFrom` takes a structural snapshot of the source before mutating the destination:

```java
// Method declaration snippet; requires import java.util.*.
static <T> void addFrom(
        Collection<? super T> destination,
        Collection<? extends T> source) {

    Objects.requireNonNull(destination, "destination");
    Objects.requireNonNull(source, "source");

    List<T> snapshot = new ArrayList<>(source);
    for (T value : snapshot) {
        destination.add(value);
    }
}
```

With a mutable list, `addFrom(list, list)` appends the initial elements once, rather than iterating over a continually growing source.

This is a deliberate design choice for our sample API:

- It incurs memory overhead proportional to the source size.
- The snapshot is a shallow copy, retaining references to the same element objects.
- It does not make reading a concurrently modified source thread-safe.
- It does not make the overall addition process transactional.
- A `Set` destination still enforces its own duplicate-elimination rules.
- The destination may still reject `null` or specific values according to its own contract.

The name `addFrom` means requesting the destination to accept elements from the source. It does not promise that the destination's size increases by the exact size of the source across all data structures.

## 7. When Reading and Writing the Same Type: Keep T

An operation that swaps two elements needs to read out and write back the exact element type of the list:

```java
// Method declaration snippet; requires import java.util.*.
static <T> void swap(List<T> values, int left, int right) {
    Objects.requireNonNull(values, "values");

    T leftValue = values.get(left);
    T rightValue = values.get(right);
    values.set(left, rightValue);
    values.set(right, leftValue);
}
```

Two values of type `T` are read from the same `List<T>` and written back into the same list. There is no need to know whether `T` is a string, a number, or a domain type.

Contract:

- Both indices must be valid.
- The list must support `set`.
- The method mutates the input list in place.
- It does not guarantee atomicity if element replacement fails partway through.
- It does not promise uniform performance across all list implementations.

Reading both elements before calling `set` ensures that an out-of-bounds index is detected before any mutation occurs in this illustrative implementation. However, it is not a general rollback guarantee against all other possible exceptions.

Fixed-size lists may support `set`, whereas unmodifiable lists do not. The type `List<T>` does not encode that distinction.

If a public API accepts a wildcard (`List<?>`) because the operation merely rearranges existing elements without exposing their type, a private wildcard-capture helper method can preserve type safety cleanly. There is no need to fall back to raw types.

## 8. Preserving the Relationship Between Source and Result

### 8.1. Returning a Copy with a Usable Type

```java
// Method declaration snippet; requires import java.util.*.
static <T> List<T> editableCopy(Collection<? extends T> source) {
    Objects.requireNonNull(source, "source");
    return new ArrayList<>(source);
}
```

With a compatible target type:

```java
// Illustrative snippet inside a method, assuming editableCopy is declared.
List<Integer> source = List.of(1, 2, 3);
List<Number> result = editableCopy(source);
result.add(2.5);
```

`T` links the result type to the set of types the source can supply. Target-type inference allows `T` to be inferred as `Number` in this example.

The returned list has a clear contract:

- It is a new, mutable list.
- It preserves the iteration order of the source.
- Structural modifications to the result do not affect the source structure.
- Element object references are still shared (shallow copy).
- `null` elements are preserved if present in the source and accepted by the copy constructor.
- It does not preserve comparators or specialized structural traits of the source.

The `ArrayList` constructor accepting `Collection<? extends E>` is itself a real-world example of a flexible source parameter. [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

### 8.2. Avoid Returning Unnecessary Wildcards

Returning `List<? extends T>` prevents the caller from adding new `T` values even when the API explicitly intends to produce a mutable list. Unless there is a specific reason to hide and preserve an unknown subtype, returning `List<T>` communicates a much more useful result.

If you want an unmodifiable result, choose an explicit mechanism such as `List.copyOf` and document its `null` policy and copying behavior. Do not use a wildcard return type as a substitute for an unmodifiable guarantee.

Flexibility on input and clarity on output are related but distinct design decisions.

## 9. Callbacks Also Have a Consumer Side and a Producer Side

A method that transforms each element into a new value can use:

```java
// Method declaration snippet; requires import java.util.* and java.util.function.Function.
static <T, R> List<R> mapToList(
        Iterable<? extends T> source,
        Function<? super T, ? extends R> mapper) {

    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(mapper, "mapper");

    List<R> result = new ArrayList<>();
    for (T value : source) {
        result.add(mapper.apply(value));
    }
    return result;
}
```

Read the signature `Function<? super T, ? extends R>` by following the data flow:

- The callback **consumes** a `T`, so a function capable of handling any supertype of `T` can also be used.
- The callback **produces** a result usable as `R`, so returning any subtype of `R` is also valid.

Example:

```java
// Illustrative snippet assuming mapToList is declared.
// Requires import java.util.* and java.util.function.Function.
List<Integer> source = List.of(1, 2, 3);
Function<Number, String> label = number -> "n=" + number;

List<CharSequence> labels = mapToList(source, label);
```

A function accepting `Number` can process `Integer` elements from the source. The `String` instances it returns can be stored and used as `CharSequence`.

The callback contract should also specify:

- Both the source and the callback must be non-`null`.
- In this example, `null` elements from the source are passed directly to the callback; the callback decides whether it can handle them.
- A `null` result returned by the callback is accepted by `ArrayList`.
- The result preserves the iteration order of the source, without inventing ordering guarantees that the source lacks.
- The callback must not mutate the source in a way that compromises safe iteration.
- Exceptions thrown by the callback propagate outward; any external side effects already performed by the callback are not rolled back automatically.

This is a simple transformation pattern meant to illustrate signature design. If a production API needs to forbid `null` values or side effects, add appropriate rules and runtime checks. [Function API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html)

## 10. Applying Bounds Independently to Map Keys and Values

A method that creates a mutable copy of a map can widen both the key type and the value type independently:

```java
// Method declaration snippet; requires import java.util.*.
static <K, V> Map<K, V> editableMapCopy(
        Map<? extends K, ? extends V> source) {

    Objects.requireNonNull(source, "source");
    return new LinkedHashMap<>(source);
}
```

Example:

```java
// Illustrative snippet assuming editableMapCopy is declared; requires import java.util.*.
Map<String, Integer> source = new LinkedHashMap<>();
source.put("A", 1);

Map<CharSequence, Number> copy = editableMapCopy(source);
copy.put("B", 2.5);
```

The source data has `String` keys usable as `CharSequence` and `Integer` values usable as `Number`. Because the copy is an independent map with its own type parameters, inserting a `Double` value into the copy does not violate the contract of the source map.

Details to document:

- Creates a new map preserving the iteration order of the source.
- Does not deep-copy keys or values.
- Does not preserve specialized source characteristics, such as a sorted map's comparator.
- Output entry count and ordering follow the contracts of the source and the chosen map implementation.
- Does not make it safe to use mutable keys whose state changes affect `equals`/`hashCode`.

If an API only reads values and requires exact key types, you can widen only the `V` side—for example, `Map<String, ? extends Number>`. There is no need to widen the key type when the domain genuinely requires `String`.

Order preservation and copy-constructor behavior are described in the [LinkedHashMap API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

## 11. Type Safety Is Only Part of the Contract

### 11.1. Mutability and Element Rules

A method accepting `Collection<? super T>` can still encounter an `UnsupportedOperationException` at runtime if passed an unmodifiable destination.

Another destination might match the generic type signature yet reject `null`, require mutually comparable elements, or enforce domain value constraints. Never treat “it compiles” as proof that every runtime input will be accepted.

### 11.2. Ownership, Views, and Aliasing

A method specification should answer:

- Does it mutate its arguments or produce a new result?
- Does it retain references to the input collection after returning?
- Can a returned view reflect subsequent changes?
- Is passing the same object for two different parameters allowed?
- Does it take a structural snapshot before mutating?

A well-crafted generic signature does not replace the answers to these questions.

### 11.3. Exceptions and Partial Modifications

In `addFrom`, several elements may already have been added before the destination rejects a subsequent element. Taking a snapshot of the source does not create a transaction for the destination.

If an API requires “all-or-nothing” (atomic failure) semantics, you must design a suitable mechanism—for instance, building a brand-new collection before publishing it, or relying on transactional capabilities provided by the target data structure or system. Do not promise generic rollback for an arbitrary `Collection`.

### 11.4. Concurrency and Performance

A method accepting a broad collection interface must still state its assumptions clearly:

- Can the underlying data be modified concurrently?
- What are the iterator's consistency guarantees?
- How many traversal passes and how much auxiliary memory are required?
- Does positional indexing implicitly assume constant-time ($O(1)$) random access?

Wildcards do not synchronize access, do not take atomic concurrent snapshots, and do not prevent callbacks from mutating shared state.

## 12. Reading JDK Signatures to Learn API Design

Consider two simplified JDK method signatures:

```java
// API signatures for analysis, not a standalone program.
boolean addAll(Collection<? extends E> source);

static <T> void copy(
        List<? super T> destination,
        List<? extends T> source);
```

- `Collection.addAll` accepts elements from a source where every element can be treated as an `E`.
- `Collections.copy` links two lists via `T`, using `extends` for the source and `super` for the destination.

However, `Collections.copy` does not append elements to the end: it overwrites existing positions in the destination, so the destination list's `size()` must already be at least as large as the source list's `size()`. An `ArrayList` allocated with a large capacity but whose `size()` is `0` still has no elements at those positions to replace.

This demonstrates that a generic signature must always be read alongside **the method's behavioral specification**—you cannot simply spot a PECS pattern and guess the algorithm. [Collections.copy API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List))

## 13. Complete Program

Save as `FlexibleCollectionApiDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;

public final class FlexibleCollectionApiDemo {
    private static double sum(Iterable<? extends Number> source) {
        Objects.requireNonNull(source, "source");
        double total = 0;
        for (Number value : source) {
            total += Objects.requireNonNull(value, "element").doubleValue();
        }
        return total;
    }

    private static <T> List<T> editableCopy(
            Collection<? extends T> source) {
        Objects.requireNonNull(source, "source");
        return new ArrayList<>(source);
    }

    private static <T> void addFrom(
            Collection<? super T> destination,
            Collection<? extends T> source) {
        Objects.requireNonNull(destination, "destination");
        Objects.requireNonNull(source, "source");
        List<T> snapshot = new ArrayList<>(source);
        for (T value : snapshot) {
            destination.add(value);
        }
    }

    private static <T> void swap(List<T> values, int left, int right) {
        Objects.requireNonNull(values, "values");
        T leftValue = values.get(left);
        T rightValue = values.get(right);
        values.set(left, rightValue);
        values.set(right, leftValue);
    }

    private static <T, R> List<R> mapToList(
            Iterable<? extends T> source,
            Function<? super T, ? extends R> mapper) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(mapper, "mapper");
        List<R> result = new ArrayList<>();
        for (T value : source) {
            result.add(mapper.apply(value));
        }
        return result;
    }

    private static <K, V> Map<K, V> editableMapCopy(
            Map<? extends K, ? extends V> source) {
        Objects.requireNonNull(source, "source");
        return new LinkedHashMap<>(source);
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2, 3);
        List<Double> decimals = List.of(0.5, 1.5);
        System.out.println("Integer sum: " + sum(integers));
        System.out.println("Double sum: " + sum(decimals));

        List<Number> copy = editableCopy(integers);
        copy.add(2.5);
        System.out.println("Editable copy: " + copy);
        System.out.println("Source unchanged: " + integers);

        List<Number> destination = new ArrayList<>();
        addFrom(destination, integers);
        addFrom(destination, decimals);
        System.out.println("Mixed destination: " + destination);

        List<String> same = new ArrayList<>(List.of("a", "b"));
        addFrom(same, same);
        System.out.println("Same source and destination: " + same);

        List<Integer> pair = new ArrayList<>(List.of(10, 20));
        swap(pair, 0, 1);
        System.out.println("Swap: " + pair);

        Function<Number, String> label = number -> "n=" + number;
        List<CharSequence> labels = mapToList(integers, label);
        System.out.println("Mapped: " + labels);

        Map<String, Integer> originalMap = new LinkedHashMap<>();
        originalMap.put("A", 1);
        originalMap.put("B", 2);
        Map<CharSequence, Number> mapCopy = editableMapCopy(originalMap);
        mapCopy.put("C", 2.5);
        System.out.println("Map copy: " + mapCopy);
        System.out.println("Original map: " + originalMap);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:unchecked FlexibleCollectionApiDemo.java
java FlexibleCollectionApiDemo
```

The code has been verified against the Java 17 API baseline on a newer JDK with zero unchecked warnings.

Stdout:

```text
Integer sum: 6.0
Double sum: 2.0
Editable copy: [1, 2, 3, 2.5]
Source unchanged: [1, 2, 3]
Mixed destination: [1, 2, 3, 0.5, 1.5]
Same source and destination: [a, b, a, b]
Swap: [20, 10]
Mapped: [n=1, n=2, n=3]
Map copy: {A=1, B=2, C=2.5}
Original map: {A=1, B=2}
```

### Explanation of the Calls

- `sum` accepts two different numeric list types through its `Iterable<? extends Number>` parameter.
- `editableCopy` creates a new `List<Number>` from a `List<Integer>`; adding `2.5` modifies only the copy.
- `addFrom` populates a `Number` destination sequentially from an `Integer` source and a `Double` source.
- Taking a source snapshot allows the aliased call (`source == destination`) to terminate cleanly after appending the initial elements once.
- `swap` preserves the exact element type `T` when reading and writing list positions.
- `mapToList` accepts a `Number -> String` callback while consuming an `Integer` source and producing a `List<CharSequence>`.
- `editableMapCopy` widens the key and value types on the new copy without unsafely casting the original map to an incompatible generic type.

No raw types or unchecked collection casts are used to bypass compiler verification.

## 14. Step-by-Step Process for Designing a New Method

1. **Describe the behavior in plain language.** Does it read, add, replace in place, filter, or create a copy?
2. **Identify the minimal sufficient interface.** Do not require a concrete class just because one call site happens to use it.
3. **Assign a role to each parameter.** Is it a producer (source), a consumer (destination), or both read and write of the same type?
4. **Introduce named type parameters when positions are related.** Use `T`, `K`/`V`, or `T`/`R` to link parameters and return types that depend on one another.
5. **Apply wildcards on the right side.** Use `extends` for sources (producers); use `super` for destinations (consumers).
6. **Choose a clear return type.** Document whether the returned object is mutable, unmodifiable, a live view, or an independent copy.
7. **Specify non-type preconditions and invariants.** Document `null` handling, aliasing, optional operations, ordering, exceptions, and concurrency.
8. **Test both valid calls and calls that must be rejected.** Never weaken a signature to raw types just to silence a compiler error.
9. **Review the level of generality.** Remove type parameters or bounds that do not serve the method's behavior; retain meaningful domain constraints.

The formal rules governing parameterized types and wildcards are specified in [JLS Chapter 4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html).

## 15. Common Mistakes

| Design pattern | Problem | How to fix |
| --- | --- | --- |
| Accepting `ArrayList<T>` when only iterating | Couples callers to a specific implementation class | Choose `Iterable` or `Collection` as appropriate |
| Accepting `Collection<Number>` to read any numeric group | Rejects `Integer`/`Double` sources due to invariance | Use `? extends Number` |
| Accepting `Collection<Object>` to hold arbitrary inputs | Cannot accept parameterized collections like `List<String>` | Use an unbounded wildcard `<?>` or role-specific type parameters |
| Using a raw `Collection` and casting each element | Defers type errors to runtime (`ClassCastException`) | Maintain generic type relationships throughout |
| Declaring a destination that receives `T` as `? extends T` | Compiler cannot prove which subtype the collection holds for writing | Re-evaluate the destination role and use `? super T` |
| Using two independent wildcards without a linking `T` | Cannot guarantee type-safe element transfer between them | Use a generic method linking source and destination via `<T>` |
| Returning a wildcard type when producing a well-typed result | Makes the return value unnecessarily awkward for callers to use | Return `List<T>` or `Map<K, V>` as appropriate |
| Treating a wildcard as an immutability guarantee | Callers or underlying views can still mutate or clear data | Use explicit ownership copies or unmodifiable wrappers/factories |
| Iterating over a source while adding directly back into it | Can trigger `ConcurrentModificationException` or infinite loops | Forbid aliasing in the contract or take a deliberate snapshot |
| Promising atomic copying for arbitrary collections | Destination may fail after partially adding elements | Document failure state or design an explicit transactional mechanism |
| Ignoring callback side effects | Callback might mutate the source mid-iteration | Document callback constraints and choose an appropriate traversal strategy |

Raw types exist primarily for backward compatibility with legacy pre-generics code; they are not a tool for making modern APIs more general. [Raw Types](https://docs.oracle.com/javase/tutorial/java/generics/rawTypes.html)

## 16. Self-Check and Practice

### Questions

1. Why doesn't a method that only iterates over elements need to accept `ArrayList`?
2. Why is `? extends T` appropriate for a source that supplies elements?
3. Can a `? super Integer` destination accept a `Collection<Number>`?
4. Why must the same type variable `T` appear in both the source and destination parameters of `addFrom`?
5. What problem does the snapshot in `addFrom` solve, and what problems does it not solve?
6. Does the type `List<T>` guarantee that calling `set` will succeed at runtime?
7. Why is `Function<? super T, ? extends R>` more flexible than `Function<T, R>` in a transformation method?
8. Does returning `List<? extends T>` automatically make the returned list unmodifiable?
9. Does `Collections.copy` increase the size of the destination list?
10. What behavioral conditions need to be documented alongside generic type relationships?

### Exercises

- Write a method that reads only the lengths of `CharSequence` elements, allowing callers to pass a list of `String` or `StringBuilder`.
- Write a method that adds default integers into a `Collection<? super Integer>`; test it with `Integer`, `Number`, and `Object` destinations.
- Attempt a call that passes a `Double` source and an `Integer` destination to `addFrom`, and explain the resulting compiler error.
- Pass the same `ArrayList` instance as both source and destination to `addFrom`, and compare the result against the snapshot policy.
- Test `swap` with a mutable list that supports `set` and an unmodifiable list (`List.of(...)`); distinguish compile-time type safety from runtime contract violations.
- Write Javadoc for `editableCopy`, explicitly stating its mutability, shallow-copy nature, iteration order preservation, and `null` policy.
- Use `mapToList` to transform integers into a concrete result type while assigning the returned list to a broader interface type.
- Write a test verifying that adding an entry to the map returned by `editableMapCopy` does not modify the original source map.

### Reference Answers

1. It does not rely on any `ArrayList`-specific capabilities, so accepting an interface that provides iteration (`Iterable` or `Collection`) is sufficient.
2. Every element read from the source can be safely treated as a `T` without needing to know its exact runtime subtype.
3. Yes; a collection of `Number` can safely hold `Integer` elements.
4. `T` acts as the type bridge proving that every element produced by the source is assignable to what the destination accepts.
5. It prevents modifying the source while iterating over it when source and destination are aliased in our sample implementation; it does not provide thread safety, deep copying, or transactional rollback.
6. No; the underlying list implementation may still throw `UnsupportedOperationException` on mutation attempts.
7. The callback can accept any supertype of the input element type `T` and return any subtype of the target result type `R`.
8. No; wildcards restrict compile-time method calls through that reference, not the underlying object's mutability.
9. No; the destination list must already have at least as many elements (`size()`) as the source list.
10. Mutability permissions, `null` policies, aliasing rules, ordering guarantees, data ownership, failure/exception states, callback constraints, and concurrency assumptions.
