# Using `Collection<T>` Instead of Arrays When Appropriate in Java Generics

## 1. Why Choose Between Collection and Array?

When learning Java Generics, a common scenario is wanting to store multiple elements of the same type `T`:

```java
class Group<T> {
    // Invalid:
    // private T[] items = new T[10];
}
```

Or wanting to store multiple lists of strings:

```java
// Invalid:
java.util.List<String>[] groups = new java.util.List<String>[3];
```

Both expressions `new T[10]` and `new List<String>[3]` hit the restriction of **generic array creation**. The type variable `T` and the parameterized type `List<String>` are not *reifiable* component types suitable for directly creating an array.

If the problem only needs a collection of elements, we can often replace it with:

```java
class Group<T> {
    private final java.util.Collection<T> items =
            new java.util.ArrayList<>();
}
```

And replace "an array of string lists" with:

```java
java.util.List<java.util.List<String>> groups =
        new java.util.ArrayList<>();
```

Both new examples are valid. The compiler preserves generic constraints in source code without needing to create an array with a non-reifiable component type.

**Core principle of this lesson:** Choose the abstraction that expresses the required operations first. If you only need adding, iterating, counting, or membership testing, `Collection<T>` may suffice. If you need order and indexed access, use `List<T>`; if you need uniqueness, `Set<T>`; if you need a queue, `Queue<T>`; and if you genuinely need array semantics, a runtime component class, or an API requiring an array, continue using arrays with an appropriate creation strategy.

`Collection<T>` is not a "trick" to make Generics reifiable. It is a data design approach that usually **fits Java's generic type system better** and eliminates the need to create arrays that the JVM cannot fully check.

## 2. Differences to Keep in Mind When Replacing an Array with a Collection

A `String[]` array retains component type `String` at runtime; it allows `Object[]` aliases, yet the JVM checks every write to reject `Integer` with `ArrayStoreException`. `Collection<String>` relies on **compile-time generic checks**; at runtime, `ArrayList<String>` and `ArrayList<Integer>` share the same `ArrayList` class due to erasure. Raw aliases can still break the contract.

| Decision | Array | Generic collection |
| --- | --- | --- |
| Element access | By index, has `length` | Iteration/iterator/`size()`; only `List` has `get(index)` |
| Size | Fixed after creation | Depends on implementation; may support add/remove |
| Element type | Runtime component class and store check | Compiler tracks type argument in typed APIs |
| Ordering | By index | `Collection` does not promise order; `List` does |
| Primitives | `int[]` directly | `Collection<Integer>` involves boxing |
| Generic instantiation | Cannot write `new T[n]` | Can write `new ArrayList<T>()` |

Switch to a Collection when business operations need a **collection of generic elements** rather than a runtime array class. Doing so does not make generics reifiable or collections automatically mutable; you must still choose the right implementation, ownership, and null policy.

## 3. Choosing the Right Interface: `Collection` Does Not Mean `List`

`java.util.Collection<E>` is the base interface for many collection types. Common operations include:

- `add`, `remove`, `contains`, `size`, `isEmpty`;
- iterating with enhanced `for`;
- iterator, `stream`, `toArray`;
- bulk operations such as `addAll`, `removeAll`, `retainAll`.

However, `Collection` **does not have `get(int)`**, does not guarantee maintaining element order across all implementations, and does not guarantee that every collection supports `add` or `remove`.

Specialized interfaces:

| Actual need | Type to consider | Key point |
|---|---|---|
| A collection of elements to iterate over or count | `Collection<T>` | Does not require index/order in the API |
| Order, positional access, duplicates allowed | `List<T>` | Has `get(int)` and element order |
| No duplicate elements under equality | `Set<T>` | No index; ordering depends on implementation |
| Adding and retrieving elements in queue order | `Queue<T>`/`Deque<T>` | Appropriate head/tail operation contracts |
| Mapping from keys to values | `Map<K,V>` | `Map` **does not extend** `Collection` |
| Array with a true runtime component type | `T[]` in a safe creation context | Use when an array contract is needed |

With `Collection<T>`, an API accepts many kinds of implementations. That is an advantage when an algorithm only needs minimal capabilities. If the algorithm must call `get(i)`, do not cast `Collection` down to `List` without justification; require `List<T>` directly in the signature.

## 4. Runnable Example: Writing a Generic Container Using Collection

Create the file **`GenericCollectionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;

public class GenericCollectionDemo {

    static final class Bag<T> {
        private final Collection<T> elements = new ArrayList<>();

        void add(T value) {
            elements.add(value);
        }

        int size() {
            return elements.size();
        }

        Collection<T> snapshot() {
            return new ArrayList<>(elements);
        }
    }

    public static void main(String[] args) {
        Bag<String> names = new Bag<>();
        names.add("Lan");
        names.add("Mai");

        System.out.println(names.size());

        for (String name : names.snapshot()) {
            System.out.println(name);
        }

        Bag<Integer> points = new Bag<>();
        points.add(8);
        points.add(9);

        System.out.println(points.size());
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac GenericCollectionDemo.java
java GenericCollectionDemo
```

Stdout:

```text
2
Lan
Mai
2
```

Points to analyze:

1. `Bag<T>` cannot directly allocate `new T[n]`, yet it can declare a `Collection<T>` field and assign an `ArrayList<T>`.
2. When using `Bag<String>`, the compiler requires `add` to take `String`; when using `Bag<Integer>`, it requires `Integer`.
3. `snapshot()` creates a **new collection** so callers do not directly hold the internal collection; the example does not claim that element objects are deep-copied.
4. The `for-each` loop works on `Collection<T>` because collections support `Iterable<T>`.
5. `ArrayList` preserves insertion order, so the example's stdout is deterministic. If the implementation changes to `HashSet`, you should not assume the same print order.

The example uses `Collection` for storage instead of a generic array without needing an unchecked cast.

### Why Not Write `Collection<T> elements = new Collection<>();`?

`Collection` is an **interface** and cannot be instantiated directly. We choose a concrete implementation:

```java
Collection<T> elements = new ArrayList<>();
```

Or if a unique set is needed:

```java
Collection<T> elements = new java.util.HashSet<>();
```

If order matters, use `ArrayList` or an ordered implementation; if only uniqueness is needed, consider `Set`.

## 5. Key Problem: Replacing `List<String>[]` with `List<List<String>>`

Suppose you need several groups, each holding multiple names. Direct array creation is invalid:

```java
// Intentionally does not compile:
List<String>[] groups = new List<String>[3];
```

Model it as a list containing lists of strings:

```java
List<List<String>> groups = new ArrayList<>();
```

This is a **List of Lists**, where both generic levels are checked by the compiler in normal code.

File **`NestedListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class NestedListDemo {
    public static void main(String[] args) {
        List<List<String>> groups = new ArrayList<>();

        groups.add(new ArrayList<>(List.of("An", "Binh")));
        groups.add(new ArrayList<>(List.of("Chi")));

        groups.get(1).add("Dung");

        System.out.println(groups.size());
        System.out.println(groups.get(0).get(1));

        for (List<String> group : groups) {
            System.out.println(String.join(", ", group));
        }
    }
}
```

Run:

```bash
javac NestedListDemo.java
java NestedListDemo
```

Stdout:

```text
2
Binh
An, Binh
Chi, Dung
```

Why this is usually a good design:

- No `new List<String>[n]` needed.
- The outer list maintains group order and provides `get(index)`.
- The inner list has type `List<String>`; the compiler prevents inserting `Integer` into a group in normal typed code.
- Adding/removing groups is not limited by a pre-allocated number of array slots.
- You can swap the outer `ArrayList` for another `List` implementation without changing most client code.

**Note:** Using `Collection<Collection<String>>` would be overly general if the requirement is accessing groups and students by index. Choose `List<List<String>>` when two-level positional access is needed.

## 6. `Collection<T>` Is the Right Choice for Traversal-Only APIs

Do not accidentally impose an "array" requirement when a function only needs to iterate over elements.

Instead of:

```java
// Valid declaration, yet ties the API to an array.
static int countNames(String[] names) {
    return names.length;
}
```

You can use:

```java
static int countNames(Collection<String> names) {
    return names.size();
}
```

When you also want to accept subtypes, wildcards can help. For example:

```java
static void printAll(Collection<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

These are **standalone method snippets for comparison**; place them inside an appropriate class and import `java.util.Collection`.

A method taking `Collection<?>` expresses "I only read elements of an unknown type." If you need to process each element as a specific type, keep a parameterization like `Collection<String>` or use a suitable bound/callback.

However, **do not use `Collection<T>` merely because everything is a collection**. If code needs index-based sorting or frequent access to the 10th element, `List<T>` is the better contract.

## 7. A Generic Utility Without `T[]`

Create the file **`CollectionUtilityDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class CollectionUtilityDemo {

    static <T> List<T> copyOf(Collection<? extends T> source) {
        return new ArrayList<>(source);
    }

    static <T> void addAll(
            Collection<? super T> target,
            Collection<? extends T> source) {
        for (T value : source) {
            target.add(value);
        }
    }

    public static void main(String[] args) {
        List<String> words = copyOf(List.of("red", "blue"));
        List<Object> output = new ArrayList<>();

        addAll(output, words);
        addAll(output, List.of(10, 20));

        System.out.println(words);
        System.out.println(output);
    }
}
```

Commands:

```bash
javac CollectionUtilityDemo.java
java CollectionUtilityDemo
```

Stdout:

```text
[red, blue]
[red, blue, 10, 20]
```

The example illustrates the **PECS** rule (*Producer Extends, Consumer Super*):

- `Collection<? extends T> source`: elements read from the source can be used as `T`.
- `Collection<? super T> target`: the target can accept elements of type `T`.
- `copyOf` returns a new `List<T>`, without needing `T[]` anywhere.

When calling `addAll(output, words)`, the target parameter `Collection<Object>` can accept `String`; generic constraints let the compiler verify the valid relationship. Accepting `Collection` lets callers pass many container kinds without temporarily converting to an array.

### Why Not Use `Collection<T>` for Both Source and Target?

The declaration:

```java
static <T> void addAll(Collection<T> target, Collection<T> source)
```

cannot accept every valid pair permitted by `<? super T>` and `<? extends T>`. For instance, `Collection<Object>` is a valid target for `Collection<String>`, yet the two containers do not share the **same** type argument `T`.

Bounded wildcards preserve safety and reduce casting requirements. Still, do not apply PECS mechanically: if a parameter both reads and writes an exact `T`, `Collection<T>` may be more appropriate.

## 8. If You Want Unique Elements, Use `Set<T>`

An array can hold duplicate copies; so can a `List`. If domain logic wants unique elements by `equals`/`hashCode`, choose `Set<T>`.

Example **`SetInsteadOfArrayDemo.java`**:

```java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

public class SetInsteadOfArrayDemo {
    static <T> int uniqueCount(Collection<? extends T> source) {
        Set<T> unique = new LinkedHashSet<>(source);
        return unique.size();
    }

    public static void main(String[] args) {
        System.out.println(uniqueCount(
                java.util.List.of("A", "B", "A")));
        System.out.println(uniqueCount(
                java.util.List.of(2, 2, 3, 4)));
    }
}
```

Compile/run:

```bash
javac SetInsteadOfArrayDemo.java
java SetInsteadOfArrayDemo
```

Stdout:

```text
2
3
```

`LinkedHashSet` is used to support insertion-based iteration order when needed, though the program only prints the size. `HashSet`, on the other hand, provides no corresponding iteration-order guarantee.

If an API must access elements by position, `Set` cannot replace `List`. Choose the abstraction from the actual properties of the data.

## 9. When Is `Collection<T>` Not Enough?

This is an important boundary on the advice "use Collection instead of arrays."

### 9.1. Needing Index Access

```java
List<String> names = new ArrayList<>();
names.add("An");
String first = names.get(0);
```

`List` has `get(int)`, whereas `Collection` does not. Do not turn a `Collection<String>` into `List<String>` via a cast if the source could be a `HashSet`.

### 9.2. Needing Fixed Size and Empty Slots

A `String[3]` array immediately has **three slots**, all holding the default value `null`. `new ArrayList<String>(3)` only sets the **initial capacity**, without creating three elements.

```java
List<String> slots = new ArrayList<>(3);
System.out.println(slots.size()); // 0
```

If you want three actual positions:

```java
List<String> slots = new ArrayList<>(
        java.util.Arrays.asList(null, null, null));
System.out.println(slots.size()); // 3
```

These are illustrative snippets; place them inside an appropriate method. A list of size 3 does not automatically become a fixed-size structure unless the API actively restricts modifications.

If you need a container with a fixed slot count or hardware-close data layout, arrays may still be suitable.

### 9.3. Needing Primitive Arrays

`int[]` and `double[]` store primitive values directly. `Collection<Integer>` and `Collection<Double>` use wrapper objects under Java Generics' type system with autoboxing/unboxing where appropriate.

For heavy numerical computation, primitive arrays can reduce object and memory overhead; however, actual performance should be measured with benchmarks rather than deduced absolutely from syntax.

### 9.4. Needing Java/Native APIs Requiring Arrays

Some APIs accept or return `String[]`, `byte[]`, `char[]`, or `int[]` because their contracts are designed around arrays. In those cases, supply the right array type instead of trying to change third-party signatures.

### 9.5. Needing a Runtime Component Type

If a program genuinely must know the component class at runtime, arrays carry useful information via `array.getClass().getComponentType()`. A generic `Collection<T>` does not carry `T` in the same way.

**Conclusion:** Use `Collection<T>` to avoid non-reifiable arrays when the problem permits, **not to eliminate all arrays** from Java.

## 10. Distinguishing `ArrayList` Size from Array Length

A very common mistake when replacing an array with a collection:

```java
int[] array = new int[5];          // array.length == 5.
ArrayList<Integer> list = new ArrayList<>(5);
                                   // list.size() == 0.
```

In `ArrayList<>(5)`, `5` is the initial capacity for the implementation, which does not mean five elements were created. Therefore:

```java
// Intentionally causes a runtime error while the list is still empty:
list.set(0, 10);
```

is out of bounds for the list's valid index range and throws `IndexOutOfBoundsException`.

If you want slots initialized with a default value:

```java
List<Integer> list = new ArrayList<>(
        java.util.Collections.nCopies(5, 0));
```

After that, you can `set` within valid index bounds. `Collections.nCopies` creates a List with the specified number of elements; the `ArrayList` constructor copies them into a modifiable list.

Unlike primitive array `new int[5]`, `List<Integer>` has no automatic default zeros when only calling the capacity constructor.

## 11. Runnable File: Contrasting `length`, `size()`, and `get()`

Create **`ArrayVsListSizeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ArrayVsListSizeDemo {
    public static void main(String[] args) {
        int[] array = new int[3];
        ArrayList<Integer> empty = new ArrayList<>(3);

        System.out.println(array.length);
        System.out.println(empty.size());

        List<Integer> filled =
                new ArrayList<>(Collections.nCopies(3, 0));

        filled.set(1, 7);
        array[1] = 7;

        System.out.println(filled);
        System.out.println(array[1]);
    }
}
```

Compile and run:

```bash
javac ArrayVsListSizeDemo.java
java ArrayVsListSizeDemo
```

Stdout:

```text
3
0
[0, 7, 0]
7
```

Self-check question: Why does `new ArrayList<>(3)` not pre-create three elements? Because this constructor only provides the **initial capacity**; the actual element count is a separate concept returned by `size()`.

## 12. Preserving Contracts When Exposing a Collection from a Class

A field of type `Collection<T>` or `List<T>` may hold a mutable collection. If a getter returns the internal collection directly, callers can add/remove elements and break domain invariants.

There are several options:

- **Return a mutable copy** such as `new ArrayList<>(elements)`: caller mutations to the copy do not alter the internal collection; elements still share object references if they are mutable.
- **Return an unmodifiable snapshot** such as `List.copyOf(elements)` when `null` restrictions and ordering are acceptable.
- **Return an unmodifiable view** such as `Collections.unmodifiableList(list)`: prevents modification through the view, yet can reflect changes made via other references to the backing list.
- **Returning an interface meant to be read-only** such as `Collection<T>` is not enough to guarantee immutability, because `Collection` declares mutating methods and the implementation may support them.

Choosing a good abstraction and protecting ownership are **two separate decisions**. Merely changing `T[]` to `Collection<T>` does not automatically encapsulate internal state.

## 13. Runnable Example: Readable Snapshot That Cannot Be Modified

File **`SnapshotCollectionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class SnapshotCollectionDemo {
    static class Registry<T> {
        private final List<T> items = new ArrayList<>();

        void register(T value) {
            items.add(value);
        }

        Collection<T> snapshot() {
            return List.copyOf(items);
        }
    }

    public static void main(String[] args) {
        Registry<String> registry = new Registry<>();
        registry.register("A");

        Collection<String> oldSnapshot = registry.snapshot();
        registry.register("B");

        System.out.println(oldSnapshot);
        System.out.println(registry.snapshot());

        try {
            oldSnapshot.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("UnsupportedOperationException");
        }
    }
}
```

Run:

```bash
javac SnapshotCollectionDemo.java
java SnapshotCollectionDemo
```

Stdout:

```text
[A]
[A, B]
UnsupportedOperationException
```

`List.copyOf` is a **shallow snapshot** and rejects `null`. Each call to `snapshot()` in the example captures the new collection state; the old snapshot does not automatically update when `registry` receives more elements.

With mutable elements, inner objects can still change state through external references. If deep immutability is desired, you must design corresponding copying or immutable element mechanisms.

## 14. Converting from `Collection<T>` to `T[]` When Genuinely Needed

In many cases, the best pattern is to **store data in a collection**, and only create an array at the boundary of an API that requires an array.

For instance, `Collection.toArray(IntFunction<T[]>)` lets the caller supply an array constructor reference with a concrete runtime component type.

Create the file **`CollectionToArrayDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;

public class CollectionToArrayDemo {

    static <T> T[] asArray(
            Collection<? extends T> input,
            java.util.function.IntFunction<T[]> factory) {
        return input.toArray(factory.apply(0));
    }

    public static void main(String[] args) {
        Collection<String> words =
                new ArrayList<>(List.of("A", "B"));

        String[] direct = words.toArray(String[]::new);
        String[] fromHelper = asArray(words, String[]::new);

        System.out.println(Arrays.toString(direct));
        System.out.println(Arrays.toString(fromHelper));
        System.out.println(direct.getClass()
                .getComponentType().getName());
    }
}
```

Compile and run with Java 17+:

```bash
javac CollectionToArrayDemo.java
java CollectionToArrayDemo
```

Stdout:

```text
[A, B]
[A, B]
java.lang.String
```

**Analyzing both conversions:**

- `words.toArray(String[]::new)` invokes the `Collection.toArray(IntFunction<T[]>)` overload, available since Java 11. The constructor reference specifies a `String[]` array with runtime component class `String`.
- `asArray` passes an array created by the factory into the `toArray(T[])` overload. The created array has length 0; `toArray`'s contract permits allocating a new array when the size is insufficient. On return, the result is still `String[]` with the right component type.
- There is no need to write `new T[n]` inside the generic helper.

The helper uses `factory.apply(0)` as an illustrative technique compatible with the `toArray(T[])` overload. In code purely meant to convert a collection to an array on JDK 17+, the direct call `input.toArray(factory)` is usually more concise.

**Do not infer** that you can create `List<String>[]` with `List<String>[]::new`: the component type of an array constructor reference must still satisfy array creation rules. A type witness or factory does not turn a non-reifiable parameterized type into a reifiable one.

## 15. Converting from an Array to a Collection

Conversely, when receiving an array with a concrete element type, you can create a collection from it.

Familiar approaches:

```java
String[] source = {"A", "B"};

List<String> backedView = java.util.Arrays.asList(source);

List<String> independent =
        new java.util.ArrayList<>(java.util.Arrays.asList(source));

List<String> unmodifiable =
        List.copyOf(java.util.Arrays.asList(source));
```

This is an illustrative snippet to place in a method importing `java.util.List`.

These approaches **are not equivalent**:

- `Arrays.asList(source)` produces a **fixed-size list backed by the array**: calling `set` on the list affects the array, and changing an array element reflects in the list. You cannot add or remove through this list.
- `new ArrayList<>(...)` creates a resizable list whose element references are copied from the input data.
- `List.copyOf(...)` creates a list that cannot be modified via standard APIs and disallows `null` elements; it is a structural snapshot.

Additionally, be careful with **primitive arrays**:

```java
int[] values = {1, 2, 3};
List<int[]> oneElement = java.util.Arrays.asList(values);
```

`Arrays.asList(int[])` treats the entire `int[]` as **a single reference element**, rather than turning primitive `int`s into three `Integer`s.

When you need `List<Integer>`, you can use `Arrays.stream(values).boxed().toList()` on Java 17; the result of `Stream.toList()` is unmodifiable. If a mutable list is needed, collect into an `ArrayList` with a collector or copy it afterward.

## 16. Practice Exercise: Converting Arrays and Lists with Proper Semantics

File **`ArraysAsListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ArraysAsListDemo {
    public static void main(String[] args) {
        String[] source = {"A", "B"};

        List<String> backed = Arrays.asList(source);
        List<String> copied = new ArrayList<>(backed);

        source[0] = "X";

        System.out.println(backed);
        System.out.println(copied);

        backed.set(1, "Y");
        System.out.println(Arrays.toString(source));

        copied.add("C");
        System.out.println(copied);
    }
}
```

Run:

```bash
javac ArraysAsListDemo.java
java ArraysAsListDemo
```

Stdout:

```text
[X, B]
[A, B]
[X, Y]
[A, B, C]
```

After `source[0] = "X"`, `backed` reflects the change because it is an array-backed view, whereas `copied` remains structurally independent. `backed.set(1, "Y")` updates the underlying array element directly. `copied.add("C")` succeeds because `ArrayList` is resizable.

The example highlights that "replacing an array with a collection" requires considering **ownership**, **resizability**, and **coupling to the original data**, not just generic syntax.

## 17. When Read-Only Input Is Needed, Use Wildcards and Clear Contracts

A generic API that only needs to read objects of type `Number` can declare:

```java
static double total(java.util.Collection<? extends Number> numbers) {
    double sum = 0;
    for (Number value : numbers) {
        sum += value.doubleValue();
    }
    return sum;
}
```

This function accepts `Collection<Integer>`, `Collection<Double>`, or collections whose elements are subtypes of `Number`, without needing to convert to `Number[]`.

This is an **illustrative method snippet**; place it in a class when compiling. With a `? extends Number` parameter, you cannot arbitrarily add a `Number` to the collection because the concrete element type could be `Integer`, `Double`, etc.

Similarly, if you need to write `Integer` into a destination accepting supertypes:

```java
static void addScores(
        java.util.Collection<? super Integer> target) {
    target.add(10);
    target.add(20);
}
```

`Collection<? super Integer>` can accept `Collection<Integer>`, `Collection<Number>`, or `Collection<Object>` under generic compatibility rules.

A major advantage of collections + wildcards is expressing the capability to **read from a producer** or **write to a consumer** without creating covariant array aliases that are easily misused.

## 18. `Object[]` Is Internal Storage, Not a Public `T[]` Array

```java
Object[] data = new Object[]{"A", "B"};
// String[] bad = (String[]) data; // ClassCastException at runtime.
```

Even if both current elements are `String`, the actual array still has component class `Object`; casting the whole array **does not** create `String[]`. You can keep `private Object[]` as backing storage for a `Store<T>` structure when every write path is controlled by `T`, cast individual elements only where the invariant is clear, and never expose the array externally. If low-level storage is unnecessary, `ArrayList<T>` is usually simpler.

The dedicated lesson on `Object[]` covers scoping `@SuppressWarnings("unchecked")`, checking `size`, and raw/reflection/alias paths that break invariants. For APIs needing a real array, require a `T[]` factory or class token instead of returning `Object[]` disguised as `T[]`.

## 19. Collections Can Replace Generic Varargs When Only Iteration Is Needed

Varargs `List<T>... values` are passed as an array, with a generic element type that is usually non-reifiable; careless methods risk heap pollution. If the requirement is merely **iterating over multiple string lists**, replace it with:

```java
static void showGroups(Collection<? extends List<String>> groups) {
    for (List<String> group : groups) {
        System.out.println(group.size());
    }
}
```

Calling `showGroups(List.of(List.of("A"), List.of("B","C")))` is type-safe and does not force the caller to create an array of `List<String>`. If an API intentionally uses varargs, audit the body and only apply `@SafeVarargs` when permitted by the language and when the implementation is genuinely safe. The focus here is **choosing the input abstraction**, not all varargs rules.

## 20. Collections Do Not Make Generic Types Reifiable

One misconception to avoid is thinking `Collection<T>` "retains" `T` as a runtime property of each instance. In reality:

```java
java.util.Collection<String> words =
        new java.util.ArrayList<>();

java.util.Collection<Integer> numbers =
        new java.util.ArrayList<>();
```

The two variables have different static types, yet both runtime objects are `ArrayList`. Java Generics still use erasure.

Therefore:

```java
words.getClass() == numbers.getClass()
```

is `true` when both are created as above.

Using `Collection<T>` increases **compile-time safety** by letting the compiler track type arguments when code is normally checked. It does not completely prevent heap pollution from raw types, unchecked casts, or unsafe reflection data.

If the program needs to verify at runtime that a collection contains only `String`s, you must inspect the data (for example iterating over `Collection<?>` and using `instanceof String`) or create a verified copy with a `String.class` token under an explicit contract.

## 21. When Receiving a Collection from an Untrusted Source

If reading from a legacy API, reflection, or external data, you cannot simply cast:

```java
// Intentionally unsafe:
@SuppressWarnings("unchecked")
Collection<String> names = (Collection<String>) unknown;
```

and conclude the elements are already `String`. The runtime cast only verifies that the object is a `Collection` of the matching raw type; it does not verify `String`.

A clearer approach is to validate each element and place it into a new collection.

File **`ValidatedCollectionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class ValidatedCollectionDemo {

    static <T> List<T> verifiedCopy(
            Collection<?> input, Class<T> elementType) {
        List<T> result = new ArrayList<>();

        for (Object element : input) {
            result.add(elementType.cast(element));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> valid = verifiedCopy(
                List.of("A", "B"), String.class);

        System.out.println(valid);

        try {
            verifiedCopy(List.of("A", 10), String.class);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Commands:

```bash
javac ValidatedCollectionDemo.java
java ValidatedCollectionDemo
```

Stdout:

```text
[A, B]
ClassCastException
```

`Class<T>.cast` verifies that an object is an instance of runtime class `T`, and `List.copyOf` creates an unmodifiable snapshot. In the example, the data contains no `null`; for data permitting `null`, decide on an explicit policy because `List.copyOf` rejects `null`.

For nested element types like `List<String>`, there is no `List<String>.class`. In such cases you must inspect the actual nested structure or use a schema/`Type` with a suitable decoder; having a `Class<List>` is not enough to guarantee type arguments.

## 22. `Collection<T>` and Immutability: Do Not Confuse Interface with State

All having type `Collection<String>`, the following values have different modification behaviors:

```java
Collection<String> mutable = new ArrayList<>();
Collection<String> immutable = List.of("A");
Collection<String> snapshot = List.copyOf(mutable);
```

Import `java.util.Collection`, `java.util.ArrayList`, and `java.util.List`.

- `mutable.add("B")` normally succeeds because it is an `ArrayList`.
- `immutable.add("B")` throws `UnsupportedOperationException`.
- `snapshot.add("B")` also throws `UnsupportedOperationException`.

The `Collection` interface **declares mutating methods**, yet an implementation may not support some optional operations. An API merely accepting `Collection<T>` does not automatically guarantee the collection is modifiable.

If a method needs to add elements to a received collection, the contract must explicitly state the mutability requirement, or the method should create `new ArrayList<>(input)` before mutating. If a method is read-only, keep its behavior non-mutating on the input.

## 23. Comparing Performance Properly

Some people pick arrays because "arrays are always fast," or pick `ArrayList` because "Generics are always better." Both are overly broad generalizations.

Practical considerations:

- `int[]` stores primitives contiguously in JVM array layout; `List<Integer>` uses wrapper objects and can incur boxing/unboxing overhead.
- `ArrayList<T>` typically stores object references in an internal array and supports fast indexed access. Logical size can grow; occasionally it must allocate new storage and copy references.
- `LinkedList<T>` has very different indexed access and memory characteristics from `ArrayList<T>`.
- `HashSet<T>` optimizes membership/uniqueness checks but has no index.
- Arrays have a fixed length; a list can grow or shrink depending on its implementation.
- A container with a simple API, strong type safety, and easy maintainability often outweighs unmeasured micro-differences.

To decide on performance-sensitive paths, use reliable benchmarks such as JMH with realistic data sizes and access patterns. Do not treat a tiny loop without warm-up as general proof of JVM performance.

## 24. Signs You Should Use a Collection Instead of an Array

You can prefer a generic collection when:

1. Elements have a generic type unknown where the implementation is written, such as `T`.
2. The problem does not require a runtime array component class.
3. Elements need to be added or removed over time.
4. The API needs to work with many implementations without knowing the concrete container.
5. You need a type-safe contract for nested collections such as `List<List<String>>`.
6. You want to use `Iterator`, streams, `contains`, `addAll`, and standard collection operations.
7. You can avoid unchecked casts or array covariance hazards.
8. You do not need large-scale primitive array optimization.

At the same time, consider keeping arrays when:

- External APIs require arrays;
- a fixed number of slots is an essential part of the model;
- direct primitive storage is needed;
- processing code requires a concrete runtime element type;
- performance measurements prove an array fits better without sacrificing type safety.

These criteria are not mutually exclusive: a module can hold data as `List<T>` in business logic and convert to `T[]` at the integration boundary.

## 25. Common Mistakes When Replacing Generic Arrays with Collections

**Mistake 1 — "`Collection<T>` has `get(index)` like an array."** No. The `Collection` contract has no indexed access method; use `List<T>`.

**Mistake 2 — "`new ArrayList<>(10)` creates ten slots just like `new T[10]`."** No. That is the initial capacity; `size()` starts at 0.

**Mistake 3 — "`Collection<T>` retains `T` at runtime."** Not in the sense of reifying the type argument; the JVM still typically sees a runtime class such as `ArrayList`.

**Mistake 4 — "`Collection<T>` is always mutable."** No. `List.of`, `Set.of`, or `List.copyOf` can supply unmodifiable collections.

**Mistake 5 — "Just changing the left-hand type to Collection gives type safety."** Not if the code still has raw types, unchecked casts, or unvalidated data operations. Keep the typed contract consistent throughout.

**Mistake 6 — "`ArrayList` behaves like `HashSet` regarding order."** No. `ArrayList` preserves element order; `HashSet` makes no iteration-order commitment.

**Mistake 7 — "`Arrays.asList` creates a list completely independent of the original array."** No. It is a fixed-size list backed by the array.

**Mistake 8 — "`List.copyOf` is always a deep copy."** No. It creates a snapshot at the collection structure level and does not deep-copy mutable element objects.

**Mistake 9 — "`List<List<String>>` can accept `List<List<Integer>>`."** No. Generic invariance prevents incompatible type-argument substitution in typed code.

**Mistake 10 — "Adding `@SuppressWarnings` solves generic arrays."** No. The annotation only hides certain warnings; it does not supply missing runtime type information.

**Mistake 11 — "`Collection<? extends T>` is suitable for adding any `T`."** No. With a `? extends T` producer, the compiler does not know the concrete subtype; you cannot arbitrarily write a `T` into it.

**Mistake 12 — "`Collection<? super T>` guarantees reading out `T`."** No. Safely reading elements can only assume `Object`, because the target collection could be `Collection<Object>`.

**Mistake 13 — "`List<T>` is better than arrays in every case."** No. Primitive arrays, fixed slots, or APIs with array contracts remain cases where arrays are needed.

## 26. Practice Exercises with Answers

### Exercise 1: Generic Container

Write `class Bag<T>` using `Collection<T>` to store elements. Can you create `Bag<String>` and `Bag<Integer>` without `new T[n]`?

**Answer:** Yes. The `Collection<T>` field can be initialized with `new ArrayList<>()`; the compiler checks `T` at call sites. No array allocation with component `T` is needed.

### Exercise 2: Multiple Lists of Strings

Two groups of names must allow adding/removing elements, while supporting `groups.get(0).get(1)`. Should you use `Collection<Collection<String>>` or `List<List<String>>`?

**Answer:** `List<List<String>>`, because indexed access is required at both levels.

### Exercise 3: Unknown Element Type

A function only needs to print the number of elements in any collection. Which signature is concise and accurate?

```java
static int sizeOf(java.util.Collection<?> values) {
    return values.size();
}
```

**Answer:** The form above fits because `T` does not need to be known. There is no need for raw `Collection`.

### Exercise 4: Maintaining Uniqueness

Duplicates must be removed when maintaining a set of names. What should be used?

**Answer:** `Set<String>`; if insertion order is needed, `LinkedHashSet<String>` can be used. No need to build an array and scan for duplicates manually.

### Exercise 5: Initial Capacity

What does `new ArrayList<String>(5).size()` return right after construction?

**Answer:** `0`. Capacity is not the actual element count.

### Exercise 6: Converting a Collection to an Array

Given `Collection<String> words`, how do you create `String[]` without an unchecked cast?

```java
String[] array = words.toArray(String[]::new);
```

**Answer:** Valid on Java 17. The array constructor reference provides `String` as the runtime component class.

### Exercise 7: Converting an Array to a List

Does `Arrays.asList(source)` guarantee that modifying `source[0]` will not affect the list?

**Answer:** No. This list is backed by the array and reflects element updates.

### Exercise 8: Input Collection Is Untrusted Data

Is an object passing `instanceof Collection<?>` sufficient proof that it is a `Collection<String>`?

**Answer:** No. This runtime check only confirms the raw container. Each element must be checked if the contract demands `String`.

### Exercise 9: PECS

What signature can a helper copying from `Collection<String>` into `Collection<Object>` use?

```java
static <T> void copy(
        java.util.Collection<? extends T> source,
        java.util.Collection<? super T> target) {
    for (T item : source) {
        target.add(item);
    }
}
```

**Answer:** This is a valid design. `source` is a producer; `target` is a consumer. No intermediate `T[]` array needs to be created.

### Exercise 10: When Can Arrays Not Be Dropped?

A native API requires `byte[]` for binary data. Should you force the design to `Collection<Byte>` just to use Generics?

**Answer:** No. `byte[]` is the natural choice for that contract and avoids boxing into `Byte`. Only convert at a boundary if another API genuinely requires it.

## 27. Checklist Before Choosing a Structure

For a new generic class or API, answer these questions:

- Do I need an **ordered list**, a **unique set**, a **queue**, or just an **iterable collection of elements**?
- Do I need frequent indexed access?
- Will the number of elements grow/shrink? Must a fixed slot count be maintained?
- Do I genuinely need a runtime array component type for integration or checking?
- Is the element type a non-reifiable `T` or `List<String>` at an array creation site?
- Can `List<T>` or `List<List<String>>` be used to eliminate generic array creation?
- Is mutability needed or an unmodifiable snapshot? Is `null` allowed?
- Am I exposing an internal collection directly to callers?
- Can `Collection<? extends T>` or `Collection<? super T>` be used to avoid copies or casts?
- If `T[]` is needed at the end, can the caller supply a valid `IntFunction<T[]>` or array constructor reference?
- Are there any raw/unchecked paths introducing heap pollution?
- Have performance requirements (primitives, memory, latency) actually been measured?

The checklist helps choose structures based on contracts rather than tricks to bypass compiler errors.

## 28. Summary and Reference Documentation

**`Collection<T>` is a suitable replacement for arrays when data should be manipulated as a collection of generic elements, especially when creating `new T[n]` or `new List<String>[n]` is invalid.** It lets the compiler check types through a general API, handling multiple elements without requiring the JVM to create a non-reifiable array component type.

Choose the narrowest interface expressing your exact need: `Collection<T>` for iterating/counting, `List<T>` for preserving order and indexed access, `Set<T>` for deduplication, or `Queue<T>` for queue processing. `List<List<String>>` is typically the natural solution instead of trying to create "an array of string lists."

However, `Collection<T>` does not reify `T`, does not guarantee mutability or ordering, and cannot replace every use of arrays. When an API truly requires an array, you can convert from a collection using `toArray(String[]::new)` or a valid array factory; when primitive storage or fixed slots are needed, using an array may be more accurate.

Authoritative references:

- [Java Language Specification §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): which types retain sufficient runtime information.
- [Java Language Specification §15.10.1 — Array Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.1): rules for creating arrays with element types.
- [Java Language Specification §10.5 — Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5): runtime array element assignment checks.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): generic types after erasure.
- [Java SE 17 `Collection<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html): collection contract, `toArray`, optional operations.
- [Java SE 17 `List<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): ordering, indices, unmodifiable factories.
- [Java SE 17 `Arrays.asList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)): fixed-size list backed by an array.
- [Java SE 17 `ArrayList<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): capacity, size, and flexible implementation.
