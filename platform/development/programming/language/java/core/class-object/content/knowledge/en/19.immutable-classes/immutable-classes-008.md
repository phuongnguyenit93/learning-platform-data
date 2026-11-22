# Testing Immutability When a Class Contains Arrays or Collections in Java

## 1. Problem to Solve: A `private final` Field Can Still Hold Mutable Data

When a Java class is presented as **immutable**, we expect that **the observable state of a fully constructed object is not modified** by operations permitted from the outside.

Example:

```java
final class Exam {
    private final int[] scores;

    Exam(int[] scores) {
        this.scores = scores;
    }

    int[] scores() {
        return scores;
    }
}
```

The `Exam` class looks "safe": `final class`, a `private final` field, and no `setScores` method. However, it is **not immutable**:

- The constructor keeps the **same array reference** passed in by the caller.
- The getter returns **the internal array itself**.
- The caller can modify any `scores[i]` element, even though reassigning the `scores` field is not allowed.

Reason: **`final` locks field reassignment, not the contents of the referenced object**. `int[]`, `ArrayList`, `HashMap`, `HashSet`, and many other types are still mutable objects.

This lesson does not only present how to write an immutable class, but primarily answers a practical question:

> **How do you test that a class containing arrays or collections truly cannot be modified through any external reference path?**

After this lesson, you will be able to identify alias paths, design *defensive copies*, distinguish an unmodifiable view from a snapshot, test multidimensional arrays and collections containing mutable elements, check record/equals/hashCode, and write Java 17+ tests with deterministic output.

## 2. Test Definition: What Must Remain Unchanged?

Suppose an object is created at time T0:

```text
Caller --input--> Constructor
                    |
                    v
               Object state S0
                    |
            caller operations
                    v
               Object state S1
```

For an object with an immutability contract, permitted external operations must not change **the logical state of the same object** from S0 to a different value. To test this, you need to choose **reliable observations**:

- Getters returning a primitive value or an immutable value: the value must remain stable.
- List snapshot: the elements and ordering according to the contract must remain stable.
- Array snapshot: the contents at each index must remain stable.
- Methods computed from state, such as `sum()`: the result must remain stable when the initial input does not change according to the contract.
- `equals`/`hashCode` of an immutable value class: must be consistent for the same logical state.
- Domain invariants: no nulls, duplicates, or out-of-range values if the constructor promises this.

**Do not take a single getter as proof for the entire object.** If one getter returns a list copy while another method returns the internal array or a nested mutable element, the object can still be modified through the remaining path.

### Three Important Attack Vectors

1. **Input alias:** modifying the original array/list after the constructor has received it.
2. **Output alias:** modifying the array/list returned from a getter.
3. **Nested alias:** modifying a mutable element or a nested collection even though the outer collection is unmodifiable.

Two additional advanced issues:

4. **State-sharing:** multiple objects hold references to the same uncontrolled mutable component.
5. **Concurrent modification:** source data is being modified right while the constructor is validating/copying it, or the object is published before construction finishes.

## 3. Distinguishing Structure, Elements, and the Object Graph

A `List` can contain `String` objects or `StringBuilder` objects. In these two cases, locking the list structure has different meanings:

```text
Case A:
List<String> --------> ["Java", "Core"]
                         |       |
                     immutable immutable

Case B:
List<StringBuilder> -> [ reference X ]
                              |
                              v
                       mutable builder
```

If you call `List.copyOf(...)`:

- You cannot call `add/remove/set` on the resulting list.
- However, if an element is a `StringBuilder`, it can still have `append` called on it through an existing reference.
- Therefore, you must check both **container mutability** and **element mutability**.

Similarly:

| Field | Common Risks |
| --- | --- |
| `private final int[] values` | Modifying the slots |
| `private final int[][] matrix` | Modifying outer/inner arrays, shallow copy |
| `private final List<String> names` | Input alias, getter alias, unmodifiable view backing |
| `private final List<StringBuilder> builders` | Mutable element contents even though the list is unmodifiable |
| `private final Map<String, List<String>> data` | Mutable nested lists, aliases in map values |
| `private final Set<MutableKey> keys` | Mutated elements alter set equality/hash behavior |
| `record Data(int[] values)` | Record does not automatically clone components or deep-compare arrays |

**Evaluate progressively deeper from the object root:** You can traverse from fields down to collections, from collections down to elements, and then to sub-elements until every mutable alias path has been blocked or controlled according to the contract.

## 4. First Example: Proving a "final + private final" Class Is Still Mutable

Create the file **`BrokenArrayDemo.java`**:

```java
final class Exam {
    private final int[] scores;

    Exam(int[] scores) {
        this.scores = scores;
    }

    int[] scores() {
        return scores;
    }

    int firstScore() {
        return scores[0];
    }
}

public class BrokenArrayDemo {
    public static void main(String[] args) {
        int[] input = {10, 20};
        Exam exam = new Exam(input);

        System.out.println("before=" + exam.firstScore());

        input[0] = 99;
        System.out.println("after input=" + exam.firstScore());

        exam.scores()[0] = 77;
        System.out.println("after getter=" + exam.firstScore());
    }
}
```

Run with JDK 17+:

```bash
javac BrokenArrayDemo.java
java BrokenArrayDemo
```

**Standard output:**

```text
before=10
after input=99
after getter=77
```

The two tests have different meanings:

1. `input[0]=99` proves a **constructor leak**: the caller retains an alias to the internal array.
2. `exam.scores()[0]=77` proves a **getter leak**: the caller can mutate the internal array through the getter.

Even if the getter is changed to return `scores.clone()`, the constructor can still be flawed if it keeps the original input. Conversely, copying the input in the constructor while returning the raw internal array through the getter is still flawed.

**QA conclusion:** To claim immutability, you must check **both the ingress and egress paths**.

## 5. Fix for One-Dimensional Arrays: Copy at Both Boundaries

Create **`SafeArrayDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Exam {
    private final int[] scores;

    Exam(int[] input) {
        Objects.requireNonNull(input, "scores");

        int[] copy = input.clone();
        for (int score : copy) {
            if (score < 0) {
                throw new IllegalArgumentException("negative score");
            }
        }

        scores = copy;
    }

    int firstScore() {
        return scores[0];
    }

    int[] snapshot() {
        return scores.clone();
    }

    @Override
    public String toString() {
        return Arrays.toString(scores);
    }
}

public class SafeArrayDemo {
    public static void main(String[] args) {
        int[] original = {10, 20};
        Exam exam = new Exam(original);

        original[0] = 99;
        System.out.println("after input=" + exam);

        int[] copy = exam.snapshot();
        copy[1] = 77;
        System.out.println("after getter=" + exam);

        System.out.println("first=" + exam.firstScore());
    }
}
```

```bash
javac SafeArrayDemo.java
java SafeArrayDemo
```

```text
after input=[10, 20]
after getter=[10, 20]
first=10
```

Why does this code protect the state?

- `input.clone()` creates an `int[]` array with a different reference from the input.
- Validation iterates over **the copy** that will be stored, rather than validating the input and copying at a different time. This avoids certain check-then-copy bugs in sequential code; **it does not by itself make the copying process safe when the input is being modified concurrently**.
- The `scores` field is `private final` and receives the copy exactly once.
- `snapshot()` returns a new clone; if the caller mutates the clone, it does not affect the internal array.
- `firstScore()` only returns a primitive and does not expose a reference.

**Note:** `firstScore` requires a non-empty array. The example uses an input with elements; if the contract allows empty arrays, a `size()`/`at(index)` API or validation requiring at least one element is needed. That is a separate design concern and does not diminish the point of defensive copying.

## 6. Input/Output Checklist: Two Independent Tests

An `ImmutableArrayValue` class is considered to pass basic alias testing when:

| Test | Action | Expected Result |
| --- | --- | --- |
| T1 — ingress | Keep `input`, construct object, modify `input[0]` | Object does not change |
| T2 — egress | Obtain array from getter, modify `getter[0]` | Object does not change |
| T3 — identity | Call getter twice if the API promises a copy | The two arrays do not share the same reference |
| T4 — value | Read `at(i)` or snapshot | Values remain unchanged per the contract |
| T5 — validation | Constructor receives invalid data | Throws an exception; does not return a valid instance |
| T6 — nested | Modify a nested array or mutable element | Object does not change if the contract is deep immutable |

**T3 is not a universal requirement for every immutable API.** If a getter returns an **immutable value object** itself, two calls can safely share the same reference. However, for a getter whose contract is to **return a mutable array snapshot**, comparing the identity of two snapshots is a useful test to detect accidentally returning the internal array.

### Do Not Test Only for Exceptions

The fact that `list.add(...)` throws `UnsupportedOperationException` proves that the caller cannot mutate **through that list reference** using `add`. It does not prove that the backing collection cannot change through another reference or that the elements are not mutable.

## 7. Complete Self-Test: Verifying the Immutable Array Contract

Create the file **`ArrayImmutabilitySelfTest.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Snapshot {
    private final int[] values;

    Snapshot(int[] source) {
        values = Objects.requireNonNull(source).clone();
    }

    int at(int index) {
        return values[index];
    }

    int[] values() {
        return values.clone();
    }
}

public class ArrayImmutabilitySelfTest {
    static void check(boolean condition, String name) {
        if (!condition) {
            throw new AssertionError(name);
        }
    }

    public static void main(String[] args) {
        int[] source = {1, 2, 3};
        Snapshot snapshot = new Snapshot(source);

        source[0] = 99;
        check(snapshot.at(0) == 1, "input alias");

        int[] exported = snapshot.values();
        exported[1] = 88;
        check(snapshot.at(1) == 2, "output alias");

        int[] firstRead = snapshot.values();
        int[] secondRead = snapshot.values();
        check(firstRead != secondRead, "fresh copies");

        check(Arrays.equals(snapshot.values(), new int[] {1, 2, 3}),
                "stable contents");

        System.out.println("array immutability PASS");
    }
}
```

```bash
javac ArrayImmutabilitySelfTest.java
java ArrayImmutabilitySelfTest
```

```text
array immutability PASS
```

`check(...)` throws `AssertionError` if a violation is detected; it does not depend on enabling Java `-ea`. This is a standalone self-test run via `main`, and does not replace full unit/property tests in a real project.

**Extending the tests:** call the constructor with null, an empty array, large sizes, and invalid values, and test multi-threaded cases only when the API guarantees concurrent safety.

## 8. `int[][]`: An Outer Clone Is Not a Deep Copy

For a two-dimensional array:

```java
int[][] input = {{1, 2}, {3}};
int[][] shallow = input.clone();
```

`shallow` is a new outer array, but its elements still hold **references to the old inner `int[]` arrays**.

```text
input ───> outer X ─┬─> inner A [1,2]
                    └─> inner B [3]

shallow ──> outer Y ┬─> inner A [1,2]
                    └─> inner B [3]
```

Modifying `input[0][0]` also causes `shallow[0][0]` to observe the change. Therefore, checking `input != shallow` is **not sufficient**.

### Counterexample Program

File **`ShallowMatrixDemo.java`**:

```java
import java.util.Arrays;

public class ShallowMatrixDemo {
    public static void main(String[] args) {
        int[][] input = {{1, 2}, {3}};
        int[][] shallow = input.clone();

        input[0][0] = 99;

        System.out.println(input != shallow);
        System.out.println(input[0] == shallow[0]);
        System.out.println(Arrays.deepToString(shallow));
    }
}
```

```bash
javac ShallowMatrixDemo.java
java ShallowMatrixDemo
```

```text
true
true
[[99, 2], [3]]
```

**Testing conclusion:** If the data contains references to mutable child objects, you must try **modifying a child** rather than stopping at verifying that the outer object has a different identity.

## 9. Copying a Two-Dimensional Array and Testing Every Level

Create **`ImmutableMatrixDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Matrix {
    private final int[][] rows;

    Matrix(int[][] source) {
        Objects.requireNonNull(source, "source");
        rows = copyRows(source);
    }

    private static int[][] copyRows(int[][] source) {
        int[][] result = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            result[i] = Objects.requireNonNull(
                    source[i], "row " + i).clone();
        }
        return result;
    }

    int at(int row, int column) {
        return rows[row][column];
    }

    int[][] snapshot() {
        return copyRows(rows);
    }

    @Override
    public String toString() {
        return Arrays.deepToString(rows);
    }
}

public class ImmutableMatrixDemo {
    public static void main(String[] args) {
        int[][] input = {{1, 2}, {3}};
        Matrix matrix = new Matrix(input);

        input[0][0] = 99;
        input[1] = new int[] {88};

        System.out.println(matrix);

        int[][] exported = matrix.snapshot();
        exported[0][1] = 77;
        exported[1] = new int[] {66};

        System.out.println(matrix);
        System.out.println(matrix.at(1, 0));
    }
}
```

```bash
javac ImmutableMatrixDemo.java
java ImmutableMatrixDemo
```

```text
[[1, 2], [3]]
[[1, 2], [3]]
3
```

Here, **the outer array and each inner primitive array** are copied:

- Prevents the caller from keeping an alias into the source.
- Prevents getters from exposing the inner arrays.
- Keeps the data stable under both element modifications and row-reference replacements in source/exported.
- Supports *jagged arrays* because each row has its own length.

**Limitation:** The `copyRows` method checks for null rows and clones while copying, but it does not synchronize with a writer modifying the source concurrently. If the source changes concurrently, the caller must provide a stable snapshot or design synchronization/ownership; `final`/`clone` alone does not make the copy operation atomic with respect to another writer.

## 10. Arrays Containing Mutable Objects: clone Is Still Shallow

With:

```java
StringBuilder[] builders = {
        new StringBuilder("A")
};
StringBuilder[] copy = builders.clone();
```

`builders != copy`, but `builders[0] == copy[0]`.

### Runnable demo

File **`MutableElementArrayDemo.java`**:

```java
public class MutableElementArrayDemo {
    public static void main(String[] args) {
        StringBuilder element = new StringBuilder("A");
        StringBuilder[] input = {element};
        StringBuilder[] shallow = input.clone();

        element.append("B");

        System.out.println(input != shallow);
        System.out.println(input[0] == shallow[0]);
        System.out.println(shallow[0]);
    }
}
```

```bash
javac MutableElementArrayDemo.java
java MutableElementArrayDemo
```

```text
true
true
AB
```

If you want to guarantee immutable **string contents**, it is usually simpler to **convert the mutable builders into immutable `String` values** and store `String[]` or `List<String>`.

Copying an arbitrary object graph cannot be solved with `clone()` alone; you must decide the semantics of each nested mutable type.

## 11. Redesigning the Representation: Converting Mutable Objects into Immutable Values

Create **`ImmutableTextBatchDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class TextBatch {
    private final String[] texts;

    TextBatch(StringBuilder[] input) {
        Objects.requireNonNull(input);
        texts = new String[input.length];

        for (int i = 0; i < input.length; i++) {
            StringBuilder item =
                    Objects.requireNonNull(input[i], "item");
            texts[i] = item.toString();
        }
    }

    String at(int index) {
        return texts[index];
    }

    String[] snapshot() {
        return texts.clone();
    }

    @Override
    public String toString() {
        return Arrays.toString(texts);
    }
}

public class ImmutableTextBatchDemo {
    public static void main(String[] args) {
        StringBuilder source = new StringBuilder("A");
        TextBatch batch = new TextBatch(
                new StringBuilder[] {source});

        source.append("B");
        System.out.println(batch);

        String[] copy = batch.snapshot();
        copy[0] = "C";

        System.out.println(batch);
        System.out.println(batch.at(0));
    }
}
```

```bash
javac ImmutableTextBatchDemo.java
java ImmutableTextBatchDemo
```

```text
[A]
[A]
A
```

In the constructor, `toString()` creates a String representation that is not affected by subsequent `append` calls. The field stores a `String[]` array; the getter returns a clone. Because `String` is immutable, sharing a `String` element is safe by content.

This is a **snapshot of the text content at the time of reading**. If another thread mutates the StringBuilder concurrently with `toString()`, the application must consider the thread-safety of the input/handoff. The example assumes the caller does not modify it concurrently during construction.

## 12. Input List: Keep an Alias or Take a Snapshot?

A class holding a `private final List<String>` can still be mutated if its constructor stores a reference to a mutable input.

File **`ListInputAliasDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class BrokenPlaylist {
    private final List<String> songs;

    BrokenPlaylist(List<String> songs) {
        this.songs = songs;
    }

    List<String> songs() {
        return songs;
    }
}

public class ListInputAliasDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("A");

        BrokenPlaylist playlist = new BrokenPlaylist(input);
        input.add("B");

        System.out.println(playlist.songs());

        playlist.songs().remove("A");
        System.out.println(input);
    }
}
```

```bash
javac ListInputAliasDemo.java
java ListInputAliasDemo
```

```text
[A, B]
[B]
```

The results show:

- Mutating the input causes the playlist to observe the new element.
- Mutating through the getter causes the input to change.
- `private final` only fixes the `songs` reference; it does not sever the alias.

**The String data is not at fault:** `String` is immutable. The bug lies in the **mutable list container** and its two reference paths.

## 13. `List.copyOf`: A Structural Snapshot When Elements Are Already Immutable

A suitable approach for a list of Strings:

```java
this.songs = List.copyOf(input);
```

`List.copyOf` creates an unmodifiable list per the API. With a mutable `ArrayList` as the source, subsequent structural changes to the source are not reflected in the snapshot. With String elements, we have immutable value components.

File **`ImmutablePlaylistDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Playlist {
    private final List<String> songs;

    Playlist(List<String> input) {
        Objects.requireNonNull(input, "songs");
        songs = List.copyOf(input);
    }

    List<String> songs() {
        return songs;
    }
}

public class ImmutablePlaylistDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("A");

        Playlist playlist = new Playlist(input);
        input.add("B");

        System.out.println("source=" + input);
        System.out.println("snapshot=" + playlist.songs());

        try {
            playlist.songs().add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("add rejected");
        }
    }
}
```

```bash
javac ImmutablePlaylistDemo.java
java ImmutablePlaylistDemo
```

```text
source=[A, B]
snapshot=[A]
add rejected
```

**Verification succeeds because of both properties:**

1. **Does not reflect the mutable input's structure** after construction.
2. **Does not allow mutating the output structure** through the getter.

Because the `String` type is immutable, testing for nested mutation also has no path through individual String objects.

### Null Policy of `List.copyOf`

`List.copyOf` **does not accept null elements**. The constructor needs to determine whether this is the desired contract or change the storage representation to support nulls. If the caller needs to distinguish null elements, a custom design is required; do not silently assume every collection copy API preserves nulls.

`List.copyOf` can optimize by reusing an unmodifiable list input; **do not test by requiring the snapshot to have a different identity from every input** when the API does not promise that. Test **the behavior that the structure cannot be changed**.

## 14. `Collections.unmodifiableList` Is a View, Not Necessarily a Snapshot

A common mistake:

```java
this.songs = Collections.unmodifiableList(input);
```

The caller cannot modify the list through the `songs` getter, but can still modify the list through the retained `input` reference. **An unmodifiable view still reflects the backing list**.

File **`ViewVsSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> view =
                Collections.unmodifiableList(source);
        List<String> copy = List.copyOf(source);

        source.add("B");

        System.out.println("view=" + view);
        System.out.println("copy=" + copy);
    }
}
```

```bash
javac ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
```

```text
view=[A, B]
copy=[A]
```

If you need a snapshot while using the legacy wrapper API, you can write:

```java
List<String> snapshot = Collections.unmodifiableList(
        new ArrayList<>(source));
```

This is a **code snippet** inside a method where `source` and the imports have already been declared. The `new ArrayList<>(source)` copy detaches the backing structure; the wrapper prevents mutating it through the exposed reference. However, elements are still copied **shallowly**.

**Test both directions thoroughly:** try `source.add` and try `snapshot.add`; a single test alone can miss bugs.

## 15. Do Not Test the Identity of `List.of`/`List.copyOf` as a Guarantee

Some unmodifiable collections from factory APIs are described as **value-based**. You must not write contracts such as:

```java
// Do not use as an immutability criterion:
// List.of("A") == List.of("A")
// List.copyOf(existing) != existing
```

The API does not promise to always create a new reference or always reuse an old reference. The right way to check is **observable equality/content and mutation behavior** according to the contract.

For example:

```java
List<String> result = List.copyOf(source);

System.out.println(result.equals(List.of("A")));
```

checks the logical contents when `source` initially contains `"A"`, without relying on implementation allocation.

With a mutable `ArrayList` input, after `List.copyOf` completes normally, the snapshot structure is not a view that reflects subsequent modifications to the ArrayList.

**Do not use `==` on two collection instances to conclude "immutable" or "mutable".** Two variables can safely point to the same immutable object; two mutable objects with different references are still mutable.

## 16. A List Containing Mutable Elements: Outer Copy Still Leaves an Alias

Create **`MutableListElementDemo.java`**:

```java
import java.util.List;

public class MutableListElementDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");
        List<StringBuilder> values =
                List.copyOf(List.of(builder));

        builder.append("B");
        System.out.println(values.get(0));

        try {
            values.add(new StringBuilder("C"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("list structure locked");
        }
    }
}
```

```bash
javac MutableListElementDemo.java
java MutableListElementDemo
```

```text
AB
list structure locked
```

The list rejects adding elements, yet the `StringBuilder` inside still mutates through the `builder` alias. This result exposes **shallow immutability**.

### Testing Mutable Elements in Two Directions

- **External element alias:** the caller retains the original `builder` object, mutates it, and checks whether the immutable class's getter reflects the change.
- **Getter element leak:** the caller obtains `list.get(0)` and calls a mutating method on the element, then checks whether the class changes.

Both can happen even when the list wrapper is unmodifiable.

**Common remediation approaches:** convert elements into immutable values (`String`, an immutable record with appropriate components), or create deep defensive copies according to the contract, or avoid exposing raw mutable elements.

## 17. Converting `List<StringBuilder>` into an Immutable `List<String>`

File **`ImmutableNotesDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Notes {
    private final List<String> lines;

    Notes(List<StringBuilder> source) {
        Objects.requireNonNull(source);
        List<String> copy = new ArrayList<>();

        for (StringBuilder builder : source) {
            copy.add(Objects.requireNonNull(builder).toString());
        }

        lines = List.copyOf(copy);
    }

    List<String> lines() {
        return lines;
    }
}

public class ImmutableNotesDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");
        List<StringBuilder> input = new ArrayList<>();
        input.add(builder);

        Notes notes = new Notes(input);

        builder.append("B");
        input.add(new StringBuilder("C"));

        System.out.println("notes=" + notes.lines());

        try {
            notes.lines().set(0, "X");
        } catch (UnsupportedOperationException ex) {
            System.out.println("replacement blocked");
        }
    }
}
```

```bash
javac ImmutableNotesDemo.java
java ImmutableNotesDemo
```

```text
notes=[A]
replacement blocked
```

**Why is this sufficient for this example?**

- The constructor converts each mutable StringBuilder into an immutable String snapshot.
- Creates an unmodifiable List from those strings.
- The getter returns the list because neither its structure nor its elements allow the caller to change the logical text content.
- The caller modifying or adding to the original input after construction does not cause `notes.lines()` to change.

**Limitation:** If the StringBuilder is modified concurrently with `toString`, taking a snapshot requires an external ownership/synchronization mechanism. The example only assumes the source is stable while the constructor reads it.

## 18. `Set` Collections: An Unmodifiable Structure Is Not Enough if Elements Are Mutable

`Set.copyOf` can create an unmodifiable set, but **it does not freeze the element objects**.

A mutable key whose `equals`/`hashCode` depends on state that is mutated after insertion into the set can make membership behavior unstable. These are two separate issues:

1. **Immutability of the class holding the Set:** the object's logical state must not change.
2. **The hashing contract:** elements used as keys/elements in hash-based structures must have proper and stable equality/hash behavior while present in the set.

Do not merely check that `set.add(...)` throws an exception and conclude that the entire Set object graph is immutable.

### Set Example with String Elements

File **`ImmutableTagsDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

final class Tags {
    private final Set<String> values;

    Tags(Set<String> input) {
        values = Set.copyOf(input);
    }

    boolean contains(String tag) {
        return values.contains(tag);
    }

    Set<String> snapshot() {
        return values;
    }
}

public class ImmutableTagsDemo {
    public static void main(String[] args) {
        Set<String> input = new HashSet<>();
        input.add("java");

        Tags tags = new Tags(input);
        input.add("oop");

        System.out.println(tags.contains("java"));
        System.out.println(tags.contains("oop"));

        try {
            tags.snapshot().add("new");
        } catch (UnsupportedOperationException ex) {
            System.out.println("tags locked");
        }
    }
}
```

```bash
javac ImmutableTagsDemo.java
java ImmutableTagsDemo
```

```text
true
false
tags locked
```

Do not print a `Set` directly with `toString()` and predict the order of multiple elements — **Set iteration order may not be guaranteed**. The example checks membership booleans so that stdout is stable.

## 19. `Map.copyOf` Protects the Mapping Structure, Does Not Deep-Copy Values

Create **`ImmutableRatesDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

final class Rates {
    private final Map<String, Integer> values;

    Rates(Map<String, Integer> input) {
        values = Map.copyOf(Objects.requireNonNull(input));
    }

    Integer forCode(String code) {
        return values.get(code);
    }

    Map<String, Integer> snapshot() {
        return values;
    }
}

public class ImmutableRatesDemo {
    public static void main(String[] args) {
        Map<String, Integer> input = new HashMap<>();
        input.put("A", 10);

        Rates rates = new Rates(input);
        input.put("A", 99);
        input.put("B", 20);

        System.out.println("A=" + rates.forCode("A"));
        System.out.println("B=" + rates.forCode("B"));

        try {
            rates.snapshot().put("C", 30);
        } catch (UnsupportedOperationException ex) {
            System.out.println("map locked");
        }
    }
}
```

```bash
javac ImmutableRatesDemo.java
java ImmutableRatesDemo
```

```text
A=10
B=null
map locked
```

- `Map.copyOf` produces a snapshot of the mappings from a mutable map input per the API; modifying the input afterward does not change the map snapshot.
- Both the `String` key and the `Integer` value in the example are immutable values.
- The caller cannot `put` into the returned map.
- The `forCode` getter returns an immutable Integer and does not expose a mutable inner value.

**Null policy:** `Map.copyOf` rejects null keys and values. If business requirements must allow null values, you must design different semantics and storage rather than assuming the API preserves nulls.

## 20. A Map Containing List Values: You Must Snapshot Both the Map and Each List

A mistake:

```java
Map<String, List<String>> snapshot = Map.copyOf(input);
```

The map structure may be unmodifiable, but the `List<String>` values **can be mutable ArrayLists**. If the caller modifies an original list value, the map snapshot can observe the change.

### How to Test Nested Layers

Create **`NestedMapLeakDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class NestedMapLeakDemo {
    public static void main(String[] args) {
        List<String> students = new ArrayList<>();
        students.add("An");

        Map<String, List<String>> source = new HashMap<>();
        source.put("A", students);

        Map<String, List<String>> outer = Map.copyOf(source);

        students.add("Binh");

        System.out.println(outer.get("A"));
        System.out.println(outer.get("A") == students);
    }
}
```

```bash
javac NestedMapLeakDemo.java
java NestedMapLeakDemo
```

```text
[An, Binh]
true
```

`Map.copyOf` does not deep-copy nested lists. Testing `students.add` detects the alias.

### Design That Severs Aliases at Both Levels

Create **`ImmutableGroupsDemo.java`**:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

final class Groups {
    private final Map<String, List<String>> members;

    Groups(Map<String, List<String>> source) {
        Objects.requireNonNull(source);

        Map<String, List<String>> copy = new HashMap<>();
        for (Map.Entry<String, List<String>> entry :
                source.entrySet()) {
            String key = Objects.requireNonNull(entry.getKey());
            List<String> value =
                    List.copyOf(Objects.requireNonNull(entry.getValue()));
            copy.put(key, value);
        }

        members = Map.copyOf(copy);
    }

    List<String> get(String group) {
        return members.get(group);
    }

    int groupCount() {
        return members.size();
    }
}

public class ImmutableGroupsDemo {
    public static void main(String[] args) {
        List<String> students =
                new java.util.ArrayList<>(List.of("An"));

        Map<String, List<String>> source = new HashMap<>();
        source.put("A", students);

        Groups groups = new Groups(source);

        students.add("Binh");
        source.put("B", List.of("Chi"));

        System.out.println("A=" + groups.get("A"));
        System.out.println("groups=" + groups.groupCount());

        try {
            groups.get("A").add("X");
        } catch (UnsupportedOperationException ex) {
            System.out.println("nested list locked");
        }
    }
}
```

```bash
javac ImmutableGroupsDemo.java
java ImmutableGroupsDemo
```

```text
A=[An]
groups=1
nested list locked
```

The fix snapshots:

1. The `Map` structure with `Map.copyOf`.
2. Each `List<String>` value with `List.copyOf`.
3. Each `String` key/element is immutable.

Therefore, no alias that can mutate logical state is exposed in the example. If the values contain mutable objects instead of String, you must also snapshot each element.

## 21. Getters Returning `Map`/`List`: Should You Return Directly or Return a Copy?

**There is no answer based solely on the getter's name.** It depends on **the actual object type** being stored.

| Internal field | Is returning the field directly from the getter safe for immutability? |
| --- | --- |
| `int[]` mutable array | **No** |
| `ArrayList<String>` mutable | **No** |
| `Collections.unmodifiableList(source)` view over a mutable source that still has an alias | **Not guaranteed** |
| `List.copyOf(List<String>)` with immutable Strings | Usually **yes**, under structural immutability |
| `List.copyOf(List<StringBuilder>)` | **No**, mutable elements |
| `Map.copyOf(Map<String,Integer>)` | Usually **yes**, immutable keys/values |
| `Map.copyOf(Map<String,List<String>>)` if list values are mutable | **No** |
| Properly designed immutable value object | Can return the reference directly |

Returning an **immutable object reference** multiple times does not by itself violate immutability. Defensive copying is only truly needed at a **mutable boundary**; indiscriminate copying complicates the code and wastes resources without providing any benefit if the data is already immutable.

## 22. Checking Through `Iterator`, `ListIterator`, and `Map.Entry`

A getter might not return a collection directly, instead returning an iterator/entry view. Do not forget that these are also **access paths** to internal state.

For example, if a method:

```java
Iterator<String> iterator() {
    return internalMutableList.iterator();
}
```

then the caller can call `iterator.remove()` in states supported by the iterator, modifying the backing list.

With `ListIterator`, the `set`/`add` methods on a mutable list's iterator can also modify the structure.

With `Map.Entry<K,V>` from a mutable `Map.entrySet()`, `entry.setValue(...)` can change the mapping in many implementations.

**The test suite must inspect every public API:** getters, iterators, streams, subLists/views, map entries, arrays returned from conversion methods, and callbacks receiving a mutable object. Do not look only for methods named `set...`.

When storing an unmodifiable snapshot created with `List.copyOf`/`Map.copyOf`, mutating operations through the respective iterator/entry views are also rejected according to the contract of unmodifiable structures. However, a **nested mutable element** can still be modified through an iterator returning that element.

### Concrete Check on an Unmodifiable List

File **`ImmutableIteratorDemo.java`**:

```java
import java.util.Iterator;
import java.util.List;

public class ImmutableIteratorDemo {
    public static void main(String[] args) {
        List<String> values = List.copyOf(List.of("A", "B"));
        Iterator<String> iterator = values.iterator();

        System.out.println(iterator.next());

        try {
            iterator.remove();
        } catch (UnsupportedOperationException ex) {
            System.out.println("iterator removal blocked");
        }

        System.out.println(values.size());
    }
}
```

```bash
javac ImmutableIteratorDemo.java
java ImmutableIteratorDemo
```

```text
A
iterator removal blocked
2
```

The iterator has already moved past the first element, so there is no "remove before next" error; the exception demonstrates that mutation via the iterator is blocked.

## 23. Records with Array/List Components: Not Automatically Deeply Immutable

A Java `record` has final component fields and auto-generated accessors, but it does not automatically copy mutable components.

Create **`BrokenRecordDemo.java`**:

```java
record Numbers(int[] values) {
}

public class BrokenRecordDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};
        Numbers numbers = new Numbers(source);

        source[0] = 99;
        System.out.println(numbers.values()[0]);

        numbers.values()[1] = 77;
        System.out.println(source[1]);
    }
}
```

```bash
javac BrokenRecordDemo.java
java BrokenRecordDemo
```

```text
99
77
```

A record does not automatically clone its constructor parameter, and the `values()` accessor returns the array reference. This code serves as a counterexample: records are **shallowly final**, not automatically deeply immutable.

Another issue: record-generated `equals`/`hashCode` for an array component uses component equality semantics based on array references; two records containing arrays with different references but identical elements are not automatically equal by content.

## 24. Safer Records via a Compact Constructor and Defensive Accessor

File **`SafeRecordDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record SafeNumbers(int[] values) {
    SafeNumbers {
        values = Objects.requireNonNull(values).clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    int at(int index) {
        return values[index];
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class SafeRecordDemo {
    public static void main(String[] args) {
        int[] input = {1, 2};
        SafeNumbers numbers = new SafeNumbers(input);

        input[0] = 99;

        int[] exported = numbers.values();
        exported[1] = 77;

        System.out.println(numbers);
        System.out.println(numbers.at(0));
    }
}
```

```bash
javac SafeRecordDemo.java
java SafeRecordDemo
```

```text
[1, 2]
1
```

In the compact constructor, `values = values.clone()` reassigns the constructor parameter before it is assigned to the component field according to the rules. The custom accessor returns a clone.

**Separate two test criteria:**

- **Immutability:** Input/output mutation does not affect the record state → the example passes.
- **Content equality:** Are two SafeNumbers instances containing two arrays with different identities but identical elements equal? The generated equals **does not automatically compare array elements**, so you must customize equals/hashCode if the domain requires content-based equality.

Do not conclude "immutable" merely because a record class has `final` fields or because `record` generates equals automatically.

## 25. Testing `equals` and `hashCode` of a Class Containing an Array

If an immutable value class defines equality by **array contents**, you should define equals/hashCode over that same data.

File **`ImmutableVectorEqualityDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Vector {
    private final int[] values;

    Vector(int[] input) {
        values = Objects.requireNonNull(input).clone();
    }

    int[] snapshot() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Vector vector)) {
            return false;
        }
        return Arrays.equals(values, vector.values);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }
}

public class ImmutableVectorEqualityDemo {
    public static void main(String[] args) {
        int[] input = {1, 2};
        Vector first = new Vector(input);
        Vector second = new Vector(new int[] {1, 2});

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(
                first.hashCode() == second.hashCode());

        input[0] = 99;
        System.out.println(first.equals(second));

        int[] exported = first.snapshot();
        exported[1] = 77;
        System.out.println(first.equals(second));
    }
}
```

```bash
javac ImmutableVectorEqualityDemo.java
java ImmutableVectorEqualityDemo
```

```text
false
true
true
true
true
```

The test suite checks:

1. Two instances have different references.
2. They are equal by contents when the class explicitly defines this.
3. Equal objects have equal hash codes.
4. Mutating the original input does not change the equals outcome.
5. Mutating the getter snapshot does not change the equals outcome.

**Remember:** For nested arrays, if you use `Arrays.deepEquals`, you must also choose a matching hash function such as `Arrays.deepHashCode` according to the type/contract. Do not use `Arrays.equals` while hashing by array identity, or vice versa.

## 26. Sets with Mutable Elements: A Different Risk from Mutating the Set Structure

Consider a `HashSet<MutableKey>`:

```java
class MutableKey {
    String code;

    MutableKey(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey key
                && java.util.Objects.equals(code, key.code);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hashCode(code);
    }
}
```

Even when creating:

```java
Set<MutableKey> snapshot = Set.copyOf(source);
```

the `MutableKey` elements can still change `code` through an existing reference. The keys' hash/equality changes accordingly, which can make lookup behavior unreliable if the collection implementation depends on stable hash/equality.

Therefore, for an **immutable set of values**, you should store **immutable element types** (for example, `record Key(String code)` with a String component), or deep-snapshot the required data into an immutable type.

**Do not write a test that requires `contains(...)` to strictly return false/true after intentionally breaking hash-key invariants**: the outcome depends on the implementation and internal state. Tests should prove that the new design prevents key state from mutating in that way.

## 27. Deep Copy and Defining "Deep" According to the Data Domain

A deep copy is not just "cloning one more time".

Suppose object A has a Map pointing to Lists, Lists pointing to MutableElements, and MutableElements pointing to buffers. You must determine:

- Which objects belong to **observable state**?
- Which objects are mutable?
- Which aliases might the caller hold?
- Is it necessary to **preserve sharing** among elements when copying?
- Are there cycles in the object graph?
- Are there external resources (socket, thread, file) that cannot be cloned in a "value" sense?
- Can it be converted into a simpler immutable representation?

### Two Strategies

**Strategy A — immutable components early:** Normalize/map each input into immutable strings/records, then use `List.copyOf`/`Map.copyOf`. Usually easier to prove and test.

**Strategy B — convention-based defensive deep copy:** Copy the array/list/map at each level and copy mutable leaf objects. You must account for cycles, shared identity, exceptions, and concurrent mutation.

Do not treat `Object.clone()` as the default "deep immutable" solution. Clone semantics differ across classes; many types do not support cloning or do not provide a safe clone contract.

## 28. Iterator/Stream and Snapshot: Do Not Confuse Observation Times

If a class returns a `Stream` created directly from a backing mutable collection, a stream traversal can observe changes to the backing collection or encounter concurrent modification depending on the collection's behavior. This can make an API look "getter-like" without actually being a snapshot.

If the object wants an immutable snapshot API, a simple approach is to **keep an unmodifiable snapshot from construction** and return a stream from that snapshot.

Example:

```java
final class Tags {
    private final java.util.List<String> tags;

    Tags(java.util.List<String> input) {
        tags = java.util.List.copyOf(input);
    }

    java.util.stream.Stream<String> stream() {
        return tags.stream();
    }
}
```

`Tags` stores a list snapshot; each stream traverses the immutable String elements in the snapshot. However, a stream is a single-use object per the API, and returning a stream is not always necessary: you can return `List<String>` if the contract makes that appropriate.

**In tests**, compare outputs via `List.copyOf(stream.toList())` or deterministic operations, avoiding reliance on the order of `Set`/`HashMap` when there is no ordered contract.

## 29. Concurrent Modification While the Constructor Copies: A Boundary `final` Does Not Solve by Itself

A constructor:

```java
this.items = List.copyOf(input);
```

can be a very good choice when **the input is not mutated concurrently during copying**. However, if another thread is adding/removing elements in the mutable input:

- It can create a race not permitted by the input collection's contract.
- The copy can fail or capture an inconsistent state depending on the collection type.
- A validation that ran before copying might no longer apply to the data actually copied.
- `final` on the resulting field cannot fix a bug that already happened while reading the source.

**Control approaches:**

1. The caller passes a **stable snapshot** or passes only an immutable input.
2. The caller/constructor shares a common synchronization protocol with writers for the snapshot step.
3. Use an API with an appropriate snapshot contract for the concurrent collection type when required.
4. After copying, validate **the exact data to be stored**, not just the source prior to copying.

Do not use a stress test that shows no race over a few runs to prove absolute thread safety. You must design clear happens-before/ownership semantics.

## 30. Checking for Premature Object Publication in the Constructor

A class can snapshot the list properly and still be unsafe if it publishes `this` before initialization finishes.

Anti-pattern example:

```java
class Registry {
    static final java.util.List<Object> ALL =
            new java.util.ArrayList<>();
}

class UnsafeCourse {
    private final java.util.List<String> topics;

    UnsafeCourse(java.util.List<String> input) {
        Registry.ALL.add(this); // Publishes the object too early.
        topics = java.util.List.copyOf(input);
    }
}
```

This is **code illustrating risky behavior**, without a `main`. The compiler may accept assignment of the final field right before the constructor returns, yet another location already holds a `this` reference while `topics` is unassigned and construction is incomplete.

**Safety checklist:**

- Do not register `this` inside the constructor before completion.
- Do not start threads/callbacks that can observe the incomplete instance.
- Do not call overridable methods that rely on subclass state from a superclass constructor.
- Hand out the reference only after invariants have been established.
- For concurrency, use a publication mechanism matching the contract.

**Do not conflate them:** defensive copying protects against *data aliasing*; proper construction/publication protects *object lifecycle/visibility*. A trustworthy immutable object needs both depending on the context.

## 31. Property-Based Reasoning: Covering Multiple Mutation Paths

A basic test only modifies `input[0]`. That does not catch every bug in an object graph. A systematic way to expand coverage is to build an **object-and-access-path matrix**:

| State type | Before construction | After construction via input alias | Via getter | Via nested element |
| --- | --- | --- | --- | --- |
| `int[]` | Copy values | `input[i]=...` | `getter[i]=...` | Not applicable |
| `int[][]` | Copy outer + inner | Modify `input[i][j]`; replace row | Modify `getter[i][j]`; replace row | Inner arrays |
| `List<String>` | Snapshot structure | `source.add/remove` | `getter.add/set/remove` | Immutable String |
| `List<Mutable>` | Snapshot elements | Modify original element object | Modify element obtained from getter | Nested fields |
| `Set<ImmutableKey>` | Snapshot structure | `source.add/remove` | `getter.add/remove` | Immutable keys |
| `Map<K,List<V>>` | Copy map + values | Mutate original map/list | Mutate returned map/list | Mutable V if present |
| Record + `int[]` | Copy constructor component | Mutate source array | Mutate accessor output | Array |

### How to Test When Using JUnit

An equivalent test suite can be written using JUnit 5 assertions such as `assertEquals`, `assertArrayEquals`, and `assertThrows`. However, so that this document **runs immediately with JDK 17 without dependencies**, the examples use a `check` helper and `main`.

Regardless of the framework, you must test the same **behavior**, not just the test annotation names.

## 32. Comprehensive Test Suite for a Class Containing Both Arrays and Collections

Create **`ImmutabilityAuditDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.Objects;

final class CourseData {
    private final int[] scores;
    private final List<String> topics;
    private final Map<String, List<String>> groups;

    CourseData(int[] scores, List<String> topics,
               Map<String, List<String>> groups) {
        this.scores = Objects.requireNonNull(scores).clone();
        this.topics = List.copyOf(Objects.requireNonNull(topics));

        Map<String, List<String>> copy = new HashMap<>();
        for (Map.Entry<String, List<String>> entry :
                Objects.requireNonNull(groups).entrySet()) {
            String key = Objects.requireNonNull(entry.getKey());
            List<String> value =
                    List.copyOf(Objects.requireNonNull(entry.getValue()));
            copy.put(key, value);
        }
        this.groups = Map.copyOf(copy);
    }

    int[] scores() {
        return scores.clone();
    }

    List<String> topics() {
        return topics;
    }

    List<String> group(String name) {
        return groups.get(name);
    }

    int groupCount() {
        return groups.size();
    }
}

public class ImmutabilityAuditDemo {
    static void check(boolean ok, String test) {
        if (!ok) {
            throw new AssertionError(test);
        }
    }

    public static void main(String[] args) {
        int[] scores = {10, 20};
        List<String> topics = new ArrayList<>(List.of("Class"));
        List<String> students = new ArrayList<>(List.of("An"));
        Map<String, List<String>> groups = new HashMap<>();
        groups.put("A", students);

        CourseData data = new CourseData(scores, topics, groups);

        // Attack 1: Mutate caller-owned inputs.
        scores[0] = 99;
        topics.add("Object");
        students.add("Binh");
        groups.put("B", List.of("Chi"));

        check(Arrays.equals(data.scores(), new int[] {10, 20}),
                "score ingress");
        check(data.topics().equals(List.of("Class")),
                "topics ingress");
        check(data.group("A").equals(List.of("An")),
                "nested list ingress");
        check(data.groupCount() == 1, "map ingress");

        // Attack 2: Mutate returned array.
        int[] exported = data.scores();
        exported[1] = 77;
        check(data.scores()[1] == 20, "score egress");

        // Attack 3: Mutate exposed immutable lists.
        boolean topicsRejected = false;
        try {
            data.topics().add("Invalid");
        } catch (UnsupportedOperationException ex) {
            topicsRejected = true;
        }
        check(topicsRejected, "topics egress");

        boolean groupRejected = false;
        try {
            data.group("A").set(0, "Other");
        } catch (UnsupportedOperationException ex) {
            groupRejected = true;
        }
        check(groupRejected, "group egress");

        check(data.topics().equals(List.of("Class")),
                "topics final state");
        check(data.group("A").equals(List.of("An")),
                "group final state");

        System.out.println("immutability audit PASS");
    }
}
```

```bash
javac ImmutabilityAuditDemo.java
java ImmutabilityAuditDemo
```

```text
immutability audit PASS
```

**Why is this audit more valuable than a single getter test?**

1. Includes both a primitive array and nested collections.
2. Mutates **all input aliases** retained beforehand.
3. Checks that the array getter returns a copy and does not expose the internal array.
4. Checks that List/Map-derived lists from getters reject mutator operations.
5. Checks that the overall final state still matches the snapshot at construction.

**Explicitly stated limitation:** Elements in `topics` and `groups` are immutable Strings; this code **does not support** arbitrary mutable elements. If you change the type to `List<StringBuilder>` while only using `List.copyOf`, you will need a test that mutates a nested builder and a new copying strategy.

## 33. Checking Errors in Constructors: Missing Data and Null Elements

An immutable class must ensure **it does not return a falsely valid instance** when the input violates the contract.

For example, with `List.copyOf`:

- `null` collection reference → error.
- `null` element inside the collection → error.
- Inputs with their own data validity requirements must be validated by the constructor, for example negative scores or duplicate codes.
- A snapshot does not replace validation: a copied list can still contain empty Strings if the domain does not allow it.

### Demo: Validation Before Publication

File **`ImmutableValidatedNamesDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Names {
    private final List<String> values;

    Names(List<String> input) {
        Objects.requireNonNull(input);

        List<String> copy = new ArrayList<>(input);
        for (String item : copy) {
            if (item == null || item.isBlank()) {
                throw new IllegalArgumentException("invalid name");
            }
        }

        values = List.copyOf(copy);
    }

    List<String> values() {
        return values;
    }
}

public class ImmutableValidatedNamesDemo {
    public static void main(String[] args) {
        Names ok = new Names(List.of("An", "Binh"));
        System.out.println(ok.values());

        try {
            new Names(List.of("An", ""));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid input rejected");
        }
    }
}
```

```bash
javac ImmutableValidatedNamesDemo.java
java ImmutableValidatedNamesDemo
```

```text
[An, Binh]
invalid input rejected
```

The constructor creates an `ArrayList` copy first, validates on the very copy that will be stored, and then converts it to an unmodifiable list. If the input is mutated concurrently during copying, a separate synchronization/handoff contract is still required.

**Do not forget business-level atomicity:** If a constructor also writes a file, registers a listener, or calls an external API before throwing an exception, there will be side effects that do not automatically roll back. Immutable fields do not guarantee transactional construction.

## 34. Not Every Mutation Attempt Has to Throw an Exception

There are at least two safe approaches:

**(A) The getter returns a separate mutable copy.** The caller is allowed to modify the copy, while the internal object remains unchanged.

```java
int[] values() {
    return internal.clone();
}
```

**(B) The getter returns an immutable/unmodifiable snapshot.** Mutator calls by the caller can be rejected.

```java
List<String> values() {
    return List.copyOf(internal);
}
```

Therefore, you should not write a generic test that always demands every mutation on a returned value throw `UnsupportedOperationException`. For arrays, `copy[0] = 10` is allowed; **what matters is that it does not alter the internal state**.

Tests must derive from **the getter's contract**:

- If the getter promises a fresh mutable snapshot → modifications may succeed on the snapshot, while the immutable object remains unchanged.
- If the getter promises an unmodifiable view/snapshot → mutators are prohibited, yet you must check that the backing data cannot be modified externally.
- If the getter promises an immutable value reference → sharing the same reference may be right, with no need for pointless copying.

## 35. Try Counterexamples Before Trusting Modifiers

A fairly common anti-pattern:

```java
final class Configuration {
    private final List<String> names;

    Configuration(List<String> names) {
        this.names = names;
    }

    List<String> names() {
        return java.util.Collections.unmodifiableList(names);
    }
}
```

The getter **blocks modification through the returned view**, yet the constructor retained a mutable input alias. The caller can still call `input.add(...)` after creation.

To **catch the bug**, the test must:

1. Pass a genuinely mutable `ArrayList`.
2. Record the state after construction.
3. Mutate `input`.
4. Read the getter again.
5. Compare against the expected snapshot, rather than only trying `getter.add`.

**Another example:** the constructor copies the list structure, but the elements are mutable objects; you must mutate an element through the reference held by the caller.

Immutability is not solved by "adding `final` everywhere" or "wrapping getters with `unmodifiableList`", but requires verifying all references capable of mutating observable state.

## 36. Testing That `equals`/`hashCode` Remain Unchanged After External Mutations

For an **immutable value class**, if equality/hashCode is based on logical state, the result must remain stable when the caller attempts to modify inputs or snapshots.

The `Vector` example from the earlier section:

```java
Vector a = new Vector(new int[] {1, 2});
Vector b = new Vector(new int[] {1, 2});
```

This is a code snippet using the `Vector` class declared in the runnable example in section 25.

You can record:

- Initial `a.equals(b)`.
- Initial `a.hashCode()`.
- Then modify the source array passed into `a` (if the reference is still held).
- Modify the array returned by the `a.snapshot()` getter.
- Re-check equality/hashCode and the contents.

**However:** if the class intentionally uses **identity equality** rather than value equality, having hashCode/equals not compare contents does not by itself make it mutable. Distinguish **the immutability contract** from **the value-equality contract**.

## 37. Common Mistakes

| Mistake | Why is it insufficient? | Additional check required |
| --- | --- | --- |
| "A `private final int[]` field is immutable" | Array slots are still mutable | Modify input and getter arrays |
| "`final class` prevents all mutation" | Methods/objects inside may still be mutable | Audit all mutation paths |
| "Returning a clone from the getter is enough" | The constructor may retain an input alias | Mutate source after construction |
| "Cloning in the constructor is enough" | The getter may return the internal reference | Mutate the getter's return value |
| "`matrix.clone()` is a deep copy" | Inner arrays are still aliased | Modify `source[i][j]` |
| "`array.clone()` deep-copies elements" | Object references are still shared | Mutate a nested mutable element |
| "`List.copyOf` deep-freezes elements" | Only the structure is unmodifiable | Mutate an element alias |
| "`unmodifiableList(source)` is a snapshot" | The backing source can still change | Mutate source, read view |
| "Cannot call `add`, so the object is immutable" | It may be mutable through another alias | Test ingress/nested aliases |
| "Getters must always create a new object" | Immutable objects can be shared safely | Check behavior, do not enforce `==` |
| "Every mutation via a getter must throw" | A mutable copy from a getter can be safely modified | Check that the original stays unchanged |
| "`Set.copyOf` makes mutable keys immutable" | Key objects remain mutable | Test nested key semantics |
| "`Map.copyOf` clones nested lists" | Values share references | Mutate a backing nested list |
| "A record containing an array is automatically deeply immutable" | Accessor/constructor can hold aliases | Test record input and output |
| "Record array equals automatically compares contents" | Arrays default to identity equality | Customize equals/hash if needed |
| "Set iteration order is fixed" | Not guaranteed in general | Test membership/size instead of string order |
| "Passing one stress test without errors means thread-safe" | Races depend on scheduling | Design synchronization/ownership |
| "Copying after validation is always concurrency-safe" | Source can change between steps | Take a stable snapshot; validate the snapshot |
| "`final` protects an object published mid-constructor" | `this` can escape early | Audit constructors/callbacks/threads |
| "An immutable object must have custom equals" | Equality depends on the domain | Decide on a specific contract |
| "Testing only the happy path is enough" | Null/blank/invalid inputs can slip through | Test constructor failures |
| "A `HashSet` holding a mutable key is still safe" | Equality/hash can change | Immutable keys and tests |
| "Deep copy always means cloning the whole graph" | Cycles/resources/ownership may exist | Define the graph's semantics |

## 38. Practice Exercises

**Exercise 1.** Write a class containing `private final byte[] payload`. Design two tests proving that the caller cannot mutate it through the input or the getter.

*Solution outline:* The constructor stores `payload.clone()` and the getter returns `payload.clone()`; then mutate both the input and the getter's clone, and read a checksum/`Arrays.equals` to verify that the original stays intact.

**Exercise 2.** For `List<StringBuilder>`, is using `List.copyOf` enough?

*Answer:* No. Mutating a StringBuilder through an external alias still changes the text. Convert them into List<String> snapshots or appropriately deep-copy the mutable leaves.

**Exercise 3.** For `Map<String,List<String>>`, when `Map.copyOf` is already used, what is still missing?

*Answer:* You need to snapshot each inner list with `List.copyOf` or an equivalent mechanism.

**Exercise 4.** For `int[][]`, why does checking `input != copied` alone not prove immutability?

*Answer:* Inner arrays can still share the same reference. You must check `input[i] != copied[i]` when the contract requires copying and mutate nested slots.

**Exercise 5.** Does `Collections.unmodifiableList(input)` allow the caller to `add` through the view? Does it block someone holding the original `input`?

*Answer:* Through the view it is blocked; it does not block mutation through the backing input reference.

**Exercise 6.** Can the list returned by `List.copyOf` reuse the input reference?

*Answer:* The API can reuse unmodifiable inputs; you must not assume a different identity every time. Test semantic immutability, not an unguaranteed reference identity.

**Exercise 7.** Create a record with an `int[]`. Which two mutation directions must be tested?

*Answer:* Modifying the constructor argument and modifying the array returned by the accessor. If using record-generated equality, you must check array semantics.

**Exercise 8.** An array returned from a getter can be modified without changing the object; does this violate immutability?

*Answer:* No. The getter can return an independent mutable defensive copy.

**Exercise 9.** Why can `HashSet<MutableKey>` break semantics even when the Set structure is never modified?

*Answer:* Mutable key fields change `equals/hashCode` while residing in the collection.

**Exercise 10.** Does a class holding `List<LocalDate>` and storing a `List.copyOf` snapshot have the same mutable-element risk as StringBuilder?

*Answer:* `LocalDate` is an immutable value type; with the proper contract and a stable input snapshot, there is no element-mutation path like StringBuilder.

**Exercise 11.** If the constructor validates an input list and another thread modifies the source before `List.copyOf`, what can happen?

*Answer:* The validation no longer applies to the actual data being stored; you need a stable copy, snapshot validation, and synchronization/ownership under concurrent mutation.

**Exercise 12.** Can an immutable class have a getter that returns the stored `List.copyOf` list itself?

*Answer:* Yes, when elements/keys/values are immutable per the contract and the snapshot has no mutable alias path that alters observable state.

**Exercise 13.** For `Map<String, MutableValue>`, is `Map.copyOf` enough?

*Answer:* No. You need to copy/convert each mutable value into an immutable representation or design different visibility/ownership.

**Exercise 14.** Does an array of mutable objects need each element to be cloned?

*Answer:* If the caller still has the ability to mutate elements and that alters observable state, you must copy/convert elements according to the contract. Cloning only the outer array is shallow.

**Exercise 15.** Can immutability be tested solely by comparing `hashCode`?

*Answer:* No. Hashes can have collisions, and not every immutable class computes its hash from its entire state; you must test observable values and mutation paths.

## 39. QA Checklist Before Claiming a Class Containing Arrays/Collections Is Immutable

- [ ] Have all fields and **nested mutable components** been listed?
- [ ] Has the object's observable state been identified?
- [ ] Do instance fields use `private final` where appropriate?
- [ ] Does the class need `final` to prevent subclasses from breaking the contract?
- [ ] Has the constructor initialized everything **completely and validly** before returning?
- [ ] Are all input arrays copied at ingress?
- [ ] Have multidimensional arrays copied the necessary inner arrays?
- [ ] Have object arrays containing mutable elements been deep-snapshotted/converted per the contract?
- [ ] Are mutable List/Set/Map inputs structurally snapshotted?
- [ ] Has `List.copyOf` been distinguished from a `Collections.unmodifiableList(source)` view?
- [ ] If using a view, can the backing collection be mutated from elsewhere?
- [ ] Are elements/keys/values immutable, or do aliases to mutable objects still exist?
- [ ] Do getters avoid returning internal mutable arrays/maps/lists?
- [ ] If a getter returns an unmodifiable collection, have you tried mutating via the input alias?
- [ ] If a getter returns a mutable copy, have you tried mutating the copy and re-reading the original?
- [ ] If a getter returns nested collections, have you tried mutating inner elements?
- [ ] Do iterators, list iterators, map entries, or subviews expose a way to mutate?
- [ ] If using a record with an array/list component, do the constructor and accessor perform defensive copying?
- [ ] If equality is content-based, are equals/hashCode defined consistently?
- [ ] Are mutable key/element hashes prevented from changing while the object is used in a Set/Map?
- [ ] Does the constructor define a null/blank/invalid-input policy?
- [ ] Are all constructor error paths tested so no complete instance violating invariants is returned?
- [ ] Does the constructor prevent `this` from escaping early?
- [ ] Has concurrent mutation of the source during snapshotting been considered?
- [ ] Do tests avoid relying on `List.of` identity or unguaranteed iteration order?
- [ ] Are there tests for ingress, egress, nested aliases, and final observable state?
- [ ] Do the Java 17+ examples have matching file/public class names, `javac`/`java` commands, and deterministic stdout?

---

**Final takeaway:** When a class contains **arrays or collections**, `private final` only protects against reassigning the **reference**, and does not automatically make the entire object graph immutable. To **test** immutability, try modifying **input data after the constructor**, **values returned from getters**, **nested mutable elements**, and **backing collections** through every existing alias. For primitive arrays, you typically clone in both the constructor and the getter; for multidimensional arrays or object arrays, you must snapshot the appropriate mutable levels. For collections, `List.copyOf`/`Set.copyOf`/`Map.copyOf` create unmodifiable structures but do not freeze mutable elements, whereas `Collections.unmodifiableList` on a mutable source is a **view**, not automatically a snapshot. Immutability is **a contract about observable state**, not a single modifier — and a proper test suite must prove that contract across **ingress, egress, and nested aliases**.
