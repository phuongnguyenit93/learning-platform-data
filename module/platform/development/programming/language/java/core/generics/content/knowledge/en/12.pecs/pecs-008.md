# Reading the Signatures of `Collections.copy`, `addAll`, and `Comparator` Through the PECS Rule

When reading source code, Javadoc, or method signatures of the Java Collections Framework, we frequently encounter types like `? extends T` and `? super T`. Instead of memorizing each API, read signatures by **data flow**: which parameter **supplies** values of type `T` to the method, and which parameter **receives** or **consumes** those `T` values?

The **PECS — Producer Extends, Consumer Super** rule decodes these important signatures:

~~~java
// Signatures with package names and modifiers simplified for readability.
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src);

public boolean addAll(Collection<? extends E> c); // Collection<E>

public static <T> boolean addAll(
        Collection<? super T> c,
        T... elements); // Collections

public void sort(Comparator<? super E> c); // List<E>
~~~

These lines are **signatures for analysis**, not a standalone compilable program. `Collections.copy` copies into existing positions; `Collection.addAll` appends elements from a source collection; `Collections.addAll` takes varargs elements; `List.sort` consumes a `Comparator` capable of comparing elements in the list.

This lesson focuses on how to **accurately read each signature**, determine which type arguments can be passed, understand compile-time errors, and distinguish runtime conditions that generics do not guarantee.

## 1. Reviewing the Rules Needed to Read APIs

Standard Java generic classes and interfaces are **invariant** in their type arguments:

~~~java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // COMPILATION ERROR.
~~~

This is an **illustrative snippet** (requires `import java.util.*` and placement inside a class). Even though `Integer` is a subtype of `Number`, `List<Integer>` is not a subtype of `List<Number>`. If the assignment were accepted, other code could call `numbers.add(3.5)` and break the contract of `List<Integer>`.

Wildcards preserve type safety while still allowing subtype relationships in **one appropriate operational direction**:

| Kind | Meaning for element `T` | Core compile-time capability |
| --- | --- | --- |
| `? extends T` | Actual type is `T` or a **subtype** of `T` | Read elements as `T`; cannot add an arbitrary `T` |
| `? super T` | Actual type is `T` or a **supertype** of `T` | Add `T`; reading only guarantees `Object` |
| `T` without wildcard | Exact type argument, once `T` is determined | Can read/write `T` per the container's contract |

An `extends` view does not mean the collection is actually immutable. It can still allow removing or clearing; conversely, a `super` view does not guarantee the collection object is modifiable at runtime. PECS is primarily a **type-compatibility contract**.

We will read each method through four questions:

1. **What is `T` or `E`?** Is it declared on the class or on the method itself?
2. **Which parameter is the source, and which is the destination?**
3. **Which subtypes/supertypes are accepted?** Deduced from `extends` or `super`.
4. **At runtime, what does the method do to the collection structure?** Appending, overwriting, sorting, and preconditions all differ.

## 2. Decoding `Collections.copy`: `extends` Source, `super` Destination

Signature from the `java.util.Collections` utility class:

~~~java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src);
~~~

This is a **method signature for reading**, not an API to redeclare.

Reading from left to right:

- `<T>`: **the method's type parameter**. The compiler can infer `T` from passed arguments, or the caller can specify it explicitly.
- `dest: List<? super T>`: destination whose type argument is `T` or a supertype of `T`, so it can accept any element used as `T`.
- `src: List<? extends T>`: source whose type argument is `T` or a subtype of `T`, so reading source elements as `T` is safe.
- `void`: the method mutates `dest` and does not return a new list.
- `static`: called via `Collections.copy(dest, src)`, not on a `List` instance.

From the signature we deduce valid relationships: for instance, `Integer` elements can be transferred from `List<Integer>` to `List<Number>` or `List<Object>` without casting.

### 2.1. Runnable Example and Output

Create **`CollectionsCopyReadingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CollectionsCopyReadingDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(4, 5);
        List<Number> destination =
                new ArrayList<>(List.of(0, 0, 0));

        Collections.<Number>copy(destination, source);

        System.out.println("source = " + source);
        System.out.println("destination = " + destination);
        System.out.println("source size = " + source.size());
        System.out.println("destination size = " + destination.size());
    }
}
~~~

Compile and run with Java 17 or higher:

~~~bash
javac CollectionsCopyReadingDemo.java
java CollectionsCopyReadingDemo
~~~

Exact stdout:

~~~text
source = [4, 5]
destination = [4, 5, 0]
source size = 2
destination size = 3
~~~

`Collections.<Number>copy(...)` explicitly fixes `T = Number`. Then:

- `src` requires `List<? extends Number>`, so `List<Integer>` is valid.
- `dest` requires `List<? super Number>`, so `List<Number>` is valid.
- The method **overwrites elements at index 0 and 1** of the destination, leaving index 2 unchanged.
- It does not change the size of the destination collection and does not mutate the source.

You can also write `Collections.copy(destination, source)`; the compiler usually infers a suitable type in this example. The `<Number>` syntax simply makes the `extends`/`super` bounds visible when reading the signature.

### 2.2. Important Runtime Condition: Does Not Auto-Append

`Collections.copy` requires `dest.size() >= src.size()` right before copying. If the destination is shorter than the source, it throws `IndexOutOfBoundsException`, even when the two generic types are compatible.

An example that **intentionally triggers a runtime error**:

~~~java
List<Integer> src = List.of(1, 2);
List<Number> dest = new ArrayList<>();

Collections.copy(dest, src); // Compiles, but throws IndexOutOfBoundsException.
~~~

This snippet needs `import java.util.*` and placement in a class; the goal is solely to distinguish the runtime contract from type checking. In addition, `dest` must support updates via `set(index, value)`; an unmodifiable list can throw `UnsupportedOperationException`.

**Do not assume `copy` creates a new `List` copy.** It writes into an **already-existing destination list**. When you need to append elements to the end, use `addAll`; when you need a new collection, use a constructor such as `new ArrayList<Number>(source)`.

### 2.3. Forbidden Reverse-Direction Assignment

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<Number> numbers = new ArrayList<>(List.of(0, 0));

Collections.copy(numbers, integers); // Valid.
// Collections.copy(integers, numbers); // COMPILATION ERROR.
~~~

In the forbidden direction, the source could supply a `Double` through `List<Number>`, whereas the `List<Integer>` destination only accepts `Integer`. Wildcards block the unsafe operation **right at the call site**.

## 3. `Collection<E>.addAll(Collection<? extends E>)`: Collection Receives Data, Argument Is Source

Instance method signature on the `Collection<E>` interface:

~~~java
boolean addAll(Collection<? extends E> c);
~~~

This is a **simplified signature for analysis**. Identify what `E` is: `E` **belongs to the receiver's generic type**, meaning the object to the left of the dot when calling `destination.addAll(source)`.

Example:

~~~java
List<Number> destination = new ArrayList<>();
List<Integer> source = List.of(10, 20);

boolean changed = destination.addAll(source);
~~~

Here the receiver has type `List<Number>`, so `E = Number`. The parameter `c` becomes `Collection<? extends Number>` and can accept `List<Integer>`. Reading the signature:

- `destination` **receives additional** `Number` (and subtype) values.
- `source` **supplies** `Number`-compatible elements to the receiver.
- Because `source` is a producer parameter, the signature uses `extends`.
- The `boolean` return value indicates **whether the collection changed** due to the call, not the number of elements added.
- The method adds elements to the receiver according to the implementation's contract; for example, `List` typically appends at the end, whereas `Set` only retains non-duplicate elements per the set's equality rules.

Note carefully: in `Collection.addAll`'s signature, **there is no `? super E` parameter for the destination** because the receiver itself is already declared as `Collection<E>`. In `Collections.copy`, both source and destination are passed as parameters, so both directions are written explicitly.

### 3.1. Runnable Program: `List.addAll` and `Set.addAll`

Create **`CollectionAddAllDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class CollectionAddAllDemo {
    public static void main(String[] args) {
        List<Integer> integers = List.of(2, 4);
        List<Double> doubles = List.of(1.5, 2.5);
        List<Number> numbers = new ArrayList<>();

        boolean firstChange = numbers.addAll(integers);
        boolean secondChange = numbers.addAll(doubles);

        System.out.println("numbers = " + numbers);
        System.out.println("changes = " + firstChange + ", " + secondChange);

        Set<Number> unique = new LinkedHashSet<>();
        unique.add(2);
        boolean unchanged = unique.addAll(integers);

        System.out.println("unique = " + unique);
        System.out.println("unchanged = " + unchanged);
    }
}
~~~

Run:

~~~bash
javac CollectionAddAllDemo.java
java CollectionAddAllDemo
~~~

Exact stdout:

~~~text
numbers = [2, 4, 1.5, 2.5]
changes = true, true
unique = [2, 4]
unchanged = true
~~~

Here `unique` initially holds only `2`, so `addAll(integers)` adds `4` and returns `true`. The variable name `unchanged` can be misleading: the boolean from `addAll` reports **whether the collection changed**, not an 'unchanged' status. If `unique` already contained both `2` and `4`, the same call would return `false`.

### 3.2. When `addAll` Is Type-Incompatible

~~~java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = List.of(1, 2.5);

// integers.addAll(numbers); // COMPILATION ERROR.
~~~

The receiver `integers` has `E = Integer`, so the parameter must be `Collection<? extends Integer>`. `List<Number>` does not guarantee every element is an `Integer`. This explains why `numbers.addAll(integers)` is valid while the reverse direction is not.

### 3.3. Conditions Beyond PECS

- `List.addAll` typically appends elements at the end in the source's iterator order; `Set.addAll` may skip duplicates depending on `equals`/`hashCode` semantics.
- The receiver may not support modification and throw `UnsupportedOperationException` (e.g., `List.of(...)`).
- A collection may restrict `null` or specific element types at runtime even when the generic signature is satisfied.
- `Collection.addAll` specifies behavior when the source is the same collection being added to; do not assume every implementation handles self-addition safely, especially when non-empty.

## 4. `Collections.addAll(Collection<? super T>, T...)`: Destination Expressed with `super`

Java has **another API with the same name `addAll`**: a static method in the `java.util.Collections` utility class:

~~~java
public static <T> boolean addAll(
        Collection<? super T> c,
        T... elements);
~~~

Do not confuse it with `Collection<E>.addAll(Collection<? extends E>)`. The two methods have different **receivers and data directions**.

Analysis:

- `<T>`: a type parameter **of the method itself**, inferred from the arguments or chosen explicitly.
- `c: Collection<? super T>`: the collection is a **consumer** of `T` elements; accepts a collection of `T` or a supertype of `T`.
- `T... elements`: `T` values **supplied** to be added into the collection; this is varargs, not a `Collection<? extends T>`.
- `boolean`: returns true if the collection changed as a result of the call.

### 4.1. Runnable Program: Using `Collections.addAll`

Create **`CollectionsAddAllDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;

public class CollectionsAddAllDemo {
    public static void main(String[] args) {
        Collection<Number> numbers = new ArrayList<>();
        Collection<Object> objects = new ArrayList<>();

        boolean addedNumbers =
                Collections.<Number>addAll(numbers, 1, 2.5, 3L);
        boolean addedObjects =
                Collections.<Integer>addAll(objects, 7, 8);

        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);
        System.out.println("changed = " + addedNumbers + ", " + addedObjects);
    }
}
~~~

Compile and run:

~~~bash
javac CollectionsAddAllDemo.java
java CollectionsAddAllDemo
~~~

Stdout:

~~~text
numbers = [1, 2.5, 3]
objects = [7, 8]
changed = true, true
~~~

From the explicit notation `Collections.<Number>addAll(...)`:

- The values `1`, `2.5`, and `3L` are boxed into `Integer`, `Double`, and `Long` respectively, all compatible with `Number`.
- `Collection<Number>` is a valid `Collection<? super Number>`.
- In `Collections.<Integer>addAll(objects, 7, 8)`, the `Collection<Object>` destination fits because `Object` is a supertype of `Integer`.
- Printing the `Number` values via `toString()` yields `1`, `2.5`, `3` as shown in stdout.

In application code you can usually omit the explicit type argument and let the compiler infer it, e.g. `Collections.addAll(numbers, 1, 2.5, 3L)`. Here we wrote `<Number>` so learners can see its connection to `? super T`.

### 4.2. Comparing the Two `addAll` Methods Side by Side

| API | Call form | Who is the source? | Who is the destination? | Wildcard position | Return value |
| --- | --- | --- | --- | --- | --- |
| `Collection<E>.addAll(Collection<? extends E>)` | `dest.addAll(src)` | Collection parameter `src` | Receiver `dest` | `src` has `extends E` | `boolean` |
| `Collections.<T>addAll(Collection<? super T>, T...)` | `Collections.addAll(dest, a, b)` | Varargs values `a`, `b` | Collection parameter `dest` | `dest` has `super T` | `boolean` |

What they share is **data entering a destination collection type-safely**. What differs is that one API reads from a source collection, whereas the other receives individual elements via varargs.

Example of recognizing wrong syntax:

~~~java
List<Number> numbers = new ArrayList<>();
List<Integer> integers = List.of(1, 2);

numbers.addAll(integers); // Valid: instance addAll.
// Collections.addAll(numbers, integers); // Not the way to add individual Integers.
~~~

Uncommenting the last static line causes a **type error**: `Collections.addAll(numbers, integers)` tries to insert **the `List<Integer>` object itself as a single element** into `Collection<Number>`, whereas `List<Integer>` is not a `Number`. To use the static version, pass individual compatible elements: `Collections.addAll(numbers, 3, 4)`.

## 5. Why Is `Comparator<? super T>` Also Consumer Super?

`Comparator<T>` does not store a list. It represents an object with a method comparing **two `T` values**:

~~~java
@FunctionalInterface
public interface Comparator<T> {
    int compare(T left, T right);
}
~~~

This is a **simplified illustrative signature** of `Comparator`: in the real JDK, the interface also declares and inherits other methods. Do not recreate this interface when using the Java Collections Framework.

The comparison method **receives** two `T` values from the caller, so the comparator acts as a **consumer of `T` values**. If a comparator can compare `Number` in general, it can naturally compare `Integer` values, which are a subtype of `Number`.

Therefore, `List<E>.sort` declares:

~~~java
default void sort(Comparator<? super E> c);
~~~

and `Collections.sort` has the overload:

~~~java
public static <T> void sort(
        List<T> list,
        Comparator<? super T> c);
~~~

These are **signatures for analysis**, not standalone runnable class code. We read them as follows:

- The list stores exact values of type `E`/`T`.
- The comparator is **passed in to consume** elements from the list, so it accepts a comparator with type argument `E`/`T` or a **supertype**.
- Using `Comparator<E>` alone would be needlessly restrictive: a `Comparator<Number>` can handle `Integer`, yet could not be passed to `List<Integer>`.
- The reverse direction is unsafe: a `Comparator<Integer>` cannot be guaranteed to compare every element of a `List<Number>`, because the list may contain `Double`.

### 5.1. Runnable Program: `Comparator<Number>` Sorting `List<Integer>`

Create **`ComparatorSuperDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class ComparatorSuperDemo {
    public static void main(String[] args) {
        Comparator<Number> byNumericValue = (a, b) ->
                Double.compare(a.doubleValue(), b.doubleValue());

        List<Integer> integers = new ArrayList<>(List.of(9, 2, 5));
        integers.sort(byNumericValue);
        System.out.println("integers = " + integers);

        List<Number> mixed = new ArrayList<>(List.of(3.5, 1, 2.0));
        Collections.sort(mixed, byNumericValue);
        System.out.println("mixed = " + mixed);
    }
}
~~~

Run:

~~~bash
javac ComparatorSuperDemo.java
java ComparatorSuperDemo
~~~

Exact stdout:

~~~text
integers = [2, 5, 9]
mixed = [1, 2.0, 3.5]
~~~

At `integers.sort(byNumericValue)`, `E = Integer`, and `sort`'s parameter is `Comparator<? super Integer>`. `Comparator<Number>` fits because `Number` is a supertype of `Integer`. The method `compare(Number, Number)` can accept any `Integer`.

`Collections.sort(mixed, byNumericValue)` is also valid because a list of `Number` has an exact `Comparator<Number>`.

Note that the example comparator converts each number to `double` for comparison. That is only to illustrate the type relationship; for very large integers, `BigDecimal` with special precision requirements, or `NaN` values, do not use this comparison mechanically in real systems. The `Comparator<? super T>` signature guarantees **type compatibility**, not that the comparator defines a sensible ordering or is consistent with `equals`.

### 5.2. Invalid Example in the Opposite Direction

~~~java
Comparator<Integer> onlyIntegers = Integer::compare;
List<Number> mixed = new ArrayList<>(List.of(1, 2.5));

// mixed.sort(onlyIntegers); // COMPILATION ERROR.
~~~

This snippet needs `import java.util.*` and placement inside a class. `List<Number>` may contain `Double`, which `Comparator<Integer>` does not promise to handle. The compiler rejects it to prevent the comparator from being invoked with an incompatible value.

Similarly, `List<Integer>.sort` is allowed to accept a `Comparator<Object>` if that comparator has logic to compare any compatible `Object`. The type contract does not state that the comparison makes mathematical sense; that is the responsibility of the comparator implementation.

## 6. Comparison Table of the Three APIs by Data Flow

| API/signature | Where does data come from? | Where does data go? | Producer wildcard | Consumer wildcard |
| --- | --- | --- | --- | --- |
| `Collections.copy(List<? super T> dest, List<? extends T> src)` | `src` | `dest`, overwriting existing positions | `src: ? extends T` | `dest: ? super T` |
| `Collection<E>.addAll(Collection<? extends E> c)` | Parameter `c` | Receiver `this` | `c: ? extends E` | Destination is receiver `Collection<E>` |
| `Collections.addAll(Collection<? super T> c, T... elements)` | Varargs arguments | Parameter `c` | Typed `T...` values | `c: ? super T` |
| `List<E>.sort(Comparator<? super E> c)` | Elements of receiver `List<E>` | `c.compare` consumes two `E` values | List emits `E` values | `c: ? super E` |

Pay special attention to the fact that **a consumer does not have to be a collection**: a comparator, callback, or function taking an input of type `T` can all act as consumers.

For each signature, ask yourself: “Who does this object **read/supply** `T` to?” or “Who does this object **receive** `T` from?”. The `extends`/`super` bounds will become natural.

## 7. Reading Generic Type Inference Properly

Two kinds of type parameters are very easy to mix up:

- **`E` on `Collection<E>`/`List<E>`:** usually determined from the receiver's type, e.g. `List<Number> numbers` → `E = Number` in `numbers.addAll(...)`.
- **`T` on static methods `Collections.<T>copy` or `Collections.<T>addAll`:** inferred at **each call site** from the arguments, or explicitly specified by the caller.

Example:

~~~java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>(List.of(0, 0));

Collections.<Number>copy(numbers, integers); // Valid.
Collections.<Integer>copy(numbers, integers); // Also valid.
~~~

This is an **illustrative snippet needing `import java.util.*` and placement inside a class**.

With `T = Number`: source `List<Integer>` matches `List<? extends Number>`; destination `List<Number>` matches `List<? super Number>`.

With `T = Integer`: source `List<Integer>` matches `List<? extends Integer>`; destination `List<Number>` matches `List<? super Integer>`.

**`T` does not have to equal the exact type argument of either the source or the destination.** All that is needed is a `T` sitting simultaneously **above the source** and **below the destination** in the subtype hierarchy. That is why generic methods can express more combinations than fixed invariant types.

Conversely:

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<Number> numbers = List.of(3, 4.5);

// Collections.<Number>copy(integers, numbers); // COMPILATION ERROR.
// Collections.<Integer>copy(integers, numbers); // COMPILATION ERROR.
~~~

With `T = Number`, `List<Integer>` is not a `List<? super Number>` destination. With `T = Integer`, `List<Number>` is not a `List<? extends Integer>` source. Neither direction satisfies both type bounds simultaneously.

### Do Not Confuse Parameter Order

`Collections.copy(dest, src)` puts **destination first, source second**. This differs from some custom helper functions with signature `copy(source, destination)`. When using library APIs, read **parameter names and Javadoc**, rather than guessing from the name `copy`.

## 8. Three Intentionally Ill-Typed Snippets and How to Fix Them

### Ill-Typed 1 — Using `Collections.copy` to Populate an Empty Destination

~~~java
List<Integer> src = List.of(1, 2);
List<Number> dest = new ArrayList<>();

// Collections.copy(dest, src); // Compiles, but runtime IndexOutOfBoundsException.
dest.addAll(src); // Valid if the goal is to append both elements.
~~~

`Collections.copy` is an overwrite operation, whereas `addAll` is a collection-appending operation. Change the API according to **the needed behavior**, not just the generic bounds.

### Ill-Typed 2 — Using the `Collections.addAll` Overload to Add an Entire Collection

~~~java
List<Integer> src = List.of(1, 2);
List<Number> dest = new ArrayList<>();

// Collections.addAll(dest, src); // Wrong: List<Integer> is not a Number.
dest.addAll(src);                  // Valid: collection is the source.
Collections.addAll(dest, 3, 4);   // Valid: each element is a Number.
~~~

If you want to call `Collections.addAll` with elements from a source, you could iterate or convert to an array, though usually `dest.addAll(src)` is already right and simpler.

### Ill-Typed 3 — Using Too Narrow a Comparator for a List

~~~java
Comparator<Integer> integerOnly = Integer::compare;
List<Number> mixed = new ArrayList<>(List.of(1, 2.5));

// mixed.sort(integerOnly); // ERROR: comparator does not accept every Number.
Comparator<Number> numeric =
        (a, b) -> Double.compare(a.doubleValue(), b.doubleValue());
mixed.sort(numeric); // Valid.
~~~

Use a comparator compatible **at least with the entire element-type domain of the list**. Do not use unchecked casts to bypass compiler warnings.

## 9. Runtime Conditions Outside the Signature

Reading generic signatures accurately is necessary, yet **not sufficient** to guarantee a call succeeds at runtime.

### 9.1. `Collections.copy` Needs a Sufficiently Long, Modifiable Destination List

- `dest.size() < src.size()`: `IndexOutOfBoundsException`.
- `dest` does not support element updates: likely `UnsupportedOperationException`.
- `dest.size() > src.size()`: remaining elements in destination are untouched; size stays unchanged.
- The method **copies element references**, not deep clones of objects.

### 9.2. `addAll` Is Subject to the Destination Collection's Rules

- `ArrayList.addAll` appends elements and generally preserves source iteration order.
- `Set.addAll` may leave the collection unchanged if all elements already exist.
- An unmodifiable collection can throw `UnsupportedOperationException`.
- Some collections restrict `null` or incompatible elements by their own rules.
- The `boolean` indicates **whether the collection changed**; it is not a count.

### 9.3. `sort` Needs a Comparator with a Consistent Contract

`Comparator<? super T>` only asserts that the comparator **accepts objects of type `T`**. It does not automatically guarantee transitivity, ordering consistency, or `null` handling. A comparator violating its general contract can cause incorrect sort results or throw `IllegalArgumentException` in certain situations. `List.of(...)` does not support in-place sorting because the list is unmodifiable.

PECS solves **compile-time type relationships**; size, mutability, ordering, and comparator semantics belong to the API's runtime contract.

## 10. Further Reading: `Comparator` Can Both Consume and Produce a Result

A comparator **accepts** two `T` values into `compare(T, T)` and **returns** an integer representing ordering. It is a *consumer of T* even though it has an `int` output.

When using a method reference or lambda, the lambda's parameter types are typically inferred from the **target type**:

~~~java
Comparator<Number> compareNumbers = (a, b) ->
        Double.compare(a.doubleValue(), b.doubleValue());

List<Integer> integers = new ArrayList<>(List.of(5, 2, 9));
integers.sort(compareNumbers);
~~~

Parameters `a` and `b` are understood by the compiler as `Number` from the target type `Comparator<Number>`. When `List<Integer>.sort` calls the comparator, each `Integer` is still a valid `Number`. There is no need to create a new `Comparator<Integer>`.

If implementing a method that accepts a comparator:

~~~java
static <T> void sortItems(List<T> items, Comparator<? super T> ordering) {
    items.sort(ordering);
}
~~~

This is an **illustrative method needing `import java.util.*`**. `items` keeps exact type argument `T` so its elements can be sorted, while `ordering` is declared consumer-super to accept a comparator of `T` or a supertype.

This demonstrates that PECS applies to **interfaces taking parameters**, not exclusively collections.

## 11. Exercise Table: Predict Compilability

Assume the following variables are declared inside a method with `import java.util.*;`:

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<Double> doubles = new ArrayList<>(List.of(2.5, 3.5));
List<Number> numbers = new ArrayList<>(List.of(0, 0));
List<Object> objects = new ArrayList<>();
Comparator<Number> numberComparator =
        (a, b) -> Double.compare(a.doubleValue(), b.doubleValue());
Comparator<Integer> integerComparator = Integer::compare;
~~~

Analyze each expression **independently**, without chaining expressions into a single program and reasoning about later runtime state:

| Expression | Compiles? | Reason |
| --- | --- | --- |
| `Collections.copy(numbers, integers);` | Yes | Source `Integer`, destination `Number`; PECS matches |
| `Collections.copy(objects, integers);` | Yes | `Object` destination also accepts `Integer` |
| `Collections.copy(integers, numbers);` | No | `Number` source is not guaranteed to be `Integer` |
| `numbers.addAll(integers);` | Yes | Receiver has `E = Number`, source `? extends Number` |
| `integers.addAll(numbers);` | No | Receiver has `E = Integer`, source is not guaranteed to be `Integer` |
| `Collections.addAll(numbers, 3, 4.5);` | Yes | There exists a `T` compatible with `Number` and the values |
| `Collections.<Number>addAll(objects, 3, 4.5);` | Yes | `Object` is a supertype of `Number` |
| `Collections.<Number>addAll(integers, 3);` | No | `Integer` is not a supertype of `Number` |
| `integers.sort(numberComparator);` | Yes | `Comparator<Number>` can consume `Integer` |
| `numbers.sort(integerComparator);` | No | Comparator is too narrow for every `Number` |
| `Collections.sort(integers, numberComparator);` | Yes | `Comparator<? super Integer>` accepts `Comparator<Number>` |
| `Collections.copy(numbers, doubles);` | Yes | `Double` is a subtype of `Number` |

Special note: for `Collections.copy(objects, integers)`, the call **compiles**, yet `objects` is initially empty so it will throw `IndexOutOfBoundsException` if executed in its declared state. That is not a generics error.

### Ask Yourself Before Checking the Compiler

1. Does `Collection.addAll` take a source collection or varargs elements?
2. Why does `Collections.copy` use `super` for the destination but `extends` for the source?
3. Why can `Comparator<Number>` sort `List<Integer>`, while `Comparator<Integer>` cannot sort `List<Number>`?
4. When does `Collections.copy` compile fine yet still fail at runtime?
5. Why is a comparator that stores no data still considered a consumer under PECS?

**Core answers:** (1) `Collection.addAll` takes a `Collection<? extends E>`; (2) source emits `T`, destination receives `T`; (3) a supertype comparator can accept subtypes, whereas a subtype comparator cannot accept every supertype; (4) destination lacks slots or does not permit modification; (5) the `compare` method has input parameters of type `T`.

## 12. Short Checklist When Encountering an Unfamiliar Generic Signature

Do not just look at `extends` or `super`. Clarify:

1. **Where is the type parameter declared?** On the class `Collection<E>`, or on the method `static <T>`?
2. **In which direction does the parameter use values of that type?** Reading values out from a source or passing values into a consumer?
3. **Do the wildcard bounds match the data flow?** Producer `? extends T`, consumer `? super T`.
4. **Are there runtime conditions beyond data types?** `copy` needs destination size, `addAll` needs a collection permitting additions, `sort` needs a comparator with a consistent contract.
5. **Is the API instance or static?** `dest.addAll(src)` is completely different from `Collections.addAll(dest, item...)` despite sharing the method name.

These three signature groups show that PECS is not a slogan to apply mechanically, but a method for **reading data responsibilities from type signatures**. `Collections.copy` clearly illustrates both producer and consumer sides; `Collection.addAll` shows an `extends` source alongside a receiver already typed with `E`; `Collections.addAll` puts a `super` destination to receive varargs; `Comparator<? super T>` shows that a consumer can also be an object receiving two values to compare. Reading these relationships accurately helps you write flexible APIs that remain strictly checked by the compiler.
