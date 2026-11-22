# Designing `private final` Fields and Complete Initialization in Java Immutable Classes

## 1. Goal: An Object with Valid and Unchanging State After Creation

An **immutable class** is a class in which **the observable state of each object does not change after the object is completely constructed**. Users of the object can read data or request computations, but cannot cause the logical value of the same object to change from state A to state B.

In Java, a common design approach for an immutable value object is:

1. Declare the class `final` when subclassing does not need to be supported, to prevent subclasses from altering the immutability contract.
2. Make instance fields `private` so that external code is not allowed to access/assign them directly.
3. Declare fields `final` so that each field is assigned only according to initialization rules and cannot be reassigned afterward.
4. **Completely initialize** every field from valid data before the constructor completes normally.
5. Do not provide any setter or method that mutates observable state.
6. For **mutable inputs** (arrays, lists, `Date`, other mutable objects), use an appropriate **defensive copy** or immutable snapshot.
7. When returning data externally, do not expose references to internal mutable state.
8. Do not let `this` escape before the constructor and invariants are complete.

Standard example:

```java
public final class Product {
    private final String code;
    private final int price;

    public Product(String code, int price) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code required");
        }
        if (price < 0) {
            throw new IllegalArgumentException("negative price");
        }

        this.code = code;
        this.price = price;
    }

    public String code() {
        return code;
    }

    public int price() {
        return price;
    }
}
```

This is a **valid class to save in `Product.java`**, though it does not have `main` yet. `String` is immutable, `int` is a primitive, and the private final fields are assigned exactly once in the constructor. With the existing methods, the caller cannot cause `code` or `price` of an already created Product to change.

**Notable point:** `private final` is the **foundation**, but **not sufficient** if a field points to a mutable object. For example, `private final List<String> items` can still point to an `ArrayList` that is being mutated.

## 2. Distinguishing `private`, `final`, and Immutability

Three concepts are very easily confused:

| Concept | Primary Guarantee | What It Does Not Automatically Guarantee |
| --- | --- | --- |
| `private` | Restricts direct access to the member outside the allowed scope | Does not prevent methods in the class from modifying the field |
| `final` on an instance field | The field must be assigned according to definite-assignment rules and cannot be reassigned after initialization | Does not make the referenced object immutable |
| `final` on a class | The class cannot be subclassed | Does not prevent the class itself from modifying mutable fields |
| Immutable object design | Observable state does not change after construction | Does not arise solely from a single modifier |

Example of a class that is **not yet immutable** despite having a private field:

```java
class Counter {
    private int count;

    void increment() {
        count++;
    }
}
```

`private` only prevents the caller from directly writing `counter.count = ...`; the `increment()` method itself still mutates it.

Another example that is **not yet immutable** even though the field is private final:

```java
class Box {
    private final java.util.List<String> names =
            new java.util.ArrayList<>();

    void add(String name) {
        names.add(name);
    }
}
```

The field reference `names` cannot point to a different list after initialization, but **the contents of the list change** after `add`.

**Correct reasoning:** You need to examine the **observable state**, the objects held internally, and the entire public/protected/package-private API, rather than just counting how many times the `final` keyword appears.

## 3. First Runnable Example: Immutable Value Object

Create the file **`ImmutableProductDemo.java`**:

```java
final class Product {
    private final String code;
    private final int price;

    Product(String code, int price) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code required");
        }
        if (price < 0) {
            throw new IllegalArgumentException("negative price");
        }

        this.code = code;
        this.price = price;
    }

    String code() {
        return code;
    }

    int price() {
        return price;
    }

    Product withPrice(int newPrice) {
        return new Product(code, newPrice);
    }

    @Override
    public String toString() {
        return code + ":" + price;
    }
}

public class ImmutableProductDemo {
    public static void main(String[] args) {
        Product original = new Product("P1", 100);
        Product updated = original.withPrice(120);

        System.out.println("original=" + original);
        System.out.println("updated=" + updated);
        System.out.println("same reference=" + (original == updated));
    }
}
```

Run with JDK 17+:

```bash
javac ImmutableProductDemo.java
java ImmutableProductDemo
```

**Standard output:**

```text
original=P1:100
updated=P1:120
same reference=false
```

**Explanation:**

1. `Product` is a `final class`, so no subclass can alter Product's contract.
2. `code` and `price` are `private final`, validated and assigned in the constructor.
3. There is no `setCode` or `setPrice` to modify Product after creation.
4. `withPrice(120)` **does not modify original**. It creates a **new Product** with a different state.
5. The two references `original` and `updated` are different, while original stays `P1:100`.

The `with...` approach returning a new object is often well-suited for immutable value classes. It has object allocation cost, but in return makes it simpler to reason about state and sharing; evaluate the trade-off based on actual requirements, rather than assuming every object in the system must be immutable.

## 4. What Does “Complete Initialization” Mean?

An object is **completely initialized** when every required property has a **valid and consistent** value before being published for use.

This consists of two distinct layers of requirements:

**A. Definite assignment by the Java compiler:** every **blank final instance field** must be definitely assigned according to the rules before the constructor completes normally.

**B. Domain invariant:** data must satisfy **business rules** such as non-blank codes, non-negative amounts, `start <= end`, non-null values, and lists containing no invalid entries.

The compiler can check A, but **cannot automatically check all of B**. For example, `private final String code` assigned `null` can still **compile**, but if the domain does not accept null, the constructor must check for it.

A constructor should **validate inputs before successfully publishing the instance**, and then assign fields consistently. If validation fails and an exception is thrown, the caller does not receive a normally completed object.

### Code Example Rejected When a Blank Final Field Is Unassigned

```java
// Example of a compile-time error when uncommented:
//
// class Broken {
//     private final int id;
//
//     Broken() {
//         // id is not assigned.
//     }
// }
```

`id` is a blank final field. Even though Java assigns a default value to instance storage, the compiler **does not consider the default 0 to be a sufficient assignment for a `final` field**. The constructor is required to definitely assign the field according to the rules.

## 5. A `final` Field Can Be Initialized at Declaration or in the Constructor

Both approaches are valid:

**Initializing at field declaration:**

```java
class FixedVersion {
    private final int version = 1;
}
```

**Initializing in the constructor:**

```java
class VersionedItem {
    private final int version;

    VersionedItem(int version) {
        this.version = version;
    }
}
```

Differences:

- A field with an initializer at declaration is assigned during the instance initialization process for each instance.
- A blank final field has no initializer and must be assigned according to a valid constructor flow.
- If `private final int version = 1;` is already declared, **`version` cannot be reassigned in the constructor**.
- If the value depends on arguments, assigning it in the constructor usually expresses the intent more clearly.
- If there is a shared value that does not depend on each instance, consider an appropriate `static final` constant instead of having each object hold its own field, though the semantics differ from an instance final field.

### Incorrect Example Due to Assigning a Final Field Twice

```java
// class Broken {
//     private final int version = 1;
//
//     Broken() {
//         version = 2; // Compile-time error.
//     }
// }
```

It is not only “reassigning after the constructor finishes” that is prohibited. For a final field already initialized at declaration, attempting to write to it again in the constructor is also invalid.

## 6. Constructor Chaining: `this(...)` and One Primary Assignment Point

With multiple constructor overloads, validation/assignment should be consolidated into **one canonical constructor** to reduce the chance of forgetting a field or creating inconsistent invariants.

File **`ImmutableConstructorChainDemo.java`**:

```java
final class Customer {
    private final String name;
    private final String country;

    Customer(String name) {
        this(name, "VN");
    }

    Customer(String name, String country) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
        if (country == null || country.isBlank()) {
            throw new IllegalArgumentException("country required");
        }
        this.name = name;
        this.country = country;
    }

    String label() {
        return name + "@" + country;
    }
}

public class ImmutableConstructorChainDemo {
    public static void main(String[] args) {
        Customer first = new Customer("An");
        Customer second = new Customer("Binh", "SG");

        System.out.println(first.label());
        System.out.println(second.label());
    }
}
```

```bash
javac ImmutableConstructorChainDemo.java
java ImmutableConstructorChainDemo
```

```text
An@VN
Binh@SG
```

- The single-parameter constructor begins with `this(name, "VN")`.
- The two-parameter constructor is the **assignment point** for both fields after validating the inputs.
- The fields are not assigned again when returning to the single-parameter constructor.
- In Java 17, an explicit constructor invocation `this(...)` or `super(...)` must be placed at the beginning of the constructor body according to the rules of this version.
- Choosing one constructor responsible for complete initialization helps avoid duplication of validations and assignment logic.

**Do not write** a constructor that uses `this(...)` and afterward assigns `final` fields already assigned by the target constructor.

## 7. Validate All Relationships Between Fields, Not Just Individual Fields

Example storing start/end times:

```java
final class TimeRange {
    private final int start;
    private final int end;

    TimeRange(int start, int end) {
        if (start < 0 || end < start) {
            throw new IllegalArgumentException("invalid range");
        }
        this.start = start;
        this.end = end;
    }

    int duration() {
        return end - start;
    }
}
```

This is a **valid class declaration**, without `main` yet.

`start` and `end` are both `final`, but the actual invariant also requires `start >= 0` and `end >= start`. The compiler does not know that this is a domain invariant.

If the constructor receives information from multiple sources, consider the **consistency of the entire state**. Avoid the pattern of “temporarily assigning and letting a setter complete it later” for an object whose public API requires it to always be valid.

**For algorithms with overflow**, additional range checks/sufficiently large data types are needed according to business requirements. The example above illustrates the relationship between two fields and does not claim to be suitable for all types of numbers or real-world times.

## 8. `private` Prevents the Caller from Modifying a Field Directly, Not the Class Itself

File **`PrivateNotImmutableDemo.java`**:

```java
class Meter {
    private int value;

    Meter(int value) {
        this.value = value;
    }

    void change(int next) {
        value = next;
    }

    int value() {
        return value;
    }
}

public class PrivateNotImmutableDemo {
    public static void main(String[] args) {
        Meter meter = new Meter(10);

        System.out.println(meter.value());
        meter.change(20);
        System.out.println(meter.value());
    }
}
```

```bash
javac PrivateNotImmutableDemo.java
java PrivateNotImmutableDemo
```

```text
10
20
```

`private` protects against direct access from the caller. However, `change` is a valid instance method and mutates the field. Therefore, this is **not an immutable object**.

If immutability is desired, fields should generally be `final` with no mutator; or the API should be organized to return a **new object** when data changes. A class with mutable state is sometimes still the right design (for example, a mutable buffer), but it should not be labeled immutable when the API changes observable state.

## 9. `final` on a Reference: Fixes the Reference, Not the Object

Consider:

```java
final java.util.List<String> names =
        new java.util.ArrayList<>();

names.add("An"); // Valid: mutates the list object.
// names = new java.util.ArrayList<>(); // Invalid: reassigning a final variable.
```

The same applies to **`private final List<String> names`** inside a class.

### Runnable Counterexample

File **`FinalReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Group {
    private final List<String> members = new ArrayList<>();

    void add(String name) {
        members.add(name);
    }

    List<String> members() {
        return members;
    }
}

public class FinalReferenceDemo {
    public static void main(String[] args) {
        Group group = new Group();

        group.add("An");
        group.members().add("Binh");

        System.out.println(group.members());
    }
}
```

```bash
javac FinalReferenceDemo.java
java FinalReferenceDemo
```

```text
[An, Binh]
```

Even though the `members` field is `private final`:

1. The `add` method mutates the internal list.
2. The getter `members()` returns **the exact list reference**; the caller can mutate internal state through it.
3. Therefore, Group is **mutable**, not an immutable value object.

Both **constructor inputs** and **getter outputs** must be handled if the referenced state can mutate. This is why defensive copying is important.

## 10. Defensive Copying with Arrays on Input and Output

Java arrays are mutable: elements can be modified with `array[i]=...`. The field `private final int[] scores` only fixes the **array reference**, and does not prevent modifying the slots.

File **`ImmutableScoresDemo.java`**:

```java
import java.util.Arrays;

final class Scores {
    private final int[] values;

    Scores(int[] input) {
        if (input == null) {
            throw new IllegalArgumentException("scores required");
        }
        for (int value : input) {
            if (value < 0) {
                throw new IllegalArgumentException("negative score");
            }
        }

        values = input.clone(); // Copy at ingress.
    }

    int size() {
        return values.length;
    }

    int at(int index) {
        return values[index];
    }

    int[] snapshot() {
        return values.clone(); // Copy at egress.
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class ImmutableScoresDemo {
    public static void main(String[] args) {
        int[] source = {10, 20};
        Scores scores = new Scores(source);

        source[0] = 99;
        System.out.println("after source change=" + scores);

        int[] fromGetter = scores.snapshot();
        fromGetter[1] = 77;

        System.out.println("after getter change=" + scores);
        System.out.println("size=" + scores.size());
        System.out.println("first=" + scores.at(0));
    }
}
```

```bash
javac ImmutableScoresDemo.java
java ImmutableScoresDemo
```

```text
after source change=[10, 20]
after getter change=[10, 20]
size=2
first=10
```

**Copying in both directions is necessary:**

- `input.clone()` in the constructor prevents the caller from modifying the object via the original array after passing it in.
- `values.clone()` in the getter prevents the caller from obtaining the internal reference and modifying slots.
- `size` and `at` return primitives, without exposing the mutable array.

`clone()` on `int[]` creates a new one-dimensional primitive array with the same values; this is sufficient for this example. If it were `MutableElement[]`, clone only copies the **array structure**, not deep-copying each mutable element.

**Concurrency detail:** If the input array is mutated concurrently by another thread while the constructor is validating/copying it, there is a risk of inconsistency between validation and the snapshot. In single-threaded examples, it is assumed the caller does not modify the input concurrently; production code needs appropriate ownership or synchronization if data can change concurrently.

## 11. Why Copying Only in the Getter Is Not Enough

Suppose the constructor is written as:

```java
class BadSnapshot {
    private final int[] values;

    BadSnapshot(int[] values) {
        this.values = values; // Only keeps an alias, does not copy.
    }

    int[] values() {
        return values.clone();
    }
}
```

The getter performs a defensive copy, but **the caller retains the original input array**. After `new BadSnapshot(source)`, if the caller writes `source[0] = 999`, the internal state `BadSnapshot.values` also changes.

Conversely, if the constructor copies but the getter returns the internal array directly, the caller gets another path to mutate it. Therefore, you must inspect **every alias path into and out of mutable state**, not just one side.

Principle:

```text
Caller mutable input
       |
       v
Validate / snapshot (copy)
       |
       v
Private final internal state
       |
       v
Query primitives / immutable values
       or copy when returning mutable data
       |
       v
Caller output
```

Copying on both sides is not always the only option: you can use immutable value components, a read-only API whose implementation genuinely cannot be mutated, or enforce strict ownership transfer rules. However, if a class is advertised as immutable for general callers, defensive copying is the approach that is easier to prove.

## 12. `List.copyOf` Creates an Immutable Structural Snapshot

Since Java 10, `List.copyOf(collection)` creates an **unmodifiable list** containing the elements from the input according to its contract. For mutable inputs such as `ArrayList`, this is a very useful way to break the list structural alias.

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

    int size() {
        return songs.size();
    }
}

public class ImmutablePlaylistDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        Playlist playlist = new Playlist(source);
        source.add("B");

        System.out.println("source=" + source);
        System.out.println("playlist=" + playlist.songs());

        try {
            playlist.songs().add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot modify playlist");
        }

        System.out.println("size=" + playlist.size());
    }
}
```

```bash
javac ImmutablePlaylistDemo.java
java ImmutablePlaylistDemo
```

```text
source=[A, B]
playlist=[A]
cannot modify playlist
size=1
```

Why can the getter return `songs` directly here?

- `List.copyOf` provides an unmodifiable list whose structure callers cannot mutate using `add`/`remove`.
- In the example, the elements are immutable `String`s, so there is no nested mutable element to alter the meaning of the logical state.
- The initial `source` is mutable, but structural modifications to source after the constructor do not add elements to Playlist's snapshot list.

**Practical note:** `List.copyOf` rejects null elements (`NullPointerException` per the API). Clearly define the domain's null policy, and do not implicitly expect null to be preserved.

`List.copyOf` can reuse an input that is already unmodifiable per the API; what matters is **appropriate unmodifiable/snapshot semantics**, not a guarantee of always creating a new object with a different identity.

## 13. `Collections.unmodifiableList` Is a View, Not Necessarily a Snapshot

These two APIs are easily conflated:

```java
List<String> view =
        java.util.Collections.unmodifiableList(source);
```

`view` **does not allow mutation through the view itself**, but it still reflects structural changes made directly to the underlying `source` list. Therefore, `unmodifiableList(source)` by itself **does not create a snapshot**.

### Runnable Comparison Example

File **`ViewVersusCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVersusCopyDemo {
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
javac ViewVersusCopyDemo.java
java ViewVersusCopyDemo
```

```text
view=[A, B]
copy=[A]
```

When a snapshot is needed and you want to use `Collections.unmodifiableList`, you can wrap **a separate copy**:

```java
List<String> snapshot =
        Collections.unmodifiableList(new ArrayList<>(source));
```

This is a **code snippet inside a method** where `source` already exists; full `java.util.*` imports can be used when needed. The caller cannot mutate the snapshot list through its API and also does not hold an alias to the internal copied list if it only receives the wrapper.

However, even a structural snapshot is still a **shallow copy** with respect to mutable elements.

## 14. Shallow Immutability: `List.copyOf` Does Not Freeze Elements

A list may disallow `add`, yet the **objects inside the list can still be mutable**.

File **`ShallowListDemo.java`**:

```java
import java.util.List;

public class ShallowListDemo {
    public static void main(String[] args) {
        StringBuilder text = new StringBuilder("A");
        List<StringBuilder> list = List.copyOf(List.of(text));

        text.append("B");

        System.out.println(list.get(0).toString());

        try {
            list.add(new StringBuilder("C"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("structure is unmodifiable");
        }
    }
}
```

```bash
javac ShallowListDemo.java
java ShallowListDemo
```

```text
AB
structure is unmodifiable
```

- `List.copyOf` keeps a reference to the `StringBuilder` element.
- The caller can mutate `text` to AB; `list.get(0)` observes AB.
- The list structure does not allow add, yet the element state still changes.

**Deeper design:** use an immutable element type like `String`, a record with immutable components, or create a **deep copy**/snapshot for each mutable element if the domain requires it. Do not call a class “fully immutable” when a nested mutable object can still be modified through an alias.

### How Shallow and Deep Copies Differ

- **Shallow copy**: copies the container, keeping references to the elements.
- **Deep copy**: also copies the necessary mutable parts of the object graph according to the contract.
- A deep copy is not a single built-in operation that works correctly for every graph, especially when there are cycles, shared identity, or external resources.
- Immutability is usually easiest to achieve by **storing immutable value components**, limiting the number of mutable objects that must be copied.

## 15. Initializing `private final int[][]` Requires Copying to the Right Depth

A field can be assigned once yet still point to a **mutable graph**. With a two-dimensional array `int[][]`, calling `source.clone()` only creates a new **outer array**; each `int[]` row can still be the same object as in source:

~~~java
int[][] source = {{1, 2}, {3}};
int[][] shallow = source.clone();
source[0][0] = 99;
// shallow[0][0] == 99, because row 0 still points to the same subarray.
~~~

This is a fragment used inside a method. If an immutable value snapshot is desired, the constructor must completely initialize the field by copying each row:

~~~java
private final int[][] rows;

Matrix(int[][] source) {
    java.util.Objects.requireNonNull(source, "source");
    int[][] copy = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        copy[i] = java.util.Objects.requireNonNull(
                source[i], "row").clone();
    }
    rows = copy;
}
~~~

The constructor/field snippet above belongs to **a `Matrix` class**, not a standalone runnable file. If the class provides an accessor returning `int[][]`, the accessor also needs to copy the outer array + each inner array before returning. For **arrays containing mutable objects**, copying each reference is not enough; you must choose an immutable representation or copy each element according to the contract.

**Scope boundary:** this lesson focuses on `private final rows` being **completely initialized with a safe representation**. The matrix deep-copy program and multi-level shallow/deep comparison are in the lesson **“Shallow Immutability and Deep Immutability”**; input/output tests and nested aliases are in the lesson **“Testing Immutability When a Class Contains Arrays or Collections”**.

## 16. Mutable `Date`: Copying in the Constructor and Getter

`java.util.Date` is a mutable class; it has a `setTime` method. Merely holding `private final Date createdAt` does not prevent others from modifying that Date object.

File **`ImmutableTimestampDemo.java`**:

```java
import java.util.Date;
import java.util.Objects;

final class Timestamp {
    private final Date moment;

    Timestamp(Date input) {
        Objects.requireNonNull(input);
        moment = new Date(input.getTime());
    }

    Date moment() {
        return new Date(moment.getTime());
    }

    long epochMillis() {
        return moment.getTime();
    }
}

public class ImmutableTimestampDemo {
    public static void main(String[] args) {
        Date input = new Date(1000L);
        Timestamp stamp = new Timestamp(input);

        input.setTime(2000L);
        System.out.println(stamp.epochMillis());

        Date extracted = stamp.moment();
        extracted.setTime(3000L);
        System.out.println(stamp.epochMillis());
    }
}
```

```bash
javac ImmutableTimestampDemo.java
java ImmutableTimestampDemo
```

```text
1000
1000
```

- The constructor copies the value from the mutable `Date` using `new Date(input.getTime())`.
- The getter returns a new Date, not the internal `moment`.
- A getter returning a `long` epoch also does not expose a mutable reference.

**Modern alternative:** if suitable for the domain, use `java.time.Instant`/`LocalDate`/`LocalDateTime` — these are immutable date-time value types in Java 17, which are usually easier to design with than `Date`.

**Condition:** The example assumes the caller does not mutate `Date input` concurrently while the constructor reads `getTime()`; thread-safe handoff needs to be handled separately if the input is being shared.

## 17. A `final` Class Helps Prevent Subclasses from Breaking the Observable Contract

Suppose a base class defines an API that returns a value but allows subclasses to override that method:

```java
class BasePrice {
    private final int amount;

    BasePrice(int amount) {
        this.amount = amount;
    }

    int amount() {
        return amount;
    }
}
```

If `BasePrice` is not final, a subclass can hold its own mutable field and override `amount()` to return changing values, causing users viewing it through a `BasePrice` reference to observe different state over time.

Therefore, a simple immutable value class should generally be a `final class`.

However, **a `final` class alone is not enough**: a class can contain mutable fields, lists, or callbacks. And a carefully designed abstract base class can still have immutable concrete subclasses — not every immutability model requires final at the root of the hierarchy.

### Avoid Calling Overridable Methods in a Constructor

A superclass constructor calling a method that can be overridden will dispatch to the subclass **while the subclass fields have not finished initializing**, violating invariant reasoning. Designing immutable classes usually avoids such overridable hooks during construction and does not let `this` escape early.

## 18. `this` Escaping Before the Constructor Completes Is a Risk

Example of a dangerous design:

```java
class Registry {
    static final java.util.List<Object> ALL =
            new java.util.ArrayList<>();
}

class Leaky {
    private final String name;

    Leaky(String name) {
        Registry.ALL.add(this); // Publishes the object before name is assigned.
        this.name = name;
    }
}
```

This is a **declaration illustrating an anti-pattern**, has no `main`, and should not be used in practice.

Even though the compiler accepts that the final field is definitely assigned before the constructor returns, `this` is written into the registry **before `name` is assigned**. External code can observe the incompletely constructed object, and in a multithreaded program there are additional publication/visibility risks.

Common escape paths:

- Registering `this` in a static collection.
- Registering a callback/listener from the constructor.
- Passing `this` to a component that might store it or call overridable methods.
- Starting a thread in the constructor with code that closes over `this`.
- Publishing the reference to a shared field without appropriate synchronization/handoff.

**Principle:** Complete validation and assignment before letting other components use the object; better yet, let a factory or the caller publish/register the object **after the constructor returns**.

## 19. Immutability and Thread Safety Are Related, Not Identical

An object designed to be immutable and safely shared has a major advantage: multiple threads only read the same state without needing a lock for each getter.

However, to be precise:

- Java has special **final field semantics** in the Java Memory Model that ensure proper visibility of final fields after construction according to the rules, when the object **is constructed properly**.
- If `this` escapes before the constructor completes, the guarantees related to final fields may no longer apply as expected.
- A `final` field does not make **mutable referenced objects** thread-safe.
- If a class holds a mutable cache or internally updates a collection, it may **no longer be immutable**.
- When publishing an immutable object through concurrent infrastructure (queues, volatile references, synchronized handoff), you must follow the contract of the publication mechanism; do not equate immutability with arbitrarily sharing a partially constructed object.

### Example of Reading an Immutable Value Object Across Multiple Threads

File **`ImmutableConcurrentReadDemo.java`**:

```java
final class Pair {
    private final int left;
    private final int right;

    Pair(int left, int right) {
        this.left = left;
        this.right = right;
    }

    int sum() {
        return left + right;
    }
}

public class ImmutableConcurrentReadDemo {
    public static void main(String[] args) throws InterruptedException {
        Pair pair = new Pair(10, 20);

        Runnable reader = () -> {
            if (pair.sum() != 30) {
                throw new AssertionError("unexpected sum");
            }
        };

        Thread a = new Thread(reader);
        Thread b = new Thread(reader);

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("shared value=" + pair.sum());
    }
}
```

```bash
javac ImmutableConcurrentReadDemo.java
java ImmutableConcurrentReadDemo
```

```text
shared value=30
```

The Pair object is completely created before the threads start. Both readers only call a pure method returning the sum from primitive final fields, without modifying the object. Calling `start`/`join` participates in happens-before relationships according to the Thread API. There is no print ordering from worker threads, so stdout is consistent.

**This does not prove that every `final` reference graph is thread-safe.** If Pair contained a shared mutable `ArrayList` and returned it externally, the situation would be completely different.

## 20. Derived Values: Compute on Demand or Cache?

An immutable class can compute derived values from its fields:

```java
final class Rectangle {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        if (width < 0 || height < 0) {
            throw new IllegalArgumentException("negative size");
        }
        this.width = width;
        this.height = height;
    }

    long area() {
        return (long) width * height;
    }
}
```

Here `area()` **does not change observable state** and can be recomputed on demand. Using `long` multiplication after a cast avoids `int*int` overflow in the case of large dimensions.

If the computation is very expensive, you can **precompute** the result in the constructor and store it in another final field:

```java
private final long area;
```

However, it is not necessary to create a mutable lazy cache inside an immutable object. A lazily updated `private long cachedArea` does not change the business value if carefully encapsulated, but introduces additional requirements for thread safety, visibility, and publication.

**Default rule for this lesson:** Compute from final fields or precompute before the constructor completes; only optimize with caching after measuring and having a clear concurrency contract.

## 21. `equals` and `hashCode` on an Immutable Value Class

Immutable objects are often suitable keys for `HashMap`/`HashSet` because the fields used for equality/hashCode do not change after creation.

File **`ImmutableKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

final class Key {
    private final String region;
    private final String code;

    Key(String region, String code) {
        this.region = Objects.requireNonNull(region);
        this.code = Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Key key)) {
            return false;
        }
        return region.equals(key.region)
                && code.equals(key.code);
    }

    @Override
    public int hashCode() {
        return Objects.hash(region, code);
    }
}

public class ImmutableKeyDemo {
    public static void main(String[] args) {
        Map<Key, String> items = new HashMap<>();

        items.put(new Key("VN", "P1"), "product");
        System.out.println(items.get(new Key("VN", "P1")));
        System.out.println(items.containsKey(new Key("US", "P1")));
    }
}
```

```bash
javac ImmutableKeyDemo.java
java ImmutableKeyDemo
```

```text
product
false
```

- Two `new Key("VN","P1")` instances are references with different identities, yet value-equal.
- `equals`/`hashCode` are based on the same two final immutable String fields.
- A HashMap lookup using a new instance with an equivalent value still satisfies the contract.
- Key has no setters and contains no mutable components, so equality/hash are stable.

**Do not infer that every immutable class must override equals.** If domain semantics require distinguishing the identity of each instance, identity equality may still be the right choice. Immutability and value equality support each other, but they are not the same concept.

## 22. Java `record` Reduces Boilerplate, but Immutability Is Only Shallow

In Java 17, a record automatically has final component fields, a canonical constructor, component accessors, and equals/hashCode/toString according to the rules. It is a good tool for immutable-ish data carriers.

Example:

```java
record Point(int x, int y) {
}
```

The two primitive fields are immutable by record design, with no setters and no external mutable state.

However:

```java
record Numbers(int[] values) {
}
```

will **not automatically clone the array** in the constructor or accessor. Therefore, the record object can be affected if the caller mutates the input array and can expose the mutable internal reference. A record also does not automatically perform deep array content comparison in its generated equals.

### Record with Defensive Copying

File **`SafeRecordArrayDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record SafeNumbers(int[] values) {
    SafeNumbers {
        Objects.requireNonNull(values);
        values = values.clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    public int at(int index) {
        return values[index];
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class SafeRecordArrayDemo {
    public static void main(String[] args) {
        int[] input = {1, 2};
        SafeNumbers numbers = new SafeNumbers(input);

        input[0] = 99;
        System.out.println(numbers);

        int[] copy = numbers.values();
        copy[1] = 77;
        System.out.println(numbers);
        System.out.println(numbers.at(0));
    }
}
```

```bash
javac SafeRecordArrayDemo.java
java SafeRecordArrayDemo
```

```text
[1, 2]
[1, 2]
1
```

In the **compact constructor**, assigning `values=values.clone()` updates the constructor parameter variable; the record will store that snapshot into the component field according to the rules of compact constructors. The `values()` accessor returns a copy.

**Important note:** The auto-generated `equals`/`hashCode` of a record with an array component still uses identity semantics for the array component. If **logical content equality** of SafeNumbers is needed, you must override equals/hashCode accordingly with `Arrays.equals`/`Arrays.hashCode` and carefully verify the contract. Defensive copying **does not automatically fix** the equality of array fields.

## 23. Java `Map.copyOf` and `Set.copyOf` Are Also Shallow Immutable Snapshots

Similar to `List.copyOf`, APIs such as `Map.copyOf` and `Set.copyOf` create unmodifiable structures according to their contracts, but **do not deep-copy mutable elements/values**.

Example:

```java
Map<String, String> source = new java.util.HashMap<>();
source.put("A", "one");

Map<String, String> snapshot = Map.copyOf(source);
source.put("B", "two");
```

This is a **code snippet** for which `import java.util.Map;` is appropriate when placed inside a method. `snapshot` does not automatically add mapping B from source after the snapshot is created. Because keys/values in the example are immutable Strings, it is a convenient snapshot.

On the contrary, if the value is a mutable `StringBuilder`, the caller can still mutate the contents of the builder referenced by both source and snapshot.

**Design rule:** “Unmodifiable container” does not mean “deeply immutable data graph”. You must inspect **mutable keys/values, aliasing, and element types**.

## 24. Builder: Gather Mutable Configuration, Then Construct an Immutable Object

When there are many fields, a long constructor makes it easy to misread the argument order. A mutable **builder** can hold temporary configuration, while the final object remains immutable.

Example file **`ImmutableBuilderDemo.java`**:

```java
final class ServerConfig {
    private final String host;
    private final int port;
    private final boolean tls;

    private ServerConfig(String host, int port, boolean tls) {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("host required");
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("invalid port");
        }

        this.host = host;
        this.port = port;
        this.tls = tls;
    }

    static Builder builder() {
        return new Builder();
    }

    String summary() {
        return host + ":" + port + ",tls=" + tls;
    }

    static final class Builder {
        private String host;
        private int port = 8080;
        private boolean tls;

        Builder host(String host) {
            this.host = host;
            return this;
        }

        Builder port(int port) {
            this.port = port;
            return this;
        }

        Builder tls(boolean tls) {
            this.tls = tls;
            return this;
        }

        ServerConfig build() {
            return new ServerConfig(host, port, tls);
        }
    }
}

public class ImmutableBuilderDemo {
    public static void main(String[] args) {
        ServerConfig config = ServerConfig.builder()
                .host("localhost")
                .port(8443)
                .tls(true)
                .build();

        System.out.println(config.summary());
    }
}
```

```bash
javac ImmutableBuilderDemo.java
java ImmutableBuilderDemo
```

```text
localhost:8443,tls=true
```

**Lifecycle distinction:**

- `Builder` is a mutable object for step-by-step configuration.
- `ServerConfig` is created via a private constructor and validated before completion.
- `ServerConfig` has three private final fields and provides no setters.
- Modifying the Builder after `build` does not change the created config, because in this example config stores String/primitive values independent of the mutable Builder.

If the Builder holds mutable collections and passes references directly into the immutable object, you still must **snapshot/copy in `build`/the constructor**. A Builder **does not replace defensive copying**.

## 25. Static Factory and Modifications via New Objects

An immutable class can use a **static factory** instead of a public constructor to name the business intent:

```java
final class Money {
    private final long cents;

    private Money(long cents) {
        this.cents = cents;
    }

    static Money ofCents(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("negative");
        }
        return new Money(cents);
    }

    Money plus(Money other) {
        return new Money(Math.addExact(cents, other.cents));
    }

    long cents() {
        return cents;
    }
}
```

This is a **valid class declaration** without `main`. Points to consider:

- `ofCents` validates non-negative input.
- `plus` returns a new Money, without mutating the receiver.
- However, `plus` currently calls the private constructor directly and **does not check that the sum is non-negative**. Since the operands under the current contract are non-negative, the sum is also non-negative barring overflow (which `Math.addExact` catches), so the invariant still holds.
- If subtraction or other operations exist, they must ensure they do not create a Money with invalid state.

**Summary:** When choosing an immutable design, every factory and arithmetic method that creates a new instance must uphold the **same invariant**, not just the first public constructor.

## 26. Distinguishing an Immutable Class from an Unmodifiable View and a Read-Only Interface

These three terms are not synonymous:

- **Immutable object:** observable state does not change after construction.
- **Unmodifiable view:** the caller cannot mutate **through the view**, but the backing source can change and the view sees those changes.
- **Read-only interface:** the interface only declares query methods, but the implementation may still have its state mutated by other callers or background jobs.

For example, a `List` returned from `Collections.unmodifiableList(source)` can still reflect additions/removals made through `source`. Similarly, `private final Repository repository` with a `read()` method does not prove that the state held by repository is immutable.

Ask yourself:

1. Who holds a reference to the backing mutable object?
2. How many paths can modify the state?
3. Does the getter return an internal alias?
4. Is there a background updater, callback, cache, or lazy evaluation affecting the observable result?
5. Are there nested mutable elements?

A truly immutable class may contain complex *implementation details*, but must guarantee that the observable state contract remains stable under every valid caller operation.

## 27. Avoiding Constructors That Leave Work Incomplete

Some common mistakes:

- Assigning one field and then invoking a callback before assigning the remaining fields.
- Putting `this` into a collection inside the constructor.
- Using a setter to “complete” the state after the constructor returns.
- Allowing an instance with nullable mandatory fields as a temporary phase.
- Reading a mutable input multiple times across validation and copying steps when the input could be modified from another thread.
- Calling an overridable method in a superclass constructor, causing unready subclass state to be observed.
- Performing I/O or side effects that are not rolled back when the constructor fails partway through.

**Better design:** validate and snapshot inputs, construct the state inside the constructor, and then **publish only the completed object**. If a multi-step configuration process is needed, use a Builder/Factory to separate the mutable build phase from the final immutable instance.

## 28. Null Policy and Normalization Must Be Explicit

An immutable class does not necessarily forbid null in every field, but it **must define the contract**:

- Mandatory non-null field → `Objects.requireNonNull` or a clear domain exception.
- Optional field → may be null per the contract, or use an appropriate type to express absence.
- String code → should it be trimmed/uppercased before storing or kept as-is?
- Collections → are null elements allowed? `List.copyOf` does not allow them.
- Date/time → should timezone or resolution be normalized?

Example:

```java
final class UserId {
    private final String value;

    UserId(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        value = raw.trim().toUpperCase(java.util.Locale.ROOT);
    }

    String value() {
        return value;
    }
}
```

This is a valid class without `main`. Normalizing **before storing into the final field** ensures every instance stores a consistent, valid representation.

**Warning:** Do not assume `trim`/uppercase is the right business normalization for every identifier, especially with Unicode/case-sensitive IDs. That is a domain-specific policy; the example only illustrates where to place normalization.

## 29. Testing: Verify Immutability Through Aliasing, Not Just Getters

A class with proper getters can still be mutated through an input array or a returned list. Immutability tests need to verify **alias paths**.

File **`ImmutableContractTestDemo.java`**:

```java
import java.util.Arrays;

final class Snapshot {
    private final int[] values;

    Snapshot(int[] input) {
        if (input == null) {
            throw new IllegalArgumentException("null input");
        }
        values = input.clone();
    }

    int[] values() {
        return values.clone();
    }
}

public class ImmutableContractTestDemo {
    static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("immutability failure");
        }
    }

    public static void main(String[] args) {
        int[] original = {1, 2};
        Snapshot snapshot = new Snapshot(original);

        original[0] = 99;
        check(Arrays.equals(snapshot.values(), new int[]{1, 2}));

        int[] leaked = snapshot.values();
        leaked[1] = 77;
        check(Arrays.equals(snapshot.values(), new int[]{1, 2}));

        int[] firstRead = snapshot.values();
        int[] secondRead = snapshot.values();
        check(firstRead != secondRead);

        System.out.println("immutable snapshot checks passed");
    }
}
```

```bash
javac ImmutableContractTestDemo.java
java ImmutableContractTestDemo
```

```text
immutable snapshot checks passed
```

This is a self-test run via `main`, not JUnit. It proves that the snapshot avoids the attempted alias mutations. For nested graphs or concurrency, additional appropriate tests are needed.

**Also test failure paths:** If the constructor receives invalid data, it must throw the appropriate exception and not publish a completed object violating the invariant. For List copies, test an input with a null element to confirm the null policy.

## 30. Summary of Common Mistakes

| Misconception / Mistake | Why Is It Incorrect? | Solution |
| --- | --- | --- |
| “`private` means immutable” | Internal methods can still mutate | Examine the entire API and fields |
| “A `final` reference makes a list immutable” | The list object can still be modified | Snapshot/unmodifiable container |
| “`final class` is enough for immutability” | The class can still have mutable state | Private final fields + no mutation + copies |
| “A blank final field has a default value so no need to assign it” | Definite assignment is mandatory | Assign in every valid constructor path |
| “Having a constructor argument is valid regardless of the data” | The compiler does not know domain invariants | Validate/normalize before completion |
| “Assigning a final field twice in a constructor is fine” | A final field cannot be reassigned | One canonical assignment point |
| “Calling `this(...)` assigns a field twice” | Constructor delegation executes initialization exactly once per instance | Do not reassign in the outer constructor |
| “Copying the array when returning it is enough” | The caller can still modify the input alias | Also copy the constructor input |
| “Copying the constructor input is enough” | The getter can expose the internal array | Copy in the getter or expose value queries |
| “`array.clone()` always deep-copies” | Nested refs still alias | Copy mutable nested parts |
| “`Collections.unmodifiableList` is a snapshot” | The view reflects source mutations | `List.copyOf` or wrap a separate copy |
| “`List.copyOf` deep-freezes elements” | Mutable elements still mutate | Immutable elements/deep copy |
| “An unmodifiable List and Date are equally immutable” | Date is still mutable | Copy Date or use `Instant` |
| “A record is automatically deeply immutable” | A record component can be a mutable reference | Compact constructor + defensive accessor |
| “A record containing an array compares contents in equals” | Array equality defaults to identity | Custom equals/hashCode if needed |
| “A mutable Builder makes the built object mutable” | Not if the built object takes an independent snapshot | Do not share mutable refs |
| “`final` fields are automatically safe across all threads” | Constructor escape and mutable graphs are dangerous | Proper construction/publication |
| “Retrieving a final field via a getter cannot mutate it” | The getter may return a mutable object | Copy/unmodifiable value components |
| “You can leave initialization incomplete and use setters” | The object appears in an invalid state | Separate Builder, complete constructor |
| “Calling a subclass override from a constructor is safe” | Subclass fields may not be initialized yet | Avoid overridable calls in constructors |
| “Every immutable class must override equals” | Equality depends on the domain | Choose identity/value semantics explicitly |
| “Every class should be immutable” | Mutable types have valid use cases | Choose based on API, performance, lifecycle |

## 31. Comprehensive Practice Exercise: Designing an Immutable `Course`

Requirements:

- `Course` has a mandatory non-blank `code` and a `topics` list containing no null/blank elements.
- The caller can mutate the input list after creation, while Course does not change.
- The getter returns a list that cannot be added to or removed from.
- Changing the topics list creates a **new Course** instead of mutating the original object.
- Readable code, using Java 17+.

File **`ImmutableCourseDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Course {
    private final String code;
    private final List<String> topics;

    Course(String code, List<String> topics) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code required");
        }
        Objects.requireNonNull(topics, "topics");

        List<String> copy = new ArrayList<>();
        for (String topic : topics) {
            if (topic == null || topic.isBlank()) {
                throw new IllegalArgumentException("invalid topic");
            }
            copy.add(topic);
        }

        this.code = code;
        this.topics = List.copyOf(copy);
    }

    String code() {
        return code;
    }

    List<String> topics() {
        return topics;
    }

    Course withTopic(String topic) {
        List<String> copy = new ArrayList<>(topics);
        copy.add(topic);
        return new Course(code, copy);
    }

    @Override
    public String toString() {
        return code + ":" + topics;
    }
}

public class ImmutableCourseDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Class");

        Course original = new Course("J17", input);
        input.add("Object");

        Course extended = original.withTopic("Constructor");

        System.out.println("input=" + input);
        System.out.println("original=" + original);
        System.out.println("extended=" + extended);

        try {
            original.topics().add("Invalid");
        } catch (UnsupportedOperationException ex) {
            System.out.println("topics are unmodifiable");
        }

        System.out.println("original remains=" + original);
    }
}
```

```bash
javac ImmutableCourseDemo.java
java ImmutableCourseDemo
```

```text
input=[Class, Object]
original=J17:[Class]
extended=J17:[Class, Constructor]
topics are unmodifiable
original remains=J17:[Class]
```

### Step One Explanation: Copy and Validate in the Constructor

- `code` must be non-null/non-blank.
- The `topics` reference must be non-null.
- The loop validates each topic and creates a new temporary list. It keeps no direct alias to `input`.
- `List.copyOf(copy)` creates an unmodifiable snapshot. Because the elements are immutable `String`s, the actual list state cannot change from the caller's side.
- The `code` and `topics` fields are `private final`, and are not reassigned after construction.

### Step Two Explanation: Input Is Mutated After Construction

The caller adds `"Object"` to `input`. `original` still contains the list `[Class]`, because the constructor created a snapshot.

### Step Three Explanation: Changes Return a New Object

`withTopic("Constructor")` creates a temporary mutable list from the old topics, adds the new topic, and constructs another Course via the constructor. The old data remains intact, while the new object has the additional topic.

### Step Four Explanation: Preventing Mutation via Getter

`topics()` returns an unmodifiable list. Calling `add("Invalid")` throws `UnsupportedOperationException`. Original remains unchanged.

**Note:** This example runs single-threaded and no other thread mutates the `topics` input during the constructor. For a shared concurrently mutable collection, achieving a consistent snapshot requires a synchronization/ownership contract; this is an issue beyond field modifiers.

## 32. Self-Practice Exercises

**Exercise 1.** Why is `private final List<String> list = new ArrayList<>()` not enough for a class to be immutable?

**Hint:** `final` only fixes the reference; a mutable list can still have its contents modified. Check public methods and getters.

**Exercise 2.** If the constructor assigns `this.values = input` for an `int[]` and the getter returns a clone, can the caller change the object?

**Answer:** Yes. The caller still holds `input` and can mutate it after the constructor; you must copy at ingress.

**Exercise 3.** What happens if the constructor copies `input.clone()` but the getter returns `values` directly?

**Answer:** The getter creates an alias path for the caller to modify the internal array; you must copy at egress or only expose value queries.

**Exercise 4.** How do `Collections.unmodifiableList(source)` and `List.copyOf(source)` differ with a mutable source?

**Answer:** The former view reflects source mutations, while copyOf snapshots the structure per its contract.

**Exercise 5.** Does `List.copyOf(List.of(new StringBuilder("A")))` guarantee that the text inside the element will not change?

**Answer:** No. The container is unmodifiable, but the StringBuilder element is still mutable if an alias remains.

**Exercise 6.** Will a blank final field that is not assigned before the constructor returns compile?

**Answer:** No, if a normal constructor path violates definite assignment rules.

**Exercise 7.** Should two overloaded constructors using `this(...)` each assign the same final field?

**Answer:** No. Assignment is usually consolidated into one primary constructor; delegation must avoid assigning a final field multiple times.

**Exercise 8.** Is `private final Date date` with a getter returning the Date itself immutable?

**Answer:** No. Date is mutable; copy at ingress/egress or use `Instant` as appropriate.

**Exercise 9.** Is `record Data(int[] values)` automatically deeply immutable?

**Answer:** No. It needs cloning/snapshotting and a custom accessor; the record's generated equals also does not deep-compare array contents.

**Exercise 10.** Is `final class` mandatory for all immutable objects?

**Answer:** Not mandatory in every architecture, but it is a simple way to prevent subclasses from breaking the observable contract when inheritance is not needed.

**Exercise 11.** Why should you not register `this` in a global registry inside the constructor before assigning final fields?

**Answer:** The object can be observed before construction completes, breaking invariants and risking broken memory visibility.

**Exercise 12.** Is `synchronized` needed on every getter of an object that has primitive final fields and is properly constructed/published?

**Answer:** Usually not needed to protect against mutation, because the object does not change. However, publication, referenced mutable objects, and other operations must be considered.

**Exercise 13.** Can `withPrice` be used to change the price of an immutable product?

**Answer:** Yes, if `withPrice` creates a new object with valid state and does not modify the original.

**Exercise 14.** Is copying an `int[][]` with `outer.clone()` enough to protect its contents?

**Answer:** No, aliases to the inner arrays remain; you must copy each inner row or design a different representation.

**Exercise 15.** For a value object with two String private final fields, what should equals/hashCode be based on?

**Answer:** The fields that determine logical equality according to the domain, with the same set of data used to compute the hash.

**Exercise 16.** If the constructor checks each field individually and they are valid, but the two fields contradict each other, is the immutable contract satisfied?

**Answer:** Not yet. You must check **invariants between fields** before the object is completely constructed.

## 33. Code Review Checklist for Immutable Classes

- [ ] Is the class `final` if inheritance does not need to be designed for?
- [ ] Do all state instance fields have appropriate `private` visibility?
- [ ] Are fields that must not change after construction declared `final`?
- [ ] Are all blank final fields definitely assigned across all constructor paths that complete normally?
- [ ] Does the constructor validate null, ranges, normalization, and cross-field invariants?
- [ ] Are there any constructor overload chains that assign a final field incorrectly or redundantly?
- [ ] Do no public/protected/package methods mutate observable state?
- [ ] Is `this` prevented from escaping before construction completes?
- [ ] Are overridable methods avoided in superclass constructors so premature observation does not occur?
- [ ] Are mutable inputs snapshotted/copied before being stored long-term?
- [ ] Is internal mutable state prevented from leaking aliases through getters?
- [ ] Are unmodifiable containers true snapshots rather than just views?
- [ ] Do nested mutable elements/arrays require deep copying or an immutable representation?
- [ ] Have `List.copyOf`/`Map.copyOf` null-element/value restrictions been accounted for?
- [ ] Do fields holding `Date`/array/StringBuilder/list have clear mutability handling?
- [ ] Has a record containing a mutable component customized its constructor/accessor if needed?
- [ ] Do `with...`/factory methods always create valid state and leave the original unchanged?
- [ ] If a lazy cache exists, are thread-safety/visibility and observable immutability guaranteed?
- [ ] If equals/hashCode exist, are they based on unchanging data according to the contract?
- [ ] Are immutable objects published across concurrency boundaries with proper semantics?
- [ ] Do tests attempt to mutate both constructor inputs and getter outputs?
- [ ] Do tests verify validation errors, copying, identity, and query results?
- [ ] Do Java 17+ examples have matching file/public class names, `javac`/`java` commands, and stdout?

---

**Final takeaway:** Designing an immutable class in Java typically starts with **`private final` instance fields and a constructor that completely initializes them and checks all invariants**. However, `final` only prevents reassigning the **field**; it does not make a mutable referenced object immutable. For an object to truly never change, **block every mutation and aliasing path**, copy arrays/`Date`/collections at the appropriate boundaries, use immutable components, never let `this` escape before the constructor completes, and understand that an unmodifiable view differs from an immutable snapshot. When a “change” is needed, create **a new object** with valid state. This is the foundation for objects that are easy to reason about, easy to test, suitable as value keys, and convenient to share safely.
