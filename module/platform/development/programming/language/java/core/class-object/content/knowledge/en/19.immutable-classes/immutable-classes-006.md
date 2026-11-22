# Shallow Immutability and Deep Immutability in Java

In object-oriented programming, **immutability** is the property of an object whose **observable state** does not change after it has been completely constructed. An immutable object is usually easier to reason about, safer to share, and well-suited to serve as a *value object*. However, in Java, declaring fields as `private final` **is not sufficient to conclude** that the entire object is immutable.

Consider an example:

```java
final class Team {
    private final List<StringBuilder> members;

    Team(List<StringBuilder> members) {
        this.members = members;
    }
}
```

`members` is a **final reference**: the constructor assigns it once, and code inside `Team` cannot reassign that field. However:

- The caller can retain a reference to the `List` itself and add or remove elements.
- The caller can retain a reference to a `StringBuilder` and modify its contents.
- If a getter returns the list or a mutable element, users can change the state that `Team` observes.
- `final class` only forbids inheritance, not modifying the contents of the list.

This is the central theme of this article: **“not changing the reference”**, **“not being able to modify the collection structure through the API”**, and **“not being able to change deep state in the object graph”** are three different levels of guarantee.

This guide targets **Java 17+** and covers concepts, reference mechanics, shallow/deep copying, pitfalls with arrays, collections, and records, designing defensive copies at both boundaries, immutable value objects, concurrency scenarios, performance trade-offs, standalone runnable programs with `javac`/`java` commands, and exercises with answers.

## 1. Three Easily Confused Layers: final, Shallow Immutability, Deep Immutability

### 1.1. The `final` Reference

```java
final List<String> names = new ArrayList<>();
names.add("An");
// names = new ArrayList<>(); // Does not compile: reassigning a final variable.
```

`final` forbids **reassigning the variable**, but does not forbid calling methods that mutate **the referenced object**. For a field, `private final` protects against reassigning the field after initialization; it does not lock all objects reachable from the field.

### 1.2. Shallow Immutability

The term *shallow immutable* can have several usages in practical literature. A useful phrasing in this article is:

> The direct components/reference relationships of the object are fixed according to the API, but mutable objects **referenced deeper** can still change.

Record example:

```java
record Group(List<StringBuilder> members) {
}
```

`Group` has no setter for the `members` component, yet `group.members().get(0).append("!")` can change the contents of the `StringBuilder` object. Therefore, considering all observable data, Group **is not a deeply immutable object**.

### 1.3. Deep Immutability

An object is deeply immutable when, according to the state boundary it exposes, **there is no valid access path to modify the observable state of even its dependent components**, including via external aliases.

Simple example:

```java
record Address(String city, String street) {
}
```

Both components are immutable `String`s; the record has no setters. After creation, a typical `Address` can be regarded as an **immutable value object** with respect to those two components.

**There is no `deep final` modifier in Java**. Deep immutability comes from **designing the entire object graph**, choosing immutable components, API boundaries, and how copy/ownership is protected.

## 2. Comparison Map

| Property | Example | What Is Guaranteed | What Is Not Guaranteed |
| --- | --- | --- | --- |
| `final` reference variable | `final List<T> a` | `a` cannot be reassigned | List/element contents remain unchanged |
| `private final` field | `private final int[] data` | Field cannot be reassigned after initialization | Array elements remain unchanged |
| `final` class | `final class X` | `X` cannot be subclassed | State of `X` remains unchanged |
| Collection unmodifiable view | `Collections.unmodifiableList(source)` | Cannot mutate through the view | The source can be mutated |
| Shallow unmodifiable snapshot | `List.copyOf(source)` | Resulting list disallows structural modification via API; detached from the mutable source | Mutable elements still change |
| Immutable elements + snapshot | `List.copyOf(List<String>)` with valid input | Collection structure and the `String`s cannot be modified | Other mutable objects outside the model |
| Defensive deep copy | Cloning each row of `int[][]` | Caller cannot modify internals via array aliases | Thread-safety of other mutable components |
| Immutable value graph | `record Point(int x,int y)` and owner does not expose mutable state | Observable value state remains unchanged | Enclosing business entity is not necessarily immutable |

A quick way to check:

1. **Are there setters/operations that mutate state directly?**
2. **Does the constructor retain an alias to mutable input?**
3. **Does a getter return an internal mutable reference?**
4. **Can elements/nested objects be mutated?**
5. **Does the object observe external mutable data without copying?**

If even a single path allows changing the observable state of an object whose contract promises immutability, the design has failed to achieve deep immutability.

## 3. Distinguishing “State” from “Identity” and “References”

A **reference variable** can point to an object; that object can contain other references.

```text
variable group ─────► Group object
                         │ final members
                         ▼
                      List object
                         │
                         ▼
                    StringBuilder object
                         │ mutable chars
                         ▼
                      "An"
```

If `Group.members` is `final`, the **Group → List** arrow cannot be reassigned via that field. However, the contents of the **List** or **StringBuilder** can still change.

This is the meaning of an **object graph**: a set of objects connected through references. You need to look at the entire relevant state graph, not just the top-level field declaration line.

### Sharing the Same Object (Aliasing)

```java
StringBuilder builder = new StringBuilder("An");
List<StringBuilder> input = new ArrayList<>();
input.add(builder);

Group group = new Group(input);
```

If Group holds `input` directly, three access paths can affect the representation of the same data:
- `input.add(...)`.
- `builder.append(...)`.
- `group.members().get(0).append(...)` if the getter opens an access path.

**Alias** is when multiple references point to the same object. Simply creating another variable or a list containing an object **does not** create a copy of that object.

## 4. What Does Java `final` Protect?

`final` can be used with:
- Local variables;
- Method parameters;
- Instance fields;
- Static fields;
- Methods (prevents overriding);
- Classes (prevents subclassing).

In this article, we are mainly interested in **final fields/references**.

```java
final int age = 20;
// age = 21; // Invalid.

final StringBuilder name = new StringBuilder("An");
name.append(" Bình"); // Valid.
```

**For a final primitive**, the primitive value cannot be reassigned through that variable. **For a final reference**, the reference cannot be reassigned, but the referent can be mutable.

When fields are `final`, the Java Memory Model also provides certain special guarantees regarding **initialization safety** if the object is properly constructed and `this` does not escape before the constructor finishes. However:

**Final-field semantics do not turn an `ArrayList` or `int[]` into thread-safe/immutable** and do not make changes occurring after construction automatically synchronized.

## 5. Runnable Example: `final` Does Not Mean Deep Immutability

Save **`FinalReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Catalog {
    private final List<String> names = new ArrayList<>();

    void add(String name) {
        names.add(name);
    }

    String description() {
        return names.toString();
    }
}

public class FinalReferenceDemo {
    public static void main(String[] args) {
        final Catalog catalog = new Catalog();

        catalog.add("Java");
        System.out.println(catalog.description());

        catalog.add("SQL");
        System.out.println(catalog.description());

        // catalog = new Catalog(); // Compile error.
    }
}
```

Run on Java 17+:

```bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
```

**Stdout:**

```text
[Java]
[Java, SQL]
```

Even though `catalog` in `main` and the `names` field in Catalog both have fixed references, the Catalog object still **changes state via `add`**. `final` is not a tool to automatically make an object immutable.

## 6. What Is a Shallow Copy?

A **shallow copy** copies the outer-layer structure while still **sharing references to the inner object elements**.

Example:

```java
List<StringBuilder> original = new ArrayList<>();
original.add(new StringBuilder("An"));

List<StringBuilder> shallow = new ArrayList<>(original);
```

`original` and `shallow` are **two different List objects**. However:

```java
original.get(0) == shallow.get(0) // true
```

because they reference the same `StringBuilder`.

As a result:
- Adding/removing elements in one list does not automatically add/remove elements in the other list.
- Modifying a **StringBuilder element** through one list is visible to the other list.
- Copying only the outer layer **is not sufficient** if the requirement is for the snapshot to be deeply immutable.

### Distinguishing Immutable from Copy

An object can be immutable **without needing** to create a new copy when shared; for example, the same `String` held by multiple lists is normally safe regarding mutation.

An object can be shallowly copied, yet **both the original and the copy remain mutable**.

**Copying** is about the relationship between two states/objects; **immutability** is about whether state can change. They are related, but not synonymous.

## 7. Program: Shallow Copying Does Not Detach Mutable Elements

Save **`ShallowCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ShallowCopyDemo {
    public static void main(String[] args) {
        StringBuilder element = new StringBuilder("An");

        List<StringBuilder> original = new ArrayList<>();
        original.add(element);

        List<StringBuilder> copy = new ArrayList<>(original);

        System.out.println(original == copy);
        System.out.println(original.get(0) == copy.get(0));

        copy.add(new StringBuilder("Bình"));
        original.get(0).append("!");

        System.out.println("original = " + original);
        System.out.println("copy = " + copy);
    }
}
```

```bash
javac -encoding UTF-8 ShallowCopyDemo.java
java ShallowCopyDemo
```

**Stdout:**

```text
false
true
original = [An!]
copy = [An!, Bình]
```

- Adding Bình to `copy` does not make `original` longer.
- Changing `element` to `An!` affects the output in **both lists**.
- There is no race condition in the example: all operations run sequentially on a single thread.

## 8. `Collections.unmodifiableList` Is a View, Not a Snapshot

`Collections.unmodifiableList(source)` creates a **wrapper view** that forbids mutating the collection **through the wrapper**, but if external code still holds a reference to `source`, changes to `source` are still reflected through the view.

```java
List<String> source = new ArrayList<>();
source.add("A");

List<String> view = Collections.unmodifiableList(source);
source.add("B");
System.out.println(view); // [A, B]
```

Therefore, the term “unmodifiable” is not synonymous with “immutable snapshot”.

Key points to remember:

- `view.add(...)` → `UnsupportedOperationException`.
- `source.add(...)` → allowed because source is mutable.
- `view` sees data changes from source.
- If elements are mutable, they can still change through aliases.

### Why Is an Unmodifiable View Still Useful?

When source is owned and mutated in a controlled manner by an object, a view can provide **read-only access through the client API** so that users cannot arbitrarily add or remove elements.

However, if the contract requires **a snapshot that does not change after being retrieved**, an independent snapshot must be created instead of just an unmodifiable view over a live backing collection.

## 9. Program: A View Changes Alongside the Backing List

Save **`UnmodifiableViewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableViewDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> view =
                Collections.unmodifiableList(source);

        System.out.println("before = " + view);

        source.add("B");
        System.out.println("after = " + view);

        try {
            view.add("C");
        } catch (UnsupportedOperationException error) {
            System.out.println("view rejects mutation");
        }
    }
}
```

```bash
javac -encoding UTF-8 UnmodifiableViewDemo.java
java UnmodifiableViewDemo
```

**Stdout:**

```text
before = [A]
after = [A, B]
view rejects mutation
```

Note: `view` still has the same elements as the backing source after source is modified. Even though the wrapper blocks mutators, it **is not a snapshot**.

## 10. `List.copyOf` Creates an Outer-Layer Unmodifiable Snapshot

With a regular mutable source:

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> snapshot = List.copyOf(source);

source.add("B");
System.out.println(snapshot); // [A]
```

`List.copyOf` returns an **unmodifiable List** containing the elements in the source order at the time of copying. It does not reflect subsequent structural changes to the mutable source.

**However:**
- The copy is **shallow** for element objects.
- `List.copyOf` **does not allow null elements**; it can throw `NullPointerException` if source contains null.
- It **may reuse** an input list that is already a suitable unmodifiable implementation; you should not assert that the method always allocates a new object.
- When elements are `String`/immutable value objects and have no hidden mutable state, the snapshot can be sufficient for deep immutability according to the model.

### Differences from `Collections.unmodifiableList`

| Creation Method | Changing Source Structure Afterward? | Mutate Through Result? | Are Mutable Elements Deep-Copied? |
| --- | --- | --- | --- |
| `Collections.unmodifiableList(source)` | View usually reflects the changes | No | No |
| `List.copyOf(source)` | Snapshot does not reflect subsequent mutations of the mutable source | No | No |
| `new ArrayList<>(source)` | New list is structurally detached from the source | Yes | No |
| Custom deep copy | Depends on implementation | Depends on exposed API | Yes, if all mutable layers are copied |

## 11. Program Comparing Three List Variants Simultaneously

Save **`ListVariantsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListVariantsDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> view =
                Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);
        List<String> mutableCopy = new ArrayList<>(source);

        source.add("B");
        mutableCopy.add("C");

        System.out.println("source = " + source);
        System.out.println("view = " + view);
        System.out.println("snapshot = " + snapshot);
        System.out.println("mutableCopy = " + mutableCopy);
    }
}
```

```bash
javac -encoding UTF-8 ListVariantsDemo.java
java ListVariantsDemo
```

**Stdout:**

```text
source = [A, B]
view = [A, B]
snapshot = [A]
mutableCopy = [A, C]
```

A very practical lesson: you cannot look at a variable name such as `snapshot` or `view` to infer behavior; you must examine the **API that created the collection** and the **mutability of the elements**.

## 12. Shallow Immutability of a Collection Containing Mutable Elements

`List.copyOf` cannot prevent a mutable element from being modified through another reference.

```java
StringBuilder builder = new StringBuilder("A");
List<StringBuilder> source = new ArrayList<>();
source.add(builder);

List<StringBuilder> snapshot = List.copyOf(source);
builder.append("!");

System.out.println(snapshot); // [A!]
```

The snapshot list still has a fixed structure, but the element's representation changes.

Similarly:
- `List<Date>` with mutable `java.util.Date`;
- `List<int[]>` because arrays are mutable;
- `Map<String, List<String>>` if values contain mutable lists;
- `Set<MutableUser>` if User has setters;
- `List<AtomicInteger>` because the atomic object is mutable.

**A structure cannot be called “deeply immutable” just because the outer collection is unmodifiable.**

### An Important Test Question

> If the caller holds a reference to an element and calls a mutator on that element, does the value exposed by the owner change?

If the answer is “yes”, the owner does not achieve deep immutability with respect to the state that includes that element.

## 13. Example: `List.copyOf` Does Not Copy `StringBuilder`

Save **`ShallowSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ShallowSnapshotDemo {
    public static void main(String[] args) {
        StringBuilder item = new StringBuilder("Java");

        List<StringBuilder> source = new ArrayList<>();
        source.add(item);

        List<StringBuilder> snapshot = List.copyOf(source);

        source.add(new StringBuilder("SQL"));
        item.append(" 17");

        System.out.println("source = " + source);
        System.out.println("snapshot = " + snapshot);

        try {
            snapshot.clear();
        } catch (UnsupportedOperationException error) {
            System.out.println("structure locked");
        }
    }
}
```

```bash
javac -encoding UTF-8 ShallowSnapshotDemo.java
java ShallowSnapshotDemo
```

**Stdout:**

```text
source = [Java 17, SQL]
snapshot = [Java 17]
structure locked
```

The snapshot structure is independent of new element additions to source, but the **mutable `StringBuilder` is the same object** in both lists.

## 14. What Is a Deep Copy?

A **deep copy** creates new state and separates the mutable objects relevant to the snapshot, rather than copying only the outer reference.

For a list of builders:

```java
List<StringBuilder> deep = new ArrayList<>();

for (StringBuilder sourceItem : source) {
    deep.add(new StringBuilder(sourceItem.toString()));
}
```

This is a deep copy **for the specific object graph consisting of the list and its StringBuilder elements**, not a general-purpose deep copy algorithm for any Java object.

The concept depends on **the model and its boundaries**:
- Immutable objects like `String` usually **do not need to be copied**.
- Entities shared by identity probably **should not be copied** if copying breaks domain semantics.
- Mutable objects that need to be independent must have all relevant mutable components copied.
- Graphs with shared aliases/cycles require an algorithm that preserves identity relationships when needed.

**Deep copy does not have a general `Object.deepCopy()` method in Java.** You design copying according to the data types and the class contract.

## 15. Program: Copying a List and Copying Each Mutable Element

Save **`DeepCopyBuildersDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DeepCopyBuildersDemo {
    private static List<StringBuilder> deepCopy(
            List<StringBuilder> original) {

        List<StringBuilder> result = new ArrayList<>();

        for (StringBuilder builder : original) {
            result.add(new StringBuilder(builder.toString()));
        }

        return result;
    }

    public static void main(String[] args) {
        StringBuilder item = new StringBuilder("An");
        List<StringBuilder> source = new ArrayList<>();
        source.add(item);

        List<StringBuilder> shallow = new ArrayList<>(source);
        List<StringBuilder> deep = deepCopy(source);

        item.append("!");
        shallow.add(new StringBuilder("Bình"));

        System.out.println("source = " + source);
        System.out.println("shallow = " + shallow);
        System.out.println("deep = " + deep);
        System.out.println(
                source.get(0) == deep.get(0));
    }
}
```

```bash
javac -encoding UTF-8 DeepCopyBuildersDemo.java
java DeepCopyBuildersDemo
```

**Stdout:**

```text
source = [An!]
shallow = [An!, Bình]
deep = [An]
false
```

Because the deep copy has a new `StringBuilder`, mutating the old builder does not change the builder inside `deep`. However, `deep` in the example is still a **mutable ArrayList** containing mutable builders; it **is a deep copy**, not an immutable object!

This is a key distinction: **deep copying is an operation that creates an independent copy; it does not automatically guarantee that the copy cannot be mutated**.

## 16. Designing an Immutable Object: Closing Both Boundaries

A class striving for deep immutability needs to protect:
- **Input boundary:** the constructor/factory does not retain mutable aliases that the caller continues to modify.
- **Output boundary:** getters/accessors do not return direct references to mutable internal state.
- **Internal methods:** the class does not provide operations that modify state promised to remain fixed.
- **Nested state:** elements/children capable of mutating must be immutable or safely copied/encapsulated.
- **Subclass boundary:** subclasses must not be allowed to violate invariants of the base contract; make it `final` or design inheritance deliberately.

Example of a class containing a primitive array:

```java
final class IntSeries {
    private final int[] values;

    IntSeries(int[] source) {
        this.values = source.clone();  // Copy on input.
    }

    int[] values() {
        return values.clone();         // Copy on output.
    }
}
```

Both calls to `clone()` **serve a purpose**. If either one is omitted, the caller has a path to modify the internal array.

## 17. Mistake 1: Only a `final` Field, No Defensive Copy

```java
final class UnsafeScores {
    private final int[] values;

    UnsafeScores(int[] source) {
        values = source; // Wrong if deep immutability is needed.
    }

    int[] values() {
        return values;
    }
}
```

Two ways to modify it:
1. The caller changes `source[0]` after the constructor finishes.
2. The caller retrieves `values()` and modifies an element.

The `values` field still points to the same array, yet **the contents of the array have changed**.

### Mistake 2: Copying on Input but Leaking on Output

```java
UnsafeScores(int[] source) {
    values = source.clone();
}

int[] values() {
    return values; // Still exposes the internal mutable array.
}
```

The input is detached from the caller, but the getter returns an internal alias. The caller can still modify it.

### Mistake 3: Not Exposing the Array but Failing to Copy on Input

```java
UnsafeScores(int[] source) {
    values = source; // The caller still owns an alias.
}

int[] values() {
    return values.clone();
}
```

The getter is safer, but the caller can still modify the original `source` externally.

**Both sides must be protected** when a class needs to commit to an immutable snapshot.

## 18. Program: Copying an Array on Both Input and Output

Save **`ImmutableScoresDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class ImmutableScores {
    private final int[] scores;

    ImmutableScores(int[] source) {
        scores = Objects.requireNonNull(source).clone();
    }

    int[] scores() {
        return scores.clone();
    }

    int sum() {
        int result = 0;
        for (int score : scores) {
            result += score;
        }
        return result;
    }

    @Override
    public String toString() {
        return "ImmutableScores" + Arrays.toString(scores);
    }
}

public class ImmutableScoresDemo {
    public static void main(String[] args) {
        int[] input = {10, 20};

        ImmutableScores scores = new ImmutableScores(input);
        input[0] = 999;

        int[] leakedCopy = scores.scores();
        leakedCopy[1] = 888;

        System.out.println(scores);
        System.out.println("sum = " + scores.sum());
        System.out.println(
                "input = " + Arrays.toString(input));
        System.out.println(
                "getter result = " + Arrays.toString(leakedCopy));
    }
}
```

```bash
javac -encoding UTF-8 ImmutableScoresDemo.java
java ImmutableScoresDemo
```

**Stdout:**

```text
ImmutableScores[10, 20]
sum = 30
input = [999, 20]
getter result = [10, 888]
```

Even though the caller modifies input and then modifies the array from the getter, the internal `scores` still retains the snapshot data `[10,20]`.

**Note:** `sum()` uses `int` and can overflow if the data is too large. This example focuses only on aliasing and immutability, not on modeling unbounded integer sums.

## 19. Primitive Arrays: Is a Single-Level `clone()` Enough?

With `int[]`, each element is a primitive, so `clone()` creates a new array containing the copied **primitive values**. There are no nested mutable objects **inside that one-dimensional array**.

Therefore, for state consisting only of an `int[]`:
- Copy the array when received.
- Do not mutate the internal array after construction.
- Return a copy when the getter is called.
- Do not publish mutable internals through any other path.

is a reasonable foundation for deep immutability.

**With `int[][]`, however, it is different:** it is an array containing **references to child `int[]` arrays**. Cloning only the outer array still shares the inner arrays.

## 20. Two-Dimensional Arrays: Shallow Copy vs. Deep Copy

```java
int[][] source = {
    {1, 2},
    {3, 4}
};

int[][] shallow = source.clone();
```

After this statement:

```java
source != shallow;            // true
source[0] == shallow[0];      // true
```

Therefore:

```java
source[0][0] = 99;
```

causes `shallow[0][0]` to become `99` as well.

To separate the rows:

```java
int[][] deep = new int[source.length][];

for (int i = 0; i < source.length; i++) {
    deep[i] = source[i].clone();
}
```

For a matrix whose elements at the deepest level are primitives, copying both the outer array and each row is sufficient to separate those mutable arrays.

### Jagged Arrays

Java allows each row to have a different length. You should not assume a matrix always has a fixed number of columns when copying. `source[i].clone()` preserves the exact length of each row; if a row can be null, you must decide on a null-handling policy first.

## 21. Program: Shallow and Deep Copies with `int[][]`

Save **`MatrixCopyDemo.java`**:

```java
import java.util.Arrays;

public class MatrixCopyDemo {
    static int[][] copyDeep(int[][] source) {
        int[][] result = new int[source.length][];

        for (int i = 0; i < source.length; i++) {
            result[i] = source[i].clone();
        }

        return result;
    }

    public static void main(String[] args) {
        int[][] original = {{1, 2}, {3, 4}};

        int[][] shallow = original.clone();
        int[][] deep = copyDeep(original);

        original[0][0] = 99;
        shallow[1][1] = 88;

        System.out.println(
                "original = " + Arrays.deepToString(original));
        System.out.println(
                "shallow = " + Arrays.deepToString(shallow));
        System.out.println(
                "deep = " + Arrays.deepToString(deep));
        System.out.println(original[0] == deep[0]);
    }
}
```

```bash
javac -encoding UTF-8 MatrixCopyDemo.java
java MatrixCopyDemo
```

**Stdout:**

```text
original = [[99, 2], [3, 88]]
shallow = [[99, 2], [3, 88]]
deep = [[1, 2], [3, 4]]
false
```

This is a deep copy for the **two array layers** of the example, not a deep-copy function for arbitrary Java object graphs.

## 22. Deep Immutability of an Object Containing a Matrix

If you want to encapsulate `int[][]` into a value object:
- The constructor copies all rows.
- The getter returns a deep copy.
- Read operations do not mutate the data.
- Make the class `final` so no subclass can break the invariant.
- Do not expose internal arrays through other methods.

### Runnable Program: Immutable Matrix Snapshot

Save **`ImmutableMatrixDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class ImmutableMatrix {
    private final int[][] data;

    ImmutableMatrix(int[][] source) {
        data = copyDeep(source);
    }

    private static int[][] copyDeep(int[][] source) {
        Objects.requireNonNull(source, "source");

        int[][] result = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            result[i] = Objects.requireNonNull(
                    source[i], "row " + i).clone();
        }
        return result;
    }

    int[][] data() {
        return copyDeep(data);
    }

    int at(int row, int col) {
        return data[row][col];
    }

    @Override
    public String toString() {
        return Arrays.deepToString(data);
    }
}

public class ImmutableMatrixDemo {
    public static void main(String[] args) {
        int[][] input = {{1, 2}, {3, 4}};

        ImmutableMatrix matrix = new ImmutableMatrix(input);

        input[0][0] = 10;
        int[][] snapshot = matrix.data();
        snapshot[1][1] = 40;

        System.out.println(matrix);
        System.out.println(matrix.at(0, 0));
        System.out.println(matrix.at(1, 1));
    }
}
```

```bash
javac -encoding UTF-8 ImmutableMatrixDemo.java
java ImmutableMatrixDemo
```

**Stdout:**

```text
[[1, 2], [3, 4]]
1
4
```

**Side note:** if the class wants **value equality**, it must implement `equals`/`hashCode` appropriately, such as using `Arrays.deepEquals`/`Arrays.deepHashCode` on the matrix (and upholding the contract). Merely making data immutable does not write equality for you.

## 23. Records: Final Components, but Not Necessarily Deeply Immutable

Records are commonly used as value carriers:

```java
record Student(String name, int age) {
}
```

With `String` and `int` as above, the exposed state has no nested mutable referents. However:

```java
record Classroom(List<String> students) {
}
```

created with a mutable `ArrayList` will retain a reference to that list unless you handle it specially. The auto-generated `students()` accessor also returns that exact component list reference.

Example:

```java
List<String> input = new ArrayList<>();
input.add("An");
Classroom classroom = new Classroom(input);

input.add("Bình");
System.out.println(classroom.students()); // [An, Bình]
```

Records do not protect the owner from aliasing **automatically**.

### Records Do Not Deep-Copy Automatically Either

Even though a record is implicitly final and component fields are final, fields like `List<StringBuilder>` or `int[]` still hold mutable objects. **Record syntax makes value classes concise; it does not replace designing ownership.**

## 24. Program: A Record That Is Shallowly Mutable via Constructor/Accessor

Save **`UnsafeRecordDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Classroom(List<String> students) {
}

public class UnsafeRecordDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        Classroom room = new Classroom(input);

        input.add("Bình");
        room.students().remove("An");

        System.out.println("input = " + input);
        System.out.println("room = " + room);
    }
}
```

```bash
javac -encoding UTF-8 UnsafeRecordDemo.java
java UnsafeRecordDemo
```

**Stdout:**

```text
input = [Bình]
room = Classroom[students=[Bình]]
```

The constructor retains a direct alias to the mutable list. The generated accessor also returns that alias; therefore, both sides can modify the same list.

## 25. Record Compact Constructor: `List.copyOf` Fits When Elements Are Immutable

Java records have a **compact canonical constructor**:

```java
record Classroom(List<String> students) {
    Classroom {
        students = List.copyOf(students);
    }
}
```

Inside the compact constructor, you can **reassign the `students` parameter**; the compiler uses the final parameter value to initialize the component field according to record rules.

Because this is a `List<String>` and `String` is immutable, this is a concise way to create a deeply immutable snapshot **for the list of strings**, assuming there is no other mutable data to consider.

### Safe Program with a Record

Save **`SafeRecordDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Classroom(List<String> students) {
    Classroom {
        students = List.copyOf(students);
    }
}

public class SafeRecordDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        Classroom room = new Classroom(input);
        input.add("Bình");

        System.out.println("input = " + input);
        System.out.println("room = " + room);

        try {
            room.students().add("Chi");
        } catch (UnsupportedOperationException error) {
            System.out.println("room list is unmodifiable");
        }
    }
}
```

```bash
javac -encoding UTF-8 SafeRecordDemo.java
java SafeRecordDemo
```

**Stdout:**

```text
input = [An, Bình]
room = Classroom[students=[An]]
room list is unmodifiable
```

**Limitation:** if you change the component to `List<StringBuilder>`, `List.copyOf` is still shallow and the record still does not achieve deep immutability.

## 26. Records Containing Arrays and Value Equality

Especially easy to get wrong:

```java
record Data(int[] values) {
}
```

There are three issues:
1. The default constructor can retain a direct alias to the array.
2. The `values()` accessor returns a direct array reference.
3. The generated `equals`/`hashCode` of a record when a component is an array is based on array equality/hash rules, **not deep content comparison like `Arrays.equals`**.

Therefore, **simply writing a compact constructor that clones the array does not automatically provide deep value semantics**.

You can:
- Use a `final class` to explicitly write defensive copies and deep-value equality.
- Use an immutable `List<Integer>` instead of an array if size/performance permits.
- Deliberately override both the accessor and the necessary `equals/hashCode` in the record.

**Immutability** and **value equality** are two different contracts: an object can be immutable while its default `equals` still compares identity.

## 27. Mutable `Date` vs. `java.time`

`java.util.Date` is mutable:

```java
Date date = new Date(0);
date.setTime(1_000L);
```

If a class stores the input `Date` directly and its getter returns a direct Date, that object is not deeply immutable.

Conversely, many classes in `java.time` such as:
- `LocalDate`;
- `LocalDateTime`;
- `Instant`;
- appropriate `ZoneId` implementations;
- `Duration`;

are designed with immutable semantics. Operations like `plusDays` return a **resulting object/value** rather than mutating the original object.

**Note:** Date vs. java.time does not mean every object in every time library is immutable. Always check the contract of the specific type.

## 28. Program: Date Aliasing Mutating an “Immutable” Object

Save **`MutableDateDemo.java`**:

```java
import java.util.Date;

final class UnsafeEvent {
    private final Date when;

    UnsafeEvent(Date when) {
        this.when = when;
    }

    long epochMillis() {
        return when.getTime();
    }
}

public class MutableDateDemo {
    public static void main(String[] args) {
        Date date = new Date(0L);
        UnsafeEvent event = new UnsafeEvent(date);

        System.out.println(event.epochMillis());

        date.setTime(2_000L);
        System.out.println(event.epochMillis());
    }
}
```

```bash
javac -encoding UTF-8 MutableDateDemo.java
java MutableDateDemo
```

**Stdout:**

```text
0
2000
```

`UnsafeEvent.when` is `final`, but the `Date` object to which the caller holds an alias has been modified.

## 29. Two Ways to Fix Date: Defensive Copy or an Immutable Time Type

Approach 1 — Copy `Date` on both input and output:

```java
final class SafeLegacyEvent {
    private final Date when;

    SafeLegacyEvent(Date input) {
        when = new Date(input.getTime());
    }

    Date when() {
        return new Date(when.getTime());
    }
}
```

You need to import `java.util.Date`. `Date` is still mutable, but the caller has no direct alias to the internal Date through these APIs.

Approach 2 — Use `Instant`:

```java
record Event(java.time.Instant at) {
}
```

`Instant` is immutable; this is usually simpler if the domain only needs a timestamp and has no compatibility constraints with legacy Date APIs.

### Runnable Program with `Instant`

Save **`InstantImmutabilityDemo.java`**:

```java
import java.time.Instant;

record Event(Instant at) {
}

public class InstantImmutabilityDemo {
    public static void main(String[] args) {
        Instant original = Instant.parse("2026-01-01T00:00:00Z");
        Event event = new Event(original);

        Instant next = original.plusSeconds(60);

        System.out.println(event.at());
        System.out.println(next);
        System.out.println(event.at() == original);
    }
}
```

```bash
javac -encoding UTF-8 InstantImmutabilityDemo.java
java InstantImmutabilityDemo
```

**Stdout:**

```text
2026-01-01T00:00:00Z
2026-01-01T00:01:00Z
true
```

`plusSeconds` creates a resulting value without mutating `original`. The `Event.at` reference still points to the original immutable Instant.

## 30. Immutable Objects Can Safely Share References

A misconception: “Deep immutability requires copying every object at every layer.”

In reality, **that is not true**. If two objects hold the same `String`, `LocalDate`, or immutable value object, sharing the reference **does not allow modifying state through an alias**.

```java
String label = "Java";
record Name(String value) { }

Name a = new Name(label);
Name b = new Name(label);
```

Both a and b can use the same `String` without worrying about the caller appending directly onto that string. Calling `label.concat(" 17")` returns a different String value without changing the original String.

**An immutable graph can share immutable subgraphs.** That is also the basis of the **structural sharing** technique in persistent immutable data structures.

There is no need to clone a String to protect state; cloning types that are already immutable usually just incurs unnecessary overhead.

## 31. Nested Collections: An Outer Snapshot Is Not Enough If Inner Lists Are Mutable

Example:

```java
List<List<String>> outer = new ArrayList<>();
List<String> first = new ArrayList<>();
first.add("A");
outer.add(first);

List<List<String>> snapshot = List.copyOf(outer);
first.add("B");
```

`snapshot` is an unmodifiable **outer list**, yet `snapshot.get(0)` is still the mutable **inner ArrayList** and now contains `[A,B]`.

A nested immutable representation is needed:

```java
List<List<String>> rows = outer.stream()
        .map(List::copyOf)
        .toList();
```

With immutable `String` elements, each inner list snapshot is detached from the mutable source; the outer list from `Stream.toList()` is unmodifiable according to the Java 17 contract.

### Copying Only the Outer Collection Does Not Deep-Clone

The following approaches **are not sufficient**:
- `List.copyOf(outer)`;
- `new ArrayList<>(outer)`;
- `Collections.unmodifiableList(outer)`;
- `Collections.unmodifiableList(new ArrayList<>(outer))`;

because they still retain references to mutable inner lists if source contains them.

## 32. Program: Two-Level Immutable Snapshot for List<List<String>>

Save **`NestedListSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Schedule {
    private final List<List<String>> rows;

    Schedule(List<List<String>> source) {
        rows = source.stream()
                .map(List::copyOf)
                .toList();
    }

    List<List<String>> rows() {
        return rows;
    }
}

public class NestedListSnapshotDemo {
    public static void main(String[] args) {
        List<String> monday = new ArrayList<>();
        monday.add("Java");

        List<List<String>> input = new ArrayList<>();
        input.add(monday);

        Schedule schedule = new Schedule(input);

        monday.add("SQL");
        input.add(new ArrayList<>(List.of("Python")));

        System.out.println("input = " + input);
        System.out.println("schedule = " + schedule.rows());

        try {
            schedule.rows().get(0).add("Kotlin");
        } catch (UnsupportedOperationException error) {
            System.out.println("inner list unmodifiable");
        }
    }
}
```

```bash
javac -encoding UTF-8 NestedListSnapshotDemo.java
java NestedListSnapshotDemo
```

**Stdout:**

```text
input = [[Java, SQL], [Python]]
schedule = [[Java]]
inner list unmodifiable
```

Because the inner elements are immutable `String`s, the Schedule object protects both levels of data here. If you replace `String` with a mutable class, you must continue handling that level as well.

## 33. `Map.copyOf` Does Not Deep-Copy Values

`Map.copyOf(input)` creates an unmodifiable map according to its contract, but it is shallow with respect to key/value objects.

```java
Map<String, List<String>> data = new HashMap<>();
List<String> items = new ArrayList<>();
items.add("A");
data.put("course", items);

Map<String, List<String>> frozenOuter = Map.copyOf(data);
items.add("B");
```

`frozenOuter.get("course")` can contain `[A,B]` because the value list is still the same mutable object.

### How to Create a Map with Immutable Nested Values

```java
Map<String, List<String>> snapshot = new HashMap<>();

for (var entry : data.entrySet()) {
    snapshot.put(entry.getKey(),
            List.copyOf(entry.getValue()));
}

snapshot = Map.copyOf(snapshot);
```

With immutable String keys/values, this is a deep snapshot according to this two-level model.

**Note:** `Map.copyOf` does not guarantee the iteration order of the resulting map. If the output requires ordering, choose a representation/collection with the corresponding ordering contract and wrap the snapshot appropriately.

In addition, `Map.copyOf` rejects null keys/values, so you need to determine a null policy before using it.

## 34. Program: Outer Map Fixed but Values Still Change

Save **`MapShallowDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class MapShallowDemo {
    public static void main(String[] args) {
        List<String> courses = new ArrayList<>();
        courses.add("Java");

        Map<String, List<String>> input = new HashMap<>();
        input.put("dev", courses);

        Map<String, List<String>> copy = Map.copyOf(input);

        courses.add("SQL");

        System.out.println(copy.get("dev"));

        try {
            copy.put("qa", List.of("Tests"));
        } catch (UnsupportedOperationException error) {
            System.out.println("outer map is unmodifiable");
        }
    }
}
```

```bash
javac -encoding UTF-8 MapShallowDemo.java
java MapShallowDemo
```

**Stdout:**

```text
[Java, SQL]
outer map is unmodifiable
```

You should not infer “unmodifiable Map → all data is immutable”.

## 35. Set and Collection Factories

Java 9+ provides:
- `List.of(...)`;
- `Set.of(...)`;
- `Map.of(...)`;
- `List.copyOf(...)`;
- `Set.copyOf(...)`;
- `Map.copyOf(...)`.

They provide **unmodifiable collections** suitable for building value graphs with immutable elements, however:
- They do not deep-copy mutable element objects.
- They have their own null/duplicate rules: `List.of`/`Set.of`/`Map.of` disallow null; `Set.of` disallows duplicate elements; `Map.of` disallows duplicate keys.
- Not every factory guarantees the expected iteration order.
- Implementations may optimize or share instances according to the contract; do not rely on identity equality `==` between collection results.

An **unmodifiable collection** is a tool, not the complete definition of an immutable object graph.

## 36. `Collections.unmodifiableMap` and Backing Aliases

`Collections.unmodifiableMap(backing)` creates a **view** over the backing map. If an owner still modifies the backing map, the view will reflect the changes.

```java
Map<String, Integer> backing = new HashMap<>();
backing.put("A", 1);

Map<String, Integer> view =
        Collections.unmodifiableMap(backing);

backing.put("B", 2);
```

Calling `view.put(...)` cannot succeed, but the view **is not a snapshot**.

If you want a snapshot with immutable keys/values, you can use `Map.copyOf(backing)` or copy to another unmodifiable map depending on ordering needs. **Do not publish `unmodifiableMap(backing)` as a historical snapshot** if the backing map can still change.

## 37. `clone()` and `Cloneable` Do Not Automatically Create a Deep Copy

`Object.clone()` has a mechanism to copy an object according to its contract, but it **does not automatically deep-copy all mutable referenced fields**.

If a class has:

```java
class Container implements Cloneable {
    int[] values;
}
```

a shallow clone can have the `values` reference pointing to the same array as the original object, unless the author manually clones that array.

Practical issues:
- `Cloneable` has an API contract that causes confusion if used carelessly.
- Constructors/invariants may not be handled in the way readers expect.
- Inheritance and new fields easily cause clone to miss deep copying.
- Cycles/shared aliases in an object graph make manual copying complex.

**You should not treat `clone()` as a “deep immutable button”**. A copy constructor, a `copyOf` factory method, or an explicit immutable design is usually easier to control.

## 38. A Copy Constructor Is Not Inherently Deep or Shallow

A method's name does not determine its semantics.

```java
final class Box {
    final List<StringBuilder> values;

    Box(Box other) {
        values = new ArrayList<>(other.values);
    }
}
```

Although called a **copy constructor**, this example only copies the **outer list**, not the builders. It is still a shallow copy with respect to elements.

A copy constructor true to a **deep copy** contract must traverse and copy all mutable state within the owner's scope.

**Do not claim a copy constructor is deep simply because it accepts an object of the same type.**

## 39. Value Objects with Nested Mutable Input: Designing an Immutable Representation

A practical approach is to **convert mutable input data into immutable value types** right at the boundary:

For example, receiving a list of `StringBuilder`s from a legacy subsystem, while internally keeping only `String`s:

```java
List<String> values = builders.stream()
        .map(StringBuilder::toString)
        .toList();
```

`StringBuilder.toString()` produces a current String representation. Because String is immutable, the owner no longer shares mutable builder references.

This is a **snapshot by converting representation**, rather than keeping the builder and trying to lock it.

### Advantages Over Retaining Mutable Elements

- Fewer alias paths to control.
- The getter can return an immutable list of immutable strings.
- Equality and hashing are simpler.
- Safer to share across threads **after proper publication**.
- Owner invariants depend less on external code.

### Limitations

Sometimes a mutable object holds identity/resources that cannot be converted into a String while preserving semantics; in that case, an appropriate snapshot type or a dedicated ownership contract is needed.

## 40. Program: Converting `StringBuilder` into Immutable Snapshots

Save **`BuilderToStringSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Names {
    private final List<String> values;

    Names(List<StringBuilder> input) {
        values = input.stream()
                .map(StringBuilder::toString)
                .toList();
    }

    List<String> values() {
        return values;
    }
}

public class BuilderToStringSnapshotDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("An");
        List<StringBuilder> input = new ArrayList<>();
        input.add(builder);

        Names names = new Names(input);

        builder.append("!");
        input.add(new StringBuilder("Bình"));

        System.out.println("input = " + input);
        System.out.println("names = " + names.values());
    }
}
```

```bash
javac -encoding UTF-8 BuilderToStringSnapshotDemo.java
java BuilderToStringSnapshotDemo
```

**Stdout:**

```text
input = [An!, Bình]
names = [An]
```

In Java 17, `Stream.toList()` returns an unmodifiable list. The resulting elements are immutable `String`s, so the graph exposed by `Names` is not altered when the caller modifies the input builders or list.

## 41. Deep Immutability and Nested Custom Classes

Suppose:

```java
class MutableAddress {
    String city;

    void setCity(String city) {
        this.city = city;
    }
}

record Person(String name, MutableAddress address) {
}
```

`Person` is created as a record, yet the caller can still call `address.setCity(...)` and cause `person.address().city` to change.

Fixes suited to the domain:
- Replace `MutableAddress` with an immutable `Address` record having `String city`.
- Or store an immutable snapshot of address fields inside Person.
- Or copy `MutableAddress` and **do not return the mutable internal Address** externally.
- Or design the owner API so nested state cannot change after construction.

**You cannot “deep copy” by copying only the `Person` record while still keeping the same MutableAddress reference.**

### Preventing Subclasses from Breaking Invariants

If an immutable class can be subclassed, a subclass could add mutable state or override methods to expose changing state. A `final class`, a record (final), or a documented inheritance design are ways to restrict extension depending on needs.

## 42. Program: Immutable Address Value Object Inside Person

Save **`DeepValueGraphDemo.java`**:

```java
import java.util.List;
import java.util.ArrayList;

record Address(String city, String street) {
}

record Person(String name, Address address) {
}

record Team(List<Person> members) {
    Team {
        members = List.copyOf(members);
    }
}

public class DeepValueGraphDemo {
    public static void main(String[] args) {
        Address address = new Address("Hà Nội", "A");
        Person an = new Person("An", address);

        List<Person> input = new ArrayList<>();
        input.add(an);

        Team team = new Team(input);
        input.add(new Person("Bình",
                new Address("Huế", "B")));

        System.out.println(team.members().size());
        System.out.println(team.members().get(0).address().city());

        Address other = new Address("Đà Nẵng", "C");
        System.out.println(other.city());
        System.out.println(team.members().get(0).address().city());
    }
}
```

```bash
javac -encoding UTF-8 DeepValueGraphDemo.java
java DeepValueGraphDemo
```

**Stdout:**

```text
1
Hà Nội
Đà Nẵng
Hà Nội
```

The `Team → List<Person> → Person → Address → Strings` graph uses immutable value objects. The list is snapshotted. Therefore, mutations to the mutable input list do not cause Team to see a new member, and creating a new Address does not change An's original Address.

## 43. Deep Immutability Does Not Mean “No Mutable Objects Externally”

An immutable object can **use** a mutable service via a method parameter without storing it in its state:

```java
record Invoice(long cents) {
    void printTo(java.io.PrintStream output) {
        output.println(cents);
    }
}
```

`PrintStream` is mutable and has side effects, yet it **is not part of the immutable state that Invoice exposes**.

Similarly, a class can provide a `render(Formatter formatter)` method that uses a mutable formatter temporarily without making the values inside the class mutable.

When classifying shallow/deep, you need to identify the **state boundary**, rather than treating every object that ever appears in a method as part of the object graph.

**You should distinguish between state, dependency, and ownership.**

## 44. Ownership: Transferring Responsibility vs. Copying

If an owner receives a mutable object, there are two main strategies:

1. **Copy a snapshot**, so the caller can continue modifying the input without affecting the owner.
2. **Transfer ownership by contract**, where the caller commits not to touch the object after handing it over; the owner controls all mutation paths.

In mainstream Java, the compiler **does not enforce** that a reference has only one owner or has been “moved” like in a linear/affine type system. If the caller keeps an alias and still has the ability to mutate through the Java API, relying solely on a transfer promise carries risk.

For widely exposed immutable value objects, **defensive copying or an immutable representation** is usually easier to prove.

**Not every object needs a deep copy:** if a part is a resource/socket/entity with real identity, copying it may violate semantics. In that case, you should design lifecycle/permissions rather than pretending to have a deeply immutable snapshot.

## 45. Mutable Graphs with Cycles: Deep Copying Is More Complex Than Iterating Getters

A graph:

```text
A ──► B
▲     │
└─────┘
```

has a **cycle**. If a naive copy function recurses:

```java
Node copy(Node node) {
    return new Node(copy(node.next));
}
```

it may never terminate when encountering a cycle.

A graph with a **shared alias**:

```text
Parent1 ──► SharedChild ◄── Parent2
```

if you deep-copy each branch independently, you can accidentally create **two** different SharedChild instances and break identity-sharing semantics.

General solution when you genuinely need to clone a graph:
- Use a map from **original object identity** to the allocated **copy object**, for example `IdentityHashMap<Object,Object>`.
- Create a placeholder/copy instance before recursing when cycle support is needed.
- Preserve the exact alias relationships according to the contract.
- After construction is complete, expose an appropriate immutable representation.

This is why **general deep copying** is much more complex than copying an `int[][]` or a list of immutable values.

## 46. Snapshots of a Mutable Graph and Cross-Thread Consistency

Suppose thread A is modifying a mutable list while thread B calls:

```java
List.copyOf(source)
```

Without proper synchronization, the snapshot can observe data in the middle of changing, encounter races, or yield unexpected results; `List.copyOf` **is not a concurrent transactional snapshot** for a mutable collection updated externally.

To obtain a consistent snapshot:
- All writers and the snapshot reader coordinate on the same lock, or
- Use immutable/persistent state and atomic publication, or
- Use a concurrent structure with documented snapshot semantics, or
- Design a more proper transactional protocol.

**Deep copying** solves the **aliasing problem of the result after copying**, but the copy operation itself must observe a consistent source if the snapshot is required to correspond to a valid point in time.

## 47. Immutability and Thread-Safety: Related but Not Identical

An **immutable value graph** after construction typically provides benefits:
- No data races caused by mutations of the graph itself.
- Multiple threads can read state simultaneously without needing locks for those read operations.
- No need to synchronize on every access to a simple immutable field.
- Caching, external memoization, and use as keys can be easier.

However, **safe publication** must be considered: transferring a reference from the constructing thread to a consuming thread must obey the Java Memory Model. Final fields provide initialization-safety guarantees when properly constructed, but do not assume that **every kind of racy reference publication is safe for all components**.

Explicit ways to publish:
- Hand off the object through a `BlockingQueue`;
- Store it in an appropriate `volatile`/atomic reference;
- Create/pass it under `synchronized`;
- Pass it via `Thread.start` following happens-before;
- Use a concurrent collection with a publication contract.

Especially with mutable elements or lazy state, `final` on the outer field **does not** automatically resolve races in child objects.

## 48. Example: Immutable Snapshot Shared Across Threads

Save **`ImmutableThreadShareDemo.java`**:

```java
import java.util.List;

record Configuration(List<String> features) {
    Configuration {
        features = List.copyOf(features);
    }
}

public class ImmutableThreadShareDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Configuration configuration =
                new Configuration(List.of("A", "B"));

        Thread first = new Thread(() -> {
            System.out.println(
                    "first size = " + configuration.features().size());
        });

        Thread second = new Thread(() -> {
            System.out.println(
                    "second size = " + configuration.features().size());
        });

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("shared safely");
    }
}
```

```bash
javac -encoding UTF-8 ImmutableThreadShareDemo.java
java ImmutableThreadShareDemo
```

**Printed lines**:

```text
first size = 2
second size = 2
shared safely
```

**Note:** the first two lines **may swap order** across runs due to non-deterministic scheduling; the `shared safely` line always comes after both because of `join`. The value and content of each line are deterministic, but if you want **stdout in an exact order**, store the results in thread-safe variables/separate slots and print them in main after `join`.

This example intentionally clarifies the limitation regarding output ordering in concurrency, without claiming determinism that Java does not promise.

## 49. Program with Deterministic Output When Multiple Threads Read an Immutable Object

Save **`ImmutableThreadDeterministicDemo.java`**:

```java
import java.util.List;

record Configuration(List<String> features) {
    Configuration {
        features = List.copyOf(features);
    }
}

public class ImmutableThreadDeterministicDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Configuration config =
                new Configuration(List.of("A", "B"));

        int[] observed = new int[2];

        Thread first = new Thread(
                () -> observed[0] = config.features().size());
        Thread second = new Thread(
                () -> observed[1] = config.features().size());

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("first = " + observed[0]);
        System.out.println("second = " + observed[1]);
        System.out.println("same object = " + (config == config));
    }
}
```

```bash
javac -encoding UTF-8 ImmutableThreadDeterministicDemo.java
java ImmutableThreadDeterministicDemo
```

**Exact stdout:**

```text
first = 2
second = 2
same object = true
```

The two threads write to **two different array elements** and main waits for `join` before reading. The last line merely illustrates a reference being equal to itself; the important point is that the `Configuration` snapshot does not change.

## 50. Deep Immutability and Hash-Based Collections

If an object is used as a key in a `HashMap` or an element of a `HashSet`, modifying the fields used for `equals/hashCode` after insertion can break lookup expectations.

Risky example:

```java
class MutableKey {
    String code;

    // equals/hashCode use code.
}
```

If `code` changes after the key is in the map, lookups using an equivalent key/value may fail because the hash bucket/search no longer matches the new state.

**Immutable value objects** are usually a good choice for keys because their equality/hash values do not change after construction.

However, you must verify:
- `equals` uses the right components according to the contract.
- `hashCode` is consistent with equals.
- Components participating in equals/hashCode are also immutable or properly snapshotted.
- No nested mutable state affecting equality is exposed.

Do not try to “fix” this by storing a cached hashCode if mutable fields still change; doing so can create a more dangerous inconsistency.

## 51. Runnable: A Mutable Key Causes Unexpected Lookup Behavior

Save **`MutableKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

final class MutableKey {
    private String code;

    MutableKey(String code) {
        this.code = code;
    }

    void setCode(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey key
                && Objects.equals(code, key.code);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(code);
    }
}

public class MutableKeyDemo {
    public static void main(String[] args) {
        MutableKey key = new MutableKey("A");
        Map<MutableKey, String> map = new HashMap<>();

        map.put(key, "value");
        System.out.println(map.get(new MutableKey("A")));

        key.setCode("B");

        System.out.println(map.get(new MutableKey("A")));
        System.out.println(map.get(new MutableKey("B")));
    }
}
```

```bash
javac -encoding UTF-8 MutableKeyDemo.java
java MutableKeyDemo
```

**Typical stdout on JDK 17:**

```text
value
null
null
```

**Important:** this example illustrates a dangerous situation; **you should not take the final lookup result as a guarantee across all hash collisions/implementations**. When a key mutates, the resulting behavior no longer conforms to the proper contract for using a HashMap. Calling `get(new MutableKey("B"))` may return results depending on hash buckets/collisions and table state details.

The right approach is to use an immutable key such as `record Key(String code) {}`, ensuring that the components participating in equality do not change.

## 52. Record `equals` with Mutable Elements

Records generate `equals/hashCode` based on components, but **this does not automatically make components immutable**.

Example:

```java
record Group(List<String> values) {
}
```

If `values` is a mutable ArrayList, after mutating it:
- `group.toString()` can change.
- `group.hashCode()` can change because the list's hash changes.
- `group.equals(other)` can change with the content.

Therefore, a record used as a key **needs to snapshot nested mutable components** or choose immutable types.

### Appropriate Structure

```java
record Group(List<String> values) {
    Group {
        values = List.copyOf(values);
    }
}
```

With List<String>, the object graph across components is immutable, and the generated equals/hashCode reflect immutable values.

## 53. Immutability and the Builder Pattern

A builder is typically a **mutable construction helper**:
- The caller adds data across multiple steps.
- `build()` creates an **immutable snapshot**.
- After `build()`, the caller can continue modifying the builder without affecting the created object.

Wrong:

```java
class Config {
    private final List<String> values;

    Config(Builder builder) {
        values = builder.values; // Alias to the builder's mutable list.
    }
}
```

If the builder modifies the list after building, the “immutable” Config is affected.

Right:
- `values = List.copyOf(builder.values)` if String is immutable.
- Or deep-copy nested mutable parts.
- The builder does not expose references to the private internal immutable snapshot.

## 54. Program: Builder Does Not Mutate Already-Built Objects

Save **`ImmutableBuilderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Config {
    private final List<String> endpoints;

    private Config(List<String> source) {
        endpoints = List.copyOf(source);
    }

    List<String> endpoints() {
        return endpoints;
    }

    static final class Builder {
        private final List<String> values = new ArrayList<>();

        Builder add(String endpoint) {
            values.add(endpoint);
            return this;
        }

        Config build() {
            return new Config(values);
        }
    }
}

public class ImmutableBuilderDemo {
    public static void main(String[] args) {
        Config.Builder builder = new Config.Builder();
        builder.add("/users");

        Config first = builder.build();
        builder.add("/orders");

        Config second = builder.build();

        System.out.println("first = " + first.endpoints());
        System.out.println("second = " + second.endpoints());
    }
}
```

```bash
javac -encoding UTF-8 ImmutableBuilderDemo.java
java ImmutableBuilderDemo
```

**Stdout:**

```text
first = [/users]
second = [/users, /orders]
```

The two immutable Config snapshots are independent of the mutable builder. The builder is mutable, while the resulting objects are immutable according to the List<String> data model.

## 55. Functional Update: Creating a New Object Instead of Mutating

An immutable value object often provides “with” or “plus” operations that return a new object:

```java
record Counter(int value) {
    Counter increment() {
        return new Counter(value + 1);
    }
}
```

`counter.increment()` does **not** modify `counter`, but returns a new Counter with a larger value.

### Program

Save **`FunctionalUpdateDemo.java`**:

```java
record Counter(int value) {
    Counter increment() {
        return new Counter(value + 1);
    }
}

public class FunctionalUpdateDemo {
    public static void main(String[] args) {
        Counter before = new Counter(4);
        Counter after = before.increment();

        System.out.println("before = " + before.value());
        System.out.println("after = " + after.value());
        System.out.println("same instance = " + (before == after));
    }
}
```

```bash
javac -encoding UTF-8 FunctionalUpdateDemo.java
java FunctionalUpdateDemo
```

**Stdout:**

```text
before = 4
after = 5
same instance = false
```

Functional updates make “before/after” data clear in code and are often convenient in concurrent programming or event-driven systems. You need to balance allocation costs against reasoning benefits, rather than assuming every mutable object is a bug.

## 56. Deep Immutability Does Not Require Forbidding Every Lazy Cache

A class can have **observational/logical immutability** while maintaining an internal cache that changes without altering the exposed business results.

For example, memoizing a computed value:
- The resulting value must be stable;
- The cache must not be exposed;
- Cache updates must be thread-safe when the class is shared;
- It must not cause side effects incompatible with the contract.

This is the **difference between physically never mutating a single bit** and **not changing observable logical state**.

However, if the problem definition requires **strict deep structural immutability**, a hidden mutable cache is still an internal mutation. When documenting, use precise wording: “observationally immutable with respect to the API” or “structurally free of mutable state”.

### Avoiding Cache-Induced Races

A `private String cached;` is not automatically thread-safe. You can use eager initialization, volatile/synchronized, or an appropriate concurrent mechanism. Simply adding `final` to a field holding a mutable cache does not resolve publication races.

## 57. Deep Immutability and Input Data Security

Suppose an auth token is represented as a `char[]` because the application wants to clear characters from memory after use. If the class stores a direct alias:

```java
final class SecretBox {
    private final char[] secret;

    SecretBox(char[] secret) {
        this.secret = secret;
    }
}
```

the caller can modify/clear the array and alter state. Copying the array for a snapshot can protect the input data, but it also **creates an extra copy of the secret in memory** that requires an explicit clearing policy/consideration.

**Trade-off:** deep immutability and secret lifecycles sometimes conflict; a secret holder requiring zeroization may intentionally be **mutable** according to the security protocol. You should not always force immutability just because “immutable is better”.

Choose your design based on the threat model and the resource/lifecycle management contract, not merely style.

## 58. Immutability and Serialization/ORM/Frameworks

An immutable value object can be serialized, persisted, or used in an ORM, however:
- A framework may require constructors, setters, reflection access, or proxies.
- Deserialization may instantiate objects through specialized mechanisms.
- An entity with its own identity/lifecycle is often mutable according to business logic.
- You can separate the **mutable persistence entity** from the **immutable read model/DTO**.

Do not make a class mutable just because a framework “usually works that way” when the value object use case can be designed separately; nor should you ignore framework constraints and claim every immutable class integrates seamlessly.

**An immutable snapshot DTO** is a good choice when exporting data from a changing entity and needing to prevent callers from mutating the persistence context's state.

## 59. The Cost of Deep Copying

Deep copying can:
- Consume CPU proportional to the number of elements/depth.
- Increase memory allocations and GC pressure.
- Require traversing a large object graph.
- Lose desired identity/reference sharing if copied thoughtlessly.
- Cause slowdowns on an API hot path if a getter always copies a large array.

There is no rule that says “you must deep-copy the entire application”.

Alternative options:
- Choose **immutable component types** from the start.
- Convert mutable input into a compact immutable representation.
- Use **persistent collections**/structural sharing if data versions change frequently.
- Do not expose mutable internals; provide read-only primitive queries.
- Limit snapshots to the data domain that truly needs independence.

### Example of a Narrowly Designed Getter

Instead of:

```java
int[] values() {
    return values.clone();
}
```

if the caller only needs to read elements/compute a sum, you can provide:

```java
int size() {
    return values.length;
}

int get(int index) {
    return values[index];
}
```

A getter does not always have to return the entire internal structure. A narrow API reduces the need for large copies and improves encapsulation.

## 60. Persistent Immutable Data Structures and Structural Sharing

A **persistent data structure** preserves previous versions after updates; operations create a new version that can share **already-immutable branches** between versions.

```text
Version 1 ──► immutable node A ──► immutable node B
Version 2 ──► immutable node C ──► immutable node B
                                    shared safely
```

Because node B is immutable, sharing it between two versions does not create alias mutation.

Do not confuse this:
- “Persistent” in the data-structure sense does not necessarily mean persisted to disk/database.
- “Structural sharing” does not mean shallow-copying a mutable node and letting anyone mutate it.
- Java Collections Framework `ArrayList` does not automatically become a persistent immutable vector just by wrapping it with an unmodifiable view.

Persistent collections are useful for large snapshots, multiple versions, and functional updates, but choosing a library/implementation requires evaluating practical constraints.

## 61. Process for Designing a Deeply Immutable Class

**Step 1 — Identify state:** which fields/values form the object's identity/value? Are there any nested objects affecting getter/equals/hashCode results?

**Step 2 — Choose types:** prefer primitives and immutable components (`String`, `Instant`, nested immutable records) whenever possible.

**Step 3 — Restrict mutators:** omit setters that modify state promised to stay fixed; use factories/with-methods returning a new object when needed.

**Step 4 — Prevent subclasses from breaking the contract:** use a `final class` or record when appropriate; if inheritance is needed, design invariants and extension points rigorously.

**Step 5 — Defensive copy on input:** arrays, collections, and mutable elements must be copied or converted in representation according to ownership boundaries.

**Step 6 — Defensive API on output:** getters must not return mutable state directly; return an immutable value/snapshot/narrow query.

**Step 7 — Validate invariants:** disallow invalid/null elements if the contract forbids them; normalize data before retaining it.

**Step 8 — Check alias paths:** caller modifying input after construction, modifying the getter result, or modifying a nested child via another reference.

**Step 9 — Review concurrency/publication:** the object does not escape the constructor prematurely and is properly published; the source snapshot must be consistent when copied from a mutable concurrent source.

**Step 10 — Test value semantics:** do equal values compare equal as required, is the hash stable, and does the serialized form satisfy the contract?

## 62. Testing Checklist for an Immutable Class

Create an object from mutable input and then test:

1. Mutating the input collection's structure after the constructor.
2. Mutating a mutable input element after the constructor.
3. Retrieving the collection from the getter and calling `add/remove/clear`.
4. Retrieving a nested element from the getter and calling a mutator.
5. Retrieving the array from the getter and modifying an element.
6. If it is a multi-dimensional array, modifying an inner row.
7. Calling `toString` before and after external modifications.
8. Checking `equals/hashCode` before and after external mutation.
9. Creating two objects from the same input and attempting to modify one reference.
10. Testing null elements/keys according to the contract.
11. Checking collection order if business logic requires ordering.
12. Running tests across multiple threads when the source is mutable concurrent state with a snapshot protocol.
13. Checking that there are no mutable caches/escapes through indirect getters.
14. If a builder is reused, building a second time does not change the first built object.
15. Measuring copying cost with sufficiently large inputs if performance matters.

If the object data observed from a getter changes despite the API promising immutability, look for an **open alias** at the input, output, or a nested layer.

## 63. Exercise 1 — Is a `final List` Deeply Immutable?

```java
final List<String> names = new ArrayList<>();
names.add("An");
```

**Answer:** No. The final reference variable forbids reassigning `names`, but the list object is mutable. You need to consider boundaries and the API if you want an immutable snapshot.

## 64. Exercise 2 — Is an Unmodifiable View a Snapshot?

```java
List<String> input = new ArrayList<>();
List<String> view = Collections.unmodifiableList(input);
input.add("Java");
```

**Answer:** No. `view` sees `Java` because the backing list was modified. This is an unmodifiable view, not a detached immutable snapshot.

## 65. Exercise 3 — Is `List.copyOf` Enough for MutableUser?

```java
List<MutableUser> users = ...;
List<MutableUser> copy = List.copyOf(users);
```

**Answer:** Not enough if `MutableUser` has observable state and mutators through aliases. The outer list structure is unmodifiable, but the elements are the same MutableUser references. An immutable user value snapshot or a domain-appropriate deep copy is needed.

## 66. Exercise 4 — How Many Times Must an `int[]` Array Be Copied?

A class receives an `int[]` and has an accessor returning `int[]`, promising an immutable snapshot.

**Answer:** Copy in the **constructor** to eliminate input aliases and copy in the **getter** so the internal array is not exposed. For a one-dimensional int[] like this, clone copies the primitive elements completely.

## 67. Exercise 5 — Is Cloning the Outer `int[][]` Enough?

```java
int[][] copied = source.clone();
```

**Answer:** No. The rows are shared int[] objects, so the caller can still modify row contents. Each row must be copied, or another immutable representation must be used.

## 68. Exercise 6 — Record with a Mutable List

```java
record Group(List<String> names) {}
```

**Answer:** The record is final and the component reference is final, but by default it still retains a mutable list alias. Use a compact constructor `names = List.copyOf(names);` with immutable `String` to create an appropriate snapshot.

## 69. Exercise 7 — Record with List<StringBuilder>

```java
record Group(List<StringBuilder> names) {
    Group {
        names = List.copyOf(names);
    }
}
```

**Answer:** This is still only a shallow snapshot of the list. The mutable `StringBuilder` elements are shared. You need to convert each Builder into an immutable String, or copy them and not expose mutators.

## 70. Exercise 8 — Does `String` Need to Be Cloned?

An immutable Person holds only a `String name` provided by the caller.

**Answer:** Usually no. `String` is immutable; the caller cannot mutate a String object through an alias. It can be safely shared with respect to mutation.

## 71. Exercise 9 — `Date` in a Final Field

```java
final class Event {
    private final Date when;
    Event(Date when) { this.when = when; }
}
```

**Answer:** Not deeply immutable if the caller retains the mutable Date and modifies it with `setTime`. You can copy Date on input/output or use the immutable `Instant`.

## 72. Exercise 10 — Is a Deep Copy Automatically Immutable?

```java
List<StringBuilder> deep = deepCopyBuilders(source);
deep.get(0).append("!");
```

**Answer:** No. Deep copying makes objects independent of the source, but the deep copy itself is still mutable if the API allows it. Additional immutable representation / encapsulation is needed to obtain an immutable object.

## 73. Exercise 11 — `Map.copyOf` with a Nested List

```java
Map<String, List<String>> copy = Map.copyOf(input);
```

**Answer:** The outer map is unmodifiable, but the values can be mutable lists. Each list (and nested mutable elements, if any) must be snapshotted.

## 74. Exercise 12 — Deep Immutability and final class

A class is final, yet it has `void increment()` that modifies `int count`.

**Answer:** A final class only forbids subclassing, not mutation. The object **is not immutable**.

## 75. Exercise 13 — Builder After Building

A builder holds an `ArrayList`; the Config object only keeps a direct alias to the builder's list.

**Answer:** Config can change when the builder adds elements after `build()`. The constructor/build should copy a snapshot and not expose mutable state.

## 76. Exercise 14 — Why Use an Immutable Key?

An object whose fields participating in `hashCode` are mutated after being put into a HashMap.

**Answer:** Lookups may fail or produce unexpected behavior. Immutable keys with stable equality/hash help prevent such bugs.

## 77. Exercise 15 — Nested Immutable Record and List.copyOf

```java
record A(String s) {}
record B(List<A> items) {
    B {
        items = List.copyOf(items);
    }
}
```

**Answer:** Because `A` contains only a String and has no external mutable state, `B` achieves deep immutability for this graph. There is no need to separately clone the immutable `A` elements.

## 78. Exercise 16 — `Collections.unmodifiableList(new ArrayList<>(src))`

**Question:** is this a deep snapshot?

**Answer:** It creates a **shallow snapshot** of the outer list and wraps the copy in an unmodifiable view; if elements are mutable, element aliases are still shared. With immutable elements, it can satisfy the model's deep immutability requirement.

## 79. Exercise 17 — Mutable Array in Record Equality

```java
record Data(int[] values) {}
```

**Answer:** Generated record equals/hashCode do not use deep content equality for an array component. Beyond defensive copying, if you want value semantics based on array contents, you must design appropriate equals/hashCode or use a different immutable value representation.

## 80. Exercise 18 — Copying a Graph with Cycles

Graph A→B→A; recursive copying without remembering already-visited objects.

**Answer:** It can loop infinitely or cause a stack overflow. You need to manage an original-to-copy identity mapping and valid placeholders to preserve cycles and shared aliases if deep copying is genuinely required.

## 81. Exercise 19 — Snapshots with Active Concurrent Writers

Thread A mutates an ArrayList; Thread B calls `List.copyOf(list)` without synchronization.

**Answer:** There is no guarantee of an atomic/consistent snapshot; furthermore, there is a data race because ArrayList is not thread-safe. Synchronization, immutable publication, or a concurrent structure with an appropriate contract is needed.

## 82. Exercise 20 — Hidden Mutable Cache

An object returns the same business results, but uses a mutable cache field to avoid recomputation.

**Answer:** It can be described as logically/observationally immutable if the cache does not affect promised behavior and is handled in a thread-safe manner; it is not strictly physically deeply immutable. Clear terminology and contracts are required.

## 83. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| “A `final` field makes the child immutable” | Locks the reference, not the referent | Use an immutable child/copy |
| “`final class` means immutable” | Can still have mutable fields/methods | Design state properly |
| “A record is always deeply immutable” | Components can be mutable | Compact constructor, immutable types |
| “An unmodifiable collection is a snapshot” | A view can track the backing collection | `copyOf`/snapshot |
| “`List.copyOf` copies each element” | Shallow-copies references | Choose immutable elements/deep copy |
| “`new ArrayList<>(input)` is a deep copy” | Only copies the outer structure | Copy mutable nested state |
| “Copying in the constructor is enough” | Getters can expose internal aliases | Defensive copy on output as well |
| “Returning a copy from the getter is fine even if keeping the original input” | The caller holds an input alias | Defensive copy on input |
| “Cloning int[][] is deep” | Inner rows are still shared | Copy each row |
| “Using `Collections.unmodifiableMap` freezes data” | It is only a view of the backing map | Copy a snapshot and nested values |
| “Deep copying automatically makes an object immutable” | The copy still has mutators | Use an immutable representation |
| “To be immutable, every String must be copied” | String is already immutable | Share immutable subgraphs |
| “Record array equality compares contents” | Arrays use reference equality in generated record methods | Custom value equality or a different representation |
| “Java has `deep final`” | No such modifier exists | Design/API/ownership |
| “Immutable means you no longer need to think about concurrency” | Safe publication/source snapshots still need to be right | Follow the Java Memory Model |
| “A `volatile` outer reference locks the inner List” | Mutable inner state still has races | Immutable state or synchronization |
| “Clone every entity like a value object” | Can break identity/lifecycle | Separate aggregate ID/snapshot |
| “A mutable HashMap key still looks up normally” | Hash/equality can change | Immutable keys |
| “Copying a graph only needs recursion” | Cycles and shared aliases | Identity mapping |
| “Immutable snapshots are free” | Have memory/CPU costs | Immutable types, structural sharing |
| “No setters means deeply immutable” | Mutation via getters/aliases | Audit all reference paths |
| “Deeply immutable requires having no cache at all” | Logical vs. physical immutability differ | Define the contract and synchronize the cache |

## 84. Decision Checklist When Reviewing a Java Class

1. **Has immutability been clearly defined** (physical or observational; which graph counts as state)?
2. What references to mutable objects exist in fields/components?
3. Is `final` preventing reference reassignment or actually eliminating mutation?
4. Does the constructor copy mutable inputs?
5. Does any getter return a mutable internal array/list/map/object?
6. Are there mutable nested elements that need to be deep-copied?
7. If using `List.copyOf`, are the elements truly immutable?
8. Is an `unmodifiable view` being confused with a detached snapshot?
9. For nested lists/maps, have all necessary layers been copied?
10. For `int[][]`, are both the outer array and each inner row copied?
11. If using a record, does a component accessor expose a mutable object?
12. If using an array component in a record, do equals/hashCode have proper value semantics?
13. Can mutable elements be modified through external aliases?
14. If the input is `Date`/`StringBuilder`, has it been replaced with an immutable type or snapshot?
15. If using a builder, does modifying the builder after building affect the built object?
16. Does the class have setters or methods that modify internal state after construction?
17. Can the class be subclassed and have its invariants broken?
18. If there is a hidden cache, are the logical immutability contract and thread-safety clear?
19. Does the object graph have cycles/shared aliases such that deep copying requires an identity map?
20. Is an entity being deep-copied when its identity should instead be preserved?
21. Is a consistent snapshot needed when the source is modified by multiple threads?
22. Is publication/visibility of the final immutable graph across threads correct?
23. Are the object's hash/equality stable when used as a map key?
24. Can costs be reduced via immutable components/structural sharing or narrow queries?
25. Have tests attempted to mutate the input, getter results, and nested children after construction?

## 85. Key Takeaways

- **Shallow immutability** refers to constraints at the outer layer (reference/structure/API), whereas **deep immutability** requires observable state within the relevant graph not to change after construction.
- **`final` does not make a mutable referent immutable**; `final class` and records do not automatically guarantee deep immutability either.
- **`Collections.unmodifiableList` is a view**; **`List.copyOf` is a collection-layer unmodifiable snapshot for a mutable source**, yet it still shares mutable elements.
- **Shallow copy** creates a new outer structure while sharing nested references; **deep copy** must sufficiently isolate the mutable objects within the snapshot's scope.
- **Deep copying does not automatically make the copy immutable**: you must close mutators and avoid exposing mutable aliases.
- **One-dimensional primitive arrays** can be cloned to isolate data; **two-dimensional arrays** require cloning each row.
- **Records with String/primitives/immutable components** are convenient for creating value objects; records with List/array/Date/StringBuilder can still be “pseudo-immutable”.
- **Perform defensive copies on both input and output** if the owner retains an internal mutable array/object.
- **Deep immutability does not require cloning immutable values** like String/Instant; they can be shared safely when the graph is properly designed.
- **Concurrency, publication, ownership, identity, and performance** still need to be considered; an immutable graph reduces mutation risks, but does not replace all concurrency contracts.
- The most sustainable design approach is usually to **choose immutable components from the start**, copy only necessary mutable boundaries, and expose just enough API to protect invariants.
