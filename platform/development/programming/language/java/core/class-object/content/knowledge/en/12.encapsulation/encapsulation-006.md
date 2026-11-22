# Preventing Exposure of Arrays, Collections, and Mutable Objects in Java

**Encapsulation** is not just about making data fields `private`. If a class **returns a reference** to an internally stored array, list, map, or mutable object, external code can still modify internal state **without calling the designed update methods**. The opposite direction matters just as much: if a constructor or setter **retains the original reference** to a mutable object provided by the caller, the caller can continue modifying that object from the outside.

This phenomenon is commonly called **representation exposure** (*exposing internal representation*) or **leaking mutable state**. It undermines encapsulation even when a field is already `private final`.

Problematic example:

```java
class Course {
    private final int[] scores;

    Course(int[] scores) {
        this.scores = scores;  // Retains the caller's array reference
    }

    int[] scores() {
        return scores;        // Returns the internal array reference
    }
}
```

The caller can do:

```java
int[] input = {8, 9};
Course course = new Course(input);

input[0] = -100;             // Modifies from input
course.scores()[1] = -200;   // Modifies via getter
```

Both operations modify **the same array** stored by `Course`. The `private final` modifiers only prevent external code from accessing the field directly and prevent the field from being reassigned after valid initialization; they **do not make the array immutable**.

**Goal:** design a class so that external code can only change internal state through an **intentional API**, not through leaked mutable references.

## 1. Mechanism: Reference Variables and Aliasing

In Java, arrays, collections, and most object types are used via **references**. Assigning one reference variable to another does not automatically create a copy of the object.

```java
int[] a = {1, 2};
int[] b = a;
b[0] = 99;

System.out.println(a[0]); // 99
```

`a` and `b` are two variables, yet both point to the same array object.

```text
a ─────┐
       ├──> int[] #1 { 99, 2 }
b ─────┘
```

A private field can still reference the exact same object that the caller holds:

```text
caller.input ──────────┐
                       ├──> int[] #1
Course.scores (private)┘
```

Therefore, **encapsulating a field** and **encapsulating the state of the referenced object** are two related yet distinct concerns.

**Java passes arguments by value:** when a constructor receives `int[] scores`, it receives a **copy of the reference value**. That copied reference still points to the caller's same array. This is not pass-by-reference of the caller's variable.

### Two Paths of State Exposure

| Path | Risky Code | Why Is It Dangerous? |
| --- | --- | --- |
| **Input** (*inbound alias*) | `this.scores = scores;` | Caller still holds `scores` and can modify the array after the constructor finishes |
| **Output** (*outbound alias*) | `return scores;` | Caller receives the internal array and can modify elements |
| Returning a mutable collection | `return items;` | Caller can call `add`/`remove`/`clear` |
| Returning a view of a mutable collection | `return Collections.unmodifiableList(items);` | Modification through the view is forbidden, but another alias can modify the backing list; the view changes accordingly |
| Returning a new collection containing mutable elements | `return new ArrayList<>(items);` | Separates the list structure, yet still shares the element objects |
| Returning a field that is a mutable object | `return address;` | Caller can invoke setters/mutators on the internal object itself |

A safe API must define **who owns the state**, **who is allowed to modify it**, **at what level copies need to be returned**, and **which business invariants must be preserved**.

## 2. Distinguishing Commonly Confused Concepts

**Mutable object:** has state that can change after creation; for example arrays, `ArrayList`, `HashMap`, `StringBuilder`, `java.util.Date`.

**Immutable object:** the type's contract does not allow changing observable state after creation; for example `String`, `LocalDate`, `Integer`. A record does not automatically become *deeply immutable* when a component holds an array or a mutable list.

**Unmodifiable collection:** a collection where structural modification operations through the returned interface are rejected. This **does not guarantee** that the underlying data or element objects are immutable.

**Defensive copy:** creating a separate object or structure to avoid unintentionally sharing mutable state. Copying can be **shallow** or **deep across the data domain** (*deep copy*).

**Snapshot:** a result reflecting the state at a point in time; subsequent updates to the source do not automatically change the snapshot's contents. However, if the snapshot contains references to mutable elements, the **element state** itself can still be changed from the outside.

**Read-only view:** the recipient does not have permission to modify through the view, but the view can **reflect updates** to the underlying source.

The terms `final`, `private`, `unmodifiable`, `immutable`, and `copy` should not be used as if they were synonymous.

## 3. Why `private final` Is Still Not Enough

Consider:

```java
class Scores {
    private final int[] values;

    Scores(int[] values) {
        this.values = values;
    }
}
```

- `private`: another independent class cannot write `scores.values` directly.
- `final`: the `values` field cannot be reassigned to another array after valid initialization.
- **None** of the conditions above forbids `values[0] = ...`, even when executed from an alias outside the class.

```java
int[] input = {5};
Scores scores = new Scores(input);
input[0] = -10;
```

Afterward, the `values` field still points to the exact original array — which is precisely what makes updates from `input` visible through the object.

This is an example of **reference immutability**, **not content immutability**.

A class that performs validation in its constructor can still have its invariants broken if it continues to hold onto the mutable input:

```java
// Error-prone idea:
if (scores[0] < 0) {
    throw new IllegalArgumentException();
}
this.scores = scores;
```

The caller can still modify `scores[0]` to a negative number after the constructor returns, bypassing the validation step.

## 4. Protecting Arrays: Copying on Input and Output

For one-dimensional primitive arrays such as `int[]`, you can use:

- `array.clone()`;
- `Arrays.copyOf(array, array.length)`;
- `System.arraycopy(...)` into a new array of appropriate length.

**Copying on only one side is not enough** if both the input caller and output caller need to be prevented from modifying internal state.

Common pattern:

```java
class GradeBook {
    private final int[] grades;

    GradeBook(int[] grades) {
        this.grades = grades.clone(); // Copy on input
    }

    int[] grades() {
        return grades.clone();       // Copy on output
    }
}
```

Each call to `grades()` returns a **new array**. If the elements are of a primitive type, this one-dimensional copy is sufficient to isolate the state of each element in the array.

### 4.1. Complete Java 17 Program

Save the entire code as **`SafeArrayDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class GradeBook {
    private final int[] grades;

    GradeBook(int[] source) {
        Objects.requireNonNull(source, "source");
        int[] copy = source.clone();

        for (int grade : copy) {
            if (grade < 0 || grade > 10) {
                throw new IllegalArgumentException("Grade must be 0..10");
            }
        }
        this.grades = copy;
    }

    int[] grades() {
        return grades.clone();
    }

    int at(int index) {
        return grades[index];
    }

    int size() {
        return grades.length;
    }
}

public class SafeArrayDemo {
    public static void main(String[] args) {
        int[] input = {8, 9};
        GradeBook book = new GradeBook(input);

        input[0] = -100;       // Only modifies the caller's array
        int[] received = book.grades();
        received[1] = -200;    // Only modifies the returned copy

        System.out.println(Arrays.toString(input));
        System.out.println(Arrays.toString(received));
        System.out.println(Arrays.toString(book.grades()));
        System.out.println(book.at(0));
        System.out.println(book.size());
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 SafeArrayDemo.java
java SafeArrayDemo
```

**Exact stdout:**

```text
[-100, 9]
[8, -200]
[8, 9]
8
2
```

The output proves that **both reference paths have been isolated**:

1. The caller modifies `input` without changing `GradeBook`'s own array.
2. The caller modifies the `received` copy without changing `GradeBook`'s own array.
3. `book.grades()` still returns the original data that passed validation.

### 4.2. Copy First, Then Validate the Data

The example performs `source.clone()` first and then iterates over **the copy**. In a design that needs to guard against unintended concurrent modification, the purpose is to validate **the exact data that will be stored**, rather than validating the source array and storing a different one. However, copying an array from an input currently being modified by multiple threads **does not by itself guarantee an atomic snapshot of the whole array**; an additional synchronization protocol is needed, or the class should only accept data with clear ownership.

`Objects.requireNonNull` provides a clear error when the input is `null` instead of letting `clone()` throw an implicit, unexplained error. For another API, you may choose to accept `null` according to the contract, but you must be consistent.

## 5. When the API Does Not Need to Return the Entire Array

One way to limit the API surface is **not to provide a getter that returns the entire mutable object** if the caller only needs a few read operations:

```java
int gradeAt(int index) {
    return grades[index];
}

int count() {
    return grades.length;
}
```

Advantages:
- No need to create a new array every time a single element is read.
- Does not expose the array reference.
- Allows adding access, bounds, invariant checks, or logging when needed.

If the caller truly needs all the data, a getter returning a **defensive copy** may be appropriate:

```java
int[] allGrades() {
    return grades.clone();
}
```

**Trade-off:** a defensive copy allocates and copies in `O(n)` for an array of length `n`; an element-by-element read API can be more economical, though it requires multiple calls. Choose based on actual needs, and do not expose an entire collection merely for convenience.

## 6. Two-Dimensional Arrays and Object Arrays: `clone()` Only Performs a Shallow Copy

A multidimensional Java array is **an array whose elements are references to other arrays**. Therefore:

```java
int[][] original = {{1, 2}, {3, 4}};
int[][] shallow = original.clone();

shallow[0][0] = 99;
System.out.println(original[0][0]); // 99
```

`original` and `shallow` are two **different** outer arrays, yet `original[0] == shallow[0]` is `true` because they still point to **the same first row array**.

### Copying Row by Row

One way to copy the structure of an `int[][]` is:

```java
static int[][] copyMatrix(int[][] source) {
    int[][] result = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        result[i] = source[i].clone();
    }
    return result;
}
```

This is an illustrative method snippet assuming `source` and every row are non-`null`. It creates:
- A new outer array;
- A new row array for each row;
- The `int` values are copied by value.

Because `int` is primitive, the result isolates the state of the elements. If a row can be `null`, a separate rule for `null` is needed; do not call `clone()` directly on a null row.

### Complete Program: Shallow and Row-by-Row Copy

Save **`MatrixCopyDemo.java`**:

```java
import java.util.Arrays;

public class MatrixCopyDemo {
    static int[][] copyMatrix(int[][] source) {
        int[][] result = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            result[i] = source[i].clone();
        }
        return result;
    }

    public static void main(String[] args) {
        int[][] original = {{1, 2}, {3, 4}};
        int[][] shallow = original.clone();
        int[][] independent = copyMatrix(original);

        shallow[0][0] = 90;
        independent[1][1] = 80;

        System.out.println(Arrays.deepToString(original));
        System.out.println(Arrays.deepToString(shallow));
        System.out.println(Arrays.deepToString(independent));
        System.out.println(original[0] == shallow[0]);
        System.out.println(original[0] == independent[0]);
    }
}
```

```bash
javac -encoding UTF-8 MatrixCopyDemo.java
java MatrixCopyDemo
```

**Stdout:**

```text
[[90, 2], [3, 4]]
[[90, 2], [3, 4]]
[[1, 2], [3, 80]]
true
false
```

**Caution:** with `Person[]`, `clone()` creates a new array but preserves the **Person references** in each slot. If `Person` is mutable, a caller can modify `copy[0].setName(...)` and cause the original array's `Person` object to change as well. In that case, you need to **copy the elements according to the contract**, not just clone the array.

## 7. Mutable Collections: What Is Wrong with a Getter Returning the List Directly?

Example:

```java
import java.util.ArrayList;
import java.util.List;

class Team {
    private final List<String> members = new ArrayList<>();

    List<String> members() {
        return members;   // Returns the internal object directly
    }
}
```

The caller can do:

```java
Team team = new Team();
team.members().add("Bình");
team.members().clear();
```

All of these operations modify **the internal list**, even though `members` is `private final`. If the `Team` class intended to control adding members through `addMember` (for instance, checking for duplicate names or enforcing a size limit), the caller has **bypassed the invariant**.

This is a case of representation exposure through a **getter**.

### Solutions Based on Requirements

- **Unmodifiable view:** `Collections.unmodifiableList(members)` prevents the caller from modifying through the view, yet still reflects subsequent changes to the backing list.
- **Unmodifiable snapshot:** `List.copyOf(members)` gives the caller an unmodifiable list that need not reflect subsequent structural changes to `members`, if the input is an ordinary mutable list.
- **Mutable copy:** `new ArrayList<>(members)` returns a separate list structure; the caller can modify the received list itself, but cannot modify the internal list structure.
- **Intentional read API:** `size()`, `memberAt(index)`, `contains(...)`, or methods returning immutable data.

There is no single solution for every API. What matters is whether **the contract declares a snapshot or a live view, a mutable copy or an immutable result**.

## 8. Differences Between `Collections.unmodifiableList` and `List.copyOf`

This is one of the most important distinctions in this lesson.

### 8.1. Unmodifiable View

```java
List<String> view = Collections.unmodifiableList(source);
```

Methods that modify directly through `view`, such as `add`, `remove`, and `set`, typically throw `UnsupportedOperationException`.

However, **the view is backed by the source collection**. If the `source` object is modified through **an alias that still has modification rights**, the data displayed by `view` can change.

### 8.2. Unmodifiable Snapshot

```java
List<String> snapshot = List.copyOf(source);
```

When `source` is an ordinary mutable `ArrayList<String>`:

- `snapshot` does not allow the caller to use `List` mutators to modify the structure.
- Structural changes to `source` after the time of copying do not automatically alter `snapshot`.
- The copy is **shallow**: element references are shared if the elements are objects.
- `List.copyOf` rejects `null` elements with a `NullPointerException`.
- If the input is already a suitable kind of unmodifiable list, the implementation **may return the same object** instead of always allocating a copy. Therefore, do not build your design relying on `snapshot != source` in every case.

Neither kind of result **by itself guarantees deep immutability** of the elements inside.

### 8.3. Java 17 Example with Exact Stdout

Save **`ViewVsSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);
        List<String> mutableCopy = new ArrayList<>(source);

        source.add("Bình");
        mutableCopy.add("Chi");

        System.out.println("Source: " + source);
        System.out.println("View: " + view);
        System.out.println("Snapshot: " + snapshot);
        System.out.println("Mutable copy: " + mutableCopy);

        try {
            view.add("Dũng");
        } catch (UnsupportedOperationException error) {
            System.out.println("View không cho add");
        }

        try {
            snapshot.add("Dũng");
        } catch (UnsupportedOperationException error) {
            System.out.println("Snapshot không cho add");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
```

**Stdout:**

```text
Source: [An, Bình]
View: [An, Bình]
Snapshot: [An]
Mutable copy: [An, Chi]
View không cho add
Snapshot không cho add
```

**Key observation:** calling `add` through the view is blocked, yet the view itself still reflects `source.add("Bình")`. The snapshot does not change when an element is added to the source. The mutable copy lets the caller independently modify **the list structure**.

## 9. `List.copyOf` Does Not Protect the State of Mutable Elements

If a `List` contains mutable objects, copying the structure is not enough.

Example: `Card` with a setter:

```java
class Card {
    private String title;

    Card(String title) {
        this.title = title;
    }

    void rename(String newTitle) {
        this.title = newTitle;
    }

    String title() {
        return title;
    }
}
```

With:

```java
Card card = new Card("A");
List<Card> input = new ArrayList<>();
input.add(card);

List<Card> result = List.copyOf(input);
card.rename("B");
```

Afterward, `result.get(0).title()` is `"B"`, because `result.get(0)` is still **the exact same `card` object**.

**An unmodifiable list does not mean immutable elements.** The caller cannot call `result.add(...)`, yet if they hold a reference to `Card`, they can still call `rename`.

### Runnable Program for Element Aliasing

Save **`MutableElementDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Card {
    private String title;

    Card(String title) {
        this.title = title;
    }

    void rename(String title) {
        this.title = title;
    }

    String title() {
        return title;
    }
}

public class MutableElementDemo {
    public static void main(String[] args) {
        Card card = new Card("Java");
        List<Card> source = new ArrayList<>();
        source.add(card);

        List<Card> snapshot = List.copyOf(source);
        source.clear();

        System.out.println(snapshot.size());
        System.out.println(snapshot.get(0).title());

        card.rename("Java 17");
        System.out.println(snapshot.get(0).title());
        System.out.println(snapshot.get(0) == card);
    }
}
```

```bash
javac -encoding UTF-8 MutableElementDemo.java
java MutableElementDemo
```

**Stdout:**

```text
1
Java
Java 17
true
```

`source.clear()` does not remove the element from `snapshot`. However, `snapshot` holds a reference to the old `Card`, so when `card.rename(...)` runs, the state displayed in the snapshot changes.

To isolate **the mutable elements as well**, a copy/immutable representation policy is needed for `Card`; for example, converting it into a record that only contains an immutable `String`, or creating a copy of each `Card`.

## 10. Deep Copying Across the Data Domain: Objects Containing Mutable Objects

There is no general `deepClone(object)` command in core Java that automatically copies every object graph correctly.

Consider a `Person` object containing a mutable `Address`:

```java
class Address {
    private String city;

    Address(String city) {
        this.city = city;
    }

    void setCity(String city) {
        this.city = city;
    }

    String city() {
        return city;
    }
}
```

If the `Person` constructor does `this.address = address;`, the caller still holds a reference to `address` and can call `address.setCity(...)` to change the state inside `Person`.

If the getter does `return address;`, the caller can do `person.address().setCity(...)`. **Both input and output are at risk of exposure.**

One solution is to **copy right at the boundaries**:

```java
Person(Address address) {
    this.address = new Address(address.city());
}

Address address() {
    return new Address(address.city());
}
```

This requires `Address` to be designed so that retrieving `city()` is sufficient to represent the desired state and there are no other mutable references that need to be copied.

### 10.1. Complete Program

Save **`DefensiveObjectDemo.java`**:

```java
import java.util.Objects;

final class Address {
    private String city;

    Address(String city) {
        this.city = Objects.requireNonNull(city, "city");
    }

    Address(Address other) {
        this(other.city);
    }

    String city() {
        return city;
    }

    void setCity(String city) {
        this.city = Objects.requireNonNull(city, "city");
    }
}

final class Person {
    private final String name;
    private final Address address;

    Person(String name, Address address) {
        this.name = Objects.requireNonNull(name, "name");
        this.address = new Address(
                Objects.requireNonNull(address, "address"));
    }

    String name() {
        return name;
    }

    Address address() {
        return new Address(address);
    }

    String city() {
        return address.city();
    }
}

public class DefensiveObjectDemo {
    public static void main(String[] args) {
        Address fromCaller = new Address("Hà Nội");
        Person person = new Person("An", fromCaller);

        fromCaller.setCity("Huế");
        Address returned = person.address();
        returned.setCity("Đà Nẵng");

        System.out.println(fromCaller.city());
        System.out.println(returned.city());
        System.out.println(person.city());
    }
}
```

```bash
javac -encoding UTF-8 DefensiveObjectDemo.java
java DefensiveObjectDemo
```

Stdout:

```text
Huế
Đà Nẵng
Hà Nội
```

Analysis:
- `Person` does not store the caller's `Address` object; the constructor creates a **copy**.
- `Person.address()` does not return the `address` field directly; the getter creates **another copy**.
- Calling `fromCaller.setCity(...)` and `returned.setCity(...)` does not change `person.city()`.

**Domain-appropriate copying policy:** if `Address` has other mutable fields, the copy constructor must handle them. If `Address` contains a mutable collection, copying the collection and its inner elements must also be considered.

## 11. Switching to Immutable Types Instead of Copying Repeatedly

An often simpler strategy is **using immutable value objects** for internal data.

Java 17 example:

```java
record Address(String city) {
    Address {
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("city required");
        }
    }
}
```

Here, the `city` component has type `String`, which is an immutable type. The `Address` record provides no setter that changes the city after creation, so `Address` references can be shared more safely under a value contract.

With fields of immutable types, returning a reference generally does not expose **mutable state of that field**. This must be distinguished from a record containing mutable components.

### Records Are Not Deeply Immutable by Default

```java
record Scores(int[] points) {
}
```

The default constructor of the record above still receives and stores the **array reference**; the `points()` accessor returns that array. The caller can modify elements:

```java
int[] source = {7, 8};
Scores scores = new Scores(source);
source[0] = 0;
scores.points()[1] = -1;
```

There is no deep immutability even though record components are final.

### 11.1. Protecting a Record with an Array Component

Save **`SafeRecordDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record Scores(int[] points) {
    public Scores {
        points = Objects.requireNonNull(points, "points").clone();
    }

    @Override
    public int[] points() {
        return points.clone();
    }
}

public class SafeRecordDemo {
    public static void main(String[] args) {
        int[] input = {7, 8};
        Scores scores = new Scores(input);

        input[0] = 0;
        int[] returned = scores.points();
        returned[1] = -1;

        System.out.println(Arrays.toString(input));
        System.out.println(Arrays.toString(returned));
        System.out.println(Arrays.toString(scores.points()));
    }
}
```

```bash
javac -encoding UTF-8 SafeRecordDemo.java
java SafeRecordDemo
```

**Stdout:**

```text
[0, 8]
[7, -1]
[7, 8]
```

Explanation:
- The **compact constructor** `public Scores { ... }` validates and copies the `points` parameter, and then component field initialization uses the reassigned parameter value.
- The `points()` accessor is overridden to return a new array.
- Records still have considerations regarding `equals`, `hashCode`, and how arrays are compared; they use component semantics according to record rules, so arrays have identity-based `equals`/`hashCode` and do not automatically deep-compare elements. If content-based value semantics are needed, you must design/override appropriately or prefer components that are immutable collections/value objects.

The takeaway is that **a record makes component fields final**, yet **does not automatically copy or freeze the objects that components point to**.

## 12. Protecting a List Received from a Constructor

A constructor prone to state exposure:

```java
class Playlist {
    private final List<String> tracks;

    Playlist(List<String> tracks) {
        this.tracks = tracks; // Exposed via input
    }
}
```

If the caller still holds a reference to `tracks`, they can call `clear()` in a way that is observable through the `Playlist` object.

If the contents are `String` (immutable), a good approach is:

```java
Playlist(List<String> tracks) {
    this.tracks = List.copyOf(tracks);
}
```

`List.copyOf`:

- Creates list data that cannot be modified through the `List` API;
- Preserves the element order of the source;
- Rejects a `null` list or `null` elements;
- Isolates the internally stored list from **structural updates** to an ordinary mutable input;
- Only shallowly copies the element references.

Because the elements are immutable `String`s, there is no sharing of mutable elements in this example.

### 12.1. Playlist Example Program

Save as **`ImmutableListFieldDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Playlist {
    private final List<String> tracks;

    Playlist(List<String> tracks) {
        this.tracks = List.copyOf(tracks);
    }

    List<String> tracks() {
        return tracks;
    }

    int size() {
        return tracks.size();
    }
}

public class ImmutableListFieldDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("Intro");

        Playlist playlist = new Playlist(source);
        source.add("Outro");

        System.out.println(source);
        System.out.println(playlist.tracks());
        System.out.println(playlist.size());

        try {
            playlist.tracks().add("Extra");
        } catch (UnsupportedOperationException error) {
            System.out.println("Không sửa được danh sách trả về");
        }
    }
}
```

```bash
javac -encoding UTF-8 ImmutableListFieldDemo.java
java ImmutableListFieldDemo
```

Stdout:

```text
[Intro, Outro]
[Intro]
1
Không sửa được danh sách trả về
```

Here, `Playlist` stores an unmodifiable `List<String>`, and each `String` is also immutable. Therefore, the getter can **directly return** the `tracks` field without having to copy it every time.

**Clear contract:** `tracks()` returns unmodifiable data. A caller who wants to make modifications for their own purposes can write `new ArrayList<>(playlist.tracks())`, without affecting the `Playlist` object.

## 13. When the Internal List Must Remain Mutable

A class may need to add or remove elements through its own methods, for example when managing a group:

```java
final class Group {
    private final List<String> members = new ArrayList<>();

    void add(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
        members.add(name);
    }

    List<String> members() {
        return List.copyOf(members);
    }
}
```

These are illustrative declarations assuming `java.util.List` and `java.util.ArrayList` have already been imported.

- `Group.add` is the update path with validation.
- `Group.members` returns an **unmodifiable snapshot** of the list at the time of the call.
- The caller cannot bypass validation by directly modifying the backing list through the getter.
- If the `Group` object changes later, the returned snapshot still retains **the old structure and `String`s**.

### Cost and Consistency

Each `List.copyOf(members)` call may have to copy `n` elements, with a cost proportional to the list size. If the API is queried frequently, consider:
- Providing `size()` and `memberAt(index)` APIs;
- Caching an immutable snapshot when state changes (invalidation must be managed);
- Using an appropriate immutable/persistent data structure;
- Returning a live unmodifiable view **only when the contract accepts changes from the source**.

**Do not optimize by automatically returning the mutable backing list**: doing so breaks encapsulation boundaries and can cause hard-to-detect bugs.

## 14. `Collections.unmodifiableList`: When Is a View Appropriate?

A live unmodifiable view is not always wrong. It is appropriate when the caller **is allowed to observe updates to an object** but must not modify it through the returned reference.

Examples:
- A UI needs to display the model's current list and the UI is read-only;
- The API documentation explicitly states that the result is a **live view**;
- The collection owner retains exclusive rights to update it through its own methods.

However, note the following:
- If the caller still holds a mutable alias to the backing list, they can still modify it through that alias.
- Changes to the backing collection can cause an iterator over the view to throw `ConcurrentModificationException` due to the fail-fast mechanism of some collections; you should not rely on this exception for synchronization.
- An unmodifiable view **does not guarantee an independent snapshot** and **does not make elements immutable**.
- For passing data across thread boundaries, additional concurrency safety rules are required.

### Example of a Method Designing a Live View

```java
class Inventory {
    private final List<String> items = new ArrayList<>();
    private final List<String> readOnly =
            Collections.unmodifiableList(items);

    void add(String item) {
        items.add(item);
    }

    List<String> view() {
        return readOnly;
    }
}
```

This is an illustrative example that requires imports from `java.util`. `view()` returns a view that cannot be modified directly, yet `inventory.add("A")` causes the contents of the previously obtained view to change accordingly.

An API should **clearly name/document** `view()` or `snapshot()` so callers do not rely on false assumptions.

## 15. Unmodifiable Collection Factories in Java 17

Common APIs:

| API | Primary Result | Notes |
| --- | --- | --- |
| `List.of("A", "B")` | Unmodifiable list | Does not accept `null` |
| `List.copyOf(collection)` | Unmodifiable list from the source collection | Shallow; does not necessarily allocate a new object if the source is already suitable |
| `Set.of("A", "B")` | Unmodifiable set | Does not accept `null`; duplicate elements can cause `IllegalArgumentException` when passed directly to the factory |
| `Set.copyOf(collection)` | Unmodifiable set | From a collection with duplicate elements, the result is a set of unique elements; iteration order is unspecified |
| `Map.of("A", 1)` | Unmodifiable map | Does not accept `null` keys/values |
| `Map.copyOf(map)` | Unmodifiable map from the source | Shallow; key/value objects can be mutable |
| `Collections.unmodifiableList(list)` | Unmodifiable view | Reflects updates to the backing list |
| `Collections.unmodifiableMap(map)` | Unmodifiable view of the map | Reflects updates to the backing map |

**"Unmodifiable collection" only protects the structural modification interface.** If a key/value or element is a mutable object, changes to **the state of the element object** can still occur through an alias.

### Notes on `List.copyOf`

`List.copyOf` rejects `null` both when the input itself is null and when it contains a null element. Therefore, do not replace `new ArrayList<>(source)` with `List.copyOf(source)` without checking the null contract.

If the data must accept null, a different convention is needed (such as filtering, an appropriate Optional representation, or using a dedicated copy and view), rather than trying to force a factory whose contract rejects null to accept null.

## 16. `Arrays.asList` Is Not a Safe Copy

`Arrays.asList(array)` returns a fixed-size list **backed by the passed-in array** for the standard overload taking a reference array.

```java
String[] array = {"A", "B"};
List<String> list = Arrays.asList(array);

array[0] = "X";
list.set(1, "Y");
```

Afterward:
- `list` displays `[X, Y]`;
- `array` contains `["X", "Y"]`.

`list.add("Z")` is not supported because the size is fixed, yet `set` can modify elements and **the original array changes accordingly**.

### Illustrative Program

Save **`ArraysAsListDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;

public class ArraysAsListDemo {
    public static void main(String[] args) {
        String[] data = {"A", "B"};
        List<String> view = Arrays.asList(data);

        data[0] = "X";
        view.set(1, "Y");

        System.out.println(Arrays.toString(data));
        System.out.println(view);

        try {
            view.add("Z");
        } catch (UnsupportedOperationException error) {
            System.out.println("Không thể thêm phần tử");
        }
    }
}
```

```bash
javac -encoding UTF-8 ArraysAsListDemo.java
java ArraysAsListDemo
```

Stdout:

```text
[X, Y]
[X, Y]
Không thể thêm phần tử
```

**If the goal is a defensive copy**, `Arrays.asList(input)` **alone is not enough**. You can use `List.copyOf(Arrays.asList(input))` if the input is suitable and contains no nulls, though for mutable elements you must still consider shallow copying.

**With primitive arrays**, `Arrays.asList(intArray)` has different generic behavior: it typically produces a single-element list containing **the entire `int[]` array**, not a list of `Integer`s as many people expect. If you want a collection of integers, you need to convert each value according to your design, for example `IntStream.of(data).boxed().toList()` in Java 17, and remember that `Stream.toList()` returns an unmodifiable list.

## 17. Map: Expose Neither the Structure Nor Mutable Values

A `Map` can contain values of a mutable type:

```java
Map<String, List<String>> roles = new HashMap<>();
roles.put("admin", new ArrayList<>(List.of("read")));
```

If you return:

```java
return Map.copyOf(roles);
```

then the result is an unmodifiable map (disallowing `put` or `remove` through that map). However, the value for key `"admin"` can still be **the exact same `ArrayList<String>` object** that `roles` holds.

The caller can do:

```java
Map<String, List<String>> exposed = Map.copyOf(roles);
exposed.get("admin").add("write");
```

This **modifies the inner list**, even without changing the map structure. `Map.copyOf` does not automatically deep-copy the values.

### 17.1. Layer-by-Layer Copying

If you want to create a result with **String keys** and **immutable lists of Strings**, you can copy the list values first and then wrap the map:

```java
static Map<String, List<String>> snapshot(
        Map<String, List<String>> source) {

    Map<String, List<String>> copy = new HashMap<>();
    for (Map.Entry<String, List<String>> entry : source.entrySet()) {
        copy.put(entry.getKey(), List.copyOf(entry.getValue()));
    }
    return Map.copyOf(copy);
}
```

This snippet is an illustration that requires importing `java.util.Map`, `java.util.HashMap`, and `java.util.List`. It assumes there are no null keys, values, or list elements. Because both the keys and elements are immutable `String`s, this is a safe snapshot of **the map structure and the list values** within the scope of this example.

If the values contain mutable objects (such as `List<Card>`), you still need to isolate them or convert them to an immutable value representation.

### 17.2. Complete Java 17 Program

Save **`NestedMapCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class NestedMapCopyDemo {
    static Map<String, List<String>> snapshot(
            Map<String, List<String>> source) {

        Map<String, List<String>> copy = new HashMap<>();
        for (Map.Entry<String, List<String>> entry : source.entrySet()) {
            copy.put(entry.getKey(), List.copyOf(entry.getValue()));
        }
        return Map.copyOf(copy);
    }

    public static void main(String[] args) {
        List<String> permissions = new ArrayList<>(List.of("read"));
        Map<String, List<String>> source = new HashMap<>();
        source.put("admin", permissions);

        Map<String, List<String>> result = snapshot(source);
        permissions.add("write");
        source.put("guest", List.of("view"));

        System.out.println(source.get("admin"));
        System.out.println(result.get("admin"));
        System.out.println(result.containsKey("guest"));

        try {
            result.get("admin").add("delete");
        } catch (UnsupportedOperationException error) {
            System.out.println("Không thể sửa nested list");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 NestedMapCopyDemo.java
java NestedMapCopyDemo
```

**Stdout:**

```text
[read, write]
[read]
false
Không thể sửa nested list
```

The example intentionally **does not directly print the entire HashMap/Map.copyOf** because map iteration order can vary. Accessing via specific keys yields stable stdout.

## 18. Sets and Object Elements: Another Trap

`Set.copyOf(source)` prevents the caller from changing the set structure through the interface, yet **does not deep-copy element objects**.

Moreover, when an element is a mutable object used as a hash key, a change to the fields participating in `equals`/`hashCode` can cause the collection to behave unpredictably.

Example design to avoid:

```java
class MutableKey {
    String code;

    // equals/hashCode is based on code and code can change.
}
```

If a `HashSet<MutableKey>` already had a key added and then `key.code` is modified, a `contains` operation may fail to find the key as expected because the hash changed.

Defensive copying of **the Set structure** does not fundamentally solve the issue of **mutable element equality/hash**. You should generally use immutable value objects as set elements and map keys.

### `Set.copyOf` and Duplicate Values

If the input is a collection with duplicate elements, `Set.copyOf` creates a set of unique elements according to its rules. The result is not guaranteed to preserve the iteration order of the source list.

Do not use a Set when the contract needs to preserve occurrence counts or order. When creating a snapshot of data, **choosing the collection type with the right semantics** matters even more than choosing the copy API.

## 19. Preventing Exposure of `java.util.Date`, `Calendar`, and Some Standard Mutable Types

Not only custom-written collections pose a risk. `java.util.Date` and `Calendar` are mutable types.

Example of exposing a `Date` field:

```java
class Event {
    private final java.util.Date startsAt;

    Event(java.util.Date startsAt) {
        this.startsAt = startsAt;
    }

    java.util.Date startsAt() {
        return startsAt;
    }
}
```

The caller can use `Date.setTime(...)` on the original argument or the value returned by the getter to change the internal time.

One way to protect it:

```java
Event(Date startsAt) {
    this.startsAt = new Date(startsAt.getTime());
}

Date startsAt() {
    return new Date(startsAt.getTime());
}
```

In the example above, `Date` stores **a millisecond instant value**. Copy constructor logic based on `getTime`/`new Date(long)` creates another object to isolate mutation; null must be handled according to the contract. For a more complex domain, time comparison and validity must also be considered.

### Complete Program

Save **`DateDefensiveDemo.java`**:

```java
import java.util.Date;

final class Event {
    private final Date timestamp;

    Event(Date source) {
        this.timestamp = new Date(source.getTime());
    }

    Date timestamp() {
        return new Date(timestamp.getTime());
    }

    long epochMillis() {
        return timestamp.getTime();
    }
}

public class DateDefensiveDemo {
    public static void main(String[] args) {
        Date input = new Date(1000L);
        Event event = new Event(input);

        input.setTime(2000L);
        Date returned = event.timestamp();
        returned.setTime(3000L);

        System.out.println(input.getTime());
        System.out.println(returned.getTime());
        System.out.println(event.epochMillis());
    }
}
```

```bash
javac -encoding UTF-8 DateDefensiveDemo.java
java DateDefensiveDemo
```

Stdout:

```text
2000
3000
1000
```

To reduce the need for defensive copying, prefer immutable value types from `java.time` such as `Instant`, `LocalDate`, `LocalDateTime`, or `ZonedDateTime` when appropriate. Choose the right temporal type for the business requirement; do not replace `Date` with `LocalDate` if the project needs an **exact instant on the timeline**.

## 20. Do Getters Returning a Stream, Iterator, or Sublist Expose Data?

Getters returning a `List` are not the only ones at risk.

### Returning an `Iterator` over the Internal Collection

```java
Iterator<String> iterator() {
    return items.iterator();
}
```

An iterator of a mutable collection can allow `remove()` if the implementation supports it, thereby modifying the collection structure. Even an iterator that does not support remove can still observe changing state.

**Possible solution:** return an iterator of an unmodifiable snapshot:

```java
Iterator<String> iterator() {
    return List.copyOf(items).iterator();
}
```

This is still a shallow copy of the element objects and incurs a copying cost. Alternatively, design the API to access one value at a time.

### Returning `subList`

```java
List<String> firstTwo() {
    return items.subList(0, 2);
}
```

For standard `List` implementations, `subList` returns a **view backed by the original list**. Calling `set`/`clear` through the view can affect the backing list; structural changes made elsewhere can also render the view's semantics undefined under the contract.

If an independent snapshot is desired:

```java
List<String> firstTwo() {
    return List.copyOf(items.subList(0, Math.min(2, items.size())));
}
```

### Returning a `Stream`

```java
Stream<String> stream() {
    return items.stream();
}
```

A stream **is not automatically a snapshot**. With a mutable source, subsequent use of the stream can depend on the source's state and stream/spliterator processing rules. You should not claim that internal state is completely protected just because `Stream` has no `add()` method.

If the API requires data captured at a point in time, you can create a **snapshot before providing the stream**, for example `List.copyOf(items).stream()`, and still account for mutable elements.

## 21. Constructors, Setters, and Builders All Have Input Exposure Paths

Risks do not appear only in getters. A class can directly retain mutable input in:

- Constructors;
- Setters;
- Builders;
- Factory methods;
- Callback/observer registration methods;
- Methods that accept a collection and retain the reference for later processing.

Setter example:

```java
void replaceTags(List<String> tags) {
    this.tags = tags;
}
```

Right after calling `model.replaceTags(input)`, the caller still holds `input` and can call `input.clear()` to change the model's state.

With a field designed to be immutable:

```java
void replaceTags(List<String> tags) {
    this.tags = List.copyOf(tags);
}
```

If the requirements accept null or mutable elements, those cases must be handled according to the contract.

### A Builder Can Accidentally Pass an Alias into the Built Object

A builder holding a mutable list:

```java
class RequestBuilder {
    List<String> headers = new ArrayList<>();

    Request build() {
        return new Request(headers); // Risk if Request stores it directly
    }
}
```

If `Request` stores the same list and the builder continues to be used to add headers after `build()`, the already created `Request` product can be modified along with it.

**Solution:** the `Request` constructor (or `build()`) must snapshot/copy according to the ownership contract. For types with immutable elements, a `List.copyOf(headers)` may be sufficient.

In terms of design, **an immutable class should protect its own invariants upon creation**, rather than relying entirely on every caller or builder remembering to copy.

## 22. Should Defensive Copying Come Before or After Validation?

There are two concerns to distinguish:

1. **Validity validation**: does the data satisfy domain constraints?
2. **Ownership isolation**: can the stored object still be modified through an external alias?

A relatively solid pattern when receiving a mutable array:

```java
int[] localCopy = Objects.requireNonNull(input).clone();
for (int value : localCopy) {
    if (value < 0) {
        throw new IllegalArgumentException("negative value");
    }
}
this.values = localCopy;
```

Benefit: it validates **the exact data being stored**, avoiding the situation where one object is validated while a reference to another object or the original mutable input is stored.

However, if the input can be modified concurrently between reads during `clone`, cloning does not automatically turn the whole process into a transaction. **Copy + validate** does not replace thread-safety rules for the data source; receiving data requires clear ownership boundaries or synchronization.

When the input is an immutable type whose contract is already guaranteed, copying may be unnecessary.

### Should You Validate First and Copy Afterward?

If the data source is not modified concurrently, validating the input and then copying can produce the correct result in many programs. However, the **copy first, validate the copy itself** pattern is usually easier to prove invariant-safe, especially when the constructor's contract promises that the object stores the exact data that was checked.

Most importantly: **do not retain the caller's mutable alias without explicit ownership or a clear sharing agreement**.

## 23. Defensive Copying and Performance Requirements

Copying is not free:

| Operation | Typical Cost |
| --- | --- |
| `array.clone()` with `n` elements | `O(n)` time and memory |
| `new ArrayList<>(source)` | Structural copy of approximately `O(n)` |
| `List.copyOf(source)` | Typically around `O(n)` to copy a mutable source; may reuse an already suitable unmodifiable input |
| Deep copy of an object graph | Depends on the number of objects, references, and copying policy |
| Getter returning scalar `int`/`long` | Usually does not require allocating an object copy |
| Getter returning an immutable value | Usually can share references more safely |

**Optimize according to the contract first:**

1. If the caller only needs a sum or count, return a scalar instead of a collection.
2. If the data is immutable, it can be shared according to the contract.
3. If snapshots are needed repeatedly, consider caching the snapshot when the state changes.
4. If the data is large, avoid creating unnecessary deep copies when the caller only reads a portion.
5. If the API must return a live view, state this clearly and protect all mutation paths of the backing collection.

You should **not** switch to exposing a mutable reference simply because copying has a cost. First determine the frequency, size, ownership model, and correctness.

## 24. Ownership: When Can a Mutable Object Be Shared?

Not every case of sharing a mutable reference is wrong. Some APIs **intentionally share state**, for example:
- A shared session object with a clear update contract;
- An editor operating on the current model;
- A caller-owned collection that the API only processes immediately without retaining it after the method finishes;
- Concurrency abstractions that allow shared updates to an object.

What is concerning is **undisclosed sharing**, especially when:
- A class promises immutable state yet retains mutable input;
- A getter looks like a data reader yet returns an object that can modify internal state;
- Setter/constructor validation is later bypassed by the caller;
- Multiple threads hold a mutable reference without a synchronization contract.

A good model defines who **is allowed to modify**, whether the object continues to be retained after the call, and when the data is observed.

### Do Not Call Every Returned Object a "Deep Copy"

For example, `new ArrayList<>(source)` is a **new list**, yet it is usually only a **shallow copy**. Method names should clarify `snapshotTags()` or `copyTags()` accurately reflecting the isolated data, rather than `deepCopy` when mutable element aliases still remain.

## 25. Thread Safety: A Defensive Copy Does Not Automatically Provide an Atomic Snapshot

An example:

```java
List<String> snapshot = List.copyOf(sharedMutableList);
```

If **another thread is modifying sharedMutableList without synchronization**, the copying process can fail with an error or observe inconsistent data depending on the collection and timing. The statement above **does not automatically create a global lock**.

A thread-safe class must consider:
- All paths that can update state;
- Visibility across threads, `happens-before`, and synchronization;
- Atomicity of read-modify-write operations;
- When the snapshot is created;
- Safe publication of constructed objects.

With a list protected by a lock, a snapshot can be created **under the same lock** that all writers obey. Afterward, callers reading an unmodifiable snapshot containing immutable elements can reduce the need for read synchronization.

`Collections.unmodifiableList` only blocks mutators through the view; it does **not** make the backing list thread-safe. Nor does `List.copyOf` automatically fix all concurrency issues at the moment the source is read.

## 26. Preventing State Exposure When Using Map Keys and equals/hashCode

When using a mutable object as a `Map` key or `Set` element, changing fields involved in `equals`/`hashCode` after inserting the object into a hash-based collection can break lookup consistency.

One way to reduce risk:
- Use immutable value objects as keys, for example `String`, `UUID`, or a record containing only truly immutable components;
- If a mutable key object must be accepted, create a canonical immutable representation or an appropriate defensive copy;
- Do not return internal mutable key objects for the caller to edit freely.

**Map.copyOf** prevents adding or removing entries through the returned map, yet it **does not make mutable keys immutable**, nor does it automatically deep-copy keys or values. Encapsulation must be verified at **every mutable node in the data structure**.

## 27. Distinguishing *defensive copy* from *unmodifiable wrapper*

Summary by question:

| Return Strategy | Can the caller modify the result structure? | Do subsequent source structure modifications affect the result? | Does a mutable element alias remain? |
| --- | --- | --- | --- |
| `return internalList;` | Yes, if the list is mutable | Yes, because it is the same object | Yes |
| `return Collections.unmodifiableList(internalList);` | No, not through the view | **Yes**, because the backing list is shared | Yes |
| `return new ArrayList<>(internalList);` | **Yes**, but on a different list | **No** for the list structure | Yes |
| `return List.copyOf(internalList);` | **No**, not through the snapshot | No for the structure from an ordinary mutable source | Yes |
| Returning an immutable list of immutable values | No | No under the snapshot contract | No corresponding mutable element state |
| Copying each mutable element and then wrapping | No, if the output is also unmodifiable | No, when all mutable paths are properly isolated | Depends on the depth of copying performed |

**Practical conclusion:** the goal does not necessarily have to be "deep copy everything". Determine **the data level that needs to be immutable**. For example, a list of `String`s only needs `List.copyOf`; a list of mutable `Address` objects requires additional design for the elements.

## 28. Preventing Exposure of Byte Arrays in Objects Containing Sensitive Data

An application may store keys, secret codes, or payloads as `byte[]`. Beyond correctness, returning the array directly also allows the caller to **modify the data outside the class's control**.

Example:

```java
final class Packet {
    private final byte[] payload;

    Packet(byte[] payload) {
        this.payload = payload.clone();
    }

    byte[] payload() {
        return payload.clone();
    }
}
```

Here each side receives a copy of the array. However, **copying does not by itself solve the security problem of secret data**, because copies may still linger in memory, the GC does not guarantee immediate erasure, and the system may have special lifecycle management requirements.

If truly managing secret bytes, a clear policy is needed covering when copies are zeroed out, which classes are permitted to handle them, avoiding logging, concurrency, and JVM memory limitations. This lesson focuses on **preventing state modification via aliases**, and does not claim that `clone()` guarantees wiping sensitive data from memory.

## 29. Testing Encapsulation: Try "Attacking" Both Input and Output

One way to verify a design is to write tests that attempt to mutate the object from the caller's side.

### Testing Procedure for Arrays

1. Create a source array `input`.
2. Call the constructor `new Holder(input)`.
3. Modify `input[0]`.
4. Verify that the Holder's state **does not change**.
5. Retrieve `int[] output = holder.values()`.
6. Modify `output[0]`.
7. Verify that the Holder **still does not change**.

### Testing Procedure for Lists

1. Create a mutable `ArrayList` as input.
2. Create the object holding the list from the input.
3. Call `input.add(...)` or `input.clear()`.
4. Verify that the internal snapshot/list does not change outside the contract.
5. Retrieve the list from the getter.
6. Try `getterResult.add(...)` and verify whether it should be blocked or only modify a copy.
7. If the list contains mutable objects, try **modifying the state of an element**.
8. If the object has multiple nested collections, try modifying each level.

### Observing Identity When Necessary

`result == internal` can be useful in dedicated tests **within an allowed scope**, yet differing identities should not be treated as sufficient proof of a **deep copy**. Two different outer lists can still hold the same mutable element.

**Verification contracts should focus on state/invariants**, rather than forcing every getter to return a new object in all cases. If a field is truly immutable, returning the same object is generally valid.

## 30. Common Mistakes and How to Fix Them

| Situation | What Is Wrong? | How to Improve |
| --- | --- | --- |
| `private final int[] data` yet getter returns `data` | Exposes the array through output | `return data.clone();` |
| Constructor `this.data = input;` | Caller retains an input alias | Copy input before storing |
| `return new ArrayList<>(items)` while assuming a deep copy | Elements are still shared | Copy mutable elements or use immutable values |
| `return Collections.unmodifiableList(items)` while thinking it is a snapshot | View can reflect mutations to the backing list | Use `List.copyOf(items)` if a snapshot is needed |
| `List.copyOf(cards)` yet the caller can mutate `Card` | Copies element references shallowly | Copy each `Card` or switch to immutable records/DTOs |
| `return Arrays.asList(data);` | View is backed by the array; `set` can change the array | Use a snapshot such as `List.copyOf(Arrays.asList(data))` when appropriate |
| Getter returns `Date` directly | `Date.setTime` changes the internal object | Copy `Date` on both sides or use `Instant` |
| Record holding `int[]` while assuming it is immutable | Record components are only shallowly immutable | Copy in the compact constructor and copy in the accessor |
| `final List<String> items` while thinking items cannot be added | `final` forbids reassigning the field, not mutating the list | Use unmodifiable data or a controlled mutation API |
| `Map.copyOf` yet nested lists can still be modified | Map is only unmodifiable at the map level | Copy nested collections/values |
| `List.copyOf` encounters null | The API rejects null | Define a null contract, filter, or choose another representation |
| `List.of(...)` then attempting `add`/`remove` | The factory creates an unmodifiable list | Use a mutable copy if modification is genuinely needed |
| Assuming `List.copyOf` always creates a new object | The implementation may reuse an unmodifiable input | Test semantics rather than relying on identity |
| Getter only returns a `Stream` while the source is mutable | A stream is not automatically a snapshot | Create a snapshot beforehand if needed |
| Setter stores a list that a builder still modifies | Builder and built object share the same backing list | Copy when building/constructing |
| Calling `clone()` on a 2D array and then mutating a row | Cloning the outer array is shallow | Copy each inner array |
| `HashSet` containing a mutable key whose `hashCode` changes | Hash lookup can become unstable | Use an immutable key |
| Copying a list while another thread is writing | Copying is not automatically atomic/thread-safe | Establish ownership or synchronization |
| Public getter returns an internal mutable object | Bypasses the owner's validation | Return a copy/immutable view or a read API |
| Getter uses defensive copy, yet constructor does not copy | Input alias still exposes state | Check **both directions** |
| Constructor copies, yet getter returns the field directly | Output alias still exposes state | Check **both directions** |
| Deep copying via automatic serialization | Assumes every type is serializable and copies properly | Design copying according to the domain, object graph, resources, and contract |

## 31. Self-Practice Exercises with Answers

### Exercise 1 — Is `private final` Already Safe?

```java
class Scores {
    private final int[] data;

    Scores(int[] data) {
        this.data = data;
    }

    int[] getData() {
        return data;
    }
}
```

**Question:** what are two ways the caller can modify internal state without calling a mutator?

**Answer:** (1) modifying the original `data` array after passing it to the constructor, and (2) modifying the array returned by `getData()`. `private final` does not block mutation of the array object. You must copy on input and output, or design the API not to return the array.

### Exercise 2 — Does an Unmodifiable View Stay Static?

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
source.add("B");
System.out.println(view);
```

**Answer:** `[A, B]`. The view does not allow direct modification through itself, yet reflects changes to the backing list structure made through the `source` alias.

### Exercise 3 — Does a Snapshot List Show Updates to the Source?

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> snapshot = List.copyOf(source);
source.add("B");
System.out.println(snapshot);
```

**Answer:** `[A]`. The snapshot structure does not change with updates to `source`. Because `String` is immutable, there is also no mutable element state to worry about in this example.

### Exercise 4 — Does Shallow Copying Protect `Card`?

```java
Card card = new Card("A");
List<Card> source = new ArrayList<>(List.of(card));
List<Card> snapshot = List.copyOf(source);
card.rename("B");
System.out.println(snapshot.get(0).title());
```

**Answer:** `B`. The snapshot holds the same `Card` reference. To encapsulate Card's state, you need to copy the elements or convert them to an immutable representation.

### Exercise 5 — Two-Dimensional Arrays

```java
int[][] a = {{1}, {2}};
int[][] b = a.clone();
b[0][0] = 7;
System.out.println(a[0][0]);
```

**Answer:** `7`. `clone()` only copies the outer array; `a[0]` and `b[0]` both point to the first row. To isolate a primitive matrix, each row must be cloned.

### Exercise 6 — Is `Arrays.asList` Independent?

```java
String[] array = {"A"};
List<String> view = Arrays.asList(array);
view.set(0, "B");
System.out.println(array[0]);
```

**Answer:** `B`. `Arrays.asList` returns a view backed by the array, not a defensive copy.

### Exercise 7 — Is a Record Deeply Immutable Automatically?

```java
record ScoreRecord(int[] values) {
}
```

**Answer:** **No.** Passing an array into the canonical constructor and receiving the array through the default accessor can expose the same mutable object. You need to copy in the constructor/accessor or choose an immutable data type.

### Exercise 8 — Unmodifiable Map, Still Mutable Value?

```java
List<String> values = new ArrayList<>(List.of("read"));
Map<String, List<String>> source = Map.of("admin", values);
Map<String, List<String>> copied = Map.copyOf(source);
values.add("write");
System.out.println(copied.get("admin"));
```

**Answer:** `[read, write]`. The map's structure cannot be modified, yet the list used as a value is still a shared mutable object.

### Exercise 9 — Does `List.copyOf` Accept Null?

```java
List<String> input = new ArrayList<>();
input.add(null);
List<String> result = List.copyOf(input);
```

**Answer:** `List.copyOf` throws `NullPointerException` because the source collection contains a null element. This is part of the API contract, not an accidental bug in the implementation.

### Exercise 10 — When Can a Getter Return the Field Directly?

Suppose a class stores:

```java
private final List<String> names;

MyType(List<String> source) {
    this.names = List.copyOf(source);
}
```

**Answer:** If the contract only needs a snapshot of immutable `String` values, `return names;` is appropriate because the list itself is unmodifiable and its elements are immutable. There is no need to clone in every getter just to get a different identity. If `names` contains mutable elements, deeper consideration is required.

### Exercise 11 — Must Validation Hold After the Constructor?

A constructor checks that all scores are between `0` and `10`, yet retains the input array directly. The caller later changes the input to `-5`. Is the invariant guaranteed?

**Answer:** **No.** The validation step only checks the state at the time of the call; an external alias can still cause the object to contain invalid data. Copy the stored data and avoid exposing the copy through getters.

### Exercise 12 — Mutable Object Exposure Even Without a Setter?

A class declares no setters at all, yet its getter returns an internal `java.util.Date`. Is it immutable?

**Answer:** **Not necessarily.** The caller can call `date.setTime(...)` on the returned object. Having no setters on the owning class does not prevent mutators on **the child object**; defensive copying or an appropriate immutable type is needed.

## 32. Checklist for Reviewing a Safely Encapsulated Class

1. **List fields of mutable reference types:** arrays, lists, sets, maps, builders, mutable DTOs, Date/Calendar, nested object graphs.
2. **Check constructors:** do they retain the same input object? Do they copy first and then validate the exact copy that will be stored?
3. **Check setters:** do they assign mutable input directly to a field? Are there specific ownership rules?
4. **Check getters:** do they return the backing array/list/map/object directly, or only read values/copies/snapshots?
5. **Check both sides:** copying only on input while exposing output is still wrong; copying only on output while retaining an input alias is also wrong.
6. **Check element mutability:** `List.copyOf`/`Map.copyOf` are shallow; are there nested mutable elements or mutable keys?
7. **Check `clone()` on multidimensional arrays:** only the outer array is cloned unless you iterate row by row.
8. **Check view APIs:** `Collections.unmodifiableList` is a live view, `Arrays.asList` is backed by the array, and `subList` is typically a view.
9. **Check null handling:** `List.copyOf`/`Map.copyOf`/`Set.copyOf` have a contract that rejects null; is the class's API compatible?
10. **Check record return types:** a final component does not prove that the child object is immutable.
11. **Prefer immutable value objects:** `String`/`Instant`/records containing truly immutable fields when appropriate.
12. **If the API needs to let the caller modify their own data:** return a mutable copy instead of the backing collection.
13. **If the API needs the caller to always see new changes:** you can return a live unmodifiable view **if explicitly documented**, and ensure the backing list is only modified by its owner.
14. **If there is a builder:** after `build()`, does the builder still hold an alias into the built object? Does the built object need a snapshot?
15. **If there are map/set hash keys:** do the keys have immutable `equals`/`hashCode`?
16. **If there is concurrency:** is snapshot creation properly synchronized when the source is modified? Has safe publication been considered?
17. **Evaluate actual performance:** is an `O(n)` copy necessary on every getter, or can a scalar API or cached immutable snapshot be used?
18. **Write two-way tests:** modify the input after the constructor and modify the output after the getter, verifying that the object is not altered outside its contract.
19. **Check nested levels as well:** lists of lists, maps of lists, objects containing Date and arrays.
20. **Explicitly document the API contract:** is the result a snapshot, live view, mutable copy, or shared mutable reference?

## Key Takeaways

- **`private` protects field access, and does not automatically protect the mutable object that the field points to.** `final` only restricts reassigning the field reference, and does not automatically make the object immutable.
- **Defensive copying on input** prevents the caller from continuing to modify internal state through the passed-in data; **copying or returning an immutable result on output** prevents modifying internal state through getters.
- **One-dimensional primitive arrays:** `clone()`/`Arrays.copyOf` is usually sufficient; **multidimensional arrays or arrays of mutable objects:** **nested elements** must be considered.
- **`Collections.unmodifiableList` is a read-only view** that can reflect updates to the backing list; **`List.copyOf` is an unmodifiable structural snapshot** of a mutable source, yet **shallow** with respect to mutable elements.
- **`Arrays.asList` is not a defensive copy** for reference arrays; `set` can mutate the array.
- **`Map.copyOf` and `Set.copyOf` do not deep-copy keys/values/elements**. If those objects are mutable, aliases can still remain.
- **A record is not automatically deeply immutable** if a component is an array, collection, or mutable object.
- **Use immutable value types whenever possible**, and design APIs around a clear ownership/snapshot contract.
- **Check both exposure directions and every mutable layer** so that encapsulation genuinely protects the object's invariants.
