# Defensive Copying to Protect Array or Collection Fields in Java

## 1. Why can a `private final` field still be modified?

**Defensive copying** is creating a private copy of data at the boundary between an object and external code, so external code cannot modify **internal state** through a shared reference. This technique is especially important for arrays and mutable collections, because both are objects passed and returned **by reference** in Java.

Consider a class holding measurement data:

```java
// Intentionally unsafe example; not yet a standalone program.
final class UnsafeMeasurements {
    private final int[] values;

    UnsafeMeasurements(int[] values) {
        this.values = values;
    }

    int[] getValues() {
        return values;
    }
}
```

Calling `new UnsafeMeasurements(source)` only copies the **reference** from the `source` variable into the `values` field; it does not copy the elements. Therefore:

- If the caller modifies `source[0]` after initialization, the internal contents of `values` change along with it.
- If the caller receives `getValues()` and modifies the returned array, it is directly modifying the internal field.
- `private` only prevents direct field access from other code, while `final` only forbids **reassigning the `values` reference**; neither forbids modifying elements of the referenced array.

With `List`, `Set`, and `Map`, the same problem occurs when a constructor retains the input collection directly or a getter returns an internal mutable collection. Multiple places holding a reference to the same object is called **aliasing**.

An important lesson in the object contract topic: if `equals()` or `hashCode()` relies on this array/collection, an external modification can change two objects' equality relation or cause a key sitting in a `HashMap`/`HashSet` to stop looking up properly. Defensive copying helps establish and preserve the class's **invariant**.

## 2. Two directions to protect: on receipt and on return

A class that truly wants to control its state must examine **both input and output**:

1. **Copy-in:** copy the mutable object passed to a constructor or setter before storing it in a field.
2. **Copy-out:** copy the mutable object before returning it to external code via a getter or data-providing method.

If you only copy in the constructor while the getter returns the original internal array, the object can still be broken from the output side. If you only copy in the getter while the constructor keeps the input array directly, the caller can still mutate internal state through the reference it passed in.

Illustration:

```text
Dangerous case:
caller.source ───────────┐
                         ├──> same mutable array <── getter
object.internal ─────────┘

Copy-in + copy-out:
caller.source ──copy──> object.internal ──copy──> caller.snapshot
     ↑                        ↑                           ↑
separate array           separate array              separate array
```

For fields of genuinely immutable types, such as `String`, copying is not needed merely to prevent content mutation. However, an unmodifiable container does not automatically make **the contained elements** immutable.

## 3. One-dimensional arrays: `clone()` or `Arrays.copyOf()`

For a one-dimensional array holding primitives such as `int[]`, both `clone()` and `Arrays.copyOf(input, input.length)` create a **new** array and copy the values. The copy is independent of the source array with respect to element modification.

```java
import java.util.Arrays;
import java.util.Objects;

// Code snippet inside a class owning int[].
private final int[] values;

public Example(int[] input) {
    this.values = Objects.requireNonNull(input, "input").clone();
}

public int[] values() {
    return values.clone();
}
```

The snippet above only illustrates methods and a field inside a class named `Example`; to compile standalone, they must be wrapped in a valid class declaration. With non-`null` data, `Arrays.copyOf(input, input.length)` can also be used; for array slices, there is `Arrays.copyOfRange(...)`. Copying does not mean sorting, normalizing, or filtering; elements are preserved in order.

Scope note: `clone()` on a **one-dimensional array whose elements are mutable objects** still creates only a *shallow copy*: the two arrays hold references to **the exact same element objects**. For example, copying a `StringBuilder[]` creates a new outer shell array, yet the `StringBuilder` instances inside remain shared. For `String[]`, `String` elements are immutable, so a shallow copy of the array is usually sufficient.

## 4. Collections: independent copies vs unmodifiable views

### 4.1. `List.copyOf`, `Set.copyOf`, `Map.copyOf`

Since Java 10, `List.copyOf(collection)` creates an **unmodifiable** list with the collection's elements at the time of copying. Similarly, there are `Set.copyOf` and `Map.copyOf`. This is a concise option when element data is also immutable and you want a read-only API:

```java
import java.util.List;
import java.util.Objects;

// Code snippet inside a class storing a list of Strings.
private final List<String> tags;

public Example(List<String> source) {
    this.tags = List.copyOf(Objects.requireNonNull(source, "source"));
}

public List<String> tags() {
    return tags; // Allowed because the collection forbids edits and String is immutable.
}
```

**Limitations to know:**

- `List.copyOf`, `Set.copyOf`, and `Map.copyOf` reject `null` elements; `Map.copyOf` also rejects `null` keys/values. Validate and report errors appropriately depending on the class.
- `Set.copyOf` takes collection data and retains only distinct elements; iteration order of the resulting set is not promised. `Map.copyOf` also does not promise iteration order. If order is meaningful, choose an appropriate storage representation and document the ordering.
- If the source is already of a suitable immutable kind, `copyOf` **may reuse** the source object; you should not rely on it always allocating a new instance. The immutability to verify lies in whether edits are blocked through the API and whether element values remain stable.
- `copyOf` copies the **collection structure**, yet **does not automatically deep copy the elements**. A `List<StringBuilder>` may be a list that disallows `add`/`set`, while the `StringBuilder` instances inside can still be modified.

### 4.2. `Collections.unmodifiableList` is not necessarily a snapshot

An **unmodifiable view** can still reflect changes to the backing collection it wraps:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

// Illustrative snippet.
List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
source.add("B");
System.out.println(view); // [A, B]
```

Even though `view.add(...)` will throw `UnsupportedOperationException`, the data visible through `view` changed because `source` was modified externally. Do not confuse **disallowing modification through a view** with an **independent snapshot**.

If you need to keep an unmodifiable interface, allow `null`, or preserve insertion order via a specific structure, you can make a copy first and then wrap it:

```java
// Illustrative snippet.
List<String> snapshot =
    Collections.unmodifiableList(new ArrayList<>(source));
```

`snapshot` does not change structure when `source` subsequently adds/removes/reorders elements, although if elements inside are mutable objects, both still hold the same element references. On Java 17, when elements are non-`null` and there are no special view requirements, `List.copyOf(source)` is usually simpler.

Similarly, you can use `Collections.unmodifiableSet(new LinkedHashSet<>(source))` to create a set snapshot that preserves insertion order and disallows edits through the wrapper, or `Collections.unmodifiableMap(new LinkedHashMap<>(source))` when the API must preserve map order. Choosing the concrete collection should follow data requirements.

### 4.3. Getters for collections

There are two sensible strategies:

- **Expose an already-stored immutable collection:** the getter directly returns a `List<String>` created via `List.copyOf`, when `String` elements are immutable. No copy allocation is needed on every read.
- **Provide a snapshot on each call:** if the class actively mutates an internal collection, the getter can return `List.copyOf(internal)` or `new ArrayList<>(internal)` wrapped as unmodifiable, depending on API semantics. The caller receives a structural snapshot as of copy time.

Do not treat a getter returning `Collections.unmodifiableList(internalMutableList)` as a snapshot: subsequent internal edits still show up through the view. If that is indeed the intended semantics, state it clearly in the API contract; if an immutable value as of call time is required, a copy must be made.

## 5. Shallow copy vs deep copy

A **shallow** copy duplicates only the first container layer. It suffices if the container holds primitives or immutable objects. A **deep** copy must continue copying mutable components inside to the required depth so no unintended mutation path remains.

| Field type | Typical shallow copy | Sufficient to prevent external changes? |
| --- | --- | --- |
| `int[]` | `array.clone()` | Yes, for the contents of that primitive array |
| `String[]` | `array.clone()` | Yes, because `String` is immutable |
| `StringBuilder[]` | `array.clone()` | No, the builders remain shared |
| `int[][]` | `matrix.clone()` | No, the `int[]` row arrays remain shared |
| `List<String>` | `List.copyOf(list)` | Yes for `String` elements and list structure |
| `List<MutableItem>` | `List.copyOf(list)` | No, the `MutableItem` objects remain shared |
| `Map<String, MutableValue>` | `Map.copyOf(map)` | No, the mutable values can still be modified |

For `int[][]`, you must copy **the outer array and each row array**; do not assume the matrix is rectangular:

```java
import java.util.Objects;

// Snippet illustrating a dedicated helper for int[][].
static int[][] deepCopy(int[][] source) {
    Objects.requireNonNull(source, "source");
    int[][] result = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        result[i] = Objects.requireNonNull(source[i], "row").clone();
    }
    return result;
}
```

This function intentionally rejects `null` rows; `null` can be preserved if the data contract allows it by handling it explicitly. When a field is `List<List<String>>`, one approach is calling `List.copyOf` on each sublist and then `List.copyOf` on the outer list; since `String` is immutable, the result disallows modification at both levels. For `List<Person>` where `Person` is mutable, you must define how to copy `Person` or store a corresponding immutable DTO/snapshot; there is no generic `deepCopy()` that is always right for every object model.

## 6. Runnable Java 17 example: aliasing bug and three fixes

The following program demonstrates:

1. Key `UnsafeKey` retains the source array, causing its hash to change when the array is modified externally.
2. `SafeKey` copies the array in both constructor and getter, preserving `equals/hashCode` semantics.
3. `Labels` stores an unmodifiable `String` list via `List.copyOf`.
4. `IntGrid` deep-copies an `int[][]` matrix on both input and output, and compares by contents.

Save to **`DefensiveCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class DefensiveCopyDemo {
    static final class UnsafeKey {
        private final int[] numbers;

        UnsafeKey(int[] numbers) {
            this.numbers = Objects.requireNonNull(numbers);
        }

        String describe() {
            return Arrays.toString(numbers);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof UnsafeKey that)) return false;
            return Arrays.equals(numbers, that.numbers);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(numbers);
        }
    }

    static final class SafeKey {
        private final int[] numbers;

        SafeKey(int[] numbers) {
            this.numbers = Objects.requireNonNull(numbers).clone();
        }

        int[] numbers() {
            return numbers.clone();
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof SafeKey that)) return false;
            return Arrays.equals(numbers, that.numbers);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(numbers);
        }
    }

    static final class Labels {
        private final List<String> labels;

        Labels(List<String> input) {
            labels = List.copyOf(Objects.requireNonNull(input));
        }

        List<String> labels() {
            return labels;
        }
    }

    static final class IntGrid {
        private final int[][] cells;

        IntGrid(int[][] input) {
            cells = deepCopy(input);
        }

        int[][] snapshot() {
            return deepCopy(cells);
        }

        private static int[][] deepCopy(int[][] source) {
            Objects.requireNonNull(source);
            int[][] copy = new int[source.length][];
            for (int i = 0; i < source.length; i++) {
                copy[i] = Objects.requireNonNull(source[i]).clone();
            }
            return copy;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof IntGrid that)) return false;
            return Arrays.deepEquals(cells, that.cells);
        }

        @Override
        public int hashCode() {
            return Arrays.deepHashCode(cells);
        }
    }

    public static void main(String[] args) {
        int[] source = {1, 2};
        UnsafeKey unsafe = new UnsafeKey(source);
        int unsafeHashBefore = unsafe.hashCode();
        source[0] = 9;
        System.out.println("Unsafe values: " + unsafe.describe());
        System.out.println("Unsafe hash changed: "
            + (unsafeHashBefore != unsafe.hashCode()));

        int[] original = {1, 2};
        SafeKey safe = new SafeKey(original);
        int safeHashBefore = safe.hashCode();
        Set<SafeKey> set = new HashSet<>();
        set.add(safe);
        original[0] = 9;
        int[] returned = safe.numbers();
        returned[1] = 99;
        System.out.println("Safe values: " + Arrays.toString(safe.numbers()));
        System.out.println("Safe hash stable: "
            + (safeHashBefore == safe.hashCode()));
        System.out.println("Safe equal to new key: "
            + safe.equals(new SafeKey(new int[] {1, 2})));
        System.out.println("Safe HashSet lookup: "
            + set.contains(new SafeKey(new int[] {1, 2})));

        List<String> input = new ArrayList<>(List.of("red", "blue"));
        Labels labels = new Labels(input);
        input.add("green");
        System.out.println("Labels snapshot: " + labels.labels());
        try {
            labels.labels().add("black");
        } catch (UnsupportedOperationException e) {
            System.out.println("Labels cannot be edited: true");
        }

        int[][] matrix = {{1, 2}, {3, 4}};
        IntGrid grid = new IntGrid(matrix);
        matrix[0][0] = 99;
        int[][] leaked = grid.snapshot();
        leaked[1][1] = 88;
        System.out.println("Grid row 0: "
            + Arrays.toString(grid.snapshot()[0]));
        System.out.println("Grid row 1: "
            + Arrays.toString(grid.snapshot()[1]));
        System.out.println("Grid equals same contents: "
            + grid.equals(new IntGrid(new int[][] {{1, 2}, {3, 4}})));
    }
}
```

Compile and run in the directory containing the file with **JDK 17+**:

```bash
javac DefensiveCopyDemo.java
java DefensiveCopyDemo
```

Deterministic output:

```text
Unsafe values: [9, 2]
Unsafe hash changed: true
Safe values: [1, 2]
Safe hash stable: true
Safe equal to new key: true
Safe HashSet lookup: true
Labels snapshot: [red, blue]
Labels cannot be edited: true
Grid row 0: [1, 2]
Grid row 1: [3, 4]
Grid equals same contents: true
```

**Why do these results occur?**

- `UnsafeKey` keeps a direct reference to `source`; changing `source[0]` also changes the contents seen by `equals()` and `hashCode()`. The hashes of arrays `{1, 2}` and `{9, 2}` actually differ under `Arrays.hashCode(int[])`. If such a key is added to a `HashSet` or `HashMap` and then modified, lookup operations can fail because the hash changed; there is no need to rely on bucket details to demonstrate the risk.
- `SafeKey` copies on input **and** on array output. The modifications `original[0] = 9` and `returned[1] = 99` only affect the caller's two arrays, without touching the array inside `safe`. Thus, the hash is stable; a new `SafeKey` with the same elements is found in `HashSet`.
- `Labels` snapshots the list structure when the constructor runs. Adding `"green"` to the source list does not alter the stored copy; the getter returns a collection that does not support `add`. The elements here are immutable `String` values, so there is no mutable aliasing at the element level.
- `IntGrid` snapshots both the outer array and each row. Modifying the source array or the returned matrix does not alter the field; `Arrays.deepEquals` and `Arrays.deepHashCode` are appropriate for comparing/hashing nested array contents.

## 7. How does defensive copying relate to `equals()` and `hashCode()`?

If an object is a **value object** defined by the contents of an array or collection, keep that data stable so comparisons remain meaningful over time.

For arrays:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof SafeKey that)) return false;
    return Arrays.equals(numbers, that.numbers);
}

@Override
public int hashCode() {
    return Arrays.hashCode(numbers);
}
```

These are the two methods from `SafeKey` in the previous example, not a standalone program.

For an `int[][]` matrix, `Arrays.deepEquals` must pair with `Arrays.deepHashCode` if equality is by row contents. If you only use `Objects.equals(array1, array2)`, you are normally comparing **array references**, not elements. If you only use `Arrays.equals` for `int[][]`, the row arrays are still compared by reference.

For `List<String>`, `List.equals` and `List.hashCode` already have consistently defined content and order semantics. Do not write a manual hash based on a list and then allow callers to mutate the list or mutate element objects involved in equality.

**A key point:** defensive copying protects against modifications **through aliases given out or received**. It does not automatically make all objects immutable if the class itself still provides setters modifying fields used in equality/hashing. If it needs to be used as a stable hash key, design immutable identifying components or avoid mutating them while the object sits in a hash collection.

## 8. Records, constructors, and nested objects

Java records do not automatically copy arrays/collections. A record's component field is `private final`, yet the referenced data can be mutable. You can use a **compact canonical constructor** to copy-in and override the accessor to copy-out when the component is an array:

```java
import java.util.Arrays;
import java.util.Objects;

// Illustrative standalone record example without main.
record BytePacket(byte[] payload) {
    public BytePacket {
        payload = Objects.requireNonNull(payload).clone();
    }

    @Override
    public byte[] payload() {
        return payload.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BytePacket that
            && Arrays.equals(payload, that.payload);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(payload);
    }
}
```

**Why must `equals/hashCode` also be overridden?** The default equality/hash generated for a record with an array-type component **does not** automatically compare array contents deeply; two records holding two different array instances with identical bytes may be treated as unequal by default. If the goal is comparing byte payloads by content, you must use the two corresponding array methods as shown above.

If a record contains `List<String>`, you can write:

```java
// Another record illustration, Java 17.
record TagSnapshot(List<String> tags) {
    public TagSnapshot {
        tags = List.copyOf(tags);
    }
}
```

When the data consists of immutable `String` values, the default `tags()` getter can directly return the immutable list. If the record holds `List<MutableItem>`, you must copy/freeze each element according to the class's rules; `List.copyOf` alone is insufficient.

## 9. Common mistakes

| Mistake | Why it is dangerous | Fix |
| --- | --- | --- |
| Constructor stores input array/`ArrayList` directly | Caller keeps an alias to mutate internal state at any time | Copy-in before storing |
| Constructor copied, yet getter returns array field directly | Caller mutates internal state via getter | Copy-out on each call or provide a safe read-only API |
| Using only `Collections.unmodifiableList(source)` | It is a view; changes to `source` still appear | Create a snapshot first or use `List.copyOf` |
| Using `List.copyOf` for mutable elements and assuming deep copy | Elements remain shared | Copy elements, use immutable values, or DTOs |
| Using `matrix.clone()` for `int[][]` | The `int[]` rows remain aliased | Clone each row |
| Using `Arrays.asList(array)` and thinking it is detached from the array | The fixed-size list is still **backed by the original array**; `set` and array edits affect each other | Use a proper snapshot such as `List.copyOf(Arrays.asList(array))` when elements fit |
| Holding `final List<MutableItem>` | `final` does not make the list or elements immutable | Choose an immutable representation and defensive copy |
| Exposing `Map<K, MutableValue>` despite `Map.copyOf` | Values can still be mutated | Copy/freeze values and handle nested objects |
| Copy-in, yet providing a setter that mutates equality keys | Hash still changes because of the class itself | Design stable keys or restrict usage lifecycle |
| Using `List.copyOf` when valid data contains `null` | Throws `NullPointerException` | Define a null policy and pick a suitable copy approach |
| Copying a mutable object without a consistent snapshot across threads | May read mixed data while source is being edited | Synchronize/read under lock or exchange immutable data |

## 10. What is not automatically guaranteed by copying?

### 10.1. Copying does not mean completely immutable

A class may copy arrays in its constructor/getter yet still have an internal method `updateValue(i, v)` that modifies the array; in that case, the object **is still mutable**, just protected from mutation through external aliases. The API should state clearly whether the object is a fixed snapshot or a controlled mutable object.

### 10.2. Deep copy must have concrete meaning

For complex object graphs, reference cycles, linked objects, or resources like files/sockets, "deep copy everything" is not always feasible or desirable. Choose the protection boundary for data: which fields must be immutable, which elements are safe to share, and which elements need snapshots. When needed, use a copy constructor or snapshot creation method defined by the element type itself.

### 10.3. Copying during concurrent writes does not create an atomic snapshot

For example, one thread adds/removes elements in an `ArrayList` while another thread calls `List.copyOf(source)`: copying does not by itself provide synchronization between threads. Similarly, copying array elements while another thread modifies them can observe values from different points in time. If a consistent snapshot is needed in a concurrent environment, both writers and copiers must follow a proper synchronization protocol, or switch to immutable data/snapshot mechanisms designed for concurrency.

### 10.4. Copying has a cost

Copy-in and copy-out consume memory and time proportional to the amount of data copied. For a getter called repeatedly on large arrays, copy-out can be expensive. You can design specific query APIs such as `size()`, `get(index)` returning primitives/immutables, return a controlled iterator/snapshot, or pre-store an immutable collection and return it directly. Optimize while preserving commitments about immutability and state protection.

## 11. Code review checklist

1. Does the class have fields that are arrays, collections, or objects holding mutable state?
2. Do constructors, builders, factories, and setters retain mutable references that external code continues to own?
3. Do getters, accessors, callback methods, or element-returning methods expose internal mutable references?
4. Is the current copy shallow or deep? Do elements and nested collections still have aliases?
5. Was an immutable snapshot or an unmodifiable view chosen? Will modifying the source later alter returned data?
6. Are rules for `null`, duplicates, ordering, and canonicalization of the collection preserved properly?
7. Do `equals/hashCode` use externally exposed mutable state? Can the hash change after use as a `HashMap/HashSet` key?
8. Are there concurrent writers and copiers? Does the snapshot need atomic consistency?
9. Have tests tried **mutating the input after the constructor** and **mutating the getter result** at every nested level?

An effective test is creating the object from mutable data, recording values, mutating the source, and reading back; then also mutating the data returned by the accessor and checking the object again. For hash keys, add the object to a `HashSet`, act through any potential aliases, and then verify equality/hash and lookup. Do not test only the no-mutation case.

## 12. Self-check

**Question 1.** Does `private final int[] scores` make every element in `scores` immutable?

**Answer:** No. `final` prevents reassigning the reference field, yet `scores[0] = 123` can still happen if someone has access to the array.

**Question 2.** If the constructor already called `input.clone()` yet the getter returns `internalArray` directly, is the class fully protected?

**Answer:** Not yet. Callers can still modify the array received from the getter. You must return a copy or design a read API that does not expose the mutable reference.

**Question 3.** Are `Collections.unmodifiableList(input)` and `List.copyOf(input)` the same with respect to external code mutating `input` later?

**Answer:** No. `unmodifiableList` only creates a view disallowing edits through the view, yet reflecting changes from the backing list; `List.copyOf` snapshots the structure and disallows structural edits on the snapshot. Neither automatically deep copies element objects.

**Question 4.** Is copying `int[][] original` with `original.clone()` enough to make elements `original[0][0]` independent?

**Answer:** Not yet. The rows are still shared arrays; each subarray must be copied as well.

**Question 5.** Does `List.copyOf(List<StringBuilder>)` stop someone holding a reference to a `StringBuilder` from calling `append`?

**Answer:** No. `List.copyOf` only prevents structural edits via the list API; `StringBuilder` remains a shared mutable object.

**Question 6.** Can a `List<String>` stored using `List.copyOf` be returned directly from a getter while still protecting internal state?

**Answer:** Yes, when the list itself does not support modification and the `String` elements are immutable; calling `add/set/remove` via the getter cannot modify the class's state.

**Question 7.** A value object has `hashCode()` based on a mutable array; you did copy-in and copy-out, yet the class itself still has a method mutating the internal array. Can it be used as a `HashMap` key without further thought?

**Answer:** Not yet. Defensive copying prevents unintended aliasing; it does not prevent the class's own methods from changing equality/hash components. Hash components must be kept stable while acting as a key, or another design should be chosen.

---

**Takeaway:** For arrays and mutable collections, determine **who owns the data at each API boundary**. Usually you need copy-in on receipt and copy-out on publication; choose a snapshot over a view if you want isolation from future changes. Shallow copying only suffices when elements are immutable; nested data requires an appropriate deep-copying policy. Protecting state keeps `equals()` and `hashCode()` consistent when they rely on those values.